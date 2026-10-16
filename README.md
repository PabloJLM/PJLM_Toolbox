# PJLM Toolbox

Herramientas de escritorio que uso para desarrollo de sistemas embebidos y FPGA 

Cada herramienta tiene su propia carpeta y se
ejecuta por separado.

| Herramienta | Para que sirve | Interfaz | Sistema |
|---|---|---|---|
| [Platformio_IDE](#platformio_ide--jojop-pio) | IDE liviano sobre PlatformIO Core (compilar, subir, monitor serie, terminal) | PyQt5 | Windows (con WSL) y Linux |
| [FPGA_IDE](#fpga_ide--jojop-ide) | IDE de ensamblador para el microcontrolador Zenith-Core y probador de testbenches | PyQt5 / Tkinter | Windows y Linux |
| [u8g2Studio](#u8g2studio) | Editor visual que edita directamente el codigo de pantallas u8g2 / U8x8 / Adafruit_GFX (sin generar codigo nuevo para pegar) | PyQt5 | Windows y Linux |
| [Flasher_ESP32](#flasher_esp32) | Grabar binarios en ESP32 con esptool | Tkinter | Windows y Linux |
| [Flasher_PY32](#flasher_py32) | Grabar y verificar microcontroladores PY32 (Puya) con ST-Link | Tkinter | Linux |

Requisito comun: Python 3.10 o superior.

---

## Platformio_IDE — JoJoP PIO

IDE con aspecto parecido a Arduino IDE que usa PlatformIO Core por debajo. En Windows
compila y sube a traves de WSL y pasa la placa con usbipd-win; en Linux llama a `pio`
directamente.

- Verificar, subir, subir sistema de archivos, limpiar, borrar flash, librerias.
- Editor con resaltado C/C++, INI y Python, buscar/reemplazar y saltar a errores.
- Monitor serie con reconexion automatica (se cierra solo al subir y se vuelve a abrir).
- Terminal integrada (PowerShell / bash) y pestana USB con usbipd.
- Temas en `temas.json` e imagen de fondo opcional.

```bash
pip install PyQt5
cd Platformio_IDE
python jojop_pio.py            # o: python jojop_pio.py ruta/al/proyecto
```

Necesita PlatformIO Core instalado (en Windows, dentro de WSL) y, en Windows,
[usbipd-win](https://github.com/dorssel/usbipd-win) para usar la placa desde WSL.
Las imagenes de la pestana Descanso van en `imgs/descanso/` (no se suben al repo).

## FPGA_IDE — JoJoP IDE

IDE de ensamblador para Zenith-Core, un microcontrolador de 8 bits inspirado en
RISC-V escrito en Verilog para la Tang Nano 9K.

- `JoJoP_IDE.py`: editor con resaltado, ejemplos (`ejemplos.json`), temas
  (`temas.json`) y mascotas (`mascotas.json`). Ensambla a `.bin` y graba por UART.
  Las rutas del ensamblador (`assembler.py`) y del grabador (`uart_flash.py`) se
  configuran en la pestana Ajustes.
- `sim_gui.py`: probador de testbenches con Icarus Verilog y GTKWave.

```bash
pip install PyQt5 pyserial
cd FPGA_IDE
python JoJoP_IDE.py
python sim_gui.py              # requiere iverilog en el PATH; gtkwave opcional
```

## u8g2Studio

Editor visual para pantallas monocromaticas (u8g2 / U8x8 / Adafruit_GFX) que
edita directamente el codigo que ya tienes en vez de generar codigo nuevo
para copiar: abre la carpeta del sketch, interpreta las funciones que dibujan
y al mover un elemento reescribe el numero exacto dentro de la llamada.

- Pestana de pantallas (arrastrar/redimensionar, panel de propiedades por
  elemento) y pestana de pixel art (editor 1-bit para los arreglos de bytes
  del proyecto, con import de PNG/JPG).
- Sigue variables hasta su declaracion, desenrolla bucles con limite
  resoluble y respeta expresiones (`SCREEN_W - w - 2`, etc.), volteando el
  operador si el valor cruza el cero.
- No crea archivo de proyecto ni `.bak`: nada toca el disco hasta `Ctrl+S`,
  que parchea el texto original.

```bash
pip install PyQt5 Pillow        # Pillow es opcional, solo para importar imagenes
cd u8g2Studio
python u8g2_studio.py            # o: python u8g2_studio.py ruta/al/sketch
```

Mas detalle (atajos, estructura interna, que no hace) en
[u8g2Studio/README.md](u8g2Studio/README.md).

## Flasher_ESP32

Interfaz para `esptool`: elige chip, puerto y velocidad, y graba uno o varios
binarios con su direccion. Incluye presets para proyectos Arduino
(bootloader, particiones, boot_app0, firmware) y binario unico, y un boton para
borrar la flash.

```bash
pip install pyserial esptool
cd Flasher_ESP32
python flasher_esp32.py
```

## Flasher_PY32

Graba microcontroladores PY32 (Puya) desde un `.hex` (por ejemplo, exportado por
Keil) usando un ST-Link V2 por SWD: lee el `.hex`, borra, escribe, verifica byte
por byte y reinicia el chip. No depende de librerias externas.

Requisitos (solo Linux):

- Tkinter: `sudo apt install python3-tk`
- OpenOCD parcheado para PY32 compilado en `~/openocd-for-py32f0xx`
  (se cambia en la constante `OCD_DIR` al inicio del script).
- ST-Link V2 cableado al PY32: SWDIO, SWCLK, GND y 3.3 V.

OpenOCD se ejecuta con `sudo`. La contraseña se toma de la variable de entorno
`PY32_SUDO_PASSWORD` o, si no existe, el programa la pide una vez y la guarda solo
en memoria. Nunca se escribe en ningun archivo.

```bash
cd Flasher_PY32
python3 flasher_py32.py
```

---

Pablo Jose Lopez Mazariegos · Guatemala, 2026 · [github.com/PabloJLM](https://github.com/PabloJLM)
