# SPDX-License-Identifier: MIT
# Copyright © 2025 Novo Nordisk A/S

import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP, NAME_TO_ID

def build_download_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # Block-type selector
    ctk.CTkLabel(frame, text="Block Type:")\
        .grid(row=0, column=0, padx=padx, pady=(10, pady), sticky="w")
    types = list(TYPE_MAP.values())
    app.dl_type_var = ctk.StringVar(value=types[0])
    app.dl_type_cb = ctk.CTkComboBox(
        frame, values=types, variable=app.dl_type_var, width=120
    )
    app.dl_type_cb.grid(row=0, column=1, padx=padx, pady=(10, pady), sticky="w")

    # Output directory
    ctk.CTkLabel(frame, text="Output Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.dl_out = ctk.CTkEntry(frame)
    app.dl_out.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: _browse_dl(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # Download button
    ctk.CTkButton(
        frame,
        text="Download",
        command=lambda: threading.Thread(target=_do_download, args=(app,), daemon=True).start()
    ).grid(row=2, column=0, columnspan=3, pady=(10, pady))

    # Progress bar and log
    app.dl_progress = ctk.CTkProgressBar(frame)
    app.dl_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=padx, pady=(0,10))
    app.dl_log = ctk.CTkTextbox(frame)
    app.dl_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=padx, pady=10)


def _browse_dl(app):
    d = filedialog.askdirectory()
    if d:
        app.dl_out.delete(0, "end")
        app.dl_out.insert(0, d)


def _do_download(app):
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    app.dl_log.delete("1.0", "end")
    app.dl_progress.set(0)

    try:
        # map name → ID
        type_name = app.dl_type_var.get()
        tid = NAME_TO_ID[type_name]

        out_dir = app.dl_out.get().strip()
        if not out_dir:
            messagebox.showerror("Download Error", "Please select an output directory")
            return
        os.makedirs(out_dir, exist_ok=True)

        with app._make_client() as client:
            blocks = list(client.list_blocks(tid))
            total = len(blocks)
            for i, bn in enumerate(blocks, start=1):
                _, _, lw = client.info_block(bn)
                data = client.read_block(tid, bn, lw*2)

                fn = f"block_{type_name}_{bn}.bin"
                path = os.path.join(out_dir, fn)
                with open(path, "wb") as f:
                    f.write(data)

                app.dl_progress.set(i/total)

            app.dl_log.insert("end", f"Downloaded {type_name} blocks: {blocks}\n")

    except Exception as e:
        messagebox.showerror("Download Error", str(e))
    finally:
        app.dl_progress.set(0)
