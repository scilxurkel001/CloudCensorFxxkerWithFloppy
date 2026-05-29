# -*- coding: utf-8 -*-
import logging
import os
import glob
import threading
import hashlib
import json
import tempfile
import zipfile
import sys
import platform

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, 
    QPushButton, QProgressBar, QGroupBox, 
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QFrame
)
from PySide2.QtCore import Qt, Signal, Slot, QThread
from PySide2.QtGui import QFontDatabase, QFont, QPalette, QColor

from pyfatfs.PyFatFS import PyFatFS

def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()

# ============ Working Thread ============
class ExtractionWorker(QThread):
    """Background worker for extracting and merging floppy images"""
    status_update = Signal(str)
    progress_value = Signal(int)
    task_finished = Signal(bool, str)
    error = Signal(str)
    info = Signal(str)
    prompt_signal = Signal(str)

    def __init__(self, src, out):
        super().__init__()
        self.src = src
        self.out = out
        self.prompt_event = threading.Event()
        self.user_response = False

    def run(self):
        search_pattern = os.path.join(self.src, "[Ff][Ll][Pp]*.[Ii][Mm][Gg]")
        img_files = sorted(glob.glob(search_pattern))
        total_files = len(img_files)
        
        if total_files == 0:
            self.info.emit("No files matching FLP*.IMG format found!")
            return
            
        os.makedirs(self.out, exist_ok=True)
        
        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(temp_zip_fd)
        
        errors = []
        manifest = None
        manifest_path = os.path.join(self.src, "manifest.json")
        
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as mf:
                    manifest = json.load(mf)
            except Exception as e:
                errors.append(f"Failed to read manifest: {e}")
        else:
            errors.append("Manifest file (manifest.json) not found.")
            
        if manifest:
            img_basenames = [os.path.basename(f) for f in img_files]
            for img_name in manifest.get("images", {}).keys():
                if img_name not in img_basenames:
                    errors.append(f"[Missing File] {img_name} is in manifest but not found in directory.")

        try:
            with open(temp_zip_path, 'wb') as zip_out:
                for index, img_path in enumerate(img_files):
                    if self.isInterruptionRequested():
                        self.task_finished.emit(False, "Cancelled")
                        return
                        
                    file_name = os.path.basename(img_path)
                    self.status_update.emit(f"Reading & Verifying ({index+1}/{total_files}): {file_name}")
                    
                    if manifest and file_name in manifest.get("images", {}):
                        img_hash = compute_sha256(img_path)
                        if img_hash != manifest["images"][file_name]["image_hash"]:
                            errors.append(f"[Image Mismatch] {file_name}")
                    elif manifest:
                        errors.append(f"[Missing in Manifest] {file_name}")
                        
                    fat = None
                    extracted_chunk = False
                    try:
                        fat = PyFatFS(img_path, read_only=True)
                        files_list = list(fat.walk.files("/"))
                        
                        target_virt_path = None
                        for virt_path in files_list:
                            virt_path = virt_path.replace("\\", "/")
                            if not virt_path.startswith("/"):
                                virt_path = "/" + virt_path
                                
                            filename = os.path.basename(virt_path)
                            if filename.upper().endswith(".DAT"):
                                target_virt_path = virt_path
                                break
                                
                        if not target_virt_path and files_list:
                            target_virt_path = files_list[0].replace("\\", "/")
                            if not target_virt_path.startswith("/"):
                                target_virt_path = "/" + target_virt_path
                                
                        if target_virt_path:
                            with fat.openbin(target_virt_path, 'rb') as src_f:
                                chunk_hash_obj = hashlib.sha256()
                                while True:
                                    chunk = src_f.read(65536)
                                    if not chunk:
                                        break
                                    zip_out.write(chunk)
                                    chunk_hash_obj.update(chunk)
                                extracted_chunk = True
                                chunk_hash = chunk_hash_obj.hexdigest()
                                
                                if manifest and file_name in manifest.get("images", {}):
                                    if chunk_hash != manifest["images"][file_name]["chunk_hash"]:
                                        errors.append(f"[Chunk Mismatch] {file_name}")
                        else:
                            errors.append(f"[No Data] {file_name} contains no readable files.")
                                
                    except Exception as e:
                        errors.append(f"[Read Error] {file_name}: {e}")
                    finally:
                        if fat is not None:
                            try: fat.close()
                            except Exception: pass
                            
                    # Update progress (0-100)
                    self.progress_value.emit(min(100, round((index + 1) / total_files * 100)))
                    
            if manifest and os.path.exists(temp_zip_path):
                final_zip_hash = compute_sha256(temp_zip_path)
                if final_zip_hash != manifest.get("zip_hash"):
                    errors.append("[ZIP Mismatch] Merged ZIP hash does not match manifest.")
                    
            if errors:
                msg = "Verification failed or manifest missing!\n\n"
                for err in errors[:10]:
                    msg += f"- {err}\n"
                if len(errors) > 10:
                    msg += f"- ... and {len(errors) - 10} more errors.\n"
                msg += "\nDo you want to Continue Anyway?"
                
                self.user_response = False
                self.prompt_event.clear()
                self.prompt_signal.emit(msg)
                
                # Block worker thread until user responds in the main UI thread
                self.prompt_event.wait()
                
                if not self.user_response:
                    self.status_update.emit("❌ Aborted by user.")
                    self.task_finished.emit(False, "Aborted by user due to verification failure.")
                    return
                    
            self.status_update.emit("Split parts merged successfully, extracting final ZIP archive...")
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(self.out)
                
            self.progress_value.emit(100)
            self.task_finished.emit(True, f"All floppy chunks have been successfully merged and extracted to:\n{self.out}")

        except Exception as e:
            self.error.emit(str(e))
        finally:
            if os.path.exists(temp_zip_path):
                try: os.remove(temp_zip_path)
                except: pass

# ============ Main Window Class ============
class FloppyExtractorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("CloudCensorFxxkerWithFloppy - Extractor - v2.00a Based on Qt5")
        self.resize(900, 600)
        self.setMinimumSize(500, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(8)

        # 1. Source Selection
        frame_src = QGroupBox(" 1. Select Directory Containing Floppy Images ")
        layout_src = QHBoxLayout()
        self.source_entry = QLineEdit()
        self.source_entry.setPlaceholderText("Select source folder...")
        btn_src = QPushButton("Browse...")
        btn_src.setFixedWidth(100)
        btn_src.clicked.connect(self.browse_source)
        
        layout_src.addWidget(self.source_entry)
        layout_src.addWidget(btn_src)
        frame_src.setLayout(layout_src)
        main_layout.addWidget(frame_src)

        # 2. Output Directory
        frame_out = QGroupBox(" 2. Select Target Directory for Extraction and Merging ")
        layout_out = QHBoxLayout()
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Select output folder...")
        btn_out = QPushButton("Browse...")
        btn_out.setFixedWidth(100)
        btn_out.clicked.connect(self.browse_output)
        
        layout_out.addWidget(self.output_entry)
        layout_out.addWidget(btn_out)
        frame_out.setLayout(layout_out)
        main_layout.addWidget(frame_out)

        # Progress Area
        frame_progress = QFrame()
        layout_progress = QVBoxLayout(frame_progress)
        layout_progress.setContentsMargins(0, 0, 0, 0)
        self.lbl_status = QLabel("Status: Ready")
        self.lbl_status.setStyleSheet("padding: 5px;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout_progress.addWidget(self.lbl_status)
        layout_progress.addWidget(self.progress)
        main_layout.addWidget(frame_progress)

        # Start Button
        self.btn_start = QPushButton("Start Automatic Extraction and Merging")
        self.btn_start.clicked.connect(self.start_extraction)
        self.btn_start.setStyleSheet("padding: 8px; font-weight: bold;")
        main_layout.addWidget(self.btn_start)

    @Slot()
    def browse_source(self):
        path = QFileDialog.getExistingDirectory(self, "Select Source Directory", "")
        if path: self.source_entry.setText(os.path.normpath(path))

    @Slot()
    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Target Directory", "")
        if path: self.output_entry.setText(os.path.normpath(path))

    @Slot()
    def start_extraction(self):
        src = self.source_entry.text().strip()
        out = self.output_entry.text().strip()
        
        if not src or not out:
            QMessageBox.warning(self, "Warning", "Please select both source and target directories!")
            return

        self.btn_start.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.worker = ExtractionWorker(src, out)
        self.worker.status_update.connect(self.lbl_status.setText)
        self.worker.progress_value.connect(self.progress.setValue)
        self.worker.prompt_signal.connect(self.on_prompt)
        self.worker.task_finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.info.connect(self.on_info)
        self.worker.start()

    @Slot(str)
    def on_prompt(self, msg):
        # Executed in main thread: Shows dialog and unblocks the worker thread
        res = QMessageBox.warning(
            self, 
            "Verification Warning", 
            msg, 
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        self.worker.user_response = (res == QMessageBox.Yes)
        self.worker.prompt_event.set()

    @Slot(bool, str)
    def on_finished(self, success, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        self.btn_start.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            if message and "Aborted" not in message and "Cancelled" not in message:
                 QMessageBox.critical(self, "Error", message)
                 
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    @Slot(str)
    def on_error(self, error_msg):
        self.lbl_status.setText("❌ An error occurred")
        self.progress.setValue(0)
        QMessageBox.critical(self, "Error", f"Processing failed:\n{error_msg}")
        self.btn_start.setEnabled(True)
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    @Slot(str)
    def on_info(self, info_msg):
        QMessageBox.information(self, "Info", info_msg)
        self.btn_start.setEnabled(True)
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            # Force release prompt block if window is closed during verification
            if hasattr(self.worker, 'prompt_event') and not self.worker.prompt_event.is_set():
                self.worker.user_response = False
                self.worker.prompt_event.set()
            self.worker.wait(2000)
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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(script_dir, "fonts", "DreamHanSansCN-Medium-W18.ttf")
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
    
    window = FloppyExtractorApp()
    window.show()
    sys.exit(app.exec_())