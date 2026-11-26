"""
Гостиничный набор мебели (20 предметов) по референсу — построен с нуля чистой геометрией.

Шкаф, книжный шкаф, тележка для багажа, вешалка, растение, чемодан, картина, торшер,
настольная лампа, комод, тумбочка, журнальный столик, банкетка, дверь, камин,
напольные часы, зеркало, стеллаж для багажа, шторы, панель на стену.

Каждый предмет — отдельная модель из нескольких деталей (каждая деталь = MeshPart в Roblox).
Текстур нет (кроме холста картины) — материалы и цвета ставит скрипт HotelSetup.server.lua,
который генерируется вместе с моделями. Он же оживляет предметы:
двери шкафа/комнаты открываются, ящики выдвигаются, часы идут, маятник качается,
камин горит, лампы светят, на банкетку можно сесть.

Ось: Z вверх, лицевая сторона смотрит в -Y, каждый предмет стоит на полу в начале координат.

Запуск: python build_hotel_set.py -- out_dir [render]
"""

import math
import os
import random
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Euler, Matrix, Vector

PI = math.pi

# ----------------------------------------------------------------------------- палитра
# ключ: (цвет для превью/Roblox 0-255, материал Roblox, прозрачность, отражение, шероховатость превью)
PALETTE = {
    "Wood":       ((88, 38, 27), "Wood", 0, 0, 0.45),
    "WoodDark":   ((56, 24, 17), "Wood", 0, 0, 0.5),
    "Fabric":     ((122, 22, 34), "Fabric", 0, 0, 0.9),
    "FabricDark": ((72, 14, 24), "Fabric", 0, 0, 0.9),
    "Brass":      ((196, 140, 72), "Metal", 0, 0, 0.3),
    "Iron":       ((52, 50, 48), "Metal", 0, 0, 0.5),
    "Glass":      ((190, 200, 205), "Glass", 0.7, 0, 0.05),
    "Mirror":     ((185, 192, 198), "Glass", 0.1, 0.6, 0.02),
    "Leaf":       ((38, 66, 34), "LeafyGrass", 0, 0, 0.8),
    "Terracotta": ((150, 78, 52), "Slate", 0, 0, 0.8),
    "Soil":       ((48, 34, 24), "Ground", 0, 0, 1.0),
    "Shade":      ((226, 192, 150), "Fabric", 0, 0, 0.9),
    "Leather":    ((62, 36, 46), "Leather", 0, 0, 0.6),
    "Strap":      ((122, 70, 40), "Leather", 0, 0, 0.6),
    "Brick":      ((122, 56, 40), "Brick", 0, 0, 0.9),
    "Mortar":     ((40, 30, 26), "Concrete", 0, 0, 1.0),
    "Log":        ((66, 44, 30), "Wood", 0, 0, 0.9),
    "Fire":       ((255, 140, 40), "Neon", 0.25, 0, 0.5),
    "Paper":      ((232, 220, 196), "SmoothPlastic", 0, 0, 0.6),
    "Black":      ((22, 18, 16), "SmoothPlastic", 0, 0, 0.5),
    "Canvas":     ((90, 90, 80), "SmoothPlastic", 0, 0, 0.8),
    "Rug":        ((110, 20, 28), "Fabric", 0, 0, 0.95),
    "Wax":        ((236, 228, 206), "SmoothPlastic", 0, 0, 0.5),
    "Flame":      ((255, 190, 90), "Neon", 0.1, 0, 0.5),
    "Ink":        ((72, 30, 20), "SmoothPlastic", 0, 0, 0.5),
    "Rust":       ((74, 36, 30), "CorrodedMetal", 0, 0, 0.75),
}


def log(*a):
    print("[hotel]", *a, flush=True)


def mat4(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    return Matrix.Translation(Vector(loc)) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1))


# ----------------------------------------------------------------------------- примитивы (bmesh)
def vf_bm(verts, faces, recalc=True):
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for f in faces:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def bm_box(sx, sy, sz, bev=0.0, seg=1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    if bev > 0:
        bev = min(bev, 0.45 * min(sx, sy, sz))
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bev, offset_type='OFFSET', segments=seg,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    return bm


def bm_cyl(r1, h, segs=16, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r1,
                          radius2=r1 if r2 is None else r2, depth=h)
    return bm


def bm_lathe(profile, segs=24, closed=False, phase=0.0):
    """Тело вращения вокруг Z. profile: [(r, z)]; r=0 -> полюс."""
    verts, faces, rings = [], [], []
    for r, z in profile:
        if r < 1e-6:
            rings.append([len(verts)])
            verts.append((0, 0, z))
        else:
            ring = []
            for k in range(segs):
                a = phase + 2 * PI * k / segs
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            faces += [[a[0], b[k], b[(k + 1) % segs]] for k in range(segs)]
        elif len(b) == 1:
            faces += [[a[k], a[(k + 1) % segs], b[0]] for k in range(segs)]
        else:
            faces += [[a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]] for k in range(segs)]
    if not closed:                                   # крышки на открытых концах
        for ring in (rings[0], rings[-1]):
            if len(ring) > 1:
                faces.append(list(ring))
    return vf_bm(verts, faces)


def bm_prism(poly, y0, y1):
    """Многоугольник в плоскости XZ, выдавленный по Y от y0 до y1."""
    n = len(poly)
    verts = [(x, y0, z) for x, z in poly] + [(x, y1, z) for x, z in poly]
    faces = [list(range(n)), list(range(n, 2 * n))]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return vf_bm(verts, faces)


def bm_ring_prism(outer, inner, y0, y1):
    """Рамка: внешний и внутренний контуры (одинаковое число точек) в XZ, толщина по Y."""
    n = len(outer)
    verts = [(x, y0, z) for x, z in outer] + [(x, y0, z) for x, z in inner] + \
            [(x, y1, z) for x, z in outer] + [(x, y1, z) for x, z in inner]
    O0, I0, O1, I1 = 0, n, 2 * n, 3 * n
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces += [[O0 + i, O0 + j, I0 + j, I0 + i], [O1 + i, I1 + i, I1 + j, O1 + j],
                  [O0 + i, O1 + i, O1 + j, O0 + j], [I0 + i, I0 + j, I1 + j, I1 + i]]
    return vf_bm(verts, faces)


def bm_tube(pts, r, segs=8, caps=True, r_end=None):
    """Труба вдоль ломаной (параллельный перенос рамки)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tang = []
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tang.append(d.normalized())
    ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tang[0].cross(ref).normalized()
    verts, faces = [], []
    for i in range(n):
        if i > 0:
            ax = tang[i - 1].cross(tang[i])
            if ax.length > 1e-8:
                ang = tang[i - 1].angle(tang[i])
                nrm = (Matrix.Rotation(ang, 3, ax.normalized()) @ nrm).normalized()
        bin_ = tang[i].cross(nrm)
        rr = r if r_end is None else r + (r_end - r) * i / (n - 1)
        for k in range(segs):
            a = 2 * PI * k / segs
            verts.append(tuple(pts[i] + (nrm * math.cos(a) + bin_ * math.sin(a)) * rr))
    for i in range(n - 1):
        for k in range(segs):
            a, b = i * segs + k, i * segs + (k + 1) % segs
            faces.append([a, b, b + segs, a + segs])
    if caps:
        faces.append(list(range(segs)))
        faces.append(list(range((n - 1) * segs, n * segs)))
    return vf_bm(verts, faces)


def bm_rect_sweep(w, h, prof):
    """Профильная рамка (багет): prof = [(отступ от внешнего края, выступ вперёд)]."""
    verts, faces = [], []
    for inset, dy in prof:
        hw, hh = w / 2 - inset, h / 2 - inset
        verts += [(-hw, -dy, -hh), (hw, -dy, -hh), (hw, -dy, hh), (-hw, -dy, hh)]
    for i in range(len(prof) - 1):
        a, b = 4 * i, 4 * (i + 1)
        for k in range(4):
            faces.append([a + k, a + (k + 1) % 4, b + (k + 1) % 4, b + k])
    return vf_bm(verts, faces)


def bm_ico(r, sub=1):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    return bm


def bm_sphere(r, u=12, v=8):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    return bm


def bm_torus(R, r, segs=24, rsegs=8):
    verts, faces = [], []
    for i in range(segs):
        a = 2 * PI * i / segs
        c = Vector((R * math.cos(a), R * math.sin(a), 0))
        d = Vector((math.cos(a), math.sin(a), 0))
        for k in range(rsegs):
            b = 2 * PI * k / rsegs
            verts.append(tuple(c + d * (r * math.cos(b)) + Vector((0, 0, r * math.sin(b)))))
    for i in range(segs):
        for k in range(rsegs):
            a0, a1 = i * rsegs + k, i * rsegs + (k + 1) % rsegs
            b0, b1 = ((i + 1) % segs) * rsegs + k, ((i + 1) % segs) * rsegs + (k + 1) % rsegs
            faces.append([a0, b0, b1, a1])
    return vf_bm(verts, faces)


def arc(cx, cz, rx, rz, a0, a1, n):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cz + rz * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


# ----------------------------------------------------------------------------- деталь / предмет
class Part:
    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.v, self.f, self.uv = [], [], []

    def add(self, bm, M=None, uvs=None):
        M = M or Matrix.Identity(4)
        off = len(self.v)
        bm.verts.index_update()
        self.v += [tuple(M @ v.co) for v in bm.verts]
        for fi, f in enumerate(bm.faces):
            self.f.append([v.index + off for v in f.verts])
            self.uv.append(uvs[fi] if uvs else None)
        bm.free()


class Item:
    def __init__(self, name):
        self.name = name
        self.parts = {}
        self.behaviors = []          # (имя детали, тип)

    def P(self, part, mat):
        key = f"{self.name}_{part}"
        if key not in self.parts:
            self.parts[key] = Part(key, mat)
        p = self.parts[key]
        assert p.mat == mat, f"{key}: {p.mat} != {mat}"
        return p

    # --- удобные обёртки
    def bx(self, part, mat, xr, yr, zr, bev=0.003, seg=1, rot=(0, 0, 0)):
        c = ((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2, (zr[0] + zr[1]) / 2)
        self.P(part, mat).add(bm_box(abs(xr[1] - xr[0]), abs(yr[1] - yr[0]), abs(zr[1] - zr[0]), bev, seg),
                              mat4(c, rot))

    def box_at(self, part, mat, size, loc, rot=(0, 0, 0), bev=0.003, seg=1):
        self.P(part, mat).add(bm_box(*size, bev, seg), mat4(loc, rot))

    def cyl(self, part, mat, r, h, loc, rot=(0, 0, 0), segs=16, r2=None):
        self.P(part, mat).add(bm_cyl(r, h, segs, r2), mat4(loc, rot))

    def lathe(self, part, mat, prof, loc=(0, 0, 0), rot=(0, 0, 0), segs=24, closed=False, phase=0.0, scale=(1, 1, 1)):
        self.P(part, mat).add(bm_lathe(prof, segs, closed, phase), mat4(loc, rot, scale))

    def prism(self, part, mat, poly, y0, y1, loc=(0, 0, 0)):
        self.P(part, mat).add(bm_prism(poly, y0, y1), mat4(loc))

    def tube(self, part, mat, pts, r, segs=8, caps=True, r_end=None):
        self.P(part, mat).add(bm_tube(pts, r, segs, caps, r_end))

    def add(self, part, mat, bm, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), uvs=None):
        self.P(part, mat).add(bm, mat4(loc, rot, scale), uvs)


def knob(it, part, mat, loc, r=0.022, depth=0.045):
    """Грибовидная ручка, торчит вперёд (-Y)."""
    s = depth / 0.058
    prof = [(0, 0), (r * 0.45, 0), (r * 0.45, 0.02 * s), (r * 0.9, 0.034 * s), (r, 0.045 * s),
            (r * 0.8, 0.055 * s), (0, 0.058 * s)]
    it.lathe(part, mat, prof, loc, (PI / 2, 0, 0), segs=14)


# ============================================================================= ПРЕДМЕТЫ
def wardrobe(it):
    w, y0, y1 = 0.6, -0.3, 0.3
    B = "Body"
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.bx(B, "Wood", (sx * 0.56 - 0.05, sx * 0.56 + 0.05), (sy * 0.26 - 0.05, sy * 0.26 + 0.05), (0, 0.05), 0.006)
    it.bx(B, "Wood", (-w - 0.03, w + 0.03), (y0 - 0.035, y1 + 0.01), (0.05, 0.15), 0.008)
    it.bx(B, "Wood", (-w - 0.015, w + 0.015), (y0 - 0.045, y1 + 0.01), (0.135, 0.165), 0.006)
    it.bx(B, "Wood", (-w, -w + 0.025), (y0, y1), (0.15, 1.86))                 # бока
    it.bx(B, "Wood", (w - 0.025, w), (y0, y1), (0.15, 1.86))
    it.bx(B, "Wood", (-w, w), (y1 - 0.02, y1), (0.15, 1.86))                   # задняя
    it.bx(B, "Wood", (-w, w), (y0, y1), (0.15, 0.18))                          # дно
    it.bx(B, "Wood", (-w, w), (y0, y1), (1.83, 1.86))                          # крыша
    it.bx(B, "Wood", (-w + 0.02, w - 0.02), (y0 + 0.03, y1 - 0.02), (1.56, 1.585))   # полка
    it.cyl("Rail", "Brass", 0.012, 2 * w - 0.06, (0, 0.02, 1.48), (0, PI / 2, 0))
    for k, (z0, z1, e) in enumerate([(1.86, 1.89, 0.02), (1.89, 1.925, 0.04), (1.925, 1.95, 0.05)]):
        it.bx(B, "Wood", (-w - e, w + e), (y0 - e, y1 + 0.01), (z0, z1), 0.006)
    top = lambda x: 2.0 + 0.11 * math.cos(PI / 2 * x / w) ** 1.5
    xs = [w - 2 * w * i / 30 for i in range(31)]
    poly = [(-w, 1.95), (w, 1.95)] + [(x, top(x)) for x in xs]
    it.prism(B, "Wood", poly, y0 - 0.03, y1)
    it.tube(B, "Wood", [(x, y0 - 0.035, top(x) + 0.005) for x in xs], 0.016, segs=8)
    it.add(B, "Wood", bm_prism(arc(0, 2.03, 0.11, 0.065, 0, 2 * PI, 24)[:-1], y0 - 0.06, y0 - 0.03))
    it.add(B, "Wood", bm_prism(arc(0, 2.03, 0.075, 0.042, 0, 2 * PI, 24)[:-1], y0 - 0.075, y0 - 0.06))
    for side, name in ((-1, "DoorL"), (1, "DoorR")):
        xa, xb = (-w + 0.004, -0.003) if side < 0 else (0.003, w - 0.004)
        it.bx(name, "Wood", (xa, xb), (y0 - 0.03, y0), (0.175, 1.825), 0.004)
        for z0, z1 in ((0.27, 0.92), (1.02, 1.73)):
            it.bx(name, "Wood", (xa + 0.075, xb - 0.075), (y0 - 0.044, y0 - 0.03), (z0, z1), 0.012, 2)
        knob(it, f"{name}_Knob", "WoodDark", ((xb - 0.06) if side < 0 else (xa + 0.06), y0 - 0.03, 0.98))
        it.behaviors.append((f"{it.name}_{name}", "hinge"))


def bookcase(it):
    w, y0, y1 = 0.5, -0.19, 0.19
    B = "Body"
    it.bx(B, "Wood", (-w - 0.03, w + 0.03), (y0 - 0.03, y1 + 0.01), (0, 0.1), 0.008)
    it.bx(B, "Wood", (-w - 0.015, w + 0.015), (y0 - 0.04, y1 + 0.01), (0.09, 0.115), 0.005)
    it.bx(B, "Wood", (-w, -w + 0.03), (y0, y1), (0.1, 1.75))
    it.bx(B, "Wood", (w - 0.03, w), (y0, y1), (0.1, 1.75))
    it.bx(B, "Wood", (-w, w), (y1 - 0.02, y1), (0.1, 1.75))
    for z in (0.1, 0.46, 0.82, 1.18):
        it.bx(B, "Wood", (-w + 0.03, w - 0.03), (y0 + 0.005, y1 - 0.02), (z, z + 0.028), 0.003)
        it.bx(B, "Wood", (-w + 0.03, w - 0.03), (y0 - 0.005, y0 + 0.02), (z, z + 0.035), 0.005)
    it.bx(B, "Wood", (-w - 0.01, -w + 0.035), (y0 - 0.012, y0 + 0.01), (0.1, 1.6), 0.005)    # пилястры
    it.bx(B, "Wood", (w - 0.035, w + 0.01), (y0 - 0.012, y0 + 0.01), (0.1, 1.6), 0.005)
    wi, wo = w - 0.03, w + 0.03
    inner = [(x, 1.42 + 0.2 * math.sqrt(max(0.0, 1 - (x / wi) ** 2))) for x in np.linspace(-wi, wi, 25)]
    top = lambda x: 1.82 + 0.1 * (1 - (x / wo) ** 2)
    poly = [(-wo, 1.42)] + inner + [(wo, 1.42)] + [(x, top(x)) for x in np.linspace(wo, -wo, 25)]
    it.prism(B, "Wood", poly, y0 - 0.025, y1)
    it.tube(B, "Wood", [(x, y0 - 0.03, top(x)) for x in np.linspace(wo, -wo, 25)], 0.015)
    it.tube(B, "Wood", [(x, y0 - 0.03, z) for x, z in inner], 0.012)
    it.bx(B, "Wood", (-wo - 0.01, wo + 0.01), (y0 - 0.035, y1 + 0.01), (1.42, 1.46), 0.006)


def suitcase(it, pre, size, base, mat="Leather"):
    w, d, h = size
    bxp, byp, bz = base
    X = lambda a, b: (bxp + a, bxp + b)
    Y = lambda a, b: (byp + a, byp + b)
    Z = lambda a, b: (bz + a, bz + b)
    it.bx(pre + "Body", mat, X(-w / 2, w / 2), Y(-d / 2, d / 2), Z(0, h), 0.025, 3)
    S = pre + "Straps"
    for cx in (-w * 0.28, w * 0.28):
        it.bx(S, "Strap", X(cx - 0.025, cx + 0.025), Y(-d / 2 - 0.006, -d / 2 + 0.03), Z(0.02, h - 0.02), 0.002)
        it.bx(S, "Strap", X(cx - 0.025, cx + 0.025), Y(d / 2 - 0.03, d / 2 + 0.006), Z(0.02, h - 0.02), 0.002)
        it.bx(S, "Strap", X(cx - 0.025, cx + 0.025), Y(-d / 2 + 0.02, d / 2 - 0.02), Z(h - 0.03, h + 0.006), 0.002)
        it.bx(S, "Strap", X(cx - 0.025, cx + 0.025), Y(-d / 2 + 0.02, d / 2 - 0.02), Z(-0.004, 0.03), 0.002)
    zm = h * 0.62
    it.bx(S, "Strap", X(-w / 2 + 0.02, w / 2 - 0.02), Y(-d / 2 - 0.004, -d / 2 + 0.03), Z(zm - 0.015, zm + 0.015), 0.002)
    it.bx(S, "Strap", X(-w / 2 + 0.02, w / 2 - 0.02), Y(d / 2 - 0.03, d / 2 + 0.004), Z(zm - 0.015, zm + 0.015), 0.002)
    for sx in (-1, 1):
        it.bx(S, "Strap", X(sx * w / 2 - 0.03, sx * w / 2 + 0.004 * sx) if sx > 0 else X(-w / 2 - 0.004, -w / 2 + 0.03),
              Y(-d / 2 + 0.02, d / 2 - 0.02), Z(zm - 0.015, zm + 0.015), 0.002)
    hp = [(bxp + 0.1 * math.cos(t), byp, bz + h + 0.012 + 0.05 * math.sin(t)) for t in np.linspace(PI, 0, 12)]
    it.tube(S, "Strap", hp, 0.011)
    Bz = pre + "Brass"
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.03, h - 0.03):
                it.box_at(Bz, "Brass", (0.072, 0.072, 0.072),
                          (bxp + sx * (w / 2 - 0.03), byp + sy * (d / 2 - 0.03), bz + z), bev=0.012, seg=2)
        it.bx(Bz, "Brass", X(sx * 0.1 - 0.012, sx * 0.1 + 0.012), Y(-0.02, 0.02), Z(h, h + 0.02), 0.003)
        it.bx(Bz, "Brass", X(sx * w * 0.14 - 0.025, sx * w * 0.14 + 0.025), Y(-d / 2 - 0.012, -d / 2 + 0.01),
              Z(h - 0.09, h - 0.03), 0.004)


def luggage_cart(it):
    it.bx("Deck", "Wood", (-0.56, 0.56), (-0.3, 0.3), (0.14, 0.2), 0.012, 2)
    it.bx("Carpet", "Fabric", (-0.53, 0.53), (-0.27, 0.27), (0.2, 0.215), 0.004)
    F = "Frame"
    for z in (0.17,):
        for pts in ([(-0.57, -0.31, z), (0.57, -0.31, z)], [(-0.57, 0.31, z), (0.57, 0.31, z)],
                    [(-0.57, -0.31, z), (-0.57, 0.31, z)], [(0.57, -0.31, z), (0.57, 0.31, z)]):
            it.tube(F, "Brass", pts, 0.014)
    for y in (-0.24, 0.24):
        path = [(-0.5, y, 0.2), (-0.5, y, 0.8)] + [(0.5 * math.cos(t), y, 1.25 + 0.4 * math.sin(t)) for t in np.linspace(PI, 0, 28)]
        path = path[:2] + [(-0.5, y, 1.25)] + path[2:] + [(0.5, y, 0.8), (0.5, y, 0.2)]
        it.tube(F, "Brass", [path[0], path[1], path[2]], 0.019)
        it.tube(F, "Brass", path[3:-3], 0.019)
        it.tube(F, "Brass", [path[-3], path[-2], path[-1]], 0.019)
        inner = [(0.36 * math.cos(t), y, 1.15 + 0.32 * math.sin(t)) for t in np.linspace(PI, 0, 24)]
        it.tube(F, "Brass", [(-0.36, y, 0.215)] + inner + [(0.36, y, 0.215)], 0.013)
    it.tube(F, "Brass", [(0, -0.26, 1.65), (0, 0.26, 1.65)], 0.016)
    for x in (-0.5, 0.5):
        for z in (0.45, 0.75):
            it.tube(F, "Brass", [(x, -0.24, z), (x, 0.24, z)], 0.012)
    it.lathe(F, "Brass", [(0, 1.64), (0.025, 1.65), (0.018, 1.68), (0.035, 1.71), (0.04, 1.73), (0.03, 1.76),
                          (0.012, 1.78), (0.006, 1.82), (0, 1.83)], segs=16)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 0.47, sy * 0.24
            it.cyl(F, "Brass", 0.035, 0.012, (x, y, 0.135))
            for dy in (-0.022, 0.022):
                it.bx(F, "Brass", (x - 0.012, x + 0.012), (y + dy - 0.004, y + dy + 0.004), (0.06, 0.13), 0.002)
            it.cyl("Wheels", "Iron", 0.06, 0.03, (x, y, 0.062), (PI / 2, 0, 0), segs=18)


def coat_rack(it):
    B = "Body"
    it.lathe(B, "Wood", [(0, 0.2), (0.05, 0.2), (0.065, 0.24), (0.06, 0.32), (0.07, 0.36), (0.055, 0.4), (0, 0.4)], segs=16)
    for k in range(3):
        a = PI / 2 + k * 2 * PI / 3
        pts = [(r * math.cos(a), r * math.sin(a), z) for r, z in
               [(0.04, 0.32), (0.11, 0.29), (0.18, 0.21), (0.24, 0.12), (0.29, 0.06), (0.33, 0.04), (0.36, 0.045)]]
        it.tube(B, "Wood", pts, 0.026, r_end=0.018)
        it.add(B, "Wood", bm_sphere(0.025), (0.36 * math.cos(a), 0.36 * math.sin(a), 0.025), scale=(1, 1, 0.8))
    prof = [(0.035, 0.4), (0.03, 0.5), (0.042, 0.55), (0.03, 0.6), (0.026, 1.0), (0.04, 1.05), (0.026, 1.1),
            (0.024, 1.45), (0.05, 1.5), (0.05, 1.6), (0.035, 1.64), (0.042, 1.7), (0.03, 1.74), (0.02, 1.77),
            (0.032, 1.8), (0.014, 1.84), (0, 1.86)]
    it.lathe(B, "Wood", prof, segs=16)
    for k in range(4):
        a = PI / 4 + k * PI / 2
        pts = [(r * math.cos(a), r * math.sin(a), z) for r, z in
               [(0.03, 1.53), (0.1, 1.55), (0.16, 1.6), (0.19, 1.68), (0.18, 1.73), (0.15, 1.75)]]
        it.tube(B, "Wood", pts, 0.014)
        it.add(B, "Wood", bm_sphere(0.02, 10, 6), pts[-1])
        a2 = k * PI / 2
        pts = [(r * math.cos(a2), r * math.sin(a2), z) for r, z in [(0.02, 1.3), (0.08, 1.31), (0.12, 1.36), (0.12, 1.41)]]
        it.tube(B, "Wood", pts, 0.012)
        it.add(B, "Wood", bm_sphere(0.017, 10, 6), pts[-1])


def plant(it):
    it.lathe("Pot", "Terracotta", [(0, 0), (0.13, 0), (0.135, 0.02), (0.17, 0.27), (0.195, 0.28), (0.2, 0.33),
                                    (0.18, 0.34), (0.165, 0.3), (0, 0.3)], segs=8, phase=PI / 8)
    it.lathe("Soil", "Soil", [(0, 0.3), (0.166, 0.3), (0.166, 0.31), (0, 0.31)], segs=8, phase=PI / 8)
    it.cyl("Trunk", "WoodDark", 0.018, 0.25, (0, 0, 0.42), segs=8)
    rnd = random.Random(7)
    z0, z1 = 0.45, 1.18
    rad = lambda t: 0.22 * math.sin(PI * min(1, max(0, t))) ** 0.75 * (1 - 0.3 * t) + 0.01
    prof = [(0, z0 + 0.02)] + [(rad(t) * 0.85, z0 + (z1 - z0) * t) for t in np.linspace(0.04, 0.96, 14)] + [(0, z1 - 0.02)]
    it.lathe("Leaves", "Leaf", prof, segs=14)
    n = 210
    for i in range(n):
        t = (i + rnd.random()) / n
        t = 0.03 + 0.94 * t
        a = rnd.random() * 2 * PI
        r = rad(t)
        s = rnd.uniform(0.04, 0.06)
        it.add("Leaves", "Leaf", bm_ico(s, 1), (r * math.cos(a), r * math.sin(a), z0 + (z1 - z0) * t),
               (rnd.random() * PI, rnd.random() * PI, 0), (1, rnd.uniform(0.6, 0.9), rnd.uniform(0.6, 0.9)))


def painting_texture(path, W=640, H=500):
    rnd = np.random.default_rng(3)
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    img = np.zeros((H, W, 3))
    sky = np.array([0.28, 0.27, 0.24]) * (1 - y) + np.array([0.52, 0.49, 0.42]) * y      # y=0 низ? (пиксели снизу)
    img[:] = sky[:, None, :] if sky.ndim == 2 else sky
    img = np.broadcast_to(sky[:, None, :], (H, W, 3)).copy()
    # дальние холмы
    hills = 0.42 + 0.05 * np.sin(x * 7 + 1) + 0.03 * np.sin(x * 17)
    img[(y < hills).repeat(1, 0) if False else (y < hills)] = [0.22, 0.24, 0.2]
    ground = 0.3 + 0.02 * np.sin(x * 5)
    img[y < ground] = [0.17, 0.17, 0.12]
    road = np.abs(x - (0.55 - 0.25 * (0.3 - y))) < (0.3 - y) * 0.35
    img[(y < 0.3) & road] = [0.32, 0.3, 0.24]
    # деревья: тёмные силуэты-конусы и кроны
    yy, xx = np.mgrid[0:H, 0:W]
    yy = yy / H
    xx = xx / W
    for _ in range(26):
        cx = rnd.uniform(0, 1)
        if 0.42 < cx < 0.62 and rnd.random() < 0.7:
            continue
        base = rnd.uniform(0.27, 0.36)
        hgt = rnd.uniform(0.25, 0.55) * (1.3 if abs(cx - 0.5) > 0.3 else 0.8)
        wid = hgt * rnd.uniform(0.2, 0.35)
        shade = rnd.uniform(0.07, 0.14)
        t = (yy - base) / hgt
        m = (t > 0) & (t < 1) & (np.abs(xx - cx) < wid * (1 - t) * (0.85 + 0.15 * np.sin(yy * 120 + cx * 9)))
        img[m] = [shade, shade * 1.15, shade * 0.9]
        trunk = (yy > base - 0.02) & (yy < base + 0.05) & (np.abs(xx - cx) < 0.004)
        img[trunk] = [0.08, 0.06, 0.05]
    img += rnd.normal(0, 0.015, img.shape)
    vign = 1 - 0.5 * ((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
    img *= vign[..., None]
    img = np.clip(img, 0, 1)
    px = np.concatenate([img, np.ones((H, W, 1))], axis=2)
    im = bpy.data.images.new("Painting_Canvas", W, H)
    im.pixels = px.astype(np.float32).ravel()
    im.filepath_raw = path
    im.file_format = 'PNG'
    im.save()
    return im


def painting(it, tex_path):
    W, H, cz = 1.0, 0.8, 0.4
    prof = [(0, 0), (0, 0.03), (0.012, 0.045), (0.025, 0.042), (0.04, 0.052), (0.06, 0.04), (0.075, 0.028),
            (0.085, 0.022), (0.09, 0.012)]
    it.add("Frame", "Wood", bm_rect_sweep(W, H, prof), (0, 0, cz))
    it.bx("Frame", "Wood", (-W / 2, W / 2), (0, 0.006), (cz - H / 2, cz + H / 2), 0.002)
    cw, ch = W / 2 - 0.09, H / 2 - 0.09
    bm = vf_bm([(-cw, 0, -ch), (cw, 0, -ch), (cw, 0, ch), (-cw, 0, ch)], [[0, 1, 2, 3]], recalc=False)
    it.add("Canvas", "Canvas", bm, (0, -0.012, cz), uvs=[[(0, 0), (1, 0), (1, 1), (0, 1)]])
    painting_texture(tex_path)


def floor_lamp(it):
    prof = [(0, 0), (0.16, 0), (0.16, 0.018), (0.14, 0.032), (0.09, 0.05), (0.05, 0.07), (0.03, 0.09), (0.026, 0.25),
            (0.042, 0.3), (0.046, 0.33), (0.03, 0.37), (0.022, 0.6), (0.036, 0.64), (0.022, 0.68), (0.02, 1.0),
            (0.035, 1.05), (0.02, 1.1), (0.018, 1.14), (0, 1.14)]
    it.lathe("Body", "Wood", prof, segs=16)
    it.cyl("Trim", "Brass", 0.022, 0.08, (0, 0, 1.18))
    it.lathe("Trim", "Brass", [(0, 1.42), (0.012, 1.425), (0.018, 1.44), (0.01, 1.455), (0, 1.46)], segs=10)
    it.lathe("Shade", "Shade", [(0.26, 1.1), (0.15, 1.42), (0.144, 1.418), (0.254, 1.102)], segs=8, closed=True, phase=PI / 8)


def table_lamp(it):
    prof = [(0, 0), (0.1, 0), (0.1, 0.016), (0.08, 0.03), (0.05, 0.042), (0.03, 0.06), (0.058, 0.12), (0.074, 0.18),
            (0.06, 0.24), (0.026, 0.28), (0.02, 0.31), (0.03, 0.33), (0.015, 0.35), (0, 0.35)]
    it.lathe("Body", "Wood", prof, segs=8, phase=PI / 8)
    it.cyl("Trim", "Brass", 0.016, 0.06, (0, 0, 0.37))
    it.lathe("Shade", "Shade", [(0.19, 0.33), (0.11, 0.58), (0.104, 0.578), (0.184, 0.332)], segs=8, closed=True, phase=PI / 8)


def chest(it, W, D, H, nd, knobs, leg=0.07):
    w, y0, y1 = W / 2, -D / 2, D / 2
    B = "Body"
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.bx(B, "Wood", (sx * (w - 0.04) - 0.045, sx * (w - 0.04) + 0.045),
                  (sy * (D / 2 - 0.04) - 0.045, sy * (D / 2 - 0.04) + 0.045), (0, leg + 0.01), 0.008)
    zc = leg + 0.05
    it.bx(B, "Wood", (-w - 0.015, w + 0.015), (y0 - 0.018, y1 + 0.005), (leg, zc), 0.007)
    zt = H - 0.035
    it.bx(B, "Wood", (-w - 0.025, w + 0.025), (y0 - 0.028, y1 + 0.012), (zt, H), 0.01, 2)
    it.bx(B, "Wood", (-w, -w + 0.025), (y0, y1), (zc, zt))
    it.bx(B, "Wood", (w - 0.025, w), (y0, y1), (zc, zt))
    it.bx(B, "Wood", (-w, w), (y1 - 0.02, y1), (zc, zt))
    it.bx(B, "Wood", (-w, w), (y0, y1), (zc, zc + 0.02))
    it.bx(B, "Wood", (-w - 0.008, -w + 0.035), (y0 - 0.01, y0 + 0.02), (zc, zt), 0.004)          # стойки рамы
    it.bx(B, "Wood", (w - 0.035, w + 0.008), (y0 - 0.01, y0 + 0.02), (zc, zt), 0.004)
    rail = 0.025
    hz = (zt - zc - (nd + 1) * rail) / nd
    for i in range(nd + 1):
        z = zc + i * (hz + rail)
        it.bx(B, "Wood", (-w + 0.03, w - 0.03), (y0 - 0.008, y0 + 0.02), (z, z + rail), 0.003)
    for i in range(nd):
        z0 = zc + rail + i * (hz + rail) + 0.004
        z1 = z0 + hz - 0.008
        name = f"Drawer{nd - i}"
        xa, xb = -w + 0.04, w - 0.04
        it.bx(name, "Wood", (xa, xb), (y0 - 0.024, y0), (z0, z1), 0.005)
        it.bx(name, "Wood", (xa + 0.05, xb - 0.05), (y0 - 0.033, y0 - 0.024), (z0 + 0.04, z1 - 0.04), 0.009, 2)
        dd = D * 0.72
        it.bx(name, "Wood", (xa + 0.01, xb - 0.01), (y0, y0 + dd), (z0 + 0.01, z0 + 0.022))
        it.bx(name, "Wood", (xa + 0.01, xa + 0.022), (y0, y0 + dd), (z0 + 0.01, z1 - 0.03))
        it.bx(name, "Wood", (xb - 0.022, xb - 0.01), (y0, y0 + dd), (z0 + 0.01, z1 - 0.03))
        it.bx(name, "Wood", (xa + 0.01, xb - 0.01), (y0 + dd - 0.012, y0 + dd), (z0 + 0.01, z1 - 0.03))
        xs = [0.0] if knobs == 1 else [-W * 0.26, W * 0.26]
        for x in xs:
            knob(it, f"{name}_Knobs", "Brass", (x, y0 - 0.033, (z0 + z1) / 2), 0.02, 0.04)
        it.behaviors.append((f"{it.name}_{name}", "slide"))


def dresser(it):
    chest(it, 1.5, 0.55, 0.85, 2, 2)


def nightstand(it):
    chest(it, 0.62, 0.45, 0.62, 2, 2, leg=0.06)


def coffee_table(it):
    it.lathe("Body", "Wood", [(0, 0.515), (0.36, 0.515), (0.374, 0.521), (0.38, 0.533), (0.375, 0.547), (0.36, 0.553),
                              (0, 0.553)], segs=48)
    it.lathe("Body", "Wood", [(0, 0.08), (0.075, 0.08), (0.075, 0.1), (0.05, 0.12), (0.04, 0.16), (0.062, 0.22),
                              (0.066, 0.26), (0.045, 0.32), (0.034, 0.4), (0.05, 0.45), (0.12, 0.49), (0.2, 0.5),
                              (0.2, 0.515), (0, 0.515)], segs=24)
    for k in range(4):
        a = PI / 4 + k * PI / 2
        pts = [(r * math.cos(a), r * math.sin(a), z) for r, z in
               [(0.03, 0.17), (0.1, 0.15), (0.17, 0.11), (0.23, 0.065), (0.28, 0.04), (0.31, 0.04)]]
        it.tube("Body", "Wood", pts, 0.032, r_end=0.022)
        it.cyl("Body", "Wood", 0.03, 0.03, (0.31 * math.cos(a), 0.31 * math.sin(a), 0.015))


def bench(it):
    it.bx("Seat", "Fabric", (-0.6, 0.6), (-0.21, 0.21), (0.37, 0.48), 0.035, 4)
    it.bx("Body", "Wood", (-0.585, 0.585), (-0.195, 0.195), (0.29, 0.375), 0.006)
    it.bx("Body", "Wood", (-0.592, 0.592), (-0.202, 0.202), (0.29, 0.305), 0.004)
    prof = [(0, 0), (0.024, 0), (0.03, 0.02), (0.021, 0.06), (0.03, 0.12), (0.036, 0.16), (0.026, 0.2), (0.032, 0.24),
            (0.036, 0.28), (0.036, 0.375), (0, 0.375)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.lathe("Body", "Wood", prof, (sx * 0.545, sy * 0.155, 0), segs=12)
    it.tube("Body", "Wood", [(-0.545, 0, 0.12), (0.545, 0, 0.12)], 0.016)
    for sx in (-1, 1):
        it.tube("Body", "Wood", [(sx * 0.545, -0.155, 0.12), (sx * 0.545, 0.155, 0.12)], 0.016)
    for x in np.linspace(-0.45, 0.45, 4):                        # стёжка — пуговицы
        for y in (-0.08, 0.08):
            it.add("Buttons", "FabricDark", bm_sphere(0.012, 8, 6), (x, y, 0.481), scale=(1, 1, 0.5))


def text_mesh(text, size, depth):
    cu = bpy.data.curves.new("txt", 'FONT')
    cu.body, cu.size, cu.extrude = text, size, depth
    cu.align_x, cu.align_y = 'CENTER', 'CENTER'
    o = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(o)
    dg = bpy.context.evaluated_depsgraph_get()
    m = o.evaluated_get(dg).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(m)
    o.evaluated_get(dg).to_mesh_clear()
    bpy.data.objects.remove(o)
    return bm


def door(it):
    B = "Body"
    it.bx(B, "Wood", (-0.55, -0.48), (-0.06, 0.06), (0, 2.2))
    it.bx(B, "Wood", (0.48, 0.55), (-0.06, 0.06), (0, 2.2))
    it.bx(B, "Wood", (-0.55, 0.55), (-0.06, 0.06), (2.13, 2.2))
    for y0, y1 in ((-0.085, -0.06), (0.06, 0.085)):
        it.bx(B, "Wood", (-0.6, -0.48), (y0, y1), (0, 2.18), 0.006)
        it.bx(B, "Wood", (0.48, 0.6), (y0, y1), (0, 2.18), 0.006)
        it.bx(B, "Wood", (-0.62, 0.62), (y0 - 0.005 if y0 < 0 else y0, y1 + 0.005 if y1 > 0 else y1), (2.13, 2.27), 0.008)
        it.bx(B, "Wood", (-0.64, 0.64), (y0 - 0.015 if y0 < 0 else y0, y1 + 0.015 if y1 > 0 else y1), (2.27, 2.3), 0.006)
    L = "Leaf"
    it.bx(L, "Wood", (-0.476, 0.476), (-0.022, 0.022), (0.012, 2.126), 0.004)
    for sgn in (-1, 1):
        ya, yb = (-0.031, -0.022) if sgn < 0 else (0.022, 0.031)
        for z0, z1 in ((0.18, 0.95), (1.1, 1.96)):
            it.bx(L, "Wood", (-0.34, 0.34), (ya, yb), (z0, z1), 0.012, 2)
    it.bx("Leaf_Plate", "Brass", (-0.12, 0.12), (-0.04, -0.031), (1.64, 1.74), 0.006, 2)
    bm = text_mesh("0001", 0.075, 0.002)
    it.add("Leaf_Number", "Black", bm, (0, -0.042, 1.69), (PI / 2, 0, 0))
    H = "Leaf_Handle"
    for sgn in (-1, 1):
        yb = -0.022 if sgn < 0 else 0.022
        it.bx(H, "Brass", (0.33, 0.39), (yb + sgn * 0.008, yb), (0.93, 1.13), 0.006)
        it.cyl(H, "Brass", 0.012, 0.035, (0.36, yb + sgn * 0.025, 1.04), (PI / 2, 0, 0))
        it.bx(H, "Brass", (0.24, 0.372), (yb + sgn * 0.035, yb + sgn * 0.05), (1.03, 1.05), 0.005)
        it.cyl(H, "Brass", 0.006, 0.02, (0.36, yb + sgn * 0.015, 0.97), (PI / 2, 0, 0))   # скважина
    it.behaviors.append((f"{it.name}_{L}", "hinge"))


def fireplace(it):
    B = "Body"
    it.bx(B, "Wood", (-0.84, 0.84), (-0.3, 0.22), (0, 0.08), 0.01)
    for sx in (-1, 1):
        xa, xb = sorted((sx * 0.5, sx * 0.8))
        it.bx(B, "Wood", (xa, xb), (-0.2, 0.2), (0.08, 0.98), 0.005)
        it.bx(B, "Wood", (xa + 0.06, xb - 0.06), (-0.215, -0.2), (0.18, 0.86), 0.01, 2)
        it.bx(B, "Wood", (xa - 0.01, xb + 0.01), (-0.215, 0.2), (0.08, 0.15), 0.006)
    it.bx(B, "Wood", (-0.5, 0.5), (-0.2, 0.2), (0.73, 0.98), 0.004)
    it.bx(B, "Wood", (-0.42, 0.42), (-0.212, -0.2), (0.78, 0.93), 0.008, 2)
    it.bx(B, "Wood", (-0.88, 0.88), (-0.27, 0.21), (0.98, 1.03), 0.012, 2)
    it.bx(B, "Wood", (-0.82, 0.82), (-0.22, 0.2), (1.03, 1.1), 0.005)
    it.bx(B, "Wood", (-0.85, 0.85), (-0.24, 0.21), (1.1, 1.13), 0.008)
    it.bx("Back", "Mortar", (-0.5, 0.5), (0.12, 0.2), (0.08, 0.73))
    it.bx("Back", "Mortar", (-0.5, 0.5), (-0.2, 0.12), (0.7, 0.73))
    for sx in (-1, 1):
        it.bx("Bricks", "Brick", sorted((sx * 0.5, sx * 0.47)), (-0.2, 0.12), (0.08, 0.7))
    bw, bh, gap = 0.19, 0.055, 0.012
    row = 0
    z = 0.08 + gap
    while z + bh < 0.7:
        x = -0.5 + (0 if row % 2 == 0 else -bw / 2)
        while x < 0.5:
            xa, xb = max(x, -0.47), min(x + bw, 0.47)
            if xb - xa > 0.03:
                it.bx("Bricks", "Brick", (xa, xb), (0.1, 0.12), (z, z + bh), 0.004)
            x += bw + gap
        z += bh + gap
        row += 1
    for x in (-0.18, 0.18):
        it.tube("Grate", "Iron", [(x, -0.12, 0.08), (x, -0.12, 0.14), (x, -0.08, 0.13), (x, 0.08, 0.13)], 0.012)
    it.tube("Grate", "Iron", [(-0.22, -0.02, 0.13), (0.22, -0.02, 0.13)], 0.01)
    for (y, z, a) in ((-0.03, 0.17, 0.05), (0.06, 0.17, -0.05), (0.015, 0.245, 0.0)):
        it.cyl("Logs", "Log", 0.045, 0.46, (0, y, z), (0, PI / 2, a), segs=10)
    rnd = random.Random(5)
    for i in range(9):
        x = -0.16 + 0.32 * i / 8 + rnd.uniform(-0.02, 0.02)
        h = rnd.uniform(0.16, 0.3) * (1.2 - abs(x) * 2)
        r = rnd.uniform(0.035, 0.06)
        it.add("Fire", "Fire", bm_cyl(r, h, 6, 0.004), (x, rnd.uniform(-0.03, 0.05), 0.24 + h / 2),
               (rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), 0), (1, 0.6, 1))


def clock(it):
    B = "Body"
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.bx(B, "Wood", (sx * 0.22 - 0.045, sx * 0.22 + 0.045), (sy * 0.12 - 0.045, sy * 0.12 + 0.045), (0, 0.05), 0.008)
    it.bx(B, "Wood", (-0.27, 0.27), (-0.175, 0.17), (0.05, 0.09), 0.008)
    it.bx(B, "Wood", (-0.25, 0.25), (-0.155, 0.155), (0.09, 0.4), 0.005)
    it.bx(B, "Wood", (-0.17, 0.17), (-0.167, -0.155), (0.14, 0.35), 0.01, 2)
    it.bx(B, "Wood", (-0.24, 0.24), (-0.165, 0.16), (0.4, 0.44), 0.008)
    it.bx(B, "Wood", (-0.19, 0.19), (0.11, 0.13), (0.44, 1.32))
    for sx in (-1, 1):
        it.bx(B, "Wood", sorted((sx * 0.17, sx * 0.19)), (-0.13, 0.13), (0.44, 1.32))
        it.bx(B, "Wood", sorted((sx * 0.13, sx * 0.195)), (-0.14, -0.11), (0.44, 1.32), 0.004)
    it.bx(B, "Wood", (-0.13, 0.13), (-0.14, -0.11), (0.44, 0.52), 0.004)
    it.bx(B, "Wood", (-0.13, 0.13), (-0.14, -0.11), (1.24, 1.32), 0.004)
    it.bx("Glass", "Glass", (-0.13, 0.13), (-0.125, -0.12), (0.52, 1.24), 0.0)
    it.bx(B, "Wood", (-0.245, 0.245), (-0.17, 0.155), (1.32, 1.36), 0.008)
    it.bx(B, "Wood", (-0.22, 0.22), (-0.14, 0.14), (1.36, 1.86), 0.004)
    for sx in (-1, 1):
        it.cyl(B, "Wood", 0.018, 0.48, (sx * 0.205, -0.15, 1.61), segs=12)
    it.bx(B, "Wood", (-0.245, 0.245), (-0.17, 0.155), (1.86, 1.89), 0.008)
    top = lambda x: 1.93 + 0.08 * math.cos(PI / 2 * x / 0.24)
    it.prism(B, "Wood", [(-0.24, 1.89), (0.24, 1.89)] + [(x, top(x)) for x in np.linspace(0.24, -0.24, 20)], -0.165, 0.15)
    it.tube(B, "Wood", [(x, -0.17, top(x)) for x in np.linspace(0.24, -0.24, 20)], 0.012)
    fin = [(0, 0), (0.02, 0.0), (0.012, 0.02), (0.022, 0.04), (0.012, 0.06), (0.005, 0.09), (0, 0.1)]
    for x, z in ((-0.22, 1.89 + 0.01), (0.22, 1.89 + 0.01), (0, 2.01)):
        it.lathe("Brass", "Brass", [(r, zz + z) for r, zz in fin], (x, 0, 0), segs=10)
    fz = 1.61
    it.cyl("Face", "Paper", 0.15, 0.012, (0, -0.146, fz), (PI / 2, 0, 0), segs=40)
    it.add("Brass", "Brass", bm_torus(0.152, 0.01, 40, 8), (0, -0.152, fz), (PI / 2, 0, 0))
    for k in range(12):
        a = k * PI / 6
        L = 0.03 if k % 3 == 0 else 0.018
        it.box_at("Numerals", "Black", (0.008 if k % 3 == 0 else 0.005, 0.003, L),
                  (0.118 * math.sin(a), -0.1535, fz + 0.118 * math.cos(a)), (0, a, 0), bev=0)
    it.cyl("Numerals", "Black", 0.008, 0.008, (0, -0.16, fz), (PI / 2, 0, 0), segs=10)
    it.bx("HourHand", "Black", (-0.006, 0.006), (-0.158, -0.155), (fz - 0.015, fz + 0.075), 0)
    it.bx("MinuteHand", "Black", (-0.004, 0.004), (-0.162, -0.159), (fz - 0.02, fz + 0.115), 0)
    it.bx("Pendulum", "Brass", (-0.005, 0.005), (-0.005, 0.005), (0.78, 1.3), 0.001)
    it.cyl("Pendulum", "Brass", 0.07, 0.012, (0, 0, 0.75), (PI / 2, 0, 0), segs=28)
    for x in (-0.08, 0.08):
        it.cyl("Weights", "Brass", 0.025, 0.2, (x, 0.05, 1.05), segs=14)
        it.tube("Weights", "Brass", [(x, 0.05, 1.15), (x, 0.05, 1.32)], 0.002, segs=4)
    it.behaviors.append((f"{it.name}_Pendulum", "pendulum"))
    it.behaviors.append((f"{it.name}_HourHand", "hour"))
    it.behaviors.append((f"{it.name}_MinuteHand", "minute"))


def mirror(it):
    S = "Stand"
    for sx in (-1, 1):
        x = sx * 0.33
        it.bx(S, "Wood", (x - 0.03, x + 0.03), (-0.22, 0.22), (0.0, 0.05), 0.012, 2)
        it.lathe(S, "Wood", [(0, 0.05), (0.03, 0.05), (0.03, 0.1), (0.02, 0.14), (0.018, 1.0), (0.026, 1.05),
                             (0.02, 1.1), (0.024, 1.18), (0.012, 1.22), (0, 1.23)], (x, 0, 0), segs=12)
        it.cyl("Pins", "Brass", 0.014, 0.05, (sx * 0.295, 0, 0.82), (0, PI / 2, 0), segs=10)
    it.tube(S, "Wood", [(-0.33, 0, 0.14), (0.33, 0, 0.14)], 0.016)

    def outline(w, z0, z1, a, n=24):
        return [(-w, z0), (w, z0)] + arc(0, z1, w, a, 0, PI, n)
    outer = outline(0.27, 0.22, 1.32, 0.22)
    inner = outline(0.225, 0.265, 1.32, 0.175)
    it.add("Frame", "Wood", bm_ring_prism(outer, inner, -0.022, 0.022))
    it.add("Glass", "Mirror", bm_prism(inner, -0.006, 0.006))


def luggage_rack(it):
    F = "Frame"
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.bx(F, "Wood", (sx * 0.43 - 0.02, sx * 0.43 + 0.02), (sy * 0.2 - 0.02, sy * 0.2 + 0.02), (0.1, 1.3), 0.004)
    for z in (0.18, 0.6, 1.0):
        it.bx(F, "Wood", (-0.46, 0.46), (-0.23, 0.23), (z, z + 0.028), 0.006)
        it.bx(F, "Wood", (-0.43, 0.43), (0.19, 0.21), (z + 0.028, z + 0.07), 0.003)
        for sx in (-1, 1):
            it.bx(F, "Wood", sorted((sx * 0.41, sx * 0.45)), (-0.2, 0.2), (z + 0.028, z + 0.06), 0.003)
    it.bx(F, "Wood", (-0.46, 0.46), (-0.23, 0.23), (0.1, 0.13), 0.004)
    for sx in (-1, 1):
        it.tube(F, "Wood", [(sx * 0.43, -0.2, 1.3), (sx * 0.43, 0.2, 1.42)], 0.02)
        it.tube(F, "Wood", [(sx * 0.43, 0.2, 1.3), (sx * 0.43, 0.2, 1.42)], 0.02)
    it.tube(F, "Wood", [(-0.45, 0.2, 1.42), (0.45, 0.2, 1.42)], 0.022)
    it.tube(F, "Wood", [(-0.43, -0.2, 1.3), (0.43, -0.2, 1.3)], 0.016)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 0.4, sy * 0.18
            it.cyl("Casters", "Brass", 0.025, 0.01, (x, y, 0.095))
            it.bx("Casters", "Brass", (x - 0.008, x + 0.008), (y - 0.02, y + 0.02), (0.05, 0.09), 0.002)
            it.cyl("Wheels", "Iron", 0.045, 0.025, (x, y, 0.046), (PI / 2, 0, 0), segs=14)
    suitcase(it, "Case1_", (0.72, 0.4, 0.3), (0, 0, 0.208))
    suitcase(it, "Case2_", (0.62, 0.37, 0.25), (0.02, 0.0, 0.628))


def curtain_sheet(xo, xi, z0, z1, ytop, tie_z, cols=44, rows=36):
    verts, faces = [], []

    def g(z):
        s = 0.55 if z > tie_z else 0.3
        return 1 - 0.62 * math.exp(-((z - tie_z) / s) ** 2)
    for layer in (0, 1):
        for j in range(rows + 1):
            z = z0 + (z1 - z0) * j / rows
            gz = g(z)
            for i in range(cols + 1):
                u = i / cols
                x = xo + (xi - xo) * u * gz
                A = 0.03 + 0.045 * (1 - gz)
                y = ytop - A * math.sin(2 * PI * 6 * u) - 0.02 * (1 - u)
                verts.append((x, y + layer * 0.007, z))
    n = (cols + 1) * (rows + 1)
    for j in range(rows):
        for i in range(cols):
            a = j * (cols + 1) + i
            q = [a, a + 1, a + cols + 2, a + cols + 1]
            faces.append(q)
            faces.append([n + v for v in reversed(q)])
    bm = vf_bm(verts, faces, recalc=False)
    # первый слой должен смотреть вперёд (-Y): проверка по средней нормали
    bm.faces.ensure_lookup_table()
    ny = sum(f.normal.y for f in list(bm.faces)[0::2])
    if ny > 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return bm, g(tie_z)


def curtains(it):
    it.bx("Pelmet", "Wood", (-0.92, 0.92), (-0.16, 0.0), (2.1, 2.24), 0.008)
    it.bx("Pelmet", "Wood", (-0.95, 0.95), (-0.18, 0.0), (2.24, 2.28), 0.008)
    it.bx("Pelmet", "Wood", (-0.94, 0.94), (-0.172, -0.15), (2.12, 2.14), 0.004)
    it.cyl("Rod", "Brass", 0.014, 1.8, (0, -0.07, 2.08), (0, PI / 2, 0), segs=12)
    for sx in (-1, 1):
        it.add("Rod", "Brass", bm_sphere(0.028, 12, 8), (sx * 0.92, -0.07, 2.08))
    for side, name in ((-1, "Left"), (1, "Right")):
        xo, xi = side * 0.82, side * 0.06
        bm, gt = curtain_sheet(xo, xi, 0.02, 2.1, -0.07, 1.0)
        it.add(name, "Fabric", bm)
        wid = abs(xi - xo) * gt
        cx = xo + (xi - xo) * gt / 2
        it.add("Tiebacks", "Brass", bm_torus(0.05, 0.012, 28, 6), (cx, -0.08, 1.0), (0, 0, 0),
               ((wid / 2 + 0.02) / 0.05, (0.09) / 0.05, 1.6))


def clip_poly(poly, xmin, xmax, zmin, zmax):
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out

    def ix(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))

    def iz(a, b, z):
        t = (z - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), z)
    p = poly
    for ins, it_ in ((lambda q: q[0] >= xmin, lambda a, b: ix(a, b, xmin)), (lambda q: q[0] <= xmax, lambda a, b: ix(a, b, xmax)),
                     (lambda q: q[1] >= zmin, lambda a, b: iz(a, b, zmin)), (lambda q: q[1] <= zmax, lambda a, b: iz(a, b, zmax))):
        if not p:
            break
        p = clip(p, ins, it_)
    return p


def wall_panel(it):
    W, H = 1.2, 1.3
    B = "Body"
    it.bx(B, "Wood", (-W / 2, W / 2), (0, 0.025), (0.0, H))
    prof = [(0, 0), (0, 0.035), (0.012, 0.05), (0.03, 0.045), (0.045, 0.055), (0.06, 0.04), (0.075, 0.03), (0.08, 0.008)]
    it.add(B, "Wood", bm_rect_sweep(W, H - 0.1, prof), (0, 0, 0.1 + (H - 0.1) / 2))
    it.bx(B, "Wood", (-W / 2 - 0.02, W / 2 + 0.02), (-0.05, 0.025), (0, 0.1), 0.006)
    it.bx(B, "Wood", (-W / 2 - 0.03, W / 2 + 0.03), (-0.065, 0.025), (H - 0.02, H + 0.03), 0.008)
    xmin, xmax, zmin, zmax = -W / 2 + 0.08, W / 2 - 0.08, 0.18, H - 0.08
    dw, dh = 0.26, 0.36
    cols = int((xmax - xmin) / dw) + 2
    rows = int((zmax - zmin) / dh) + 2
    for r in range(-1, rows + 1):
        for c in range(-1, cols + 1):
            for half in (0, 1):
                cx = (xmin + xmax) / 2 + (c - cols / 2) * dw + half * dw / 2
                cz = zmin + r * dh + half * dh / 2
                d = [(cx, cz - dh / 2 + 0.006), (cx + dw / 2 - 0.006, cz), (cx, cz + dh / 2 - 0.006), (cx - dw / 2 + 0.006, cz)]
                p = clip_poly(d, xmin, xmax, zmin, zmax)
                if len(p) < 3:
                    continue
                verts = [(x, 0, z) for x, z in p]
                bm = vf_bm(verts, [list(range(len(p)))], recalc=False)
                it.add("Diamonds" if half == 0 else "DiamondsDark", "Fabric" if half == 0 else "FabricDark",
                       bm, (0, -0.004, 0))


# ============================================================================= второй набор (люстра, ковёр, бра, столы, часы)
ROMAN = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]


def roman_dial(it, part, center, radius, size, y):
    """Римские цифры по кругу на циферблате, плоскость XZ, лицом в -Y."""
    cx, cz = center
    for k, s in enumerate(ROMAN):
        a = k * PI / 6
        it.add(part, "Black", text_mesh(s, size, 0.0008),
               (cx + radius * math.sin(a), y, cz + radius * math.cos(a)), (PI / 2, 0, 0))


def clock_hands(it, center, y, hour_len, min_len, w=1.0):
    cx, cz = center
    it.bx("HourHand", "Black", (cx - 0.006 * w, cx + 0.006 * w), (y - 0.003, y), (cz - 0.015, cz + hour_len), 0)
    it.add("HourHand", "Black", bm_prism(arc(cx, cz + hour_len * 0.75, 0.018 * w, 0.025 * w, 0, 2 * PI, 12)[:-1], y - 0.003, y))
    it.bx("MinuteHand", "Black", (cx - 0.004 * w, cx + 0.004 * w), (y - 0.007, y - 0.004), (cz - 0.02, cz + min_len), 0)
    it.add("MinuteHand", "Black", bm_prism(arc(cx, cz + min_len * 0.8, 0.012 * w, 0.02 * w, 0, 2 * PI, 12)[:-1], y - 0.007, y - 0.004))
    it.behaviors.append((f"{it.name}_HourHand", "hour"))
    it.behaviors.append((f"{it.name}_MinuteHand", "minute"))


def chandelier(it):
    B = "Body"
    it.lathe(B, "Wood", [(0, 0.0), (0.012, 0.01), (0.03, 0.04), (0.02, 0.08), (0.035, 0.11), (0.09, 0.15), (0.12, 0.2),
                         (0.11, 0.25), (0.07, 0.28), (0.035, 0.3), (0.05, 0.34), (0.03, 0.38), (0.022, 0.45),
                         (0.04, 0.5), (0.025, 0.54), (0.035, 0.57), (0.012, 0.6), (0, 0.61)], segs=20)
    z = 0.6
    for i in range(11):                                         # цепь
        it.add("Chain", "Iron", bm_torus(0.022, 0.0055, 14, 6), (0, 0, z + 0.022), (PI / 2, 0, PI / 2 * (i % 2)))
        z += 0.04
    it.lathe(B, "Wood", [(0, z + 0.02), (0.03, z + 0.02), (0.08, z + 0.05), (0.085, z + 0.07), (0, z + 0.07)], segs=20)
    for k in range(6):
        a = k * PI / 3
        ca, sa = math.cos(a), math.sin(a)
        pts = [(r * ca, r * sa, zz) for r, zz in [(0.09, 0.22), (0.16, 0.18), (0.24, 0.17), (0.31, 0.2), (0.35, 0.26),
                                                  (0.36, 0.32)]]
        it.tube("Arms", "Wood", pts, 0.016, r_end=0.012)
        it.tube("Arms", "Wood", [(r * ca, r * sa, zz) for r, zz in [(0.12, 0.27), (0.17, 0.3), (0.2, 0.28), (0.21, 0.24)]], 0.008)
        x, y = 0.36 * ca, 0.36 * sa
        it.lathe("Arms", "Wood", [(0, 0.31), (0.012, 0.31), (0.05, 0.33), (0.052, 0.34), (0.03, 0.34), (0.026, 0.37),
                                  (0, 0.37)], (x, y, 0), segs=14)
        it.cyl("Candles", "Wax", 0.016, 0.12, (x, y, 0.43), segs=12)
        it.add("Candles", "Wax", bm_sphere(0.006, 6, 4), (x + 0.015 * ca, y + 0.015 * sa, 0.46), scale=(1, 1, 2.5))
        it.add("Flames", "Flame", bm_sphere(0.012, 8, 6), (x, y, 0.505), scale=(0.7, 0.7, 2.0))
    it.behaviors.append((f"{it.name}_Flames", "light"))


def rug_texture(path, W=1024, H=720):
    rnd = np.random.default_rng(11)
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    u, v = xx / W, yy / H
    img = np.zeros((H, W, 3))
    img[:] = [0.42, 0.07, 0.09]
    d = np.abs((u * 14) % 1 - 0.5) + np.abs((v * 10) % 1 - 0.5)
    img[d < 0.3] = [0.3, 0.04, 0.06]
    img[(d > 0.22) & (d < 0.27)] = [0.55, 0.32, 0.18]
    img[d < 0.07] = [0.62, 0.42, 0.22]
    e = ((u - 0.5) / 0.2) ** 2 + ((v - 0.5) / 0.28) ** 2
    img[e < 1.0] = [0.2, 0.03, 0.05]
    img[(e > 0.88) & (e < 1.0)] = [0.62, 0.42, 0.22]
    ring = (e > 0.45) & (e < 0.55)
    img[ring] = [0.5, 0.1, 0.1]
    pet = np.abs(np.sin(np.arctan2(v - 0.5, u - 0.5) * 8)) * 0.35
    img[(e < pet + 0.12)] = [0.48, 0.09, 0.1]
    img[e < 0.05] = [0.62, 0.42, 0.22]
    b = np.minimum(np.minimum(xx, W - 1 - xx), np.minimum(yy, H - 1 - yy))
    along = np.where(np.minimum(yy, H - 1 - yy) <= np.minimum(xx, W - 1 - xx), xx, yy)
    t = (b - 22) / 46.0
    img[b < 70] = [0.16, 0.03, 0.04]
    zig = np.abs(((along / 36) % 1) - 0.5) * 2
    img[(b >= 22) & (b < 68) & (np.abs(zig - t) < 0.14)] = [0.62, 0.42, 0.22]
    img[(b >= 14) & (b < 19)] = [0.62, 0.42, 0.22]
    img[(b >= 70) & (b < 75)] = [0.62, 0.42, 0.22]
    img[b < 6] = [0.12, 0.02, 0.03]
    img *= (1 + rnd.normal(0, 0.06, (H, W)))[..., None]
    wear = np.exp(-(((u - 0.4) / 0.25) ** 2 + ((v - 0.55) / 0.3) ** 2))
    img *= (1 - 0.18 * wear)[..., None]
    img *= 0.62                                   # тёмный бордовый, как на референсе
    img = np.clip(img, 0, 1)
    px = np.concatenate([img, np.ones((H, W, 1))], axis=2)
    im = bpy.data.images.new("Rug_Pattern", W, H)
    im.pixels = px.astype(np.float32).ravel()
    im.filepath_raw = path
    im.file_format = 'PNG'
    im.save()


def rug(it, tex_path):
    L, Wd = 2.2, 1.55
    it.bx("Body", "Rug", (-L / 2, L / 2), (-Wd / 2, Wd / 2), (0, 0.01), 0.003)
    bm = vf_bm([(-L / 2, -Wd / 2, 0), (L / 2, -Wd / 2, 0), (L / 2, Wd / 2, 0), (-L / 2, Wd / 2, 0)], [[0, 1, 2, 3]], recalc=False)
    it.add("Body", "Rug", bm, (0, 0, 0.0115), uvs=[[(0, 0), (1, 0), (1, 1), (0, 1)]])
    rug_texture(tex_path)


def bm_pleated(rb, rt, z0, z1, n=28, amp=0.06, wall=0.004):
    verts, faces = [], []
    for layer, dr in ((0, 0.0), (1, -wall)):
        for z, r in ((z0, rb), (z1, rt)):
            for k in range(n):
                a = 2 * PI * k / n
                rr = (r + dr) * (1 + amp * (1 if k % 2 == 0 else -1))
                verts.append((rr * math.cos(a), rr * math.sin(a), z))
    O0, O1, I0, I1 = 0, n, 2 * n, 3 * n
    for k in range(n):
        j = (k + 1) % n
        faces += [[O0 + k, O0 + j, O1 + j, O1 + k], [I0 + k, I1 + k, I1 + j, I0 + j],
                  [O0 + k, I0 + k, I0 + j, O0 + j], [O1 + k, O1 + j, I1 + j, I1 + k]]
    return vf_bm(verts, faces)


def catmull(pts, n=10):
    """Гладкая кривая Катмулла-Рома через точки (для изогнутых рожков и завитков)."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                                    (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
    out.append(tuple(P[-2]))
    return out


def sconce(it):
    """Бра: резная картушная пластина, розетка, завитки, корона из листьев, точёная подвеска,
    два S-образных рожка с кольцами, чашечками и свечными трубками, плиссированные абажуры."""
    B, A = "Body", "Arms"
    cz = 0.2                                            # центр пластины по высоте

    def cartouche(k, n=64):                             # фигурный контур, k — масштаб (ступени профиля)
        pts = []
        for i in range(n):
            t = 2 * PI * i / n
            x = 0.085 * math.sin(t) * (1 + 0.26 * math.cos(2 * t) + 0.1 * math.cos(4 * t) - 0.12 * math.cos(t))
            z = -0.19 * math.cos(t) - 0.03 * math.cos(3 * t)
            pts.append((x * k, cz + z * k))
        return pts
    # ступенчатый профиль пластины: основание -> скос -> поле
    for k, y0, y1 in ((1.0, -0.012, 0.0), (0.955, -0.02, -0.012), (0.9, -0.026, -0.02)):
        it.prism(B, "Wood", cartouche(k), y0, y1)
    it.add(B, "Wood", bm_ring_prism(cartouche(0.86), cartouche(0.8), -0.034, -0.026))     # выпуклый кант
    it.prism(B, "Wood", cartouche(0.8), -0.03, -0.026)                                  # утопленное поле
    it.add(B, "Wood", bm_ring_prism(cartouche(0.66), cartouche(0.63), -0.034, -0.03))   # внутренний кант
    for sx in (-1, 1):                                  # боковые волюты на уровне «талии»
        vx, vz = sx * 0.072, cz - 0.01
        vol = [(vx + sx * 0.022 * (1 - t / 8) * math.cos(t), -0.02, vz + 0.022 * (1 - t / 8) * math.sin(t))
               for t in np.linspace(0, 2.4 * PI, 36)]
        it.tube(B, "Wood", vol, 0.0065, segs=8, r_end=0.003)
    # розетка в центре поля
    rz = cz + 0.085
    it.lathe(B, "Wood", [(0, 0), (0.026, 0), (0.028, 0.004), (0.022, 0.009), (0, 0.012)], (0, -0.03, rz), (PI / 2, 0, 0), segs=20)
    for k in range(10):
        a = k * PI / 5
        it.add(B, "Wood", bm_sphere(0.011, 10, 6), (0.024 * math.sin(a), -0.04, rz + 0.024 * math.cos(a)),
               (0, a, 0), (0.6, 0.5, 1.2))
    it.add(B, "Wood", bm_sphere(0.012, 12, 8), (0, -0.045, rz), scale=(1, 0.7, 1))
    # C-завитки по бокам розетки
    for sx in (-1, 1):
        sp = [(sx * (0.04 + 0.02 * math.cos(t)), -0.034, rz - 0.035 + 0.06 * (t / (2.6 * PI)) + 0.02 * math.sin(t))
              for t in np.linspace(0.3, 2.6 * PI, 40)]
        it.tube(B, "Wood", sp, 0.0055, segs=6, r_end=0.003)
    # корона из листьев сверху
    top = cz + 0.205
    for k, a in enumerate(np.linspace(-0.9, 0.9, 7)):
        L = 0.05 - 0.012 * abs(a)
        it.add(B, "Wood", bm_sphere(0.012, 10, 6), (math.sin(a) * L * 0.6, -0.016, top + math.cos(a) * L * 0.55),
               (0, a, 0), (0.55, 0.5, 2.0))
    it.add(B, "Wood", bm_sphere(0.014, 12, 8), (0, -0.02, top + 0.005), scale=(1, 0.7, 1))
    # точёная подвеска снизу
    bz = cz - 0.205
    it.lathe(B, "Wood", [(0, bz + 0.01), (0.016, bz + 0.01), (0.02, bz - 0.005), (0.012, bz - 0.02), (0.016, bz - 0.032),
                         (0.008, bz - 0.048), (0.004, bz - 0.06), (0, bz - 0.064)], (0, -0.016, 0), segs=16)
    # точёный кронштейн, из которого выходят рожки
    mz = cz - 0.04
    it.lathe(B, "Wood", [(0, 0), (0.03, 0), (0.034, 0.008), (0.026, 0.02), (0.02, 0.03), (0.024, 0.042), (0.03, 0.05),
                         (0.026, 0.06), (0, 0.064)], (0, -0.03, mz), (PI / 2, 0, 0), segs=20)
    it.add("Trim", "Brass", bm_torus(0.022, 0.004, 24, 6), (0, -0.075, mz), (PI / 2, 0, 0))
    # рожки: плавная S-кривая, точёные кольца, завиток снизу, чашечка и свечная трубка
    for sx in (-1, 1):
        ctrl = [(0.0, -0.085, mz), (sx * 0.05, -0.11, mz - 0.03), (sx * 0.11, -0.135, mz - 0.025),
                (sx * 0.155, -0.15, mz + 0.01), (sx * 0.172, -0.152, mz + 0.05), (sx * 0.175, -0.152, 0.225)]
        path = catmull(ctrl, 10)
        it.tube(A, "WoodDark", path, 0.011, segs=10)
        for frac in (0.35, 0.75):
            i = int(len(path) * frac)
            p0, p1 = Vector(path[i]), Vector(path[min(i + 1, len(path) - 1)])
            d = (p1 - p0).normalized()
            q = d.to_track_quat('Z', 'Y').to_euler()
            it.add("Trim", "Brass", bm_torus(0.0125, 0.0035, 18, 6), tuple(p0), tuple(q))
        cx = sx * 0.1
        curl = [(cx + sx * 0.026 * math.cos(t) * (1 - t / 9), -0.132, mz - 0.04 - 0.03 * (t / 7) + 0.026 * math.sin(t) * (1 - t / 9))
                for t in np.linspace(0, 2.2 * PI, 30)]
        it.tube(A, "WoodDark", [(cx, -0.132, mz - 0.025)] + curl, 0.0065, segs=8, r_end=0.003)
        x = sx * 0.175
        it.lathe(A, "WoodDark", [(0, 0.218), (0.014, 0.218), (0.03, 0.222), (0.045, 0.23), (0.048, 0.236),
                                 (0.04, 0.236), (0.02, 0.24), (0.015, 0.245), (0, 0.245)], (x, -0.152, 0), segs=20)
        it.cyl("Candles", "Wax", 0.012, 0.06, (x, -0.152, 0.275), segs=14)
        it.add("Shades", "Shade", bm_pleated(0.1, 0.065, 0.27, 0.45), (x, -0.152, 0))
        for zz, rr in ((0.27, 0.102), (0.45, 0.067)):
            it.add("Trim", "Brass", bm_torus(rr, 0.004, 28, 5), (x, -0.152, zz))


def round_table(it):
    it.lathe("Body", "Wood", [(0, 0.725), (0.53, 0.725), (0.548, 0.732), (0.555, 0.745), (0.55, 0.757), (0.535, 0.762),
                              (0, 0.762)], segs=56)
    it.lathe("Body", "Wood", [(0, 0.66), (0.47, 0.66), (0.48, 0.67), (0.48, 0.725), (0, 0.725)], segs=48)
    it.lathe("Body", "Wood", [(0, 0.12), (0.11, 0.12), (0.11, 0.15), (0.08, 0.18), (0.06, 0.24), (0.095, 0.32),
                              (0.1, 0.36), (0.07, 0.42), (0.055, 0.5), (0.065, 0.56), (0.09, 0.6), (0.16, 0.64),
                              (0.2, 0.66), (0, 0.66)], segs=24)
    for k in range(4):
        a = PI / 4 + k * PI / 2
        pts = [(r * math.cos(a), r * math.sin(a), z) for r, z in
               [(0.06, 0.2), (0.14, 0.17), (0.22, 0.12), (0.29, 0.07), (0.34, 0.045), (0.37, 0.05), (0.38, 0.07)]]
        it.tube("Body", "Wood", pts, 0.045, segs=10, r_end=0.03)
        it.add("Body", "Wood", bm_sphere(0.04, 12, 8), (0.36 * math.cos(a), 0.36 * math.sin(a), 0.035), scale=(1.3, 1.3, 0.9))


def rect_table(it):
    L, D, H = 1.1, 0.62, 0.5
    it.bx("Body", "Wood", (-L / 2, L / 2), (-D / 2, D / 2), (H - 0.04, H), 0.012, 2)
    it.bx("Body", "Wood", (-L / 2 + 0.05, L / 2 - 0.05), (-D / 2 + 0.05, D / 2 - 0.05), (H - 0.12, H - 0.04), 0.004)
    it.bx("Body", "Wood", (-L / 2 + 0.045, L / 2 - 0.045), (-D / 2 + 0.045, D / 2 - 0.045), (H - 0.125, H - 0.11), 0.004)
    prof = [(0, 0), (0.028, 0), (0.034, 0.03), (0.026, 0.06), (0.032, 0.1), (0.05, 0.17), (0.052, 0.21), (0.038, 0.26),
            (0.03, 0.3), (0.04, 0.33), (0.035, 0.35), (0.038, H - 0.04), (0, H - 0.04)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.lathe("Body", "Wood", prof, (sx * (L / 2 - 0.085), sy * (D / 2 - 0.085), 0), segs=14)


def grand_clock(it):
    B = "Body"
    for sx in (-1, 1):
        for sy in (-1, 1):
            it.lathe(B, "Wood", [(0, 0), (0.035, 0), (0.045, 0.02), (0.03, 0.05), (0, 0.06)],
                     (sx * 0.23, sy * 0.12, 0), segs=10)
    it.bx(B, "Wood", (-0.29, 0.29), (-0.18, 0.17), (0.05, 0.1), 0.01, 2)
    it.bx(B, "Wood", (-0.27, 0.27), (-0.16, 0.16), (0.1, 0.42), 0.006)
    it.bx(B, "Wood", (-0.19, 0.19), (-0.172, -0.16), (0.15, 0.37), 0.012, 2)
    it.add(B, "Wood", bm_prism(arc(0, 0.26, 0.08, 0.05, 0, 2 * PI, 20)[:-1], -0.182, -0.172))
    it.bx(B, "Wood", (-0.27, 0.27), (-0.175, 0.165), (0.42, 0.47), 0.01, 2)
    it.bx(B, "Wood", (-0.21, 0.21), (0.11, 0.13), (0.47, 1.4))
    for sx in (-1, 1):
        it.bx(B, "Wood", sorted((sx * 0.19, sx * 0.21)), (-0.13, 0.13), (0.47, 1.4))
        it.bx(B, "Wood", sorted((sx * 0.14, sx * 0.215)), (-0.145, -0.115), (0.47, 1.4), 0.004)
        it.lathe(B, "Wood", [(0.016, 0.5), (0.024, 0.53), (0.016, 0.56), (0.016, 1.3), (0.024, 1.33), (0.016, 1.37)],
                 (sx * 0.235, -0.13, 0), segs=10)
    it.bx(B, "Wood", (-0.14, 0.14), (-0.145, -0.115), (0.47, 0.56), 0.004)
    top_arch = [(x, 1.24 + 0.08 * math.sqrt(max(0, 1 - (x / 0.14) ** 2))) for x in np.linspace(0.14, -0.14, 16)]
    it.prism(B, "Wood", [(-0.14, 1.4), (-0.14, 1.24)] + top_arch[::-1] + [(0.14, 1.24), (0.14, 1.4)], -0.145, -0.115)
    it.prism("Glass", "Glass", [(-0.14, 0.56), (0.14, 0.56)] + top_arch, -0.132, -0.127)
    it.bx(B, "Wood", (-0.27, 0.27), (-0.175, 0.165), (1.4, 1.45), 0.01, 2)
    it.bx(B, "Wood", (-0.245, 0.245), (-0.15, 0.15), (1.45, 1.98), 0.004)
    for sx in (-1, 1):
        it.lathe(B, "Wood", [(0.018, 1.46), (0.026, 1.49), (0.018, 1.52), (0.018, 1.9), (0.026, 1.93), (0.018, 1.97)],
                 (sx * 0.225, -0.165, 0), segs=10)
    it.bx(B, "Wood", (-0.27, 0.27), (-0.18, 0.165), (1.98, 2.02), 0.01, 2)
    for sx in (-1, 1):                                          # «лебединая шея» — резные завитки
        pts = [(sx * x, -0.17, z) for x, z in [(0.26, 2.02), (0.24, 2.08), (0.18, 2.13), (0.11, 2.14), (0.07, 2.12),
                                               (0.06, 2.09), (0.08, 2.075), (0.1, 2.09)]]
        it.tube(B, "Wood", pts, 0.022, segs=10)
        it.prism(B, "Wood", [(sx * x, z) for x, z in [(0.26, 2.02), (0.24, 2.07), (0.18, 2.11), (0.11, 2.12), (0.06, 2.02)]]
                 if sx > 0 else [(sx * x, z) for x, z in [(0.06, 2.02), (0.11, 2.12), (0.18, 2.11), (0.24, 2.07), (0.26, 2.02)]],
                 -0.16, 0.15)
    it.lathe("Brass", "Brass", [(0, 2.02), (0.025, 2.02), (0.018, 2.05), (0.03, 2.08), (0.02, 2.11), (0.008, 2.16), (0, 2.18)], segs=12)
    for sx in (-1, 1):
        it.lathe("Brass", "Brass", [(0, 2.02), (0.015, 2.02), (0.02, 2.04), (0.008, 2.07), (0, 2.09)], (sx * 0.24, 0, 0), segs=10)
    fz = 1.72
    it.bx(B, "Wood", (-0.215, 0.215), (-0.163, -0.15), (1.47, 1.96), 0.004)
    it.cyl("Face", "Paper", 0.17, 0.008, (0, -0.167, fz), (PI / 2, 0, 0), segs=48)
    it.add("Brass", "Brass", bm_torus(0.172, 0.011, 48, 8), (0, -0.172, fz), (PI / 2, 0, 0))
    roman_dial(it, "Numerals", (0, fz), 0.135, 0.032, -0.1725)
    it.cyl("Numerals", "Black", 0.009, 0.01, (0, -0.18, fz), (PI / 2, 0, 0), segs=10)
    clock_hands(it, (0, fz), -0.173, 0.075, 0.12)
    it.bx("Pendulum", "Brass", (-0.006, 0.006), (-0.004, 0.004), (0.82, 1.38), 0.001)
    for sx in (-1, 1):
        it.tube("Pendulum", "Brass", [(sx * 0.006, 0, 1.3), (sx * 0.035, 0, 1.2), (sx * 0.045, 0, 1.08), (sx * 0.02, 0, 0.98),
                                      (sx * 0.006, 0, 0.94)], 0.004, segs=6)
    it.cyl("Pendulum", "Brass", 0.09, 0.014, (0, 0, 0.8), (PI / 2, 0, 0), segs=32)
    it.add("Pendulum", "Brass", bm_torus(0.09, 0.008, 32, 6), (0, 0, 0.8), (PI / 2, 0, 0))
    for x in (-0.09, 0.09):
        it.cyl("Weights", "Brass", 0.026, 0.22, (x, 0.06, 1.12), segs=14)
        it.tube("Weights", "Brass", [(x, 0.06, 1.23), (x, 0.06, 1.4)], 0.002, segs=4)
    it.behaviors.append((f"{it.name}_Pendulum", "pendulum"))


def wall_clock(it):
    R = 0.25
    cz = R + 0.04
    it.lathe("Body", "Wood", [(R - 0.045, 0), (R, 0), (R + 0.012, 0.015), (R + 0.006, 0.035), (R - 0.01, 0.055),
                              (R - 0.03, 0.06), (R - 0.045, 0.045)], (0, 0, cz), (PI / 2, 0, 0), segs=48, closed=True)
    it.cyl("Body", "Wood", R - 0.04, 0.02, (0, -0.01, cz), (PI / 2, 0, 0), segs=40)
    for k in range(12):                                         # резные «бусины» по ободу
        a = k * PI / 6 + PI / 12
        it.add("Body", "Wood", bm_sphere(0.022, 10, 6), (R * 0.98 * math.sin(a), -0.03, cz + R * 0.98 * math.cos(a)),
               scale=(1, 0.8, 1.3), rot=(0, a, 0))
    for zz, sz in ((cz + R + 0.03, 0.05), (cz - R - 0.03, 0.04)):
        it.add("Body", "Wood", bm_prism(arc(0, zz, sz * 1.4, sz, 0, 2 * PI, 16)[:-1], -0.04, 0.0))
    it.cyl("Face", "Paper", R - 0.04, 0.006, (0, -0.023, cz), (PI / 2, 0, 0), segs=48)
    it.add("Numerals", "Black", bm_torus(R - 0.085, 0.0015, 48, 4), (0, -0.027, cz), (PI / 2, 0, 0))
    roman_dial(it, "Numerals", (0, cz), R - 0.105, 0.036, -0.0275)
    it.cyl("Cap", "Brass", 0.01, 0.01, (0, -0.036, cz), (PI / 2, 0, 0), segs=12)
    clock_hands(it, (0, cz), -0.028, 0.1, 0.15, 1.2)


def facet_clock(it):
    """Настенные часы: 12-гранный деревянный обод, светлый циферблат, риски и стрелки."""
    cz = 0.27
    ph = PI / 12                                                # грань сверху, как на референсе
    rot = (PI / 2, 0, 0)                                        # ось лейзера Z -> -Y (лицом вперёд)
    it.lathe("Body", "Wood", [(0.205, 0.0), (0.26, 0.0), (0.262, 0.028), (0.245, 0.05), (0.215, 0.055),
                              (0.2, 0.045)], (0, 0, cz), rot, segs=12, closed=True, phase=ph)
    it.lathe("Body", "Wood", [(0, 0.0), (0.21, 0.0), (0.21, 0.01), (0, 0.01)], (0, 0, cz), rot, segs=12, phase=ph)
    it.lathe("Rim", "WoodDark", [(0.188, 0.008), (0.207, 0.008), (0.207, 0.046), (0.188, 0.034)], (0, 0, cz), rot,
             segs=12, closed=True, phase=ph)
    it.lathe("Face", "Paper", [(0, 0.008), (0.19, 0.008), (0.19, 0.022), (0, 0.022)], (0, 0, cz), rot, segs=12, phase=ph)
    yf = -0.022
    for k in range(12):
        a = k * PI / 6
        L, W = (0.05, 0.022) if k == 0 else (0.042, 0.018)
        r = 0.15 if k else 0.148
        it.box_at("Ticks", "Ink", (W, 0.004, L), (r * math.sin(a), yf - 0.002, cz + r * math.cos(a)), (0, a, 0), bev=0)
    y = yf - 0.005
    it.prism("HourHand", "Ink", [(-0.011, cz - 0.02), (0.011, cz - 0.02), (0.007, cz + 0.07), (0.0, cz + 0.095),
                                 (-0.007, cz + 0.07)], y - 0.004, y)
    y -= 0.005
    it.prism("MinuteHand", "Ink", [(-0.008, cz - 0.025), (0.008, cz - 0.025), (0.005, cz + 0.12), (0.0, cz + 0.15),
                                   (-0.005, cz + 0.12)], y - 0.004, y)
    it.cyl("Cap", "Ink", 0.02, 0.012, (0, y - 0.006, cz), rot, segs=16)
    it.behaviors.append((f"{it.name}_HourHand", "hour"))
    it.behaviors.append((f"{it.name}_MinuteHand", "minute"))


def rounded_rect(x0, x1, z0, z1, r, n=6, top_only=False):
    """Скруглённый прямоугольник в XZ (обход против часовой)."""
    pts = []
    if top_only:
        pts += [(x0, z0), (x1, z0)]
    else:
        pts += arc(x0 + r, z0 + r, r, r, PI, 1.5 * PI, n) + arc(x1 - r, z0 + r, r, r, 1.5 * PI, 2 * PI, n)
    pts += arc(x1 - r, z1 - r, r, r, 0, 0.5 * PI, n) + arc(x0 + r, z1 - r, r, r, 0.5 * PI, PI, n)
    return pts


def rect_ring(xa, xb, za, zb, f, d1, d2):
    """Цельная прямоугольная рамка (без стыков на углах) в плоскости XZ, толщина d1..d2 по Y."""
    outer = [(xa, za), (xb, za), (xb, zb), (xa, zb)]
    inner = [(xa + f, za + f), (xb - f, za + f), (xb - f, zb - f), (xa + f, zb - f)]
    return bm_ring_prism(outer, inner, d1, d2)


def raised_panel(it, part, mat, xr, zr, y, out=-1, frame=0.03):
    """Филёнка: цельная рамка + выпуклая доска. out=-1 — лицом в -Y, +1 — в +Y."""
    xa, xb = xr
    za, zb = zr
    d1, d2 = sorted((y, y + out * 0.012))
    it.add(part, mat, rect_ring(xa, xb, za, zb, frame, d1, d2))
    d1, d2 = sorted((y, y + out * 0.016))
    it.bx(part, mat, (xa + frame + 0.006, xb - frame - 0.006), (d1, d2), (za + frame + 0.006, zb - frame - 0.006), 0.012, 2)


def raised_panel_side(it, part, mat, yr, zr, x, out=1, frame=0.03):
    """Филёнка на боковой стенке (плоскость YZ), лицом в +X (out=1) или -X (out=-1)."""
    ya, yb = yr
    za, zb = zr
    d1, d2 = sorted((x, x + out * 0.012))
    it.add(part, mat, rect_ring(-yb, -ya, za, zb, frame, d1, d2), rot=(0, 0, -PI / 2))
    d1, d2 = sorted((x, x + out * 0.016))
    it.bx(part, mat, (d1, d2), (ya + frame + 0.006, yb - frame - 0.006), (za + frame + 0.006, zb - frame - 0.006), 0.012, 2)


def reception_desk(it):
    B = "Body"
    W, yF, yB = 0.9, -0.36, 0.36              # полуширина, рабочая сторона (-Y), сторона гостя (+Y)
    ped = [(-W, -0.48), (0.48, W)]
    # --- тумбы
    for xa, xb in ped:
        it.bx(B, "Wood", (xa - 0.02, xb + 0.02), (yF - 0.025, yB - 0.02), (0.0, 0.09), 0.008)      # цоколь
        it.bx(B, "Wood", (xa - 0.01, xb + 0.01), (yF - 0.032, yB - 0.02), (0.08, 0.1), 0.005)
        it.bx(B, "Wood", (xa, xa + 0.025), (yF, yB - 0.02), (0.1, 0.72))
        it.bx(B, "Wood", (xb - 0.025, xb), (yF, yB - 0.02), (0.1, 0.72))
        it.bx(B, "Wood", (xa, xb), (yF, yB - 0.02), (0.1, 0.12))
        for z in (0.1, 0.4, 0.69):                                                     # рельсы между ящиками
            it.bx(B, "Wood", (xa + 0.02, xb - 0.02), (yF - 0.008, yF + 0.02), (z, z + 0.03), 0.003)
        for x0, x1 in ((xa - 0.006, xa + 0.035), (xb - 0.035, xb + 0.006)):            # стойки рамы
            it.bx(B, "Wood", (x0, x1), (yF - 0.012, yF + 0.02), (0.1, 0.72), 0.004)
        outer = xa if xa < 0 else xb                                                  # филёнка на боку тумбы
        s = -1 if xa < 0 else 1
        for y0, y1 in ((yF + 0.06, -0.02), (0.02, yB - 0.06)):
            raised_panel_side(it, B, "Wood", (y0, y1), (0.16, 0.66), outer, s)
    # --- задняя стенка проёма для ног
    it.bx(B, "Wood", (-0.48, 0.48), (0.18, 0.2), (0.1, 0.6))
    # --- столешница с профилем и кожаной вставкой
    it.bx(B, "Wood", (-W - 0.035, W + 0.035), (yF - 0.05, 0.2), (0.72, 0.745), 0.008, 2)
    it.bx(B, "Wood", (-W - 0.045, W + 0.045), (yF - 0.06, 0.2), (0.745, 0.765), 0.01, 2)
    it.bx("Inset", "Leather", (-0.6, 0.6), (yF + 0.02, 0.14), (0.765, 0.768), 0.002)
    it.tube("InsetTrim", "Brass", [(-0.61, yF + 0.01, 0.767), (0.61, yF + 0.01, 0.767), (0.61, 0.15, 0.767),
                                   (-0.61, 0.15, 0.767), (-0.61, yF + 0.01, 0.767)], 0.003, segs=4, caps=False)
    # --- стойка (поднятая стенка) со скруглёнными верхними углами
    hutch = rounded_rect(-W, W, 0.765, 1.08, 0.12, top_only=True)
    it.prism(B, "Wood", hutch, 0.2, yB - 0.02)
    it.tube(B, "Wood", [(x, 0.195, z) for x, z in hutch[2:]], 0.012, segs=6)                 # кант по рабочей стороне
    raised_panel(it, B, "Wood", (-0.75, -0.06), (0.8, 1.0), 0.2, -1)
    raised_panel(it, B, "Wood", (0.06, 0.75), (0.8, 1.0), 0.2, -1)
    it.bx(B, "Wood", (-0.82, 0.82), (0.13, 0.2), (0.86, 0.875), 0.004)                         # полочка для бумаг
    # --- стойка гостя: широкий подоконник со скруглёнными концами
    plan = rounded_rect(-W - 0.06, W + 0.06, 0.16, yB + 0.12, 0.1)
    it.add(B, "Wood", bm_prism(plan, -1.125, -1.08), rot=(-PI / 2, 0, 0))
    it.add(B, "Wood", bm_prism(rounded_rect(-W - 0.04, W + 0.04, 0.17, yB + 0.1, 0.09), -1.08, -1.055), rot=(-PI / 2, 0, 0))
    # --- сторона гостя (+Y): плинтус, пилястры, три филёнки в два яруса, карниз
    it.bx(B, "Wood", (-W - 0.03, W + 0.03), (yB, yB + 0.045), (0, 0.1), 0.008)
    it.bx(B, "Wood", (-W, W), (yB - 0.02, yB), (0.1, 1.06))
    xs = [-W, -0.3, 0.3, W]
    for x in xs:
        it.bx(B, "Wood", (x - 0.04, x + 0.04), (yB, yB + 0.03), (0.1, 1.04), 0.006)
        it.bx(B, "Wood", (x - 0.05, x + 0.05), (yB, yB + 0.04), (0.1, 0.15), 0.006)
        it.bx(B, "Wood", (x - 0.05, x + 0.05), (yB, yB + 0.04), (0.98, 1.02), 0.006)
    for a, b in zip(xs, xs[1:]):
        raised_panel(it, B, "Wood", (a + 0.07, b - 0.07), (0.16, 0.55), yB, 1)
        raised_panel(it, B, "Wood", (a + 0.07, b - 0.07), (0.62, 0.97), yB, 1)
    it.bx(B, "Wood", (-W - 0.02, W + 0.02), (yB, yB + 0.05), (1.02, 1.055), 0.008)
    # --- ящики (выдвигаются): по 2 в тумбах + центральный
    drawers = []
    for side, (xa, xb) in zip(("L", "R"), ped):
        drawers += [(f"Drawer{side}1", xa + 0.035, xb - 0.035, 0.43, 0.69), (f"Drawer{side}2", xa + 0.035, xb - 0.035, 0.13, 0.4)]
    drawers.append(("DrawerC", -0.46, 0.46, 0.6, 0.715))
    for name, xa, xb, z0, z1 in drawers:
        z0, z1 = z0 + 0.004, z1 - 0.004
        it.bx(name, "Wood", (xa, xb), (yF - 0.024, yF), (z0, z1), 0.005)
        fr = 0.025 if z1 - z0 < 0.15 else 0.04
        it.bx(name, "Wood", (xa + fr, xb - fr), (yF - 0.032, yF - 0.024), (z0 + fr * 0.8, z1 - fr * 0.8), 0.008, 2)
        dd = 0.24 if name != "DrawerC" else 0.3
        it.bx(name, "Wood", (xa + 0.01, xb - 0.01), (yF, yF + dd), (z0 + 0.01, z0 + 0.02))
        it.bx(name, "Wood", (xa + 0.01, xa + 0.02), (yF, yF + dd), (z0 + 0.01, z1 - 0.02))
        it.bx(name, "Wood", (xb - 0.02, xb - 0.01), (yF, yF + dd), (z0 + 0.01, z1 - 0.02))
        it.bx(name, "Wood", (xa + 0.01, xb - 0.01), (yF + dd - 0.01, yF + dd), (z0 + 0.01, z1 - 0.02))
        w = xb - xa
        kx = [(xa + xb) / 2 - w * 0.28, (xa + xb) / 2 + w * 0.28] if name != "DrawerC" else [-0.3, 0.3]
        for x in kx:
            knob(it, f"{name}_Knobs", "Brass", (x, yF - 0.032, (z0 + z1) / 2), 0.016, 0.035)
        it.cyl(f"{name}_Knobs", "Brass", 0.006, 0.006, ((xa + xb) / 2, yF - 0.034, z1 - 0.03 if name != "DrawerC" else (z0 + z1) / 2),
               (PI / 2, 0, 0), segs=8)                                                     # замочная скважина
        it.behaviors.append((f"{it.name}_{name}", "slide"))
    # --- звонок портье на стойке (3 детали: подставка, купол, кнопка — для анимации нажатия)
    desk_bell(it, "Bell", (0.62, yB - 0.02, 1.125))


def desk_bell(it, pre, loc):
    """Звонок портье: Base (деревянная подставка), Dome (латунный купол), Button (шток + кнопка — нажимается)."""
    x, y, z = loc
    it.lathe(f"{pre}Base", "WoodDark", [(0, 0), (0.056, 0), (0.06, 0.004), (0.06, 0.011), (0.055, 0.016), (0.05, 0.018),
                                       (0, 0.018)], (x, y, z), segs=32)
    it.lathe(f"{pre}Dome", "Brass", [(0, 0.018), (0.047, 0.018), (0.048, 0.021), (0.046, 0.03), (0.041, 0.042),
                                     (0.033, 0.052), (0.022, 0.059), (0.01, 0.062), (0.005, 0.0625), (0, 0.0625)],
             (x, y, z), segs=32)
    it.lathe(f"{pre}Button", "Brass", [(0, 0.056), (0.0028, 0.056), (0.0028, 0.071), (0.006, 0.072), (0.0105, 0.074),
                                       (0.011, 0.077), (0.008, 0.08), (0, 0.081)], (x, y, z), segs=16)
    it.behaviors.append((f"{it.name}_{pre}Button", "press"))


def desk_bell_item(it):
    desk_bell(it, "", (0, 0, 0))


def grand_chandelier(it):
    """Деревянная люстра: потолочная чаша, цепь, точёный 8-гранный корпус-ваза, 8 изогнутых рожков
    на двух уровнях, ступенчатые чашечки, колоколообразные 8-гранные абажуры с рёбрами."""
    ph = PI / 8
    B = "Body"
    # потолочная чаша
    it.lathe(B, "Wood", [(0, 1.1), (0.11, 1.1), (0.15, 1.115), (0.2, 1.125), (0.205, 1.16), (0.18, 1.175), (0, 1.175)],
             segs=8, phase=ph)
    it.lathe("Trim", "Brass", [(0.2, 1.124), (0.209, 1.128), (0.209, 1.135), (0.2, 1.139)], segs=8, phase=ph, closed=True)
    # цепь из прямоугольных звеньев
    z = 1.1
    k = 0
    while z > 0.76:
        it.add("Chain", "Wood", rect_ring(-0.028, 0.028, z - 0.085, z, 0.014, -0.009, 0.009), rot=(0, 0, (k % 2) * PI / 2))
        z -= 0.062
        k += 1
    # корпус: подвеска-шип, чаша, пояс с рожками, колонна, ваза, верхняя шапка
    prof = [(0, 0.0), (0.012, 0.03), (0.032, 0.07), (0.056, 0.105), (0.046, 0.125), (0.062, 0.145), (0.05, 0.165),
            (0.09, 0.19), (0.13, 0.225), (0.152, 0.265), (0.152, 0.3), (0.165, 0.31), (0.165, 0.335), (0.12, 0.345),
            (0.1, 0.36), (0.1, 0.375), (0.13, 0.385), (0.13, 0.405), (0.1, 0.415), (0.122, 0.45), (0.112, 0.52),
            (0.086, 0.575), (0.068, 0.598), (0.1, 0.608), (0.1, 0.63), (0.064, 0.64), (0.09, 0.66), (0.132, 0.68),
            (0.132, 0.71), (0.1, 0.722), (0.06, 0.73), (0.045, 0.75), (0.03, 0.765), (0, 0.765)]
    S = (1.2, 1.2, 1.0)                                  # корпус массивнее, как на референсе
    it.lathe(B, "Wood", prof, segs=8, phase=ph, scale=S)
    for zz, rr in ((0.165, 0.052), (0.303, 0.168), (0.335, 0.167), (0.395, 0.133), (0.618, 0.102), (0.695, 0.134)):
        it.lathe("Trim", "Brass", [(rr - 0.004, zz - 0.004), (rr + 0.004, zz - 0.004), (rr + 0.004, zz + 0.004),
                                   (rr - 0.004, zz + 0.004)], segs=8, phase=ph, closed=True, scale=S)
    # рожки, чашечки, патроны, абажуры
    for i in range(8):
        a = i * PI / 4 + PI / 8
        ca, sa = math.cos(a), math.sin(a)
        long_arm = i % 2 == 0
        if long_arm:
            prof_a = [(0.15, 0.31), (0.25, 0.275), (0.38, 0.255), (0.49, 0.27), (0.555, 0.32), (0.575, 0.38)]
        else:
            prof_a = [(0.15, 0.325), (0.22, 0.33), (0.3, 0.355), (0.36, 0.41), (0.385, 0.47), (0.39, 0.5)]
        pts = catmull([(r * ca, r * sa, zz) for r, zz in prof_a], 6)
        it.tube("Arms", "Wood", pts, 0.026, segs=6)
        rx, cz = prof_a[-1]
        x, y = rx * ca, rx * sa
        cup = [(0, cz - 0.01), (0.03, cz - 0.01), (0.05, cz), (0.068, cz + 0.015), (0.068, cz + 0.032),
               (0.05, cz + 0.042), (0.04, cz + 0.05), (0.04, cz + 0.078), (0.052, cz + 0.084), (0.052, cz + 0.094), (0, cz + 0.094)]
        it.lathe("Arms", "Wood", cup, (x, y, 0), segs=8, phase=ph)
        it.lathe("Trim", "Brass", [(0.064, cz + 0.02), (0.072, cz + 0.02), (0.072, cz + 0.028), (0.064, cz + 0.028)],
                 (x, y, 0), segs=8, phase=ph, closed=True)
        it.cyl("Sockets", "WoodDark", 0.022, 0.06, (x, y, cz + 0.124), segs=8)
        # абажур: 8-гранный колокол (тонкая оболочка), рёбра по граням, окантовка сверху и снизу
        z0, h = cz + 0.085, 0.15
        bell = [(0.122 - 0.047 * (t ** 0.7), z0 + h * t) for t in np.linspace(0, 1, 7)]
        shell = bell + [(r - 0.004, zz) for r, zz in reversed(bell)]
        it.lathe("Shades", "Shade", shell, (x, y, 0), segs=8, phase=ph, closed=True)
        for zz, rr in ((z0, 0.123), (z0 + h, 0.076)):
            it.lathe("ShadeFrames", "WoodDark", [(rr - 0.003, zz - 0.008), (rr + 0.006, zz - 0.008), (rr + 0.006, zz + 0.008),
                                                 (rr - 0.003, zz + 0.008)], (x, y, 0), segs=8, phase=ph, closed=True)
        for kk in range(8):
            b = kk * PI / 4 + ph
            rib = [(x + (r + 0.003) * math.cos(b), y + (r + 0.003) * math.sin(b), zz) for r, zz in bell]
            it.tube("ShadeFrames", "WoodDark", rib, 0.0035, segs=4)
    # завитки под корпусом
    for i in range(4):
        a = i * PI / 2
        ca, sa = math.cos(a), math.sin(a)
        prof_s = [(0.1, 0.235), (0.17, 0.21), (0.21, 0.16), (0.2, 0.115), (0.165, 0.1), (0.14, 0.12), (0.15, 0.145)]
        it.tube("Arms", "Wood", catmull([(r * ca, r * sa, zz) for r, zz in prof_s], 5), 0.016, segs=6, r_end=0.011)


def locker(it):
    """Ржавый металлический шкафчик: 2 двери с жалюзи и утопленными ручками, наружные петли,
    ножки-уголки, внутри полка и штанга. Материал в Roblox — CorrodedMetal (ржавчина)."""
    W, D = 0.92, 0.5
    w, y0, y1 = W / 2, -D / 2, D / 2
    zb, zt = 0.14, 1.84                                  # низ и верх корпуса
    B, M = "Body", "Rust"
    t = 0.012                                            # толщина листа
    # ножки-уголки
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (w - 0.02), sy * (D / 2 - 0.02)
            it.bx(B, M, sorted((x, x - sx * 0.055)), sorted((y, y - sy * 0.006)), (0.0, zb + 0.02), 0.002)
            it.bx(B, M, sorted((x, x - sx * 0.006)), sorted((y, y - sy * 0.055)), (0.0, zb + 0.02), 0.002)
    # корпус из листа
    it.bx(B, M, (-w, -w + t), (y0, y1), (zb, zt))
    it.bx(B, M, (w - t, w), (y0, y1), (zb, zt))
    it.bx(B, M, (-w, w), (y1 - t, y1), (zb, zt))
    it.bx(B, M, (-w + 0.002, w - 0.002), (y0, y1 - 0.002), (zb, zb + 0.06), 0.003)   # цоколь (не в плоскости стенок)
    it.bx(B, M, (-w + 0.01, w - 0.01), (y0 - 0.004, y0 + 0.02), (zb, zb + 0.06), 0.003)
    it.bx(B, M, (-w - 0.012, w + 0.012), (y0 - 0.02, y1 + 0.012), (zt, zt + 0.03), 0.006)   # крышка с отбортовкой
    it.bx(B, M, (-w + t, w - t), (y0, y1 - t), (zt - 0.012, zt))
    # рамка проёма
    it.bx(B, M, (-w, -w + 0.03), (y0 - 0.004, y0 + 0.02), (zb, zt), 0.002)
    it.bx(B, M, (w - 0.03, w), (y0 - 0.004, y0 + 0.02), (zb, zt), 0.002)
    it.bx(B, M, (-w, w), (y0 - 0.004, y0 + 0.02), (zt - 0.03, zt), 0.002)
    # внутри: полка, штанга, рёбра жёсткости
    it.bx(B, M, (-w + t, w - t), (y0 + 0.03, y1 - t), (1.5, 1.512))
    it.bx(B, M, (-w + t, w - t), (y0 + 0.03, y1 - t), (zb + 0.06, zb + 0.072))
    it.cyl("Rod", "Iron", 0.011, W - 0.04, (0, 0.0, 1.42), (0, PI / 2, 0), segs=10)
    # петли снаружи на боковинах
    for sx in (-1, 1):
        for zc in (0.45, 1.55):
            x = sx * (w + 0.006)
            it.cyl("Hinges", "Iron", 0.008, 0.1, (x, y0 + 0.004, zc), segs=8)
            it.bx("Hinges", "Iron", sorted((sx * w, sx * (w + 0.003))), (y0 + 0.004, y0 + 0.05), (zc - 0.045, zc + 0.045), 0.001)
    # двери
    zd0, zd1 = zb + 0.065, zt - 0.035
    for side, name in ((-1, "DoorL"), (1, "DoorR")):
        xa, xb = (-w + 0.032, -0.004) if side < 0 else (0.004, w - 0.032)
        yd = y0 - 0.004
        it.bx(name, M, (xa, xb), (yd - 0.018, yd), (zd0, zd1), 0.004)
        it.bx(name, M, (xa + 0.015, xb - 0.015), (yd - 0.02, yd - 0.018), (zd0 + 0.015, zd1 - 0.015), 0.002)
        cx = (xa + xb) / 2
        lw = (xb - xa) * 0.62
        for zc in (1.66, zd0 + 0.24):                    # жалюзи: тёмная щель + наклонная планка
            for k in range(5):
                zz = zc - 0.09 + k * 0.045
                it.bx(f"{name}_Vents", "Black", (cx - lw / 2, cx + lw / 2), (yd - 0.0215, yd - 0.0205), (zz - 0.012, zz + 0.006), 0)
                it.box_at(name, M, (lw, 0.004, 0.026), (cx, yd - 0.026, zz + 0.004), (math.radians(-38), 0, 0), bev=0.0015)
                for sx in (-1, 1):                       # боковые «щёчки» планки
                    it.bx(name, M, sorted((cx + sx * lw / 2, cx + sx * (lw / 2 - 0.004))), (yd - 0.033, yd - 0.02),
                          (zz - 0.012, zz + 0.018), 0.001)
        # утопленная ручка у притвора
        hx = xb - 0.075 if side < 0 else xa + 0.075
        zc = 0.98
        it.add(f"{name}_Handle", "Iron", rect_ring(hx - 0.028, hx + 0.028, zc - 0.075, zc + 0.075, 0.012, yd - 0.027, yd - 0.02))
        it.bx(f"{name}_HandleHole", "Black", (hx - 0.016, hx + 0.016), (yd - 0.0215, yd - 0.0205), (zc - 0.063, zc + 0.063), 0)
        it.behaviors.append((f"{it.name}_{name}", "hinge"))


ITEMS = [
    ("Wardrobe", wardrobe), ("Bookcase", bookcase), ("LuggageCart", luggage_cart), ("CoatRack", coat_rack),
    ("Plant", plant), ("Suitcase", lambda it: suitcase(it, "", (0.8, 0.42, 0.5), (0, 0, 0))),
    ("Painting", None), ("FloorLamp", floor_lamp), ("TableLamp", table_lamp), ("Dresser", dresser),
    ("Nightstand", nightstand), ("CoffeeTable", coffee_table), ("Bench", bench), ("Door", door),
    ("Fireplace", fireplace), ("Clock", clock), ("Mirror", mirror), ("LuggageRack", luggage_rack),
    ("Curtains", curtains), ("WallPanel", wall_panel),
    ("Chandelier", chandelier), ("Rug", None), ("Sconce", sconce), ("RoundTable", round_table),
    ("RectTable", rect_table), ("GrandClock", grand_clock), ("WallClock", wall_clock),
    ("FacetClock", facet_clock), ("ReceptionDesk", reception_desk), ("DeskBell", desk_bell_item),
    ("GrandChandelier", grand_chandelier), ("Locker", locker),
]
RU = {"Wardrobe": "Шкаф", "Bookcase": "Книжный шкаф", "LuggageCart": "Тележка", "CoatRack": "Вешалка",
      "Plant": "Растение", "Suitcase": "Чемодан", "Painting": "Картина", "FloorLamp": "Торшер",
      "TableLamp": "Настольная лампа", "Dresser": "Комод", "Nightstand": "Тумбочка", "CoffeeTable": "Журнальный столик",
      "Bench": "Банкетка", "Door": "Дверь", "Fireplace": "Камин", "Clock": "Напольные часы", "Mirror": "Зеркало",
      "LuggageRack": "Стеллаж для багажа", "Curtains": "Шторы", "WallPanel": "Панель на стену",
      "Chandelier": "Люстра", "Rug": "Ковёр", "Sconce": "Бра", "RoundTable": "Круглый стол",
      "RectTable": "Столик", "GrandClock": "Резные часы", "WallClock": "Настенные часы",
      "FacetClock": "Часы (12 граней)",
      "ReceptionDesk": "Стол-стойка", "DeskBell": "Звонок портье",
      "GrandChandelier": "Люстра с абажурами",
      "Locker": "Металлический шкафчик"}


# ----------------------------------------------------------------------------- сборка в Blender
def make_material(key, tex=None):
    rgb, _, alpha, refl, rough = PALETTE[key]
    m = bpy.data.materials.new(key)
    b = m.node_tree.nodes["Principled BSDF"]
    c = [(v / 255) ** 2.2 for v in rgb]
    b.inputs["Base Color"].default_value = (*c, 1)
    b.inputs["Roughness"].default_value = rough
    if key in ("Brass", "Iron", "Mirror"):
        b.inputs["Metallic"].default_value = 1.0
    if key == "Glass":
        b.inputs["Alpha"].default_value = 0.25
    if key in ("Fire", "Flame"):
        b.inputs["Emission Color"].default_value = (*c, 1)
        b.inputs["Emission Strength"].default_value = 6.0
    if key == "Shade":
        b.inputs["Emission Color"].default_value = (*c, 1)
        b.inputs["Emission Strength"].default_value = 0.6
    if key == "Rust":                                     # превью ржавчины (в Roblox — материал CorrodedMetal)
        nt = m.node_tree
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 14.0
        noise.inputs["Detail"].default_value = 8.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.45, 0.62
        ramp.color_ramp.elements[0].color = (0.011, 0.007, 0.007, 1)
        ramp.color_ramp.elements[1].color = (0.06, 0.013, 0.008, 1)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Metallic"].default_value = 0.4
    if tex is not None:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = tex
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    return m


def build_object(part, mats, col):
    me = bpy.data.meshes.new(part.name)
    me.from_pydata(part.v, [], part.f)
    if any(u is not None for u in part.uv):
        uvl = me.uv_layers.new(name="UVMap")
        li = 0
        for f, u in zip(part.f, part.uv):
            for k in range(len(f)):
                uvl.data[li].uv = u[k] if u else (0, 0)
                li += 1
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(38))
    me.materials.append(mats[part.mat])
    o = bpy.data.objects.new(part.name, me)
    col.objects.link(o)
    return o


def set_origin_bounds(o):
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    c = (co.max(0) + co.min(0)) / 2
    o.data.transform(Matrix.Translation(Vector(-c)))
    o.location = Vector(c)


def lua_table(items):
    """Генерация HotelSetup.server.lua: материалы деталей + поведение."""
    pal = ",\n".join(
        f'\t{k} = {{ Enum.Material.{v[1]}, Color3.fromRGB({v[0][0]}, {v[0][1]}, {v[0][2]}), {v[2]}, {v[3]} }}'
        for k, v in PALETTE.items())
    parts = ",\n".join(f'\t["{p.name}"] = "{p.mat}"' for it in items for p in it.parts.values())
    beh = ",\n".join(f'\t["{n}"] = "{t}"' for it in items for n, t in it.behaviors)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "HotelSetup.template.lua"), encoding="utf-8") as fh:
        tpl = fh.read()
    return tpl.replace("--@PALETTE@", pal).replace("--@PARTS@", parts).replace("--@BEHAVIORS@", beh)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    out = os.path.abspath(a[0])
    do_render = "render" in a
    for sub in ("models", "roblox", "textures"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    tex_path = os.path.join(out, "textures", "Painting_Canvas.png")
    items = []
    for name, fn in ITEMS:
        it = Item(name)
        if name == "Painting":
            painting(it, tex_path)
        elif name == "Rug":
            rug(it, os.path.join(out, "textures", "Rug_Pattern.png"))
        else:
            fn(it)
        items.append(it)
    texs = {"Canvas": bpy.data.images.get("Painting_Canvas"), "Rug": bpy.data.images.get("Rug_Pattern")}
    mats = {k: make_material(k, texs.get(k)) for k in PALETTE}
    total = 0
    objs_by_item = {}
    for it in items:
        col = bpy.data.collections.new(it.name)
        bpy.context.scene.collection.children.link(col)
        objs = []
        for p in it.parts.values():
            o = build_object(p, mats, col)
            set_origin_bounds(o)
            objs.append(o)
        objs_by_item[it.name] = objs
        tris = sum(len(o.data.polygons) for o in objs)
        mx = max(len(o.data.polygons) for o in objs)
        total += tris
        log(f"{it.name:12s} деталей {len(objs):2d}  треугольников {tris:6d}  (макс. деталь {mx})")
        assert mx < 20000, it.name
    log("всего треугольников:", total)

    # экспорт: каждый предмет — свой FBX (Roblox) и GLB
    for it in items:
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in objs_by_item[it.name]:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs_by_item[it.name][0]
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, "roblox", f"{it.name}.fbx"), use_selection=True,
                                 axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                                 path_mode='COPY', embed_textures=True)
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "models", f"{it.name}.glb"), export_format='GLB',
                                  use_selection=True)
    with open(os.path.join(out, "roblox", "HotelSetup.server.lua"), "w", encoding="utf-8") as fh:
        fh.write(lua_table(items))
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "HotelSet.blend"))
    if do_render:
        render(objs_by_item, out)
    log("готово ->", out)


# ----------------------------------------------------------------------------- превью
ROWS = [["Wardrobe", "Bookcase", "LuggageCart", "CoatRack", "Plant", "Suitcase", "Painting"],
        ["FloorLamp", "TableLamp", "Dresser", "Nightstand", "CoffeeTable", "Bench", "Door"],
        ["Fireplace", "Clock", "Mirror", "LuggageRack", "Curtains", "WallPanel"],
        ["Chandelier", "Sconce", "RoundTable", "RectTable", "Rug", "GrandClock", "WallClock", "FacetClock"],
        ["ReceptionDesk", "DeskBell", "GrandChandelier", "Locker"]]


def render(objs_by_item, out):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'AgX'
    sc.render.resolution_x, sc.render.resolution_y = 1800, 560
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.012, 0.006, 0.005, 1)
    floor = bpy.data.objects.new("floor", bpy.data.meshes.new("floor"))
    floor.data.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [[0, 1, 2, 3]])
    fm = bpy.data.materials.new("floor")
    fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.015, 0.008, 0.006, 1)
    floor.data.materials.append(fm)
    sc.collection.objects.link(floor)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = 'ORTHO'
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", 'AREA'))
    key.data.energy, key.data.size = 2600, 6
    key.data.color = (1.0, 0.75, 0.55)
    sc.collection.objects.link(key)
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", 'AREA'))
    fill.data.energy, fill.data.size = 700, 8
    fill.data.color = (0.9, 0.55, 0.45)
    sc.collection.objects.link(fill)
    shots = []
    for ri, row in enumerate(ROWS):
        all_objs = [o for objs in objs_by_item.values() for o in objs]
        for o in all_objs:
            o.hide_render = True
        x = 0.0
        for name in row:
            objs = objs_by_item[name]
            co = np.array([(o.matrix_world @ v.co)[:] for o in objs for v in o.data.vertices])
            lo, hi = co.min(0), co.max(0)
            dx = x - lo[0]
            dz = {"Painting": 0.9, "Chandelier": 1.0, "Sconce": 1.0, "WallClock": 1.0, "FacetClock": 1.0, "GrandChandelier": 1.0}.get(name, 0.0)
            if name == "Rug":                    # ковёр на превью приподнят к камере, чтобы был виден узор
                for o in objs:
                    o.rotation_euler.x = math.radians(62)
                    o.location.z += 0.75
            for o in objs:
                o.location.x += dx
                o.location.z += dz
                o.hide_render = False
            x += (hi[0] - lo[0]) + 0.45
        width = x - 0.45
        cx = width / 2
        cam.data.ortho_scale = max(width + 0.6, 2.6 * 1800 / 560 * 0.9)
        cam.location = (cx - 1.5, -12, 3.7)
        cam.rotation_euler = (math.radians(78), 0, math.radians(-7))
        key.location = (cx - 3, -6, 6)
        key.rotation_euler = (math.radians(50), 0, math.radians(-25))
        fill.location = (cx + 4, -5, 3)
        fill.rotation_euler = (math.radians(70), 0, math.radians(35))
        path = os.path.join(out, f"_row{ri}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        shots.append(path)
        for name in row:                       # вернуть на место
            for o in objs_by_item[name]:
                o.location.x -= 0
    imgs = [np.array(bpy.data.images.load(p).pixels[:]).reshape(560, 1800, 4) for p in shots]
    full = np.concatenate(imgs[::-1], axis=0)
    im = bpy.data.images.new("overview", 1800, 560 * len(imgs))
    im.pixels = full.ravel()
    im.filepath_raw = os.path.join(out, "overview.png")
    im.file_format = 'PNG'
    im.save()
    for p in shots:
        os.remove(p)


if __name__ == "__main__":
    main()
