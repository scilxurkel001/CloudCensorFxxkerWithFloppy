import os
import struct
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pyfatfs.PyFatFS import PyFatFS
import zipfile
import tempfile
import hashlib
import json

# 🔴 Gold standard line for 2.88MB floppy to keep 100% compatibility and enough FS overhead
CHUNK_SIZE = 2760 * 1024  

# General utility functions with optimized 64KB buffer for speed
def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()

def create_blank_fat12_image(path):
    """Generate a standard BLANK 2.88MB FAT12 floppy disk image (ED Floppy)"""
    with open(path, 'wb') as f:
        # 1. Boot Sector (512 bytes)
        bs = bytearray(512)
        bs[0:3] = b'\xEB\x3C\x90'
        bs[3:11] = b'MSDOS5.0'
        struct.pack_into('<H', bs, 11, 512)  # Bytes per sector
        bs[13] = 2                           # 🔴 Standard 2 sectors per cluster (1KB per cluster)
        struct.pack_into('<H', bs, 14, 1)    # Reserved sectors
        bs[16] = 2                           # Number of FATs
        struct.pack_into('<H', bs, 17, 240)  # 🔴 Standard 2.88MB root dir entries (240 entries)
        struct.pack_into('<H', bs, 19, 5760) # 🔴 Standard 2.88MB total sectors (5760 sectors)
        bs[21] = 0xF0                        # Media descriptor
        struct.pack_into('<H', bs, 22, 9)    # Sectors per FAT
        struct.pack_into('<H', bs, 24, 36)   # 🔴 Standard 2.88MB sectors per track (36 SPT)
        struct.pack_into('<H', bs, 26, 2)    # Heads
        bs[38] = 0x29                        # Extended boot signature
        struct.pack_into('<I', bs, 39, 0x12345678) # Volume serial
        bs[43:54] = b'NO NAME    '           # Volume label
        bs[54:62] = b'FAT12   '              # File system type
        bs[510] = 0x55
        bs[511] = 0xAA
        f.write(bs)

        # 2. FAT 1 & FAT 2 (9 sectors each = 4608 bytes)
        fat = bytearray(4608)
        fat[0] = 0xF0; fat[1] = 0xFF; fat[2] = 0xFF; fat[3] = 0xFF
        f.write(fat)
        f.write(fat)

        # 3. Root Directory (240 entries = 15 sectors = 7680 bytes)
        # 🔴 2.88MB Root dir requires 15 sectors (7680 bytes)
        f.write(bytearray(7680))

        # 4. Data Area (5760 - 1 - 9 - 9 - 15 = 5726 sectors = 2,931,712 bytes)
        # 🔴 2.88MB Standard Data area size
        f.write(bytearray(2931712))

class FloppyCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Compressor - v1.10b")
        self.root.geometry("620x400")
        self.source_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.create_widgets()

    def create_widgets(self):
        frame_src = ttk.LabelFrame(self.root, text=" 1. Select Source ", padding=10)
        frame_src.pack(fill="x", padx=15, pady=10)

        ttk.Entry(frame_src, textvariable=self.source_path, width=45).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_src, text="Browse File", command=self.browse_file).pack(side="right", padx=2)
        ttk.Button(frame_src, text="Browse Folder", command=self.browse_folder).pack(side="right", padx=2)

        frame_out = ttk.LabelFrame(self.root, text=" 2. Select Output Directory ", padding=10)
        frame_out.pack(fill="x", padx=15, pady=10)

        ttk.Entry(frame_out, textvariable=self.output_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_out, text="Browse...", command=self.browse_output).pack(side="right", padx=5)

        frame_progress = ttk.Frame(self.root, padding=10)
        frame_progress.pack(fill="x", padx=15, pady=10)

        self.lbl_status = ttk.Label(frame_progress, text="Ready", padding=10)
        self.lbl_status.pack(anchor="w", pady=2)

        self.progress = ttk.Progressbar(frame_progress, orient="horizontal", mode="indeterminate")
        self.progress.pack(fill="x", pady=5)

        self.btn_start = ttk.Button(self.root, text="Start Compression and Generate Floppy Image", command=self.start_compression_thread)
        self.btn_start.pack(pady=15)

    def browse_file(self):
        path = filedialog.askopenfilename()
        if path: self.source_path.set(os.path.normpath(path))

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.source_path.set(os.path.normpath(path))

    def browse_output(self):
        path = filedialog.askdirectory()
        if path: self.output_dir.set(os.path.normpath(path))

    def start_compression_thread(self):
        if not self.source_path.get() or not self.output_dir.get():
            messagebox.showwarning("Warning", "Please select both source and output directories!")
            return

        self.btn_start.config(state="disabled")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)

        threading.Thread(target=self.compress_process, daemon=True).start()

    def compress_process(self):
        src = self.source_path.get()
        out = self.output_dir.get()
        
        temp_zip = os.path.join(tempfile.gettempdir(), f"floppy_temp_{os.getpid()}.zip")

        try:
            self.root.after(0, lambda: self.lbl_status.config(text="Step 1/2: Compressing source files..."))

            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                if os.path.isfile(src):
                    zf.write(src, os.path.basename(src))
                else:
                    base_dir = src.rstrip(os.sep)
                    for root_dir, _, files in os.walk(base_dir):
                        for file in files:
                            full_path = os.path.join(root_dir, file)
                            arcname = os.path.relpath(full_path, base_dir)
                            zf.write(full_path, arcname)

            zip_hash = compute_sha256(temp_zip)
            manifest = {
                "zip_hash": zip_hash,
                "images": {}
            }

            file_size = os.path.getsize(temp_zip)
            total_disks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

            # 🔴 Thread-safe GUI transformation using after()
            def switch_to_determinate_mode(total):
                self.progress.stop()
                self.progress.config(mode="determinate", maximum=total, value=0)
                self.lbl_status.config(text=f"Step 2/2: Splitting and Writing 2.88MB Floppy Images (Total: {total})...")

            self.root.after(0, switch_to_determinate_mode, total_disks)

            with open(temp_zip, 'rb') as f:
                disk_num = 0
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    disk_num += 1
                    
                    chunk_hash = hashlib.sha256(chunk).hexdigest()

                    img_name = f"FLP{disk_num:05d}.IMG"
                    img_path = os.path.join(out, img_name)

                    self.root.after(0, lambda d=disk_num, t=total_disks: self.lbl_status.config(
                        text=f"Writing Floppy Image ({d}/{t})..."))

                    create_blank_fat12_image(img_path)

                    try:
                        # PyFatFS successfully initializes because BPB geometry is perfectly mapped
                        fat = PyFatFS(img_path)
                        fat_filename = f"FLP{disk_num:05d}.DAT"
                        
                        with fat.openbin(f"/{fat_filename}", 'wb') as dst_f:
                            dst_f.write(chunk)
                        fat.close()
                    except Exception as e:
                        raise RuntimeError(f"Failed to write to pyfatfs [{img_name}]: {e}") from e

                    image_hash = compute_sha256(img_path)
                    manifest["images"][img_name] = {
                        "chunk_hash": chunk_hash,
                        "image_hash": image_hash
                    }

                    self.root.after(0, lambda v=disk_num: self.progress.config(value=v))

            # Export manifest.json
            manifest_path = os.path.join(out, "manifest.json")
            with open(manifest_path, 'w', encoding='utf-8') as mf:
                json.dump(manifest, mf, indent=4)

            if os.path.exists(temp_zip):
                os.remove(temp_zip)

            self.root.after(0, lambda: messagebox.showinfo(
                "Success", 
                f"2.88MB Floppy images and manifest.json generated at:\n{out}\n\n💡 Tip: Splitting count reduced significantly due to 2760KB density!"
            ))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed:\n{str(e)}"))
            self.root.after(0, lambda: self.lbl_status.config(text="❌ An error occurred"))
        finally:
            if os.path.exists(temp_zip):
                try: os.remove(temp_zip)
                except: pass
            # 🔴 Thread-safe GUI resets
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: self.btn_start.config(state="normal"))

if __name__ == "__main__":
    root = tk.Tk()
    app = FloppyCompressorApp(root)
    root.mainloop()
