"""
3D Studio - Conversor 2D para 3D
Interface desktop dark com tkinter puro (sem dependencias extras de UI)
Exporta: GLB, OBJ, STL
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageFilter, ImageTk
import numpy as np
import threading
import struct
import json
import math
import os
import io
import time

# ═══════════════════════════════════════════════════════════════════
#  CORES / TEMA DARK
# ═══════════════════════════════════════════════════════════════════
BG      = "#0f0f12"
SURFACE = "#18181c"
CARD    = "#1e1e24"
BORDER  = "#2e2e3a"
ACCENT  = "#4f7cff"
ACCENT2 = "#ff6b35"
YELLOW  = "#f5c518"
GREEN   = "#22c55e"
TEXT    = "#f0f0f5"
MUTED   = "#777788"
WHITE   = "#ffffff"
RED_ERR = "#ef4444"

FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_BODY   = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_LABEL  = ("Segoe UI", 10, "bold")
FONT_BIG    = ("Segoe UI", 16, "bold")


# ═══════════════════════════════════════════════════════════════════
#  MOTOR 3D
# ═══════════════════════════════════════════════════════════════════
def estimate_depth(img: Image.Image, resolution: int = 200) -> np.ndarray:
    """Mapa de profundidade por luminância + bordas + centro-bias."""
    from scipy.ndimage import gaussian_filter
    img_r = img.resize((resolution, resolution), Image.LANCZOS)
    gray  = img_r.convert("L")
    lum   = np.array(gray, dtype=np.float32) / 255.0
    edge  = np.array(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32) / 255.0

    # Centro-bias: objetos no centro tendem a ser mais próximos
    h, w = lum.shape
    y_idx, x_idx = np.mgrid[0:h, 0:w]
    cy, cx = h / 2, w / 2
    dist = np.sqrt(((y_idx - cy) / cy)**2 + ((x_idx - cx) / cx)**2)
    center_bias = np.clip(1.0 - dist * 0.5, 0, 1)

    depth = lum * 0.55 + (1.0 - edge) * 0.25 + center_bias * 0.20
    depth = gaussian_filter(depth, sigma=4)
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
    return depth


def depth_to_stl(depth: np.ndarray, scale_z: float = 0.4) -> bytes:
    """Gera STL binário a partir do mapa de profundidade."""
    h, w = depth.shape
    triangles = []

    for y in range(h - 1):
        for x in range(w - 1):
            # Vértices do quad
            def v(yy, xx):
                nx = (xx / (w-1)) * 2 - 1
                ny = -((yy / (h-1)) * 2 - 1)
                nz = float(depth[yy, xx]) * scale_z
                return (nx, ny, nz)

            a, b = v(y, x),     v(y, x+1)
            c, d = v(y+1, x+1), v(y+1, x)

            # Normal simples (0,0,1) — suficiente para impressão 3D
            norm = (0.0, 0.0, 1.0)
            triangles.append((norm, a, b, c))
            triangles.append((norm, a, c, d))

    # Adiciona face traseira plana (base sólida para impressão 3D)
    base_z = -0.05
    corners = [(-1,-1,base_z),(1,-1,base_z),(1,1,base_z),(-1,1,base_z)]
    a,b,c,d = corners
    triangles.append(((0,0,-1), a, c, b))
    triangles.append(((0,0,-1), a, d, c))

    # Lados (fecha o sólido)
    top_edge = [(x/(w-1)*2-1, -(0/(h-1)*2-1), float(depth[0,x])*scale_z) for x in range(w)]
    bot_edge = [(x/(w-1)*2-1, -(((h-1)/(h-1))*2-1), float(depth[h-1,x])*scale_z) for x in range(w)]
    left_edge  = [(-(0/(w-1)*2-1),   -(y/(h-1)*2-1), float(depth[y,0])*scale_z)   for y in range(h)]
    right_edge = [(-((w-1)/(w-1)*2-1),-(y/(h-1)*2-1), float(depth[y,w-1])*scale_z) for y in range(h)]

    def add_side(edge, nx, ny):
        for i in range(len(edge)-1):
            t, b_left = edge[i], (edge[i][0], edge[i][1], base_z)
            t2, b_right = edge[i+1], (edge[i+1][0], edge[i+1][1], base_z)
            norm = (nx, ny, 0.0)
            triangles.append((norm, t,  b_left, t2))
            triangles.append((norm, t2, b_left, b_right))

    add_side(top_edge,  0, 1)
    add_side(bot_edge,  0,-1)
    add_side(left_edge,-1, 0)
    add_side(right_edge,1, 0)

    # Escreve binário STL
    header = b"3D Studio - Generated STL" + b'\x00' * (80 - len(b"3D Studio - Generated STL"))
    buf = bytearray()
    buf += header
    buf += struct.pack('<I', len(triangles))
    for norm, v1, v2, v3 in triangles:
        buf += struct.pack('<3f', *norm)
        buf += struct.pack('<3f', *v1)
        buf += struct.pack('<3f', *v2)
        buf += struct.pack('<3f', *v3)
        buf += struct.pack('<H', 0)
    return bytes(buf)


def depth_to_glb(depth: np.ndarray, img: Image.Image, scale_z: float = 0.4) -> bytes:
    """Gera GLB com textura da imagem original."""
    h, w = depth.shape
    img_small = img.resize((w, h), Image.LANCZOS).convert("RGB")
    positions, normals, uvs, indices = [], [], [], []

    for y in range(h):
        for x in range(w):
            positions.extend([(x/(w-1))*2-1, -((y/(h-1))*2-1), float(depth[y,x])*scale_z])
            normals.extend([0.0, 0.0, 1.0])
            uvs.extend([x/(w-1), 1.0-y/(h-1)])

    for y in range(h-1):
        for x in range(w-1):
            a=y*w+x; b=y*w+x+1; c=(y+1)*w+x+1; d=(y+1)*w+x
            indices.extend([a,b,c,a,c,d])

    pos_d=np.array(positions,dtype=np.float32).tobytes()
    nor_d=np.array(normals,  dtype=np.float32).tobytes()
    uv_d =np.array(uvs,      dtype=np.float32).tobytes()
    idx_d=np.array(indices,  dtype=np.uint32 ).tobytes()
    buf=io.BytesIO(); img_small.save(buf,"PNG"); tex_d=buf.getvalue()

    def pad4(b): return b+b'\x00'*((4-len(b)%4)%4)
    pos_d=pad4(pos_d);nor_d=pad4(nor_d);uv_d=pad4(uv_d);idx_d=pad4(idx_d);tex_d=pad4(tex_d)

    po=0;no=po+len(pos_d);uo=no+len(nor_d);io2=uo+len(uv_d);to=io2+len(idx_d)
    total=to+len(tex_d)
    bin_buf=pos_d+nor_d+uv_d+idx_d+tex_d
    pa=np.array(positions,dtype=np.float32).reshape(-1,3)
    gltf={"asset":{"version":"2.0","generator":"3D Studio"},"scene":0,
          "scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
          "meshes":[{"primitives":[{"attributes":{"POSITION":0,"NORMAL":1,"TEXCOORD_0":2},"indices":3,"material":0}]}],
          "accessors":[
            {"bufferView":0,"byteOffset":0,"componentType":5126,"count":h*w,"type":"VEC3","min":pa.min(0).tolist(),"max":pa.max(0).tolist()},
            {"bufferView":1,"byteOffset":0,"componentType":5126,"count":h*w,"type":"VEC3"},
            {"bufferView":2,"byteOffset":0,"componentType":5126,"count":h*w,"type":"VEC2"},
            {"bufferView":3,"byteOffset":0,"componentType":5125,"count":len(indices),"type":"SCALAR"},
          ],
          "bufferViews":[
            {"buffer":0,"byteOffset":po,"byteLength":len(pos_d)},
            {"buffer":0,"byteOffset":no,"byteLength":len(nor_d)},
            {"buffer":0,"byteOffset":uo,"byteLength":len(uv_d)},
            {"buffer":0,"byteOffset":io2,"byteLength":len(idx_d)},
            {"buffer":0,"byteOffset":to,"byteLength":len(tex_d)},
          ],
          "buffers":[{"byteLength":total}],
          "materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0},"metallicFactor":0.0,"roughnessFactor":0.8},"doubleSided":True}],
          "textures":[{"source":0}],"images":[{"bufferView":4,"mimeType":"image/png"}]}
    jb=pad4(json.dumps(gltf,separators=(',',':')).encode())
    def chunk(t,d):return struct.pack('<II',len(d),t)+d
    jc=chunk(0x4E4F534A,jb);bc=chunk(0x004E4942,bin_buf)
    return struct.pack('<III',0x46546C67,2,12+len(jc)+len(bc))+jc+bc


def depth_to_obj(depth: np.ndarray, img: Image.Image, scale_z: float = 0.4):
    h,w=depth.shape
    img_s=img.resize((w,h),Image.LANCZOS).convert("RGB")
    lines=["# 3D Studio","mtllib model.mtl","o Mesh"]
    for y in range(h):
        for x in range(w):
            lines.append(f"v {(x/(w-1))*2-1:.4f} {-((y/(h-1))*2-1):.4f} {float(depth[y,x])*scale_z:.4f}")
    for y in range(h):
        for x in range(w):
            lines.append(f"vt {x/(w-1):.4f} {1-y/(h-1):.4f}")
    lines+=["vn 0 0 1","usemtl Material","s 1"]
    def idx(y,x):return y*w+x+1
    for y in range(h-1):
        for x in range(w-1):
            a,b,c,d=idx(y,x),idx(y,x+1),idx(y+1,x+1),idx(y+1,x)
            lines.append(f"f {a}/{a}/1 {b}/{b}/1 {c}/{c}/1")
            lines.append(f"f {a}/{a}/1 {c}/{c}/1 {d}/{d}/1")
    mtl="newmtl Material\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nmap_Kd texture.jpg\n"
    buf=io.BytesIO();img_s.save(buf,"JPEG",quality=85)
    return "\n".join(lines),mtl,buf.getvalue()


# ═══════════════════════════════════════════════════════════════════
#  WIDGET AUXILIAR — botão arredondado com Canvas
# ═══════════════════════════════════════════════════════════════════
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg=ACCENT, fg=WHITE,
                 width=160, height=36, radius=10, font=FONT_LABEL, **kw):
        super().__init__(parent, width=width, height=height,
                         bg=SURFACE, highlightthickness=0, **kw)
        self._cmd    = command
        self._bg     = bg
        self._hover  = self._darken(bg)
        self._text   = text
        self._font   = font
        self._r      = radius
        self._w      = width
        self._h      = height
        self._draw(self._bg)
        self.bind("<Button-1>",   self._click)
        self.bind("<Enter>",      lambda e: self._draw(self._hover))
        self.bind("<Leave>",      lambda e: self._draw(self._bg))
        self.bind("<ButtonRelease-1>", lambda e: self._draw(self._bg))

    def _darken(self, hex_color):
        r,g,b = int(hex_color[1:3],16),int(hex_color[3:5],16),int(hex_color[5:7],16)
        return f"#{max(r-30,0):02x}{max(g-30,0):02x}{max(b-30,0):02x}"

    def _draw(self, color):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            self.delete("all")
            r,w,h = self._r,self._w,self._h
            self.create_arc(0,0,r*2,r*2,start=90,extent=90,fill=color,outline=color)
            self.create_arc(w-r*2,0,w,r*2,start=0,extent=90,fill=color,outline=color)
            self.create_arc(0,h-r*2,r*2,h,start=180,extent=90,fill=color,outline=color)
            self.create_arc(w-r*2,h-r*2,w,h,start=270,extent=90,fill=color,outline=color)
            self.create_rectangle(r,0,w-r,h,fill=color,outline=color)
            self.create_rectangle(0,r,w,h-r,fill=color,outline=color)
            self.create_text(w//2,h//2,text=self._text,fill=WHITE,font=self._font)
        except tk.TclError:
            return

    def _click(self, e):
        if self._cmd: self._cmd()

    def configure_text(self, text):
        self._text = text
        self._draw(self._bg)

    def set_state(self, state):
        self._bg    = MUTED if state=="disabled" else ACCENT
        self._hover = MUTED if state=="disabled" else self._darken(ACCENT)
        self._draw(self._bg)
        if state == "disabled":
            self.unbind("<Button-1>"); self.unbind("<Enter>"); self.unbind("<Leave>")
        else:
            self.bind("<Button-1>",   self._click)
            self.bind("<Enter>",      lambda e: self._draw(self._hover))
            self.bind("<Leave>",      lambda e: self._draw(self._bg))


# ═══════════════════════════════════════════════════════════════════
#  APP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════
class Studio3D(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("3D Studio — Conversor 2D → 3D")
        self.geometry("1120x740")
        self.minsize(920, 620)
        self.configure(bg=BG)
        try: self.iconbitmap(default="")
        except: pass

        self.img_pil    = None
        self.depth_arr  = None
        self.output_data= None
        self.output_fmt = None
        self._last_dir  = os.path.expanduser("~")

        # Variáveis
        self.fmt_var    = tk.StringVar(value="GLB")
        self.mode_var   = tk.StringVar(value="HD")
        self.depth_var  = tk.DoubleVar(value=0.4)
        self.status_var = tk.StringVar(value="Pronto — selecione uma imagem para começar")
        self.prog_var   = tk.DoubleVar(value=0)
        self.prog_lbl   = tk.StringVar(value="")

        self._build_ui()

    # ── BUILD UI ──────────────────────────────────────────────────
    def _build_ui(self):
        self._build_navbar()
        self._build_body()
        self._build_statusbar()

    def _build_navbar(self):
        nav = tk.Frame(self, bg="#111116", height=52)
        nav.pack(fill="x"); nav.pack_propagate(False)

        # Logo
        logo = tk.Frame(nav, bg="#111116")
        logo.pack(side="left", padx=18)
        tk.Label(logo, text="⬡", font=("Segoe UI",20), fg=YELLOW, bg="#111116").pack(side="left")
        tk.Label(logo, text=" 3D STUDIO", font=("Segoe UI",13,"bold"), fg=WHITE, bg="#111116").pack(side="left")
        tk.Label(logo, text=f"  v1.1", font=FONT_SMALL, fg=MUTED, bg="#111116").pack(side="left")

        for lbl in ["Converter","Galeria","Sobre"]:
            tk.Label(nav, text=lbl, font=FONT_BODY, fg=MUTED, bg="#111116",
                     cursor="hand2").pack(side="left", padx=12)

        # Badge right
        badge = tk.Label(nav, text="⚡ Powered by IA", font=FONT_SMALL,
                         fg=YELLOW, bg="#111116")
        badge.pack(side="right", padx=18)

        # Separator
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # Left panel
        left = tk.Frame(body, bg=CARD, bd=0, relief="flat")
        left.pack(side="left", fill="both", expand=True, padx=(0,8))
        self._build_left(left)

        # Right panel
        right = tk.Frame(body, bg=CARD, bd=0, relief="flat")
        right.pack(side="left", fill="both", expand=True, padx=(8,0))
        self._build_right(right)

    def _build_left(self, parent):
        # Header
        hdr = tk.Frame(parent, bg=CARD)
        hdr.pack(fill="x", padx=18, pady=(14,10))
        tk.Label(hdr, text="●", fg=ACCENT, bg=CARD, font=("Segoe UI",10)).pack(side="left")
        tk.Label(hdr, text=" Imagem de Entrada", font=FONT_TITLE, fg=TEXT, bg=CARD).pack(side="left")

        # Drop zone
        self.drop_outer = tk.Frame(parent, bg=BORDER, bd=1, relief="solid")
        self.drop_outer.pack(fill="both", expand=True, padx=18, pady=(0,10))
        self.drop_zone = tk.Frame(self.drop_outer, bg="#13131a", cursor="hand2")
        self.drop_zone.pack(fill="both", expand=True, padx=1, pady=1)

        self.drop_icon  = tk.Label(self.drop_zone, text="🖼", font=("Segoe UI",40),
                                   fg=MUTED, bg="#13131a")
        self.drop_icon.pack(expand=True, pady=(30,4))
        self.drop_text  = tk.Label(self.drop_zone,
                                   text="Clique aqui para selecionar imagem\nPNG  ·  JPG  ·  WEBP  ·  BMP",
                                   font=FONT_BODY, fg=MUTED, bg="#13131a", justify="center")
        self.drop_text.pack(expand=True, pady=(0,30))

        self.img_label  = tk.Label(self.drop_zone, bg="#13131a")

        for w in [self.drop_zone, self.drop_icon, self.drop_text]:
            w.bind("<Button-1>", lambda e: self._pick_image())
        self.drop_zone.bind("<Enter>", lambda e: self.drop_outer.configure(bg=ACCENT))
        self.drop_zone.bind("<Leave>", lambda e: self.drop_outer.configure(bg=BORDER))

        # ── Separator
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=4)

        # ── Options
        opts = tk.Frame(parent, bg=CARD)
        opts.pack(fill="x", padx=18, pady=4)

        # Format
        r1 = tk.Frame(opts, bg=CARD); r1.pack(fill="x", pady=3)
        tk.Label(r1, text="Formato:", font=FONT_LABEL, fg=MUTED, bg=CARD, width=11, anchor="w").pack(side="left")
        for fmt, col in [("GLB", ACCENT), ("OBJ", ACCENT), ("STL", GREEN)]:
            rb = tk.Radiobutton(r1, text=fmt, variable=self.fmt_var, value=fmt,
                                font=FONT_BODY, fg=TEXT, bg=CARD,
                                selectcolor=CARD, activebackground=CARD,
                                activeforeground=TEXT,
                                indicatoron=True)
            rb.pack(side="left", padx=10)

        # Mode
        r2 = tk.Frame(opts, bg=CARD); r2.pack(fill="x", pady=3)
        tk.Label(r2, text="Modo:", font=FONT_LABEL, fg=MUTED, bg=CARD, width=11, anchor="w").pack(side="left")
        for mode in [("HD 🔮", "HD"), ("Smart ⚡", "Smart")]:
            tk.Radiobutton(r2, text=mode[0], variable=self.mode_var, value=mode[1],
                           font=FONT_BODY, fg=TEXT, bg=CARD,
                           selectcolor=CARD, activebackground=CARD,
                           activeforeground=TEXT).pack(side="left", padx=10)

        # Depth
        r3 = tk.Frame(opts, bg=CARD); r3.pack(fill="x", pady=3)
        tk.Label(r3, text="Profundidade Z:", font=FONT_LABEL, fg=MUTED, bg=CARD, width=11, anchor="w").pack(side="left")
        self.depth_lbl = tk.Label(r3, text="0.40", font=FONT_LABEL, fg=ACCENT, bg=CARD, width=4)
        self.depth_lbl.pack(side="right")
        sl = tk.Scale(r3, from_=0.1, to=0.8, resolution=0.01, orient="horizontal",
                      variable=self.depth_var, bg=CARD, fg=TEXT, troughcolor=BORDER,
                      highlightthickness=0, showvalue=False, length=200,
                      command=lambda v: self.depth_lbl.configure(text=f"{float(v):.2f}"))
        sl.pack(side="left", padx=8, fill="x", expand=True)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=18, pady=4)

        # ── Convert button
        btn_f = tk.Frame(parent, bg=CARD)
        btn_f.pack(fill="x", padx=18, pady=6)
        self.conv_btn = RoundedButton(btn_f, text="⚡  Converter para 3D",
                                      command=self._start_convert,
                                      bg=MUTED, width=340, height=42,
                                      font=("Segoe UI",11,"bold"))
        self.conv_btn.pack(anchor="center", pady=2)
        self.conv_btn.set_state("disabled")

        # ── Progress
        prog_f = tk.Frame(parent, bg=CARD)
        prog_f.pack(fill="x", padx=18, pady=(2,4))

        self.prog_canvas = tk.Canvas(prog_f, height=6, bg=BORDER,
                                     highlightthickness=0)
        self.prog_canvas.pack(fill="x", pady=(2,3))
        self.prog_fill_id = self.prog_canvas.create_rectangle(0,0,0,6,
                                                                fill=ACCENT, outline="")
        self.prog_canvas.bind("<Configure>", self._redraw_prog)

        self.prog_text = tk.Label(prog_f, textvariable=self.prog_lbl,
                                  font=FONT_SMALL, fg=MUTED, bg=CARD)
        self.prog_text.pack(anchor="w")

    def _build_right(self, parent):
        hdr = tk.Frame(parent, bg=CARD)
        hdr.pack(fill="x", padx=18, pady=(14,10))
        tk.Label(hdr, text="●", fg=ACCENT2, bg=CARD, font=("Segoe UI",10)).pack(side="left")
        tk.Label(hdr, text=" Mapa de Profundidade + Resultado",
                 font=FONT_TITLE, fg=TEXT, bg=CARD).pack(side="left")

        # Viewer
        viewer_outer = tk.Frame(parent, bg=BORDER, bd=1, relief="solid")
        viewer_outer.pack(fill="both", expand=True, padx=18, pady=(0,10))
        self.viewer = tk.Frame(viewer_outer, bg="#0d0d14")
        self.viewer.pack(fill="both", expand=True, padx=1, pady=1)

        self.viewer_ph = tk.Label(self.viewer,
            text="⬡\n\nO mapa de profundidade\naparecerá aqui após a conversão",
            font=("Segoe UI",12), fg=MUTED, bg="#0d0d14", justify="center")
        self.viewer_ph.pack(expand=True)
        self.viewer_img_lbl = tk.Label(self.viewer, bg="#0d0d14")

        # Stats frame
        stats_f = tk.Frame(parent, bg="#13131a", relief="flat")
        stats_f.pack(fill="x", padx=18, pady=(0,8))

        self.stats_lbl = tk.Label(stats_f,
            text="Aguardando conversão…",
            font=FONT_SMALL, fg=MUTED, bg="#13131a", pady=8)
        self.stats_lbl.pack(anchor="w", padx=12)

        # Download buttons
        dl_f = tk.Frame(parent, bg=CARD)
        dl_f.pack(fill="x", padx=18, pady=(0,10))

        self.dl_btn = RoundedButton(dl_f, text="📁  Salvar Modelo",
                                    command=self._save_model,
                                    bg=MUTED, width=200, height=38)
        self.dl_btn.pack(side="left", padx=(0,8))
        self.dl_btn.set_state("disabled")

        self.folder_btn = RoundedButton(dl_f, text="📂  Abrir Pasta",
                                        command=self._open_folder,
                                        bg="#333344", width=160, height=38)
        self.folder_btn.pack(side="left")

        # Features card
        feat = tk.Frame(parent, bg="#141420", relief="flat")
        feat.pack(fill="x", padx=18, pady=(0,14))

        tk.Label(feat, text="✨  Formatos suportados",
                 font=FONT_LABEL, fg=YELLOW, bg="#141420").pack(anchor="w", padx=12, pady=(10,6))

        items = [
            ("🧊 GLB",  "GLTF binário · Unity, Blender, Three.js, Sketchfab"),
            ("📦 OBJ",  "Universal · com textura e material (.mtl)"),
            ("🖨 STL",  "Impressão 3D · Cura, PrusaSlicer, Tinkercad"),
        ]
        for icon_txt, desc in items:
            row = tk.Frame(feat, bg="#141420")
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=icon_txt, font=FONT_LABEL, fg=TEXT, bg="#141420", width=7, anchor="w").pack(side="left")
            tk.Label(row, text=desc, font=FONT_SMALL, fg=MUTED, bg="#141420", anchor="w").pack(side="left")

        tk.Frame(feat, bg="#141420", height=8).pack()

    def _build_statusbar(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        bar = tk.Frame(self, bg="#0d0d10", height=26)
        bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status_var,
                 font=FONT_SMALL, fg=MUTED, bg="#0d0d10").pack(side="left", padx=12)

    # ── HELPERS ───────────────────────────────────────────────────
    def _redraw_prog(self, event=None):
        try:
            if not self.prog_canvas.winfo_exists():
                return
            w = self.prog_canvas.winfo_width()
            pct = self.prog_var.get()
            fill_w = int(w * pct)
            self.prog_canvas.coords(self.prog_fill_id, 0, 0, fill_w, 6)
        except tk.TclError:
            pass

    def _set_progress(self, pct, msg=""):
        self.prog_var.set(pct)
        self.prog_lbl.set(msg)
        self._redraw_prog()

    # ── PICK IMAGE ────────────────────────────────────────────────
    def _pick_image(self):
        path = filedialog.askopenfilename(
            title="Selecionar imagem",
            filetypes=[("Imagens","*.png *.jpg *.jpeg *.webp *.bmp"),("Todos","*.*")]
        )
        if not path: return
        try:
            pil = Image.open(path).convert("RGB")
            self.img_pil = pil

            # Thumbnail
            tw, th = 320, 200
            thumb = pil.copy(); thumb.thumbnail((tw, th), Image.LANCZOS)
            tk_thumb = ImageTk.PhotoImage(thumb)
            self.drop_icon.pack_forget(); self.drop_text.pack_forget()
            self.img_label.configure(image=tk_thumb, text=""); self.img_label._img = tk_thumb
            self.img_label.pack(expand=True, pady=10)

            self.conv_btn.set_state("normal")
            self.status_var.set(f"Imagem: {os.path.basename(path)}  |  {pil.width}×{pil.height} px")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir:\n{e}")

    # ── CONVERT ───────────────────────────────────────────────────
    def _start_convert(self):
        if not self.img_pil: return
        self.conv_btn.set_state("disabled")
        self.dl_btn.set_state("disabled")
        self._set_progress(0, "Iniciando…")
        threading.Thread(target=self._convert_thread, daemon=True).start()

    def _convert_thread(self):
        try:
            steps = [
                (0.12, "Analisando imagem…"),
                (0.30, "Estimando mapa de profundidade…"),
                (0.55, "Construindo malha 3D…"),
                (0.78, "Otimizando polígonos…"),
                (0.92, "Exportando arquivo…"),
            ]
            for p, msg in steps:
                self.after(0, lambda p=p,m=msg: self._set_progress(p, m))
                time.sleep(0.35)

            res   = 200 if self.mode_var.get() == "HD" else 140
            z     = self.depth_var.get()
            depth = estimate_depth(self.img_pil, resolution=res)
            self.depth_arr = depth
            fmt   = self.fmt_var.get()

            if fmt == "GLB":
                self.output_data = depth_to_glb(depth, self.img_pil, z)
                self.output_fmt  = "glb"
            elif fmt == "OBJ":
                self.output_data = depth_to_obj(depth, self.img_pil, z)
                self.output_fmt  = "obj"
            else:  # STL
                self.output_data = depth_to_stl(depth, z)
                self.output_fmt  = "stl"

            # Colorize depth for preview
            d8 = (depth * 255).astype(np.uint8)
            d_rgb = np.stack([
                (d8 * 0.3 + 20).clip(0,255).astype(np.uint8),
                (d8 * 0.5 + 40).clip(0,255).astype(np.uint8),
                d8
            ], axis=2)
            depth_pil = Image.fromarray(d_rgb)
            vw = max(self.viewer.winfo_width() - 20, 200)
            vh = max(self.viewer.winfo_height() - 20, 150)
            depth_pil.thumbnail((vw, vh), Image.LANCZOS)
            tk_depth = ImageTk.PhotoImage(depth_pil)

            verts = res * res
            faces = (res-1)*(res-1)*2
            sz    = len(self.output_data) if fmt != "OBJ" else len(self.output_data[0])
            stats = f"Modo: {self.mode_var.get()}  |  Formato: {fmt}  |  Vértices: {verts:,}  |  Faces: {faces:,}  |  Tamanho: {sz//1024} KB  |  Profundidade: {z:.2f}"

            def done():
                self._set_progress(1.0, "✅ Concluído!")
                self.viewer_ph.pack_forget()
                self.viewer_img_lbl.configure(image=tk_depth); self.viewer_img_lbl._img = tk_depth
                self.viewer_img_lbl.pack(expand=True, pady=10)
                self.stats_lbl.configure(text=stats, fg=TEXT)
                self.dl_btn.set_state("normal")
                self.conv_btn.set_state("normal")
                self.status_var.set(f"✅ Modelo {fmt} gerado com sucesso!")
            self.after(0, done)

        except Exception as e:
            import traceback; traceback.print_exc()
            def err():
                self._set_progress(0, f"❌ Erro: {e}")
                self.conv_btn.set_state("normal")
                messagebox.showerror("Erro na conversão", str(e))
            self.after(0, err)

    # ── SAVE ──────────────────────────────────────────────────────
    def _save_model(self):
        fmt = self.output_fmt
        if fmt == "glb":
            path = filedialog.asksaveasfilename(
                defaultextension=".glb",
                filetypes=[("GLB","*.glb"),("Todos","*.*")],
                initialfile="modelo_3d.glb", initialdir=self._last_dir)
            if path:
                with open(path,"wb") as f: f.write(self.output_data)
                self._last_dir = os.path.dirname(path)
                messagebox.showinfo("Salvo!",f"GLB salvo em:\n{path}")

        elif fmt == "stl":
            path = filedialog.asksaveasfilename(
                defaultextension=".stl",
                filetypes=[("STL","*.stl"),("Todos","*.*")],
                initialfile="modelo_3d.stl", initialdir=self._last_dir)
            if path:
                with open(path,"wb") as f: f.write(self.output_data)
                self._last_dir = os.path.dirname(path)
                messagebox.showinfo("Salvo!",f"STL salvo em:\n{path}\n\nAbra no Cura ou PrusaSlicer para imprimir!")

        elif fmt == "obj":
            folder = filedialog.askdirectory(title="Pasta para salvar OBJ", initialdir=self._last_dir)
            if folder:
                obj_str, mtl_str, tex_bytes = self.output_data
                with open(os.path.join(folder,"modelo_3d.obj"),"w") as f: f.write(obj_str)
                with open(os.path.join(folder,"model.mtl"),    "w") as f: f.write(mtl_str)
                with open(os.path.join(folder,"texture.jpg"), "wb") as f: f.write(tex_bytes)
                self._last_dir = folder
                messagebox.showinfo("Salvo!",f"OBJ + MTL + textura salvos em:\n{folder}")

    def _open_folder(self):
        import subprocess, platform
        d = self._last_dir
        if platform.system()=="Windows": os.startfile(d)
        elif platform.system()=="Darwin": subprocess.Popen(["open",d])
        else: subprocess.Popen(["xdg-open",d])


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = Studio3D()
    app.mainloop()
