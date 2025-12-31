"""Tests for database operations."""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import init_db, save_result


class TestDatabase:
    """Tests for SQLite database operations."""

    def test_init_db_creates_table(self, temp_dir):
        """Test that init_db creates the screenshots table."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='screenshots'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_init_db_creates_indexes(self, temp_dir):
        """Test that init_db creates indexes."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_source_app" in indexes
        assert "idx_content_type" in indexes
        assert "idx_topics" in indexes

        conn.close()

    def test_init_db_idempotent(self, temp_dir):
        """Test that init_db can be called multiple times safely."""
        db_path = temp_dir / "test.db"

        conn1 = init_db(db_path)
        conn1.close()

        # Should not raise
        conn2 = init_db(db_path)
        conn2.close()

    def test_save_result(self, temp_dir, sample_image_path):
        """Test saving analysis results."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        analysis = {
            "source_app": "twitter",
            "content_type": "social_post",
            "has_text": True,
            "primary_text": "Hello world",
            "people_mentioned": ["user1", "user2"],
            "topics": ["tech", "twitter"],
            "language": "en",
            "sentiment": "positive",
            "description": "A tweet about tech",
            "confidence": 0.85,
            "image_width": 1920,
            "image_height": 1080,
        }

        save_result(conn, sample_image_path, analysis, "ocr")

        # Verify saved
        cursor = conn.execute(
            "SELECT source_app, content_type, backend FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "twitter"
        assert row[1] == "social_post"
        assert row[2] == "ocr"

        conn.close()

    def test_save_result_json_fields(self, temp_dir, sample_image_path):
        """Test that JSON fields are properly serialized."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        analysis = {
            "source_app": "slack",
            "people_mentioned": ["alice", "bob"],
            "topics": ["engineering", "slack"],
        }

        save_result(conn, sample_image_path, analysis, "ocr")

        cursor = conn.execute(
            "SELECT people_mentioned, topics FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()

        people = json.loads(row[0])
        topics = json.loads(row[1])

        assert people == ["alice", "bob"]
        assert topics == ["engineering", "slack"]

        conn.close()

    def test_save_result_with_error(self, temp_dir, sample_image_path):
        """Test saving results with errors."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        analysis = {"error": "Failed to process image"}

        save_result(conn, sample_image_path, analysis, "vlm")

        cursor = conn.execute(
            "SELECT error, backend FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()

        assert row[0] == "Failed to process image"
        assert row[1] == "vlm"

        conn.close()

    def test_save_result_upsert(self, temp_dir, sample_image_path):
        """Test that saving same filepath updates existing row."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # First save
        save_result(conn, sample_image_path, {"source_app": "twitter"}, "ocr")

        # Second save (should update)
        save_result(conn, sample_image_path, {"source_app": "instagram"}, "vlm")

        # Should only have one row
        cursor = conn.execute("SELECT COUNT(*) FROM screenshots")
        assert cursor.fetchone()[0] == 1

        # Should have updated values
        cursor = conn.execute(
            "SELECT source_app, backend FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()
        assert row[0] == "instagram"
        assert row[1] == "vlm"

        conn.close()
