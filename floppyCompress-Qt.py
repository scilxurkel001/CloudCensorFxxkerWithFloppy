# -*- coding: utf-8 -*-
import logging
import os
import struct
import hashlib
import json
import sys
import platform
import tempfile
import zipfile

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, 
    QPushButton, QComboBox, QProgressBar, QGroupBox, 
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QFrame
)
from PySide2.QtCore import Qt, Signal, Slot, QThread
# Added imports for font handling and dark mode
from PySide2.QtGui import QFontDatabase, QFont, QPalette, QColor

from pyfatfs.PyFatFS import PyFatFS

FLOPPY_CONFIGS = {
    "720KB (Standard Double Density Floppy) for <= 2GB data": {
        "key": "720KB", "chunk_size": 540 * 1024, "total_sectors": 1440,
        "sectors_per_track": 9, "sectors_per_cluster": 2, "root_dir_entries": 112,
        "sectors_per_fat": 3, "media_descriptor": 0xF9
    },
    "1440KB (Standard High Density Floppy) for 2-4GB data": {
        "key": "1440KB", "chunk_size": 1320 * 1024, "total_sectors": 2880,
        "sectors_per_track": 18, "sectors_per_cluster": 2, "root_dir_entries": 224,
        "sectors_per_fat": 9, "media_descriptor": 0xF0
    },
    "2880KB (Extreme Density Floppy) for 4-8GB data": {
        "key": "2880KB", "chunk_size": 2760 * 1024, "total_sectors": 5760,
        "sectors_per_track": 36, "sectors_per_cluster": 2, "root_dir_entries": 240,
        "sectors_per_fat": 9, "media_descriptor": 0xF0
    },
    "5760KB (RARE Triple Density Floppy) for 8-16GB data": {
        "key": "5760KB", "chunk_size": 5640 * 1024, "total_sectors": 11520,
        "sectors_per_track": 72, "sectors_per_cluster": 4, "root_dir_entries": 240,
        "sectors_per_fat": 18, "media_descriptor": 0xF0
    },
    "11520KB (Quad Density Floppy) - Not Recommended": {
        "key": "11520KB", "chunk_size": 10960 * 1024, "total_sectors": 23040,
        "sectors_per_track": 144, "sectors_per_cluster": 8, "root_dir_entries": 240,
        "sectors_per_fat": 18, "media_descriptor": 0xF0
    },
    "23040KB (idk Density Floppy) - Not Recommended": {
        "key": "23040KB", "chunk_size": 22640 * 1024, "total_sectors": 46080,
        "sectors_per_track": 288, "sectors_per_cluster": 16, "root_dir_entries": 240,
        "sectors_per_fat": 18, "media_descriptor": 0xF0
    },
}

def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()

def create_dynamic_fat12_image(path, cfg):
    """Generate a standard blank FAT12 floppy image dynamically"""
    with open(path, 'wb') as f:
        bs = bytearray(512)
        bs[0:3] = b'\xEB\x3C\x90'
        bs[3:11] = b'MSDOS5.0'
        struct.pack_into('<H', bs, 11, 512)
        bs[13] = cfg["sectors_per_cluster"]
        struct.pack_into('<H', bs, 14, 1)
        bs[16] = 2
        struct.pack_into('<H', bs, 17, cfg["root_dir_entries"])
        struct.pack_into('<H', bs, 19, cfg["total_sectors"])
        bs[21] = cfg["media_descriptor"]
        struct.pack_into('<H', bs, 22, cfg["sectors_per_fat"])
        struct.pack_into('<H', bs, 24, cfg["sectors_per_track"])
        struct.pack_into('<H', bs, 26, 2)
        bs[38] = 0x29
        struct.pack_into('<I', bs, 39, 0x12345678)
        bs[43:54] = b'NO NAME    '
        bs[54:62] = b'FAT12   '
        bs[510] = 0x55; bs[511] = 0xAA
        f.write(bs)

        fat_size = cfg["sectors_per_fat"] * 512
        fat = bytearray(fat_size)
        fat[0] = cfg["media_descriptor"]; fat[1] = 0xFF; fat[2] = 0xFF; fat[3] = 0xFF
        f.write(fat)
        f.write(fat)

        root_dir_size = cfg["root_dir_entries"] * 32
        f.write(bytearray(root_dir_size))

        root_sectors = root_dir_size // 512
        used_sectors = 1 + (2 * cfg["sectors_per_fat"]) + root_sectors
        data_sectors = cfg["total_sectors"] - used_sectors
        data_area_size = data_sectors * 512
        f.write(bytearray(data_area_size))

# ============ Working Thread ============
class CompressionWorker(QThread):
    """Background worker for compressing and generating floppy images"""
    status_update = Signal(str)
    progress_mode = Signal(str, int)
    progress_value = Signal(int)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(self, src, out, cfg, chunk_size, raw_format_key, format_label):
        super().__init__()
        self.src = src
        self.out = out
        self.cfg = cfg
        self.chunk_size = chunk_size
        self.raw_format_key = raw_format_key
        self.format_label = format_label

    def run(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmpf:
            temp_zip = tmpf.name
        try:
            os.makedirs(self.out, exist_ok=True)
            self.status_update.emit("Step 1/2: Compressing source files into temporary archive...")
            
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                if os.path.isfile(self.src):
                    zf.write(self.src, os.path.basename(self.src))
                else:
                    base_dir = self.src.rstrip(os.sep)
                    for root_dir, _, files in os.walk(base_dir):
                        for file in files:
                            full_path = os.path.join(root_dir, file)
                            arcname = os.path.relpath(full_path, base_dir)
                            zf.write(full_path, arcname)

            zip_hash = compute_sha256(temp_zip)
            manifest = {
                "zip_hash": zip_hash,
                "floppy_format": {
                    "key": self.raw_format_key,
                    "label": self.format_label
                },
                "images": {}
            }

            file_size = os.path.getsize(temp_zip)
            total_disks = (file_size + self.chunk_size - 1) // self.chunk_size

            self.progress_mode.emit("determinate", total_disks)
            self.status_update.emit(
                f"Step 2/2: Splitting and Writing {self.raw_format_key} Images (Total: {total_disks})...")

            with open(temp_zip, 'rb') as f:
                disk_num = 0
                while True:
                    if self.isInterruptionRequested():
                        self.finished.emit(False, "Cancelled")
                        return
                        
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    disk_num += 1
                    chunk_hash = hashlib.sha256(chunk).hexdigest()
                    img_name = f"FLP{disk_num:05d}.IMG"
                    img_path = os.path.join(self.out, img_name)

                    self.status_update.emit(
                        f"Writing {self.raw_format_key} Image ({disk_num}/{total_disks})...")
                    self.progress_value.emit(min(100, round(disk_num/total_disks*100)))

                    create_dynamic_fat12_image(img_path, self.cfg)
                    fat = None
                    try:
                        fat = PyFatFS(img_path)
                        fat_filename = f"FLP{disk_num:05d}.DAT"
                        with fat.openbin(f"/{fat_filename}", 'wb') as dst_f:
                            dst_f.write(chunk)
                    except Exception as e:
                        self.error.emit(f"Failed to write to pyfatfs [{img_name}]: {e}")
                        return
                    finally:
                        if fat:
                            fat.close()

                    image_hash = compute_sha256(img_path)
                    manifest["images"][img_name] = {
                        "chunk_hash": chunk_hash,
                        "image_hash": image_hash
                    }
            total_disks = max(1, (file_size + self.chunk_size - 1) // self.chunk_size)

            manifest_path = os.path.join(self.out, "manifest.json")
            with open(manifest_path, 'w', encoding='utf-8') as mf:
                json.dump(manifest, mf, indent=4)

            self.finished.emit(True, f"Successfully generated {total_disks} floppy image(s)!")

        except Exception as e:
            self.error.emit(str(e))
        finally:
            for tmp in [temp_zip]:
                if os.path.exists(tmp):
                    try: os.remove(tmp)
                    except OSError as e: logging.warning(f"Failed to remove {tmp}: {e}")

# ============ Main Window Class ============
class FloppyCompressorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("CloudCensorFxxkerWithFloppy - Compressor - v2.00d Based on Qt5")
        self.resize(900, 600)
        self.setMinimumSize(500, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(8)

        # 1. Source Selection
        frame_src = QGroupBox(" 1. Select Source ")
        layout_src = QHBoxLayout()
        self.source_entry = QLineEdit()
        self.source_entry.setPlaceholderText("Select file or folder...")
        btn_file = QPushButton("File")
        btn_file.setFixedWidth(60)
        btn_file.clicked.connect(self.browse_file)
        btn_folder = QPushButton("Folder")
        btn_folder.setFixedWidth(60)
        btn_folder.clicked.connect(self.browse_folder)
        
        layout_src.addWidget(self.source_entry)
        layout_src.addWidget(btn_file)
        layout_src.addWidget(btn_folder)
        frame_src.setLayout(layout_src)
        main_layout.addWidget(frame_src)

        # 2. Floppy Format
        frame_cfg = QGroupBox(" 2. Floppy Target Specification ")
        layout_cfg = QVBoxLayout()
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Select Format Type:"))
        self.combo_capacity = QComboBox()
        self.combo_capacity.addItems(list(FLOPPY_CONFIGS.keys()))
        self.combo_capacity.setCurrentText("1440KB (Standard High Density Floppy) for 2-4GB data")
        self.combo_capacity.currentTextChanged.connect(self.update_chunk_hint)
        row1.addWidget(self.combo_capacity)
        layout_cfg.addLayout(row1)
        
        self.lbl_chunk_hint = QLabel("Split Chunk Size: 1320 KB")
        self.lbl_chunk_hint.setStyleSheet("color: #5dade2; padding: 9px;")
        layout_cfg.addWidget(self.lbl_chunk_hint)
        
        frame_cfg.setLayout(layout_cfg)
        main_layout.addWidget(frame_cfg)

        # 3. Output Directory
        frame_out = QGroupBox(" 3. Select Output Directory ")
        layout_out = QHBoxLayout()
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Select output folder...")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_output)
        
        layout_out.addWidget(self.output_entry)
        layout_out.addWidget(btn_browse)
        frame_out.setLayout(layout_out)
        main_layout.addWidget(frame_out)

        # Progress Area
        frame_progress = QFrame()
        layout_progress = QVBoxLayout(frame_progress)
        layout_progress.setContentsMargins(0, 0, 0, 0)
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("padding: 5px;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout_progress.addWidget(self.lbl_status)
        layout_progress.addWidget(self.progress)
        main_layout.addWidget(frame_progress)

        # Start Button
        self.btn_start = QPushButton("Start Matrix Compression and Generate Floppy Images")
        self.btn_start.clicked.connect(self.start_compression)
        self.btn_start.setStyleSheet("padding: 8px; font-weight: bold;")
        main_layout.addWidget(self.btn_start)

        self.update_chunk_hint()

    @Slot()
    def update_chunk_hint(self):
        selected = self.combo_capacity.currentText()
        chunk_kb = FLOPPY_CONFIGS[selected]["chunk_size"] // 1024
        self.lbl_chunk_hint.setText(f"Split Chunk Size: {chunk_kb} KB")

    @Slot()
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Source File", "", "All Files (*)")
        if path: self.source_entry.setText(os.path.normpath(path))

    @Slot()
    def browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Source Folder", "")
        if path: self.source_entry.setText(os.path.normpath(path))

    @Slot()
    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory", "")
        if path: self.output_entry.setText(os.path.normpath(path))

    @Slot()
    def start_compression(self):
        src = self.source_entry.text().strip()
        out = self.output_entry.text().strip()
        
        if not src or not out:
            QMessageBox.warning(self, "Warning", "Please select both source and output directories!")
            return

        self.btn_start.setEnabled(False)
        self.combo_capacity.setEnabled(False)
        self.progress.setRange(0, 0)

        selected = self.combo_capacity.currentText()
        cfg = FLOPPY_CONFIGS[selected]
        raw_format_key = cfg["key"]
        format_label = selected
        
        self.worker = CompressionWorker(src, out, cfg, cfg["chunk_size"], raw_format_key, format_label)
        self.worker.status_update.connect(self.lbl_status.setText)
        self.worker.progress_mode.connect(self.update_progress_mode)
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    @Slot(str, int)
    def update_progress_mode(self, mode, total):
        if mode == "determinate":
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    @Slot(bool, str)
    def on_finished(self, success, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.btn_start.setEnabled(True)
        self.combo_capacity.setEnabled(True)
        
        if success:
            QMessageBox.information(
                self, "Success", 
                f"{message}\n\nDestination:\n{self.output_entry.text()}"
            )
        self.worker = None

    @Slot(str)
    def on_error(self, error_msg):
        self.lbl_status.setText("❌ An error occurred")
        QMessageBox.critical(self, "Error", f"Processing failed:\n{error_msg}")
        self.btn_start.setEnabled(True)
        self.combo_capacity.setEnabled(True)
        self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(5000)
        event.accept()

# ============ Program Entry Point ============
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ================= DARK MODE =================
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    
    # Set disabled text to a gray color for better visibility in dark mode
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))

    app.setPalette(dark_palette)
    
    # Fix ToolTip style for better visibility in dark mode
    app.setStyleSheet("QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")
    # =====================================================
    
    font_path = os.path.join(os.path.dirname(__file__), "fonts", "MiSans-Medium.ttf")
    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id != -1:
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        font_name = font_families[0]
        print(f"✅ Loaded font: {font_name}")
    else:
        print(f"❌ Failed to load font: {font_path}")
        font_name = "Segoe UI"

    font = QFont(font_name, 9)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)
    
    window = FloppyCompressorApp()
    window.show()
    sys.exit(app.exec_())
