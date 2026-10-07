"""pdfstruct-gui - entry point of the desktop window.

    pdfstruct-gui [files or folders ...]
    pdfstruct-gui --smoke-test [--screenshot FILE]    open, report, close (for checks)
"""
from __future__ import annotations

import argparse
import json
import sys

INSTALL_HINT = 'The desktop window needs PySide6. Install it with: pip install "pdfstruct[gui]"'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdfstruct-gui", description="PDFStruct desktop window")
    parser.add_argument("paths", nargs="*", help="files or folders to put in the queue")
    parser.add_argument("--smoke-test", action="store_true",
                        help="open the window, print its state as JSON and close again")
    parser.add_argument("--screenshot", help="with --smoke-test: save a picture of the window")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from .window import MainWindow, describe
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        return 1

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PDFStruct")
    window = MainWindow()
    if args.paths:
        window.add_paths(args.paths)
    window.show()
    if not args.smoke_test:
        return app.exec()

    report: dict = {}

    def finish() -> None:
        report.update(describe(window), platform=app.platformName(),
                      ocr_loaded=any(name.split(".")[0] in ("paddle", "paddleocr", "paddlex")
                                     for name in sys.modules))
        if args.screenshot:
            report["screenshot"] = bool(window.grab().save(args.screenshot))
        window.close()
        app.quit()

    QTimer.singleShot(1200, finish)
    app.exec()
    report["closed"] = not window.isVisible()
    print("GUI_SMOKE " + json.dumps(report, ensure_ascii=False))
    return 0 if report.get("visible") and report["closed"] else 1


if __name__ == "__main__":
    sys.exit(main())
