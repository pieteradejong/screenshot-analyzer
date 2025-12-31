"""Pytest fixtures for Screenshot Analyzer tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_texts():
    """Sample text snippets for testing classifiers."""
    return {
        "twitter": """
            @elonmusk just posted a new tweet about SpaceX 🚀
            2.5K Retweets  15K Likes  1.2K Replies
            Reply  Retweet  Like  Share
        """,
        "instagram": """
            photo_user Posted this amazing sunset
            ❤️ 1,234 likes
            View all 56 comments
            photo_user Great day at the beach! #sunset #vibes
            2 hours ago
        """,
        "slack": """
            #engineering
            John Smith  10:34 AM
            Hey team, the deployment is complete
            
            Reply in thread
            
            Sarah Jones  10:35 AM
            Great work! 👍
        """,
        "terminal": """
            user@macbook:~/projects$ git status
            On branch main
            Your branch is up to date with 'origin/main'.
            
            nothing to commit, working tree clean
            user@macbook:~/projects$ exit
        """,
        "code": """
            def calculate_total(items):
                total = 0
                for item in items:
                    total += item.price
                return total
            
            class ShoppingCart:
                def __init__(self):
                    self.items = []
        """,
        "receipt": """
            ACME STORE
            123 Main Street
            
            Item 1          $12.99
            Item 2          $8.50
            Subtotal        $21.49
            Tax (8%)        $1.72
            Total           $23.21
            
            Card ending in 4242
            Thank you for your purchase!
        """,
        "error": """
            Traceback (most recent call last):
              File "main.py", line 42, in <module>
                raise ValueError("Invalid input")
            ValueError: Invalid input
            
            Error: Process failed with exit code 1
        """,
        "empty": "",
        "minimal": "Hello",
    }


@pytest.fixture
def sample_image_path(temp_dir):
    """Create a minimal valid PNG image for testing."""
    # Minimal 1x1 white PNG
    png_data = bytes(
        [
            0x89,
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,  # PNG signature
            0x00,
            0x00,
            0x00,
            0x0D,
            0x49,
            0x48,
            0x44,
            0x52,  # IHDR chunk
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,  # 1x1
            0x08,
            0x02,
            0x00,
            0x00,
            0x00,
            0x90,
            0x77,
            0x53,
            0xDE,
            0x00,
            0x00,
            0x00,
            0x0C,
            0x49,
            0x44,
            0x41,  # IDAT chunk
            0x54,
            0x08,
            0xD7,
            0x63,
            0xF8,
            0xFF,
            0xFF,
            0x3F,
            0x00,
            0x05,
            0xFE,
            0x02,
            0xFE,
            0xDC,
            0xCC,
            0x59,
            0xE7,
            0x00,
            0x00,
            0x00,
            0x00,
            0x49,
            0x45,
            0x4E,  # IEND chunk
            0x44,
            0xAE,
            0x42,
            0x60,
            0x82,
        ]
    )

    img_path = temp_dir / "test_image.png"
    img_path.write_bytes(png_data)
    return img_path
