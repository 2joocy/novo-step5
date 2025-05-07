#!/usr/bin/env python3
"""
as511_gui_modern.py

Modern Dark-Mode GUI for AS511 PLC Tool using CustomTkinter.
"""

import threading, re, os
import customtkinter as ctk
from tkinter import filedialog, messagebox
from as511_core import ExtendedAS511Client, TYPE_MAP

# Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class PLCToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AS511 PLC Tool")
        self.geometry("800x600")
        
        # Connection Frame
        conn = ctk.CTkFrame(self, corner_radius=12)
        conn.pack(fill="x", padx=20, pady=10)
        self._make_conn_controls(conn)
        
        # Tab View
        tv = ctk.CTkTabview(self, width=860, height=480, corner_radius=8)
        tv.pack(padx=20, pady=(0,20), expand=True)
        for name in ("Download", "Upload", "Compare"):
            tv.add(name)
        
        self._build_download_tab(tv.tab("Download"))
        self._build_upload_tab(tv.tab("Upload"))
        self._build_compare_tab(tv.tab("Compare"))
        
        self.client = None

    def _make_conn_controls(self, parent):
        labels = ["Device","Baud","Addr","Timeout","Retries"]
        defaults = ["/dev/ttyUSB0","9600","2","1.0","3"]
        vars_ = []
        for i,(lbl,defv) in enumerate(zip(labels, defaults)):
            ctk.CTkLabel(parent, text=lbl).grid(row=0, column=2*i, padx=(5,2))
            var = ctk.StringVar(value=defv); vars_.append(var)
            ctk.CTkEntry(parent, textvariable=var, width=80).grid(row=0, column=2*i+1, padx=(0,5))
        self.device_var,self.baud_var,self.addr_var,self.timeout_var,self.retries_var = vars_

    def _make_client(self):
        if self.client: self.client.close()
        self.client = ExtendedAS511Client(
            device=self.device_var.get(),
            baudrate=int(self.baud_var.get()),
            plc_address=int(self.addr_var.get()),
            timeout=float(self.timeout_var.get()),
            retries=int(self.retries_var.get()),
            logger=None
        )

    def _build_download_tab(self, frame):
        self.dl_type = ctk.CTkEntry(frame, placeholder_text="Type ID (e.g. 0x08 or 8)")
        self.dl_type.pack(padx=20, pady=(20,5), anchor="w")
        self.dl_out  = ctk.CTkEntry(frame, placeholder_text="Select output directory", width=400)
        self.dl_out.pack(padx=20, pady=(0,5), anchor="w")
        ctk.CTkButton(frame, text="Browse…", command=self._browse_dl).pack(padx=20, anchor="w")
        ctk.CTkButton(frame, text="Download", command=lambda: threading.Thread(target=self._dl,daemon=True).start())\
            .pack(padx=20, pady=10, anchor="w")
        self.dl_log = ctk.CTkTextbox(frame, width=800, height=200)
        self.dl_log.pack(padx=20, pady=(0,10))

    def _browse_dl(self):
        d = filedialog.askdirectory()
        if d: self.dl_out.delete(0,"end"); self.dl_out.insert(0,d)

    def _dl(self):
        self._make_client(); self.client.open()
        try:
            tid = int(self.dl_type.get(),0)
            blks = self.client.download_blocks(tid, self.dl_out.get())
            self.dl_log.insert("end", f"Downloaded blocks: {blks}\\n")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.client.close()

    def _build_upload_tab(self, frame):
        self.ul_type = ctk.CTkEntry(frame, placeholder_text="Type ID")
        self.ul_type.pack(padx=20, pady=(20,5), anchor="w")
        self.ul_in   = ctk.CTkEntry(frame, placeholder_text="Select input directory", width=400)
        self.ul_in.pack(padx=20, pady=(0,5), anchor="w")
        ctk.CTkButton(frame, text="Browse…", command=self._browse_ul).pack(padx=20, anchor="w")
        ctk.CTkButton(frame, text="Upload", command=lambda: threading.Thread(target=self._ul,daemon=True).start())\
            .pack(padx=20, pady=10, anchor="w")
        self.ul_log = ctk.CTkTextbox(frame, width=800, height=200)
        self.ul_log.pack(padx=20, pady=(0,10))

    def _browse_ul(self):
        d = filedialog.askdirectory()
        if d: self.ul_in.delete(0,"end"); self.ul_in.insert(0,d)

    def _ul(self):
        self._make_client(); self.client.open()
        try:
            tid = int(self.ul_type.get(),0)
            blks = self.client.upload_blocks(tid, self.ul_in.get())
            self.ul_log.insert("end", f"Uploaded blocks: {blks}\\n")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.client.close()

    def _build_compare_tab(self, frame):
        self.cr_pat = ctk.CTkEntry(frame, placeholder_text="Type Regex (e.g. FB)")
        self.cr_pat.pack(padx=20, pady=(20,5), anchor="w")
        self.cr_base= ctk.CTkEntry(frame, placeholder_text="Baseline directory", width=400)
        self.cr_base.pack(padx=20, pady=(0,5), anchor="w")
        ctk.CTkButton(frame, text="Browse…", command=self._browse_cr).pack(padx=20, anchor="w")
        ctk.CTkButton(frame, text="Compare", command=lambda: threading.Thread(target=self._cmp,daemon=True).start())\
            .pack(padx=20, pady=10, anchor="w")
        self.cr_log = ctk.CTkTextbox(frame, width=800, height=200)
        self.cr_log.pack(padx=20, pady=(0,10))

    def _browse_cr(self):
        d = filedialog.askdirectory()
        if d: self.cr_base.delete(0,"end"); self.cr_base.insert(0,d)

    def _cmp(self):
        self._make_client(); self.client.open()
        try:
            pat = re.compile(self.cr_pat.get(), re.IGNORECASE)
            for tid,name in TYPE_MAP.items():
                if not pat.search(name): continue
                for bn in self.client.list_blocks(tid):
                    fn = f"block_{tid:02X}_{bn}.bin"
                    fp = os.path.join(self.cr_base.get(), fn)
                    if not os.path.isfile(fp):
                        self.cr_log.insert("end", f"{name}#{bn} missing\\n"); continue
                    diff = self.client.compare_block(tid, bn, fp)
                    if diff:
                        self.cr_log.insert("end", f"=== DIFF {name}#{bn} ===\\n")
                        self.cr_log.insert("end", "\\n".join(diff)+"\\n")
                    else:
                        self.cr_log.insert("end", f"{name}#{bn} OK\\n")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.client.close()

if __name__ == "__main__":
    app = PLCToolApp()
    app.mainloop()
