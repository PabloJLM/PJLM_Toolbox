import tkinter as tk
from tkinter import filedialog, scrolledtext
import subprocess
import shutil
import sys
import os
import threading
import pathlib

GTKWAVE_PATH = None


PROJECT_FILES = [
    "alu.v",
    "regfile.v",
    "cpu_core.v",
    "instruction_memory.v",
    "data_memory.v",
    "gpio.v",
    "uart.v",
    "pwm.v",
    "uart_loader.v",
    "microrv8_system.v",
    "tang_nano_top.v",
]


def find_gtkwave():
    if GTKWAVE_PATH and pathlib.Path(GTKWAVE_PATH).exists():
        return GTKWAVE_PATH
    found = shutil.which("gtkwave")
    if found:
        return found
    for p in [r"C:\gtkwave64\bin\gtkwave.exe",
              r"C:\Program Files\GTKWave\bin\gtkwave.exe"]:
        if pathlib.Path(p).exists():
            return p
    return None


class SimGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Probador de testbenches")
        self.root.geometry("780x640")
        self.root.resizable(True, True)

        self.project_dir = tk.StringVar(value=str(pathlib.Path(__file__).parent))
        self.tb_file     = tk.StringVar()
        self.test_file   = tk.StringVar()
        self.top_module  = tk.StringVar()
        self.out_dir     = tk.StringVar(
            value=str(pathlib.Path(__file__).resolve().parent / "output"))
        self.mode        = tk.IntVar(value=1)
        self.vvp_path    = None

        self.gtkwave_exe = find_gtkwave()
        self.iverilog_ok = bool(shutil.which("iverilog"))
        try:
            import cocotb_tools.runner
            self.cocotb_ok = True
        except ImportError:
            self.cocotb_ok = False

        self._build_ui()


    def _build_ui(self):
        P = {"padx": 8, "pady": 3}

        # Directorio
        f = tk.LabelFrame(self.root, text="Directorio del proyecto")
        f.pack(fill="x", **P)
        tk.Entry(f, textvariable=self.project_dir, width=70).pack(
            side="left", padx=4, pady=4)
        tk.Button(f, text="...", command=self._pick_dir, width=3).pack(side="left")

        # Carpeta de salida
        fo = tk.LabelFrame(self.root, text="Carpeta de salida (vvp, vcd, fst, logs)")
        fo.pack(fill="x", **P)
        tk.Entry(fo, textvariable=self.out_dir, width=70).pack(
            side="left", padx=4, pady=4)
        tk.Button(fo, text="...", command=self._pick_out, width=3).pack(side="left")

        # Modo
        fm = tk.LabelFrame(self.root, text="Modo de simulacion")
        fm.pack(fill="x", **P)
        tk.Radiobutton(fm,
            text="Testbench",
            variable=self.mode, value=1,
            command=self._mode_changed).pack(anchor="w", padx=8, pady=2)
        tk.Radiobutton(fm,
            text="cocotb",
            variable=self.mode, value=2,
            command=self._mode_changed).pack(anchor="w", padx=8, pady=2)

        # Panel modo 1
        self.frm_v = tk.LabelFrame(self.root, text="Testbench .v")
        tk.Entry(self.frm_v, textvariable=self.tb_file, width=68).pack(
            side="left", padx=4, pady=4)
        tk.Button(self.frm_v, text="...", command=self._pick_tb, width=3
                  ).pack(side="left")

        # Panel modo 2
        self.frm_c = tk.LabelFrame(self.root, text="Test cocotb")
        r = tk.Frame(self.frm_c)
        r.pack(fill="x", padx=4, pady=4)
        tk.Label(r, text="Archivo .py:", width=12, anchor="w").grid(
            row=0, column=0, sticky="w")
        tk.Entry(r, textvariable=self.test_file, width=55).grid(
            row=0, column=1, padx=4)
        tk.Button(r, text="...", command=self._pick_test, width=3).grid(
            row=0, column=2)
        tk.Label(r, text="Top module:", width=12, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(4,0))
        tk.Entry(r, textvariable=self.top_module, width=30).grid(
            row=1, column=1, sticky="w", padx=4, pady=(4,0))
        tk.Label(r, text="nombre del modulo Verilog DUT",
                 fg="gray").grid(row=1, column=1, sticky="e", padx=4)

        # Herramientas
        ft = tk.LabelFrame(self.root, text="Herramientas")
        ft.pack(fill="x", **P)
        self._status(ft, "iverilog", self.iverilog_ok)
        self._status(ft, "GTKWave",  bool(self.gtkwave_exe),
                     self.gtkwave_exe or "NO — ver 01_INSTALACION.md")
        self._status(ft, "cocotb",   self.cocotb_ok,
                     "OK" if self.cocotb_ok else "NO — pip install cocotb")

        # Botoes
        fb = tk.Frame(self.root)
        fb.pack(fill="x", **P)
        self.fb = fb
        btns = [
            ("Compilar",  self._compile,   "#1565C0"),
            ("Simular",   self._simulate,  "#2E7D32"),
            ("GTKWave",   self._gtkwave,   "#E65100"),
            ("Todo",      self._run_all,   "#6A1B9A"),
            ("Limpiar",   self._clear,     "#37474F"),
        ]
        for label, cmd, color in btns:
            tk.Button(fb, text=label, command=cmd, height=2,
                      bg=color, fg="white", font=("Arial", 10, "bold"),
                      activebackground=color, relief="flat"
                      ).pack(side="left", fill="x", expand=True, padx=2)

        # Log
        fl = tk.LabelFrame(self.root, text="Log")
        fl.pack(fill="both", expand=True, **P)
        self.fl = fl
        self.log = scrolledtext.ScrolledText(
            fl, height=14, font=("Courier New", 9),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        self._mode_changed()

    def _status(self, parent, name, ok, text=None):
        t = text or ("OK" if ok else "NO ENCONTRADO")
        tk.Label(parent, text=f"  {name}: {t}",
                 fg="#2E7D32" if ok else "#B71C1C"
                 ).pack(side="left", padx=8)

    def _mode_changed(self):
        if self.mode.get() == 1:
            self.frm_c.pack_forget()
            self.frm_v.pack(fill="x", padx=8, pady=3, before=self.fl)
        else:
            self.frm_v.pack_forget()
            self.frm_c.pack(fill="x", padx=8, pady=3, before=self.fb)

    # ------------------------------------------------------------ Selectores

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.project_dir.get())
        if d:
            self.project_dir.set(d)

    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def _out(self):
        d = pathlib.Path(self.out_dir.get()).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _pick_tb(self):
        f = filedialog.askopenfilename(
            initialdir=self.project_dir.get(),
            filetypes=[("Verilog", "*.v")])
        if f:
            self.tb_file.set(f)

    def _pick_test(self):
        f = filedialog.askopenfilename(
            initialdir=self.project_dir.get(),
            filetypes=[("Python", "*.py")])
        if f:
            self.test_file.set(f)
            stem = pathlib.Path(f).stem
            if stem.startswith("test_") and not self.top_module.get():
                self.top_module.set(stem[5:])

    # ------------------------------------------------------------------ Log

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.root.update()

    def _log_safe(self, msg):
        """Loggear desde un hilo secundario."""
        self.root.after(0, self._log, msg)

    def _clear(self):
        self.log.delete("1.0", "end")

    # ---------------------------------------------------------- Archivos .v

    def _get_sources(self):
        proj = pathlib.Path(self.project_dir.get())
        out  = []
        for name in PROJECT_FILES:
            p = proj / name
            if p.exists():
                out.append(str(p))
            else:
                self._log(f"  AVISO: {name} no encontrado")
        return out

    # ------------------------------------------- Modo 1: Testbench Verilog

    def _compile(self):
        if self.mode.get() == 2:
            self._log("Modo cocotb: compilacion es automatica al simular.")
            return True
        return self._do_compile()

    def _do_compile(self):
        if not self.iverilog_ok:
            self._log("ERROR: iverilog no esta en PATH.")
            return False
        tb = self.tb_file.get()
        if not tb:
            self._log("ERROR: seleccionar un testbench .v")
            return False

        outdir = self._out()
        out  = str(outdir / "output.vvp")
        cmd  = ["iverilog", "-g2012", "-o", out] + self._get_sources() + [tb]

        self._log(f"\n[COMPILAR]\n{' '.join(cmd)}\n")
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(outdir))
        if r.stdout: self._log(r.stdout)
        if r.stderr: self._log(r.stderr)
        if r.returncode != 0:
            self._log("FAIL")
            return False
        self.vvp_path = out
        self._log(f"OK: {out}")
        return True

    def _simulate(self):
        if self.mode.get() == 2:
            return self._run_cocotb()
        return self._run_vvp()

    def _run_vvp(self):
        if not self.vvp_path or not pathlib.Path(self.vvp_path).exists():
            self._log("ERROR: compilar primero.")
            return False
        self._log(f"\n[SIMULAR]\nvvp {self.vvp_path}\n")
        r = subprocess.run(["vvp", self.vvp_path], capture_output=True, text=True,
                           cwd=str(pathlib.Path(self.vvp_path).parent))
        if r.stdout: self._log(r.stdout)
        if r.stderr: self._log(r.stderr)
        if r.returncode != 0:
            self._log("FAIL")
            return False
        self._log("OK: simulacion terminada.")
        return True

    def _gtkwave(self):
        if not self.gtkwave_exe:
            self._log(
                "ERROR: GTKWave no encontrado.\n"
                "  Windows: https://sourceforge.net/projects/gtkwave/files/\n"
                "  Linux:   sudo apt install gtkwave\n"
                "  Luego configurar GTKWAVE_PATH en sim_gui.py"
            )
            return
        outdir = self._out()
        vcds = sorted([*outdir.rglob("*.vcd"), *outdir.rglob("*.fst")],
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if not vcds:
            self._log(f"ERROR: no hay .vcd/.fst en {outdir}. Simular primero.")
            return
        vcd = vcds[0]
        self._log(f"\n[GTKWAVE] {vcd}")
        subprocess.Popen([self.gtkwave_exe, str(vcd)])

    # -------------------------------------------- Modo 2: cocotb sin Make

    def _run_cocotb(self):
        if not self.cocotb_ok:
            self._log("ERROR: cocotb no instalado.\n  pip install cocotb")
            return False
        if not self.iverilog_ok:
            self._log("ERROR: iverilog no esta en PATH.")
            return False

        test_path = pathlib.Path(self.test_file.get())
        if not test_path.exists():
            self._log("ERROR: seleccionar un archivo .py")
            return False

        top = self.top_module.get().strip()
        if not top:
            self._log("ERROR: escribir el nombre del Top Module (modulo Verilog DUT)")
            return False

        self._log(f"\n[COCOTB]\n  DUT:  {top}\n  Test: {test_path}\n")
        threading.Thread(
            target=self._cocotb_thread,
            args=(test_path, top),
            daemon=True
        ).start()
        return True

    def _cocotb_thread(self, test_path, top):
        try:
            from cocotb_tools.runner import get_runner

            test_dir = test_path.parent
            test_mod = test_path.stem
            out      = self._out()
            work     = out / "cocotb" / test_mod
            work.mkdir(parents=True, exist_ok=True)
            build_log = work / "build.log"
            sim_log   = work / "sim.log"
            xml       = work / "results.xml"

            sources = [pathlib.Path(f) for f in self._get_sources_silent()]
            for extra in test_dir.glob("*.v"):
                if extra not in sources:
                    sources.append(extra)

            env = {
                "PYTHONDONTWRITEBYTECODE": "1",
                "ZC_OUTDIR": str(out),
                "ZC_TRACE": str(out / "cocotb_trace.json"),
            }

            self._log_safe(f"\n[COCOTB] {top}  <-  {test_path.name}")
            runner = get_runner("icarus")
            runner.build(
                sources=sources,
                hdl_toplevel=top,
                build_dir=str(work),
                always=True,
                timescale=("1ns", "1ps"),
                waves=True,
                log_file=str(build_log),
            )
            try:
                runner.test(
                    hdl_toplevel=top,
                    test_module=test_mod,
                    build_dir=str(work),
                    test_dir=str(test_dir),
                    extra_env=env,
                    waves=True,
                    results_xml=str(xml),
                    log_file=str(sim_log),
                )
            except SystemExit:
                pass
            self._cocotb_report(sim_log, xml, work)

        except subprocess.CalledProcessError:
            self._log_safe("FAIL: error de compilacion")
            try:
                tail = (work / "build.log").read_text(
                    encoding="utf-8", errors="replace").strip().splitlines()[-20:]
                self._log_safe("\n".join(tail))
            except Exception:
                pass
        except Exception as e:
            self._log_safe(f"ERROR: {e}")

    def _cocotb_report(self, sim_log, xml, work):
        import re
        import xml.etree.ElementTree as ET

        pat = re.compile(
            r"^\s*(?:-\.--|[\d.]+)ns\s+(INFO|WARNING|ERROR|CRITICAL)\s+(\S+)\s+(.*)$")
        noise = ("Seeding", "Initialized cocotb", "Running on", "VPI registered",
                 "Running tests", "Unexpected sys.executable", "vpi_iterate",
                 "Using Python", "Results file")
        try:
            raw = sim_log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            raw = []

        lines, in_tb = [], False
        for ln in raw:
            m = pat.match(ln)
            if m:
                in_tb = False
                lvl, logger, msg = m.groups()
                msg = msg.strip()
                if logger.startswith("gpi") or any(n in msg for n in noise):
                    continue
                if msg.startswith("*"):
                    continue
                if logger == "cocotb.regression":
                    mm = re.match(r"running (\S+) \(\d+/\d+\)", msg)
                    if mm:
                        lines.append(f"  {mm.group(1)}")
                    elif msg.endswith(" failed"):
                        lines.append("    -> FAILED")
                        in_tb = True
                    continue
                lines.append(f"    {msg}" if lvl == "INFO" else f"    {lvl}: {msg}")
            elif in_tb and ln.strip() and not ln.lstrip().startswith("**"):
                lines.append("      " + ln.strip())

        if lines:
            self._log_safe("\n".join(lines))

        try:
            root = ET.parse(xml).getroot()
        except Exception:
            self._log_safe("FAIL: no se genero results.xml")
            if raw:
                self._log_safe("\n".join(raw[-15:]))
            return

        self._log_safe("")
        total = passed = 0
        for tc in root.iter("testcase"):
            total += 1
            name = f"{tc.get('classname', '')}.{tc.get('name', '')}".strip(".")
            bad = any(tc.find(t) is not None for t in ("failure", "error"))
            skip = tc.find("skipped") is not None
            status = "FAIL" if bad else ("SKIP" if skip else "PASS")
            if status == "PASS":
                passed += 1
            t = next((q.get("value") for q in tc.iter("property")
                      if q.get("name") == "sim_time_duration"), None)
            tt = f"  {float(t):.0f} ns" if t else ""
            self._log_safe(f"  {status}  {name}{tt}")
        verdict = "PASSED" if total and passed == total else "FAILED"
        self._log_safe(f"\n{verdict}  ({passed}/{total} tests)")
        self._log_safe(f"Salida: {work}")

    def _get_sources_silent(self):
        """Como _get_sources pero sin loggear advertencias (para usar desde hilo)."""
        proj = pathlib.Path(self.project_dir.get())
        return [str(proj / n) for n in PROJECT_FILES if (proj / n).exists()]

    def _run_all(self):
        if self.mode.get() == 1:
            if self._do_compile():
                if self._run_vvp():
                    self._gtkwave()
        else:
            self._run_cocotb()


if __name__ == "__main__":
    root = tk.Tk()
    SimGUI(root)
    root.mainloop()