#!/usr/bin/env python3
"""
as511_gui.py Main launcher for the AS511 PLC Tool GUI.

This version uses the `views` package for each tab, delegating UI building to those modules.
"""
import customtkinter as ctk
from serial.tools import list_ports
from tkinter import messagebox

from as511_core import AS511Client
from views.download_gui import build_download_tab
from views.upload_gui import build_upload_tab
from views.compare_gui import build_compare_tab
from views.record_gui import build_record_tab

# Dark-mode appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Defaults
BAUD_RATE = 9600
PLC_ADDRESS = 1
TIMEOUT = 2.0
RETRIES = 3

class PLCToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AS511 PLC Tool")
        self.geometry("900x600")

        self.client = None
        self.connected = False

        self._build_top_bar()
        self._build_tabs()

    def _build_top_bar(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=10, pady=5)

        # Port selection
        self.port_cb = ctk.CTkComboBox(frame, width=200)
        self._refresh_ports()
        self.port_cb.grid(row=0, column=0, padx=5)
        ctk.CTkButton(frame, text="Refresh", command=self._refresh_ports).grid(row=0, column=1, padx=5)

        # Connect and Scan buttons
        self.connect_btn = ctk.CTkButton(frame, text="Connect", fg_color="#d9534f", command=self._connect)
        self.connect_btn.grid(row=0, column=2, padx=5)
        self.scan_btn = ctk.CTkButton(frame, text="Scan", command=self._start_scan)
        self.scan_btn.grid(row=0, column=6, padx=5)

        # Settings entries
        self.addr_entry = ctk.CTkEntry(frame, width=50, placeholder_text="Addr")
        self.addr_entry.insert(0, str(PLC_ADDRESS))
        self.addr_entry.grid(row=0, column=3, padx=5)
        self.timeout_entry = ctk.CTkEntry(frame, width=50, placeholder_text="Timeout")
        self.timeout_entry.insert(0, str(TIMEOUT))
        self.timeout_entry.grid(row=0, column=4, padx=5)
        self.retries_entry = ctk.CTkEntry(frame, width=50, placeholder_text="Retries")
        self.retries_entry.insert(0, str(RETRIES))
        self.retries_entry.grid(row=0, column=5, padx=5)

    def _refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_cb.configure(values=ports)
        if ports:
            self.port_cb.set(ports[0])

    def _make_client(self):
        raw = self.port_cb.get()
        cfg = dict(
            port=raw,
            baudrate=BAUD_RATE,
            plc_address=int(self.addr_entry.get()),
            timeout=float(self.timeout_entry.get()),
            max_retries=int(self.retries_entry.get())
        )
        if self.client:
            self.client.close()
        self.client = AS511Client(**cfg)
        return self.client

    def _connect(self):
        self.connect_btn.configure(state="disabled", text="Connecting…")
        try:
            client = self._make_client()
            client.connect()
            self.connected = True
            self.connect_btn.configure(text="Online", fg_color="#5cb85c")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.connect_btn.configure(text="Connect", fg_color="#d9534f", state="normal")

    def _build_tabs(self):
        tabs = ctk.CTkTabview(self)
        tabs.pack(expand=True, fill="both", padx=10, pady=10)
        # Add tabs
        tabs.add("Download")
        tabs.add("Upload")
        tabs.add("Compare")
        tabs.add("Identify")

        # Delegate tab building to view modules
        build_download_tab(self, tabs.tab("Download"))
        build_upload_tab(self, tabs.tab("Upload"))
        build_compare_tab(self, tabs.tab("Compare"))
        build_record_gui_tab(self, tabs.tab("Record"))

if __name__ == "__main__":
    app = PLCToolApp()
    app.mainloop()
