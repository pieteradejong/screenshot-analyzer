"""Unit tests for OCR backend classifiers.

These tests verify the regex-based heuristic classifiers work correctly.
They don't require any ML models or external dependencies.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backends.ocr import (
    classify_content_type,
    classify_source_app,
    detect_faces,
    detect_language,
    detect_sentiment,
    extract_people,
    extract_topics,
    generate_description,
)


class TestClassifySourceApp:
    """Tests for source app classification."""

    def test_twitter_detection(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["twitter"])
        assert app == "twitter"
        assert confidence > 0.5

    def test_instagram_detection(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["instagram"])
        assert app == "instagram"
        assert confidence >= 0.4  # Sample text matches 2+ patterns

    def test_slack_detection(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["slack"])
        assert app == "slack"
        assert confidence > 0.3

    def test_terminal_detection(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["terminal"])
        assert app == "terminal"
        assert confidence > 0.3

    def test_unknown_for_empty_text(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["empty"])
        assert app == "unknown"
        assert confidence == 0.3

    def test_unknown_for_minimal_text(self, sample_texts):
        app, confidence = classify_source_app(sample_texts["minimal"])
        assert app == "unknown"

    def test_confidence_capped_at_1(self):
        # Text with many matching patterns
        text = "retweet tweet likes retweets replies follow following " * 10
        app, confidence = classify_source_app(text)
        assert confidence <= 1.0


class TestClassifyContentType:
    """Tests for content type classification."""

    def test_code_detection(self, sample_texts):
        content_type, confidence = classify_content_type(sample_texts["code"])
        assert content_type == "code"
        assert confidence > 0.5

    def test_receipt_detection(self, sample_texts):
        content_type, confidence = classify_content_type(sample_texts["receipt"])
        assert content_type == "receipt"
        assert confidence > 0.5

    def test_error_detection(self, sample_texts):
        content_type, confidence = classify_content_type(sample_texts["error"])
        assert content_type == "error_message"
        assert confidence > 0.3

    def test_conversation_detection(self, sample_texts):
        content_type, confidence = classify_content_type(sample_texts["slack"])
        # Slack text has conversation patterns
        assert content_type in ["conversation", "social_post"]

    def test_empty_text_returns_photo(self, sample_texts):
        content_type, confidence = classify_content_type(sample_texts["empty"])
        assert content_type == "photo"
        assert confidence == 0.3

    def test_short_text_returns_photo(self):
        content_type, confidence = classify_content_type("Hi there")
        assert content_type == "photo"

    def test_long_text_returns_article(self):
        long_text = "This is a very long article. " * 50
        content_type, confidence = classify_content_type(long_text)
        assert content_type == "article"


class TestDetectLanguage:
    """Tests for language detection."""

    def test_english_default(self):
        assert detect_language("Hello, how are you?") == "en"

    def test_chinese_characters(self):
        assert detect_language("你好世界") == "zh"

    def test_japanese_characters(self):
        assert detect_language("こんにちは") == "ja"

    def test_korean_characters(self):
        assert detect_language("안녕하세요") == "ko"

    def test_spanish_characters(self):
        assert detect_language("¿Cómo estás?") == "es"

    def test_french_characters(self):
        assert detect_language("Ça va très bien") == "fr"

    def test_german_characters(self):
        assert detect_language("Größe und Schönheit") == "de"

    def test_empty_text(self):
        assert detect_language("") == "unknown"


class TestDetectSentiment:
    """Tests for sentiment detection."""

    def test_positive_sentiment(self):
        assert detect_sentiment("This is great! I love it, amazing work!") == "positive"

    def test_negative_sentiment(self):
        assert (
            detect_sentiment("Error failed, this is terrible and broken") == "negative"
        )

    def test_mixed_sentiment(self):
        assert detect_sentiment("Great feature but there's an error") == "mixed"

    def test_neutral_sentiment(self):
        assert detect_sentiment("The meeting is at 3pm") == "neutral"


class TestExtractPeople:
    """Tests for @mention extraction."""

    def test_extract_mentions(self):
        text = "Hey @john and @jane, check this out!"
        people = extract_people(text)
        assert "john" in people
        assert "jane" in people

    def test_no_mentions(self):
        people = extract_people("No mentions here")
        assert people == []

    def test_duplicate_mentions(self):
        text = "@user said @user is great"
        people = extract_people(text)
        assert len(people) == 1
        assert "user" in people

    def test_limit_to_10(self):
        text = " ".join([f"@user{i}" for i in range(20)])
        people = extract_people(text)
        assert len(people) <= 10


class TestExtractTopics:
    """Tests for topic extraction."""

    def test_includes_source_and_content_type(self):
        topics = extract_topics("Some text", "twitter", "social_post")
        assert "twitter" in topics
        assert "social_post" in topics

    def test_extracts_hashtags(self):
        topics = extract_topics("Check out #python #coding", "unknown", "unknown")
        assert "python" in topics
        assert "coding" in topics

    def test_extracts_keywords(self):
        topics = extract_topics(
            "This is about finance and tech startups", "unknown", "unknown"
        )
        assert "finance" in topics
        assert "tech" in topics
        assert "startup" in topics

    def test_limit_to_5(self):
        text = "#a #b #c #d #e #f #g #h about finance tech programming design music"
        topics = extract_topics(text, "twitter", "code")
        assert len(topics) <= 5

    def test_unknown_not_included(self):
        topics = extract_topics("Hello world", "unknown", "unknown")
        assert "unknown" not in topics


class TestGenerateDescription:
    """Tests for description generation."""

    def test_no_text_description(self):
        desc = generate_description("", "twitter", "social_post", has_text=False)
        assert "twitter" in desc.lower()
        assert "no readable text" in desc.lower()

    def test_with_text_description(self):
        text = "This is a sample tweet about technology and innovation in the modern world."
        desc = generate_description(text, "twitter", "social_post", has_text=True)
        assert "Twitter" in desc
        assert "social_post" in desc

    def test_truncates_long_preview(self):
        text = "A" * 200
        desc = generate_description(text, "browser", "article", has_text=True)
        # Should truncate to ~100 chars for preview
        assert len(desc) < 200


class TestDetectFaces:
    """Tests for face detection helper."""

    def test_detect_faces_returns_bool(self):
        """Test that detect_faces returns a boolean."""
        # Create a simple solid color image (no faces)
        import io

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        result = detect_faces(image_bytes)
        assert isinstance(result, bool)

    def test_detect_faces_no_face_image(self):
        """Test that detect_faces returns False for an image without faces."""
        import io

        from PIL import Image

        # Create a simple gradient image (no faces)
        img = Image.new("RGB", (200, 200), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        result = detect_faces(image_bytes)
        assert result is False

    def test_detect_faces_handles_invalid_bytes(self):
        """Test that detect_faces fails safely on invalid image bytes."""
        result = detect_faces(b"not an image")
        assert result is False

    def test_detect_faces_handles_empty_bytes(self):
        """Test that detect_faces fails safely on empty bytes."""
        result = detect_faces(b"")
        assert result is False
