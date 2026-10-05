"""OCR worker for pdf_to_json.py.

Runs inside a Python environment that has PaddleOCR 3.x installed (by default the
existing C:\\HermesOCR venv; nothing is written there by this script). The model
is loaded once; the parent then sends one JSON line per page image on stdin:

    {"image": "C:\\\\path\\\\page.png"}

and receives one JSON line on the protocol channel:

    {"ok": true, "lines": [{"text": "...", "bbox": [x1, y1, x2, y2], "score": 0.98}]}

bbox is in image pixels. Everything Paddle prints goes to stderr, never to the
protocol channel.
"""
import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--det-model", required=True)
    ap.add_argument("--rec-model", required=True)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    # Keep a private handle on the real stdout, then point fd 1 at stderr so
    # library/native prints cannot corrupt the protocol.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    sys.stdout.flush()
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send(message: dict) -> None:
        proto.write(json.dumps(message, ensure_ascii=False) + "\n")
        proto.flush()

    try:
        import paddle
        import paddleocr
        from paddleocr import PaddleOCR

        device = args.device
        if device == "auto":
            has_gpu = paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
            device = "gpu:0" if has_gpu else "cpu"
        ocr = PaddleOCR(
            text_detection_model_name=args.det_model,
            text_recognition_model_name=args.rec_model,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
        )
    except Exception as exc:
        send({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    send({"ready": True, "engine": f"paddleocr {paddleocr.__version__}", "device": device})

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
            predictions = list(ocr.predict(request["image"]))
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
            send({"ok": True, "lines": lines})
        except Exception as exc:
            send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
