"""
VLM Backend: Vision-Language Model for semantic screenshot analysis.

Uses local models (Moondream2, Qwen2-VL, etc.) for smart understanding.
Slower but much better quality than regex heuristics.

Requirements:
    pip install transformers accelerate
"""

import json
import re
from pathlib import Path

from PIL import Image

from .base import AnalysisBackend, get_device

# Check if transformers is available
VLM_AVAILABLE = False
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    VLM_AVAILABLE = True
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None


# Default model - Moondream2 is small and efficient
DEFAULT_MODEL = "vikhyatk/moondream2"

# Prompt for structured extraction
ANALYSIS_PROMPT = """Analyze this screenshot and extract the following information.
Return ONLY valid JSON with these fields:

{
  "source_app": "the application this screenshot is from (twitter, instagram, slack, discord, whatsapp, messages, email, terminal, vscode, browser, finder, or unknown)",
  "content_type": "type of content (social_post, conversation, code, receipt, error_message, article, settings, dashboard, form, photo, or unknown)",
  "primary_text": "main text visible in the screenshot, up to 200 characters",
  "people_mentioned": ["list", "of", "@handles", "or", "names"],
  "topics": ["up", "to", "5", "topic", "tags"],
  "description": "one sentence describing what this screenshot shows",
  "confidence": 0.85
}

Return ONLY the JSON, no other text."""


class VLMBackend(AnalysisBackend):
    """Vision-Language Model backend using Moondream2 or similar."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._device = get_device()

    def initialize(self) -> None:
        """Load the VLM model."""
        if not VLM_AVAILABLE:
            raise RuntimeError(
                "VLM backend requires 'transformers' package. "
                "Install with: pip install transformers accelerate"
            )

        if self._model is not None:
            return

        print(f"Loading VLM model: {self.model_name}")
        print(f"  Device: {self._device}")
        print("  (First run downloads the model, ~2-4GB)")

        import torch

        # Moondream2 specific loading
        if "moondream" in self.model_name.lower():
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16
                if self._device.type != "cpu"
                else torch.float32,
            ).to(self._device)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=True
            )
        else:
            # Generic loading for other models
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16
                if self._device.type != "cpu"
                else torch.float32,
                device_map="auto",
            )
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        print("  VLM ready")
        print()

    def analyze(self, path: Path, verbose: bool = False) -> dict:
        """Analyze image using the VLM."""
        self.initialize()

        try:
            # Load image
            with Image.open(path) as img:
                width, height = img.size
                # Convert to RGB if necessary
                if img.mode != "RGB":
                    img = img.convert("RGB")
                image = img.copy()

            # Generate analysis using Moondream2's interface
            if "moondream" in self.model_name.lower():
                enc_image = self._model.encode_image(image)
                response = self._model.answer_question(
                    enc_image, ANALYSIS_PROMPT, self._tokenizer
                )
            else:
                # Generic generation (may need adjustment per model)
                response = self._generate_generic(image)

            # Parse JSON from response
            result = self._parse_response(response, verbose)

            # Add image dimensions
            result["image_width"] = width
            result["image_height"] = height
            result["has_text"] = bool(result.get("primary_text"))

            # Ensure all required fields exist
            result.setdefault("source_app", "unknown")
            result.setdefault("content_type", "unknown")
            result.setdefault("primary_text", None)
            result.setdefault("people_mentioned", [])
            result.setdefault("topics", [])
            result.setdefault("language", "en")
            result.setdefault("sentiment", "neutral")
            result.setdefault("description", "Screenshot analyzed by VLM")
            result.setdefault("confidence", 0.5)
            result.setdefault("has_people", False)

            return result

        except Exception as e:
            if verbose:
                print(f"  Error analyzing {path.name}: {e}")
            return {"error": str(e)}

    def _generate_generic(self, image: Image.Image) -> str:
        """Generic generation for non-Moondream models."""
        # This is a placeholder - different models have different APIs
        # Would need model-specific code here
        raise NotImplementedError(
            f"Generic generation not implemented for {self.model_name}. "
            "Please use moondream2 or implement model-specific code."
        )

    def _parse_response(self, response: str, verbose: bool = False) -> dict:
        """Parse JSON from VLM response."""
        # Try to extract JSON from response
        response = response.strip()

        # Try direct parse first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in response
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: return raw response as description
        if verbose:
            print(f"  Could not parse JSON from VLM response: {response[:100]}...")

        return {
            "description": response[:500] if response else "VLM analysis failed",
            "confidence": 0.3,
        }
