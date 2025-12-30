# Screenshot Analyzer

Batch analyze screenshots using Claude Vision API. Auto-categorizes by source app, content type, extracts text, and stores structured metadata in SQLite.

## Setup
```bash
./scripts/init.sh
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage
```bash
# Test on 10 images first
python src/analyzer.py /Users/pieterdejong/screenshots --limit 10

# Run on everything (~$15-30 for 1,659 images)
python src/analyzer.py /Users/pieterdejong/screenshots

# Custom output location
python src/analyzer.py /path/to/screenshots --output ./results
```

## Output

Creates `_analysis/` folder in target directory with:
- `screenshots.db` - SQLite database
- `screenshots.json` - Full export

## Querying Results
```bash
# Breakdown by source app
sqlite3 _analysis/screenshots.db "SELECT source_app, COUNT(*) FROM screenshots GROUP BY source_app ORDER BY 2 DESC"

# Find Instagram posts
sqlite3 _analysis/screenshots.db "SELECT filename, description FROM screenshots WHERE source_app='instagram'"

# Search by topic
sqlite3 _analysis/screenshots.db "SELECT filename, topics FROM screenshots WHERE topics LIKE '%finance%'"

# Full-text search in extracted text
sqlite3 _analysis/screenshots.db "SELECT filename, primary_text FROM screenshots WHERE primary_text LIKE '%error%'"
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| source_app | text | instagram, twitter, slack, terminal, browser, etc. |
| content_type | text | social_post, conversation, code, receipt, etc. |
| primary_text | text | Extracted text (first 500 chars) |
| people_mentioned | json | @handles and names |
| topics | json | Up to 5 topic tags |
| description | text | 1-2 sentence summary |
| confidence | real | 0.0-1.0 |

## Cost

~$0.01-0.02 per image using Claude Sonnet.

