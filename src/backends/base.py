"""Base class for analysis backends."""

from abc import ABC, abstractmethod
from pathlib import Path

import torch


def get_device() -> torch.device:
    """Detect best available device: MPS (Apple Silicon) > CUDA > CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class AnalysisBackend(ABC):
    """Abstract base class for screenshot analysis backends."""

    @abstractmethod
    def analyze(self, path: Path, verbose: bool = False) -> dict:
        """
        Analyze an image and return structured metadata.

        Returns dict with keys:
            - source_app: str (twitter, instagram, slack, terminal, browser, etc.)
            - content_type: str (social_post, conversation, code, receipt, etc.)
            - has_text: bool
            - primary_text: str | None (first 500 chars of extracted text)
            - people_mentioned: list[str]
            - topics: list[str]
            - language: str
            - sentiment: str
            - description: str
            - confidence: float (0.0-1.0)
            - image_width: int
            - image_height: int
            - error: str | None (if analysis failed)
        """
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the backend (load models, etc.)."""
        pass
