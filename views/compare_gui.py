# views/compare_gui.py

import threading
import re
import os
import difflib
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP, ExtendedAS511Client

def build_compare_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # ── Block Type Regex ──
    ctk.CTkLabel(frame, text="Block Type Regex:")\
        .grid(row=0, column=0, padx=padx, pady=(10, pady), sticky="w")
    app.cr_pat = ctk.CTkEntry(frame, placeholder_text="e.g. FB|DB")
    app.cr_pat.grid(row=0, column=1, padx=padx, pady=(10, pady), sticky="ew")

    # ── Baseline Directory ──
    ctk.CTkLabel(frame, text="Baseline Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.cr_base = ctk.CTkEntry(frame)
    app.cr_base.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: browse_cr(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # ── Compare Button ──
    app.cr_btn = ctk.CTkButton(
        frame,
        text="Compare",
        command=lambda: threading.Thread(target=_do_compare, args=(app,), daemon=True).start()
    )
    app.cr_btn.grid(row=2, column=0, columnspan=3, pady=(10, pady))

    # ── Progress Bar ──
    app.cr_progress = ctk.CTkProgressBar(frame)
    app.cr_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=padx, pady=(0,10))

    # ── Log ──
    app.cr_log = ctk.CTkTextbox(frame, state="disabled")
    app.cr_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=padx, pady=pady)


def browse_cr(app):
    path = filedialog.askdirectory()
    if path:
        app.cr_base.delete(0, "end")
        app.cr_base.insert(0, path)


def _do_compare(app):
    # Guard: must be connected
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    # Prepare UI
    app.cr_btn.configure(state="disabled")
    app.cr_log.configure(state="normal")
    app.cr_log.delete("1.0", "end")
    app.cr_progress.set(0)

    # Validate regex
    pat_text = app.cr_pat.get().strip()
    if not pat_text:
        messagebox.showerror("Compare Error", "Enter a block type regex")
        app.cr_btn.configure(state="normal")
        app.cr_log.configure(state="disabled")
        return
    try:
        pat = re.compile(pat_text, re.IGNORECASE)
    except re.error as e:
        messagebox.showerror("Compare Error", f"Invalid regex: {e}")
        app.cr_btn.configure(state="normal")
        app.cr_log.configure(state="disabled")
        return

    # Validate baseline directory
    base_dir = app.cr_base.get().strip()
    if not os.path.isdir(base_dir):
        messagebox.showerror("Compare Error", "Select a valid baseline directory")
        app.cr_btn.configure(state="normal")
        app.cr_log.configure(state="disabled")
        return

    # Compute total blocks to compare
    with app._make_client() as client:
        total = sum(
            len(list(client.list_blocks(tid)))
            for tid, name in TYPE_MAP.items()
            if pat.search(name)
        )

    if total == 0:
        app.cr_log.insert("end", "No matching block types found on PLC.\n")
    else:
        done = 0
        with app._make_client() as client:
            for tid, name in TYPE_MAP.items():
                if not pat.search(name):
                    continue
                blocks = list(client.list_blocks(tid))
                if not blocks:
                    app.cr_log.insert("end", f"No {name} blocks on PLC.\n")
                    continue
                for bn in blocks:
                    done += 1
                    app.cr_progress.set(done / total)

                    # Baseline file path
                    fn = f"block_{name}_{bn}.bin"
                    fp = os.path.join(base_dir, fn)
                    if not os.path.isfile(fp):
                        app.cr_log.insert("end", f"{name}#{bn} missing baseline\n")
                        continue

                    # Read and diff
                    _, _, lw = client.info_block(bn)
                    remote = client.read_block(tid, bn, lw * 2)
                    local = open(fp, "rb").read()
                    a = [f"{b:02X}" for b in local]
                    b = [f"{b:02X}" for b in remote]
                    diffs = list(difflib.unified_diff(
                        a, b,
                        fromfile="baseline", tofile="online",
                        lineterm=""
                    ))
                    if diffs:
                        app.cr_log.insert("end", f"=== DIFF {name}#{bn} ===\n")
                        app.cr_log.insert("end", "\n".join(diffs) + "\n")
                    else:
                        app.cr_log.insert("end", f"{name}#{bn} OK\n")

    # Finalize UI
    app.cr_progress.set(0)
    app.cr_log.configure(state="disabled")
    app.cr_btn.configure(state="normal")
