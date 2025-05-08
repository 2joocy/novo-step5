#!/usr/bin/env python3
"""
as511_gui.py

Main launcher for the AS511 PLC Tool GUI.

Implements the AS511 protocol handshake per spec:
  - PG sends STX (0x02)
  - AG responds DLE (0x10)
  - PG reads next byte: ACK (0x06) or NAK (0x15)
  - On ACK: connection established
  - On NAK: immediate abort of that attempt, 500 ms delay, then retry
  - Retries and timeouts user-configurable

Features:
  - Manual Connect button
  - Auto-detect scan: INFO/IDENTIFY across all serial ports
  - Dropdown shows port, optional system description and HWID
  - Scan enriches entries with PLC identity
  - Dynamic info panel on selection
  - Tabs: Download, Upload, Compare, Record
  - Dark-mode CustomTkinter UI

Protocol doc: https://www.runmode.com/as511protocol_description.pdf
"""

import time
import threading
import customtkinter as ctk
from serial.tools import list_ports
from tkinter import messagebox
from as511_core import ExtendedAS511Client

from views.download_gui import build_download_tab
from views.upload_gui import build_upload_tab
from views.compare_gui import build_compare_tab
from views.record_gui import build_record_gui_tab

# Dark-mode appearance
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
        self.port_map = {}      # display -> raw device
        self.port_info = {}     # display -> ListPortInfo

        self._build_top_bar()
        self._build_tabs()

    def _build_top_bar(self):
        # Initialize all required StringVars
        self.device_var = ctk.StringVar()
        self.baud_var = ctk.StringVar(value="9600")
        self.addr_var = ctk.StringVar(value="2")
        self.timeout_var = ctk.StringVar(value="1.0")
        self.retries_var = ctk.StringVar(value="3")

        bar = ctk.CTkFrame(self, corner_radius=6, fg_color="#2b2b2b")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        bar.grid_columnconfigure((0, 1, 2), weight=1)

        # LEFT SECTION: Device controls
        left_frame = ctk.CTkFrame(bar, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        left_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(left_frame, text="Device:").grid(row=0, column=0, sticky="e", padx=4)
        self.device_combo = ctk.CTkComboBox(left_frame, variable=self.device_var, width=150)
        self.device_combo.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(left_frame, text="↻", width=30, command=self._refresh_ports).grid(
            row=0, column=2, sticky="ew", padx=5)
        self.conn_btn = ctk.CTkButton(left_frame, text="Connect", fg_color="#d9534f",
                                      hover_color="#c9302c", command=self._connect)
        self.conn_btn.grid(row=0, column=3, sticky="ew", padx=5)

        # MIDDLE SECTION: Auto-detect
        middle_frame = ctk.CTkFrame(bar, fg_color="transparent")
        middle_frame.grid(row=0, column=1, sticky="ew", padx=10)
        middle_frame.grid_columnconfigure(0, weight=1)

        self.scan_btn = ctk.CTkButton(middle_frame, text="Auto-detect", command=self._start_scan)
        self.scan_btn.grid(row=0, column=0, sticky="ew")

        # RIGHT SECTION: Serial settings
        right_frame = ctk.CTkFrame(bar, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="ew", padx=(10, 0))

        settings = [
            ("Baud", self.baud_var),
            ("Addr", self.addr_var),
            ("Timeout", self.timeout_var),
            ("Retries", self.retries_var)
        ]

        for idx, (label_text, var) in enumerate(settings):
            ctk.CTkLabel(right_frame, text=f"{label_text}:").grid(
                row=0, column=idx * 2, sticky="e", padx=(0, 4))
            entry = ctk.CTkEntry(right_frame, textvariable=var, width=60)
            entry.grid(row=0, column=idx * 2 + 1, sticky="ew", padx=(0, 8))
            right_frame.grid_columnconfigure(idx * 2 + 1, weight=1)

        self._refresh_ports()

    def _refresh_ports(self):
        infos = list_ports.comports()
        disp_vals = []
        self.port_map.clear()
        self.port_info.clear()
        for info in infos:
            disp = info.device
            if info.description.strip():
                disp += f" ({info.description})"
            disp_vals.append(disp)
            self.port_map[disp] = info.device
            self.port_info[disp] = info
        # Update combo values or show placeholder
        if disp_vals:
            self.device_combo.configure(values=disp_vals)
            self.device_var.set(disp_vals[0])
        else:
            self.device_combo.configure(values=["<No ports detected>"])
            self.device_var.set("<No ports detected>")

    def _on_device_select(self, *args):
        info = self.port_info.get(self.device_var.get())
        if not info:
            self.device_info.configure(text="")
            return
        parts = []
        if info.description:
            parts.append(f"Desc: {info.description}")
        if info.hwid:
            parts.append(f"HWID: {info.hwid}")
        if getattr(info, 'identity', None):
            parts.append(f"PLC: {info.identity}")
        self.device_info.configure(text=" | ".join(parts))

    def _start_scan(self):
        self.scan_btn.configure(state="disabled")
        self.conn_btn.configure(state="disabled")
        self.scan_btn.configure(text="Scanning…")
        threading.Thread(target=self._scan_ports, daemon=True).start()

    def _scan_ports(self):
        found = []
        baud = int(self.baud_var.get())
        addr = int(self.addr_var.get())
        timeout = float(self.timeout_var.get())
        for info in list_ports.comports():
            try:
                client = ExtendedAS511Client(
                    device=info.device,
                    baudrate=baud,
                    plc_address=addr,
                    timeout=timeout,
                    retries=1
                )
                with client as cli:
                    identity = cli.get_identification()
                info.identity = identity
                found.append(info)
            except:
                continue
        self.after(0, self._update_scan_results, found)

    def _update_scan_results(self, infos):
        disp_vals = []
        self.port_map.clear()
        self.port_info.clear()
        for info in infos:
            disp = info.device
            disp += f" — {info.identity}" if getattr(info, 'identity', None) else ''
            if info.description.strip():
                disp += f" ({info.description})"
            disp_vals.append(disp)
            self.port_map[disp] = info.device
            self.port_info[disp] = info
        if disp_vals:
            self.device_combo.configure(values=disp_vals)
            self.device_var.set(disp_vals[0])
            messagebox.showinfo(
                "Scan Complete",
                f"Found {len(disp_vals)} devices:\n" + "\n".join(disp_vals)
            )
        else:
            messagebox.showwarning("Warning", "No devices found")
            self.device_combo.configure(values=["<No ports detected>"])
        self.scan_btn.configure(state="normal")
        self.conn_btn.configure(state="normal")
        self.scan_btn.configure(text="Auto-detect")

    def _make_client(self) -> ExtendedAS511Client:
        if self.client:
            self.client.close()
        raw = self.port_map.get(self.device_var.get(), self.device_var.get())
        self.client = ExtendedAS511Client(
            device=raw,
            baudrate=int(self.baud_var.get()),
            plc_address=int(self.addr_var.get()),
            timeout=float(self.timeout_var.get()),
            retries=int(self.retries_var.get())
        )
        return self.client

    def _connect(self):
        tries = int(self.retries_var.get())
        delay = float(self.timeout_var.get())
        last_error = None
        for attempt in range(1, tries + 1):
            self.conn_btn.configure(
                text=f"Connecting ({attempt}/{tries})", fg_color="#f0ad4e", state="disabled"
            )
            self.update_idletasks()
            try:
                cli = self._make_client()
                cli.__enter__()
                ser = cli._ser
                ser.flush_input(); ser.flush_output()
                # 1) send STX
                ser.write(bytes([ExtendedAS511Client.STX]))
                # 2) expect DLE
                dle = ser.read(1)
                if dle != bytes([ExtendedAS511Client.DLE]):
                    raise RuntimeError(f"Expected DLE, got {dle!r}")
                # 3) read ACK/NAK
                resp = ser.read(1)
                cli.__exit__(None, None, None)
                if resp == bytes([ExtendedAS511Client.ACK]):
                    self.connected = True
                    self.conn_btn.configure(text="Online", fg_color="#5cb85c")
                    return
                if resp == bytes([ExtendedAS511Client.NAK]):
                    last_error = RuntimeError("Received NAK from PLC")
                    messagebox.showwarning("Connect", "PLC NAK’d the connection request.")
                    time.sleep(0.5)
                else:
                    last_error = RuntimeError(f"Unexpected reply: {resp!r}")
            except Exception as e:
                last_error = e
            finally:
                try: cli.__exit__(None, None, None)
                except: pass
            time.sleep(delay)
        # all attempts failed
        self.conn_btn.configure(text="Connect", fg_color="#d9534f", state="normal")
        messagebox.showerror("Connection Error", f"Failed after {tries} attempts.\n{last_error}")

    def _build_tabs(self):
        tabs = ctk.CTkTabview(self, corner_radius=6)
        tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,8))
        tabs.configure(width=0, height=0)
        for name in ("Download", "Upload", "Compare", "Record"):
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