import threading
import time
import customtkinter as ctk
from tkinter import messagebox
from tkinter import ttk


def build_record_tab(app, container):
    """
    Builds the Record tab UI for continuous block monitoring (bit or byte) (friendly names).

    Displays regular numbers (0 or 1) for specific bits (e.g. DB65.1),
    or whole byte values in decimal and hex for full blocks (e.g. DB65).

    Parameters:
    - app: reference to the main PLCToolApp instance
    - container: the CTkFrame for this tab
    """
    # Controls frame
    ctrl = ctk.CTkFrame(container)
    ctrl.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
    ctk.CTkLabel(ctrl, text="Block ID (e.g. DB65 or DB65.1):").grid(row=0, column=0, padx=(0,5))
    block_entry = ctk.CTkEntry(ctrl, width=100)
    block_entry.grid(row=0, column=1, sticky="w", padx=(0,15))
    ctk.CTkLabel(ctrl, text="Interval (s):").grid(row=0, column=2, padx=(0,5))
    interval_entry = ctk.CTkEntry(ctrl, width=60)
    interval_entry.insert(0, "1.0")
    interval_entry.grid(row=0, column=3, sticky="w", padx=(0,15))
    record_btn = ctk.CTkButton(ctrl, text="Start Recording", width=120)
    record_btn.grid(row=0, column=4)
    ctrl.grid_columnconfigure(1, weight=1)

    # Summary label
    summary_label = ctk.CTkLabel(container, text="", anchor="w")
    summary_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0,5))

    # Treeview frame for recorded values
    tree_frame = ctk.CTkFrame(container)
    tree_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
    container.grid_rowconfigure(2, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # Columns for timestamp, decimal, and hex output (if full byte)
    cols = ("Timestamp", "Decimal/Bit", "Hex (Byte)")
    record_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    for col in cols:
        record_tree.heading(col, text=col)
        record_tree.column(col, anchor="w", width=120)

    # Scrollbar
    vscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=record_tree.yview)
    record_tree.configure(yscrollcommand=vscroll.set)
    record_tree.grid(row=0, column=0, sticky="nsew")
    vscroll.grid(row=0, column=1, sticky="ns")
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    # State for recording thread
    stop_event = threading.Event()
    worker = None

    def on_record():
        nonlocal worker, stop_event
        if not app.connected:
            messagebox.showwarning("Not connected", "Please connect to a device first.")
            return
        # Toggle recording state
        if worker and worker.is_alive():
            stop_event.set()
            record_btn.configure(text="Start Recording", fg_color="#007bff")
            summary_label.configure(text="Recording stopped.")
        else:
            # Get and parse block ID
            blk_id_str = block_entry.get().strip()
            try:
                blk_num, bit_offset, friendly = app.client._parse_block_id(blk_id_str)
            except Exception as e:
                summary_label.configure(text=f"Invalid Block ID: {e}")
                return
            # Validate interval
            try:
                interval = float(interval_entry.get())
            except ValueError:
                summary_label.configure(text="Invalid interval; must be a number.")
                return
            stop_event.clear()
            record_btn.configure(text="Stop Recording", fg_color="#d9534f")
            summary_label.configure(text=f"Recording {friendly}...")
            # Clear previous entries
            for item in record_tree.get_children():
                record_tree.delete(item)

            def task():
                while not stop_event.is_set():
                    try:
                        res = app.client.read_block(blk_id_str)
                        ts = time.strftime("%H:%M:%S")
                        values = res['values']
                        if bit_offset is not None:
                            # get specific bit of first byte
                            byte_val = values[0]
                            bit_val = (byte_val >> bit_offset) & 1
                            dec_display = str(bit_val)
                            hex_display = ''  # no byte hex when showing bit
                        else:
                            dec_display = ' '.join(str(v) for v in values)
                            # show only first byte hex for context or full bytes?
                            hex_display = ' '.join(f"0x{v:02X}" for v in values)
                        # Insert row
                        record_tree.after(0, lambda t=ts, d=dec_display, h=hex_display: record_tree.insert(
                            "", "end", values=(t, d, h)
                        ))
                    except Exception as e:
                        err = str(e)
                        record_tree.after(0, lambda t="Error", d=err, h="": record_tree.insert(
                            "", "end", values=(t, d, h)
                        ))
                        stop_event.set()
                        summary_label.after(0, lambda: summary_label.configure(text="Error during recording."))
                        break
                    time.sleep(interval)
            worker = threading.Thread(target=task, daemon=True)
            worker.start()

    record_btn.configure(command=on_record)

    return {
        'block_entry': block_entry,
        'interval_entry': interval_entry,
        'record_btn': record_btn,
        'summary_label': summary_label,
        'record_tree': record_tree
    }
