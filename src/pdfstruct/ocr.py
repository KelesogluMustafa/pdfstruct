"""pdfstruct.ocr - the OCR backend (PaddleOCR, in-process, CPU by default).

Nothing here is imported or initialised while a native PDF is processed:
`extract` only calls `OcrEngine.ocr_image()` when a page really needs OCR, and
that is the first moment paddleocr/paddlepaddle are imported and the models are
loaded. Models are downloaded by PaddleX on first use into a per-user cache
(default ~/.pdfstruct/models) and reused afterwards.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import logging
import os
import platform
import sys
import warnings
from pathlib import Path

DEFAULT_MODEL_CACHE = Path.home() / ".pdfstruct" / "models"
OCR_PACKAGES = ("paddleocr", "paddle")
INSTALL_HINT = 'pip install "pdfstruct[ocr]"'

# Platforms with official CPU wheels for paddlepaddle 3.x (checked on PyPI, 10/2026).
_SUPPORTED = {("Windows", "amd64"), ("Linux", "x86_64"), ("Darwin", "arm64")}
_SUPPORTED_PYTHON = ((3, 9), (3, 13))
# Keys of older configs that no longer mean anything (OCR ran in another Python).
LEGACY_KEYS = ("python", "python_candidates")


class OcrUnavailable(RuntimeError):
    pass


def platform_supported() -> bool:
    system, machine = platform.system(), platform.machine().lower()
    machine = {"x86_64": "x86_64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    if system == "Windows":
        machine = "amd64" if machine in ("amd64", "x86_64") else machine
    if system == "Linux":
        machine = "x86_64" if machine in ("amd64", "x86_64") else machine
    low, high = _SUPPORTED_PYTHON
    return (system, machine) in _SUPPORTED and low <= sys.version_info[:2] <= high


def available() -> bool:
    """True when the OCR packages are installed (checked without importing them)."""
    return all(importlib.util.find_spec(name) is not None for name in OCR_PACKAGES)


def unavailable_reason() -> str:
    if platform_supported():
        return f"OCR support is not installed. Install with: {INSTALL_HINT}"
    return ("OCR support is not available on this platform "
            f"({platform.system()} {platform.machine()}, Python {platform.python_version()}): "
            "paddlepaddle has no wheel for it. Native PDF text still works.")


def model_cache_dir(cfg: dict) -> Path:
    configured = cfg.get("model_cache_dir")
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_CACHE


def models_cached(cfg: dict) -> bool:
    root = model_cache_dir(cfg) / "official_models"
    return all((root / cfg[key]).is_dir() for key in ("det_model", "rec_model"))


@contextlib.contextmanager
def _quiet():
    """Hide library chatter (model banners, warnings) from the user's terminal."""
    for name in ("paddlex", "paddleocr", "paddle"):
        logging.getLogger(name).setLevel(logging.ERROR)
    sink = io.StringIO()
    with warnings.catch_warnings(), contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        warnings.simplefilter("ignore")
        yield


class OcrEngine:
    """Lazy PaddleOCR handle. `info` and `failed_reason` are filled on first use."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ocr = None
        self.info = None
        self.failed_reason = None

    def _start(self) -> None:
        if not available():
            raise OcrUnavailable(unavailable_reason())
        cache = model_cache_dir(self.cfg)
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache)
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        if not models_cached(self.cfg):
            print("Preparing OCR models for first use...", file=sys.stderr, flush=True)
        try:
            with _quiet():
                import paddle
                import paddleocr
                from paddleocr import PaddleOCR

                device = self.cfg.get("device", "auto")
                if device == "auto":
                    has_gpu = (paddle.device.is_compiled_with_cuda()
                               and paddle.device.cuda.device_count() > 0)
                    device = "gpu:0" if has_gpu else "cpu"
                self.ocr = PaddleOCR(
                    text_detection_model_name=self.cfg["det_model"],
                    text_recognition_model_name=self.cfg["rec_model"],
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    device=device,
                    # oneDNN fails on CPU with current paddlepaddle 3.x builds
                    enable_mkldnn=bool(self.cfg.get("enable_mkldnn", False)),
                )
        except OcrUnavailable:
            raise
        except Exception as exc:
            raise OcrUnavailable(f"OCR engine failed to start: {type(exc).__name__}: {exc}") from exc
        self.info = {"engine": f"paddleocr {paddleocr.__version__}", "device": device,
                     "det_model": self.cfg["det_model"], "rec_model": self.cfg["rec_model"],
                     "model_cache_dir": str(cache)}

    def ocr_image(self, image_path: Path) -> list[dict]:
        """-> [{"text", "bbox": [x1, y1, x2, y2] in image pixels, "score"}, ...]"""
        if self.failed_reason:
            raise OcrUnavailable(self.failed_reason)
        if self.ocr is None:
            try:
                self._start()
            except OcrUnavailable as exc:
                self.failed_reason = str(exc)
                raise
        with _quiet():
            predictions = list(self.ocr.predict(str(image_path)))
        lines = []
        if predictions:
            data = predictions[0].json
            data = data.get("res", data)
            texts = data.get("rec_texts") or []
            scores = data.get("rec_scores") or []
            boxes = data.get("rec_boxes")
            if boxes is None or len(boxes) != len(texts):
                boxes = []
                for poly in data.get("rec_polys") or []:
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    boxes.append([min(xs), min(ys), max(xs), max(ys)])
            for index, text in enumerate(texts):
                if index >= len(boxes):
                    break
                lines.append({
                    "text": text,
                    "bbox": [float(v) for v in boxes[index]],
                    "score": float(scores[index]) if index < len(scores) else None,
                })
        return lines

    def close(self) -> None:
        self.ocr = None
