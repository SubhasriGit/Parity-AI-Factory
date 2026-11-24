"""Generate a standalone PM000003 production-metrics PowerPoint."""

# pyright: reportRedeclaration=false, reportUnusedImport=false
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "reports" / "production_metrics.json"
OUTPUT = ROOT / "reports" / "CPP_PM000003_Production_Metrics.pptx"

NAVY = RGBColor(20, 35, 52)
INK = RGBColor(28, 39, 46)
TEAL = RGBColor(0, 130, 128)
CORAL = RGBColor(229, 100, 74)
GOLD = RGBColor(224, 173, 55)
SKY = RGBColor(75, 141, 186)
WHITE = RGBColor(255, 255, 255)
OFFWHITE = RGBColor(247, 248, 246)
MID = RGBColor(111, 126, 134)
LINE = RGBColor(211, 220, 220)
GREEN = RGBColor(45, 132, 89)


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, rounded=False):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE, Inches(
        x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    return shape


def text(slide, value, x, y, w, h, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.03)
    frame.margin_right = Inches(0.03)
    paragraph = frame.paragraphs[0]
    paragraph.text = str(value)
    paragraph.alignment = align
    run = paragraph.runs[0]
    run.font.name = "Aptos"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def slide_title(slide, eyebrow, title, subtitle):
    text(slide, eyebrow.upper(), 0.72, 0.38, 4.5, 0.25, 10, TEAL, True)
    text(slide, title, 0.72, 0.72, 11.8, 0.54, 26, NAVY, True)
    text(slide, subtitle, 0.72, 1.30, 11.8, 0.42, 13, MID)


def footer(slide, number):
    text(slide, "PM000003 • PRODUCTION METRICS",
         0.72, 7.12, 4.5, 0.18, 8, MID, True)
    text(slide, f"{number:02d}", 12.12, 7.08,
         0.45, 0.2, 9, MID, True, PP_ALIGN.RIGHT)


def metric(slide, x, y, w, value, label, accent=TEAL, note=""):
    rect(slide, x, y, w, 1.18, WHITE, LINE, True)
    text(slide, value, x+0.18, y+0.12, w-0.36, 0.45, 24, accent, True)
    text(slide, label, x+0.18, y+0.65, w-0.36, 0.22, 10, INK, True)
    if note:
        text(slide, note, x+0.18, y+0.91, w-0.36, 0.18, 8, MID)


def bullet(slide, items, x, y, w, h, size=13):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    for index, item in enumerate(items):
        p = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        p.text = "•  " + item
        p.space_after = Pt(8)
        p.font.name = "Aptos"
        p.font.size = Pt(size)
        p.font.color.rgb = INK
    return box


def new_slide(presentation, background=OFFWHITE):
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = background
    return slide


def bar(slide, label, value, max_value, y, color):
    text(slide, label, 0.85, y, 2.45, 0.22, 11, NAVY, True)
    rect(slide, 3.4, y+0.03, 5.9, 0.22, RGBColor(232,
         238, 238), RGBColor(232, 238, 238), True)
    rect(slide, 3.4, y+0.03, max(0.07, 5.9 *
         value / max_value), 0.22, color, color, True)
    text(slide, f"{value:,}", 9.58, y, 0.8,
         0.22, 11, INK, True, PP_ALIGN.RIGHT)


data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# 1 cover
slide = new_slide(prs, NAVY)
rect(slide, 0, 0, 0.18, 7.5, TEAL, TEAL)
text(slide, "PM000003", 0.82, 0.65, 3.5,
     0.28, 11, RGBColor(123, 229, 211), True)
text(slide, "Production metrics", 0.82, 1.25, 8.4, 0.62, 34, WHITE, True)
text(slide, "Measured scale, quality, AI controls and telemetry readiness",
     0.84, 2.02, 8.2, 0.55, 17, RGBColor(209, 221, 225))
rect(slide, 9.25, 1.25, 3.0, 4.2, RGBColor(
    27, 48, 65), RGBColor(62, 86, 103), True)
metric(slide, 9.55, 1.80, 2.4, "250", "synthetic parsed rows", TEAL)
metric(slide, 9.55, 3.15, 2.4, "100%", "reconciliation", GOLD)
metric(slide, 9.55, 4.50, 2.4, "31", "tests passed", CORAL)
text(slide, "Run period • 16–20 Nov 2026", 0.84,
     6.75, 4.5, 0.25, 10, RGBColor(160, 180, 188))

# 2 executive scorecard
slide = new_slide(prs)
slide_title(slide, "01 • Executive scorecard", "Current run: production-scale and reconciled",
            "Observed metrics extracted from the populated database and validated workbook.")
metric(slide, 0.75, 2.0, 2.25, "5", "analysis days", TEAL)
metric(slide, 3.2, 2.0, 2.25, "5", "synthetic stores", SKY)
metric(slide, 5.65, 2.0, 2.25, "200", "CPP evidence rows", CORAL)
metric(slide, 8.1, 2.0, 2.25, "250", "verdict rows", GOLD)
metric(slide, 10.55, 2.0, 2.0, "0", "malformed rows", GREEN)
rect(slide, 0.75, 3.65, 11.8, 2.35, WHITE, LINE, True)
text(slide, "Coverage", 1.03, 3.98, 1.1, 0.25, 13, NAVY, True)
text(slide, "50 synthetic log rows expanded into 250 normalized records across two directions.",
     2.18, 3.94, 9.55, 0.36, 13, INK)
text(slide, "Control", 1.03, 4.62, 1.1, 0.25, 13, NAVY, True)
text(slide, "Mismatch, verdict and workbook counts match exactly; 20 indexes and the canonical schema validate.",
     2.18, 4.58, 9.55, 0.36, 13, INK)
text(slide, "Recovery", 1.03, 5.26, 1.1, 0.25, 13, NAVY, True)
text(slide, "A private backup of the replaced original data remains outside the active project path.",
     2.18, 5.22, 9.55, 0.36, 13, INK)
footer(slide, 2)

# 3 operational volume
slide = new_slide(prs)
slide_title(slide, "02 • Operational volume", "The pipeline processed multiple representations of the same work",
            "Source rows → DTO rows → logical groups → paired field mismatches.")
values = [("Synthetic source rows", 50, SKY), ("Normalized records", 250,
                                               TEAL), ("Logical groups", 220, CORAL), ("Paired mismatches", 30, GOLD)]
maxv = max(v for _, v, _ in values)
for index, (label, value, color) in enumerate(values):
    bar(slide, label, value, maxv, 2.10 + index*0.92, color)
rect(slide, 0.85, 6.05, 11.25, 0.62, RGBColor(
    239, 246, 245), RGBColor(202, 228, 221), True)
text(slide, "Expansion is expected: one log message can contain many DTOs. Pairing converts raw directional rows into business-review groups.",
     1.08, 6.23, 10.8, 0.26, 11, TEAL, True, PP_ALIGN.CENTER)
footer(slide, 3)

# 4 classification
slide = new_slide(prs)
slide_title(slide, "03 • Classification outcome", "80.00% of rows classified as expected",
            "Missing evidence is tracked separately as a user-confirmation requirement.")
metric(slide, 0.82, 2.0, 2.65, "200", "EXPECTED", TEAL)
metric(slide, 3.73, 2.0, 2.65, "0", "IMS DATA ISSUE", GOLD)
metric(slide, 6.64, 2.0, 2.65, "50", "POTENTIAL ISSUE", CORAL)
metric(slide, 9.55, 2.0, 2.65, "150", "expected rows needing confirmation", SKY)
items = [("KD-2", 50, TEAL), ("KD-9", 50, RGBColor(50, 150, 125)), ("KD-6", 40,
                                                                    RGBColor(91, 168, 145)), ("No KD", 50, CORAL), ("KD-8", 25, GOLD), ("KD-10", 25, SKY)]
for index, (label, value, color) in enumerate(items):
    y = 3.70 + index*0.45
    text(slide, label, 1.0, y, 1.6, 0.2, 10, NAVY, True)
    rect(slide, 2.75, y+0.02, 7.0, 0.18,
         RGBColor(232, 238, 238), RGBColor(232, 238, 238), True)
    rect(slide, 2.75, y+0.02, 7.0*value/50, 0.18, color, color, True)
    text(slide, f"{value:,}", 10.15, y, 0.8,
         0.2, 10, INK, True, PP_ALIGN.RIGHT)
footer(slide, 4)

# 5 quality and controls
slide = new_slide(prs)
slide_title(slide, "04 • Quality controls", "Production quality is evidenced, not assumed",
            "The run carries deterministic reconciliation, validation and backup evidence.")
controls = [("Reconciliation", "100%", "250 rows at DB, verdict and workbook stages", GREEN), ("Malformed input", "0", "No rejected synthetic source row", GREEN), ("Test suite", "31", "Automated tests pass",
                                                                                                                                                                    TEAL), ("Schema", "9 / 20", "Tables / required indexes", SKY), ("Synthetic data", "100%", "Active inputs and DB use generated identifiers", GOLD), ("LLM ambiguity", "0", "No ambiguous or rejected findings", CORAL)]
for index, (label, value, note, color) in enumerate(controls):
    row, col = divmod(index, 3)
    x = 0.78+col*4.18
    y = 1.95+row*2.05
    rect(slide, x, y, 3.72, 1.56, WHITE, LINE, True)
    text(slide, label.upper(), x+0.2, y+0.2, 3.2, 0.2, 9, MID, True)
    text(slide, value, x+0.2, y+0.52, 3.2, 0.42, 23, color, True)
    text(slide, note, x+0.2, y+1.08, 3.2, 0.3, 10, INK)
footer(slide, 5)

# 6 AI metrics
slide = new_slide(prs)
slide_title(slide, "05 • AI usage metrics", "LLM workload was reduced without lowering control quality",
            "Expected KD rows are reviewed through user confirmation, not sent to LLM as potential issues.")
metric(slide, 0.85, 2.0, 2.55, "50", "candidate rows", SKY)
metric(slide, 3.66, 2.0, 2.55, "50", "insufficient evidence", TEAL)
metric(slide, 6.47, 2.0, 2.55, "80%", "queue reduction", GREEN)
metric(slide, 9.28, 2.0, 2.55, "0", "reclassified without evidence", GOLD)
rect(slide, 0.85, 3.75, 11.0, 2.12, WHITE, LINE, True)
text(slide, "AI control outcome", 1.15, 4.04, 2.8, 0.3, 15, NAVY, True)
bullet(slide, ["50/50 synthetic findings were INSUFFICIENT_EVIDENCE", "No ambiguous or rejected output",
       "Current queue = 50 uncoded potential issues", "Expected KD-2/KD-8/KD-9/KD-10 rows move to user confirmation"], 1.15, 4.50, 10.0, 1.12, 12)
footer(slide, 6)

# 7 telemetry gap
slide = new_slide(prs)
slide_title(slide, "06 • Telemetry gap", "Production ROI is not yet measured",
            "Volume and quality are observed. Runtime, cost and reviewer productivity still require telemetry.")
measured = ["Row and result counts", "Classification distribution", "Database and workbook reconciliation",
            "LLM candidate and no-writeback counts", "Missing-evidence workload"]
pending = ["Automation runtime and rows/second", "LLM tokens, cost and latency",
           "Reviewer hours and agreement rate", "Overturn/rework rate", "Hours saved and report SLA"]
rect(slide, 0.78, 1.95, 5.75, 4.55, RGBColor(
    239, 247, 245), RGBColor(203, 227, 218), True)
text(slide, "MEASURED NOW", 1.12, 2.28, 4.8, 0.3, 15, TEAL, True)
bullet(slide, measured, 1.12, 2.84, 4.75, 2.65, 12)
rect(slide, 6.82, 1.95, 5.72, 4.55, RGBColor(
    251, 246, 235), RGBColor(232, 215, 175), True)
text(slide, "TELEMETRY REQUIRED", 7.16, 2.28, 4.7, 0.3, 15, GOLD, True)
bullet(slide, pending, 7.16, 2.84, 4.75, 2.65, 12)
footer(slide, 7)

# 8 KPI definitions
slide = new_slide(prs)
slide_title(slide, "07 • Recommended production KPIs", "Track volume, speed, quality, AI efficiency and business impact",
            "Use these definitions for future dashboards and management reporting.")
kpis = [("Throughput", "processed rows ÷ automated runtime"), ("First-pass automation", "expected rows ÷ total rows"), ("Review yield", "rows confirmed without overturn ÷ reviewed rows"), ("LLM acceptance", "supported updates ÷ valid findings"),
        ("Reconciliation", "rows agreeing across DB / verdict / workbook"), ("Hours saved", "manual baseline − automation − review − rework"), ("Evidence closure", "confirmation-required rows closed per period"), ("SLA", "completed report time − input availability time")]
for i, (name, formula) in enumerate(kpis):
    row, col = divmod(i, 2)
    x = 0.8+col*6.08
    y = 1.95+row*1.15
    rect(slide, x, y, 5.72, 0.86, WHITE, LINE, True)
    text(slide, name, x+0.18, y+0.15, 1.35, 0.25, 11, NAVY, True)
    text(slide, formula, x+1.68, y+0.15, 3.75, 0.46, 10, MID)
footer(slide, 8)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUTPUT)
print(f"Created {OUTPUT} with {len(prs.slides)} slides")
