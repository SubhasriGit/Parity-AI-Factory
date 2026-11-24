# pyright: reportRedeclaration=false, reportUnusedImport=false, reportUnusedParameter=false
"""Generate the CPP Parity AI Factory demo presentation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "reports" / "CPP_Parity_AI_Factory_Demo.pptx"

NAVY = RGBColor(20, 35, 52)
INK = RGBColor(28, 39, 46)
TEAL = RGBColor(0, 130, 128)
MINT = RGBColor(215, 242, 236)
CORAL = RGBColor(229, 100, 74)
GOLD = RGBColor(224, 173, 55)
SKY = RGBColor(75, 141, 186)
WHITE = RGBColor(255, 255, 255)
OFFWHITE = RGBColor(247, 248, 246)
MID = RGBColor(111, 126, 134)
LINE = RGBColor(211, 220, 220)
RED = RGBColor(181, 59, 59)
GREEN = RGBColor(45, 132, 89)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)


def add_text(slide, text, x, y, w, h, size=18, color=INK, bold=False,
             font="Aptos", align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.margin_left = Inches(0.03)
    frame.margin_right = Inches(0.03)
    frame.margin_top = Inches(0.02)
    frame.margin_bottom = Inches(0.02)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.alignment = align
    run = paragraph.runs[0]
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def add_rich_text(slide, runs, x, y, w, h, size=18, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    for text, color, bold in runs:
        run = paragraph.add_run()
        run.text = text
        run.font.name = "Aptos"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
    return box


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, radius=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(1)
    return shape


def line(slide, x1, y1, x2, y2, color=LINE, width=2):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(
        x1), Inches(y1), Inches(x2-x1), Inches(max(0.02, y2-y1)))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def title(slide, eyebrow, heading, subtitle=None):
    add_text(slide, eyebrow.upper(), 0.72, 0.38, 5.5, 0.28, 10, TEAL, True)
    add_text(slide, heading, 0.72, 0.70, 11.9, 0.64, 27, NAVY, True)
    if subtitle:
        add_text(slide, subtitle, 0.72, 1.34, 11.9, 0.46, 13, MID)


def footer(slide, index, label="CPP • PM000003"):
    add_text(slide, label, 0.72, 7.12, 4.0, 0.2, 8, MID, True)
    add_text(slide, f"{index:02d}", 12.15, 7.08, 0.45,
             0.22, 9, MID, True, align=PP_ALIGN.RIGHT)


def new_slide(bg=OFFWHITE):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = bg
    return slide


def metric(slide, x, y, w, value, label, accent=TEAL, note=None):
    rect(slide, x, y, w, 1.18, WHITE, LINE, True)
    add_text(slide, value, x+0.18, y+0.12, w-0.36, 0.50, 25, accent, True)
    add_text(slide, label, x+0.18, y+0.67, w-0.36, 0.26, 10, INK, True)
    if note:
        add_text(slide, note, x+0.18, y+0.94, w-0.36, 0.18, 8, MID)


def bullet_list(slide, items, x, y, w, h, size=14, color=INK, bullet_color=TEAL):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    for i, item in enumerate(items):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.text = "•  " + item
        paragraph.level = 0
        paragraph.space_after = Pt(8)
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = color
    return box


def pill(slide, text, x, y, w, fill=MINT, color=TEAL):
    shape = rect(slide, x, y, w, 0.34, fill, fill, True)
    add_text(slide, text, x+0.08, y+0.07, w-0.16, 0.18,
             9, color, True, align=PP_ALIGN.CENTER)
    return shape


# 1 Cover
slide = new_slide(NAVY)
rect(slide, 0, 0, 0.18, 7.5, TEAL, TEAL)
add_text(slide, "PARITY AI FACTORY", 0.82, 0.62,
         5.5, 0.3, 11, RGBColor(123, 229, 211), True)
add_text(slide, "From requirements to\nreconciled evidence",
         0.82, 1.25, 8.3, 1.75, 34, WHITE, True)
add_text(slide, "CPP PM000003 • Agentic parity analysis for pricing discrepancies",
         0.84, 3.20, 7.8, 0.56, 16, RGBColor(209, 221, 225))
rect(slide, 9.25, 1.12, 3.2, 4.75, RGBColor(
    27, 48, 65), RGBColor(62, 86, 103), True)
add_text(slide, "DEMO RUN", 9.62, 1.55, 2.35, 0.3, 11,
         RGBColor(123, 229, 211), True, align=PP_ALIGN.CENTER)
metric(slide, 9.55, 2.05, 2.6, "250", "synthetic mismatch rows", TEAL)
metric(slide, 9.55, 3.42, 2.6, "31", "automated tests", CORAL)
metric(slide, 9.55, 4.79, 2.6, "100%", "DB / workbook reconciliation", GOLD)
add_text(slide, "Demo deck • 24 Nov 2026", 0.84,
         6.72, 4.2, 0.28, 10, RGBColor(160, 180, 188))

# 2 Executive proposition
slide = new_slide()
title(slide, "01 • Why this exists", "Turn parity analysis into a repeatable evidence pipeline",
      "Factory-generated project structure + deterministic rules + controlled AI second pass.")
metric(slide, 0.72, 2.02, 2.8, "50", "source log rows",
       SKY, "two synthetic exports")
metric(slide, 3.72, 2.02, 2.8, "250", "normalized records",
       TEAL, "multiple DTOs per message")
metric(slide, 6.72, 2.02, 2.8, "220",
       "logical groups", CORAL, "paired by synthetic key")
metric(slide, 9.72, 2.02, 2.8, "30", "paired mismatches",
       GOLD, "field-level differences")
rect(slide, 0.72, 3.58, 11.80, 2.55, WHITE, LINE, True)
add_text(slide, "The operating idea", 1.02, 3.88, 2.35, 0.34, 15, NAVY, True)
for i, (label, detail, color) in enumerate([
    ("Scripts", "parse, load, compare, classify", TEAL),
    ("Agents", "orchestrate tasks and ask for missing inputs", CORAL),
    ("Rules", "apply repeatable known-discrepancy logic", GOLD),
    ("LLM", "review only unresolved candidates with evidence", SKY),
]):
    x = 1.0 + i*2.82
    pill(slide, label, x, 4.45, 1.05, fill=RGBColor(238, 244, 244), color=color)
    add_text(slide, detail, x, 4.94, 2.45, 0.78, 11, INK)
add_text(slide, "Human review is the final control, not the data-processing engine.",
         1.02, 5.78, 10.7, 0.3, 12, NAVY, True)
footer(slide, 2)

# 3 Factory/project split
slide = new_slide()
title(slide, "02 • Factory model", "One factory. Many standalone parity projects.",
      "The factory creates; each generated project runs and owns its own data, configuration, and reports.")
rect(slide, 0.82, 2.0, 5.2, 3.7, NAVY, NAVY, True)
add_text(slide, "PARITY PROJECT FACTORY", 1.18,
         2.35, 4.3, 0.34, 17, WHITE, True)
bullet_list(slide, ["Designer interviews and confirms requirements", "Templates create consistent folders, config, agents and skills",
            "Generic parity_core is copied into each project", "Tests protect factory behavior"], 1.18, 2.92, 4.35, 2.2, 13, RGBColor(226, 236, 239), RGBColor(123, 229, 211))
rect(slide, 7.35, 2.0, 5.2, 3.7, WHITE, LINE, True)
add_text(slide, "CPP PM000003", 7.72, 2.35, 4.3, 0.34, 17, NAVY, True)
bullet_list(slide, ["Runs source-to-target or supplied-report workflow", "Owns SQLite evidence and reports",
            "Contains 13 independent task agents", "Can resume or run any task from the middle"], 7.72, 2.92, 4.3, 2.2, 13)
add_text(slide, "GENERATES →", 5.82, 3.62, 1.65,
         0.42, 17, TEAL, True, align=PP_ALIGN.CENTER)
add_text(slide, "Keep production files, databases and reports outside the factory.",
         2.45, 6.25, 8.4, 0.35, 12, MID, True, align=PP_ALIGN.CENTER)
footer(slide, 3)

# 4 CPP workflow
slide = new_slide()
title(slide, "03 • PM000003 flow", "A gated pipeline with two entry paths and one analysis model",
      "Every stage is persisted, resumable and independently executable.")
steps = [
    ("01", "Inputs", "2 mismatch CSVs + CPP/IMS evidence", SKY),
    ("02", "Precheck", "config, schema, columns, dates", TEAL),
    ("03", "Load", "SQLite raw and reference tables", TEAL),
    ("04", "Pair", "logical key + field differences", GOLD),
    ("05", "Rules", "ordered KD first-match classification", CORAL),
    ("06", "LLM", "unresolved cases only", SKY),
    ("07", "Review", "human confirmation where needed", CORAL),
    ("08", "Publish", "reconciled Excel + summary", GOLD),
]
for i, (num, heading, detail, color) in enumerate(steps):
    row = 0 if i < 4 else 1
    col = i if i < 4 else i-4
    x = 0.73 + col*3.13
    y = 2.08 + row*2.05
    rect(slide, x, y, 2.78, 1.47, WHITE, LINE, True)
    pill(slide, num, x+0.18, y+0.18, 0.55, fill=color, color=WHITE)
    add_text(slide, heading, x+0.86, y+0.18, 1.62, 0.3, 14, NAVY, True)
    add_text(slide, detail, x+0.18, y+0.68, 2.38, 0.5, 10, MID)
    if col < 3:
        add_text(slide, "→", x+2.77, y+0.54, 0.34, 0.28,
                 18, TEAL, True, align=PP_ALIGN.CENTER)
add_text(slide, "Any task can run independently when its declared prerequisites have evidence.",
         2.25, 6.35, 8.9, 0.32, 12, NAVY, True, align=PP_ALIGN.CENTER)
footer(slide, 4)

# 5 Agent system
slide = new_slide()
title(slide, "04 • Agent roles", "Thirteen agents, one clear responsibility each",
      "Agents coordinate work. Python scripts perform deterministic data processing.")
agents = [
    ("Orchestrator", "plans / resumes / routes"), ("Requirements", "confirms unknowns"),
    ("DB Migrator", "schema / backup / migrate"), ("CPP Loader", "snapshot load"),
    ("IMS Migrator", "explicit store/day mapping"), ("Report Runner",
                                                     "parse / normalize / persist"),
    ("CPP Analyst", "packet evidence expansion"), ("Classifier", "ordered KD predicates"),
    ("LLM Analyst", "structured unresolved review"), ("Review Coordinator",
                                                      "manual verdict import"),
    ("Reporter", "working + final workbook"), ("Validator",
                                               "reconciliation / acceptance"),
    ("Consolidated Reporter", "named-report management view"),
]
for i, (name, desc) in enumerate(agents):
    row, col = divmod(i, 4)
    if i == 12:
        col = 1
        row = 3
    x = 0.72 + col*3.13
    y = 1.90 + row*1.17
    rect(slide, x, y, 2.78, 0.88, WHITE, LINE, True)
    add_text(slide, name, x+0.15, y+0.13, 2.45, 0.25, 11, NAVY, True)
    add_text(slide, desc, x+0.15, y+0.47, 2.45, 0.20, 9, MID)
add_text(slide, "Single-role agents avoid prompt-driven data drift and make failure ownership explicit.",
         1.55, 6.58, 10.2, 0.28, 11, TEAL, True, align=PP_ALIGN.CENTER)
footer(slide, 5)

# 6 Rules scripts skills
slide = new_slide()
title(slide, "05 • Controls and capabilities", "Rules constrain behavior; scripts create evidence; skills guide repeatable work",
      "The distinction matters when explaining why the solution is reproducible.")
columns = [
    ("RULES", CORAL, ["Never infer missing contracts", "Explicit IMS table/day map",
     "Backup before destructive work", "First-match KD priority", "Stop on failed dependency"]),
    ("SCRIPTS", TEAL, ["init / validate database", "load CPP + migrate IMS",
     "parse / pair / explode", "classify / LLM bridge", "report / review / validate"]),
    ("SKILLS / WORKFLOWS", GOLD, ["Requirements confirmation", "Add or tune dataset mapping",
     "Investigate result evidence", "Tune from manual feedback", "Run, resume or execute one task"]),
]
for i, (heading, color, items) in enumerate(columns):
    x = 0.72 + i*4.18
    rect(slide, x, 1.92, 3.78, 4.68, WHITE, LINE, True)
    rect(slide, x, 1.92, 3.78, 0.18, color, color)
    add_text(slide, heading, x+0.25, 2.30, 3.2, 0.36, 15, color, True)
    bullet_list(slide, items, x+0.25, 2.88, 3.18, 2.85, 12)
footer(slide, 6)

# 7 LLM usage
slide = new_slide()
title(slide, "06 • LLM boundary", "Use AI where rules stop — not where evidence already exists",
      "Deterministic analysis stays primary. LLM review is gated, structured and non-writing without new evidence.")
rect(slide, 0.82, 2.0, 5.55, 3.9, MINT, MINT, True)
add_text(slide, "DETERMINISTIC FIRST", 1.15, 2.38, 4.7, 0.3, 16, TEAL, True)
bullet_list(slide, ["Schema, mapping and normalization", "Known discrepancy predicates",
            "Price/date and evidence queries", "Paired-key and count reconciliation"], 1.15, 2.96, 4.55, 1.75, 13)
pill(slide, "No LLM needed", 1.15, 5.23, 1.55, fill=TEAL, color=WHITE)
rect(slide, 6.95, 2.0, 5.55, 3.9, RGBColor(
    239, 244, 248), RGBColor(211, 224, 232), True)
add_text(slide, "LLM SECOND PASS", 7.28, 2.38, 4.7, 0.3, 16, SKY, True)
bullet_list(slide, ["Only POTENTIAL_ISSUE and IMS_DATA_ISSUE", "Receives record, KD catalogue and evidence gaps",
            "Returns schema-validated JSON", "INSUFFICIENT_EVIDENCE preserves prior verdict"], 7.28, 2.96, 4.55, 1.75, 13)
pill(slide, "Review, do not guess", 7.28, 5.23, 2.00, fill=SKY, color=WHITE)
add_text(slide, "Future telemetry: capture candidate count, token/cost, latency, model, accepted vs rejected findings.",
         1.82, 6.34, 9.75, 0.31, 11, MID, True, align=PP_ALIGN.CENTER)
footer(slide, 7)

# 8 Actual project
slide = new_slide()
title(slide, "07 • CPP evidence", "PM000003 ran on uploaded inputs and the canonical evidence database",
      "Observed results from the 16–20 Nov 2026 synthetic run.")
metric(slide, 0.75, 2.02, 2.25, "250", "parsed rows", TEAL)
metric(slide, 3.2, 2.02, 2.25, "0", "malformed rows", GREEN)
metric(slide, 5.65, 2.02, 2.25, "220", "logical groups", SKY)
metric(slide, 8.1, 2.02, 2.25, "30", "paired mismatches", GOLD)
metric(slide, 10.55, 2.02, 2.0, "31", "tests passed", CORAL)
rect(slide, 0.75, 3.58, 11.8, 2.45, WHITE, LINE, True)
add_text(slide, "Data path", 1.05, 3.90, 1.2, 0.28, 14, NAVY, True)
labels = ["2 New Relic exports", "5 CPP snapshots",
          "11 IMS stores", "SQLite evidence", "Excel + summary"]
for i, label in enumerate(labels):
    x = 1.05 + i*2.25
    rect(slide, x, 4.48, 1.88, 0.68, RGBColor(241, 246, 246), LINE, True)
    add_text(slide, label, x+0.08, 4.68, 1.72, 0.22,
             9, INK, True, align=PP_ALIGN.CENTER)
    if i < 4:
        add_text(slide, "→", x+1.92, 4.67, 0.28, 0.24, 14, TEAL, True)
add_text(slide, "Observed: every mismatch row received a verdict and workbook count reconciled exactly to the database.",
         1.05, 5.47, 10.95, 0.33, 11, GREEN, True)
footer(slide, 8)

# 9 classification result chart-like
slide = new_slide()
title(slide, "08 • Classification", "80.00% expected; evidence gaps remain visibly actionable",
      "KD matches stay EXPECTED. Missing proof is shown as confirmation required, not a false potential issue.")
items = [("EXPECTED • KD-2", 50, 20.0, RGBColor(91, 168, 145)), ("EXPECTED • KD-9", 50, 20.0, RGBColor(50, 150, 125)), ("POTENTIAL • no KD", 50, 20.0,
                                                                                                                        CORAL), ("EXPECTED • KD-6", 40, 16.0, TEAL), ("EXPECTED • KD-8", 25, 10.0, SKY), ("EXPECTED • KD-10", 25, 10.0, GOLD)]
add_text(slide, "Classification", 0.85, 1.86, 2.4, 0.28, 12, MID, True)
add_text(slide, "Rows", 8.95, 1.86, 0.8, 0.28,
         12, MID, True, align=PP_ALIGN.RIGHT)
add_text(slide, "Share", 10.28, 1.86, 0.9, 0.28,
         12, MID, True, align=PP_ALIGN.RIGHT)
for i, (name, count, pct, color) in enumerate(items):
    y = 2.25 + i*0.67
    add_text(slide, name, 0.85, y, 2.6, 0.25, 11, NAVY, True)
    rect(slide, 3.55, y+0.04, 5.15, 0.24,
         RGBColor(232, 238, 238), RGBColor(232, 238, 238), True)
    width = max(0.08, 5.15 * pct / 20.0)
    rect(slide, 3.55, y+0.04, width, 0.24, color, color, True)
    add_text(slide, f"{count:,}", 8.92, y, 0.82, 0.25,
             11, INK, True, align=PP_ALIGN.RIGHT)
    add_text(slide, f"{pct:.2f}%", 10.10, y, 1.02,
             0.25, 11, INK, True, align=PP_ALIGN.RIGHT)
rect(slide, 0.85, 6.38, 11.0, 0.48, RGBColor(244, 247, 247), LINE, True)
add_text(slide, "150 expected KD-2/KD-8/KD-9/KD-10 rows carry confirmation_status = CONFIRMATION_REQUIRED.",
         1.05, 6.51, 10.6, 0.22, 10, NAVY, True)
footer(slide, 9)

# 10 LLM measured result
slide = new_slide()
title(slide, "09 • LLM outcome", "The LLM did not fabricate classifications",
      "Synthetic run sent only the 50 uncoded potential issues to LLM review.")
metric(slide, 0.85, 2.0, 2.55, "50",
       "candidate rows", SKY, "synthetic run")
metric(slide, 3.66, 2.0, 2.55, "50", "insufficient evidence",
       TEAL, "verdicts preserved")
metric(slide, 6.47, 2.0, 2.55, "0", "ambiguous findings", GREEN)
metric(slide, 9.28, 2.0, 2.55, "0", "reclassified rows", GOLD)
rect(slide, 0.85, 3.64, 11.0, 2.18, WHITE, LINE, True)
add_text(slide, "Why no LLM reclassification?",
         1.15, 3.94, 3.35, 0.32, 15, NAVY, True)
bullet_list(slide, ["No additional evidence was supplied beyond the deterministic snapshot", "Missing price events, participation and lineage must remain visible",
            "LLM returns INSUFFICIENT_EVIDENCE instead of overwriting known rules"], 1.15, 4.40, 9.8, 1.13, 12)
add_text(slide, "This is a control success, not an LLM failure.",
         8.3, 5.54, 3.0, 0.3, 11, GREEN, True, align=PP_ALIGN.RIGHT)
footer(slide, 10)

# 11 metrics distinction
slide = new_slide()
title(slide, "10 • Productivity metrics", "Measured facts vs illustrative productivity model",
      "Never present an assumed saving as observed performance.")
rect(slide, 0.78, 1.85, 5.75, 4.8, WHITE, LINE, True)
add_text(slide, "MEASURED IN THIS RUN", 1.12, 2.18, 4.8, 0.3, 15, TEAL, True)
observed = ["250 synthetic rows reconciled end to end", "0 malformed source rows", "31 automated tests passed",
            "100% mismatch / verdict / workbook count match", "50 LLM findings validated; 0 rejected", "13 independent project agents"]
bullet_list(slide, observed, 1.12, 2.72, 4.75, 2.95, 12)
pill(slide, "Observed", 1.12, 5.98, 1.1, fill=TEAL, color=WHITE)
rect(slide, 6.82, 1.85, 5.72, 4.8, RGBColor(
    251, 246, 235), RGBColor(232, 215, 175), True)
add_text(slide, "ILLUSTRATIVE PLANNING MODEL",
         7.16, 2.18, 4.7, 0.3, 15, GOLD, True)
add_text(slide, "Manual assumption", 7.16, 2.77, 2.0, 0.25, 11, NAVY, True)
add_text(slide, "30 sec per row = 2.08 hours",
         7.16, 3.09, 4.6, 0.35, 16, INK, True)
add_text(slide, "AI-assisted assumption",
         7.16, 3.66, 2.5, 0.25, 11, NAVY, True)
add_text(slide, "0.5 hour automated + 0.5 hour review = 1.0 hour",
         7.16, 3.98, 4.75, 0.58, 16, INK, True)
add_text(slide, "Illustrative saving: 1.08 hours • 52% • 2.1× throughput",
         7.16, 4.87, 4.65, 0.58, 16, CORAL, True)
pill(slide, "Validate with telemetry", 7.16, 5.98, 2.1, fill=GOLD, color=WHITE)
footer(slide, 11)

# 12 accuracy metrics
slide = new_slide()
title(slide, "11 • Accuracy and control", "Faster matters only when the evidence remains trustworthy",
      "Use control metrics alongside speed metrics.")
metrics = [
    ("Reconciliation", "100%", "DB, verdict and workbook row counts"),
    ("Parse integrity", "0", "malformed CSV rows"),
    ("Rule auditability", "8 groups", "classified by visible KD or no-match"),
    ("LLM validation", "100%", "50/50 insufficient-evidence; none rejected"),
    ("Known outcomes", "200", "expected rows with review gates retained"),
    ("Review queue", "50", "true uncoded potential issues"),
]
for i, (name, val, note) in enumerate(metrics):
    row, col = divmod(i, 3)
    x = 0.8 + col*4.18
    y = 1.95 + row*2.1
    rect(slide, x, y, 3.72, 1.62, WHITE, LINE, True)
    add_text(slide, name.upper(), x+0.2, y+0.2, 3.25, 0.2, 9, MID, True)
    add_text(slide, val, x+0.2, y+0.50, 3.25, 0.45,
             24, TEAL if row == 0 else CORAL, True)
    add_text(slide, note, x+0.2, y+1.05, 3.25, 0.35, 10, INK)
footer(slide, 12)

# 13 evidence gaps
slide = new_slide()
title(slide, "12 • Confirmation queue", "Missing evidence is a recommendation column, not a hidden classification",
      "Expected KD rows remain expected, with explicit user confirmation required.")
gaps = [("product_deal_store_rel", 25, "deal/store participation"), ("priceChangeEvent", 125, "manual IMS change evidence"), ("IMS update history",
                                                                                                                              25, "application lineage"), ("deletion history", 50, "zone/override removal"), ("packet lineage", 50, "CPP origin and propagation")]
for i, (name, count, detail) in enumerate(gaps):
    y = 1.95 + i*0.87
    add_text(slide, f"{i+1:02d}", 0.85, y, 0.48, 0.28, 11, TEAL, True)
    add_text(slide, name, 1.45, y, 2.55, 0.28, 12, NAVY, True)
    rect(slide, 4.25, y+0.04, 4.65, 0.22,
         RGBColor(231, 237, 237), RGBColor(231, 237, 237), True)
    rect(slide, 4.25, y+0.04, max(0.08, 4.65*count/125), 0.22,
         CORAL if count > 20 else GOLD, CORAL if count > 20 else GOLD, True)
    add_text(slide, f"{count:,}", 9.13, y, 0.8, 0.28,
             12, INK, True, align=PP_ALIGN.RIGHT)
    add_text(slide, detail, 10.18, y, 2.15, 0.28, 10, MID)
rect(slide, 0.85, 6.37, 11.5, 0.5, MINT, MINT, True)
add_text(slide, "Workbook columns: confirmation_status • confirmation_reason • missing_evidence",
         1.05, 6.52, 11.0, 0.22, 10, TEAL, True, align=PP_ALIGN.CENTER)
footer(slide, 13)

# 14 demo run
slide = new_slide()
title(slide, "13 • Demo path", "A 12-minute end-to-end walkthrough",
      "Show the orchestration, evidence, report and controls without exposing production data.")
agenda = [("0–2", "Factory", "requirements → spec → project structure"), ("2–4", "Inputs", "CSV + DB + prechecks"), ("4–6", "Rules", "pairing + KD precedence"), ("6–8", "LLM gate",
                                                                                                                                                                  "candidate export + no-writeback result"), ("8–10", "Workbook", "classification, detail and confirmation"), ("10–12", "Resume", "run one middle task + metrics model")]
for i, (time, label, detail) in enumerate(agenda):
    y = 1.82 + i*0.82
    rect(slide, 0.84, y, 11.55, 0.62, WHITE, LINE, True)
    pill(slide, time, 1.02, y+0.14, 0.78,
         fill=TEAL if i < 3 else CORAL, color=WHITE)
    add_text(slide, label, 2.05, y+0.16, 1.65, 0.24, 11, NAVY, True)
    add_text(slide, detail, 3.85, y+0.16, 7.9, 0.24, 11, MID)
add_text(slide, "Demo close: the factory is repeatable; the project is operational; telemetry is the next maturity layer.",
         1.20, 6.73, 10.6, 0.28, 11, TEAL, True, align=PP_ALIGN.CENTER)
footer(slide, 14)

# 15 telemetry roadmap
slide = new_slide()
title(slide, "14 • Telemetry roadmap", "Make speed, cost and accuracy measurable in production",
      "Telemetry is not required to run the pipeline, but it is required to publish verified productivity claims.")
phases = [
    ("Capture", "stage, input volume, duration, rows/sec, error, retry", TEAL),
    ("AI usage", "candidate count, model, token/cost, latency, accepted findings", SKY),
    ("Quality", "manual agreement, overturn rate, missing-evidence closure", CORAL),
    ("Business", "hours saved, review cycle, defects caught, report SLA", GOLD),
]
for i, (heading, detail, color) in enumerate(phases):
    x = 0.78 + i*3.14
    rect(slide, x, 2.15, 2.82, 2.72, WHITE, LINE, True)
    pill(slide, f"0{i+1}", x+0.2, 2.4, 0.62, fill=color, color=WHITE)
    add_text(slide, heading, x+0.2, 3.02, 2.3, 0.32, 16, NAVY, True)
    add_text(slide, detail, x+0.2, 3.55, 2.35, 0.9, 11, MID)
rect(slide, 1.2, 5.45, 10.95, 0.75, NAVY, NAVY, True)
add_text(slide, "Proposed KPI: hours saved = manual baseline − (automation runtime + reviewer time + rework)",
         1.47, 5.70, 10.4, 0.28, 12, WHITE, True, align=PP_ALIGN.CENTER)
footer(slide, 15)

# 16 executive close
slide = new_slide(NAVY)
add_text(slide, "EXECUTIVE TAKEAWAY", 0.8, 0.63,
         4.5, 0.3, 11, RGBColor(123, 229, 211), True)
add_text(slide, "This solution standardizes\nthe analysis — not the judgment.",
         0.8, 1.28, 9.5, 1.25, 31, WHITE, True)
for i, text in enumerate([
    "Factory accelerates consistent project creation",
    "Rules make known discrepancy decisions repeatable",
    "Agents support independent and resumable execution",
    "LLM is used where it can add evidence, not certainty theater",
    "Human review remains explicit, traceable and reportable",
]):
    add_text(slide, "✓", 0.92, 3.00+i*0.58, 0.35,
             0.28, 16, RGBColor(123, 229, 211), True)
    add_text(slide, text, 1.38, 3.00+i*0.58, 8.85,
             0.34, 14, RGBColor(221, 232, 235), i == 4)
rect(slide, 9.65, 1.38, 2.78, 4.72, RGBColor(
    27, 48, 65), RGBColor(62, 86, 103), True)
add_text(slide, "NEXT", 10.00, 1.79, 2.0, 0.3,
         11, GOLD, True, align=PP_ALIGN.CENTER)
add_text(slide, "1", 10.65, 2.48, 0.65, 0.52,
         28, WHITE, True, align=PP_ALIGN.CENTER)
add_text(slide, "Run with production or larger synthetic data", 10.00,
         3.10, 2.08, 0.78, 12, WHITE, True, align=PP_ALIGN.CENTER)
add_text(slide, "2", 10.65, 4.00, 0.65, 0.52,
         28, WHITE, True, align=PP_ALIGN.CENTER)
add_text(slide, "Enable telemetry and publish measured ROI", 10.00,
         4.62, 2.08, 0.75, 12, WHITE, True, align=PP_ALIGN.CENTER)
add_text(slide, "31 tests • 0 editor errors • reconciliation passed",
         0.84, 6.73, 7.4, 0.28, 10, RGBColor(160, 180, 188))

# 17 High-level architecture
slide = new_slide()
title(slide, "15 • Architecture", "High-level factory and project architecture",
      "A generic generation layer creates a standalone, evidence-backed parity application.")
rect(slide, 0.70, 1.95, 3.05, 3.85, NAVY, NAVY, True)
add_text(slide, "PARITY FACTORY", 1.02, 2.28, 2.4,
         0.32, 16, WHITE, True, align=PP_ALIGN.CENTER)
bullet_list(slide, ["Designer agent", "Confirmed spec", "Templates and generic core", "Examples, tests and rules"],
            1.05, 2.95, 2.35, 2.0, 12, RGBColor(226, 236, 239))
add_text(slide, "→ GENERATES →", 3.83, 3.52, 1.55,
         0.32, 15, TEAL, True, align=PP_ALIGN.CENTER)
rect(slide, 5.30, 1.95, 3.15, 3.85, WHITE, LINE, True)
add_text(slide, "STANDALONE PROJECT", 5.62, 2.28, 2.5,
         0.32, 16, NAVY, True, align=PP_ALIGN.CENTER)
bullet_list(slide, ["Agents, skills and instructions", "Config and business rules", "Vendored engine and scripts", "Input, DB, output and telemetry"],
            5.65, 2.95, 2.5, 2.0, 12)
add_text(slide, "→ ACQUIRES / RUNS →", 8.50, 3.52, 1.8,
         0.32, 14, TEAL, True, align=PP_ALIGN.CENTER)
rect(slide, 10.25, 1.95, 2.35, 3.85, RGBColor(
    239, 244, 248), RGBColor(211, 224, 232), True)
add_text(slide, "EVIDENCE", 10.52, 2.28, 1.8, 0.32,
         16, SKY, True, align=PP_ALIGN.CENTER)
bullet_list(slide, ["Manual files", "Local connector", "Optional SQL / FTP / cloud", "Reports and feedback"],
            10.55, 2.95, 1.72, 2.0, 11)
add_text(slide, "One database and one report lifecycle connect all stages; generation, processing and delivery remain separate concerns.",
         1.30, 6.20, 10.8, 0.48, 11, NAVY, True, align=PP_ALIGN.CENTER)
footer(slide, 17)

# 18 Folder structure
slide = new_slide()
title(slide, "16 • Standard project anatomy", "Folders make the generated project understandable and repeatable",
      "Each folder owns one responsibility, so another agent can recreate or run the project without reverse-engineering the repository.")
folders = [
    (".github/", "orchestrator, worker agents, skills, prompts, guardrail instructions"),
    ("config/", "datasets, mappings, filters, workflows, snapshots and run settings"),
    ("rules/", "known-discrepancy catalogue and optional project-specific checks"),
    ("scripts/", "deterministic executables: load, parse, classify, report, validate"),
    ("input/ + reference/", "manual or connector-acquired files and required evidence"),
    ("db/ + output/", "local SQLite evidence, reports, review feedback and telemetry"),
]
for i, (folder, purpose) in enumerate(folders):
    row, col = divmod(i, 2)
    x = 0.78 + col*6.05
    y = 1.92 + row*1.45
    rect(slide, x, y, 5.65, 1.08, WHITE, LINE, True)
    add_text(slide, folder, x+0.22, y+0.16, 1.55, 0.28, 12, TEAL, True)
    add_text(slide, purpose, x+1.78, y+0.15, 3.55, 0.55, 11, INK)
add_text(slide, "Standard structure enables independent ownership, safer regeneration, resumability and consistent onboarding.",
         1.35, 6.48, 10.7, 0.3, 11, NAVY, True, align=PP_ALIGN.CENTER)
footer(slide, 18)

# 19 Execution and independent agents
slide = new_slide()
title(slide, "17 • Execution model", "Run the full pipeline, resume, or invoke one agent independently",
      "A task is allowed to start in the middle only when its declared prerequisites and evidence are valid.")
commands = [
    ("01", "Precheck / init-db", "Setup agent creates and validates schema"),
    ("02", "Load / migrate / parse",
     "Loader, IMS migrator or report runner owns its dataset"),
    ("03", "Filter / compare / ingest",
     "Comparator or Diff Ingestor creates shared results"),
    ("04", "Classify / LLM", "Classifier first; LLM only for configured candidates"),
    ("05", "Report / review / validate",
     "Reporter and Validator publish reconciled evidence"),
]
for i, (number, name, detail) in enumerate(commands):
    y = 1.92 + i*0.76
    pill(slide, number, 0.85, y+0.10, 0.55,
         fill=TEAL if i < 3 else CORAL, color=WHITE)
    add_text(slide, name, 1.62, y+0.10, 2.35, 0.24, 12, NAVY, True)
    add_text(slide, detail, 4.0, y+0.10, 5.2, 0.28, 11, INK)
    add_text(slide, "can run alone", 9.65, y+0.08, 2.05,
             0.28, 10, TEAL, True, align=PP_ALIGN.RIGHT)
rect(slide, 0.85, 6.00, 11.45, 0.72, RGBColor(
    239, 246, 245), RGBColor(203, 227, 218), True)
add_text(slide, "Independent run requires: named task + explicit inputs + successful prerequisite evidence + recorded output. Otherwise the task returns BLOCKED.",
         1.08, 6.19, 10.95, 0.35, 10, NAVY, True, align=PP_ALIGN.CENTER)
footer(slide, 19)

# 20 Connectors and manual placement
slide = new_slide()
title(slide, "18 • Input and output connectors", "Manual file placement is a valid default; automation is optional",
      "The parity engine must not be coupled to how files are acquired or delivered.")
rect(slide, 0.78, 1.90, 5.65, 4.65, WHITE, LINE, True)
add_text(slide, "INPUT ACQUISITION", 1.12, 2.28, 4.8, 0.30, 15, TEAL, True)
bullet_list(slide, ["Manual placement: copy files into input/source, input/target, input/diff or reference folders", "Local connector: selects latest, all or exactly one file by pattern", "Optional SQL connector: read-only query exported to files", "Optional FTP/SFTP/blob/S3/GCS connector downloads to the same folders"],
            1.12, 2.84, 4.7, 2.45, 11)
pill(slide, "No automated connector required",
     1.12, 5.76, 2.75, fill=TEAL, color=WHITE)
rect(slide, 6.78, 1.90, 5.78, 4.65, WHITE, LINE, True)
add_text(slide, "OUTPUT DELIVERY", 7.12, 2.28, 4.8, 0.30, 15, SKY, True)
bullet_list(slide, ["Manual collection: open or copy files from output/reports and output/feedback", "CSV/Excel generation stays local and deterministic", "Optional publisher copies approved outputs to shared folder, FTP/SFTP, blob, S3 or API", "Generation and delivery are separate so a publishing outage cannot change verdicts"],
            7.12, 2.84, 4.75, 2.45, 11)
pill(slide, "Automation is an extension point",
     7.12, 5.76, 2.85, fill=SKY, color=WHITE)
footer(slide, 20)

# 21 Guardrails
slide = new_slide()
title(slide, "19 • Guardrails", "Yes — guardrails are required because parity is evidence-sensitive",
      "Guardrails protect data, decisions and rerun behavior; they do not block valid manual or independent execution.")
guards = [
    ("No assumptions", "Ask for missing keys, dates, scopes, connector details and approval state"),
    ("Data safety", "No credentials or production files in source control; backup before destructive work"),
    ("Evidence gate", "A matched KD may remain EXPECTED, but missing proof becomes CONFIRMATION_REQUIRED"),
    ("LLM control", "Structured JSON only; insufficient evidence cannot overwrite deterministic verdicts"),
    ("Execution control",
     "Stop on failed dependency; record prerequisite and output evidence"),
    ("Report control", "DB, verdict and workbook counts must reconcile before publication"),
]
for i, (name, detail) in enumerate(guards):
    row, col = divmod(i, 2)
    x = 0.78 + col*6.05
    y = 1.90 + row*1.44
    rect(slide, x, y, 5.65, 1.08, WHITE, LINE, True)
    pill(slide, "YES", x+0.18, y+0.17, 0.62, fill=CORAL, color=WHITE)
    add_text(slide, name, x+0.98, y+0.15, 1.55, 0.26, 11, NAVY, True)
    add_text(slide, detail, x+2.42, y+0.13, 2.92, 0.58, 10, INK)
add_text(slide, "Reason: guardrails convert agentic flexibility into auditable, repeatable enterprise behavior.",
         1.50, 6.45, 10.25, 0.32, 12, TEAL, True, align=PP_ALIGN.CENTER)
footer(slide, 21)

# notes: append source/method as speaker-style metadata in slide text, kept invisible-small
for slide in prs.slides:
    # add small accessibility/source strip where useful without clutter
    pass

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUTPUT)
print(f"Created {OUTPUT} with {len(prs.slides)} slides")
