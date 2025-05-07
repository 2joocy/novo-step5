# SPDX-License-Identifier: MIT
# Copyright © 2025 Novo Nordisk A/S

import os
import glob
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP, NAME_TO_ID

def build_upload_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # Block-type selector
    ctk.CTkLabel(frame, text="Block Type:")\
        .grid(row=0, column=0, padx=padx, pady=(10,pady), sticky="w")
    types = list(TYPE_MAP.values())
    app.ul_type_var = ctk.StringVar(value=types[0])
    app.ul_type_cb = ctk.CTkComboBox(
        frame, values=types, variable=app.ul_type_var, width=120
    )
    app.ul_type_cb.grid(row=0, column=1, padx=padx, pady=(10,pady), sticky="w")

    # Input directory
    ctk.CTkLabel(frame, text="Input Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.ul_in = ctk.CTkEntry(frame)
    app.ul_in.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: _browse_ul(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # Upload button
    ctk.CTkButton(
        frame,
        text="Upload",
        command=lambda: threading.Thread(target=_do_upload, args=(app,), daemon=True).start()
    ).grid(row=2, column=0, columnspan=3, pady=(10,pady))

    # Progress bar and log
    app.ul_progress = ctk.CTkProgressBar(frame)
    app.ul_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=padx, pady=(0,10))
    app.ul_log = ctk.CTkTextbox(frame)
    app.ul_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=padx, pady=10)


def _browse_ul(app):
    d = filedialog.askdirectory()
    if d:
        app.ul_in.delete(0, "end")
        app.ul_in.insert(0, d)


def _do_upload(app):
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    app.ul_log.delete("1.0", "end")
    app.ul_progress.set(0)

    try:
        # map name → ID
        type_name = app.ul_type_var.get()
        tid = NAME_TO_ID[type_name]

        in_dir = app.ul_in.get().strip()
        if not os.path.isdir(in_dir):
            messagebox.showerror("Upload Error", f"Directory not found: {in_dir}")
            return

        # find files matching block_<TypeName>_<BlockNum>.bin
        pattern = os.path.join(in_dir, f"block_{type_name}_*.bin")
        files = glob.glob(pattern)
        total = len(files)
        written = []

        with app._make_client() as client:
            for i, fn in enumerate(files, start=1):
                # parse block number from filename
                base = os.path.basename(fn)
                num_str = base.rsplit("_", 1)[-1].split(".")[0]
                bn = int(num_str, 0)

                data = open(fn, "rb").read()
                client.write_block(tid, bn, data)
                written.append(bn)

                app.ul_progress.set(i/total)

        app.ul_log.insert("end", f"Uploaded {type_name} blocks: {written}\n")

    except Exception as e:
        messagebox.showerror("Upload Error", str(e))
    finally:
        app.ul_progress.set(0)
