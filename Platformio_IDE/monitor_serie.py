"""Puente serie minimo para el monitor del IDE.

Corre del lado donde esta el puerto (WSL, Linux o Windows) con el Python de
PlatformIO, que ya trae pyserial:  python monitor_serie.py <puerto> <baudios>

puerto -> stdout (bytes crudos)
stdin  -> puerto
stderr -> mensajes de estado
Si el puerto desaparece (la placa se reinicia o se reconecta) espera y vuelve
a abrirlo. Termina cuando se cierra stdin.
"""
import os
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.stderr.write("pyserial no esta instalado (pip install pyserial)\n")
    sys.exit(2)


def estado(msj):
    sys.stderr.write(msj + "\n")
    sys.stderr.flush()


def main():
    puerto, baudios = sys.argv[1], int(sys.argv[2])
    salir = threading.Event()
    candado = threading.Lock()
    actual = {"ser": None}

    def entrada():
        while True:
            try:
                datos = os.read(0, 4096)
            except OSError:
                datos = b""
            if not datos:
                salir.set()
                return
            with candado:
                s = actual["ser"]
                if s is not None:
                    try:
                        s.write(datos)
                    except (serial.SerialException, OSError):
                        pass

    threading.Thread(target=entrada, daemon=True).start()
    out = sys.stdout.buffer
    avisado = False
    while not salir.is_set():
        s = serial.Serial()
        s.port = puerto
        s.baudrate = baudios
        s.timeout = 0.05
        s.dtr = False   # no reiniciar la placa al abrir el puerto
        s.rts = False
        try:
            s.open()
        except (serial.SerialException, OSError, ValueError):
            if not avisado:
                estado(f"esperando {puerto} ...")
                avisado = True
            time.sleep(0.5)
            continue
        with candado:
            actual["ser"] = s
        estado(f"conectado a {puerto} @ {baudios}")
        avisado = False
        try:
            while not salir.is_set():
                datos = s.read(s.in_waiting or 1)
                if datos:
                    out.write(datos)
                    out.flush()
        except (serial.SerialException, OSError):
            estado(f"{puerto} desconectado, esperando ...")
            avisado = True
        finally:
            with candado:
                actual["ser"] = None
            try:
                s.close()
            except Exception:
                pass
    estado("monitor cerrado")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
