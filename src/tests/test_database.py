"""Tests for database operations."""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import cleanup_deleted_files, init_db, save_result


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

    def test_init_db_has_people_column(self, temp_dir):
        """Test that init_db creates has_people column in schema."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        cursor = conn.execute("PRAGMA table_info(screenshots)")
        columns = {row[1] for row in cursor.fetchall()}

        assert "has_people" in columns

        conn.close()

    def test_init_db_idempotent(self, temp_dir):
        """Test that init_db can be called multiple times safely."""
        db_path = temp_dir / "test.db"

        conn1 = init_db(db_path)
        conn1.close()

        # Should not raise
        conn2 = init_db(db_path)
        conn2.close()

    def test_init_db_migrates_has_people(self, temp_dir):
        """Test that init_db migrates has_people column to older databases."""
        import sqlite3

        db_path = temp_dir / "test.db"

        # Create an "old" database without has_people column but with the
        # columns that indexes are created on (source_app, content_type, topics)
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE screenshots (
                id INTEGER PRIMARY KEY,
                filepath TEXT UNIQUE,
                filename TEXT,
                source_app TEXT,
                content_type TEXT,
                topics TEXT,
                image_width INTEGER,
                image_height INTEGER,
                backend TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Now call init_db which should migrate
        conn = init_db(db_path)

        cursor = conn.execute("PRAGMA table_info(screenshots)")
        columns = {row[1] for row in cursor.fetchall()}

        assert "has_people" in columns

        conn.close()

    def test_save_result(self, temp_dir, sample_image_path):
        """Test saving analysis results."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        analysis = {
            "source_app": "twitter",
            "content_type": "social_post",
            "has_text": True,
            "has_people": True,
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

    def test_save_result_has_people(self, temp_dir, sample_image_path):
        """Test that has_people is persisted correctly."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Test with has_people=True
        analysis = {
            "source_app": "instagram",
            "has_people": True,
        }
        save_result(conn, sample_image_path, analysis, "ocr")

        cursor = conn.execute(
            "SELECT has_people FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1  # True stored as 1

        # Test with has_people=False (create a new file path)
        analysis2 = {
            "source_app": "twitter",
            "has_people": False,
        }
        fake_path = temp_dir / "no_people.png"
        fake_path.write_bytes(sample_image_path.read_bytes())
        save_result(conn, fake_path, analysis2, "ocr")

        cursor = conn.execute(
            "SELECT has_people FROM screenshots WHERE filepath = ?",
            (str(fake_path),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 0  # False stored as 0

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


class TestDeletionDetection:
    """Tests for deletion detection functionality."""

    def test_cleanup_deleted_files_marks_deleted(self, temp_dir, sample_image_path):
        """Test that cleanup_deleted_files marks deleted files with error."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Save a file
        save_result(conn, sample_image_path, {"source_app": "twitter"}, "ocr")

        # Delete the file
        sample_image_path.unlink()

        # Run cleanup
        deleted_count = cleanup_deleted_files(conn, [temp_dir], remove_from_db=False)

        assert deleted_count == 1

        # Check that file is marked with error
        cursor = conn.execute(
            "SELECT error FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] is not None
        assert "File deleted" in row[0]

        conn.close()

    def test_cleanup_deleted_files_removes_when_flag_set(
        self, temp_dir, sample_image_path
    ):
        """Test that cleanup_deleted_files removes records when remove_from_db=True."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Save a file
        save_result(conn, sample_image_path, {"source_app": "twitter"}, "ocr")

        # Delete the file
        sample_image_path.unlink()

        # Run cleanup with remove_from_db=True
        deleted_count = cleanup_deleted_files(conn, [temp_dir], remove_from_db=True)

        assert deleted_count == 1

        # Check that record is removed
        cursor = conn.execute(
            "SELECT COUNT(*) FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        assert cursor.fetchone()[0] == 0

        conn.close()

    def test_cleanup_deleted_files_ignores_existing_files(
        self, temp_dir, sample_image_path
    ):
        """Test that cleanup_deleted_files doesn't affect existing files."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Save a file that exists
        save_result(conn, sample_image_path, {"source_app": "twitter"}, "ocr")

        # Run cleanup
        deleted_count = cleanup_deleted_files(conn, [temp_dir], remove_from_db=False)

        assert deleted_count == 0

        # Check that file is still there without error
        cursor = conn.execute(
            "SELECT error FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] is None  # No error

        conn.close()

    def test_cleanup_deleted_files_handles_multiple_deletions(
        self, temp_dir, sample_image_path
    ):
        """Test cleanup with multiple deleted files."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Create and save multiple files
        file1 = temp_dir / "image1.png"
        file2 = temp_dir / "image2.png"
        file3 = temp_dir / "image3.png"

        # Copy sample image to create multiple files
        file1.write_bytes(sample_image_path.read_bytes())
        file2.write_bytes(sample_image_path.read_bytes())
        file3.write_bytes(sample_image_path.read_bytes())

        save_result(conn, file1, {"source_app": "twitter"}, "ocr")
        save_result(conn, file2, {"source_app": "instagram"}, "ocr")
        save_result(conn, file3, {"source_app": "slack"}, "ocr")

        # Delete two files
        file1.unlink()
        file3.unlink()

        # Run cleanup
        deleted_count = cleanup_deleted_files(conn, [temp_dir], remove_from_db=False)

        assert deleted_count == 2

        # Check that deleted files are marked
        cursor = conn.execute(
            "SELECT COUNT(*) FROM screenshots WHERE error IS NOT NULL"
        )
        assert cursor.fetchone()[0] == 2

        # Check that existing file is untouched
        cursor = conn.execute(
            "SELECT error FROM screenshots WHERE filepath = ?",
            (str(file2),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] is None  # No error

        conn.close()

    def test_cleanup_deleted_files_ignores_already_marked_errors(
        self, temp_dir, sample_image_path
    ):
        """Test that cleanup doesn't re-process files already marked with errors."""
        db_path = temp_dir / "test.db"
        conn = init_db(db_path)

        # Save a file with an error
        analysis = {"error": "Processing failed"}
        save_result(conn, sample_image_path, analysis, "ocr")

        # Delete the file
        sample_image_path.unlink()

        # Run cleanup
        deleted_count = cleanup_deleted_files(conn, [temp_dir], remove_from_db=False)

        # Should return 0 because file already has error (not in WHERE error IS NULL)
        assert deleted_count == 0

        # Original error should still be there
        cursor = conn.execute(
            "SELECT error FROM screenshots WHERE filepath = ?",
            (str(sample_image_path),),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Processing failed"  # Original error preserved

        conn.close()
