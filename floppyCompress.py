import logging
import os
import glob
import struct
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pyfatfs.PyFatFS import PyFatFS
import zipfile
import tempfile
import hashlib
import json
import ctypes
import sys
import platform

# Optimized buffer for larger 2.88MB floppy images
def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):  # Upgrade to 64KB chunks for speed
            h.update(b)
    return h.hexdigest()

def setup_high_dpi():
    if platform.system() == 'Windows':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass

class FloppyExtractorApp:
    def __init__(self, root):
        def get_scale_factor():
            if platform.system() == 'Windows':
                try:
                    return ctypes.windll.user32.GetDpiForSystem() / 96.0
                except:
                    hdc = ctypes.windll.user32.GetDC(0)
                    dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
                    ctypes.windll.user32.ReleaseDC(0, hdc)
                    return dpi / 96.0
            # Linux and macOS typically handle DPI scaling automatically, but we can attempt to read GDK_SCALE for Linux
            try:
                # Some Linux environments use GDK_SCALE for scaling factor, default to 1.0 if not set
                return float(os.environ.get('GDK_SCALE', 1.0))
            except:
                return 1.0
        scale = get_scale_factor()
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Extractor - v1.20b")
        BASE_W, BASE_H = 650, 450
        self.root.geometry(f"{int(BASE_W * scale)}x{int(BASE_H * scale)}")
        self.source_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        
        self.create_widgets()

    def create_widgets(self):
        frame_src = ttk.LabelFrame(self.root, text=" 1. Select Directory Containing Floppy Images ", padding=10)
        frame_src.pack(fill="x", padx=15, pady=10)
        
        ttk.Entry(frame_src, textvariable=self.source_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_src, text="Browse...", command=self.browse_source).pack(side="right", padx=5)

        frame_out = ttk.LabelFrame(self.root, text=" 2. Select Target Directory for Extraction and Merging ", padding=10)
        frame_out.pack(fill="x", padx=15, pady=10)
        
        ttk.Entry(frame_out, textvariable=self.output_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_out, text="Browse...", command=self.browse_output).pack(side="right", padx=5)

        frame_progress = ttk.Frame(self.root, padding=10)
        frame_progress.pack(fill="x", padx=15, pady=10)
        
        self.lbl_status = ttk.Label(frame_progress, text="Ready", padding=10)
        self.lbl_status.pack(anchor="w", pady=2)
        
        self.progress = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=5)

        self.btn_start = ttk.Button(self.root, text="Start Automatic Extraction and Merging", command=self.start_extraction_thread)
        self.btn_start.pack(pady=15)

    def browse_source(self):
        directory = filedialog.askdirectory()
        if directory: self.source_dir.set(os.path.normpath(directory))

    def browse_output(self):
        directory = filedialog.askdirectory()
        if directory: self.output_dir.set(os.path.normpath(directory))

    def start_extraction_thread(self):
        if not self.source_dir.get() or not self.output_dir.get():
            messagebox.showwarning("Warning", "Please select both source and target directories!")
            return
        
        self.btn_start.config(state="disabled")
        threading.Thread(target=self.extract_process, daemon=True).start()

    def extract_process(self):
        src = self.source_dir.get()
        out = self.output_dir.get()
        
        search_pattern = os.path.join(src, "[Ff][Ll][Pp]*.[Ii][Mm][Gg]")
        img_files = sorted(glob.glob(search_pattern))
        
        total_files = len(img_files)
        if total_files == 0:
            self.root.after(0, lambda: messagebox.showinfo("Info", "No files matching FLP*.IMG format found!"))
            self.root.after(0, lambda: self.btn_start.config(state="normal"))
            return

        self.root.after(0, lambda: self.progress.config(maximum=total_files + 1, value=0))
        os.makedirs(out, exist_ok=True)

        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(temp_zip_fd)

        errors = []
        manifest = None
        manifest_path = os.path.join(src, "manifest.json")

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
                    file_name = os.path.basename(img_path)
                    self.root.after(0, lambda f=file_name, i=index: self.lbl_status.config(text=f"Reading & Verifying ({i+1}/{total_files}): {f}"))
                    
                    if manifest and file_name in manifest.get("images", {}):
                        img_hash = compute_sha256(img_path)
                        if img_hash != manifest["images"][file_name]["image_hash"]:
                            errors.append(f"[Image Mismatch] {file_name}")
                    elif manifest:
                        errors.append(f"[Missing in Manifest] {file_name}")
                        
                    fat = None
                    chunk_data = b""
                    extracted_chunk = False
                    try:
                        # PyFatFS safely opens 2.88MB as long as BPB is standard
                        fat = PyFatFS(img_path, read_only=True)
                        files_list = list(fat.walk.files("/"))
                        
                        for virt_path in files_list:
                            virt_path = virt_path.replace("\\", "/")
                            if not virt_path.startswith("/"):
                                virt_path = "/" + virt_path
                                
                            filename = os.path.basename(virt_path)
                            if filename.upper().endswith(".DAT"):
                                with fat.openbin(virt_path, 'rb') as src_f:
                                    chunk_data = src_f.read()
                                extracted_chunk = True
                                break
                        if not extracted_chunk and files_list:
                            virt_path = files_list[0].replace("\\", "/")
                            if not virt_path.startswith("/"):
                                virt_path = "/" + virt_path
                            with fat.openbin(virt_path, 'rb') as src_f:
                                chunk_data = src_f.read()
                            extracted_chunk = True
                            
                        if extracted_chunk:
                            if manifest and file_name in manifest.get("images", {}):
                                chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                                if chunk_hash != manifest["images"][file_name]["chunk_hash"]:
                                    errors.append(f"[Chunk Mismatch] {file_name}")
                                    
                            zip_out.write(chunk_data)
                        else:
                            errors.append(f"[No Data] {file_name} contains no readable files.")
                                
                    except Exception as e:
                        errors.append(f"[Read Error] {file_name}: {e}")
                    finally:
                        if fat is not None:
                            try: fat.close()
                            except Exception: pass
                    
                    self.root.after(0, lambda i=index+1: self.progress.config(value=i))

            if manifest and os.path.exists(temp_zip_path):
                final_zip_hash = compute_sha256(temp_zip_path)
                if final_zip_hash != manifest.get("zip_hash"):
                    errors.append("[ZIP Mismatch] Merged ZIP hash does not match manifest.")

            if errors:
                event = threading.Event()
                result = [False]
                
                def prompt():
                    try:
                        msg = "Verification failed or manifest missing!\n\n"
                        for err in errors[:10]:
                            msg += f"- {err}\n"
                        if len(errors) > 10:
                            msg += f"- ... and {len(errors) - 10} more errors.\n"
                        msg += "\nDo you want to Continue Anyway?"
                        result[0] = messagebox.askyesno("Verification Warning", msg, icon='warning')
                    finally:
                        event.set() # Avoid thread deadlock even if window closes abruptly
                    
                self.root.after(0, prompt)
                event.wait()
                
                if not result[0]:
                    self.root.after(0, lambda: self.lbl_status.config(text="❌ Aborted by user."))
                    raise Exception("Aborted by user due to verification failure.")
                    
            self.root.after(0, lambda: self.lbl_status.config(text="Split parts merged successfully, extracting final ZIP archive..."))
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(out)
                
            # Thread-safe UI update
            self.root.after(0, lambda: self.progress.config(value=total_files + 1))
            self.root.after(0, lambda: self.lbl_status.config(text="✅ Extraction and merging successful!"))
            self.root.after(0, lambda: messagebox.showinfo("Success", f"All floppy chunks have been successfully merged and extracted to:\n{out}"))

        except Exception as e:
            if "Aborted by user" not in str(e):
                self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed:\n{str(e)}"))
            self.root.after(0, lambda: self.lbl_status.config(text="❌ An error occurred"))
        finally:
            if os.path.exists(temp_zip_path):
                try: os.remove(temp_zip_path)
                except: pass
            self.root.after(0, lambda: self.btn_start.config(state="normal"))

if __name__ == "__main__":
    setup_high_dpi()
    root = tk.Tk()
    app = FloppyExtractorApp(root)
    root.mainloop()
