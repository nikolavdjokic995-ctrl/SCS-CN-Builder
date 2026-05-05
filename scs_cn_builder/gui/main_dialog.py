from __future__ import annotations

from pathlib import Path
import csv

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from ..core.cn_workflow import run_cn_workflow
from ..core.validators import validate_paths


DEFAULT_CN_LOOKUP = [
    [1, 77, 85, 90, 92],
    [2, 67, 78, 85, 89],
    [3, 39, 61, 74, 80],
    [4, 30, 55, 70, 77],
    [5, 45, 66, 77, 83],
    [6, 68, 79, 86, 89],
    [7, 100, 100, 100, 100],
]


class LULC2HMSCNDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("SCS-CN Builder")
        self.resize(900, 760)

        self.lulc_edit = QLineEdit()
        self.hsg_edit = QLineEdit()
        self.subbasins_edit = QLineEdit()
        self.cn_lookup_edit = QLineEdit()
        self.output_dir_edit = QLineEdit()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        self.cn_table = QTableWidget()
        self._build_ui()
        self._load_default_cn_table()

    def _build_ui(self):
        root = QVBoxLayout()
        tabs = QTabWidget()

        workflow_tab = QWidget()
        workflow_layout = QVBoxLayout(workflow_tab)

        inputs_group = QGroupBox("Inputs")
        form = QFormLayout()
        form.addRow("LULC raster", self._with_browse(self.lulc_edit, "file"))
        form.addRow("HSG raster", self._with_browse(self.hsg_edit, "file"))
        form.addRow("Basin vector", self._with_browse(self.subbasins_edit, "file"))
        form.addRow("CN lookup CSV", self._with_browse(self.cn_lookup_edit, "cn_file"))
        form.addRow("Output folder", self._with_browse(self.output_dir_edit, "dir"))
        inputs_group.setLayout(form)

        btns = QHBoxLayout()
        run_btn = QPushButton("Run SCS-CN Workflow")
        run_btn.clicked.connect(self.run_workflow)
        btns.addWidget(run_btn)

        workflow_layout.addWidget(inputs_group)
        workflow_layout.addLayout(btns)
        workflow_layout.addWidget(QLabel("Log"))
        workflow_layout.addWidget(self.log_box)

        cn_tab = QWidget()
        cn_layout = QVBoxLayout(cn_tab)
        cn_layout.addWidget(QLabel(
            "CN2 lookup values used by the workflow. CN3 is calculated automatically from CN2. Edit cells directly, add/remove LULC classes, "
            "or load/save a CSV with columns: LULC_code, CN_A, CN_B, CN_C, CN_D."
        ))
        self.cn_table.setColumnCount(5)
        self.cn_table.setHorizontalHeaderLabels(["LULC_code", "CN_A", "CN_B", "CN_C", "CN_D"])
        self.cn_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cn_layout.addWidget(self.cn_table)

        cn_btns = QHBoxLayout()
        add_btn = QPushButton("Add class")
        add_btn.clicked.connect(self._add_cn_row)
        remove_btn = QPushButton("Remove selected class")
        remove_btn.clicked.connect(self._remove_selected_cn_rows)
        default_btn = QPushButton("Reset to default")
        default_btn.clicked.connect(self._load_default_cn_table)
        load_btn = QPushButton("Load CSV")
        load_btn.clicked.connect(self._load_cn_csv_dialog)
        save_btn = QPushButton("Save CSV")
        save_btn.clicked.connect(self._save_cn_csv_dialog)
        for btn in [add_btn, remove_btn, default_btn, load_btn, save_btn]:
            cn_btns.addWidget(btn)
        cn_layout.addLayout(cn_btns)

        tabs.addTab(workflow_tab, "Workflow")
        tabs.addTab(cn_tab, "CN lookup table")

        root.addWidget(tabs)
        self.setLayout(root)

    def _with_browse(self, line_edit: QLineEdit, mode: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Browse")
        btn.clicked.connect(lambda: self._browse(line_edit, mode))
        layout.addWidget(line_edit)
        layout.addWidget(btn)
        return widget

    def _browse(self, line_edit: QLineEdit, mode: str):
        if mode in ("file", "cn_file"):
            path, _ = QFileDialog.getOpenFileName(self, "Select file")
            if path:
                line_edit.setText(path)
                if mode == "cn_file":
                    self._load_cn_csv(path)
        else:
            path = QFileDialog.getExistingDirectory(self, "Select folder")
            if path:
                line_edit.setText(path)

    def log(self, text: str):
        self.log_box.append(text)

    def _load_default_cn_table(self):
        self._set_cn_table_rows(DEFAULT_CN_LOOKUP)

    def _set_cn_table_rows(self, rows):
        self.cn_table.setRowCount(0)
        for row_values in rows:
            row = self.cn_table.rowCount()
            self.cn_table.insertRow(row)
            for col, value in enumerate(row_values):
                self.cn_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _add_cn_row(self):
        row = self.cn_table.rowCount()
        self.cn_table.insertRow(row)
        next_code = row + 1
        existing = []
        for r in range(row):
            item = self.cn_table.item(r, 0)
            if item and item.text().strip():
                try:
                    existing.append(int(float(item.text().strip())))
                except ValueError:
                    pass
        if existing:
            next_code = max(existing) + 1
        defaults = [next_code, 0, 0, 0, 0]
        for col, value in enumerate(defaults):
            self.cn_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _remove_selected_cn_rows(self):
        rows = sorted({idx.row() for idx in self.cn_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.cn_table.removeRow(row)

    def _load_cn_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load CN lookup CSV", "", "CSV files (*.csv);;All files (*.*)")
        if path:
            self.cn_lookup_edit.setText(path)
            self._load_cn_csv(path)

    def _save_cn_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CN lookup CSV", "CNlookup.csv", "CSV files (*.csv);;All files (*.*)")
        if path:
            self._write_cn_table_to_csv(path)
            self.cn_lookup_edit.setText(path)
            self.log(f"CN lookup table saved: {path}")

    def _load_cn_csv(self, path: str):
        rows = []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = ["LULC_code", "CN_A", "CN_B", "CN_C", "CN_D"]
            if not set(required).issubset(set(reader.fieldnames or [])):
                raise ValueError(f"CN lookup CSV must contain columns: {required}")
            for row in reader:
                rows.append([row[c] for c in required])
        self._set_cn_table_rows(rows)
        self.log(f"CN lookup table loaded: {path}")

    def _collect_cn_table_rows(self):
        rows = []
        for r in range(self.cn_table.rowCount()):
            values = []
            empty_row = True
            for c in range(5):
                item = self.cn_table.item(r, c)
                text = item.text().strip() if item else ""
                if text:
                    empty_row = False
                values.append(text)
            if empty_row:
                continue
            try:
                lulc_code = int(float(values[0]))
                cn_values = [float(v) for v in values[1:]]
            except Exception:
                raise ValueError(f"Invalid CN lookup value in row {r + 1}.")
            for cn in cn_values:
                if cn < 0 or cn > 100:
                    raise ValueError(f"CN values must be between 0 and 100. Check row {r + 1}.")
            rows.append([lulc_code] + cn_values)
        if not rows:
            raise ValueError("CN lookup table is empty.")
        return rows

    def _write_cn_table_to_csv(self, path: str):
        rows = self._collect_cn_table_rows()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["LULC_code", "CN_A", "CN_B", "CN_C", "CN_D"])
            writer.writerows(rows)

    def run_workflow(self):
        try:
            validate_paths([
                self.lulc_edit.text(),
                self.hsg_edit.text(),
                self.subbasins_edit.text(),
                self.output_dir_edit.text(),
            ])

            cn_lookup_csv = self.cn_lookup_edit.text().strip()
            if not cn_lookup_csv:
                cn_lookup_csv = str(Path(self.output_dir_edit.text()) / "CNlookup_used.csv")
            self._write_cn_table_to_csv(cn_lookup_csv)
            self.cn_lookup_edit.setText(cn_lookup_csv)

            outputs = run_cn_workflow(
                lulc_path=self.lulc_edit.text(),
                hsg_path=self.hsg_edit.text(),
                subbasins_path=self.subbasins_edit.text(),
                cn_lookup_csv=cn_lookup_csv,
                output_dir=self.output_dir_edit.text(),
            )

            self.log("Workflow finished.")
            for key, value in outputs.items():
                self.log(f"{key}: {value}")

            QMessageBox.information(self, "SCS-CN Builder", "SCS-CN workflow finished successfully. CN2, CN3, QC file and HTML report were created.")
        except Exception as exc:
            QMessageBox.critical(self, "Workflow error", str(exc))
