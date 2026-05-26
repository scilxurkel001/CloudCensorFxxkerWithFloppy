import os
import glob
import threading
import tempfile
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pyfatfs.PyFatFS import PyFatFS

class FloppyExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CloudCensorFxxkerWithFloppy - Extractor")
        self.root.geometry("620x400")
        
        # Init tkinter variables
        self.source_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        
        self.create_widgets()

    def create_widgets(self):
        # --- Input Dir ---
        frame_src = ttk.LabelFrame(self.root, text=" 1. Select Directory Containing Floppy Images ", padding=10)
        frame_src.pack(fill="x", padx=15, pady=10)
        
        ttk.Entry(frame_src, textvariable=self.source_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_src, text="Browse...", command=self.browse_source).pack(side="right", padx=5)

        # --- Output Dir ---
        frame_out = ttk.LabelFrame(self.root, text=" 2. Select Target Directory for Extraction and Merging ", padding=10)
        frame_out.pack(fill="x", padx=15, pady=10)
        
        ttk.Entry(frame_out, textvariable=self.output_dir, width=50).pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(frame_out, text="Browse...", command=self.browse_output).pack(side="right", padx=5)

        # --- Progressbar ---
        frame_progress = ttk.Frame(self.root, padding=10)
        frame_progress.pack(fill="x", padx=15, pady=10)
        
        self.lbl_status = ttk.Label(frame_progress, text="Ready", padding=10)
        self.lbl_status.pack(anchor="w", pady=2)
        
        self.progress = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=5)

        # --- Layout: Action Buttons ---
        self.btn_start = ttk.Button(self.root, text="Start Automatic Extraction and Merging", command=self.start_extraction_thread)
        self.btn_start.pack(pady=15)

    def browse_source(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(os.path.normpath(directory))

    def browse_output(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir.set(os.path.normpath(directory))

    def start_extraction_thread(self):
        if not self.source_dir.get() or not self.output_dir.get():
            messagebox.showwarning("Warning", "Please select both source and target directories!")
            return
        
        self.btn_start.config(state="disabled")
        threading.Thread(target=self.extract_process, daemon=True).start()

    def extract_process(self):
        src = self.source_dir.get()
        out = self.output_dir.get()
        
        search_pattern = os.path.join(src, "flp*.img")
        img_files = sorted(glob.glob(search_pattern))
        
        total_files = len(img_files)
        if total_files == 0:
            self.root.after(0, lambda: messagebox.showinfo("Info", "No files matching flp*.img format found!"))
            self.root.after(0, lambda: self.btn_start.config(state="normal"))
            return

        self.root.after(0, lambda: self.progress.config(maximum=total_files + 1, value=0))
        
        os.makedirs(out, exist_ok=True)

        # Use a temporary ZIP file to store extracted chunks before final extraction
        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(temp_zip_fd)

        try:
            # 1. Walk through each floppy image, extract the .DAT file (or first file if no .DAT), and write to the temporary ZIP
            with open(temp_zip_path, 'wb') as zip_out:
                for index, img_path in enumerate(img_files):
                    file_name = os.path.basename(img_path)
                    self.root.after(0, lambda f=file_name, i=index: self.lbl_status.config(text=f"Reading split part ({i+1}/{total_files}): {f}"))
                    fat = None
                    try:
                        fat = PyFatFS(img_path, read_only=True)
                            
                        extracted_chunk = False
                        # Convert all paths to use forward slashes for consistency
                        files_list = list(fat.walk.files("/"))
                        
                        for virt_path in files_list:
                            virt_path = virt_path.replace("\\", "/")
                            if not virt_path.startswith("/"):
                                virt_path = "/" + virt_path
                                
                            filename = os.path.basename(virt_path)
                            if filename.upper().endswith(".DAT"):
                                with fat.openbin(virt_path, 'rb') as src_f:
                                    zip_out.write(src_f.read())
                                extracted_chunk = True
                                break
                        if not extracted_chunk and files_list:
                            virt_path = files_list[0].replace("\\", "/")
                            if not virt_path.startswith("/"):
                                virt_path = "/" + virt_path
                            with fat.openbin(virt_path, 'rb') as src_f:
                                zip_out.write(src_f.read())
                            extracted_chunk = True
                                
                    except Exception as e:
                        raise Exception(f"Failed to process {file_name}: {e}") from e
                    finally:
                        if fat is not None:
                            try:
                                fat.close()
                            except Exception:
                                pass
                    
                    self.root.after(0, lambda i=index+1: self.progress.config(value=i))

            self.root.after(0, lambda: self.lbl_status.config(text="Split parts merged successfully, extracting final ZIP archive..."))
            
            # 2. Unzip the merged ZIP file to the output directory
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(out)
                
            self.root.after(0, lambda: self.progress.config(value=total_files + 1))
            self.root.after(0, lambda: self.lbl_status.config(text="✅ Extraction and merging successful!"))
            self.root.after(0, lambda: self.btn_start.config(state="normal"))
            self.root.after(0, lambda: messagebox.showinfo("Success", f"All floppy chunks have been successfully merged and extracted to:\n{out}"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed:\n{str(e)}"))
            self.root.after(0, lambda: self.lbl_status.config(text="❌ An error occurred"))
        finally:
            # 3. Clean up the temporary ZIP file
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            self.root.after(0, lambda: self.btn_start.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    app = FloppyExtractorApp(root)
    root.mainloop()