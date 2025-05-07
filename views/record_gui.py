import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import csv
import time
import customtkinter as ctk
from as511_core import TYPE_MAP, NAME_TO_ID

DEFAULT_INTERVAL = 1.0  # seconds

def build_record_gui_tab(app, frame):
    # Apply a dark style to the Treeview so it matches the CTk theme
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Dark.Treeview",
        background="#2b2b2b",
        fieldbackground="#2b2b2b",
        foreground="#ffffff",
        rowheight=24
    )
    style.map(
        "Dark.Treeview",
        background=[("selected", "#1f6feb")],
        foreground=[("selected", "#ffffff")]
    )
    style.configure("Dark.Treeview.Heading", background="#333333", foreground="#ffffff")

    frame.grid_columnconfigure(1, weight=1)
    padx, pady = 10, 5

    # ── Block Type & Block # & Bit # inputs ──
    ctk.CTkLabel(frame, text="Block Type:")\
        .grid(row=0, column=0, padx=padx, pady=(10, pady), sticky="w")
    types = list(TYPE_MAP.values())
    app.rec_type_var = ctk.StringVar(value=types[0])
    app.rec_type_cb = ctk.CTkComboBox(
        frame, values=types, variable=app.rec_type_var, width=120
    )
    app.rec_type_cb.grid(row=0, column=1, padx=padx, pady=(10, pady), sticky="w")

    ctk.CTkLabel(frame, text="Block #:")\
        .grid(row=1, column=0, padx=padx, pady=pady, sticky="w")
    app.rec_num = ctk.CTkEntry(frame, width=80, placeholder_text="e.g. 5")
    app.rec_num.grid(row=1, column=1, padx=padx, pady=pady, sticky="w")

    ctk.CTkLabel(frame, text="Bit #:")\
        .grid(row=0, column=2, padx=padx, pady=(10, pady), sticky="w")
    app.rec_bit = ctk.CTkEntry(frame, width=50, placeholder_text="e.g. 2")
    app.rec_bit.grid(row=0, column=3, padx=padx, pady=(10, pady), sticky="w")

    # Add / Remove buttons
    ctk.CTkButton(
        frame, text="Add",
        fg_color="#5cb85c", hover_color="#4cae4c",
        command=lambda: add_record(app)
    ).grid(row=0, column=4, rowspan=2, padx=5, pady=pady)

    ctk.CTkButton(
        frame, text="Remove",
        fg_color="#d9534f", hover_color="#c9302c",
        command=lambda: remove_record(app)
    ).grid(row=0, column=5, rowspan=2, padx=5, pady=pady)

    # ── Table for live values ──
    container = tk.Frame(frame, bg="#2b2b2b")
    container.grid(row=2, column=0, columnspan=6, sticky="nsew", padx=padx, pady=pady)
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    cols = ("Timestamp", "Block", "Value")
    app.rec_table = ttk.Treeview(
        container,
        columns=cols,
        show="headings",
        style="Dark.Treeview",
        height=10
    )
    for col in cols:
        app.rec_table.heading(col, text=col)
        app.rec_table.column(col, anchor="center")

    vsb = ttk.Scrollbar(container, orient="vertical", command=app.rec_table.yview)
    app.rec_table.configure(yscrollcommand=vsb.set)
    app.rec_table.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    # ── Interval & CSV controls ──
    ctk.CTkLabel(frame, text="Interval (s):")\
        .grid(row=3, column=0, padx=padx, pady=pady, sticky="w")
    app.rec_interval = ctk.CTkEntry(frame, width=80)
    app.rec_interval.insert(0, str(DEFAULT_INTERVAL))
    app.rec_interval.grid(row=3, column=1, padx=padx, pady=pady, sticky="w")

    ctk.CTkLabel(frame, text="Output CSV:")\
        .grid(row=3, column=2, padx=padx, pady=pady, sticky="w")
    app.rec_out = ctk.CTkEntry(frame, placeholder_text="Select path", width=300)
    app.rec_out.grid(row=3, column=3, padx=padx, pady=pady, sticky="ew")
    ctk.CTkButton(frame, text="Browse…", command=lambda: browse_rec(app))\
        .grid(row=3, column=4, padx=5, pady=pady)

    # ── Record toggle ──
    app.rec_btn = ctk.CTkButton(
        frame, text="Start Recording",
        fg_color="#0275d8", hover_color="#025aa5",
        command=lambda: toggle_record(app)
    )
    app.rec_btn.grid(row=4, column=0, columnspan=6, pady=(10, pady))

    # launch monitor thread
    threading.Thread(target=_monitor_blocks, args=(app,), daemon=True).start()


def add_record(app):
    try:
        name = app.rec_type_var.get()
        t = NAME_TO_ID[name]
        b = int(app.rec_num.get(), 0)
        bit_text = app.rec_bit.get().strip()
        bit = int(bit_text, 0) if bit_text else None
        key = f"{name},{b}" + (f".{bit}" if bit is not None else "")
        existing = [app.rec_table.item(i, "values")[1] for i in app.rec_table.get_children()]
        if key in existing:
            return
        app.rec_table.insert("", "end", values=("", key, ""))
        app.rec_num.delete(0, "end")
        app.rec_bit.delete(0, "end")
    except Exception:
        messagebox.showerror("Error", "Invalid block or bit number")


def remove_record(app):
    sel = app.rec_table.selection()
    if not sel:
        messagebox.showerror("Error", "No entry selected to remove")
        return
    for iid in sel:
        app.rec_table.delete(iid)


def browse_rec(app):
    path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
    if path:
        app.rec_out.delete(0, "end")
        app.rec_out.insert(0, path)


def toggle_record(app):
    if not app.connected:
        messagebox.showerror("Error", "Not connected to PLC")
        return
    app.recording = not getattr(app, "recording", False)
    text = "Stop Recording" if app.recording else "Start Recording"
    app.rec_btn.configure(text=text)


def _monitor_blocks(app):
    client = app._make_client()
    client.__enter__()
    csv_file = None
    csv_writer = None
    first = True

    try:
        while True:
            if not app.connected:
                time.sleep(0.5)
                continue

            try:
                interval = float(app.rec_interval.get())
            except ValueError:
                interval = DEFAULT_INTERVAL

            ts = time.strftime("%Y-%m-%d %H:%M:%S")

            if app.recording and first:
                path = app.rec_out.get().strip()
                try:
                    csv_file = open(path, "w", newline="")
                    csv_writer = csv.writer(csv_file)
                    csv_writer.writerow(["timestamp", "block", "value"])
                except Exception as e:
                    messagebox.showerror("Record Error", str(e))
                    app.recording = False
                first = False

            if not app.recording and not first:
                if csv_file:
                    csv_file.close()
                csv_file = None
                csv_writer = None
                first = True

            for iid in app.rec_table.get_children():
                _, key, _ = app.rec_table.item(iid, "values")
                try:
                    if "." in key:
                        base, bitpart = key.split(".", 1)
                    else:
                        base, bitpart = key, None
                    name, num = base.split(",", 1)
                    t = NAME_TO_ID[name]
                    b = int(num, 0)
                    _, _, lw = client.info_block(b)
                    data = client.read_block(t, b, lw * 2)
                    if bitpart is not None:
                        bit = int(bitpart, 0)
                        byte = data[bit // 8]
                        val = str((byte >> (bit % 8)) & 1)
                    else:
                        val = data.hex()
                except Exception:
                    val = "ERR"

                def _update(i=iid, time=ts, value=val):
                    if i in app.rec_table.get_children():
                        app.rec_table.item(i, values=(time, key, value))
                app.rec_table.after(0, _update)

                if app.recording and csv_writer:
                    try:
                        csv_writer.writerow([ts, key, val])
                        csv_file.flush()
                    except:
                        pass

            time.sleep(interval)

    finally:
        client.__exit__(None, None, None)
        if csv_file:
            csv_file.close()
