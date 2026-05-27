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

# 🔴 Optimized Geometry Configurations Matrix with Human-Readable Display Names
FLOPPY_CONFIGS = {
    "720KB (Standard Double Density Floppy)": {
        "key": "720KB",
        "chunk_size": 540 * 1024,
        "total_sectors": 1440,
        "sectors_per_track": 9,
        "sectors_per_cluster": 2,
        "root_dir_entries": 112,
        "sectors_per_fat": 3,
        "media_descriptor": 0xF9
    },
    "1.44MB (Standard High Density Floppy)": {
        "key": "1440KB",
        "chunk_size": 1320 * 1024,
        "total_sectors": 2880,
        "sectors_per_track": 18,
        "sectors_per_cluster": 2,
        "root_dir_entries": 224,
        "sectors_per_fat": 9,
        "media_descriptor": 0xF0
    },
    "2.88MB (Extreme Density Floppy)": {
        "key": "2880KB",
        "chunk_size": 2760 * 1024,
        "total_sectors": 5760,
        "sectors_per_track": 36,
        "sectors_per_cluster": 2,
        "root_dir_entries": 240,
        "sectors_per_fat": 9,
        "media_descriptor": 0xF0
    },
    "5.76MB (RARE Triple Density Floppy)": {
        "key": "5760KB",
        "chunk_size": 5640 * 1024,
        "total_sectors": 11520,
        "sectors_per_track": 72,
        "sectors_per_cluster": 4,
        "root_dir_entries": 240,
        "sectors_per_fat": 18,
        "media_descriptor": 0xF0
    }
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
        # 1. Boot Sector (512 bytes)
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

        # 2. FAT 1 & FAT 2
        fat_size = cfg["sectors_per_fat"] * 512
        fat = bytearray(fat_size)
        fat[0] = cfg["media_descriptor"]; fat[1] = 0xFF; fat[2] = 0xFF; fat[3] = 0xFF
        f.write(fat)
        f.write(fat)

        # 3. Root Directory
        root_dir_size = cfg["root_dir_entries"] * 32
        f.write(bytearray(root_dir_size))

        # 4. Data Area
        root_sectors = root_dir_size // 512
        used_sectors = 1 + (2 * cfg["sectors_per_fat"]) + root_sectors
        data_sectors = cfg["total_sectors"] - used_sectors
        data_area_size = data_sectors * 512
        f.write(bytearray(data_area_size))

class FloppyCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Compressor - v1.21a")
        self.root.geometry("650x450")
        self.source_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        
        # Default combo selection text
        self.capacity_display_var = tk.StringVar(value="1.44MB (Standard High Density Floppy)")
        self.create_widgets()

    def create_widgets(self):
        # 1. Select Source
        frame_src = ttk.LabelFrame(self.root, text=" 1. Select Source ", padding=10)
        frame_src.pack(fill="x", padx=15, pady=8)
        ttk.Entry(frame_src, textvariable=self.source_path, width=42).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_src, text="File", command=self.browse_file, width=6).pack(side="right", padx=2)
        ttk.Button(frame_src, text="Folder", command=self.browse_folder, width=6).pack(side="right", padx=2)

        # 2. Select Floppy Format Size (UI Optimized)
        frame_cfg = ttk.LabelFrame(self.root, text=" 2. Floppy Target Specification ", padding=10)
        frame_cfg.pack(fill="x", padx=15, pady=8)
        ttk.Label(frame_cfg, text="Select Format Type: ").pack(side="left", padx=5)
        self.combo_capacity = ttk.Combobox(
            frame_cfg,
            textvariable=self.capacity_display_var,
            values=list(FLOPPY_CONFIGS.keys()),
            state="readonly",
            width=36
        )
        self.combo_capacity.pack(side="left", padx=5)
        self.lbl_chunk_hint = ttk.Label(frame_cfg, text="Split Chunk Size: 1320 KB", foreground="#0066cc", padding=9)
        self.lbl_chunk_hint.pack(side="left", padx=5)
        self.combo_capacity.bind("<<ComboboxSelected>>", self.update_chunk_hint)

        # 3. Select Output
        frame_out = ttk.LabelFrame(self.root, text=" 3. Select Output Directory ", padding=10)
        frame_out.pack(fill="x", padx=15, pady=8)
        ttk.Entry(frame_out, textvariable=self.output_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_out, text="Browse...", command=self.browse_output).pack(side="right", padx=5)

        # Progress Area
        frame_progress = ttk.Frame(self.root, padding=10)
        frame_progress.pack(fill="x", padx=15, pady=5)
        self.lbl_status = ttk.Label(frame_progress, text="Ready", padding=5)
        self.lbl_status.pack(anchor="w", pady=2)
        self.progress = ttk.Progressbar(frame_progress, orient="horizontal", mode="indeterminate")
        self.progress.pack(fill="x", pady=5)

        self.btn_start = ttk.Button(self.root, text="Start Matrix Compression and Generate Floppy Images", command=self.start_compression_thread)
        self.btn_start.pack(pady=10)

    def update_chunk_hint(self, event=None):
        selected_display = self.capacity_display_var.get()
        chunk_kb = FLOPPY_CONFIGS[selected_display]["chunk_size"] // 1024
        self.lbl_chunk_hint.config(text=f"Split Chunk Size: {chunk_kb} KB")

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
        self.combo_capacity.config(state="disabled")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)

        threading.Thread(target=self.compress_process, daemon=True).start()

    def compress_process(self):
        src = self.source_path.get()
        out = self.output_dir.get()
        
        # Map the verbose display text back to hardware configuration
        selected_display = self.capacity_display_var.get()
        cfg = FLOPPY_CONFIGS[selected_display]
        chunk_size = cfg["chunk_size"]
        raw_format_key = cfg["key"]

        temp_zip = os.path.join(tempfile.gettempdir(), f"floppy_temp_{os.getpid()}.zip")

        try:
            self.root.after(0, lambda: self.lbl_status.config(text="Step 1/2: Compressing source files into temporary archive..."))

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
                "floppy_format": raw_format_key, # Keep clean key strings inside json for backend parsing
                "images": {}
            }

            file_size = os.path.getsize(temp_zip)
            total_disks = (file_size + chunk_size - 1) // chunk_size

            def switch_to_determinate_mode(total, fmt):
                self.progress.stop()
                self.progress.config(mode="determinate", maximum=total, value=0)
                self.lbl_status.config(text=f"Step 2/2: Splitting and Writing {fmt} Images (Total: {total})...")

            self.root.after(0, switch_to_determinate_mode, total_disks, raw_format_key)

            with open(temp_zip, 'rb') as f:
                disk_num = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    disk_num += 1
                    
                    chunk_hash = hashlib.sha256(chunk).hexdigest()

                    img_name = f"FLP{disk_num:05d}.IMG"
                    img_path = os.path.join(out, img_name)

                    self.root.after(0, lambda d=disk_num, t=total_disks: self.lbl_status.config(
                        text=f"Writing {raw_format_key} Image ({d}/{t})..."))

                    create_dynamic_fat12_image(img_path, cfg)

                    try:
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

            self.root.after(0, lambda f=raw_format_key, t=total_disks: messagebox.showinfo(
                "Success", 
                f"Successfully generated {t} floppy image(s) using {f} standard layout!\n\nDestination:\n{out}"
            ))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed:\n{str(e)}"))
            self.root.after(0, lambda: self.lbl_status.config(text="❌ An error occurred"))
        finally:
            if os.path.exists(temp_zip):
                try: os.remove(temp_zip)
                except: pass
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: self.btn_start.config(state="normal"))
            self.root.after(0, lambda: self.combo_capacity.config(state="readonly"))

if __name__ == "__main__":
    root = tk.Tk()
    app = FloppyCompressorApp(root)
    root.mainloop()
