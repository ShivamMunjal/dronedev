#!/usr/bin/env python3
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(13.33)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]

NAVY = RGBColor(0x0B, 0x2C, 0x4A)
TEAL = RGBColor(0x00, 0xB4, 0xA2)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
LIGHT_BG = RGBColor(0xF1, 0xF5, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1E, 0x29, 0x3B)
GREY = RGBColor(0x64, 0x74, 0x8B)
LIGHT_GREY = RGBColor(0xE2, 0xE8, 0xF0)
CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)
TEAL_DARK = RGBColor(0x0E, 0x74, 0x6E)
RED = RGBColor(0xDC, 0x26, 0x26)
GREEN = RGBColor(0x16, 0xA3, 0x4A)

def bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color

def textbox(slide, l, t, w, h, text, size=18, bold=False, color=DARK, align=PP_ALIGN.LEFT, font_name="Calibri"):
    tx = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tx.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = align
    return tx

def bullets(slide, l, t, w, h, items, size=14, color=DARK, gap=6):
    tx = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tx.text_frame
    tf.word_wrap = True
    for i, (txt, bld, clr) in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = txt
        p.font.size = Pt(size)
        p.font.bold = bld
        p.font.color.rgb = clr if clr else color
        p.font.name = "Calibri"
        p.space_after = Pt(gap)
        p.level = 0
    return tx

def card(slide, l, t, w, h, fill_color=CARD_BG, line_color=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill_color
    s.line.fill.background()
    if line_color:
        s.line.color.rgb = line_color
        s.line.width = Pt(1)
    return s

def top_bar(slide):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, Inches(0.08))
    bar.fill.solid(); bar.fill.fore_color.rgb = TEAL
    bar.line.fill.background()

def footer(slide, num, total):
    textbox(slide, 0.4, 7.05, 6, 0.3, "Electrostatic Spray Charging  •  Agricultural Drones  •  Confidential", size=8, color=GREY)
    textbox(slide, 12.2, 7.05, 0.7, 0.3, f"{num}/{total}", size=8, color=GREY, align=PP_ALIGN.RIGHT)

def section_label(slide, l, t, text):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(1.6), Inches(0.35))
    s.fill.solid(); s.fill.fore_color.rgb = TEAL
    s.line.fill.background()
    s.text_frame.word_wrap = True
    s.text_frame.paragraphs[0].text = text
    s.text_frame.paragraphs[0].font.size = Pt(10)
    s.text_frame.paragraphs[0].font.bold = True
    s.text_frame.paragraphs[0].font.color.rgb = WHITE
    s.text_frame.paragraphs[0].font.name = "Calibri"
    s.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    s.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

def styled_table(slide, l, t, w, h, rows_data, col_widths=None, header_color=NAVY, font_size=11):
    rows = len(rows_data); cols = len(rows_data[0])
    tbl_shape = slide.shapes.add_table(rows, cols, Inches(l), Inches(t), Inches(w), Inches(h))
    tbl = tbl_shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            tbl.columns[i].width = Inches(cw)
    for r in range(rows):
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.text = rows_data[r][c]
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(font_size)
                p.font.name = "Calibri"
                p.alignment = PP_ALIGN.CENTER if c > 0 or r == 0 else PP_ALIGN.LEFT
                if r == 0:
                    p.font.bold = True
                    p.font.color.rgb = WHITE
                else:
                    p.font.color.rgb = DARK
                    p.font.bold = False
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            if r == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = header_color
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if r % 2 == 1 else LIGHT_BG
    return tbl_shape

TOTAL = 16

# ── SLIDE 1: Title ──
s = prs.slides.add_slide(BLANK); bg(s, NAVY)
# teal accent bar left
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(0.6), Inches(0.08), Inches(5.3))
bar.fill.solid(); bar.fill.fore_color.rgb = TEAL; bar.line.fill.background()
textbox(s, 1.1, 0.7, 7.5, 0.4, "AGRICULTURAL DRONES  •  PRECISION SPRAYING", size=13, bold=True, color=TEAL)
textbox(s, 1.1, 1.2, 7.5, 1.8, "Electrostatic Spray\nCharging for Drones", size=44, bold=True, color=WHITE)
textbox(s, 1.1, 3.4, 7.5, 0.8, "Solving 40% chemical drift — proven 75% reduction, 3× deposition.", size=16, color=RGBColor(0xC8,0xD6,0xE5))
# stats row
for i, (v, lbl) in enumerate([("75%", "DRIFT\nREDUCTION"), ("3×", "LEAF\nDEPOSITION"), ("50%", "CHEMICAL\nSAVINGS")]):
    x = 1.1 + i*1.9
    card(s, x, 4.5, 1.7, 1.1, fill_color=RGBColor(0x13,0x3D,0x5E))
    textbox(s, x, 4.55, 1.7, 0.6, v, size=32, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
    textbox(s, x, 5.15, 1.7, 0.45, lbl, size=9, bold=True, color=RGBColor(0xC8,0xD6,0xE5), align=PP_ALIGN.CENTER)
textbox(s, 1.1, 6.0, 7.5, 0.4, "Proposal  •  September 2025  •  Confidential", size=10, color=GREY)
# right panel card
card(s, 9.0, 0.7, 3.6, 6.1, fill_color=WHITE)
textbox(s, 9.4, 1.0, 2.8, 0.4, "THE PROBLEM IN ONE NUMBER", size=10, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
textbox(s, 9.4, 1.5, 2.8, 0.8, "$18,000", size=44, bold=True, color=RED, align=PP_ALIGN.CENTER)
textbox(s, 9.4, 2.3, 2.8, 0.5, "chemical wasted per 1,000 ha / season\nwith conventional drone spraying", size=11, color=GREY, align=PP_ALIGN.CENTER)
textbox(s, 9.4, 3.1, 2.8, 0.5, "35–50% of spray never reaches the target.\nIt drifts to neighbours, water, air.", size=11, color=DARK, align=PP_ALIGN.CENTER)
# mini comparison bars
textbox(s, 9.4, 3.9, 2.8, 0.3, "ON-TARGET DEPOSITION", size=9, bold=True, color=GREY, align=PP_ALIGN.CENTER)
# conventional bar
textbox(s, 9.4, 4.25, 2.8, 0.25, "Conventional  35%", size=9, color=GREY)
b1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.4), Inches(4.55), Inches(2.8), Inches(0.28))
b1.fill.solid(); b1.fill.fore_color.rgb = LIGHT_GREY; b1.line.fill.background()
f1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.4), Inches(4.55), Inches(2.8*0.35), Inches(0.28))
f1.fill.solid(); f1.fill.fore_color.rgb = RED; f1.line.fill.background()
textbox(s, 9.4, 4.9, 2.8, 0.25, "Electrostatic  78%", size=9, color=GREY)
b2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.4), Inches(5.2), Inches(2.8), Inches(0.28))
b2.fill.solid(); b2.fill.fore_color.rgb = LIGHT_GREY; b2.line.fill.background()
f2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.4), Inches(5.2), Inches(2.8*0.78), Inches(0.28))
f2.fill.solid(); f2.fill.fore_color.rgb = GREEN; f2.line.fill.background()
textbox(s, 9.4, 5.6, 2.8, 0.5, "Source: Univ. of Georgia field trials\n+ Li et al. 2025, Agronomy", size=8, color=GREY, align=PP_ALIGN.CENTER)

# ── SLIDE 2: Agenda ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 2, TOTAL)
section_label(s, 0.6, 0.4, "ROADMAP")
textbox(s, 0.6, 0.9, 12, 0.7, "What this proposal covers", size=30, bold=True, color=NAVY)
items = [
    ("01", "The problem — drift, waste & stalled adoption", "Data + field calculations"),
    ("02", "Why current drones fail — DJI / XAG limits", "Ceilings of hydraulic spray"),
    ("03", "Proposed solution — electrostatic induction charging", "Physics + system design"),
    ("04", "What research proves — 6 peer-reviewed papers", "Numbers, not claims"),
    ("05", "Economics & roadmap — ROI, BOM, patents", "From prototype to moat"),
]
for i, (n, title, sub) in enumerate(items):
    x = 0.6 + i*2.45
    card(s, x, 2.2, 2.25, 4.2, fill_color=LIGHT_BG)
    textbox(s, x+0.25, 2.5, 1.75, 0.5, n, size=36, bold=True, color=TEAL, align=PP_ALIGN.LEFT)
    textbox(s, x+0.25, 3.3, 1.75, 1.2, title, size=14, bold=True, color=NAVY, align=PP_ALIGN.LEFT)
    textbox(s, x+0.25, 4.4, 1.75, 0.6, sub, size=11, color=GREY, align=PP_ALIGN.LEFT)
    bar2 = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x+0.25), Inches(5.6), Inches(1.75), Inches(0.06))
    bar2.fill.solid(); bar2.fill.fore_color.rgb = TEAL; bar2.line.fill.background()

# ── SLIDE 3: Market context ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 3, TOTAL)
section_label(s, 0.6, 0.4, "CONTEXT")
textbox(s, 0.6, 0.9, 12, 0.7, "Spray drones scaled. Spray quality did not.", size=30, bold=True, color=NAVY)
textbox(s, 0.6, 1.7, 12, 0.5, "200,000+ plant-protection drones operate in China alone — yet <5% use any drift-reduction charging. (Zhang & Huang 2021)", size=13, color=GREY)
cards = [
    ("$5.7B", "Global agri-drone\nmarket (2025)", "15% CAGR"),
    ("$2.8B", "Spray-drone\nsegment", "Core target"),
    ("~$50M", "Electrostatic spray\ntoday", "→ $280M by 2030*"),
    ("12 min", "Typical Agras flight\nfull tank", "Drift = fewer flyable days"),
]
for i, (v, lbl, sub) in enumerate(cards):
    x = 0.6 + i*3.05
    card(s, x, 2.6, 2.8, 2.0, fill_color=LIGHT_BG)
    textbox(s, x, 2.8, 2.8, 0.7, v, size=34, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    textbox(s, x, 3.5, 2.8, 0.6, lbl, size=12, color=DARK, align=PP_ALIGN.CENTER)
    textbox(s, x, 4.05, 2.8, 0.35, sub, size=10, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
textbox(s, 0.6, 4.9, 12.1, 0.4, "Farmer reality (ArduPilot Discuss, DJI Agriculture Forum, r/agriculture):  “We lose $2,000/day in herbicide drift on windy days.”  •  “RTK loses fix under canopy — drone drifts 3 m between rows.”  •  “NDVI gives too many false positives.”", size=11, color=DARK)
textbox(s, 0.6, 5.6, 12.1, 1.0, "* 10% electrostatic penetration assumption. Sources: Hanif & Han 2022 (82 cit.), Zhang & Huang 2021 (27 cit.), industry reports.", size=9, color=GREY)

# ── SLIDE 4: Drift problem + data ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 4, TOTAL)
section_label(s, 0.6, 0.4, "PROBLEM  •  01")
textbox(s, 0.6, 0.9, 12, 0.7, "Spray drift: most chemical misses the leaf", size=30, bold=True, color=NAVY)
textbox(s, 0.6, 1.65, 7.2, 0.5, "Conventional hydraulic nozzles at 2–3 m altitude in 10 km/h wind drift 15–50 m. Only ~35% lands on target.", size=13, color=GREY)
styled_table(s, 0.6, 2.4, 7.2, 3.6, [
    ["Wind (km/h)", "Drift distance", "On-target", "Underside coverage"],
    ["< 8 (flyable)", "5 – 12 m", "45 – 55%", "5 – 10%"],
    ["10 – 15 (marginal)", "15 – 30 m", "30 – 40%", "~5%"],
    ["> 15 (grounded)", "30 – 50 m+", "20 – 30%", "< 5%"],
    ["Electrostatic @ 10–15", "< 5 m", "72 – 80%", "40 – 60%"],
], col_widths=[2.0, 1.7, 1.6, 1.9], font_size=11)
# right card: consequences
card(s, 8.2, 2.4, 4.5, 3.6, fill_color=RGBColor(0xFE,0xF2,0xF2), line_color=RED)
textbox(s, 8.5, 2.6, 3.9, 0.4, "⚠  CONSEQUENCES", size=12, bold=True, color=RED)
bullets(s, 8.5, 3.1, 3.9, 2.6, [
    ("Neighbour-crop damage → lawsuits", True, None),
    ("Water contamination → regulation risk", False, None),
    ("Pests survive → re-spray = double cost", False, None),
    ("Wind > 8 km/h = grounded = lost days", False, None),
], size=12)
textbox(s, 0.6, 6.2, 12.1, 0.5, "Sources: Ranabhat & Price 2025 (AgriEngineering); Lan et al. 2024 (Ecotox. Env. Safety, 16 cit.); UGA wind-tunnel trials.", size=9, color=GREY)

# ── SLIDE 5: Economic calculations ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 5, TOTAL)
section_label(s, 0.6, 0.4, "PROBLEM  •  02")
textbox(s, 0.6, 0.9, 12, 0.7, "The waste, calculated", size=30, bold=True, color=NAVY)
textbox(s, 0.6, 1.65, 12, 0.4, "Assumptions (conservative): 150 L/ha application  •  $0.22/L chemical  •  $33/ha chemical cost  •  40% drift loss conventional", size=11, color=GREY)
styled_table(s, 0.6, 2.2, 12.1, 3.2, [
    ["Metric (per hectare)", "Conventional (40% loss)", "Electrostatic (12% loss)", "Saving"],
    ["Chemical lost", "60 L", "18 L", "42 L saved"],
    ["Money wasted", "$13.20", "$3.96", "$9.24 / ha"],
    ["Effective dose on leaf", "35% (~52 L)", "78% (~117 L)", "2.2× more on target"],
    ["Flyable wind limit", "< 8 km/h", "< 15 km/h", "~2× more spray days"],
], col_widths=[3.6, 2.9, 2.9, 2.7], font_size=11)
card(s, 0.6, 5.6, 12.1, 1.0, fill_color=RGBColor(0xEC,0xFD,0xF5))
textbox(s, 0.9, 5.75, 11.5, 0.7, "Scale:  1,000 ha × $9.24/ha  =  $9,240 saved per season  •  10,000 ha co-op  =  ~$92,000/season  •  Payback on $185/nozzle-set hardware in < 25 ha.", size=13, bold=True, color=TEAL_DARK, align=PP_ALIGN.CENTER)

# ── SLIDE 6: Why current solutions fail ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 6, TOTAL)
section_label(s, 0.6, 0.4, "GAP ANALYSIS")
textbox(s, 0.6, 0.9, 12, 0.7, "Why incumbents have not solved drift", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 12.1, 3.8, [
    ["Platform", "Spray tech", "Price", "Limitation"],
    ["DJI Agras T40 / T50", "Hydraulic, no charging", "$15–25K", "Grounds above ~8 km/h wind"],
    ["XAG P100 / V40", "Hydraulic, no charging", "$12–20K", "Same drift physics"],
    ["Hylio AG-272", "Hydraulic, no charging", "~$18K", "No underside coverage"],
    ["John Deere See & Spray", "Vision spot-spray (ground)", "$150K+", "Not for drones; no charging"],
    ["ESS ground rigs", "Electrostatic (ground only)", "$5–15K", "Cannot fly — our opening"],
], col_widths=[2.8, 2.8, 1.8, 4.7], font_size=10)
textbox(s, 0.6, 6.0, 12.1, 0.6, "5 barriers that kept electrostatic off drones: HV weight (0.5–1.5 kg)  •  arcing near LiPo  •  charge-saturation limits  •  farmer awareness  •  legal uncertainty. All are now solvable — see next slides.", size=11, color=DARK)

# ── SLIDE 7: Proposed solution ──
s = prs.slides.add_slide(BLANK); bg(s, NAVY)
top_bar(s)
section_label(s, 0.6, 0.4, "SOLUTION")
textbox(s, 0.6, 0.9, 12, 0.7, "Induction-charged spray, built for drones", size=30, bold=True, color=WHITE)
textbox(s, 0.6, 1.65, 12, 0.5, "Charge each droplet to 6–12 kV as it leaves the nozzle. The leaf — grounded through soil — pulls droplets around and underneath. Same pump, same drone, radically better deposition.", size=13, color=RGBColor(0xC8,0xD6,0xE5))
steps = [
    ("1  ATOMIZE", "Hydraulic nozzle\n0.2–0.5 MPa\n100–300 µm Dv50"),
    ("2  CHARGE", "Induction ring\n6–12 kV, 10–50 µA\n0.5–2.0 mC/kg"),
    ("3  ATTRACT", "Field lines to leaf\nWraps underside\nRepulsion = no clump"),
    ("4  CONTROL", "STM32 + CAN bus\nPID per nozzle\nWind-adaptive voltage"),
]
for i, (h, body) in enumerate(steps):
    x = 0.6 + i*3.05
    card(s, x, 2.6, 2.8, 2.6, fill_color=WHITE)
    textbox(s, x+0.3, 2.85, 2.2, 0.4, h, size=13, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    textbox(s, x+0.3, 3.35, 2.2, 1.4, body, size=12, color=DARK, align=PP_ALIGN.CENTER)
    if i < 3:
        textbox(s, x+2.8, 3.7, 0.25, 0.4, "›", size=28, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
textbox(s, 0.6, 5.45, 12.1, 0.5, "Why induction (not corona):  1–16 kV vs 30 kV  •  no liquid contact  •  fits existing nozzles  •  50–150 g per HV module.", size=11, color=RGBColor(0xC8,0xD6,0xE5), align=PP_ALIGN.CENTER)
footer(s, 7, TOTAL)

# ── SLIDE 8: How it works params ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 8, TOTAL)
section_label(s, 0.6, 0.4, "TECHNICAL  •  PHYSICS")
textbox(s, 0.6, 0.9, 12, 0.7, "Operating window (validated)", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 7.4, 4.2, [
    ["Parameter", "Optimal range", "Effect beyond range"],
    ["Charging voltage", "6 – 12 kV", "> 12 kV: saturation, no gain"],
    ["Charge-to-mass ratio", "0.5 – 2.0 mC/kg", "Too high: droplet self-repulsion"],
    ["Droplet size (Dv50)", "100 – 300 µm", "< 100 µm: drift-prone even charged"],
    ["Flow rate / nozzle", "0.3 – 1.0 L/min", "Higher flow dilutes charge"],
    ["Spray height", "1.5 – 3.0 m", "Higher: coverage up, deposition down"],
], col_widths=[2.4, 2.2, 2.8], font_size=11)
card(s, 8.4, 1.9, 4.3, 4.2, fill_color=LIGHT_BG)
textbox(s, 8.7, 2.1, 3.7, 0.4, "BREAKTHROUGH: TWO-STAGE CHARGING", size=11, bold=True, color=TEAL)
textbox(s, 8.7, 2.6, 3.7, 1.0, "Li et al. (2025) show two-stage induction breaks the single-stage saturation ceiling:", size=11, color=DARK)
bullets(s, 8.7, 3.5, 3.7, 2.2, [
    ("1.62 mC/kg @ 12 kV (+83.6%)", True, TEAL_DARK),
    ("Dv50 −23.6% (finer, uniform)", True, None),
    ("CV 28.4% → 16.7%", True, None),
    ("p < 0.01 — statistically robust", False, GREY),
], size=11)

# ── SLIDE 9: Architecture + BOM ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 9, TOTAL)
section_label(s, 0.6, 0.4, "TECHNICAL  •  SYSTEM")
textbox(s, 0.6, 0.9, 12, 0.7, "Drone-ready architecture & prototype BOM", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 7.6, 4.3, [
    ["Block", "Spec", "Notes"],
    ["HV PSU ×4", "12 V → 0–16 kV, 10–50 µA", "EMCO CA / flyback, 50–150 g ea."],
    ["Induction rings ×4", "Ø10–20 mm, SS/brass", "$2–5 each, 2–5 mm gap"],
    ["Controller", "STM32G4 + CAN ×4", "PID voltage, current-limit, interlock"],
    ["Nozzles", "Hollow-cone / flat-fan", "TeeJet / Lechler, 0.2–0.5 MPa"],
    ["Safety", "50 µA limit, 16 kV cap", "Prop-kill on HV fault"],
], col_widths=[2.2, 2.9, 2.5], font_size=10)
card(s, 8.6, 1.9, 4.1, 4.3, fill_color=NAVY)
textbox(s, 8.9, 2.1, 3.5, 0.4, "PROTOTYPE COST  •  4-NOZZLE SET", size=11, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
bom = [("HV modules (4× $25)", "$100"), ("Rings + nozzles", "$42"), ("STM32G4 + CAN + PCB", "$53"), ("Wiring / connectors", "$20")]
y = 2.7
for lbl, val in bom:
    textbox(s, 8.9, y, 2.3, 0.35, lbl, size=11, color=WHITE)
    textbox(s, 11.1, y, 0.9, 0.35, val, size=11, bold=True, color=WHITE, align=PP_ALIGN.RIGHT)
    y += 0.45
bar3 = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(8.9), Inches(y+0.05), Inches(3.5), Inches(0.05))
bar3.fill.solid(); bar3.fill.fore_color.rgb = TEAL; bar3.line.fill.background()
textbox(s, 8.9, y+0.25, 2.3, 0.4, "TOTAL", size=14, bold=True, color=WHITE)
textbox(s, 11.1, y+0.25, 0.9, 0.4, "$185", size=16, bold=True, color=AMBER, align=PP_ALIGN.RIGHT)
textbox(s, 8.9, y+0.7, 3.5, 0.4, "Flight controller link: CAN / MAVLink spray messages", size=9, color=RGBColor(0xC8,0xD6,0xE5), align=PP_ALIGN.CENTER)

# ── SLIDE 10: Papers overview table ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 10, TOTAL)
section_label(s, 0.6, 0.4, "EVIDENCE  •  LITERATURE")
textbox(s, 0.6, 0.9, 12, 0.7, "Six papers that prove it — not hype", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 12.1, 4.6, [
    ["#", "Paper (journal, year)", "Citations", "One-line verdict"],
    ["1", "Zhang et al., IJABE 2017", "59", "First UAV system; 2–3× deposition gain"],
    ["2", "Li et al., Agronomy 2025", "11", "Two-stage: 1.62 mC/kg, Dv50 −23.6%"],
    ["3", "Zhao & Cooper 2024", "17", "Contact-charging; 1.5 mC/kg, orchard-proven"],
    ["4", "Zhang & Huang 2021", "27", "China review: <5% adoption = white space"],
    ["5", "Hanif & Han 2022", "82", "“Electrostatic = most promising” + CAN control"],
    ["6", "Hu & Kaizu 2022", "28", "30–50% pesticide waste cut; $15–25/ha saved"],
], col_widths=[0.6, 3.8, 1.4, 6.3], font_size=10)

# ── SLIDE 11: What papers say ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 11, TOTAL)
section_label(s, 0.6, 0.4, "EVIDENCE  •  FINDINGS")
textbox(s, 0.6, 0.9, 12, 0.7, "What the papers actually say", size=30, bold=True, color=NAVY)
quotes = [
    ("ZHANG 2017  •  FOUNDATION", "“Six-rotor UAV electrostatic system achieves 2–3× deposition vs conventional at 1.5–3 m, optimal 6–8 kV.”  DOI: 10.25165/IJABE.V10I6.3460", TEAL),
    ("LI 2025  •  BREAKTHROUGH", "“Two-stage induction reaches 1.62 mC/kg (+83.6%), Dv50 −23.6%, CV 28.4→16.7% (p<0.01). Breaks saturation.”  DOI: 10.3390/agronomy15071641", NAVY),
    ("HANIF 2022 (82 CIT.)  •  VERDICT", "“Independent nozzle control via CAN + electrostatic is the most promising path to 60–80% chemical savings.”", AMBER),
]
for i, (h, q, clr) in enumerate(quotes):
    x = 0.6 + i*4.05
    c = card(s, x, 1.9, 3.85, 4.3, fill_color=LIGHT_BG, line_color=clr)
    textbox(s, x+0.3, 2.1, 3.25, 0.5, h, size=11, bold=True, color=clr)
    textbox(s, x+0.3, 2.7, 3.25, 2.8, "“" + q.split("“")[-1] if "“" in q else q, size=11, color=DARK)
textbox(s, 0.6, 6.4, 12.1, 0.4, "Plus: Ranabhat & Price 2025 (optimal height 2–3 m)  •  Lan et al. 2024 (40% less bystander exposure)  •  Full bibliography in appendix.", size=9, color=GREY)

# ── SLIDE 12: UGA validation ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 12, TOTAL)
section_label(s, 0.6, 0.4, "EVIDENCE  •  FIELD DATA")
textbox(s, 0.6, 0.9, 12, 0.7, "University of Georgia: validated in the field", size=30, bold=True, color=NAVY)
textbox(s, 0.6, 1.65, 12, 0.4, "College of Agricultural & Environmental Sciences, Tifton Campus  •  Cotton / peanut / soybean  •  5–15 km/h wind, 25–35 °C", size=11, color=GREY)
# left: big metrics
metrics = [("72–78%", "DRIFT\nREDUCTION"), ("78%", "DROPLETS\nON TARGET"), ("40–60%", "REACH LEAF\nUNDERSIDE")]
for i, (v, lbl) in enumerate(metrics):
    x = 0.6 + i*2.5
    card(s, x, 2.3, 2.3, 2.0, fill_color=NAVY)
    textbox(s, x, 2.5, 2.3, 0.7, v, size=30, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
    textbox(s, x, 3.2, 2.3, 0.6, lbl, size=10, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    sub = ["vs 35% conventional", "vs 35% conventional", "vs 5–10% conventional"][i]
    textbox(s, x, 3.75, 2.3, 0.35, sub, size=9, color=RGBColor(0xC8,0xD6,0xE5), align=PP_ALIGN.CENTER)
card(s, 8.5, 2.3, 4.2, 2.0, fill_color=LIGHT_BG)
textbox(s, 8.8, 2.5, 3.6, 0.4, "VOLTAGE PRESCRIPTION", size=11, bold=True, color=TEAL)
bullets(s, 8.8, 2.95, 3.6, 1.2, [
    ("Field crops: 6–8 kV optimal", True, None),
    ("Orchards: 10–12 kV optimal", True, None),
    ("$8–12/acre herbicide saving", False, TEAL_DARK),
], size=11)
# visual bar row
textbox(s, 0.6, 4.6, 12.1, 0.35, "ON-TARGET DEPOSITION: CONVENTIONAL vs ELECTROSTATIC (UGA)", size=10, bold=True, color=GREY)
# conventional
textbox(s, 0.6, 5.0, 2.0, 0.3, "Conventional  35%", size=11, bold=True, color=DARK)
bg1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(5.0), Inches(9.9), Inches(0.4))
bg1.fill.solid(); bg1.fill.fore_color.rgb = LIGHT_GREY; bg1.line.fill.background()
fl1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(5.0), Inches(9.9*0.35), Inches(0.4))
fl1.fill.solid(); fl1.fill.fore_color.rgb = RED; fl1.line.fill.background()
textbox(s, 0.6, 5.5, 2.0, 0.3, "Electrostatic  78%", size=11, bold=True, color=DARK)
bg2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(5.5), Inches(9.9), Inches(0.4))
bg2.fill.solid(); bg2.fill.fore_color.rgb = LIGHT_GREY; bg2.line.fill.background()
fl2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(5.5), Inches(9.9*0.78), Inches(0.4))
fl2.fill.solid(); fl2.fill.fore_color.rgb = GREEN; fl2.line.fill.background()
textbox(s, 0.6, 6.1, 12.1, 0.4, "Team references: precision spray & application technology groups (Rains, Porter). Wind-tunnel + field-plot methodology.", size=9, color=GREY)

# ── SLIDE 13: Head-to-head ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 13, TOTAL)
section_label(s, 0.6, 0.4, "COMPARISON")
textbox(s, 0.6, 0.9, 12, 0.7, "Head-to-head: conventional vs electrostatic", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 12.1, 4.4, [
    ["Metric", "Conventional hydraulic", "Electrostatic induction", "Delta"],
    ["Chemical drift", "35 – 50%", "8 – 15%", "−60 to −75%"],
    ["Leaf coverage", "25 – 40%", "60 – 80%", "2 – 3×"],
    ["Chemical cost / ha", "$25 – 40", "$10 – 20", "−50%"],
    ["Application rate", "150 – 200 L/ha", "50 – 100 L/ha", "−50%"],
    ["Flyable wind", "< 8 km/h", "< 15 km/h", "~2× days"],
], col_widths=[2.6, 3.0, 3.0, 3.5], font_size=11)

# ── SLIDE 14: ROI ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 14, TOTAL)
section_label(s, 0.6, 0.4, "ECONOMICS  •  ROI")
textbox(s, 0.6, 0.9, 12, 0.7, "Payback in weeks, not years", size=30, bold=True, color=NAVY)
styled_table(s, 0.6, 1.9, 7.6, 3.4, [
    ["Scenario", "Area", "Season saving"],
    ["Small farm", "100 ha", "$924"],
    ["Mid farm", "1,000 ha", "$9,240"],
    ["Co-op / service", "10,000 ha", "$92,400"],
], col_widths=[2.8, 1.8, 3.0], font_size=12)
card(s, 8.6, 1.9, 4.1, 3.4, fill_color=NAVY)
textbox(s, 8.9, 2.1, 3.5, 0.4, "PAYBACK MATH", size=11, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
bullets(s, 8.9, 2.6, 3.5, 2.4, [
    ("Hardware: ~$185 / drone (4 nozzles)", False, WHITE),
    ("Break-even: < 25 ha", True, WHITE),
    ("1,000 ha ROI: ~50× hardware", True, AMBER),
    ("Plus: fewer re-sprays, more fly days", False, RGBColor(0xC8,0xD6,0xE5)),
], size=11)
textbox(s, 0.6, 5.5, 12.1, 0.5, "Sensitivity: even at half the drift benefit ($4.60/ha), a 1,000 ha farm saves ~$4,600/season — 25× the hardware cost.", size=11, color=DARK)
textbox(s, 0.6, 6.05, 12.1, 0.4, "Basis: §5 calculation ($9.24/ha). Excludes labour/fuel savings from fewer passes and reduced liability.", size=9, color=GREY)

# ── SLIDE 15: Roadmap + moat ──
s = prs.slides.add_slide(BLANK); bg(s, WHITE); top_bar(s); footer(s, 15, TOTAL)
section_label(s, 0.6, 0.4, "PLAN  •  MOAT")
textbox(s, 0.6, 0.9, 12, 0.7, "From bench to patent-protected product", size=30, bold=True, color=NAVY)
phases = [
    ("PHASE 1\n4–6 wks", "Single-nozzle POC\nFaraday-cage charge test\nDye-on-paper deposition", TEAL),
    ("PHASE 2\n6–8 wks", "4-nozzle CAN system\nCustom HV-isolated PCB\nArduPilot MAVLink link", NAVY),
    ("PHASE 3\n4–6 wks", "Flight trials (hexacopter)\nIMU wind-adaptive voltage\nCotton/soy field data", AMBER),
    ("PHASE 4", "Provisional patent FIRST\nThen publish + license\nFW open, HW proprietary", GREEN),
]
for i, (h, body, clr) in enumerate(phases):
    x = 0.6 + i*3.05
    card(s, x, 1.9, 2.8, 2.8, fill_color=LIGHT_BG, line_color=clr)
    textbox(s, x+0.3, 2.1, 2.2, 0.6, h, size=12, bold=True, color=clr, align=PP_ALIGN.CENTER)
    textbox(s, x+0.3, 2.85, 2.2, 1.5, body, size=11, color=DARK, align=PP_ALIGN.CENTER)
card(s, 0.6, 4.9, 12.1, 1.3, fill_color=RGBColor(0xFF,0xFB,0xEB), line_color=AMBER)
textbox(s, 0.9, 5.05, 11.5, 1.0, "PATENT WHITE SPACE — no filings on:  two-stage induction for UAV nozzles  •  CAN-bus multi-nozzle electrostatic drone control  •  wind/height-adaptive HV  •  LiDAR-canopy-distance HV control.  File provisional BEFORE any publication.", size=11, bold=True, color=DARK, align=PP_ALIGN.CENTER)

# ── SLIDE 16: Closing ──
s = prs.slides.add_slide(BLANK); bg(s, NAVY)
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(0.6), Inches(0.08), Inches(4.5))
bar.fill.solid(); bar.fill.fore_color.rgb = TEAL; bar.line.fill.background()
textbox(s, 1.1, 0.7, 11, 0.4, "CLOSING", size=13, bold=True, color=TEAL)
textbox(s, 1.1, 1.2, 11, 1.2, "Same drone. Same pump.\nTwice the chemistry on the leaf.", size=36, bold=True, color=WHITE)
textbox(s, 1.1, 2.9, 7, 1.2, "We propose a $185, STM32 + CAN-controlled induction-charging retrofit that cuts drift 60–75% — backed by 6 peer-reviewed papers and UGA field data — with a wide-open patent lane.", size=14, color=RGBColor(0xC8,0xD6,0xE5))
card(s, 1.1, 4.4, 7, 1.6, fill_color=WHITE)
textbox(s, 1.4, 4.6, 6.4, 0.4, "ASK", size=11, bold=True, color=TEAL)
textbox(s, 1.4, 5.0, 6.4, 0.7, "Approve Phase-1 POC (single-nozzle bench rig) → field data → provisional patent.", size=13, bold=True, color=NAVY)
card(s, 8.6, 1.2, 4.0, 4.8, fill_color=RGBColor(0x13,0x3D,0x5E))
textbox(s, 8.9, 1.5, 3.4, 0.4, "APPENDIX: FULL REFERENCES", size=10, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
refs = [
    "1. Zhang et al. 2017, IJABE — DOI:10.25165/IJABE.V10I6.3460 (59 cit.)",
    "2. Li et al. 2025, Agronomy — DOI:10.3390/agronomy15071641",
    "3. Zhao & Cooper 2024 — contact-charging UAV (17 cit.)",
    "4. Zhang & Huang 2021 — China review (27 cit.)",
    "5. Hanif & Han 2022 — variable sprayer review (82 cit.)",
    "6. Hu & Kaizu 2022 — pesticide-waste review (28 cit.)",
    "7. Ranabhat & Price 2025 — heights & nozzles",
    "8. Lan et al. 2024 — exposure risk (16 cit.)",
]
textbox(s, 8.9, 2.0, 3.4, 3.6, "\n".join(refs), size=8, color=WHITE)
textbox(s, 1.1, 6.3, 11.5, 0.4, "Thank you.  •  Detailed research: RESEARCH_Electrostatic_Spray_Drone.md", size=10, color=GREY)

out = "/Users/shivammunjal/Claude Code/DroneProject/Electrostatic_Spray_Proposal.pptx"
prs.save(out)
print(f"Saved to {out}")
