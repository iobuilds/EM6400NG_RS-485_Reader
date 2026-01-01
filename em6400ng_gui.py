import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
from dataclasses import dataclass
from typing import List, Optional

from serial.tools import list_ports
from pymodbus.client import ModbusSerialClient
from PIL import Image, ImageTk


# ----------------------------
# Register model
# ----------------------------
@dataclass
class RegItem:
    offset: int
    name: str
    unit: str
    fc: int = 4           # 4=input, 3=holding
    dtype: str = "float32"
    count: int = 2        # float32 = 2 regs
    scale: float = 1.0

    @property
    def address(self) -> int:
        return self.offset - 1


# ----------------------------
# Helpers
# ----------------------------
def list_serial_ports_preferred() -> List[str]:
    """
    On macOS you'll see many /dev/cu.* entries (Bluetooth etc.)
    We prefer real USB serial ports first, but still show others.
    """
    ports = [p.device for p in list_ports.comports()]

    def is_noise(p: str) -> bool:
        s = p.lower()
        return ("bluetooth" in s) or ("debug-console" in s) or ("internalmodem" in s)

    def is_usb(p: str) -> bool:
        s = p.lower()
        return ("usbserial" in s) or ("usbmodem" in s) or ("wchusbserial" in s) or ("slab_usbto" in s)

    usb = [p for p in ports if is_usb(p)]
    other = [p for p in ports if (p not in usb) and (not is_noise(p))]
    noise = [p for p in ports if is_noise(p)]

    # Show USB first, then other useful, keep noise last (still available if needed)
    return usb + other + noise


def decode_float32(regs: List[int], swap_words: bool = False) -> Optional[float]:
    if regs is None or len(regs) < 2:
        return None
    hi = int(regs[0]) & 0xFFFF
    lo = int(regs[1]) & 0xFFFF
    if swap_words:
        hi, lo = lo, hi
    raw = (hi << 16) | lo
    import struct
    return struct.unpack(">f", struct.pack(">I", raw))[0]


# ----------------------------
# Default register list
# ----------------------------
DEFAULT_REGS: List[RegItem] = [
    RegItem(2699, "Active energy delivered (into load)", "kWh", fc=3),
    RegItem(2701, "Active energy received (out of load)", "kWh", fc=3),
    RegItem(2703, "Active energy delivered + received", "kWh", fc=3),

    RegItem(2999, "Current A", "A", fc=4),
    RegItem(3001, "Current B", "A", fc=4),
    RegItem(3003, "Current C", "A", fc=4),
    RegItem(3009, "Current avg", "A", fc=4),

    RegItem(3019, "Voltage A B", "V", fc=4),
    RegItem(3021, "Voltage B C", "V", fc=4),
    RegItem(3023, "Voltage C A", "V", fc=4),
    RegItem(3025, "Voltage L L avg", "V", fc=4),

    RegItem(3053, "Active power A", "kW", fc=4),
    RegItem(3055, "Active power B", "kW", fc=4),
    RegItem(3057, "Active power C", "kW", fc=4),
    RegItem(3059, "Active power total", "kW", fc=4),

    RegItem(3061, "Reactive power A", "kVAR", fc=4),
    RegItem(3063, "Reactive power B", "kVAR", fc=4),
    RegItem(3065, "Reactive power C", "kVAR", fc=4),
    RegItem(3067, "Reactive power total", "kVAR", fc=4),

    RegItem(3069, "Apparent power A", "kVA", fc=4),
    RegItem(3071, "Apparent power B", "kVA", fc=4),
    RegItem(3073, "Apparent power C", "kVA", fc=4),
    RegItem(3075, "Apparent power total", "kVA", fc=4),
]


class EM6400NGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EM6400NG RS-485 Reader (Modbus RTU)")
        self.geometry("1020x620")

        self.client: Optional[ModbusSerialClient] = None
        self.connected = False
        self.polling = False
        self.poll_thread: Optional[threading.Thread] = None

        self.regs: List[RegItem] = list(DEFAULT_REGS)

        self._build_ui()
        self._refresh_ports()
        self._render_regs()
        self._log("Ready.")

    def _build_ui(self):
        # Top row
        top = ttk.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        # Logo (keep aspect ratio)
        logo_frame = ttk.Frame(top)
        logo_frame.pack(side=tk.LEFT, padx=(0, 12), anchor="n")

        try:
            logo_path = os.path.join(os.path.dirname(__file__), "images", "logo.png")
            img = Image.open(logo_path)
            target_h = 80
            w, h = img.size
            scale = target_h / h
            new_size = (max(1, int(w * scale)), target_h)
            img = img.resize(new_size, Image.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(logo_frame, image=self.logo_img).pack(anchor="nw")
        except Exception as e:
            ttk.Label(
                logo_frame,
                text="LOGO\nmissing",
                width=16,
                anchor="center",
                relief="groove"
            ).pack(ipadx=8, ipady=12)
            print("Logo load error:", e)

        # Connection
        conn = ttk.LabelFrame(top, text="Connection", padding=10)
        conn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(conn, text="Port").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(conn, textvariable=self.port_var, width=34, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Button(conn, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, sticky="w", padx=6)

        ttk.Label(conn, text="Baud").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.baud_var = tk.StringVar(value="19200")
        self.baud_cb = ttk.Combobox(conn, textvariable=self.baud_var, width=34, state="readonly",
                                    values=["4800", "9600", "19200", "38400"])
        self.baud_cb.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(conn, text="Parity").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.parity_var = tk.StringVar(value="E")
        self.parity_cb = ttk.Combobox(conn, textvariable=self.parity_var, width=34, state="readonly",
                                      values=["E", "O", "N"])
        self.parity_cb.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(conn, text="Slave ID").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.slave_var = tk.StringVar(value="1")
        ttk.Entry(conn, textvariable=self.slave_var, width=37).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(conn, text="Poll (ms)").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.poll_ms_var = tk.StringVar(value="1000")
        ttk.Entry(conn, textvariable=self.poll_ms_var, width=37).grid(row=4, column=1, sticky="w", padx=6, pady=(6, 0))

        self.swap_words_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(conn, text="Swap 16-bit words (if values wrong)", variable=self.swap_words_var)\
            .grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.connect_btn = ttk.Button(conn, text="Connect", command=self._connect)
        self.connect_btn.grid(row=0, column=3, sticky="w", padx=(16, 6))

        self.disconnect_btn = ttk.Button(conn, text="Disconnect", command=self._disconnect, state="disabled")
        self.disconnect_btn.grid(row=1, column=3, sticky="w", padx=(16, 6), pady=(6, 0))

        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(conn, textvariable=self.status_var).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # Main area: use GRID so log doesn't collapse on startup
        main = ttk.Frame(self, padding=10)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        main.grid_rowconfigure(0, weight=1)   # table row expands
        main.grid_rowconfigure(1, weight=0)   # log row fixed
        main.grid_columnconfigure(0, weight=1)

        # Table
        table_frame = ttk.LabelFrame(main, text="Live Values", padding=10)
        table_frame.grid(row=0, column=0, sticky="nsew")

        cols = ("name", "fc", "offset", "address", "unit", "value")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=c.upper())

        self.tree.column("name", width=360)
        self.tree.column("fc", width=50, anchor="center")
        self.tree.column("offset", width=80, anchor="e")
        self.tree.column("address", width=80, anchor="e")
        self.tree.column("unit", width=80, anchor="center")
        self.tree.column("value", width=200, anchor="e")

        self.tree.grid(row=0, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=table_scroll.set)

        # Log (fixed visible height)
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.log = tk.Text(log_frame, height=6)
        self.log.grid(row=0, column=0, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

        ttk.Button(log_frame, text="Clear Log", command=lambda: self.log.delete("1.0", tk.END))\
            .grid(row=0, column=2, padx=(8, 0), sticky="ne")

    # ----------------------------
    # Core
    # ----------------------------
    def _refresh_ports(self):
        ports = list_serial_ports_preferred()
        self.port_cb["values"] = ports

        # Keep current selection if still present
        current = self.port_var.get()
        if current and current in ports:
            self.port_var.set(current)
        elif ports:
            self.port_var.set(ports[0])

        self._log(f"Ports: {ports if ports else 'No ports found'}")

    def _render_regs(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.regs):
            self.tree.insert("", tk.END, iid=str(i),
                             values=(r.name, r.fc, r.offset, r.address, r.unit, ""))

    def _connect(self):
        if self.connected:
            return

        port = (self.port_var.get() or "").strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port.")
            return

        try:
            baud = int(self.baud_var.get())
            slave = int(self.slave_var.get())
            if not (1 <= slave <= 247):
                raise ValueError("Slave ID must be 1..247")
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")
            return

        parity = (self.parity_var.get() or "").strip().upper()
        if parity not in ("E", "O", "N"):
            messagebox.showerror("Error", "Parity must be E, O, or N.")
            return

        self.client = ModbusSerialClient(
            port=port,
            baudrate=baud,
            parity=parity,
            stopbits=1,
            bytesize=8,
            timeout=1.0
        )

        ok = self.client.connect()
        if not ok:
            self.client = None
            messagebox.showerror("Error", "Failed to open port. Check USB-RS485 driver/port.")
            return

        self.connected = True
        self.connect_btn.config(state="disabled")
        self.disconnect_btn.config(state="normal")
        self.status_var.set(f"Connected: {port}  {baud}  8{parity}1  Slave {slave}")
        self._log("Connected OK.")

        self.polling = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _disconnect(self):
        self.polling = False
        time.sleep(0.1)
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.connected = False
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.status_var.set("Not connected")
        self._log("Disconnected.")

    def _poll_loop(self):
        while self.polling:
            try:
                poll_ms = int(self.poll_ms_var.get())
                if poll_ms < 200:
                    poll_ms = 200
            except Exception:
                poll_ms = 1000

            if self.connected and self.client:
                self._poll_once()

            time.sleep(poll_ms / 1000.0)

    def _poll_once(self):
        try:
            slave = int(self.slave_var.get())
        except Exception:
            slave = 1

        swap_words = bool(self.swap_words_var.get())

        for idx, reg in enumerate(self.regs):
            try:
                if reg.fc == 3:
                    rr = self.client.read_holding_registers(reg.address, reg.count, slave=slave)
                else:
                    rr = self.client.read_input_registers(reg.address, reg.count, slave=slave)

                if rr.isError():
                    val_txt = "ERR"
                    self._log(f"{reg.name}: {rr}")
                else:
                    v = decode_float32(rr.registers, swap_words=swap_words)
                    val_txt = "N/A" if v is None else f"{(v * reg.scale):.4f}"

                self.after(0, self._set_tree_value, idx, val_txt)

            except Exception as e:
                self.after(0, self._set_tree_value, idx, "EXC")
                self._log(f"{reg.name}: Exception {e}")

    def _set_tree_value(self, idx: int, val_txt: str):
        iid = str(idx)
        if self.tree.exists(iid):
            self.tree.set(iid, "value", val_txt)

    def _log(self, s: str):
        ts = time.strftime("%H:%M:%S")
        try:
            self.log.insert(tk.END, f"[{ts}] {s}\n")
            self.log.see(tk.END)
        except Exception:
            print(f"[{ts}] {s}")


if __name__ == "__main__":
    EM6400NGApp().mainloop()