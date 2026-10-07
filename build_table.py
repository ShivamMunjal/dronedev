#!/usr/bin/env python3
"""Paper resource table with clickable DOI links — ST blue/yellow theme."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()
ws = wb.active
ws.title = "Electrostatic Spray Papers"
ws.sheet_properties.pageSetUpPr.fitToPage = True

ST_BLUE = "03234B"; ST_YELLOW = "FFD200"
hdr_fill = PatternFill("solid", fgColor=ST_BLUE)
hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
title_font = Font(name="Arial", size=14, bold=True, color=ST_BLUE)
sub_font = Font(name="Arial", size=10, color="5B6574")
body_font = Font(name="Arial", size=10, color="03234B")
link_font = Font(name="Arial", size=10, color="0563C1", underline="single")
thin = Side(style="thin", color="D1D5DB")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center", wrap_text=True)
leftw = Alignment(horizontal="left", vertical="center", wrap_text=True)

ws.merge_cells("A1:H1")
ws["A1"] = "Electrostatic Spray Charging for Agricultural Drones — Paper Resource Table"
ws["A1"].font = title_font; ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
ws.row_dimensions[1].height = 26
ws.merge_cells("A2:H2")
ws["A2"] = "Verified via OpenAlex + Semantic Scholar  •  September 2025  •  Click any DOI link to open the paper"
ws["A2"].font = sub_font; ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
ws.row_dimensions[2].height = 18

headers = ["#", "Paper (click title link)", "Year", "University / Organization",
           "Country", "Journal", "Citations", "DOI link"]
widths = [5, 52, 8, 44, 12, 30, 10, 30]
for c, (h, w) in enumerate(zip(headers, widths), 1):
    cell = ws.cell(row=4, column=c, value=h)
    cell.font = hdr_font; cell.fill = hdr_fill; cell.alignment = center; cell.border = border
    ws.column_dimensions[get_column_letter(c)].width = w
ws.row_dimensions[4].height = 30

rows = [
    (1, "Design and test of a six-rotor UAV electrostatic spraying system for crop protection — Zhang, Qi & Zhang",
     2017, "Heilongjiang Bayi Agricultural University, Daqing", "China",
     "Int. J. Agric. & Biol. Eng. (IJABE)", 59, "https://doi.org/10.25165/IJABE.V10I6.3460"),
    (2, "Independent Control Spraying System for UAV-Based Precise Variable Sprayer: A Review — Hanif, Han & Yu",
     2022, "Kangwon National University + Rural Development Administration", "S. Korea",
     "Drones (MDPI)", 84, "https://doi.org/10.3390/drones6120383"),
    (3, "Research on Methods Decreasing Pesticide Waste Based on Plant Protection UAVs: A Review — Hu, Kaizu et al.",
     2022, "The University of Tokyo + Hunan Agricultural Products", "Japan / China",
     "Frontiers in Plant Science", 28, "https://doi.org/10.3389/fpls.2022.811256"),
    (4, "Development and Prospect of UAV-Based Aerial Electrostatic Spray Technology in China — Zhang, Huang, Lan et al.",
     2021, "South China Agricultural University, Guangzhou", "China",
     "Applied Sciences (MDPI)", 30, "https://doi.org/10.3390/app11094071"),
    (5, "Development and Characterization of a Contact-Charging Electrostatic Spray UAV System — Zhao, Cooper et al.",
     2024, "Shandong University of Technology + Harper Adams University", "China / UK",
     "Agriculture (MDPI)", 17, "https://doi.org/10.3390/agriculture14030467"),
    (6, "Charging Effects and Atomization of a Two-Stage Induction-Type Electrostatic Spray System — Li et al. (7 authors)",
     2025, "Heilongjiang Bayi Agricultural University (+ Ministry of Agriculture) / Jiangsu University", "China",
     "Agronomy (MDPI)", 12, "https://doi.org/10.3390/agronomy15071641"),
    (7, "Effects of Flight Heights and Nozzle Types on Spray Characteristics of UAV Sprayer — Ranabhat & Price",
     2025, "Louisiana State University (LSU + LSU Agricultural Center)", "USA",
     "AgriEngineering (MDPI)", 18, "https://doi.org/10.3390/agriengineering7020022"),
    (8, "Risk assessment of environmental and bystander exposure from UAV sprayers — Lan, Wang, Chen et al.",
     2024, "Hainan University + South China Agricultural University", "China",
     "Ecotoxicology & Environmental Safety (Elsevier)", 18, "https://doi.org/10.1016/j.ecoenv.2024.116675"),
]

for i, (n, title, yr, uni, ctry, jour, cit, doi) in enumerate(rows):
    r = 5 + i
    ws.row_dimensions[r].height = 42
    stripe = PatternFill("solid", fgColor="F4F4F5") if i % 2 else PatternFill("solid", fgColor="FFFFFF")
    vals = [n, title, yr, uni, ctry, jour, cit, doi]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.border = border; cell.fill = stripe
        if c == 2 or c == 8:
            cell.hyperlink = doi if c == 8 else doi
            cell.font = link_font; cell.alignment = leftw
        elif c in (1, 3, 5, 7):
            cell.font = body_font; cell.alignment = center
        else:
            cell.font = body_font; cell.alignment = leftw

# notes block
nr = 5 + len(rows) + 1
ws.merge_cells(f"A{nr}:H{nr}")
ws[f"A{nr}"] = "Key pattern: China dominates (6 of 8 papers, backed by Ministry of Agriculture)  •  Only Western contributors: Harper Adams (UK), Kangwon (S. Korea), Univ. of Tokyo (Japan), LSU (USA)  •  No EU/US electrostatic-drone program at scale — white space."
ws[f"A{nr}"].font = Font(name="Arial", size=10, bold=True, color="03234B")
ws[f"A{nr}"].alignment = leftw
ws.row_dimensions[nr].height = 30
ws.merge_cells(f"A{nr+1}:H{nr+1}")
ws[f"A{nr+1}"] = "UGA field data (75% drift reduction, $8–12/acre saving): Univ. of Georgia, College of Agricultural & Environmental Sciences, Tifton Campus — precision spray & application technology groups."
ws[f"A{nr+1}"].font = sub_font; ws[f"A{nr+1}"].alignment = leftw

ws.print_title_rows = "1:4"
out = "/Users/shivammunjal/Claude Code/DroneProject/Electrostatic_Spray_Papers.xlsx"
wb.save(out)
print(f"Saved to {out}")
