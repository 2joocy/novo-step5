import threading
import re
import customtkinter as ctk
from tkinter import messagebox
from tkinter import ttk


def build_upload_tab(app, container):
    """
    Builds the Upload tab UI with a Treeview for multiple block writes.

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
    ctk.CTkLabel(ctrl, text="Data (comma separated bytes):").grid(row=0, column=2, padx=(10,5))
    data_entry = ctk.CTkEntry(ctrl)
    data_entry.grid(row=0, column=3, sticky="ew", padx=(0,5))
    write_btn = ctk.CTkButton(ctrl, text="Write", width=80)
    write_btn.grid(row=0, column=4)
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

    # Treeview setup: columns for Block, Data, Status
    cols = ("Block", "Data", "Status")
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

    def on_write():
        if not app.connected:
            messagebox.showwarning("Not connected", "Please connect to a device first.")
            return
        blk_id = block_entry.get().strip()
        raw = data_entry.get().strip()
        # parse data
        try:
            values = [int(x) for x in re.split(r"\s*,\s*", raw) if x]
        except ValueError:
            summary_label.configure(text="Invalid data format; use comma-separated decimals.")
            return
        summary_label.configure(text="Writing...")

        def task():
            try:
                res = app.client.write_block(blk_id, bytes(values))
                status = "OK" if res.get('success') else "FAIL"
                # update summary
                summary_label.after(0, lambda: summary_label.configure(text=f"Block {res['block']} write: {status}"))
                # insert row
                data_str = ','.join(str(v) for v in values)
                tree.after(0, lambda: tree.insert(
                    "", "end", values=(res['block'], data_str, status)
                ))
            except Exception as e:
                summary_label.after(0, lambda: summary_label.configure(text=str(e)))

        threading.Thread(target=task, daemon=True).start()

    write_btn.configure(command=on_write)

    return {
        'block_entry': block_entry,
        'data_entry': data_entry,
        'summary_label': summary_label,
        'tree': tree
    }
