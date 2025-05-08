import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import TYPE_MAP, NAME_TO_ID

def build_download_tab(app, frame):
    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # ── Block Type Selector ──
    ctk.CTkLabel(frame, text="Block Type:")\
        .grid(row=0, column=0, padx=padx, pady=(10, pady), sticky="w")
    types = list(TYPE_MAP.values())
    app.dl_type_var = ctk.StringVar(value=types[0])
    app.dl_type_cb = ctk.CTkComboBox(
        frame, values=types, variable=app.dl_type_var, width=120
    )
    app.dl_type_cb.grid(row=0, column=1, padx=padx, pady=(10, pady), sticky="w")

    # ── Output Directory ──
    ctk.CTkLabel(frame, text="Output Dir:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.dl_out = ctk.CTkEntry(frame)
    app.dl_out.grid(row=1, column=1, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: _browse_dl(app))\
        .grid(row=1, column=2, padx=5, pady=pady)

    # ── Download Button ──
    ctk.CTkButton(
        frame,
        text="Download",
        command=lambda: threading.Thread(target=_do_download, args=(app,), daemon=True).start()
    ).grid(row=2, column=0, columnspan=3, pady=(10, pady))

    # ── Progress & Log ──
    app.dl_progress = ctk.CTkProgressBar(frame)
    app.dl_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=padx, pady=(0,10))

    app.dl_log = ctk.CTkTextbox(frame, state="disabled")
    app.dl_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=padx, pady=pady)


def _browse_dl(app):
    path = filedialog.askdirectory()
    if path:
        app.dl_out.delete(0, "end")
        app.dl_out.insert(0, path)


def _do_download(app):
    # Guard: must be connected first
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return

    # Prepare UI
    app.dl_log.configure(state="normal")
    app.dl_log.delete("1.0", "end")
    app.dl_progress.set(0)

    try:
        # Map block type name → ID
        type_name = app.dl_type_var.get()
        tid = NAME_TO_ID.get(type_name)
        if tid is None:
            messagebox.showerror("Download Error", f"Unknown block type: {type_name}")
            return

        out_dir = app.dl_out.get().strip()
        if not out_dir:
            messagebox.showerror("Download Error", "Please select an output directory")
            return
        os.makedirs(out_dir, exist_ok=True)

        # Perform download
        with app._make_client() as client:
            blocks = list(client.list_blocks(tid))
            total = len(blocks)
            if total == 0:
                app.dl_log.insert("end", f"No {type_name} blocks found on PLC.\n")
            else:
                for idx, bn in enumerate(blocks, start=1):
                    _, _, lw = client.info_block(bn)
                    data = client.read_block(tid, bn, lw * 2)
                    filename = f"block_{type_name}_{bn}.bin"
                    filepath = os.path.join(out_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(data)
                    app.dl_progress.set(idx/total)
                    app.dl_log.insert("end", f"Saved {filename}\n")

        app.dl_log.insert("end", "Download complete.\n")

    except Exception as e:
        messagebox.showerror("Download Error", str(e))

    finally:
        app.dl_progress.set(0)
        app.dl_log.configure(state="disabled")
