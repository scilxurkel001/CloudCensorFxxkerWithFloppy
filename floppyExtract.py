import logging
import os
import glob
import threading
import hashlib
import json
import tempfile
import zipfile
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pyfatfs.PyFatFS import PyFatFS

# Setting up CustomTkinter appearance and theme
ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")  

def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()

class FloppyExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Extractor - v1.30a - Based on CustomTkinter")
        self.root.geometry("650x550")  
        self.source_dir = ctk.StringVar()
        self.output_dir = ctk.StringVar()
        self.progress_max = 1 
        self.create_widgets()

    def create_widgets(self):
        # 1. Input Directory Selection
        frame_src = ctk.CTkFrame(self.root)
        frame_src.pack(fill="x", padx=20, pady=(20, 10))
        
        lbl_src = ctk.CTkLabel(frame_src, text="1. Select Directory Containing Floppy Images", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_src.pack(anchor="w", padx=15, pady=(15, 5))
        
        subframe_src = ctk.CTkFrame(frame_src, fg_color="transparent")
        subframe_src.pack(fill="x", padx=15, pady=(0, 15))
        
        self.entry_src = ctk.CTkEntry(subframe_src, textvariable=self.source_dir, placeholder_text="Select source folder...")
        self.entry_src.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        btn_src = ctk.CTkButton(subframe_src, text="Browse...", width=100, command=self.browse_source)
        btn_src.pack(side="right")

        # 2. Output Directory Selection
        frame_out = ctk.CTkFrame(self.root)
        frame_out.pack(fill="x", padx=20, pady=10)
        
        lbl_out = ctk.CTkLabel(frame_out, text="2. Select Target Directory for Extraction and Merging", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_out.pack(anchor="w", padx=15, pady=(15, 5))
        
        subframe_out = ctk.CTkFrame(frame_out, fg_color="transparent")
        subframe_out.pack(fill="x", padx=15, pady=(0, 15))
        
        self.entry_out = ctk.CTkEntry(subframe_out, textvariable=self.output_dir, placeholder_text="Select output folder...")
        self.entry_out.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        btn_out = ctk.CTkButton(subframe_out, text="Browse...", width=100, command=self.browse_output)
        btn_out.pack(side="right")

        # 3. Progress and Status
        frame_progress = ctk.CTkFrame(self.root)
        frame_progress.pack(fill="x", padx=20, pady=10)
        
        self.lbl_status = ctk.CTkLabel(frame_progress, text="Status: Ready", anchor="w")
        self.lbl_status.pack(fill="x", padx=15, pady=(15, 10))
        
        self.progress = ctk.CTkProgressBar(frame_progress)
        self.progress.pack(fill="x", padx=15, pady=(0, 15))
        self.progress.set(0)

        # 4. Start Button
        self.btn_start = ctk.CTkButton(
            self.root, 
            text="Start Automatic Extraction and Merging", 
            height=40, 
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_extraction_thread
        )
        self.btn_start.pack(pady=20)

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
        self.btn_start.configure(state="disabled")
        threading.Thread(target=self.extract_process, daemon=True).start()

    def extract_process(self):
        src = self.source_dir.get()
        out = self.output_dir.get()
        
        search_pattern = os.path.join(src, "[Ff][Ll][Pp]*.[Ii][Mm][Gg]")
        img_files = sorted(glob.glob(search_pattern))
        
        total_files = len(img_files)
        if total_files == 0:
            self.root.after(0, lambda: messagebox.showinfo("Info", "No files matching FLP*.IMG format found!"))
            self.root.after(0, lambda: self.btn_start.configure(state="normal"))
            return
        self.progress_max = total_files + 1
        self.root.after(0, lambda: self.progress.set(0))
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
                    self.root.after(0, lambda f=file_name, i=index: self.lbl_status.configure(text=f"Reading & Verifying ({i+1}/{total_files}): {f}"))
                    
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
                    self.root.after(0, lambda i=index+1: self.progress.set(i / self.progress_max))

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
                        event.set()
                    
                self.root.after(0, prompt)
                event.wait()
                
                if not result[0]:
                    self.root.after(0, lambda: self.lbl_status.configure(text="❌ Aborted by user."))
                    raise Exception("Aborted by user due to verification failure.")
                    
            self.root.after(0, lambda: self.lbl_status.configure(text="Split parts merged successfully, extracting final ZIP archive..."))
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(out)
            self.root.after(0, lambda: self.progress.set(1.0))
            self.root.after(0, lambda: self.lbl_status.configure(text="✅ Extraction and merging successful!"))
            self.root.after(0, lambda: messagebox.showinfo("Success", f"All floppy chunks have been successfully merged and extracted to:\n{out}"))

        except Exception as e:
            if "Aborted by user" not in str(e):
                self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed:\n{str(e)}"))
            self.root.after(0, lambda: self.lbl_status.configure(text="❌ An error occurred"))
        finally:
            if os.path.exists(temp_zip_path):
                try: os.remove(temp_zip_path)
                except: pass
            self.root.after(0, lambda: self.btn_start.configure(state="normal"))

if __name__ == "__main__":
    root = ctk.CTk()
    app = FloppyExtractorApp(root)
    root.mainloop()
