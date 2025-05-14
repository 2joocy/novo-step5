import threading
import re
import customtkinter as ctk
from tkinter import messagebox
from tkinter import ttk


def build_download_tab(app, container):
    """
    Builds the Download tab UI with a Treeview for multiple block reads.

    Parameters:
    - app: reference to the main PLCToolApp instance
    - container: the CTkFrame for this tab
    """
    # Controls frame
    ctrl = ctk.CTkFrame(container)
    ctrl.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
    ctk.CTkLabel(ctrl, text="Block ID (e.g. DB65 or DB65.1):").grid(row=0, column=0, padx=(0,5))
    block_entry = ctk.CTkEntry(ctrl)
    block_entry.grid(row=0, column=1, sticky="ew", padx=(0,5))
    read_btn = ctk.CTkButton(ctrl, text="Read", width=80)
    read_btn.grid(row=0, column=2)
    ctrl.grid_columnconfigure(1, weight=1)

    # Summary label
    summary_label = ctk.CTkLabel(container, text="", anchor="w")
    summary_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0,5))

    # Treeview frame for results
    tree_frame = ctk.CTkFrame(container)
    tree_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
    container.grid_rowconfigure(2, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # Treeview setup: columns for Block, Index, Decimal, Hex
    cols = ("Block", "Index", "Decimal", "Hex")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=80)

    # Scrollbar
    vscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vscroll.set)

    # Layout
    tree.grid(row=0, column=0, sticky="nsew")
    vscroll.grid(row=0, column=1, sticky="ns")
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    def on_read():
        if not app.connected:
            messagebox.showwarning("Not connected", "Please connect to a device first.")
            return
        blk_id = block_entry.get().strip()
        summary_label.configure(text="Reading...")

        def task():
            try:
                res = app.client.read_block(blk_id)
                # Update summary
                summary = f"Block: {res['block']}  Length: {len(res['values'])} bytes"
                summary_label.after(0, lambda: summary_label.configure(text=summary))
                # Insert rows into treeview
                for idx, val in enumerate(res['values']):
                    tree.after(0, lambda b=res['block'], i=idx, v=val: tree.insert(
                        "", "end", values=(b, i, v, f"0x{v:02X}")))
            except Exception as e:
                summary_label.after(0, lambda: summary_label.configure(text=str(e)))

        threading.Thread(target=task, daemon=True).start()

    read_btn.configure(command=on_read)

    return {
        'block_entry': block_entry,
        'summary_label': summary_label,
        'tree': tree
    }
