#!/usr/bin/env python3
"""
as511_gui.py

Main launcher for the AS511 PLC Tool GUI.
Includes a Connect button that toggles through Offline→Connecting→Online,
and prevents any PLC actions until connected.
"""

import customtkinter as ctk
from serial.tools import list_ports
from tkinter import messagebox

from as511_core import ExtendedAS511Client, AS511Client
from views.download_gui import build_download_tab
from views.upload_gui import build_upload_tab
from views.compare_gui import build_compare_tab
from views.record_gui import build_record_gui_tab

# dark mode
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class PLCToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AS511 PLC Tool")
        self.geometry("1000x700")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.client = None
        self.connected = False

        self._build_conn_frame()
        self._build_tabs()

    def _build_conn_frame(self):
        frm = ctk.CTkFrame(self, corner_radius=8, border_width=2, border_color="gray30")
        frm.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        for i in range(14):
            frm.grid_columnconfigure(i, weight=1)

        # Device selector
        ctk.CTkLabel(frm, text="Device:").grid(row=0, column=0, padx=5, sticky="w")
        ports = [p.device for p in list_ports.comports()] or [f"COM{i}" for i in range(1,9)]
        self.device_var = ctk.StringVar(value=ports[0])
        self.device_combo = ctk.CTkComboBox(frm, values=ports, variable=self.device_var, width=200)
        self.device_combo.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(frm, text="↻", width=30, command=self._refresh_ports)\
            .grid(row=0, column=2, padx=5)

        # Connect button / status
        self.conn_btn = ctk.CTkButton(
            frm,
            text="Connect",
            fg_color="#d9534f",      # red
            hover_color="#c9302c",
            command=self._connect
        )
        self.conn_btn.grid(row=0, column=3, padx=5)

        # Serial parameters
        opts = [("Baud","9600"), ("Addr","2"), ("Timeout","1.0"), ("Retries","3")]
        for idx, (lbl, default) in enumerate(opts, start=3):
            col = idx * 2
            ctk.CTkLabel(frm, text=f"{lbl}:").grid(row=0, column=col, padx=5, sticky="e")
            var = ctk.StringVar(value=default)
            setattr(self, f"{lbl.lower()}_var", var)
            ctk.CTkEntry(frm, textvariable=var, width=80)\
                .grid(row=0, column=col+1, padx=5, sticky="w")

    def _refresh_ports(self):
        ports = [p.device for p in list_ports.comports()] or [f"COM{i}" for i in range(1,9)]
        self.device_combo.configure(values=ports)
        self.device_var.set(ports[0])

    def _make_client(self) -> ExtendedAS511Client:
        if self.client:
            self.client.close()
        self.client = ExtendedAS511Client(
            device=self.device_var.get(),
            baudrate=int(self.baud_var.get()),
            plc_address=int(self.addr_var.get()),
            timeout=float(self.timeout_var.get()),
            retries=int(self.retries_var.get())
        )
        return self.client

    def _connect(self):
        MAX_RETRIES = 3  # Define the maximum number of retries
        for attempt in range(1, MAX_RETRIES + 1):
            # Update the button to show the current connection attempt
            self.conn_btn.configure(
                text=f"Connecting… (Attempt {attempt}/{MAX_RETRIES})",
                fg_color="#f0ad4e",
                state="disabled"
            )
            self.update_idletasks()

            try:
                cli = self._make_client()
                cli.__enter__()
                ser = cli._ser
                ser.flush_input()
                ser.flush_output()
                ser.write(bytes([AS511Client.STX]))
                resp = ser.read(2)
                cli.__exit__(None, None, None)

                if resp == bytes([AS511Client.DLE, AS511Client.ACK]):
                    # Success: Update button and set connected flag
                    self.connected = True
                    self.conn_btn.configure(text="Online", fg_color="#5cb85c", state="disabled")
                    return
                else:
                    raise RuntimeError(f"Unexpected reply: {resp!r}")

            except Exception as e:
                self.logger.warning(f"Connection attempt {attempt} failed: {e}")

            # If it's the last attempt, show an error message
            if attempt == MAX_RETRIES:
                self.connected = False
                self.conn_btn.configure(text="Connect", fg_color="#d9534f", state="normal")
                messagebox.showerror("Connection Error", f"Failed to connect after {MAX_RETRIES} attempts.\nError: {e}")

    def _build_tabs(self):
        tabs = ctk.CTkTabview(self, width=980, height=580, corner_radius=8)
        tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))

        for name in ("Download","Upload","Compare","Record"):
            tabs.add(name)
            frame = tabs.tab(name)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(4, weight=1)

        build_download_tab(self, tabs.tab("Download"))
        build_upload_tab(self, tabs.tab("Upload"))
        build_compare_tab(self, tabs.tab("Compare"))
        build_record_gui_tab(self, tabs.tab("Record"))


if __name__ == "__main__":
    app = PLCToolApp()
    app.mainloop()
