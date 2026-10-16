#!/usr/bin/env python3
"""
Generador universal de paletas / temas con GUI.

- Entrada: 2 a 5 colores semilla.
- Salida: 3 a 10 roles configurables.
- Export: C++ (rgb565), JSON, CSS variables, Hex list.
"""

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import colorsys
import json


# ---------- utilidades de color ----------

def hex_a_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_a_hex(rgb):
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_a_hsl(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s * 100.0, l * 100.0


def hsl_a_rgb(h, s, l):
    h = (h % 360) / 360.0
    s = max(0, min(100, s)) / 100.0
    l = max(0, min(100, l)) / 100.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (r * 255, g * 255, b * 255)


def rgb_a_rgb565(rgb):
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def mix(rgb1, rgb2, t):
    return tuple(a + (b - a) * t for a, b in zip(rgb1, rgb2))


def ajustar_l(rgb, delta):
    h, s, l = rgb_a_hsl(rgb)
    return hsl_a_rgb(h, s, max(0, min(100, l + delta)))


def ajustar_hsl(rgb, dh=0, ds=0, dl=0):
    h, s, l = rgb_a_hsl(rgb)
    return hsl_a_rgb(h + dh, max(0, min(100, s + ds)), max(0, min(100, l + dl)))


def contraste(rgb1, rgb2):
    def lum(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    L1 = 0.2126*lum(rgb1[0]) + 0.7152*lum(rgb1[1]) + 0.0722*lum(rgb1[2])
    L2 = 0.2126*lum(rgb2[0]) + 0.7152*lum(rgb2[1]) + 0.0722*lum(rgb2[2])
    return (max(L1, L2) + 0.05) / (min(L1, L2) + 0.05)


def mejor_texto_sobre(rgb):
    oscuro = (18, 12, 24)
    claro  = (245, 240, 230)
    return oscuro if contraste(rgb, oscuro) >= contraste(rgb, claro) else claro


# ---------- catálogo de roles ----------

def _sup_delta(ctx, mult):
    d = ctx["superficie_delta"] * mult
    return -d if ctx["modo_claro"] else d


ROLES_CATALOGO = {
    "background":   {"label": "background",   "gen": lambda c: c["fondo"],           "core": True},
    "surface":      {"label": "surface",      "gen": lambda c: ajustar_l(c["fondo"], _sup_delta(c, 1)), "core": True},
    "surfaceAlt":   {"label": "surfaceAlt",   "gen": lambda c: ajustar_l(c["fondo"], _sup_delta(c, 2)), "core": True},
    "border":       {"label": "border",       "gen": lambda c: mix(ajustar_l(c["fondo"], _sup_delta(c, 2)), c["primario"], 0.45)},
    "primary":      {"label": "primary",      "gen": lambda c: c["primario"],        "core": True},
    "accent":       {"label": "accent",       "gen": lambda c: c["acento"],          "core": True},
    "accentAlt":    {"label": "accentAlt",    "gen": lambda c: c["acentoAlt"] or ajustar_hsl(c["acento"], dh=-35, ds=-25)},
    "text":         {"label": "text",         "gen": lambda c: c["texto"],           "core": True},
    "textMuted":    {"label": "textMuted",    "gen": lambda c: mix(c["texto"], c["fondo"], 0.45), "core": True},
    "textOnAccent": {"label": "textOnAccent", "gen": lambda c: mejor_texto_sobre(c["acento"]), "core": True},
    "textOnPrimary":{"label": "textOnPrimary","gen": lambda c: mejor_texto_sobre(c["primario"])},
    "success":      {"label": "success",      "gen": lambda c: hsl_a_rgb(140, 55, 45)},
    "warning":      {"label": "warning",      "gen": lambda c: hsl_a_rgb(38, 85, 55)},
    "danger":       {"label": "danger",       "gen": lambda c: hsl_a_rgb(0, 70, 50)},
    "info":         {"label": "info",         "gen": lambda c: hsl_a_rgb(205, 70, 55)},
    "shadow":       {"label": "shadow",       "gen": lambda c: mix(c["fondo"], (0, 0, 0), 0.6)},
    "overlay":      {"label": "overlay",      "gen": lambda c: mix(c["fondo"], c["texto"], 0.08)},
    "link":         {"label": "link",         "gen": lambda c: ajustar_hsl(c["primario"], ds=15, dl=10)},
}

ROLES_DEFAULT = ["background", "surface", "surfaceAlt", "border",
                 "primary", "accent", "accentAlt",
                 "text", "textMuted", "textOnAccent"]


# ---------- análisis de semillas ----------

def analizar_semillas(colores):
    info = [{"rgb": c, "h": rgb_a_hsl(c)[0], "s": rgb_a_hsl(c)[1], "l": rgb_a_hsl(c)[2]}
            for c in colores]

    por_l = sorted(info, key=lambda x: x["l"])
    fondo = por_l[0]["rgb"]
    texto = por_l[-1]["rgb"]

    medios = por_l[1:-1] if len(por_l) > 2 else por_l

    if medios:
        acento_cand = max(medios, key=lambda x: x["s"])
        acento = acento_cand["rgb"]
        otros = [m for m in medios if m is not acento_cand]
    else:
        acento = info[0]["rgb"]
        otros = []

    if otros:
        primario = max(otros, key=lambda x: x["s"])["rgb"]
        acento_alt = otros[0]["rgb"] if len(otros) > 1 else None
    else:
        h, s, l = rgb_a_hsl(acento)
        primario = hsl_a_rgb(h + 180, min(80, s), max(25, l * 0.8))
        acento_alt = None

    return {"fondo": fondo, "primario": primario, "acento": acento,
            "acentoAlt": acento_alt, "texto": texto}


def derivar_tema(semillas, roles_salida, nombre="Custom",
                 modo_claro=False, superficie_delta=7.0):
    base = analizar_semillas(semillas)

    fondo, texto = base["fondo"], base["texto"]
    if modo_claro:
        fondo, texto = texto, fondo
    if contraste(fondo, texto) < 4.5:
        h, s, l = rgb_a_hsl(texto)
        delta = 10 if not modo_claro else -10
        texto = hsl_a_rgb(h, s, max(2, min(98, l + delta)))

    ctx = {
        "fondo": fondo, "texto": texto,
        "primario": base["primario"], "acento": base["acento"],
        "acentoAlt": base["acentoAlt"],
        "modo_claro": modo_claro,
        "superficie_delta": superficie_delta,
        "roles": {},
    }

    resultado = {}
    orden = [r for r in roles_salida if ROLES_CATALOGO.get(r, {}).get("core")] + \
            [r for r in roles_salida if not ROLES_CATALOGO.get(r, {}).get("core")]

    for rol in orden:
        if rol in resultado:
            continue
        gen = ROLES_CATALOGO.get(rol, {}).get("gen")
        rgb = gen(ctx) if gen else (128, 128, 128)
        resultado[rol] = rgb
        ctx["roles"][rol] = rgb

    return {"nombre": nombre, "roles": resultado}


# ---------- exportadores ----------

def exp_cpp(tema):
    lineas = ["  {"]
    lineas.append(f'    /* nombre           */ "{tema["nombre"]}",')
    for rol, rgb in tema["roles"].items():
        r, g, b = (int(round(c)) for c in rgb)
        v565 = rgb_a_rgb565(rgb)
        lineas.append(f"    /* {rol:<16} */ rgb565({r:3d}, {g:3d}, {b:3d}),   // {rgb_a_hex(rgb)}  ->  0x{v565:04X}")
    lineas.append("  },")
    return "\n".join(lineas)


def exp_json(tema):
    data = {
        "nombre": tema["nombre"],
        "colores": {rol: rgb_a_hex(rgb) for rol, rgb in tema["roles"].items()},
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def exp_css(tema):
    lineas = [":root {"]
    for rol, rgb in tema["roles"].items():
        lineas.append(f"  --{rol}: {rgb_a_hex(rgb)};")
    lineas.append("}")
    return "\n".join(lineas)


def exp_hex(tema):
    lineas = [f"# Tema: {tema['nombre']}"]
    for rol, rgb in tema["roles"].items():
        lineas.append(f"{rol}: {rgb_a_hex(rgb)}")
    return "\n".join(lineas)


EXPORTADORES = {
    "C++ (RGB565)": exp_cpp,
    "JSON":         exp_json,
    "CSS":          exp_css,
    "Hex list":     exp_hex,
}

EXTENSIONES = {
    "C++ (RGB565)": ".h",
    "JSON":         ".json",
    "CSS":          ".css",
    "Hex list":     ".txt",
}


# ---------- GUI ----------

PRESETS = {
    "Afton":     ["#6D28A8", "#C9A227", "#F3E9D8"],
    "Bosque":    ["#2E7D5B", "#E8B84B", "#E6F0E9"],
    "Cyberpunk": ["#7B2CBF", "#FF2E97", "#F0E6FF"],
    "Café":      ["#8B5E34", "#D4A574", "#F0E2CE"],
    "Océano":    ["#0A2540", "#2EC4B6", "#E0FBFC"],
    "Minimal":   ["#111111", "#FFFFFF"],
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador universal de temas")
        self.geometry("1280x800")
        self.configure(bg="#1e1e1e")

        self.semillas = ["#6D28A8", "#C9A227", "#F3E9D8"]
        self.roles_activos = list(ROLES_DEFAULT)
        self.tema = None

        self._build_ui()
        self._render_semillas()
        self._render_roles()
        self._recalcular()

    # ---------- UI ----------

    def _build_ui(self):
        left = tk.Frame(self, bg="#252526", width=340)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="Generador universal de temas", bg="#252526", fg="#e0e0e0",
                 font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))
        tk.Label(left, text="2-5 colores entrada · 3-10 roles salida",
                 bg="#252526", fg="#888", font=("Segoe UI", 9)).pack()

        # Nombre + preset
        f = tk.Frame(left, bg="#252526"); f.pack(fill="x", padx=15, pady=(15, 5))
        tk.Label(f, text="Nombre:", bg="#252526", fg="#ccc").pack(side="left")
        self.var_nombre = tk.StringVar(value="Custom")
        tk.Entry(f, textvariable=self.var_nombre, bg="#3c3c3c", fg="#eee",
                 insertbackground="#eee", relief="flat", width=16).pack(side="left", padx=5)

        f = tk.Frame(left, bg="#252526"); f.pack(fill="x", padx=15, pady=5)
        tk.Label(f, text="Preset:", bg="#252526", fg="#ccc").pack(side="left")
        self.combo_preset = ttk.Combobox(f, values=list(PRESETS.keys()),
                                         state="readonly", width=14)
        self.combo_preset.pack(side="left", padx=5)
        self.combo_preset.bind("<<ComboboxSelected>>", self._on_preset)

        # Semillas
        tk.Label(left, text="Colores semilla (2-5):", bg="#252526", fg="#ccc",
                 anchor="w").pack(fill="x", padx=15, pady=(12, 3))
        self.f_semillas = tk.Frame(left, bg="#252526")
        self.f_semillas.pack(fill="x", padx=15)

        f = tk.Frame(left, bg="#252526"); f.pack(fill="x", padx=15, pady=6)
        tk.Button(f, text="+ Añadir", command=self._add_semilla,
                  bg="#3c3c3c", fg="#eee", relief="flat",
                  activebackground="#505050").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(f, text="– Quitar", command=self._remove_semilla,
                  bg="#3c3c3c", fg="#eee", relief="flat",
                  activebackground="#505050").pack(side="left", expand=True, fill="x", padx=2)

        # Roles
        tk.Label(left, text="Roles de salida (3-10):", bg="#252526", fg="#ccc",
                 anchor="w").pack(fill="x", padx=15, pady=(12, 3))

        f_roles = tk.Frame(left, bg="#252526")
        f_roles.pack(fill="x", padx=15)

        self.canvas = tk.Canvas(f_roles, bg="#252526", highlightthickness=0, height=180)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(f_roles, command=self.canvas.yview)
        sb.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=sb.set)

        self.f_checks = tk.Frame(self.canvas, bg="#252526")
        self.canvas.create_window((0, 0), window=self.f_checks, anchor="nw")
        self.f_checks.bind("<Configure>",
                           lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Ajustes
        f = tk.Frame(left, bg="#252526"); f.pack(fill="x", padx=15, pady=(12, 3))
        self.var_claro = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Modo claro", variable=self.var_claro,
                       bg="#252526", fg="#ccc", selectcolor="#3c3c3c",
                       activebackground="#252526", activeforeground="#eee",
                       command=self._recalcular).pack(anchor="w")

        f = tk.Frame(left, bg="#252526"); f.pack(fill="x", padx=15, pady=3)
        tk.Label(f, text="Δ luminosidad superficies:", bg="#252526", fg="#ccc").pack(side="left")
        self.var_delta = tk.DoubleVar(value=7.0)
        tk.Spinbox(f, from_=3, to=20, increment=1, textvariable=self.var_delta,
                   width=4, bg="#3c3c3c", fg="#eee", relief="flat",
                   command=self._recalcular).pack(side="left", padx=5)

        # Export
        tk.Label(left, text="Formato de export:", bg="#252526", fg="#ccc",
                 anchor="w").pack(fill="x", padx=15, pady=(15, 3))
        self.var_formato = tk.StringVar(value="C++ (RGB565)")
        combo_fmt = ttk.Combobox(left, textvariable=self.var_formato,
                                 values=list(EXPORTADORES.keys()), state="readonly")
        combo_fmt.pack(fill="x", padx=15)
        combo_fmt.bind("<<ComboboxSelected>>", lambda e: self._actualizar_salida())

        tk.Button(left, text="📋 Copiar salida", command=self._copiar_salida,
                  bg="#0e639c", fg="#fff", relief="flat",
                  activebackground="#1177bb").pack(fill="x", padx=15, pady=(10, 4))
        tk.Button(left, text="💾 Guardar...", command=self._guardar_archivo,
                  bg="#3c3c3c", fg="#eee", relief="flat",
                  activebackground="#505050").pack(fill="x", padx=15, pady=(0, 15))

        # Panel derecho
        right = tk.Frame(self, bg="#1e1e1e")
        right.pack(side="right", fill="both", expand=True)

        self.mockup = tk.Frame(right, bg="#000")
        self.mockup.pack(fill="both", expand=True, padx=20, pady=20)
        self._build_mockup()

        self.f_swatches = tk.Frame(right, bg="#1e1e1e")
        self.f_swatches.pack(fill="x", padx=20, pady=(0, 8))

        f_out = tk.Frame(right, bg="#1e1e1e")
        f_out.pack(fill="x", padx=20, pady=(0, 20))
        tk.Label(f_out, text="Salida:", bg="#1e1e1e", fg="#aaa",
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        self.txt_out = tk.Text(f_out, height=6, bg="#111", fg="#c8e6c9",
                               insertbackground="#eee", relief="flat",
                               font=("Consolas", 9), wrap="none")
        self.txt_out.pack(fill="both", expand=True)

    def _build_mockup(self):
        self.hdr = tk.Frame(self.mockup, height=60)
        self.hdr.pack(fill="x"); self.hdr.pack_propagate(False)

        self.lbl_titulo = tk.Label(self.hdr, text="Preview", font=("Segoe UI", 16, "bold"))
        self.lbl_titulo.pack(side="left", padx=15)
        self.lbl_badge = tk.Label(self.hdr, text=" NUEVO ", font=("Segoe UI", 8, "bold"))
        self.lbl_badge.pack(side="left", padx=5)
        self.lbl_hora = tk.Label(self.hdr, text="12:34", font=("Segoe UI", 11))
        self.lbl_hora.pack(side="right", padx=15)

        self.body = tk.Frame(self.mockup)
        self.body.pack(fill="both", expand=True, padx=15, pady=15)

        self.card = tk.Frame(self.body)
        self.card.pack(fill="x", pady=(0, 12))

        self.lbl_card_t = tk.Label(self.card, text="Panel principal",
                                   font=("Segoe UI", 12, "bold"), anchor="w")
        self.lbl_card_t.pack(fill="x", padx=12, pady=(12, 3))

        self.lbl_card_d = tk.Label(self.card, text="Texto secundario de ejemplo",
                                   font=("Segoe UI", 9), anchor="w")
        self.lbl_card_d.pack(fill="x", padx=12, pady=(0, 10))

        f_btn = tk.Frame(self.card); f_btn.pack(fill="x", padx=12, pady=(0, 12))
        self.btn_primario = tk.Label(f_btn, text="  Acción  ", font=("Segoe UI", 10, "bold"))
        self.btn_primario.pack(side="left", padx=(0, 8))
        self.btn_acento = tk.Label(f_btn, text="  Destacar  ", font=("Segoe UI", 10, "bold"))
        self.btn_acento.pack(side="left", padx=(0, 8))
        self.btn_alt = tk.Label(f_btn, text="  Alt  ", font=("Segoe UI", 10, "bold"))
        self.btn_alt.pack(side="left")

        self.lista = tk.Frame(self.body); self.lista.pack(fill="both", expand=True)
        for txt in ["Elemento uno", "Elemento dos", "Elemento tres"]:
            row = tk.Frame(self.lista, height=38)
            row.pack(fill="x", pady=2); row.pack_propagate(False)
            tk.Label(row, text="●", font=("Segoe UI", 12)).pack(side="left", padx=10)
            tk.Label(row, text=txt, font=("Segoe UI", 10),
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text="›", font=("Segoe UI", 14)).pack(side="right", padx=12)

    # ---------- render dinámico ----------

    def _render_semillas(self):
        for w in self.f_semillas.winfo_children():
            w.destroy()
        for i, c in enumerate(self.semillas):
            row = tk.Frame(self.f_semillas, bg="#252526"); row.pack(fill="x", pady=2)
            sw = tk.Label(row, bg=c, width=3, cursor="hand2"); sw.pack(side="left", padx=(0, 8), ipady=6)
            sw.bind("<Button-1>", lambda e, idx=i: self._pick_color(idx))
            tk.Label(row, text=c, bg="#252526", fg="#ddd", font=("Consolas", 9),
                     anchor="w").pack(side="left", fill="x", expand=True)

    def _render_roles(self):
        for w in self.f_checks.winfo_children():
            w.destroy()
        self.role_vars = {}
        for rol in ROLES_CATALOGO:
            var = tk.BooleanVar(value=(rol in self.roles_activos))
            self.role_vars[rol] = var
            cb = tk.Checkbutton(self.f_checks, text=ROLES_CATALOGO[rol]["label"],
                                variable=var, bg="#252526", fg="#ccc",
                                selectcolor="#3c3c3c", activebackground="#252526",
                                activeforeground="#eee", anchor="w",
                                command=self._on_role_toggle)
            cb.pack(fill="x")

    # ---------- eventos ----------

    def _on_preset(self, _evt):
        n = self.combo_preset.get()
        if n in PRESETS:
            self.semillas = list(PRESETS[n])
            self.var_nombre.set(n)
            self._render_semillas()
            self._recalcular()

    def _on_role_toggle(self):
        activos = [r for r, v in self.role_vars.items() if v.get()]
        if len(activos) < 3:
            messagebox.showinfo("Mínimo", "Selecciona al menos 3 roles.")
            return
        if len(activos) > 10:
            messagebox.showinfo("Máximo", "Máximo 10 roles.")
            return
        self.roles_activos = activos
        self._recalcular()

    def _pick_color(self, idx):
        rgb, _ = colorchooser.askcolor(color=self.semillas[idx], title="Elige un color")
        if rgb:
            self.semillas[idx] = rgb_a_hex(rgb)
            self._render_semillas()
            self._recalcular()

    def _add_semilla(self):
        if len(self.semillas) >= 5:
            messagebox.showinfo("Límite", "Máximo 5 colores.")
            return
        self.semillas.append("#808080")
        self._render_semillas(); self._recalcular()

    def _remove_semilla(self):
        if len(self.semillas) <= 2:
            messagebox.showinfo("Límite", "Mínimo 2 colores.")
            return
        self.semillas.pop()
        self._render_semillas(); self._recalcular()

    # ---------- cálculo y preview ----------

    def _recalcular(self):
        colores = [hex_a_rgb(c) for c in self.semillas]
        nombre = self.var_nombre.get() or "Custom"
        roles = [r for r, v in self.role_vars.items() if v.get()] if hasattr(self, "role_vars") else list(ROLES_DEFAULT)
        if len(roles) < 3: roles = list(ROLES_DEFAULT)
        if len(roles) > 10: roles = roles[:10]

        roles = [r for r in ROLES_CATALOGO if r in roles]

        self.tema = derivar_tema(
            colores, roles, nombre,
            self.var_claro.get(),
            self.var_delta.get(),
        )
        self._actualizar_preview()
        self._actualizar_salida()

    def _actualizar_preview(self):
        t = self.tema
        col = t["roles"]
        H = lambda rgb: rgb_a_hex(rgb) if rgb else "#888"

        bg    = col.get("background", (30, 30, 30))
        surf  = col.get("surface", bg)
        surfA = col.get("surfaceAlt", surf)
        bord  = col.get("border", surfA)
        prim  = col.get("primary", bg)
        acc   = col.get("accent", prim)
        accA  = col.get("accentAlt", acc)
        txt   = col.get("text", (240, 240, 240))
        muted = col.get("textMuted", txt)
        onAcc = col.get("textOnAccent", (0, 0, 0))

        self.mockup.configure(bg=H(bg))
        self.hdr.configure(bg=H(surf))
        self.lbl_titulo.configure(bg=H(surf), fg=H(txt))
        self.lbl_badge.configure(bg=H(acc), fg=H(onAcc))
        self.lbl_hora.configure(bg=H(surf), fg=H(muted))

        self.body.configure(bg=H(bg))
        self.card.configure(bg=H(surf), highlightbackground=H(bord), highlightthickness=1)
        self.lbl_card_t.configure(bg=H(surf), fg=H(txt))
        self.lbl_card_d.configure(bg=H(surf), fg=H(muted))
        self.btn_primario.master.configure(bg=H(surf))
        self.btn_primario.configure(bg=H(prim), fg=H(onAcc))
        self.btn_acento.configure(bg=H(acc), fg=H(onAcc))
        self.btn_alt.configure(bg=H(accA), fg=H(onAcc))

        self.lista.configure(bg=H(bg))
        for row in self.lista.winfo_children():
            row.configure(bg=H(surfA), highlightbackground=H(bord), highlightthickness=1)
            for w in row.winfo_children():
                if isinstance(w, tk.Label):
                    if w.cget("text") == "●":
                        w.configure(bg=H(surfA), fg=H(prim))
                    elif w.cget("text") == "›":
                        w.configure(bg=H(surfA), fg=H(muted))
                    else:
                        w.configure(bg=H(surfA), fg=H(txt))

        # Swatches
        for w in self.f_swatches.winfo_children():
            w.destroy()
        for rol, rgb in self.tema["roles"].items():
            col_f = tk.Frame(self.f_swatches, bg="#1e1e1e")
            col_f.pack(side="left", expand=True, fill="x", padx=1)
            box = tk.Frame(col_f, height=40, bg=H(rgb), cursor="hand2")
            box.pack(fill="x"); box.pack_propagate(False)
            lbl = tk.Label(col_f, text=rol, bg="#1e1e1e", fg="#aaa", font=("Segoe UI", 7))
            lbl.pack(pady=(2, 0))
            def copiar(e, c=H(rgb), l=lbl, r=rol):
                self.clipboard_clear(); self.clipboard_append(c)
                l.configure(text=f"{r} ✓")
                self.after(900, lambda: l.configure(text=r))
            box.bind("<Button-1>", copiar)

    def _actualizar_salida(self):
        fmt = self.var_formato.get()
        fn = EXPORTADORES.get(fmt, exp_hex)
        self.txt_out.delete("1.0", "end")
        self.txt_out.insert("1.0", fn(self.tema))

    # ---------- export ----------

    def _copiar_salida(self):
        self.clipboard_clear()
        self.clipboard_append(self.txt_out.get("1.0", "end-1c"))
        messagebox.showinfo("Copiado", f"Salida ({self.var_formato.get()}) copiada.")

    def _guardar_archivo(self):
        fmt = self.var_formato.get()
        ext = EXTENSIONES.get(fmt, ".txt")
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Todos", "*.*")],
            initialfile=f"tema_{self.tema['nombre'].lower()}{ext}")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_out.get("1.0", "end-1c"))
            messagebox.showinfo("Guardado", path)


if __name__ == "__main__":
    App().mainloop()