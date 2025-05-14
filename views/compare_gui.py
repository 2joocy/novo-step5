import threading
import re
import customtkinter as ctk
from tkinter import messagebox
from tkinter import ttk


def build_compare_tab(app, container):
    """
    Builds the Compare tab UI with a Treeview for multiple block type comparisons.

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
    ctk.CTkLabel(ctrl, text="Expected Type ID:").grid(row=0, column=2, padx=(10,5))
    type_entry = ctk.CTkEntry(ctrl, width=80)
    type_entry.grid(row=0, column=3, sticky="ew", padx=(0,5))
    compare_btn = ctk.CTkButton(ctrl, text="Compare", width=100)
    compare_btn.grid(row=0, column=4)
    ctrl.grid_columnconfigure(1, weight=1)
    ctrl.grid_columnconfigure(3, weight=1)

    # Summary label
    summary_label = ctk.CTkLabel(container, text="", anchor="w")
    summary_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0,5))

    # Treeview frame for results
    tree_frame = ctk.CTkFrame(container)
    tree_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
    container.grid_rowconfigure(2, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # Treeview setup: columns for Block, Expected, Actual, Match
    cols = ("Block", "Expected", "Actual", "Match")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, anchor="center")

    # Scrollbar
    vscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vscroll.set)

    # Layout
    tree.grid(row=0, column=0, sticky="nsew")
    vscroll.grid(row=0, column=1, sticky="ns")
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    def on_compare():
        if not app.connected:
            messagebox.showwarning("Not connected", "Please connect to a device first.")
            return
        blk_id = block_entry.get().strip()
        exp_text = type_entry.get().strip()
        if not exp_text.isdigit():
            summary_label.configure(text="Expected Type ID must be an integer.")
            return
        exp_type = int(exp_text)
        summary_label.configure(text="Comparing...")

        def task():
            try:
                actual_ok = app.client.compare_block(blk_id, exp_type)
                # After calling compare, fetch actual type via info_block for display
                info = app.client.info_block(blk_id)
                actual_type = info.get('type_id')
                match = "Yes" if actual_ok else "No"
                # Update summary
                summary = f"Block {blk_id}: expected {exp_type}, actual {actual_type}, match: {match}"
                summary_label.after(0, lambda: summary_label.configure(text=summary))
                # Insert into tree
                tree.after(0, lambda: tree.insert(
                    "", "end", values=(blk_id, exp_type, actual_type, match)
                ))
            except Exception as e:
                summary_label.after(0, lambda: summary_label.configure(text=str(e)))

        threading.Thread(target=task, daemon=True).start()

    compare_btn.configure(command=on_compare)

    return {
        'block_entry': block_entry,
        'type_entry': type_entry,
        'summary_label': summary_label,
        'tree': tree
    }
