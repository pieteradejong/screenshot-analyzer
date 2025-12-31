#!/usr/bin/env python3
"""
HTML Report Generator for Screenshot Analyzer.

Generates a self-contained HTML report from the SQLite database.

Usage:
    python report.py _analysis/screenshots.db
    python report.py _analysis/screenshots.db --output report.html
"""

import argparse
import html
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

# =============================================================================
# HTML TEMPLATE
# =============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Screenshot Analysis Report</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
            line-height: 1.5;
        }}
        
        h1 {{
            text-align: center;
            margin-bottom: 10px;
            color: #fff;
        }}
        
        .stats {{
            text-align: center;
            color: #888;
            margin-bottom: 20px;
        }}

        .tabs {{
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 12px;
        }}

        .tab-btn {{
            padding: 8px 14px;
            border: none;
            border-radius: 999px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            background: #0f3460;
            color: #fff;
        }}

        .tab-btn:hover {{
            background: #1a5490;
        }}

        .tab-btn.active {{
            background: #e94560;
        }}
        
        .filters {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            margin-bottom: 20px;
            padding: 15px;
            background: #16213e;
            border-radius: 10px;
        }}
        
        .filter-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            align-items: center;
        }}
        
        .filter-label {{
            color: #888;
            font-size: 12px;
            margin-right: 5px;
        }}
        
        .filter-btn {{
            padding: 5px 12px;
            border: none;
            border-radius: 15px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
            background: #0f3460;
            color: #fff;
        }}
        
        .filter-btn:hover {{
            background: #1a5490;
        }}
        
        .filter-btn.active {{
            background: #e94560;
        }}
        
        .search-box {{
            padding: 8px 15px;
            border: none;
            border-radius: 20px;
            background: #0f3460;
            color: #fff;
            width: 200px;
            outline: none;
        }}
        
        .search-box::placeholder {{
            color: #666;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }}
        
        .card {{
            background: #16213e;
            border-radius: 10px;
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
            cursor: pointer;
        }}
        
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}
        
        .card.hidden {{
            display: none;
        }}
        
        .card-image {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            background: #0f3460;
        }}
        
        .card-body {{
            padding: 15px;
        }}
        
        .card-badges {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }}
        
        .badge {{
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 500;
        }}
        
        .badge-app {{
            background: #0f3460;
            color: #4da8da;
        }}
        
        .badge-type {{
            background: #1a3a5c;
            color: #7ec8e3;
        }}
        
        .badge-twitter {{ background: #1da1f2; color: #fff; }}
        .badge-instagram {{ background: #e1306c; color: #fff; }}
        .badge-slack {{ background: #4a154b; color: #fff; }}
        .badge-discord {{ background: #5865f2; color: #fff; }}
        .badge-terminal {{ background: #2d2d2d; color: #0f0; }}
        .badge-vscode {{ background: #007acc; color: #fff; }}
        .badge-browser {{ background: #ff7139; color: #fff; }}
        .badge-email {{ background: #ea4335; color: #fff; }}
        .badge-people {{ background: #9c27b0; color: #fff; }}
        
        .card-title {{
            font-size: 13px;
            color: #ccc;
            margin-bottom: 5px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .card-description {{
            font-size: 12px;
            color: #888;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        
        .card-confidence {{
            margin-top: 10px;
            font-size: 11px;
            color: #666;
        }}
        
        .confidence-bar {{
            height: 4px;
            background: #0f3460;
            border-radius: 2px;
            margin-top: 3px;
            overflow: hidden;
        }}
        
        .confidence-fill {{
            height: 100%;
            background: linear-gradient(90deg, #e94560, #4da8da);
            border-radius: 2px;
        }}
        
        /* Modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            overflow-y: auto;
            padding: 20px;
        }}
        
        .modal.active {{
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }}
        
        .modal-content {{
            background: #16213e;
            border-radius: 15px;
            max-width: 900px;
            width: 100%;
            margin: 20px auto;
        }}
        
        .modal-close {{
            position: fixed;
            top: 20px;
            right: 30px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
            z-index: 1001;
        }}
        
        .modal-image {{
            width: 100%;
            max-height: 500px;
            object-fit: contain;
            background: #0a0a1a;
            border-radius: 15px 15px 0 0;
        }}
        
        .modal-body {{
            padding: 25px;
        }}
        
        .modal-title {{
            font-size: 18px;
            margin-bottom: 15px;
            word-break: break-all;
        }}
        
        .modal-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        
        .meta-item {{
            background: #0f3460;
            padding: 12px;
            border-radius: 8px;
        }}
        
        .meta-label {{
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        
        .meta-value {{
            font-size: 14px;
            color: #fff;
        }}
        
        .modal-text {{
            background: #0f3460;
            padding: 15px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 200px;
            overflow-y: auto;
        }}
        
        .no-results {{
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }}
        
        .topics {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }}
        
        .topic {{
            background: #1a3a5c;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            color: #7ec8e3;
        }}
    </style>
</head>
<body>
    <h1>Screenshot Analysis Report</h1>
    <p class="stats">{stats}</p>

    <div class="tabs">
        <button class="tab-btn active" data-tab="all" onclick="setTab('all', this)">
            All ({total_count})
        </button>
        <button class="tab-btn" data-tab="people" onclick="setTab('people', this)">
            People ({has_people_count})
        </button>
    </div>
    
    <div class="filters">
        <input type="text" class="search-box" id="search" placeholder="Search descriptions...">
        
        <div class="filter-group">
            <span class="filter-label">App:</span>
            {app_filters}
        </div>
        
        <div class="filter-group">
            <span class="filter-label">Type:</span>
            {type_filters}
        </div>
        
        <div class="filter-group">
            <span class="filter-label">Features:</span>
            <button class="filter-btn" data-feature="has_text" onclick="filterByFeature('has_text', this)">Has Text ({has_text_count})</button>
            <button class="filter-btn" data-feature="has_people" onclick="filterByFeature('has_people', this)">Has People ({has_people_count})</button>
        </div>
        
        <button class="filter-btn" onclick="clearFilters()">Clear All</button>
    </div>
    
    <div class="grid" id="grid">
        {cards}
    </div>
    
    <div class="no-results" id="no-results" style="display: none;">
        No screenshots match your filters.
    </div>
    
    <div class="modal" id="modal" onclick="closeModal(event)">
        <span class="modal-close" onclick="closeModal()">&times;</span>
        <div class="modal-content" onclick="event.stopPropagation()">
            <img class="modal-image" id="modal-image" src="" alt="">
            <div class="modal-body">
                <h2 class="modal-title" id="modal-title"></h2>
                <div class="modal-meta" id="modal-meta"></div>
                <div class="modal-text" id="modal-text"></div>
            </div>
        </div>
    </div>
    
    <script>
        // Store all card data for modal
        const cardData = {card_data_json};
        
        // Filter state
        let activeTab = 'all';
        let activeApp = null;
        let activeType = null;
        let activeFeature = null;
        let searchQuery = '';
        
        // Filter functions
        function setTab(tab, btn) {{
            activeTab = tab;
            updateFilters();
            updateButtonStates();
        }}

        function filterByApp(app, btn) {{
            activeApp = activeApp === app ? null : app;
            updateFilters();
            updateButtonStates();
        }}
        
        function filterByType(type, btn) {{
            activeType = activeType === type ? null : type;
            updateFilters();
            updateButtonStates();
        }}
        
        function filterByFeature(feature, btn) {{
            activeFeature = activeFeature === feature ? null : feature;
            updateFilters();
            updateButtonStates();
        }}
        
        function clearFilters() {{
            activeApp = null;
            activeType = null;
            activeFeature = null;
            searchQuery = '';
            document.getElementById('search').value = '';
            updateFilters();
            updateButtonStates();
        }}
        
        function updateButtonStates() {{
            document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.tab === activeTab);
            }});
            document.querySelectorAll('.filter-btn[data-app]').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.app === activeApp);
            }});
            document.querySelectorAll('.filter-btn[data-type]').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.type === activeType);
            }});
            document.querySelectorAll('.filter-btn[data-feature]').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.feature === activeFeature);
            }});
        }}
        
        function updateFilters() {{
            const cards = document.querySelectorAll('.card');
            let visible = 0;
            
            cards.forEach(card => {{
                const matchesTab =
                    activeTab === 'all' ||
                    (activeTab === 'people' && card.dataset.hasPeople === '1');
                const matchesApp = !activeApp || card.dataset.app === activeApp;
                const matchesType = !activeType || card.dataset.type === activeType;
                const matchesSearch = !searchQuery || 
                    card.dataset.description.toLowerCase().includes(searchQuery) ||
                    card.dataset.text.toLowerCase().includes(searchQuery);
                
                // Feature filter (has_text, has_people)
                let matchesFeature = true;
                if (activeFeature === 'has_text') {{
                    matchesFeature = card.dataset.hasText === '1';
                }} else if (activeFeature === 'has_people') {{
                    matchesFeature = card.dataset.hasPeople === '1';
                }}
                
                if (matchesTab && matchesApp && matchesType && matchesSearch && matchesFeature) {{
                    card.classList.remove('hidden');
                    visible++;
                }} else {{
                    card.classList.add('hidden');
                }}
            }});
            
            document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
        }}
        
        // Search
        document.getElementById('search').addEventListener('input', (e) => {{
            searchQuery = e.target.value.toLowerCase();
            updateFilters();
        }});
        
        // Modal
        function openModal(id) {{
            const data = cardData[id];
            if (!data) return;
            
            document.getElementById('modal-image').src = data.filepath;
            document.getElementById('modal-title').textContent = data.filename;
            
            const meta = document.getElementById('modal-meta');
            meta.innerHTML = `
                <div class="meta-item">
                    <div class="meta-label">Source App</div>
                    <div class="meta-value">${{data.source_app || 'Unknown'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Content Type</div>
                    <div class="meta-value">${{data.content_type || 'Unknown'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Confidence</div>
                    <div class="meta-value">${{(data.confidence * 100).toFixed(0)}}%</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Dimensions</div>
                    <div class="meta-value">${{data.image_width || '?'}} × ${{data.image_height || '?'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Has Text</div>
                    <div class="meta-value">${{data.has_text ? 'Yes' : 'No'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Has People</div>
                    <div class="meta-value">${{data.has_people ? 'Yes' : 'No'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Language</div>
                    <div class="meta-value">${{data.language || 'Unknown'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Sentiment</div>
                    <div class="meta-value">${{data.sentiment || 'Neutral'}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Topics</div>
                    <div class="meta-value topics">${{(data.topics || []).map(t => `<span class="topic">${{t}}</span>`).join('')}}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">People Mentioned</div>
                    <div class="meta-value">${{(data.people_mentioned || []).map(p => '@' + p).join(', ') || 'None'}}</div>
                </div>
                <div class="meta-item" style="grid-column: 1 / -1;">
                    <div class="meta-label">File Path (click to copy)</div>
                    <div class="meta-value" style="font-family: monospace; cursor: pointer; user-select: all;" 
                         onclick="navigator.clipboard.writeText(${{JSON.stringify(data.raw_filepath)}}).then(() => this.style.color = '#4da8da'); setTimeout(() => this.style.color = '', 1000);"
                         title="Click to copy">${{data.raw_filepath || 'Unknown'}}</div>
                </div>
            `;
            
            document.getElementById('modal-text').textContent = data.primary_text || '(No text extracted)';
            document.getElementById('modal').classList.add('active');
            document.body.style.overflow = 'hidden';
        }}
        
        function closeModal(event) {{
            if (event && event.target.classList.contains('modal-content')) return;
            document.getElementById('modal').classList.remove('active');
            document.body.style.overflow = '';
        }}
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
        }});
    </script>
</body>
</html>
"""

CARD_TEMPLATE = """
<div class="card" data-id="{id}" data-app="{source_app}" data-type="{content_type}" 
     data-description="{description_escaped}" data-text="{text_escaped}"
     data-has-text="{has_text}" data-has-people="{has_people}"
     onclick="openModal({id})">
    <img class="card-image" src="{image_url}" alt="{filename}" loading="lazy"
         onerror="this.style.display='none'">
    <div class="card-body">
        <div class="card-badges">
            <span class="badge badge-app badge-{source_app}">{source_app}</span>
            <span class="badge badge-type">{content_type}</span>
            {people_badge}
        </div>
        <div class="card-title">{filename}</div>
        <div class="card-description">{description}</div>
        <div class="card-confidence">
            Confidence: {confidence_pct}%
            <div class="confidence-bar">
                <div class="confidence-fill" style="width: {confidence_pct}%"></div>
            </div>
        </div>
    </div>
</div>
"""


# =============================================================================
# REPORT GENERATOR
# =============================================================================


def load_screenshots(db_path: Path) -> list[dict]:
    """Load all screenshots from database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM screenshots 
        WHERE error IS NULL 
        ORDER BY analyzed_at DESC
    """)

    rows = []
    for row in cursor:
        data = dict(row)
        # Parse JSON fields
        for field in ["people_mentioned", "topics"]:
            if data.get(field):
                try:
                    data[field] = json.loads(data[field])
                except json.JSONDecodeError:
                    data[field] = []
            else:
                data[field] = []
        rows.append(data)

    conn.close()
    return rows


def get_app_counts(screenshots: list[dict]) -> dict[str, int]:
    """Count screenshots by source app."""
    counts = {}
    for s in screenshots:
        app = s.get("source_app") or "unknown"
        counts[app] = counts.get(app, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_type_counts(screenshots: list[dict]) -> dict[str, int]:
    """Count screenshots by content type."""
    counts = {}
    for s in screenshots:
        ctype = s.get("content_type") or "unknown"
        counts[ctype] = counts.get(ctype, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def generate_report(db_path: Path, output_path: Path) -> None:
    """Generate HTML report from database."""
    screenshots = load_screenshots(db_path)

    if not screenshots:
        print("No screenshots found in database.")
        return

    # Generate stats
    app_counts = get_app_counts(screenshots)
    type_counts = get_type_counts(screenshots)
    stats = f"{len(screenshots)} screenshots analyzed"
    total_count = len(screenshots)

    # Count feature stats
    has_text_count = sum(1 for s in screenshots if s.get("has_text"))
    has_people_count = sum(1 for s in screenshots if s.get("has_people"))

    # Generate filter buttons
    app_filters = " ".join(
        f'<button class="filter-btn" data-app="{app}" onclick="filterByApp(\'{app}\', this)">'
        f"{app} ({count})</button>"
        for app, count in list(app_counts.items())[:8]
    )

    type_filters = " ".join(
        f'<button class="filter-btn" data-type="{ctype}" onclick="filterByType(\'{ctype}\', this)">'
        f"{ctype} ({count})</button>"
        for ctype, count in list(type_counts.items())[:8]
    )

    # Generate cards
    cards = []
    card_data = {}

    for s in screenshots:
        sid = s.get("id", 0)
        filepath = s.get("filepath", "")

        # Convert to file:// URL for local viewing
        if filepath:
            image_url = "file://" + quote(filepath)
        else:
            image_url = ""

        # has_text and has_people as 1/0 for data attributes
        has_text = 1 if s.get("has_text") else 0
        has_people = 1 if s.get("has_people") else 0

        # Generate people badge if has_people
        people_badge = (
            '<span class="badge badge-people">👤 people</span>' if has_people else ""
        )

        card = CARD_TEMPLATE.format(
            id=sid,
            source_app=s.get("source_app") or "unknown",
            content_type=s.get("content_type") or "unknown",
            filename=html.escape(s.get("filename") or ""),
            description=html.escape(s.get("description") or ""),
            description_escaped=html.escape(s.get("description") or "").replace(
                '"', "&quot;"
            ),
            text_escaped=html.escape(s.get("primary_text") or "")[:200].replace(
                '"', "&quot;"
            ),
            image_url=image_url,
            confidence_pct=int((s.get("confidence") or 0) * 100),
            has_text=has_text,
            has_people=has_people,
            people_badge=people_badge,
        )
        cards.append(card)

        # Store data for modal
        card_data[sid] = {
            "id": sid,
            "filepath": image_url,
            "raw_filepath": filepath,
            "filename": s.get("filename"),
            "source_app": s.get("source_app"),
            "content_type": s.get("content_type"),
            "description": s.get("description"),
            "primary_text": s.get("primary_text"),
            "confidence": s.get("confidence") or 0,
            "language": s.get("language"),
            "sentiment": s.get("sentiment"),
            "topics": s.get("topics") or [],
            "people_mentioned": s.get("people_mentioned") or [],
            "image_width": s.get("image_width"),
            "image_height": s.get("image_height"),
            "has_text": bool(has_text),
            "has_people": bool(has_people),
        }

    # Generate final HTML
    html_content = HTML_TEMPLATE.format(
        stats=stats,
        app_filters=app_filters,
        type_filters=type_filters,
        cards="\n".join(cards),
        card_data_json=json.dumps(card_data),
        has_text_count=has_text_count,
        has_people_count=has_people_count,
        total_count=total_count,
    )

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Report generated: {output_path}")


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML report from screenshot analysis database"
    )
    parser.add_argument(
        "database",
        type=Path,
        help="Path to screenshots.db",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output HTML file (default: same directory as database)",
    )

    args = parser.parse_args()

    if not args.database.exists():
        print(f"Error: Database not found: {args.database}")
        return 1

    output_path = args.output or args.database.parent / "report.html"
    generate_report(args.database, output_path)
    return 0


if __name__ == "__main__":
    exit(main())
