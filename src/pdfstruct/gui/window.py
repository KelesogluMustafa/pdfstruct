"""The PDFStruct window: a file queue, ten format checkboxes, an output folder and Convert.

It owns no conversion logic. Convert builds a service.JobRequest and hands it to the
worker thread; everything shown here comes from the service's events and result.
A second tab, “Create from text” (create_panel.py), writes typed or pasted text as documents.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import __version__
from . import state, worker
from .create_panel import CreatePanel

DEFAULT_OUTPUT_HINT = "an “output” folder next to each file"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.queue = state.Queue()
        self.progress = state.Progress()
        self.job_thread = None
        self.worker = None
        self.last_result: dict | None = None
        self.setWindowTitle(f"PDFStruct {__version__}")
        self.setAcceptDrops(True)
        self.resize(760, 680)
        self._build()
        self._refresh()

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        files_box = QGroupBox("Files")
        files_layout = QVBoxLayout(files_box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumHeight(150)
        self.file_list.setTextElideMode(Qt.ElideRight)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.drop_hint = QLabel("Drop files or folders here, or use Select Files.\n"
                                "PDF, DOCX, TXT, Markdown, HTML, JPG, PNG, TIFF, BMP, WebP")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setEnabled(False)
        files_layout.addWidget(self.drop_hint)
        files_layout.addWidget(self.file_list)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Select Files…")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self.choose_files)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_queue)
        self.file_list.itemSelectionChanged.connect(self._refresh)
        for button in (self.add_button, self.remove_button, self.clear_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        files_layout.addLayout(buttons)
        layout.addWidget(files_box, 3)

        formats_box = QGroupBox("Output formats")
        grid = QGridLayout(formats_box)
        self.format_boxes: dict[str, QCheckBox] = {}
        for index, (key, label) in enumerate(state.FORMAT_LABELS.items()):
            box = QCheckBox(label)
            box.setChecked(key in state.DEFAULT_FORMATS)
            box.toggled.connect(self._refresh)
            self.format_boxes[key] = box
            grid.addWidget(box, index // 5, index % 5)
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.toggle_all_formats)
        self.force_ocr_box = QCheckBox("Force OCR on every page")
        self.force_ocr_box.setToolTip("Normally OCR runs only on pages without a usable text layer.")
        grid.addWidget(self.select_all_button, 2, 0)
        grid.addWidget(self.force_ocr_box, 2, 1, 1, 4)
        layout.addWidget(formats_box)

        output_box = QGroupBox("Output folder")
        output_layout = QHBoxLayout(output_box)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(f"Default: {DEFAULT_OUTPUT_HINT}")
        self.output_edit.setClearButtonEnabled(True)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.choose_output)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.browse_button)
        layout.addWidget(output_box)

        actions = QHBoxLayout()
        self.convert_button = QPushButton("Convert")
        self.convert_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.open_button = QPushButton("Open Output Folder")
        self.convert_button.clicked.connect(self.start_conversion)
        self.cancel_button.clicked.connect(self.cancel_conversion)
        self.open_button.clicked.connect(self.open_output_folder)
        actions.addWidget(self.convert_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.open_button)
        layout.addLayout(actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)

        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(110)
        self.result_list.setWordWrap(True)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        results_layout.addWidget(self.result_list)
        results_layout.addWidget(self.summary_label)
        layout.addWidget(results_box, 2)

        self.create_panel = CreatePanel()
        self.tabs = QTabWidget()
        self.tabs.addTab(root, "Convert files")
        self.tabs.addTab(self.create_panel, "Create from text")
        self.setCentralWidget(self.tabs)

    # ------------------------------------------------------------ queue
    def add_paths(self, paths) -> dict:
        report = self.queue.add(paths)
        self._reload_file_list()
        self.status_label.setText(state.add_report_text(report))
        return report

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files", "", state.FILE_DIALOG_FILTER)
        if paths:
            self.add_paths(paths)

    def remove_selected(self) -> None:
        self.queue.remove([index.row() for index in self.file_list.selectedIndexes()])
        self._reload_file_list()

    def clear_queue(self) -> None:
        self.queue.clear()
        self._reload_file_list()

    def _reload_file_list(self) -> None:
        self.file_list.clear()
        for path in self.queue.files:
            self.file_list.addItem(f"{path.name}    ({path.parent})")  # name first: long paths get cut
            self.file_list.item(self.file_list.count() - 1).setToolTip(str(path))
        self._refresh()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not self.is_running() and self.tabs.currentIndex() == 0:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    # ------------------------------------------------------------ options
    def selected_formats(self) -> list[str]:
        return [key for key, box in self.format_boxes.items() if box.isChecked()]

    def toggle_all_formats(self) -> None:
        check = len(self.selected_formats()) < len(self.format_boxes)
        for box in self.format_boxes.values():
            box.setChecked(check)

    def choose_output(self) -> None:
        start = self.output_edit.text().strip() or (
            str(self.queue.files[0].parent) if self.queue.files else "")
        folder = QFileDialog.getExistingDirectory(self, "Output folder", start)
        if folder:
            self.output_edit.setText(folder)

    # ------------------------------------------------------------ conversion
    def is_running(self) -> bool:
        return self.job_thread is not None

    def start_conversion(self) -> None:
        if self.is_running():
            return
        try:
            request = state.build_request(self.queue.files, self.selected_formats(),
                                          self.output_edit.text().strip() or None,
                                          self.force_ocr_box.isChecked())
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.last_result = None
        self.result_list.clear()
        self.summary_label.setText("")
        self.progress = state.Progress()
        self.progress_bar.setRange(0, 0)  # busy until the first real step is known
        self.job_thread, self.worker = worker.start(request, self)
        self.worker.event.connect(self.on_event)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.job_thread.finished.connect(self._thread_done)
        self.job_thread.start()
        self.status_label.setText("Starting…")
        self._refresh()

    def cancel_conversion(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelling after the current step…")

    def on_event(self, event: dict) -> None:
        self.progress.update(event)
        if self.progress.total > 1:  # files finished out of files: a real, countable measure
            self.progress_bar.setRange(0, self.progress.total)
            self.progress_bar.setValue(self.progress.done)
        if event["type"] != "job_finished" and self.cancel_button.isEnabled():
            self.status_label.setText(self.progress.text)

    def on_finished(self, result: dict) -> None:
        self.last_result = result
        for item in result["files"]:
            self.result_list.addItem(state.result_line(item))
            for warning in item["warnings"]:
                self.result_list.addItem(f"    ! {warning}")
        self.summary_label.setText(state.summary_text(result))
        self.status_label.setText("")

    def on_failed(self, message: str) -> None:
        self.summary_label.setText(f"Could not start: {message}")
        self.status_label.setText("")

    def _thread_done(self) -> None:
        thread, self.job_thread, self.worker = self.job_thread, None, None
        if thread is not None:
            thread.deleteLater()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if self.last_result else 0)
        self._refresh()

    def open_output_folder(self) -> None:
        folders = state.output_folders(self.last_result) if self.last_result else []
        if folders:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folders[0]))

    # ------------------------------------------------------------ state
    def _refresh(self) -> None:
        running = self.is_running()
        has_files = len(self.queue) > 0
        self.drop_hint.setVisible(not has_files)
        for widget in (self.add_button, self.clear_button, self.select_all_button, self.force_ocr_box,
                       self.output_edit, self.browse_button, *self.format_boxes.values()):
            widget.setEnabled(not running)
        self.clear_button.setEnabled(not running and has_files)
        self.remove_button.setEnabled(not running and bool(self.file_list.selectedIndexes()))
        self.convert_button.setEnabled(not running and has_files and bool(self.selected_formats()))
        self.cancel_button.setEnabled(running)
        self.open_button.setEnabled(bool(self.last_result and state.output_folders(self.last_result)))
        all_checked = len(self.selected_formats()) == len(self.format_boxes)
        self.select_all_button.setText("Select None" if all_checked else "Select All")

    def closeEvent(self, event) -> None:
        if self.is_running():
            answer = QMessageBox.question(self, "PDFStruct", "A conversion is running. Stop it and quit?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.job_thread.quit()
            self.job_thread.wait(30000)
        self.create_panel.wait()
        event.accept()


def describe(window: MainWindow) -> dict:
    """Facts about the window for smoke tests."""
    return {"title": window.windowTitle(), "visible": window.isVisible(),
            "formats": [box.text() for box in window.format_boxes.values()],
            "queue": [Path(p).name for p in window.queue.files],
            "convert_enabled": window.convert_button.isEnabled(),
            "tabs": [window.tabs.tabText(index) for index in range(window.tabs.count())],
            "create_formats": [box.text() for box in window.create_panel.format_boxes.values()]}
