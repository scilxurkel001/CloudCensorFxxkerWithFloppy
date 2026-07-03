# -*- coding: utf-8 -*-
import logging
import os
import glob
import threading
import hashlib
import json
import tempfile
import webbrowser
import zipfile
import sys
import platform

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, 
    QPushButton, QProgressBar, QGroupBox, 
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QFrame,
    QDialog
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

# ==================== ACTIVATION SYSTEM ====================
import uuid

KEY_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
# Secret Magic bytes to identify the activation file format
_ACTIVATION_MAGIC = b'CCFX\x01'
# Static salt for key derivation, should be kept secret and consistent
_ACTIVATION_SALT = "Scilxurkel-LOVE-Gensokyo!"

def get_machine_code() -> str:
    mac = str(uuid.getnode())
    info = f"{mac}|{platform.system()}|{platform.node()}"
    return hashlib.md5(info.encode('utf-8')).hexdigest().upper()[:16]

def get_activation_file_path() -> str:
    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base_dir = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    config_dir = os.path.join(base_dir, "CloudCensorFxxker")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "activation.dat")

def _derive_key_stream(password: str, length: int) -> bytes:
    stream = b''
    counter = 0
    while len(stream) < length:
        block = hashlib.sha256(f"{_ACTIVATION_SALT}|{password}|{counter}".encode('utf-8')).digest()
        stream += block
        counter += 1
    return stream[:length]

def _crypt_bytes(data: bytes, password: str) -> bytes:
    key_stream = _derive_key_stream(password, len(data))
    return bytes(d ^ k for d, k in zip(data, key_stream))

def _save_activation_data(data: dict) -> None:
    plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')
    password = f"{get_machine_code()}|{_ACTIVATION_SALT}"
    ciphertext = _crypt_bytes(plaintext, password)
    path = get_activation_file_path()
    with open(path, 'wb') as f:
        f.write(_ACTIVATION_MAGIC)
        f.write(ciphertext)

def _load_activation_data() -> dict:
    path = get_activation_file_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        if not raw.startswith(_ACTIVATION_MAGIC):
            return None
        ciphertext = raw[len(_ACTIVATION_MAGIC):]
        password = f"{get_machine_code()}|{_ACTIVATION_SALT}"
        plaintext = _crypt_bytes(ciphertext, password)
        return json.loads(plaintext.decode('utf-8'))
    except Exception:
        return None

def validate_activation_key(key: str, machine_code: str) -> bool:
    clean = key.replace('-', '').upper().strip()
    if len(clean) != 25:
        return False
    try:
        values = [KEY_CHARSET.index(c) for c in clean]
    except ValueError:
        return False

    # Layer 1
    for i in range(0, 25, 5):
        g = values[i:i+5]
        checksum = (g[0] * 2 + g[1] * 3 + g[2] * 5 + g[3] * 7) % 24
        if checksum != g[4]:
            return False

    # Layer 2
    checksums = [values[i] for i in [4, 9, 14, 19, 24]]
    cross_total = sum(c * (i + 1) for i, c in enumerate(checksums))
    if cross_total % 24 not in (2, 6, 8, 13):
        return False

    # Layer 3
    if sum(values) % 24 not in (6, 9, 10, 11, 13, 15):
        return False

    # Layer 4
    fingerprint = ''.join(KEY_CHARSET[values[i]] for i in [0, 5, 10, 15, 20])
    expected_fp = hashlib.md5(
        f"{machine_code}|{_ACTIVATION_SALT}|finger".encode('utf-8')
    ).hexdigest().upper()[:5]
    expected_fp = ''.join(c if c in KEY_CHARSET else KEY_CHARSET[ord(c) % len(KEY_CHARSET)] for c in expected_fp)
    if fingerprint != expected_fp:
        return False

    return True

def is_activated() -> bool:
    data = _load_activation_data()
    if not data:
        return False
    if data.get("machine") != get_machine_code():
        return False
    return data.get("activated", False) and validate_activation_key(
        data.get("key", ""), data.get("machine", "")
    )

def activate_app(key: str) -> bool:
    machine = get_machine_code()
    if validate_activation_key(key, machine):
        _save_activation_data({
            "activated": True,
            "key": key.upper(),
            "machine": machine,
            "time": int(__import__('time').time())
        })
        return True
    return False

# ==================== ACTIVATION DIALOG ====================
class ActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 Product Activation")
        self.setFixedSize(520, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("CloudCensorFxxker Activation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4fc3f7;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Machine Code Display
        machine_frame = QFrame()
        machine_frame.setStyleSheet("""
            QFrame { background-color: #1e272e; border: 1px solid #455a64; border-radius: 5px; }
        """)
        mf_layout = QVBoxLayout(machine_frame)
        mf_layout.setContentsMargins(10, 8, 10, 8)
        mf_layout.setSpacing(4)

        mc_label = QLabel("Your Machine Code (send this to get your key):")
        mc_label.setStyleSheet("color: #b0bec5; font-size: 11px;")
        mf_layout.addWidget(mc_label)

        mc_row = QHBoxLayout()
        self.txt_machine = QLineEdit(get_machine_code())
        self.txt_machine.setReadOnly(True)
        self.txt_machine.setStyleSheet("""
            QLineEdit {
                padding: 6px; font-family: Consolas, monospace; font-size: 13px;
                background-color: #263238; color: #ffca28; border: 1px solid #455a64;
            }
        """)
        btn_copy = QPushButton("Copy")
        btn_copy.setFixedWidth(60)
        btn_copy.setStyleSheet("""
            QPushButton { background-color: #455a64; color: white; padding: 4px; }
            QPushButton:hover { background-color: #546e7a; }
        """)
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_machine.text()))
        mc_row.addWidget(self.txt_machine)
        mc_row.addWidget(btn_copy)
        mf_layout.addLayout(mc_row)
        layout.addWidget(machine_frame)

        info = QLabel("Enter your 25-character activation key:")
        info.setStyleSheet("color: #b0bec5;")
        layout.addWidget(info)

        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")
        self.txt_key.setMaxLength(29)
        self.txt_key.setStyleSheet("""
            QLineEdit {
                padding: 10px; font-size: 14px; font-family: Consolas, monospace;
                border: 2px solid #455a64; border-radius: 5px;
                background-color: #263238; color: #ffffff;
            }
            QLineEdit:focus { border-color: #4fc3f7; }
        """)
        self.txt_key.textChanged.connect(self.auto_format_key)
        layout.addWidget(self.txt_key)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #ef5350; min-height: 20px;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        btn_layout = QHBoxLayout()
        self.btn_activate = QPushButton("Activate")
        self.btn_activate.setFixedHeight(38)
        self.btn_activate.setStyleSheet("""
            QPushButton { background-color: #1976d2; color: white; font-weight: bold;
                border-radius: 5px; padding: 8px 20px; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0d47a1; }
        """)
        self.btn_activate.clicked.connect(self.on_activate)

        self.btn_exit = QPushButton("Exit")
        self.btn_exit.setFixedHeight(38)
        self.btn_exit.setStyleSheet("""
            QPushButton { background-color: #455a64; color: white; border-radius: 5px; padding: 8px 20px; }
            QPushButton:hover { background-color: #37474f; }
        """)
        self.btn_exit.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_activate)
        btn_layout.addWidget(self.btn_exit)
        layout.addLayout(btn_layout)

        key_info = QLabel("Click here to get a keygen.")
        key_info.setStyleSheet("color: #b0bec5; text-decoration: underline;")
        key_info.mousePressEvent = lambda e: webbrowser.open("https://github.com/scilxurkel001/sxk-soft-keygen")
        layout.addWidget(key_info)

    def auto_format_key(self, text):
        clean = text.replace('-', '').upper()
        clean = ''.join(c for c in clean if c in KEY_CHARSET)
        parts = [clean[i:i+5] for i in range(0, len(clean), 5)]
        formatted = '-'.join(parts)
        cursor_pos = self.txt_key.cursorPosition()
        self.txt_key.blockSignals(True)
        self.txt_key.setText(formatted)
        new_pos = cursor_pos
        dash_count = formatted[:cursor_pos].count('-')
        old_dash_count = text[:cursor_pos].count('-')
        if dash_count > old_dash_count:
            new_pos += (dash_count - old_dash_count)
        self.txt_key.setCursorPosition(min(new_pos, len(formatted)))
        self.txt_key.blockSignals(False)

    def on_activate(self):
        key = self.txt_key.text().strip()
        if not key:
            self.lbl_status.setText("⚠️ Please enter an activation key")
            return
        if activate_app(key):
            self.lbl_status.setStyleSheet("color: #66bb6a;")
            self.lbl_status.setText("✅ Activation successful!")
            from PySide2.QtCore import QTimer
            QTimer.singleShot(500, self.accept)
        else:
            self.lbl_status.setStyleSheet("color: #ef5350;")
            self.lbl_status.setText("❌ Invalid key or not matched to this machine.")

# ==================== MAIN WINDOW ====================

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
            self.error.emit(f"An error occurred during processing: {e}")
            return
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
        self.setWindowTitle("CloudCensorFxxkerWithFloppy - Extractor - v2.10a Based on Qt5")
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
    # === ACTIVATION CHECK ===
    if not is_activated():
        dialog = ActivationDialog()
        dialog.setStyleSheet("""
            QDialog {
                background-color: #353535;
            }
            QLabel {
                color: #ffffff;
            }
        """)
        if dialog.exec_() != QDialog.Accepted:
            sys.exit(0)
    # ========================
    # Fix ToolTip style for better visibility in dark mode
    app.setStyleSheet("QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")
    # =====================================================
    script_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(script_dir, "fonts", "MiSans-Medium.ttf")
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
