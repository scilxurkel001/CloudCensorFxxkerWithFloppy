#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import struct
import threading
import hashlib
import json
import ctypes
import sys
import platform
import tempfile
import zipfile
import customtkinter as ctk
from tkinter import filedialog, messagebox

from pyfatfs.PyFatFS import PyFatFS

# ============================================================================
# Configuration for different floppy formats
# ============================================================================
FLOPPY_CONFIGS = {
    "720KB (Standard Double Density Floppy) for <= 2GB data": {
        "key": "720KB",
        "chunk_size": 540 * 1024,
        "total_sectors": 1440,
        "sectors_per_track": 9,
        "sectors_per_cluster": 2,
        "root_dir_entries": 112,
        "sectors_per_fat": 3,
        "media_descriptor": 0xF9
    },
    "1440KB (Standard High Density Floppy) for 2-4GB data": {
        "key": "1440KB",
        "chunk_size": 1320 * 1024,
        "total_sectors": 2880,
        "sectors_per_track": 18,
        "sectors_per_cluster": 2,
        "root_dir_entries": 224,
        "sectors_per_fat": 9,
        "media_descriptor": 0xF0
    },
    "2880KB (Extreme Density Floppy) for 4-8GB data": {
        "key": "2880KB",
        "chunk_size": 2760 * 1024,
        "total_sectors": 5760,
        "sectors_per_track": 36,
        "sectors_per_cluster": 2,
        "root_dir_entries": 240,
        "sectors_per_fat": 9,
        "media_descriptor": 0xF0
    },
    "5760KB (RARE Triple Density Floppy) for 8-16GB data": {
        "key": "5760KB",
        "chunk_size": 5640 * 1024,
        "total_sectors": 11520,
        "sectors_per_track": 72,
        "sectors_per_cluster": 4,
        "root_dir_entries": 240,
        "sectors_per_fat": 18,
        "media_descriptor": 0xF0
    },
    "11520KB (Quad Density Floppy) - Not Recommended": {
        "key": "11520KB",
        "chunk_size": 10960 * 1024,
        "total_sectors": 23040,
        "sectors_per_track": 144,
        "sectors_per_cluster": 8,
        "root_dir_entries": 240,
        "sectors_per_fat": 18,
        "media_descriptor": 0xF0
    },
    "23040KB (idk Density Floppy) - Not Recommended": {
        "key": "23040KB",
        "chunk_size": 22640 * 1024,
        "total_sectors": 46080,
        "sectors_per_track": 288,
        "sectors_per_cluster": 16,
        "root_dir_entries": 240,
        "sectors_per_fat": 18,
        "media_descriptor": 0xF0
    },
}

# ============================================================================
# Tool functions
# ============================================================================
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

def setup_high_dpi():
    if platform.system() == 'Windows':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass

# ============================================================================
# CustomTkinter Theme Setup
# ============================================================================
def setup_customtkinter_theme():
    """Configure CustomTkinter appearance and theme settings"""
    ctk.set_appearance_mode("System")
    
    ctk.set_default_color_theme("blue")

# ============================================================================
# Main Application Class
# ============================================================================
class FloppyCompressorApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Compressor - v1.30a - Based on CustomTkinter")
        self.root.geometry("650x450")
        # Binding variables
        self.source_path = ctk.StringVar()
        self.output_dir = ctk.StringVar()
        self.capacity_display_var = ctk.StringVar(
            value="1440KB (Standard High Density Floppy) for 2-4GB data"
        )
        
        # Create UI components
        self._create_widgets()

    def _create_widgets(self):
        """Create and layout all UI components using CustomTkinter"""
        
        def create_labeled_frame(parent, title, **frame_kwargs):
            """Function to create a labeled section frame with a title and content area"""
            container = ctk.CTkFrame(parent, **frame_kwargs)
            title_label = ctk.CTkLabel(
                container, 
                text=f" {title} ",
                font=ctk.CTkFont(weight="bold", size=12)
            )
            title_label.pack(anchor="w", padx=10, pady=(5, 0))
            content_frame = ctk.CTkFrame(container, fg_color="transparent")
            content_frame.pack(fill="both", expand=True, padx=10, pady=5)
            return container, content_frame

        # 1. Select Source Section
        frame_src, content_src = create_labeled_frame(
            self.root, "1. Select Source", corner_radius=10
        )
        frame_src.pack(fill="x", padx=15, pady=8)
        entry_frame = ctk.CTkFrame(content_src, fg_color="transparent")
        entry_frame.pack(fill="x", expand=True)
        
        ctk.CTkEntry(
            entry_frame, 
            textvariable=self.source_path, 
            width=300,
            placeholder_text="Select file or folder..."
        ).pack(side="left", padx=(0, 5), expand=True, fill="x")
        
        btn_frame = ctk.CTkFrame(entry_frame, fg_color="transparent")
        btn_frame.pack(side="right")
        
        ctk.CTkButton(
            btn_frame, text="📁 File", command=self.browse_file, width=60
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame, text="📂 Folder", command=self.browse_folder, width=60
        ).pack(side="left", padx=2)

        # 2. Floppy Format Configuration
        frame_cfg, content_cfg = create_labeled_frame(
            self.root, "2. Floppy Target Specification", corner_radius=10
        )
        frame_cfg.pack(fill="x", padx=15, pady=8)
        
        # Row 1: Combobox
        row1 = ctk.CTkFrame(content_cfg, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))
        
        ctk.CTkLabel(row1, text="Select Format Type:").pack(side="left", padx=5)
        
        self.combo_capacity = ctk.CTkComboBox(
            row1,
            variable=self.capacity_display_var,
            values=list(FLOPPY_CONFIGS.keys()),
            state="readonly",
            width=400,
            command=lambda _: self.update_chunk_hint()
        )
        self.combo_capacity.pack(side="left", padx=5)
        self.combo_capacity.set(self.capacity_display_var.get())

        # Row 2: Chunk hint label
        row2 = ctk.CTkFrame(content_cfg, fg_color="transparent")
        row2.pack(fill="x")
        
        self.lbl_chunk_hint = ctk.CTkLabel(
            row2,
            text="Split Chunk Size: 1320 KB",
            text_color="#3498db",
            font=ctk.CTkFont(size=11)
        )
        self.lbl_chunk_hint.pack(side="left", padx=(120, 0))
        
        # Initial update of chunk hint based on default selection
        self.update_chunk_hint()

        # 3. Output Directory
        frame_out, content_out = create_labeled_frame(
            self.root, "3. Select Output Directory", corner_radius=10
        )
        frame_out.pack(fill="x", padx=15, pady=8)
        
        out_frame = ctk.CTkFrame(content_out, fg_color="transparent")
        out_frame.pack(fill="x", expand=True)
        
        ctk.CTkEntry(
            out_frame, 
            textvariable=self.output_dir, 
            width=350,
            placeholder_text="Output folder..."
        ).pack(side="left", padx=(0, 5), expand=True, fill="x")
        
        ctk.CTkButton(
            out_frame, text="Browse...", command=self.browse_output, width=80
        ).pack(side="right", padx=5)

        # Progress & Status Area
        frame_progress = ctk.CTkFrame(self.root, corner_radius=10)
        frame_progress.pack(fill="x", padx=15, pady=5)
        
        self.lbl_status = ctk.CTkLabel(
            frame_progress, 
            text="Ready", 
            anchor="w",
            font=ctk.CTkFont(size=11)
        )
        self.lbl_status.pack(anchor="w", pady=2, padx=5)
        
        self.progress = ctk.CTkProgressBar(
            frame_progress, 
            orientation="horizontal", 
            mode="indeterminate",
            progress_color="#2ecc71"
        )
        self.progress.pack(fill="x", pady=5, padx=5)
        self.progress.set(0)

        # Start Button
        self.btn_start = ctk.CTkButton(
            self.root, 
            text="🚀 Start Matrix Compression and Generate Floppy Images", 
            command=self.start_compression_thread,
            height=40,
            font=ctk.CTkFont(weight="bold", size=12),
            corner_radius=8
        )
        self.btn_start.pack(pady=15)

    def update_chunk_hint(self, event=None):
        """Update the chunk size hint label based on the selected floppy format"""
        selected_display = self.capacity_display_var.get()
        if selected_display in FLOPPY_CONFIGS:
            chunk_kb = FLOPPY_CONFIGS[selected_display]["chunk_size"] // 1024
            self.lbl_chunk_hint.configure(text=f"Split Chunk Size: {chunk_kb} KB")

    # Messagebox and File Dialog Methods
    def browse_file(self):
        path = filedialog.askopenfilename()
        if path: 
            self.source_path.set(os.path.normpath(path))

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: 
            self.source_path.set(os.path.normpath(path))

    def browse_output(self):
        path = filedialog.askdirectory()
        if path: 
            self.output_dir.set(os.path.normpath(path))

    # Compression Process in a Separate Thread
    def start_compression_thread(self):
        if not self.source_path.get() or not self.output_dir.get():
            messagebox.showwarning("Warning", "Please select both source and output directories!")
            return

        self.btn_start.configure(state="disabled")
        self.combo_capacity.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        threading.Thread(target=self.compress_process, daemon=True).start()

    def compress_process(self):
        src = self.source_path.get()
        out = self.output_dir.get()
        
        selected_display = self.capacity_display_var.get()
        cfg = FLOPPY_CONFIGS[selected_display]
        chunk_size = cfg["chunk_size"]
        raw_format_key = cfg["key"]

        temp_zip = os.path.join(tempfile.gettempdir(), f"floppy_temp_{os.getpid()}.zip")

        try:
            self.root.after(0, lambda: self.lbl_status.configure(
                text="Step 1/2: Compressing source files into temporary archive..."))

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
                "floppy_format": raw_format_key,
                "images": {}
            }

            file_size = os.path.getsize(temp_zip)
            total_disks = (file_size + chunk_size - 1) // chunk_size

            def switch_to_determinate_mode(total, fmt):
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(0)
                self.lbl_status.configure(text=f"Step 2/2: Splitting and Writing {fmt} Images (Total: {total})...")

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

                    self.root.after(0, lambda d=disk_num, t=total_disks: self.lbl_status.configure(
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

                    self.root.after(0, lambda v=disk_num, t=total_disks: 
                        self.progress.set(v / t) if self.progress.cget("mode") == "determinate" else None)

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
            self.root.after(0, lambda: self.lbl_status.configure(text="❌ An error occurred"))
        finally:
            if os.path.exists(temp_zip):
                try: 
                    os.remove(temp_zip)
                except: 
                    pass
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: self.btn_start.configure(state="normal"))
            self.root.after(0, lambda: self.combo_capacity.configure(state="normal"))


# ============================================================================
# Main Entry Point
# ============================================================================
if __name__ == "__main__":
    setup_customtkinter_theme()
    root = ctk.CTk()
    app = FloppyCompressorApp(root)
    root.mainloop()
