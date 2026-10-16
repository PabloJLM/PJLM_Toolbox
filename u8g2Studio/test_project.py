# -*- coding: utf-8 -*-
"""Pruebas del editor de proyecto contra el firmware MeshNow real."""
import os
import sys
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ms_core as core
import ms_cparse as cp
import ms_project as mpj

FAIL = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + ("  " + str(extra) if not cond else ""))
    if not cond:
        FAIL.append(name)


# usa el sketch de muestra si existe; si no, el MeshNow de al lado
SRC = os.path.join(HERE, "_sample_sketch")
if not os.path.isdir(SRC):
    SRC = os.path.join(os.path.dirname(HERE), "MeshNow")
if not os.path.isdir(SRC):
    print("(no encontre un sketch para probar; omito)")
    sys.exit(0)
N_FILES = len([f for f in os.listdir(SRC) if f.lower().endswith(mpj.SOURCE_EXT)])


def fresh():
    d = tempfile.mkdtemp()
    for f in os.listdir(SRC):
        p = os.path.join(SRC, f)
        if os.path.isfile(p):
            shutil.copy(p, d)
    return d


print("== analisis del sketch real ==")
d = fresh()
p = mpj.Project(d)
check("lee los %d archivos" % N_FILES, len(p.files) == N_FILES, len(p.files))
check("SCREEN_W/H de config.h", (p.screen_w, p.screen_h) == (128, 64))
check("resuelve #define MESH_TTL", p.globals.get("MESH_TTL") == 6)
check("resuelve enum SCR_SCANNER", p.globals.get("SCR_SCANNER") == 5,
      p.globals.get("SCR_SCANNER"))
check("lee MENU_ITEMS", p.globals.get("MENU_ITEMS", [None])[0] == "Metricas",
      p.globals.get("MENU_ITEMS"))
check("lee MENU_COUNT", p.globals.get("MENU_COUNT") == 5)
names = [s.name for s in p.screens]
for n in ("drawMenu", "drawMetrics", "drawNeighbors", "drawPing",
          "drawScanner", "drawEaster", "header", "splash"):
    check("encuentra %s()" % n, n in names, names)
check("encuentra easter_bits", any(b[1] == "easter_bits" for b in p.bitmaps))

print("== drawMenu: interpretacion ==")
s = p.screen_by_name("drawMenu")
kinds = [e.kind for e in s.elements]
check("6 elementos", len(s.elements) == 6, kinds)
check("titulo literal", cp.as_str(s.elements[0].value("text")) == "MeshNow")
check("texto de snprintf resuelto",
      "nodos" in cp.as_str(s.elements[1].value("text")),
      cp.as_str(s.elements[1].value("text")))
right = s.elements[1]
# "0 nodos" = 7 chars * 6 px = 42  ->  x = 128 - 42 - 2 = 84
check("getStrWidth se calcula de verdad (alineado a la derecha)",
      cp.as_int(right.value("x")) == 84, cp.as_int(right.value("x")))
loop_el = [e for e in s.elements if e.repeats > 1]
check("desenrolla el for del menu", loop_el and loop_el[0].repeats == 4,
      [e.repeats for e in s.elements])
inv = [e for e in s.elements if e.color == 0]
check("detecta setDrawColor(0) del item resaltado", len(inv) == 1, len(inv))

print("== mover: literal directo ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawMenu")
e = s.elements[0]
before = p.files[e.file]
check("no hay cambios al abrir", not p.is_dirty())
check("mueve +3,+1", p.move_element(e, 3, 1))
s = p.screen_by_name("drawMenu")
line = s.elements[0].source_line(p.files[s.elements[0].file])
check("reescribio la llamada", line == 'u8g2.drawStr(5, 10, "MeshNow");', line)
check("marca el archivo como sucio", p.is_dirty(e.file))
check("solo cambio esa linea",
      sum(1 for a, b in zip(before.splitlines(), p.files[e.file].splitlines())
          if a != b) == 1)
check("mismo numero de lineas",
      len(before.splitlines()) == len(p.files[e.file].splitlines()))
check("nada escrito al disco todavia",
      open(os.path.join(d, "ui.cpp")).read() == before)

print("== mover: expresion con resta ==")
d = fresh(); p = mpj.Project(d)
e = p.screen_by_name("drawMenu").elements[1]
p.move_element(e, 3, 0)
line = p.screen_by_name("drawMenu").elements[1].source_line(p.files[e.file])
check("SCREEN_W - w - 2  ->  SCREEN_W - w + 1",
      line == "u8g2.drawStr(SCREEN_W - w + 1, 9, sub);", line)
p.move_element(p.screen_by_name("drawMenu").elements[1], -3, 0)
line = p.screen_by_name("drawMenu").elements[1].source_line(p.files[e.file])
check("y vuelve a - 2 al regresar",
      line == "u8g2.drawStr(SCREEN_W - w - 2, 9, sub);", line)

print("== mover: coordenada que sale de una variable ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawMenu")
e = [x for x in s.elements if x.repeats > 1][0]
check("y es indirecta", e.indirect("y") and e.var_name("y") == "y")
check("y no esta bloqueada", not e.locked("y"))
ys_before = [cp.as_int(e.value("y", o)) for o in e.ops]
check("mueve el grupo +2", p.move_element(e, 0, 2))
s = p.screen_by_name("drawMenu")
e = [x for x in s.elements if x.repeats > 1][0]
ys_after = [cp.as_int(e.value("y", o)) for o in e.ops]
check("las 4 filas bajaron 2", [a + 2 for a in ys_before] == ys_after,
      (ys_before, ys_after))
txt = p.files[e.file]
check("edito la asignacion, no la llamada", "int y = 26 + i * 10;" in txt)
check("la llamada quedo intacta", "u8g2.drawStr(6, y, MENU_ITEMS[i]);" in txt)
check("la barra resaltada siguio a la variable",
      "u8g2.drawBox(0, y - 8, 128, 10);" in txt)

print("== argumentos sin literal = bloqueados ==")
d = fresh(); p = mpj.Project(d)
sc = p.screen_by_name("drawScanner")
locked_any = [e for e in sc.elements if e.locked("x") or e.locked("y")]
check("drawScanner tiene elementos evaluados", len(sc.elements) >= 3, len(sc.elements))
fake = {"type": "id"}
check("locked() no revienta", isinstance(sc.elements[0].locked("x"), bool))

print("== elemento heredado de header() ==")
d = fresh(); p = mpj.Project(d)
m = p.screen_by_name("drawMetrics")
foreign = [e for e in m.elements
           if not (m.fn["body_start"] <= e.site <= m.fn["body_end"])]
check("drawMetrics hereda 3 elementos de header()", len(foreign) == 3, len(foreign))
check("header sigue viviendo en ui.cpp", all(e.file.endswith("ui.cpp") for e in foreign))
p.move_element(foreign[0], 1, 0)
check("mover el header cambia header()", "u8g2.drawStr(3, 9, title);" in p.files[m.file],
      [l for l in p.files[m.file].splitlines() if "drawStr" in l and "title" in l])
n = p.screen_by_name("drawNeighbors")
nf = [e for e in n.elements if cp.as_str(e.value("text")) == ""] or n.elements
check("y se ve tambien en drawNeighbors",
      cp.as_int(n.elements[0].value("x")) == 3, cp.as_int(n.elements[0].value("x")))

print("== editar texto ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawMenu")
check("literal editable", s.elements[0].is_literal_text())
p.set_arg(s.elements[0], "text", "MallaESP")
check("cambio el literal", 'u8g2.drawStr(2, 9, "MallaESP");' in p.files[s.elements[0].file])
s = p.screen_by_name("drawMenu")
p.set_arg(s.elements[1], "text", "%d vivos")
check("cambio la cadena de snprintf",
      'snprintf(sub, sizeof(sub), "%d vivos", meshNodeCount());' in p.files[s.file])
check("y el render lo refleja",
      "vivos" in cp.as_str(p.screen_by_name("drawMenu").elements[1].value("text")))

print("== agregar / duplicar / borrar ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawPing")
n0 = len(s.elements)
p.add_element(s, "frame", 4, 20)
p.analyze()
s = p.screen_by_name("drawPing")
check("agrega un marco", len(s.elements) == n0 + 1, (n0, len(s.elements)))
check("la llamada es valida", "u8g2.drawFrame(4, 20," in p.files[s.file])
last = s.elements[-1]
p.duplicate_element(last)
s = p.screen_by_name("drawPing")
check("duplica", len(s.elements) == n0 + 2, len(s.elements))
p.delete_element(s.elements[-1])
p.delete_element(p.screen_by_name("drawPing").elements[-1])
s = p.screen_by_name("drawPing")
check("borra las dos", len(s.elements) == n0, len(s.elements))
check("drawFrame ya no esta", "u8g2.drawFrame(4, 20," not in p.files[s.file])

print("== elementos obsoletos no corrompen el archivo ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawMetrics")
stale = list(s.elements)
p.move_element(stale[0], 1, 0)
before = p.files[os.path.join(d, "ui.cpp")]
ok2 = p.move_element(stale[1], 1, 0)      # este ya caduco
check("rechaza el elemento viejo", ok2 is False)
check("y no toca el archivo", p.files[os.path.join(d, "ui.cpp")] == before)
check("explica por que", "obsoleto" in p.last_error, p.last_error)
s2 = p.screen_by_name("drawMetrics")
check("tomandolo de nuevo si funciona", p.move_element(s2.elements[1], 1, 0))
check("no se perdieron elementos",
      len(p.screen_by_name("drawMetrics").elements) == len(stale),
      len(p.screen_by_name("drawMetrics").elements))

print("== deshacer / rehacer sobre el texto ==")
d = fresh(); p = mpj.Project(d)
orig = p.files[os.path.join(d, "ui.cpp")]
s = p.screen_by_name("drawMenu")
p.move_element(s.elements[0], 5, 0)
check("cambio aplicado", p.files[os.path.join(d, "ui.cpp")] != orig)
p.undo()
check("undo restaura el texto exacto", p.files[os.path.join(d, "ui.cpp")] == orig)
check("undo limpia el estado sucio", not p.is_dirty())
p.redo()
check("redo lo vuelve a aplicar", p.files[os.path.join(d, "ui.cpp")] != orig)

print("== guardar ==")
d = fresh(); p = mpj.Project(d)
s = p.screen_by_name("drawMenu")
p.move_element(s.elements[0], 4, 0)
check("hay 1 archivo sucio", len(p.dirty_files()) == 1, p.dirty_files())
written = p.save()
check("escribio 1 archivo", len(written) == 1)
check("el disco tiene el cambio",
      'drawStr(6, 9, "MeshNow")' in open(os.path.join(d, "ui.cpp")).read())
check("ya no hay nada sucio", not p.is_dirty())
check("NO se creo ningun .bak",
      not any(f.endswith(".bak") for f in os.listdir(d)), os.listdir(d))
check("los demas archivos no se tocaron",
      open(os.path.join(d, "config.h")).read() ==
      open(os.path.join(SRC, "config.h")).read())

print("== el archivo sigue compilando (misma estructura) ==")
d = fresh(); p = mpj.Project(d)
before = p.files[os.path.join(d, "ui.cpp")]
for i in range(len(p.screen_by_name("drawMetrics").elements)):
    e = p.screen_by_name("drawMetrics").elements[i]   # siempre fresco
    p.move_element(e, 1, 1)
after = p.files[os.path.join(d, "ui.cpp")]
check("mismo numero de lineas",
      len(before.splitlines()) == len(after.splitlines()))
check("mismo numero de llaves",
      before.count("{") == after.count("{") and before.count("}") == after.count("}"))
check("mismo numero de ;", before.count(";") == after.count(";"))
check("comentarios intactos",
      before.count("//") == after.count("//"))
check("sigue analizandose igual", len(mpj.Project(d).screens) == len(p.screens),
      (len(mpj.Project(d).screens), len(p.screens)))

print("== bitmap dentro del proyecto ==")
d = fresh(); p = mpj.Project(d)
bm, nframes = p.load_bitmap(os.path.join(d, "easteregg.h"), "easter_bits")
check("carga 128x64", (bm.width, bm.height) == (128, 64))
before_h = p.files[os.path.join(d, "easteregg.h")]
bm.invert()
p.save_bitmap(os.path.join(d, "easteregg.h"), "easter_bits", bm)
bm2, _ = p.load_bitmap(os.path.join(d, "easteregg.h"), "easter_bits")
check("round-trip del bitmap invertido", bm2.data == bm.data)
after_h = p.files[os.path.join(d, "easteregg.h")]
check("cabecera del .h preservada",
      after_h.startswith("#pragma once") and "image2cpp" in after_h)
check("defines preservados", "#define EASTER_W 128" in after_h)
p.save()
check("sin .bak tampoco aqui",
      not any(f.endswith(".bak") for f in os.listdir(d)), os.listdir(d))
check("drawEaster lo sigue viendo",
      p.screen_by_name("drawEaster").elements[0].kind == "xbm")

print("== render ==")
import ms_designer as des
d = fresh(); p = mpj.Project(d)
art = {}
b, _ = p.load_bitmap(os.path.join(d, "easteregg.h"), "easter_bits")
art["easter_bits"] = b
img = des.render_ops(p.screen_by_name("drawMenu").ops, 128, 64, art)
on = sum(img.get(x, y) for y in range(64) for x in range(128))
check("drawMenu dibuja algo", on > 400, on)
img2 = des.render_ops(p.screen_by_name("drawEaster").ops, 128, 64, art)
check("drawEaster usa el arte real de easteregg.h", img2.data == b.data)
bb = des.element_bounds(p.screen_by_name("drawMenu").elements[0])
check("bounds del titulo", (bb.x(), bb.width()) == (2, 42), (bb.x(), bb.width()))

print("== GUI ==")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap
app = QApplication([])
import meshnow_studio as studio
d = fresh()
w = studio.MainWindow(d)
check("abre sin marcar sucio", "*" not in w.windowTitle(), w.windowTitle())
check("arbol poblado", w.designer.tree.topLevelItemCount() >= 2,
      w.designer.tree.topLevelItemCount())
w.designer.select_screen("drawMenu")
check("selecciona pantalla", w.designer.canvas.screen.name == "drawMenu")
w.designer.canvas.selected = 0
w.designer.on_select(0)
check("panel de propiedades", w.designer.props.count() > 0)
w.designer.canvas.project.move_element(w.designer.canvas.current(), 2, 0)
w.designer.canvas.refresh(keep=0)
w.update_title()
check("ahora si marca sucio", "*" in w.windowTitle(), w.windowTitle())
pm = QPixmap(w.designer.canvas.size())
w.designer.canvas.render(pm)
check("el lienzo repinta", not pm.isNull())
w.tabs.setCurrentIndex(1)
check("la pestana de pixel art lista bitmaps", w.editor.cb_bitmap.count() > 0,
      w.editor.cb_bitmap.count())
w.project.save()
w.update_title()
check("guardar limpia el titulo", "*" not in w.windowTitle(), w.windowTitle())
check("sin .bak al final", not any(f.endswith(".bak") for f in os.listdir(d)))

print()
if FAIL:
    print("FALLARON %d: %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("TODO OK")
