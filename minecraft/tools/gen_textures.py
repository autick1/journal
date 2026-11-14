"""Generates the 16x16 pixel-art textures for the Arcanum mod (wands, scrolls, conjured blocks, icon)."""
import os, random, math
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..", "arcanum", "src", "main", "resources", "assets", "arcanum", "textures")
ITEM = os.path.join(ROOT, "item"); BLOCK = os.path.join(ROOT, "block")
os.makedirs(ITEM, exist_ok=True); os.makedirs(BLOCK, exist_ok=True)

def hexc(h, a=255):
    h = h.lstrip("#"); return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)

def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (c[3],)

def new():
    return Image.new("RGBA", (16, 16), (0, 0, 0, 0))

# Shaft runs diagonally from bottom-left (1,14) to top-right (11,4); gem sits at top-right.
SHAFT = [(1 + i, 14 - i) for i in range(11)]

def wand(name, wood, grip, gem, extra=None, glow=None):
    im = new(); p = im.load()
    light, dark = shade(wood, 1.25), shade(wood, 0.6)
    for i, (x, y) in enumerate(SHAFT):
        base = grip if i <= 3 else wood
        p[x, y] = base
        if y - 1 >= 0: p[x, y - 1] = shade(base, 1.25) if i > 0 else dark   # highlight edge
        if x + 1 < 16: p[x + 1, y] = shade(base, 0.62)                       # shadow edge
    # pommel
    p[0, 15] = shade(grip, 0.5); p[1, 15] = shade(grip, 0.7); p[0, 14] = shade(grip, 0.8)
    # grip wrap stripes
    for (x, y) in SHAFT[1:4:2]:
        p[x, y] = shade(grip, 1.4)
    # gem (3x3 diamond-ish) at top-right
    gx, gy = 12, 3
    g_hi, g_lo = shade(gem, 1.35), shade(gem, 0.65)
    for dx, dy, c in [(0, -1, g_hi), (-1, 0, gem), (0, 0, g_hi), (1, 0, gem), (0, 1, g_lo), (1, -1, gem), (-1, 1, g_lo), (1, 1, g_lo), (-1, -1, gem)]:
        p[gx + dx, gy + dy] = c
    p[gx, gy] = (255, 255, 255, 255)
    if glow:  # sparkle pixels
        for (x, y) in glow:
            p[x, y] = shade(gem, 1.5)[:3] + (200,)
    if extra: extra(p)
    im.save(os.path.join(ITEM, name + ".png"))

def ember_extra(p):  # golden claw holding the ember gem
    gold = hexc("#f2c14e")
    for x, y in [(10, 2), (11, 1), (14, 4), (15, 3), (10, 5), (13, 6)]: p[x, y] = gold
def frost_extra(p):  # ice prongs
    ice = hexc("#d8f6ff")
    for x, y in [(12, 0), (15, 2), (15, 1), (9, 3), (14, 6)]: p[x, y] = ice
def storm_extra(p):  # copper rings + sparks
    cop = hexc("#e08a4f")
    for x, y in [(5, 10), (8, 7)]: p[x, y] = cop; p[x + 1, y - 1] = cop
    for x, y in [(14, 1), (10, 0), (15, 5)]: p[x, y] = hexc("#fff59a")
def grove_extra(p):  # leaves sprouting from the shaft
    leaf, leaf2 = hexc("#5fd35f"), hexc("#3d9e3d")
    for x, y in [(6, 7), (7, 7), (6, 6), (9, 3), (9, 2), (10, 2), (4, 11), (3, 11)]: p[x, y] = leaf
    for x, y in [(7, 6), (10, 1)]: p[x, y] = leaf2
def void_extra(p):  # orbiting shards
    vio = hexc("#c38bff")
    for x, y in [(15, 0), (9, 1), (15, 6), (7, 8)]: p[x, y] = vio
def arch_extra(p):  # gold bands + crown
    gold = hexc("#ffd75e")
    for x, y in [(4, 11), (7, 8), (9, 6)]: p[x, y] = gold
    for x, y in [(11, 0), (13, 0), (15, 2), (15, 4), (10, 1)]: p[x, y] = gold

wand("apprentice_wand", hexc("#9a6a3a"), hexc("#5a3a1e"), hexc("#6fb8ff"))
wand("ember_wand", hexc("#3b2219"), hexc("#7a1f12"), hexc("#ff7a2a"), ember_extra)
wand("frost_wand", hexc("#cfe3ef"), hexc("#5b7a99"), hexc("#8fe6ff"), frost_extra)
wand("storm_wand", hexc("#2c3a6b"), hexc("#151c38"), hexc("#ffe066"), storm_extra)
wand("grove_wand", hexc("#6b5531"), hexc("#3f5e2a"), hexc("#6dff8a"), grove_extra)
wand("void_wand", hexc("#1b1524"), hexc("#3a1f55"), hexc("#b070ff"), void_extra)
wand("archmage_wand", hexc("#f4f0e6"), hexc("#2d2a6b"), hexc("#ff5ec4"), arch_extra)

# ---- scrolls ----
rng = random.Random(7)
def scroll(name, seal):
    im = new(); p = im.load()
    paper, edge = hexc("#efe0b9"), hexc("#b99a62")
    for y in range(3, 13):
        for x in range(3, 13):
            c = paper if rng.random() > 0.12 else shade(paper, 0.93)
            p[x, y] = c
    for y in range(3, 13): p[3, y] = edge; p[12, y] = shade(edge, 0.9)
    # rolled ends
    for x in range(2, 14):
        p[x, 2] = hexc("#d9c08a"); p[x, 1] = edge
        p[x, 13] = hexc("#d9c08a"); p[x, 14] = edge
    p[1, 1] = p[14, 1] = p[1, 14] = p[14, 14] = shade(edge, 0.8)
    # writing lines
    for y in (5, 7, 9):
        for x in range(5, 11):
            if rng.random() > 0.25: p[x, y] = hexc("#6b5a44")
    if seal:
        s_hi, s_lo = shade(seal, 1.3), shade(seal, 0.7)
        for x, y in [(9, 10), (10, 10), (9, 11), (10, 11), (8, 11), (11, 10)]:
            p[x, y] = seal
        p[9, 10] = s_hi; p[10, 11] = s_lo; p[9, 12] = s_lo; p[10, 12] = seal
    im.save(os.path.join(ITEM, name + ".png"))

scroll("blank_scroll", None)
for el, col in [("arcane", "#7fb8ff"), ("fire", "#ff6a2a"), ("frost", "#8fe6ff"), ("storm", "#ffd84a"), ("nature", "#5fd35f"), ("void", "#a259ff")]:
    scroll("spell_scroll_" + el, hexc(col))

# ---- conjured blocks ----
def block(name, fn):
    im = Image.new("RGBA", (16, 16)); p = im.load()
    for y in range(16):
        for x in range(16): p[x, y] = fn(x, y)
    im.save(os.path.join(BLOCK, name + ".png"))

def ice(x, y):
    base = (150, 215, 255)
    k = 1 + (rng.random() - 0.5) * 0.08
    if (x + y) % 7 == 0 or (x - y) % 11 == 0: k += 0.18      # crystal streaks
    if x in (0, 15) or y in (0, 15): k += 0.25
    rune = abs(x - 7.5) + abs(y - 7.5)
    a = 150
    if 4.6 < rune < 5.6: return (210, 250, 255, 220)           # faint glowing sigil
    return tuple(min(255, int(c * k)) for c in base) + (a,)
block("conjured_ice", ice)

def stone(x, y):
    base = (112, 108, 122)
    k = 1 + (rng.random() - 0.5) * 0.22
    if x in (0, 15) or y in (0, 15): k *= 0.75
    if (x * 3 + y * 5) % 17 == 0: k *= 0.7
    rune = abs(x - 7.5) + abs(y - 7.5)
    if 4.6 < rune < 5.6 or (x in (7, 8) and 4 < y < 11): return (150, 120, 255, 255)
    return tuple(min(255, int(c * k)) for c in base) + (255,)
block("conjured_stone", stone)

# ---- mod icon (128x128, upscaled wand on a dark violet disc) ----
icon = Image.new("RGBA", (128, 128), (0, 0, 0, 0)); ip = icon.load()
for y in range(128):
    for x in range(128):
        d = math.hypot(x - 64, y - 64)
        if d < 62: ip[x, y] = (int(40 + 30 * (1 - d / 62)), int(20 + 10 * (1 - d / 62)), int(70 + 60 * (1 - d / 62)), 255)
w = Image.open(os.path.join(ITEM, "archmage_wand.png")).resize((96, 96), Image.NEAREST)
icon.alpha_composite(w, (16, 16))
icon_dir = os.path.join(os.path.dirname(__file__), "..", "arcanum", "src", "main", "resources", "assets", "arcanum")
icon.save(os.path.join(icon_dir, "icon.png"))
print("textures written")
