# views/upload_gui.py

import os
import glob
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP, NAME_TO_ID

def build_upload_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # ── Block Type Selector ──
    ctk.CTkLabel(frame, text="Block Type:")\
        .grid(row=0, column=0, padx=padx, pady=(10, pady), sticky="w")
    types = list(TYPE_MAP.values())
    app.ul_type_var = ctk.StringVar(value=types[0])
    app.ul_type_cb = ctk.CTkComboBox(
        frame, values=types, variable=app.ul_type_var, width=120
    )
    app.ul_type_cb.grid(row=0, column=1, padx=padx, pady=(10, pady), sticky="w")

    # ── Input Directory ──
    ctk.CTkLabel(frame, text="Input Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.ul_in = ctk.CTkEntry(frame)
    app.ul_in.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: _browse_ul(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # ── Upload Button ──
    ctk.CTkButton(
        frame,
        text="Upload",
        command=lambda: threading.Thread(target=_do_upload, args=(app,), daemon=True).start()
    ).grid(row=2, column=0, columnspan=3, pady=(10, pady))

    # ── Progress & Log ──
    app.ul_progress = ctk.CTkProgressBar(frame)
    app.ul_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=padx, pady=(0,10))
    app.ul_log = ctk.CTkTextbox(frame, state="disabled")
    app.ul_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=padx, pady=pady)


def _browse_ul(app):
    path = filedialog.askdirectory()
    if path:
        app.ul_in.delete(0, "end")
        app.ul_in.insert(0, path)


def _do_upload(app):
    # Guard: must be connected first
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    # Prepare UI
    app.ul_log.configure(state="normal")
    app.ul_log.delete("1.0", "end")
    app.ul_progress.set(0)

    try:
        # Map block type name → ID
        type_name = app.ul_type_var.get()
        tid = NAME_TO_ID.get(type_name)
        if tid is None:
            messagebox.showerror("Upload Error", f"Unknown block type: {type_name}")
            return

        in_dir = app.ul_in.get().strip()
        if not os.path.isdir(in_dir):
            messagebox.showerror("Upload Error", f"Directory not found: {in_dir}")
            return

        # Find matching files
        pattern = os.path.join(in_dir, f"block_{type_name}_*.bin")
        files = sorted(glob.glob(pattern))
        total = len(files)
        if total == 0:
            app.ul_log.insert("end", f"No files matching {pattern}\n")
        else:
            with app._make_client() as client:
                for idx, filepath in enumerate(files, start=1):
                    filename = os.path.basename(filepath)
                    # parse block number
                    try:
                        num_str = filename.rsplit("_", 1)[1].split(".")[0]
                        bn = int(num_str, 0)
                    except Exception:
                        app.ul_log.insert("end", f"Skipping invalid filename: {filename}\n")
                        continue

                    data = open(filepath, "rb").read()
                    client.write_block(tid, bn, data)
                    app.ul_progress.set(idx/total)
                    app.ul_log.insert("end", f"Uploaded {filename}\n")

        app.ul_log.insert("end", "Upload complete.\n")

    except Exception as e:
        messagebox.showerror("Upload Error", str(e))

    finally:
        app.ul_progress.set(0)
        app.ul_log.configure(state="disabled")
