"""The “Create from text” tab: a name, a text box, five formats, an output folder and Create.

Like the window, it owns no document logic. Create builds a create.CreateRequest and
hands it to a worker thread; what is shown afterwards comes from the service's result.
The text box is plain text only: no rich text, no pictures, no remote content.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from .. import create
from . import state, worker


class CreatePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.job_thread = None
        self.worker = None
        self.last_result: dict | None = None
        self._build()
        self._refresh()

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Document name, e.g. PROJECT_TEMPLATE")
        self.name_edit.setClearButtonEnabled(True)
        self.name_edit.textChanged.connect(self._refresh)
        self.type_box = QComboBox()
        for key, label in state.CONTENT_TYPE_LABELS.items():
            self.type_box.addItem(label, key)
        top.addWidget(QLabel("Name"))
        top.addWidget(self.name_edit, 1)
        top.addWidget(QLabel("Text is"))
        top.addWidget(self.type_box)
        layout.addLayout(top)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Paste or type the text here.")
        self.text_edit.setMinimumHeight(180)
        self.text_edit.textChanged.connect(self._refresh)
        layout.addWidget(self.text_edit, 3)

        formats_box = QGroupBox("Output formats")
        formats_layout = QHBoxLayout(formats_box)
        self.format_boxes: dict[str, QCheckBox] = {}
        for key, label in state.CREATE_FORMAT_LABELS.items():
            box = QCheckBox(label)
            box.setChecked(key in create.DEFAULT_FORMATS)
            box.toggled.connect(self._refresh)
            self.format_boxes[key] = box
            formats_layout.addWidget(box)
        formats_layout.addStretch(1)
        layout.addWidget(formats_box)

        output_box = QGroupBox("Output folder")
        output_layout = QVBoxLayout(output_box)
        folder = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(f"Default: {create.default_output_dir()}")
        self.output_edit.setClearButtonEnabled(True)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.choose_output)
        folder.addWidget(self.output_edit, 1)
        folder.addWidget(self.browse_button)
        self.overwrite_box = QCheckBox("Replace existing files")
        self.overwrite_box.setToolTip("Off: a file that already exists is kept and reported.")
        output_layout.addLayout(folder)
        output_layout.addWidget(self.overwrite_box)
        layout.addWidget(output_box)

        actions = QHBoxLayout()
        self.create_button = QPushButton("Create")
        self.open_button = QPushButton("Open Output Folder")
        self.create_button.clicked.connect(self.start_create)
        self.open_button.clicked.connect(self.open_output_folder)
        actions.addWidget(self.create_button)
        actions.addStretch(1)
        actions.addWidget(self.open_button)
        layout.addLayout(actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)

        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(90)
        self.result_list.setWordWrap(True)
        results_layout.addWidget(self.result_list)
        layout.addWidget(results_box, 1)

    # ------------------------------------------------------------ options
    def selected_formats(self) -> list[str]:
        return [key for key, box in self.format_boxes.items() if box.isChecked()]

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder", self.output_edit.text().strip())
        if folder:
            self.output_edit.setText(folder)

    # ------------------------------------------------------------ create
    def is_running(self) -> bool:
        return self.job_thread is not None

    def start_create(self) -> None:
        if self.is_running():
            return
        try:
            request = state.build_create_request(
                self.name_edit.text(), self.text_edit.toPlainText(), self.selected_formats(),
                self.output_edit.text(), self.type_box.currentData(), self.overwrite_box.isChecked())
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.last_result = None
        self.result_list.clear()
        self.progress_bar.setRange(0, 0)  # busy: the service reports no partial steps
        self.job_thread, self.worker = worker.start_create(request, self)
        self.worker.finished.connect(self.on_finished)
        self.job_thread.finished.connect(self._thread_done)
        self.job_thread.start()
        self.status_label.setText("Creating…")
        self._refresh()

    def on_finished(self, result: dict) -> None:
        self.last_result = result
        self.result_list.addItems(state.create_result_lines(result))
        self.status_label.setText(state.create_summary(result))

    def _thread_done(self) -> None:
        thread, self.job_thread, self.worker = self.job_thread, None, None
        if thread is not None:
            thread.deleteLater()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if self.last_result and self.last_result["outputs"] else 0)
        self._refresh()

    def open_output_folder(self) -> None:
        folders = state.output_folders({"files": [{"outputs": dict(enumerate(
            (self.last_result or {}).get("outputs", [])))}]})
        if folders:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folders[0]))

    def wait(self, milliseconds: int = 30000) -> None:
        """Let a running creation finish (it is short and leaves no partial file)."""
        if self.job_thread is not None:
            self.job_thread.quit()
            self.job_thread.wait(milliseconds)

    # ------------------------------------------------------------ state
    def _refresh(self) -> None:
        running = self.is_running()
        for widget in (self.name_edit, self.type_box, self.text_edit, self.output_edit,
                       self.browse_button, self.overwrite_box, *self.format_boxes.values()):
            widget.setEnabled(not running)
        ready = bool(self.name_edit.text().strip() and self.text_edit.toPlainText().strip()
                     and self.selected_formats())
        self.create_button.setEnabled(not running and ready)
        self.open_button.setEnabled(bool(self.last_result and self.last_result["outputs"]))
