"""
Salary slip PDF generator — CPS LLP branded.
Uses Arial Unicode for full ₹ symbol support.
"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from app.payroll_engine import PayrollResult, MONTH_NAMES

# ── Register Unicode font (supports ₹) ───────────────────────────────────────
ARIAL_UNICODE = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
try:
    pdfmetrics.registerFont(TTFont("AU",     ARIAL_UNICODE))
    pdfmetrics.registerFont(TTFont("AU-Bold", ARIAL_UNICODE))  # same file; weight via size
    BODY  = "AU"
    BOLD  = "AU-Bold"
except Exception:
    BODY  = "Helvetica"
    BOLD  = "Helvetica-Bold"

# ── CPS LLP palette ───────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor("#243673")
C_BLUE   = colors.HexColor("#3b4fe4")
C_RED    = colors.HexColor("#b91c1c")
C_GREEN  = colors.HexColor("#166534")
C_LGREY  = colors.HexColor("#f3f4f6")
C_MGREY  = colors.HexColor("#e2e5e7")
C_TEXT   = colors.HexColor("#1a1a1a")
C_SUB    = colors.HexColor("#6e7180")
C_BORDER = colors.HexColor("#dddddd")
C_EARN_BG  = colors.HexColor("#eef0ff")   # light blue tint for earn total row
C_DED_BG   = colors.HexColor("#fff0f0")   # light red tint for ded total row
C_NET_BG   = colors.HexColor("#dcfce7")   # green for net pay


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", BODY), **kw)


def _pct(v: float, gross: float) -> str:
    if gross == 0:
        return " — "
    return f"{v / gross * 100:.1f}%"


def _inr(n: float) -> str:
    return f"₹{int(n):,}"


def generate_salary_slip_pdf(
    result: PayrollResult,
    month: int,
    year: int,
    company_name: str = "Corporate Personnel Services LLP",
    company_address: str = "Mumbai, Maharashtra — 400001",
) -> bytes:
    buf = io.BytesIO()
    W, H = A4  # 595 × 842 pts
    MARGIN = 1.6 * cm

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=MARGIN, bottomMargin=MARGIN,
        leftMargin=MARGIN, rightMargin=MARGIN,
    )

    story = []

    # ── 1. Header band (two-column) ───────────────────────────────────────────
    col_w = (W - 2 * MARGIN) / 2

    left_lines = [
        [Paragraph("CPS LLP", _s("hl", font=BOLD, fontSize=18,
                                   textColor=C_NAVY, leading=22))],
        [Paragraph("Corporate Personnel Services", _s("hs", fontSize=9,
                                                        textColor=C_BLUE))],
        [Paragraph("cpsllpgroup.com · 25+ Years of Expertise",
                   _s("hss", fontSize=7.5, textColor=C_SUB))],
    ]
    right_lines = [
        [Paragraph("SALARY STATEMENT", _s("rt", font=BOLD, fontSize=13,
                                           textColor=C_NAVY, alignment=TA_RIGHT))],
        [Paragraph(f"{MONTH_NAMES[month]} {year}",
                   _s("rp", fontSize=10, textColor=C_BLUE, alignment=TA_RIGHT))],
        [Paragraph(company_name,
                   _s("rc", fontSize=8, textColor=C_SUB, alignment=TA_RIGHT))],
    ]

    def _mini(rows, align):
        t = Table(rows, colWidths=[col_w - 0.3*cm])
        t.setStyle(TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), BODY),
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        return t

    hdr_tbl = Table(
        [[_mini(left_lines, "left"), _mini(right_lines, "right")]],
        colWidths=[col_w, col_w],
    )
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width="100%", thickness=3, color=C_BLUE))
    story.append(Spacer(1, 4*mm))

    # ── 2. Employee info grid ─────────────────────────────────────────────────
    def _str(v): return str(v) if v and v not in ("nan", "None", "") else "—"

    INFO_STYLE = TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), BODY),
        ("FONTNAME",      (0, 0), ( 0, -1), BOLD),
        ("FONTNAME",      (2, 0), ( 2, -1), BOLD),
        ("FONTNAME",      (4, 0), ( 4, -1), BOLD),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TEXTCOLOR",     (0, 0), ( 0, -1), C_NAVY),
        ("TEXTCOLOR",     (2, 0), ( 2, -1), C_NAVY),
        ("TEXTCOLOR",     (4, 0), ( 4, -1), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LGREY),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_LGREY, C_MGREY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
    ])

    esic_val = "Yes" if result.esic_applicable else "No"
    info_rows = [
        ["Employee ID", _str(result.emp_id),    "Name",        _str(result.name),        "Designation", _str(result.designation)],
        ["Department",  _str(result.department), "UAN",         _str(result.uan),         "PF Number",   _str(result.pf_number)],
        ["ESIC No.",    _str(result.esic_number),"ESIC Applic.",esic_val,                 "Bank A/C",    _str(result.bank_account)],
        ["IFSC",        _str(result.ifsc_code),  "Days in Month",str(result.days_in_month),"Days Worked", str(result.days_worked)],
    ]
    TW = W - 2 * MARGIN
    CW = [2.3*cm, 3.2*cm, 2.3*cm, 3.8*cm, 2.5*cm, 3.4*cm]
    info_tbl = Table(info_rows, colWidths=CW)
    info_tbl.setStyle(INFO_STYLE)
    story.append(info_tbl)
    story.append(Spacer(1, 5*mm))

    # ── 3. Earnings & Deductions side-by-side ─────────────────────────────────
    g = result.gross_earned

    def _section_hdr(text, bg):
        return Table([[text]], colWidths=[None])  # placeholder; styled inline

    # Column widths inside each sub-table: description | amount | %
    DESC_W = 4.6 * cm
    AMT_W  = 2.2 * cm
    PCT_W  = 1.3 * cm
    SUB_W  = DESC_W + AMT_W + PCT_W   # 8.1 cm per side; gap 1 cm → 17.2 cm total ✓

    def make_earn_table():
        rows = [
            # header
            ["EARNINGS",           "Amount",      "% Gross"],
            ["Basic Salary",       _inr(result.earned_basic),  _pct(result.earned_basic, g)],
            ["Dearness Allow.",    _inr(result.earned_da),     _pct(result.earned_da, g)],
            ["HRA",                _inr(result.earned_hra),    _pct(result.earned_hra, g)],
            ["Other Allow.",       _inr(result.earned_other),  _pct(result.earned_other, g)],
            ["Gross Earnings",     _inr(g),                    "100.0%"],
        ]
        t = Table(rows, colWidths=[DESC_W, AMT_W, PCT_W])
        t.setStyle(TableStyle([
            # Header row
            ("BACKGROUND",    (0, 0), (-1, 0),  C_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
            ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
            # Data rows
            ("FONTNAME",      (0, 1), (-1, -2), BODY),
            ("FONTSIZE",      (0, 1), (-1, -2), 8),
            ("TEXTCOLOR",     (0, 1), (-1, -2), C_TEXT),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, C_LGREY]),
            # Total row
            ("BACKGROUND",    (0, -1), (-1, -1), C_EARN_BG),
            ("FONTNAME",      (0, -1), (-1, -1), BOLD),
            ("FONTSIZE",      (0, -1), (-1, -1), 8.5),
            ("TEXTCOLOR",     (0, -1), (-1, -1), C_NAVY),
            # Alignment
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
            # Padding
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            # Grid
            ("LINEBELOW",     (0, 0), (-1, 0),  1,   C_BLUE),
            ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
            ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
        ]))
        return t

    def make_ded_table():
        lwf_lbl = "LWF — Employee" if result.lwf_employee > 0 else "LWF (Jun/Dec only)"
        lwf_amt = _inr(result.lwf_employee) if result.lwf_employee > 0 else "—"
        lwf_pct = _pct(result.lwf_employee, g) if result.lwf_employee > 0 else "—"

        esic_lbl = "ESIC — 0.75%" if result.esic_applicable else "ESIC — N/A"
        esic_amt = _inr(result.employee_esic) if result.esic_applicable else "—"
        esic_pct = _pct(result.employee_esic, g) if result.esic_applicable else "—"

        rows = [
            ["DEDUCTIONS",        "Amount",          "% Gross"],
            [f"EPF — 12%\n(on ₹{int(result.pf_wages):,})",
                                  _inr(result.employee_pf),  _pct(result.employee_pf, g)],
            [esic_lbl,            esic_amt,           esic_pct],
            ["Prof. Tax (MH)",    _inr(result.professional_tax), _pct(result.professional_tax, g)],
            [lwf_lbl,             lwf_amt,            lwf_pct],
            ["Advance Recovery",  _inr(result.advance_deduction), _pct(result.advance_deduction, g)],
            ["Total Deductions",  _inr(result.total_deductions),  _pct(result.total_deductions, g)],
        ]
        t = Table(rows, colWidths=[DESC_W, AMT_W, PCT_W])
        t.setStyle(TableStyle([
            # Header
            ("BACKGROUND",    (0, 0), (-1, 0),  C_RED),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
            ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
            # Data rows
            ("FONTNAME",      (0, 1), (-1, -2), BODY),
            ("FONTSIZE",      (0, 1), (-1, -2), 8),
            ("TEXTCOLOR",     (0, 1), (-1, -2), C_TEXT),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, C_LGREY]),
            # Total row
            ("BACKGROUND",    (0, -1), (-1, -1), C_DED_BG),
            ("FONTNAME",      (0, -1), (-1, -1), BOLD),
            ("FONTSIZE",      (0, -1), (-1, -1), 8.5),
            ("TEXTCOLOR",     (0, -1), (-1, -1), C_RED),
            # Alignment
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
            # Padding
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            # Grid
            ("LINEBELOW",     (0, 0), (-1, 0),  1,   C_RED),
            ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
            ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
        ]))
        return t

    GAP = 0.8 * cm
    pair = Table(
        [[make_earn_table(), Spacer(GAP, 1), make_ded_table()]],
        colWidths=[SUB_W, GAP, SUB_W],
    )
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether([pair]))
    story.append(Spacer(1, 5*mm))

    # ── 4. Net Pay banner ─────────────────────────────────────────────────────
    net_rows = [[
        Paragraph("NET PAY (Take Home)", _s("np", font=BOLD, fontSize=12,
                                             textColor=colors.white)),
        Paragraph(_inr(result.net_pay),  _s("na", font=BOLD, fontSize=16,
                                             textColor=colors.white,
                                             alignment=TA_RIGHT)),
        Paragraph(f"{_pct(result.net_pay, g)} of Gross",
                  _s("np2", fontSize=8, textColor=colors.HexColor("#bbf7d0"),
                     alignment=TA_RIGHT)),
    ]]
    net_tbl = Table(net_rows, colWidths=[TW * 0.45, TW * 0.35, TW * 0.20])
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_GREEN),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS",(0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    story.append(net_tbl)
    story.append(Spacer(1, 5*mm))

    # ── 5. Employer contributions panel ──────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "Employer Statutory Contributions — not deducted from your salary",
        _s("ech", font=BOLD, fontSize=8, textColor=C_NAVY, spaceAfter=4),
    ))

    er_rows = [
        ["Contribution Head",     "Rate",     "Amount",        "% of Your Gross"],
        ["EPF — Employer Share",  "3.67%",    _inr(result.employer_epf), _pct(result.employer_epf, g)],
        ["EPS — Employer Share",  "8.33%",    _inr(result.employer_eps), _pct(result.employer_eps, g)],
        ["ESIC — Employer Share", "3.25%",    _inr(result.employer_esic) if result.esic_applicable else "N/A",
                                              _pct(result.employer_esic, g) if result.esic_applicable else "—"],
        ["LWF — Employer (MH)",   "₹12",      _inr(result.lwf_employer) if result.lwf_employer > 0 else "—", "—"],
        ["Total Employer Cost",   "",
            _inr(result.employer_epf + result.employer_eps +
                 (result.employer_esic if result.esic_applicable else 0) + result.lwf_employer),
            _pct(result.employer_epf + result.employer_eps +
                 (result.employer_esic if result.esic_applicable else 0) + result.lwf_employer, g)],
    ]
    er_cw = [5.5*cm, 1.8*cm, 3.2*cm, 3.0*cm]
    er_tbl = Table(er_rows, colWidths=er_cw)
    er_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("FONTNAME",      (0, 1), (-1, -2), BODY),
        ("FONTSIZE",      (0, 1), (-1, -2), 7.5),
        ("BACKGROUND",    (0, -1), (-1, -1), C_MGREY),
        ("FONTNAME",      (0, -1), (-1, -1), BOLD),
        ("FONTSIZE",      (0, -1), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, C_LGREY]),
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("LINEBELOW",     (0, 0), (-1, 0),  1, C_NAVY),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
    ]))
    story.append(er_tbl)
    story.append(Spacer(1, 4*mm))

    # ── 6. Statutory note ─────────────────────────────────────────────────────
    note = (
        "<b>Statutory Notes:</b> "
        "(1) EPF computed on wages ₹" + f"{int(result.pf_wages):,}" +
        " (ceiling ₹15,000). EPS capped ₹1,250/month. "
        "(2) ESIC applicable for gross ≤ ₹21,000. "
        "(3) Maharashtra PT: ₹0 (≤₹7,500) · ₹175 (≤₹10,000) · ₹200/₹300-Feb (>₹10,000). "
        "(4) LWF deducted in June &amp; December only."
    )
    story.append(Paragraph(note, _s("note", fontSize=6.5, textColor=C_SUB, leading=9)))

    # ── 7. Footer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_NAVY))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Corporate Personnel Services LLP (CPS LLP) · cpsllpgroup.com · "
        "System-generated document — no physical signature required.",
        _s("foot", fontSize=6.5, textColor=C_SUB, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
