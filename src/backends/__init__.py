"""
Backend modules for screenshot analysis.

Available backends:
- ocr: EasyOCR + regex heuristics (fast, low memory)
- vlm: Vision-Language Model (smart, higher memory)
"""

from .ocr import OCRBackend
from .vlm import VLMBackend, VLM_AVAILABLE

__all__ = ["OCRBackend", "VLMBackend", "VLM_AVAILABLE"]
