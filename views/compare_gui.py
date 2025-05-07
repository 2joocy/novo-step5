# SPDX-License-Identifier: MIT
# Copyright © 2025 Novo Nordisk A/S

import threading
import re
import os
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP

def build_compare_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    frame.grid_rowconfigure(3, weight=1)
    padx, pady = 10, 5

    # Regex matcher for block names
    ctk.CTkLabel(frame, text="Block Type Regex:")\
        .grid(row=0, column=0, padx=padx, pady=(10,pady), sticky="w")
    app.cr_pat = ctk.CTkEntry(frame, placeholder_text="e.g. FB|DB", width=200)
    app.cr_pat.grid(row=0, column=1, padx=padx, pady=(10,pady), sticky="w")

    # Baseline directory
    ctk.CTkLabel(frame, text="Baseline Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.cr_base = ctk.CTkEntry(frame)
    app.cr_base.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: _browse_cr(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # Compare button
    ctk.CTkButton(
        frame,
        text="Compare",
        command=lambda: threading.Thread(target=_do_compare, args=(app,), daemon=True).start()
    ).grid(row=2, column=0, columnspan=3, pady=(10,pady))

    app.cr_log = ctk.CTkTextbox(frame)
    app.cr_log.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=padx, pady=10)


def _browse_cr(app):
    d = filedialog.askdirectory()
    if d:
        app.cr_base.delete(0, "end")
        app.cr_base.insert(0, d)


def _do_compare(app):
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    app.cr_log.delete("1.0", "end")

    try:
        pattern = app.cr_pat.get().strip()
        if not pattern:
            messagebox.showerror("Compare Error", "Enter a block type regex")
            return
        try:
            pat = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            messagebox.showerror("Compare Error", f"Invalid regex: {e}")
            return

        base_dir = app.cr_base.get().strip()
        if not os.path.isdir(base_dir):
            messagebox.showerror("Compare Error", "Select a valid baseline directory")
            return

        with app._make_client() as client:
            for tid, name in TYPE_MAP.items():
                if not pat.search(name):
                    continue

                blocks = list(client.list_blocks(tid))
                if not blocks:
                    app.cr_log.insert("end", f"No {name} blocks on PLC\n")
                    continue

                for bn in blocks:
                    fn = f"block_{name}_{bn}.bin"
                    fp = os.path.join(base_dir, fn)
                    if not os.path.isfile(fp):
                        app.cr_log.insert("end", f"{name}#{bn} missing baseline\n")
                        continue

                    diffs = list(client.compare_block(tid, bn, fp))
                    if diffs:
                        app.cr_log.insert("end", f"=== DIFF {name}#{bn} ===\n")
                        app.cr_log.insert("end", "\n".join(diffs) + "\n")
                    else:
                        app.cr_log.insert("end", f"{name}#{bn} OK\n")

    except Exception as e:
        messagebox.showerror("Compare Error", str(e))
