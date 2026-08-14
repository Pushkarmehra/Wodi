"""
OCR — Optical Character Recognition fallback.

Uses EasyOCR (primary) with Tesseract fallback to extract text from
screen captures. Text is used for:
  - Faster-Whisper initial_prompt (domain adaptation)
  - Lite-tier vision (no VLM available)
  - Element targeting when UI Automation tree is unavailable
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from wodi.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class OCRResult:
    text: str
    boxes: list[dict]       # [{"text": str, "conf": float, "rect": [x,y,w,h]}]
    elapsed_ms: float

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class OCREngine:
    """
    OCR wrapper supporting EasyOCR and Tesseract backends.

    Usage:
        ocr = OCREngine(engine="easyocr")
        ocr.load()
        result = ocr.read_image(pil_image)
        print(result.text)
    """

    def __init__(self, engine: str = "easyocr", language: str = "en") -> None:
        self.engine = engine
        self.language = language
        self._reader: Any = None

    def load(self) -> None:
        if self.engine == "easyocr":
            self._load_easyocr()
        else:
            log.info("ocr.engine", engine="tesseract")

    def _load_easyocr(self) -> None:
        try:
            import easyocr
            log.info("ocr.loading", engine="easyocr")
            self._reader = easyocr.Reader([self.language], gpu=self._has_gpu())
            log.info("ocr.ready", engine="easyocr")
        except ImportError:
            log.warning("ocr.easyocr_missing", fallback="tesseract")
            self.engine = "tesseract"
        except Exception as e:
            log.warning("ocr.load_failed", error=str(e), fallback="tesseract")
            self.engine = "tesseract"

    def _has_gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def read_image(self, image: Any, min_confidence: float = 0.3) -> OCRResult:
        """
        Extract text from a PIL.Image.
        Returns OCRResult with full text and bounding-box data.
        """
        t0 = time.perf_counter()
        try:
            if self.engine == "easyocr" and self._reader:
                return self._read_easyocr(image, min_confidence, t0)
            else:
                return self._read_tesseract(image, t0)
        except Exception as e:
            log.error("ocr.read_error", error=str(e))
            return OCRResult(text="", boxes=[], elapsed_ms=0)

    def _read_easyocr(self, image: Any, min_conf: float, t0: float) -> OCRResult:
        import numpy as np
        img_array = np.array(image)
        results = self._reader.readtext(img_array, detail=1)
        boxes = []
        texts = []
        for bbox, text, conf in results:
            if conf >= min_conf:
                boxes.append({"text": text, "conf": conf, "bbox": bbox})
                texts.append(text)
        full_text = " ".join(texts)
        elapsed = (time.perf_counter() - t0) * 1000
        return OCRResult(text=full_text, boxes=boxes, elapsed_ms=elapsed)

    def _read_tesseract(self, image: Any, t0: float) -> OCRResult:
        try:
            import pytesseract
            text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            boxes = []
            for i, word in enumerate(data["text"]):
                if word.strip() and int(data["conf"][i]) > 30:
                    boxes.append({
                        "text": word,
                        "conf": data["conf"][i] / 100.0,
                        "bbox": [data["left"][i], data["top"][i], data["width"][i], data["height"][i]],
                    })
            elapsed = (time.perf_counter() - t0) * 1000
            return OCRResult(text=text.strip(), boxes=boxes, elapsed_ms=elapsed)
        except ImportError:
            log.error("ocr.tesseract_missing", hint="pip install pytesseract + install Tesseract exe")
            return OCRResult(text="", boxes=[], elapsed_ms=0)
