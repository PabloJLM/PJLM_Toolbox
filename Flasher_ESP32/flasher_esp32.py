import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox

import serial.tools.list_ports as list_ports

CHIPS = ["auto", "esp32c6", "esp32c5", "esp32s3", "esp32s2", "esp32c3", "esp32"]
BAUDS = ["115200", "230400", "460800", "921600"]

PRESET_ARDUINO = [
    ("0x0",     "bootloader.bin"),
    ("0x8000",  "partitions.bin"),
    ("0xe000",  "boot_app0.bin"),
    ("0x10000", "firmware.bin"),
]
PRESET_BIN_UNICO = [("0x0", "firmware.bin")]


class FlashGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flasher ESP32 (esptool)")
        self.geometry("720x520")

        self.proc = None
        self.log_q = queue.Queue()

        self._build_top()
        self._build_table()
        self._build_actions()
        self._build_log()

        self.refresh_ports()
        self.after(100, self._poll_log)

    # ---------- UI ----------

    def _build_top(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(top, text="Puerto").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=18, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=5)
        tk.Button(top, text="Refrescar", command=self.refresh_ports).grid(row=0, column=2, padx=5)

        tk.Label(top, text="Baudios").grid(row=0, column=3, sticky="w", padx=(15, 0))
        self.baud_var = tk.StringVar(value="460800")
        ttk.Combobox(top, textvariable=self.baud_var, values=BAUDS, width=10, state="readonly").grid(row=0, column=4, padx=5)

        tk.Label(top, text="Chip").grid(row=0, column=5, sticky="w", padx=(15, 0))
        self.chip_var = tk.StringVar(value="auto")
        ttk.Combobox(top, textvariable=self.chip_var, values=CHIPS, width=10, state="readonly").grid(row=0, column=6, padx=5)

    def _build_table(self):
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=False, padx=10, pady=10)

        cols = ("offset", "archivo")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=6)
        self.tree.heading("offset", text="Offset")
        self.tree.heading("archivo", text="Archivo")
        self.tree.column("offset", width=90, anchor="center")
        self.tree.column("archivo", width=560)
        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=10)
        tk.Button(btns, text="+ Archivo...", command=self.add_file_row).pack(side="left")
        tk.Button(btns, text="Quitar seleccionado", command=self.remove_row).pack(side="left", padx=5)
        tk.Button(btns, text="Preset: Arduino", command=lambda: self.load_preset(PRESET_ARDUINO)).pack(side="left", padx=5)
        tk.Button(btns, text="Preset: binario", command=lambda: self.load_preset(PRESET_BIN_UNICO)).pack(side="left", padx=5)

    def _build_actions(self):
        frame = tk.Frame(self)
        frame.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(frame, text="Flashear", bg="#2e7d32", fg="white", command=self.flash).pack(side="left")
        tk.Button(frame, text="Borrar flash completa", bg="#b71c1c", fg="white", command=self.erase_flash).pack(side="left", padx=5)
        tk.Button(frame, text="Detectar chip", command=self.detect_chip).pack(side="left", padx=5)
        tk.Button(frame, text="Detener", command=self.stop_proc).pack(side="left", padx=5)

    def _build_log(self):
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(frame, bg="#0b0b0b", fg="#d9d9d9", font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

    # ---------- acciones de la tabla ----------

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def add_file_row(self):
        path = filedialog.askopenfilename(
            title="Elegi el binario (.bin)",
            filetypes=[("Binarios", "*.bin"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        offset = simpledialog.askstring(
            "Offset", "Direccion de flasheo (ej. 0x10000):", initialvalue="0x10000", parent=self
        )
        if not offset:
            return
        self.tree.insert("", "end", values=(offset, path))

    def remove_row(self):
        for item in self.tree.selection():
            self.tree.delete(item)

    def load_preset(self, preset):
        for offset, hint in preset:
            path = filedialog.askopenfilename(
                title=f"Elegi el archivo para {offset} ({hint})",
                filetypes=[("Binarios", "*.bin"), ("Todos los archivos", "*.*")],
            )
            if not path:
                continue
            self.tree.insert("", "end", values=(offset, path))

    def get_rows(self):
        rows = []
        for item in self.tree.get_children():
            offset, path = self.tree.item(item, "values")
            rows.append((offset, path))
        return rows

    # ---------- esptool ----------

    def _base_cmd(self):
        if not self.port_var.get():
            messagebox.showerror("Error", "Elegi un puerto serial.")
            return None
        cmd = [sys.executable, "-m", "esptool",
               "--port", self.port_var.get(),
               "--baud", self.baud_var.get()]
        if self.chip_var.get() != "auto":
            cmd += ["--chip", self.chip_var.get()]
        return cmd

    def flash(self):
        rows = self.get_rows()
        if not rows:
            messagebox.showwarning("Sin archivos", "Agrega al menos un archivo con su offset.")
            return
        cmd = self._base_cmd()
        if cmd is None:
            return
        cmd += ["write_flash"]
        for offset, path in rows:
            cmd += [offset, path]
        self._run(cmd)

    def erase_flash(self):
        if not messagebox.askyesno("Confirmar", "Esto borra TODA la flash. Continuar?"):
            return
        cmd = self._base_cmd()
        if cmd is None:
            return
        cmd += ["erase_flash"]
        self._run(cmd)

    def detect_chip(self):
        cmd = self._base_cmd()
        if cmd is None:
            return
        cmd += ["chip_id"]
        self._run(cmd)

    def _run(self, cmd):
        if self.proc is not None:
            messagebox.showwarning("Ocupado", "Ya hay un comando corriendo.")
            return
        self._log_line("$ " + " ".join(cmd) + "\n")

        def worker():
            try:
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                for line in self.proc.stdout:
                    self.log_q.put(line)
                self.proc.wait()
                self.log_q.put(f"\n[terminado, codigo {self.proc.returncode}]\n")
            except FileNotFoundError:
                self.log_q.put("\n[error] no se encontro esptool. Instala con: pip install esptool\n")
            except Exception as e:
                self.log_q.put(f"\n[error] {e}\n")
            finally:
                self.proc = None

        threading.Thread(target=worker, daemon=True).start()

    def stop_proc(self):
        if self.proc is not None:
            self.proc.terminate()
            self._log_line("\n[detenido por el usuario]\n")

    def _poll_log(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self._log_line(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    def _log_line(self, line):
        self.log.insert("end", line)
        self.log.see("end")


if __name__ == "__main__":
    FlashGUI().mainloop()