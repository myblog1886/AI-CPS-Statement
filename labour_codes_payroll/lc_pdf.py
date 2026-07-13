"""
Salary slip PDF generator — New Labour Codes Compliant Payroll Tool.
Teal/amber colour scheme to distinguish from legacy CPS LLP navy/gold tool.
Includes: compliance flags panel, OT pay section, gratuity accrual note.
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

from lc_engine import PayrollResultLC, MONTH_NAMES

# ── Font ─────────────────────────────────────────────────────────────────────
ARIAL_UNICODE = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
try:
    pdfmetrics.registerFont(TTFont("AU",      ARIAL_UNICODE))
    pdfmetrics.registerFont(TTFont("AU-Bold", ARIAL_UNICODE))
    BODY = "AU"
    BOLD = "AU-Bold"
except Exception:
    BODY = "Helvetica"
    BOLD = "Helvetica-Bold"

# ── Colour palette — teal/amber (distinct from legacy navy/blue) ─────────────
C_TEAL    = colors.HexColor("#0f766e")   # Primary teal
C_TEAL2   = colors.HexColor("#14b8a6")   # Lighter teal
C_AMBER   = colors.HexColor("#d97706")   # Amber accent
C_AMBER2  = colors.HexColor("#fef3c7")   # Light amber
C_RED     = colors.HexColor("#b91c1c")
C_GREEN   = colors.HexColor("#15803d")
C_LGREY   = colors.HexColor("#f3f4f6")
C_MGREY   = colors.HexColor("#e2e5e7")
C_TEXT    = colors.HexColor("#1a1a1a")
C_SUB     = colors.HexColor("#6e7180")
C_BORDER  = colors.HexColor("#dddddd")
C_EARN_BG = colors.HexColor("#ccfbf1")   # teal tint
C_DED_BG  = colors.HexColor("#fff0f0")
C_NET_BG  = colors.HexColor("#dcfce7")
C_FLAG_CRIT = colors.HexColor("#fef2f2")
C_FLAG_WARN = colors.HexColor("#fffbeb")
C_FLAG_INFO = colors.HexColor("#f0fdfa")


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", BODY), **kw)


def _inr(n: float) -> str:
    return f"\u20b9{int(n):,}"


def _pct(v: float, base: float) -> str:
    if base == 0:
        return " \u2014 "
    return f"{v / base * 100:.1f}%"


def generate_salary_slip_lc_pdf(
    result: PayrollResultLC,
    month: int,
    year: int,
    company_name: str = "New Labour Codes Payroll Demo",
    company_address: str = "Maharashtra, India",
) -> bytes:
    buf = io.BytesIO()
    W, H = A4
    MARGIN = 1.5 * cm

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=MARGIN, bottomMargin=MARGIN,
        leftMargin=MARGIN, rightMargin=MARGIN,
    )
    TW = W - 2 * MARGIN
    story = []

    # ── 1. Header ─────────────────────────────────────────────────────────────
    col_w = TW / 2
    left_rows = [
        [Paragraph("NLC Payroll", _s("hl", font=BOLD, fontSize=17, textColor=C_TEAL, leading=21))],
        [Paragraph("New Labour Codes Compliant", _s("hs", fontSize=8.5, textColor=C_TEAL2))],
        [Paragraph("CoW 2019 · CoSS 2020 · IRC 2020 · OSH 2020",
                   _s("hss", fontSize=7, textColor=C_SUB))],
    ]
    right_rows = [
        [Paragraph("SALARY STATEMENT", _s("rt", font=BOLD, fontSize=12,
                                           textColor=C_TEAL, alignment=TA_RIGHT))],
        [Paragraph(f"{MONTH_NAMES[month]} {year}",
                   _s("rp", fontSize=10, textColor=C_AMBER, alignment=TA_RIGHT))],
        [Paragraph(company_name,
                   _s("rc", fontSize=8, textColor=C_SUB, alignment=TA_RIGHT))],
    ]

    def _mini(rows):
        t = Table(rows, colWidths=[col_w - 0.3 * cm])
        t.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        return t

    hdr = Table([[_mini(left_rows), _mini(right_rows)]], colWidths=[col_w, col_w])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(hdr)
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="100%", thickness=3, color=C_TEAL))
    story.append(Spacer(1, 3 * mm))

    # ── 2. Employee Info ──────────────────────────────────────────────────────
    def _v(v): return str(v) if v and str(v) not in ("nan", "None", "") else "\u2014"

    emp_type_display = result.employment_type.replace("_", "-").title()
    esic_val = "Yes" if result.esic_applicable else "No"
    wage_flag = "NON-COMPLIANT" if not result.wage_ratio_compliant else "COMPLIANT"
    wage_color = C_RED if not result.wage_ratio_compliant else C_GREEN

    INFO_STYLE = TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), BODY),
        ("FONTNAME",      (0, 0), ( 0, -1), BOLD),
        ("FONTNAME",      (2, 0), ( 2, -1), BOLD),
        ("FONTNAME",      (4, 0), ( 4, -1), BOLD),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TEXTCOLOR",     (0, 0), ( 0, -1), C_TEAL),
        ("TEXTCOLOR",     (2, 0), ( 2, -1), C_TEAL),
        ("TEXTCOLOR",     (4, 0), ( 4, -1), C_TEAL),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LGREY),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_LGREY, C_MGREY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
    ])
    info_rows = [
        ["Employee ID", _v(result.emp_id), "Name",        _v(result.name),        "Designation", _v(result.designation)],
        ["Department",  _v(result.department),"UAN",      _v(result.uan),          "PF Number",   _v(result.pf_number)],
        ["ESIC No.",    _v(result.esic_number),"ESIC",    esic_val,                "Bank A/C",    _v(result.bank_account)],
        ["Emp. Type",   emp_type_display,   "Yrs Service",f"{result.years_of_service:.1f}","Days", f"{result.days_worked}/{result.days_in_month}"],
    ]
    CW = [2.2 * cm, 3.3 * cm, 2.2 * cm, 3.5 * cm, 2.5 * cm, 3.5 * cm]
    story.append(Table(info_rows, colWidths=CW, style=INFO_STYLE))
    story.append(Spacer(1, 4 * mm))

    # ── 3. Wage Ratio Compliance Banner ──────────────────────────────────────
    banner_bg = C_FLAG_CRIT if not result.wage_ratio_compliant else C_FLAG_INFO
    banner_border = C_RED if not result.wage_ratio_compliant else C_TEAL
    ratio_pct = result.wage_ratio_actual * 100
    banner_text = (
        f"<b>Code on Wages 2019 \u2014 Wage Ratio Check:</b> "
        f"Basic+DA = {_inr(result.core_wages_earned)} "
        f"({ratio_pct:.1f}% of CTC {_inr(result.ctc_gross_monthly)}) \u2014 "
        f"<b>{wage_flag}</b>"
        + (f" \u2014 PF base adjusted to {_inr(result.adjusted_wages)}"
           if result.pf_base_adjusted else "")
    )
    banner_style = _s("banner", fontSize=7.5, textColor=C_RED if not result.wage_ratio_compliant else C_TEAL,
                      leading=11)
    banner_row = [[Paragraph(banner_text, banner_style)]]
    banner_tbl = Table(banner_row, colWidths=[TW])
    banner_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), banner_bg),
        ("BOX",           (0, 0), (-1, -1), 1.2, banner_border),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS",(0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    story.append(banner_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── 4. Earnings & Deductions side-by-side ─────────────────────────────────
    g = result.gross_earned + result.ot_pay
    DESC_W = 4.6 * cm
    AMT_W  = 2.2 * cm
    PCT_W  = 1.3 * cm
    SUB_W  = DESC_W + AMT_W + PCT_W
    GAP    = 0.8 * cm

    def make_earn_table():
        rows = [
            ["EARNINGS (New Labour Codes)", "Amount", "% Gross"],
            [f"Basic Salary\n(Core Wages \u2014 CoW)",
             _inr(result.earned_basic), _pct(result.earned_basic, g)],
            [f"Dearness Allow.",
             _inr(result.earned_da),    _pct(result.earned_da, g)],
            ["HRA\n(Excluded from wages)",
             _inr(result.earned_hra),   _pct(result.earned_hra, g)],
            ["Special Allow.",
             _inr(result.earned_special), _pct(result.earned_special, g)],
            ["Other Allowances",
             _inr(result.earned_other), _pct(result.earned_other, g)],
        ]
        if result.ot_pay > 0:
            rows.append([f"OT Pay (2\u00d7 rate, {result.ot_hours_month:.1f} hrs)",
                         _inr(result.ot_pay), _pct(result.ot_pay, g)])
        rows.append(["Gross Earnings", _inr(g), "100.0%"])

        t = Table(rows, colWidths=[DESC_W, AMT_W, PCT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_TEAL),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTNAME",      (0, 1), (-1, -2), BODY),
            ("FONTSIZE",      (0, 1), (-1, -2), 7.5),
            ("TEXTCOLOR",     (0, 1), (-1, -2), C_TEXT),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, C_LGREY]),
            ("BACKGROUND",    (0, -1), (-1, -1), C_EARN_BG),
            ("FONTNAME",      (0, -1), (-1, -1), BOLD),
            ("FONTSIZE",      (0, -1), (-1, -1), 8.5),
            ("TEXTCOLOR",     (0, -1), (-1, -1), C_TEAL),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, 0),  1,   C_TEAL),
            ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
            ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
        ]))
        return t

    def make_ded_table():
        pf_label = (
            f"EPF \u2014 12% on {_inr(result.pf_wages)}"
            + (" [adjusted]" if result.pf_base_adjusted else "")
        )
        esic_lbl = "ESIC \u2014 0.75%" if result.esic_applicable else "ESIC \u2014 N/A"
        esic_amt = _inr(result.employee_esic) if result.esic_applicable else "\u2014"
        lwf_lbl  = "LWF (Jun/Dec)" if result.lwf_employee == 0 else "LWF \u2014 Employee"
        lwf_amt  = _inr(result.lwf_employee) if result.lwf_employee > 0 else "\u2014"

        rows = [
            ["DEDUCTIONS",       "Amount",       "% Gross"],
            [pf_label,           _inr(result.employee_pf),  _pct(result.employee_pf, g)],
            [esic_lbl,           esic_amt,       _pct(result.employee_esic, g) if result.esic_applicable else "\u2014"],
            ["Prof. Tax (MH)",   _inr(result.professional_tax), _pct(result.professional_tax, g)],
            [lwf_lbl,            lwf_amt,        _pct(result.lwf_employee, g) if result.lwf_employee > 0 else "\u2014"],
            ["Advance Recovery", _inr(result.advance_deduction), _pct(result.advance_deduction, g)],
            ["Total Deductions", _inr(result.total_deductions),  _pct(result.total_deductions, g)],
        ]
        t = Table(rows, colWidths=[DESC_W, AMT_W, PCT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_RED),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTNAME",      (0, 1), (-1, -2), BODY),
            ("FONTSIZE",      (0, 1), (-1, -2), 7.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, C_LGREY]),
            ("BACKGROUND",    (0, -1), (-1, -1), C_DED_BG),
            ("FONTNAME",      (0, -1), (-1, -1), BOLD),
            ("FONTSIZE",      (0, -1), (-1, -1), 8.5),
            ("TEXTCOLOR",     (0, -1), (-1, -1), C_RED),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, 0),  1,   C_RED),
            ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
            ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
        ]))
        return t

    pair = Table(
        [[make_earn_table(), Spacer(GAP, 1), make_ded_table()]],
        colWidths=[SUB_W, GAP, SUB_W],
    )
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether([pair]))
    story.append(Spacer(1, 4 * mm))

    # ── 5. Net Pay banner ────────────────────────────────────────────────────
    net_rows = [[
        Paragraph("NET PAY (Take Home)", _s("np", font=BOLD, fontSize=12, textColor=colors.white)),
        Paragraph(_inr(result.net_pay),  _s("na", font=BOLD, fontSize=16, textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph(f"{_pct(result.net_pay, g)} of Gross",
                  _s("np2", fontSize=8, textColor=colors.HexColor("#bbf7d0"), alignment=TA_RIGHT)),
    ]]
    net_tbl = Table(net_rows, colWidths=[TW * 0.45, TW * 0.35, TW * 0.20])
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_GREEN),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(net_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── 6. Employer contributions ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Employer Statutory Contributions — not deducted from salary",
        _s("ech", font=BOLD, fontSize=8, textColor=C_TEAL, spaceAfter=3),
    ))
    er_rows = [
        ["Contribution", "Rate", "Amount", "Note"],
        ["EPF \u2014 Employer", "3.67%",  _inr(result.employer_epf),
         "On adj. wages" if result.pf_base_adjusted else "On PF wages"],
        ["EPS \u2014 Employer", "8.33%",  _inr(result.employer_eps), "Max \u20b91,250"],
        ["ESIC \u2014 Employer","3.25%",  _inr(result.employer_esic) if result.esic_applicable else "N/A",
         "Gross \u2264\u20b921,000" if result.esic_applicable else "Not applicable"],
        ["LWF \u2014 Employer (MH)", "\u20b912",
         _inr(result.lwf_employer) if result.lwf_employer > 0 else "\u2014", "Jun & Dec only"],
    ]
    if result.gratuity_eligible:
        er_rows.append([
            "Gratuity Accrual (CoSS S.53)", "",
            _inr(result.monthly_gratuity_accrual),
            f"{result.years_of_service:.1f}yr \u00d7 15/26",
        ])
    er_cw = [5.0 * cm, 1.8 * cm, 3.0 * cm, 3.5 * cm]
    er_tbl = Table(er_rows, colWidths=er_cw)
    er_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_TEAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("FONTNAME",      (0, 1), (-1, -1), BODY),
        ("FONTSIZE",      (0, 1), (-1, -1), 7.5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, C_LGREY]),
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), ( 0, -1), "LEFT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("LINEBELOW",     (0, 0), (-1, 0),  1, C_TEAL),
        ("LINEBELOW",     (0, 1), (-1, -1), 0.3, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
    ]))
    story.append(er_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── 7. Leave accrual note ─────────────────────────────────────────────────
    story.append(Paragraph(
        f"<b>Leave (OSH Code S.32):</b> "
        f"Earned this month: {result.leave_earned_this_month:.2f} days "
        f"(1 day per 20 days worked). "
        f"Carry-forward balance: {result.leave_carry_forward_net:.1f} days"
        + (" [CAPPED at 30 days — PENDING GAZETTE]" if result.leave_carry_capped else "."),
        _s("leave", fontSize=7, textColor=C_SUB, leading=10, spaceAfter=3),
    ))

    # ── 8. Compliance flags ──────────────────────────────────────────────────
    if result.flags:
        story.append(Spacer(1, 2 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "Compliance Flags — New Labour Codes",
            _s("flh", font=BOLD, fontSize=8, textColor=C_TEAL, spaceAfter=3),
        ))
        SEV_COLOR = {"critical": C_RED, "warning": C_AMBER, "info": C_TEAL}
        SEV_BG    = {"critical": C_FLAG_CRIT, "warning": C_FLAG_WARN, "info": C_FLAG_INFO}
        flag_rows = [["Severity", "Code", "Detail"]]
        for f in result.flags:
            flag_rows.append([
                f.severity.upper(),
                f.code,
                f.detail[:120],
            ])
        f_tbl = Table(flag_rows, colWidths=[1.8 * cm, 5.2 * cm, TW - 7.0 * cm])
        f_style = [
            ("BACKGROUND",    (0, 0), (-1, 0),  C_TEAL),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  BOLD),
            ("FONTSIZE",      (0, 0), (-1, 0),  7.5),
            ("FONTNAME",      (0, 1), (-1, -1), BODY),
            ("FONTSIZE",      (0, 1), (-1, -1), 7),
            ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, 0),  1, C_TEAL),
            ("LINEBELOW",     (0, 1), (-1, -1), 0.3, C_BORDER),
            ("BOX",           (0, 0), (-1, -1), 0.8, C_BORDER),
        ]
        for i, fl in enumerate(result.flags, 1):
            bg = SEV_BG.get(fl.severity, C_LGREY)
            tc = SEV_COLOR.get(fl.severity, C_TEXT)
            f_style += [
                ("BACKGROUND", (0, i), (-1, i), bg),
                ("TEXTCOLOR",  (0, i), (0, i),  tc),
                ("FONTNAME",   (0, i), (0, i),  BOLD),
                ("FONTSIZE",   (0, i), (0, i),  7),
            ]
        f_tbl.setStyle(TableStyle(f_style))
        story.append(f_tbl)
        story.append(Spacer(1, 3 * mm))

    # ── 9. Statutory notes ─────────────────────────────────────────────────────
    notes = (
        "<b>Statutory Notes (New Labour Codes):</b> "
        "(1) Code on Wages 2019 S.2(y): Basic+DA must be \u226550% of CTC. "
        f"PF wages: {_inr(result.pf_wages)} (ceiling \u20b915,000). "
        "(2) CoSS 2020 S.3: ESIC ceiling \u20b921,000 gross (PENDING GAZETTE for revision). "
        "(3) CoSS 2020 S.53: Gratuity \u2014 fixed-term employees eligible at 1 year; max \u20b920 lakhs. "
        "(4) OSH Code 2020 S.25: OT at 2\u00d7 rate; max shift 12 hrs; 48-hr weekly limit. "
        "(5) Items marked PENDING GAZETTE use widely accepted draft provisions."
    )
    story.append(Paragraph(notes, _s("note", fontSize=6.5, textColor=C_SUB, leading=9)))

    # ── 10. Footer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_TEAL))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "New Labour Codes Compliant Payroll Tool \u2014 "
        "CoW 2019 \u00b7 CoSS 2020 \u00b7 IRC 2020 \u00b7 OSH 2020 \u00b7 "
        "System-generated document.",
        _s("foot", fontSize=6.5, textColor=C_SUB, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
