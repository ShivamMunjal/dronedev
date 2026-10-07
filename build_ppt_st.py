#!/usr/bin/env python3
"""Electrostatic Spray proposal — ST style (blue #03234B + yellow #FFD200), visual/diagram-first."""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(10.0)
prs.slide_height = Inches(5.625)
BLANK = prs.slide_layouts[6]

ST_BLUE = RGBColor(0x03, 0x23, 0x4B)
ST_YELLOW = RGBColor(0xFF, 0xD2, 0x00)
CARD = RGBColor(0xF4, 0xF4, 0xF5)
BORDER = RGBColor(0xD1, 0xD5, 0xDB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x03, 0x23, 0x4B)
GREY = RGBColor(0x5B, 0x65, 0x74)
GREEN = RGBColor(0x1B, 0x9E, 0x57)
RED = RGBColor(0xD9, 0x2D, 0x20)
LTEAL = RGBColor(0xD9, 0xEF, 0xF7)
LGREEN = RGBColor(0xE3, 0xF5, 0xE9)
AMBER_BG = RGBColor(0xFF, 0xF8, 0xE1)

LOGO = "/Users/shivammunjal/Claude Code/DroneProject/st_assets/slide4_pic5.png"
TOTAL = 10

# ---------- chrome ----------
def chrome(slide, title, caption="", num=0):
    # top bar
    b = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(10), Inches(0.94))
    b.fill.solid(); b.fill.fore_color.rgb = ST_BLUE; b.line.fill.background()
    # yellow accent
    y = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.31), Inches(5.625))
    y.fill.solid(); y.fill.fore_color.rgb = ST_YELLOW; y.line.fill.background()
    # logo
    try:
        slide.shapes.add_picture(LOGO, Inches(8.54), Inches(0.04), Inches(1.25), Inches(0.85))
    except Exception:
        pass
    # title
    t = slide.shapes.add_textbox(Inches(0.62), Inches(0.21), Inches(7.7), Inches(0.52))
    t.text_frame.word_wrap = True
    p = t.text_frame.paragraphs[0]
    p.text = title; p.font.size = Pt(20); p.font.bold = True
    p.font.color.rgb = WHITE; p.font.name = "Arial"
    # bottom bar + caption
    f = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(5.31), Inches(10), Inches(0.31))
    f.fill.solid(); f.fill.fore_color.rgb = ST_BLUE; f.line.fill.background()
    c = slide.shapes.add_textbox(Inches(0.62), Inches(5.31), Inches(8.0), Inches(0.31))
    c.text_frame.word_wrap = True
    c.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    pc = c.text_frame.paragraphs[0]
    pc.text = caption; pc.font.size = Pt(8); pc.font.color.rgb = WHITE; pc.font.name = "Arial"
    n = slide.shapes.add_textbox(Inches(9.3), Inches(5.31), Inches(0.5), Inches(0.31))
    n.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    pn = n.text_frame.paragraphs[0]
    pn.text = f"{num}"; pn.font.size = Pt(8); pn.font.color.rgb = WHITE
    pn.font.name = "Arial"; pn.alignment = PP_ALIGN.RIGHT

def txt(slide, l, t, w, h, s_, size=12, bold=False, color=INK, align=PP_ALIGN.LEFT, name="Arial"):
    tx = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tx.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = s_; p.font.size = Pt(size); p.font.bold = bold
    p.font.color.rgb = color; p.font.name = name; p.alignment = align
    return tx

def box(slide, l, t, w, h, fill=CARD, line=BORDER, lw=0.75):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line; s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    return s

def arrow_down(slide, cx, t, h=0.22, w=0.22, color=ST_BLUE):
    a = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(cx - w/2), Inches(t), Inches(w), Inches(h))
    a.fill.solid(); a.fill.fore_color.rgb = color; a.line.fill.background()
    return a

def arrow_right(slide, l, cy, w=0.3, h=0.18, color=ST_BLUE):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(l), Inches(cy - h/2), Inches(w), Inches(h))
    a.fill.solid(); a.fill.fore_color.rgb = color; a.line.fill.background()
    return a

def bar(slide, l, t, w_total, h, frac, fill, bg=CARD):
    b = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w_total), Inches(h))
    b.fill.solid(); b.fill.fore_color.rgb = bg; b.line.fill.background()
    f = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w_total*frac), Inches(h))
    f.fill.solid(); f.fill.fore_color.rgb = fill; f.line.fill.background()

# ================= S1 TITLE =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = ST_BLUE
y = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.31), Inches(5.625))
y.fill.solid(); y.fill.fore_color.rgb = ST_YELLOW; y.line.fill.background()
try:
    s.shapes.add_picture(LOGO, Inches(8.54), Inches(0.25), Inches(1.25), Inches(0.85))
except Exception:
    pass
txt(s, 0.62, 0.5, 8.0, 0.35, "AGRICULTURAL DRONES  •  PRECISION SPRAYING", 11, True, ST_YELLOW)
txt(s, 0.62, 0.95, 8.0, 1.5, "Electrostatic Spray\nCharging for Drones", 36, True, WHITE)
txt(s, 0.62, 2.75, 6.2, 0.5, "Cutting spray drift by 75% — a drone-ready retrofit.", 14, False, WHITE)
# 3 stat chips (yellow)
for i, (v, lbl) in enumerate([("75%", "drift reduction"), ("3×", "leaf deposition"), ("50%", "chemical saving")]):
    x = 0.62 + i*1.95
    box(s, x, 3.6, 1.75, 1.0, fill=ST_YELLOW, line=None)
    txt(s, x, 3.65, 1.75, 0.55, v, 26, True, ST_BLUE, PP_ALIGN.CENTER)
    txt(s, x, 4.2, 1.75, 0.35, lbl, 10, True, ST_BLUE, PP_ALIGN.CENTER)
txt(s, 0.62, 4.85, 8.0, 0.3, "Confidential proposal  •  September 2025", 9, False, WHITE)
# right card
box(s, 7.0, 1.1, 2.4, 3.5, fill=WHITE, line=None)
txt(s, 7.2, 1.3, 2.0, 0.3, "ONE NUMBER", 10, True, GREY, PP_ALIGN.CENTER)
txt(s, 7.2, 1.65, 2.0, 0.6, "$18,000", 34, True, RED, PP_ALIGN.CENTER)
txt(s, 7.2, 2.3, 2.0, 0.6, "wasted per 1,000 ha / season on drifted chemical", 10, False, GREY, PP_ALIGN.CENTER)
bar(s, 7.25, 3.0, 1.9, 0.28, 0.35, RED)
txt(s, 7.25, 3.32, 1.9, 0.25, "Conventional: 35% on target", 8, False, GREY, PP_ALIGN.CENTER)
bar(s, 7.25, 3.62, 1.9, 0.28, 0.78, GREEN)
txt(s, 7.25, 3.94, 1.9, 0.25, "Electrostatic: 78% on target", 8, False, GREY, PP_ALIGN.CENTER)
txt(s, 7.2, 4.25, 2.0, 0.25, "U. of Georgia field trials", 8, False, GREY, PP_ALIGN.CENTER)

# ================= S2 PROBLEM (diagram) =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "The problem: most spray misses the leaf", "Wind 10–15 km/h  •  altitude 2–3 m  •  conventional hydraulic nozzle", 2)
# drone
box(s, 1.1, 1.5, 1.3, 0.35, fill=ST_BLUE, line=None)
txt(s, 1.1, 1.56, 1.3, 0.25, "✛  SPRAY DRONE", 9, True, WHITE, PP_ALIGN.CENTER)
# spray cone (triangle)
cone = s.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, Inches(1.35), Inches(1.9), Inches(0.8), Inches(1.1))
cone.rotation = 180.0
cone.fill.solid(); cone.fill.fore_color.rgb = LTEAL; cone.line.fill.background()
txt(s, 1.15, 2.35, 1.2, 0.25, "spray", 8, False, GREY, PP_ALIGN.CENTER)
# wind arrow
arrow_right(s, 2.5, 2.2, w=1.7, h=0.22, color=ST_BLUE)
txt(s, 2.5, 1.85, 1.7, 0.25, "wind 10–15 km/h", 9, True, ST_BLUE, PP_ALIGN.CENTER)
# drift cloud
for (cx, cy, w, h) in [(4.3, 2.0, 0.7, 0.45), (4.9, 2.2, 0.9, 0.55), (5.6, 2.0, 0.7, 0.45)]:
    o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx), Inches(cy), Inches(w), Inches(h))
    o.fill.solid(); o.fill.fore_color.rgb = RGBColor(0xE5,0xE7,0xEB); o.line.fill.background()
txt(s, 4.3, 2.85, 2.0, 0.3, "drift cloud: 15–30 m", 9, True, RED, PP_ALIGN.CENTER)
# crop row
for i in range(6):
    x = 0.9 + i*0.55
    g = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(3.9), Inches(0.4), Inches(0.5))
    g.fill.solid(); g.fill.fore_color.rgb = GREEN; g.line.fill.background()
txt(s, 0.9, 4.45, 3.3, 0.25, "crop row — only ~35% lands here", 9, False, GREY, PP_ALIGN.CENTER)
# right stats
box(s, 7.0, 1.5, 2.4, 1.3, fill=AMBER_BG, line=ST_YELLOW)
txt(s, 7.2, 1.65, 2.0, 0.6, "40% lost", 26, True, RED, PP_ALIGN.CENTER)
txt(s, 7.2, 2.25, 2.0, 0.4, "of every tank drifts away", 10, False, INK, PP_ALIGN.CENTER)
box(s, 7.0, 3.0, 2.4, 1.3, fill=CARD, line=BORDER)
txt(s, 7.2, 3.15, 2.0, 0.6, "< 5% reach", 22, True, ST_BLUE, PP_ALIGN.CENTER)
txt(s, 7.2, 3.7, 2.0, 0.4, "the leaf underside where pests live", 10, False, INK, PP_ALIGN.CENTER)

# ================= S3 MONEY FLOW =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "What drift costs — per hectare", "$0.22/L chemical  •  150 L/ha  •  40% drift (conventional)", 3)
# 3 flow boxes
box(s, 0.62, 1.7, 2.5, 1.9, fill=CARD, line=BORDER)
txt(s, 0.82, 1.9, 2.1, 0.3, "SPEND", 10, True, GREY, PP_ALIGN.CENTER)
txt(s, 0.82, 2.25, 2.1, 0.5, "$33.00", 30, True, ST_BLUE, PP_ALIGN.CENTER)
txt(s, 0.82, 2.85, 2.1, 0.5, "chemical per hectare per pass", 10, False, INK, PP_ALIGN.CENTER)
arrow_right(s, 3.2, 2.65, w=0.5, h=0.25, color=RED)
box(s, 3.8, 1.7, 2.5, 1.9, fill=RGBColor(0xFE,0xE2,0xE2), line=RED)
txt(s, 4.0, 1.9, 2.1, 0.3, "DRIFTS AWAY", 10, True, RED, PP_ALIGN.CENTER)
txt(s, 4.0, 2.25, 2.1, 0.5, "$13.20", 30, True, RED, PP_ALIGN.CENTER)
txt(s, 4.0, 2.85, 2.1, 0.5, "60 litres lost to wind", 10, False, INK, PP_ALIGN.CENTER)
arrow_right(s, 6.4, 2.65, w=0.5, h=0.25, color=GREEN)
box(s, 7.0, 1.7, 2.4, 1.9, fill=LGREEN, line=GREEN)
txt(s, 7.2, 1.9, 2.0, 0.3, "WORKS", 10, True, GREEN, PP_ALIGN.CENTER)
txt(s, 7.2, 2.25, 2.0, 0.5, "$19.80", 30, True, GREEN, PP_ALIGN.CENTER)
txt(s, 7.2, 2.85, 2.0, 0.5, "only this part hits the leaf", 10, False, INK, PP_ALIGN.CENTER)
box(s, 0.62, 3.9, 8.78, 1.0, fill=ST_BLUE, line=None)
txt(s, 0.82, 4.05, 8.38, 0.7, "Electrostatic keeps $9.24/ha on the leaf  →  $9,240 per 1,000 ha per season  →  hardware pays back in < 25 ha.", 12, True, WHITE, PP_ALIGN.CENTER)

# ================= S4 WHY INCUMBENTS FAIL =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Nobody selling spray drones charges the droplets", "DJI • XAG • Hylio • Deere • ESS — all hydraulic or ground-only", 4)
brands = [("DJI Agras", "$15–25K", "no charging"), ("XAG P100", "$12–20K", "no charging"), ("John Deere", "$150K+", "ground only"), ("ESS rigs", "$5–15K", "ground only")]
for i, (b_, p_, n_) in enumerate(brands):
    x = 0.62 + i*2.25
    box(s, x, 1.6, 2.05, 1.7, fill=CARD, line=BORDER)
    txt(s, x+0.15, 1.8, 1.75, 0.35, b_, 13, True, ST_BLUE, PP_ALIGN.CENTER)
    txt(s, x+0.15, 2.2, 1.75, 0.35, p_, 12, False, GREY, PP_ALIGN.CENTER)
    no = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x+0.62), Inches(2.6), Inches(0.8), Inches(0.5))
    no.fill.solid(); no.fill.fore_color.rgb = RED; no.line.fill.background()
    txt(s, x+0.62, 2.68, 0.8, 0.35, "✕", 16, True, WHITE, PP_ALIGN.CENTER)
    txt(s, x+0.15, 2.95, 1.75, 0.25, n_, 9, False, GREY, PP_ALIGN.CENTER)
box(s, 0.62, 3.6, 8.78, 1.4, fill=AMBER_BG, line=ST_YELLOW)
txt(s, 0.82, 3.75, 8.38, 1.0, "5 barriers kept charging off drones — HV weight  •  arcing near LiPo  •  charge saturation  •  awareness  •  legal grey zone.   Our design clears all five (next slides).", 11, True, INK, PP_ALIGN.CENTER)

# ================= S5 SOLUTION FLOWCHART =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Solution: charge each droplet as it leaves the nozzle", "Induction charging  •  6–12 kV  •  10–50 µA  •  fits existing nozzles", 5)
stages = [
    ("1  PUMP", "0.2–0.5 MPa\n100–300 µm", CARD),
    ("2  CHARGE", "induction ring\n6–12 kV", ST_YELLOW),
    ("3  FLY", "0.5–2.0 mC/kg\nrepel = no clump", LTEAL),
    ("4  STICK", "wraps leaf\n+ underside", LGREEN),
]
for i, (h, body, fill) in enumerate(stages):
    x = 0.62 + i*2.3
    box(s, x, 1.6, 2.0, 1.6, fill=fill, line=BORDER if fill != ST_YELLOW else ST_BLUE)
    txt(s, x+0.15, 1.8, 1.7, 0.35, h, 13, True, ST_BLUE, PP_ALIGN.CENTER)
    txt(s, x+0.15, 2.25, 1.7, 0.7, body, 10, False, INK, PP_ALIGN.CENTER)
    if i < 3:
        arrow_right(s, x+2.0, 2.4, w=0.3, h=0.2, color=ST_BLUE)
# leaf wrap mini-diagram
box(s, 0.62, 3.5, 8.78, 1.5, fill=CARD, line=BORDER)
txt(s, 0.82, 3.6, 3.0, 0.3, "WHY IT WORKS", 10, True, GREY)
leaf = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4.2), Inches(3.95), Inches(1.6), Inches(0.7))
leaf.fill.solid(); leaf.fill.fore_color.rgb = GREEN; leaf.line.fill.background()
txt(s, 4.2, 4.12, 1.6, 0.35, "leaf", 11, True, WHITE, PP_ALIGN.CENTER)
for (l, t2, w, h, rot) in [(3.3, 3.7, 0.5, 0.16, 35), (5.6, 3.7, 0.5, 0.16, -35), (3.3, 4.5, 0.5, 0.16, -35), (5.6, 4.5, 0.5, 0.16, 35)]:
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(l), Inches(t2), Inches(w), Inches(h))
    a.rotation = rot
    a.fill.solid(); a.fill.fore_color.rgb = ST_BLUE; a.line.fill.background()
txt(s, 6.2, 3.9, 2.9, 0.9, "Leaf is grounded through soil →\nfield lines pull droplets around\nand under. 40–60% reach the\nunderside (vs ~5% before).", 10, False, INK)

# ================= S6 SYSTEM ARCHITECTURE =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "System architecture — 4 layers", "CAN bus links every layer  •  STM32G4 at the centre", 6)
layers = [
    ("LAYER 1 — FLIGHT", "ArduPilot + RTK  →  spray commands over CAN / MAVLink"),
    ("LAYER 2 — CONTROL", "STM32G4  →  PID voltage per nozzle + current limit + prop-kill interlock"),
    ("LAYER 3 — SPRAY ×4", "HV PSU (12 V → 16 kV)  →  induction ring  →  hydraulic nozzle"),
    ("LAYER 4 — POWER", "12 V rail  →  isolated HV  →  ADC feedback (1000:1) + 50 µA cap"),
]
yy = 1.35
for i, (h, body) in enumerate(layers):
    box(s, 0.62, yy, 7.6, 0.78, fill=CARD, line=BORDER)
    txt(s, 0.85, yy+0.06, 7.15, 0.28, h, 10, True, ST_BLUE)
    txt(s, 0.85, yy+0.32, 7.15, 0.4, body, 9, False, INK)
    if i < 3:
        arrow_down(s, 4.4, yy+0.78, h=0.14, w=0.2, color=ST_BLUE)
    yy += 0.95
# side bus labels
box(s, 8.4, 1.35, 1.0, 3.6, fill=ST_BLUE, line=None)
txt(s, 8.45, 1.5, 0.9, 3.3, "C\nA\nN\n\nb\nu\ns", 9, True, WHITE, PP_ALIGN.CENTER)

# ================= S7 CONTROL LOOP =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Control loop — per nozzle, every 5 ms", "PID on voltage  •  hard current cap  •  fail-safe by default", 7)
# main column
box(s, 1.0, 1.35, 2.0, 0.5, fill=ST_BLUE, line=None)
txt(s, 1.0, 1.45, 2.0, 0.3, "Target voltage via CAN", 10, True, WHITE, PP_ALIGN.CENTER)
arrow_down(s, 2.0, 1.85, h=0.15, color=ST_BLUE)
box(s, 1.0, 2.0, 2.0, 0.5, fill=CARD, line=BORDER)
txt(s, 1.0, 2.1, 2.0, 0.3, "Measure HV (ADC)", 10, True, ST_BLUE, PP_ALIGN.CENTER)
arrow_down(s, 2.0, 2.5, h=0.15, color=ST_BLUE)
d1 = s.shapes.add_shape(MSO_SHAPE.DIAMOND, Inches(1.15), Inches(2.65), Inches(1.7), Inches(0.75))
d1.fill.solid(); d1.fill.fore_color.rgb = ST_YELLOW; d1.line.fill.background()
txt(s, 1.15, 2.85, 1.7, 0.4, "V = target?", 11, True, ST_BLUE, PP_ALIGN.CENTER)
# no branch -> adjust
arrow_right(s, 2.85, 3.0, w=0.5, h=0.16, color=ST_BLUE)
txt(s, 2.9, 2.75, 0.5, 0.2, "no", 8, True, RED, PP_ALIGN.CENTER)
box(s, 3.4, 2.75, 1.7, 0.5, fill=CARD, line=BORDER)
txt(s, 3.4, 2.85, 1.7, 0.3, "Adjust DAC (PID)", 10, True, ST_BLUE, PP_ALIGN.CENTER)
up = s.shapes.add_shape(MSO_SHAPE.UP_ARROW, Inches(4.95), Inches(2.1), Inches(0.18), Inches(0.65))
up.fill.solid(); up.fill.fore_color.rgb = ST_BLUE; up.line.fill.background()
# yes branch down
arrow_down(s, 2.0, 3.4, h=0.15, color=ST_BLUE)
txt(s, 1.55, 3.42, 0.9, 0.2, "yes", 8, True, GREEN, PP_ALIGN.CENTER)
d2 = s.shapes.add_shape(MSO_SHAPE.DIAMOND, Inches(1.15), Inches(3.6), Inches(1.7), Inches(0.75))
d2.fill.solid(); d2.fill.fore_color.rgb = ST_YELLOW; d2.line.fill.background()
txt(s, 1.15, 3.8, 1.7, 0.4, "Current < 50 µA?", 11, True, ST_BLUE, PP_ALIGN.CENTER)
arrow_down(s, 2.0, 4.35, h=0.12, color=GREEN)
txt(s, 1.55, 4.35, 0.9, 0.2, "yes", 8, True, GREEN, PP_ALIGN.CENTER)
box(s, 1.0, 4.5, 2.0, 0.5, fill=LGREEN, line=GREEN)
txt(s, 1.0, 4.6, 2.0, 0.3, "✔  HOLD + SPRAY", 10, True, GREEN, PP_ALIGN.CENTER)
# fault branch
arrow_right(s, 2.85, 3.95, w=0.5, h=0.16, color=RED)
txt(s, 2.9, 3.7, 0.5, 0.2, "no", 8, True, RED, PP_ALIGN.CENTER)
box(s, 3.4, 3.7, 1.7, 0.5, fill=RGBColor(0xFE,0xE2,0xE2), line=RED)
txt(s, 3.4, 3.8, 1.7, 0.3, "✕  FAULT → kill props", 10, True, RED, PP_ALIGN.CENTER)
# right notes
box(s, 6.9, 1.35, 2.5, 3.65, fill=CARD, line=BORDER)
txt(s, 7.1, 1.5, 2.1, 0.3, "SAFETY RULES", 10, True, ST_BLUE)
for j, t_ in enumerate(["50 µA hard cap", "16 kV ceiling", "HV fault = instant prop-kill", "Default state = OFF"]):
    txt(s, 7.1, 1.95 + j*0.45, 2.1, 0.35, "•  " + t_, 10, False, INK)
txt(s, 7.1, 3.9, 2.1, 0.9, "Wind-adaptive mode:\nIMU estimates crosswind →\nvoltage auto-tunes 6–12 kV.", 10, False, INK)

# ================= S8 PAPERS =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Research proof — 4 papers, one verdict", "Full DOIs in closing slide  •  verified via Semantic Scholar", 8)
papers = [
    ("Zhang 2017", "59 cit.", "First UAV system · 2–3× deposition", 1.0),
    ("Hanif 2022", "82 cit.", "“Most promising” + CAN control", 1.0),
    ("Li 2025", "11 cit.", "Two-stage · 1.62 mC/kg", 0.35),
    ("Zhao 2024", "17 cit.", "Orchard-proven contact charging", 0.45),
]
for i, (t_, c_, d_, frac) in enumerate(papers):
    x = 0.62 + i*2.25
    box(s, x, 1.5, 2.05, 2.9, fill=CARD, line=BORDER)
    txt(s, x+0.15, 1.7, 1.75, 0.35, t_, 13, True, ST_BLUE, PP_ALIGN.CENTER)
    txt(s, x+0.15, 2.1, 1.75, 0.35, c_, 11, True, GREY, PP_ALIGN.CENTER)
    bar(s, x+0.25, 2.55, 1.55, 0.22, frac, ST_BLUE)
    txt(s, x+0.15, 2.9, 1.75, 0.9, d_, 10, False, INK, PP_ALIGN.CENTER)
    if i == 1:
        ribbon = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x+0.35), Inches(3.75), Inches(1.35), Inches(0.32))
        ribbon.fill.solid(); ribbon.fill.fore_color.rgb = ST_YELLOW; ribbon.line.fill.background()
        txt(s, x+0.35, 3.77, 1.35, 0.28, "★ TOP VERDICT", 8, True, ST_BLUE, PP_ALIGN.CENTER)
txt(s, 0.62, 4.55, 8.78, 0.4, "+ Zhang & Huang 2021 (27 cit.): China has 200,000+ spray drones, <5% electrostatic  •  Hu & Kaizu 2022 (28 cit.): 30–50% waste cut", 9, False, GREY, PP_ALIGN.CENTER)

# ================= S9 UGA BARS =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Field proof — University of Georgia", "Cotton / peanut / soybean  •  5–15 km/h wind", 9)
txt(s, 0.62, 1.3, 5.5, 0.35, "ON-TARGET DEPOSITION", 11, True, GREY)
txt(s, 0.62, 1.75, 2.2, 0.35, "Conventional  35%", 12, True, INK)
bar(s, 2.9, 1.75, 3.4, 0.4, 0.35, RED)
txt(s, 0.62, 2.3, 2.2, 0.35, "Electrostatic  78%", 12, True, INK)
bar(s, 2.9, 2.3, 3.4, 0.4, 0.78, GREEN)
txt(s, 0.62, 2.85, 5.5, 0.35, "LEAF-UNDERSIDE REACH", 11, True, GREY)
txt(s, 0.62, 3.2, 2.2, 0.35, "Conventional  ~5%", 12, True, INK)
bar(s, 2.9, 3.2, 3.4, 0.4, 0.08, RED)
txt(s, 0.62, 3.75, 2.2, 0.35, "Electrostatic  50%", 12, True, INK)
bar(s, 2.9, 3.75, 3.4, 0.4, 0.55, GREEN)
for i, (v, lbl) in enumerate([("75%", "drift cut"), ("$10/ac", "saved"), ("8 kV", "field sweet-spot")]):
    x = 7.0 + i*0.82
    box(s, x, 1.5, 0.75, 2.6, fill=ST_BLUE, line=None)
    txt(s, x, 1.7, 0.75, 0.5, v, 13, True, ST_YELLOW, PP_ALIGN.CENTER)
    txt(s, x, 2.3, 0.75, 0.6, lbl, 8, True, WHITE, PP_ALIGN.CENTER)
box(s, 7.0, 4.25, 2.42, 0.75, fill=AMBER_BG, line=ST_YELLOW)
txt(s, 7.15, 4.35, 2.12, 0.55, "Orchards: 10–12 kV", 10, True, INK, PP_ALIGN.CENTER)

# ================= S10 ROADMAP + ASK =================
s = prs.slides.add_slide(BLANK)
s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
chrome(s, "Roadmap → patent → product", "File provisional BEFORE any publication", 10)
phases = [("P1 · 4–6 w", "Bench rig\n1 nozzle"), ("P2 · 6–8 w", "4-nozzle\nCAN system"), ("P3 · 4–6 w", "Flight trials\nfield data"), ("P4", "Patent →\nlicense")]
for i, (h, body) in enumerate(phases):
    x = 0.62 + i*2.0
    box(s, x, 1.4, 1.7, 1.3, fill=ST_YELLOW if i == 3 else CARD, line=ST_BLUE if i == 3 else BORDER)
    txt(s, x+0.1, 1.55, 1.5, 0.35, h, 11, True, ST_BLUE, PP_ALIGN.CENTER)
    txt(s, x+0.1, 1.95, 1.5, 0.6, body, 10, False, INK, PP_ALIGN.CENTER)
    if i < 3:
        arrow_right(s, x+1.7, 2.05, w=0.3, h=0.18, color=ST_BLUE)
box(s, 0.62, 2.95, 8.78, 1.0, fill=ST_BLUE, line=None)
txt(s, 0.82, 3.1, 8.38, 0.7, "ASK: approve the single-nozzle bench rig  →  field data  →  provisional patent.   Hardware ≈ $185/drone · payback < 25 ha.", 12, True, WHITE, PP_ALIGN.CENTER)
txt(s, 0.62, 4.1, 8.78, 0.9, "Refs: Zhang 2017 DOI:10.25165/IJABE.V10I6.3460  •  Li 2025 DOI:10.3390/agronomy15071641  •  Hanif 2022 (82 cit.)  •  Hu & Kaizu 2022 (28 cit.)  •  Thank you.", 8, False, GREY, PP_ALIGN.CENTER)

out = "/Users/shivammunjal/Claude Code/DroneProject/Electrostatic_Spray_Proposal_ST.pptx"
prs.save(out)
print(f"Saved to {out}")
