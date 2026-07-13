"""
EPFO ECR Validation Acknowledgement PDF Generator
Mimics the PDF summary produced by the EPFO Unified Portal after a successful
ECR (.txt) file upload and validation.

Sections mirror the real portal output:
  1. Header — EPFO logo band, establishment identity
  2. Validation Status banner
  3. TRRN & challan reference block
  4. Wage & contribution summary (the "ECR Summary" table)
  5. Account-wise challan breakup (A/c 1, 2, 10, 21, 22)
  6. Member-wise contribution table (scrollable; same columns as ECR)
  7. NCP / LOP summary
  8. Footer — portal watermark, disclaimer
"""
import io
import random
import string
from datetime import datetime, date
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether, PageBreak,
)

from payroll_engine import PayrollResult, MONTH_NAMES

# ── Font ─────────────────────────────────────────────────────────────────────
_ARIAL = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
try:
    pdfmetrics.registerFont(TTFont("AU",  _ARIAL))
    pdfmetrics.registerFont(TTFont("AUB", _ARIAL))
    BODY, BOLD = "AU", "AUB"
except Exception:
    BODY, BOLD = "Helvetica", "Helvetica-Bold"

# ── EPFO colour scheme (matches the portal's visual language) ─────────────────
EPFO_RED    = colors.HexColor("#8B0000")   # EPFO dark red
EPFO_DKRED  = colors.HexColor("#5c0000")   # darker shade for sub-headers
EPFO_ORANGE = colors.HexColor("#e06c1b")   # accent (portal uses orange CTAs)
EPFO_NAVY   = colors.HexColor("#1a2b5f")   # dark navy text
EPFO_LGREY  = colors.HexColor("#f5f5f5")
EPFO_MGREY  = colors.HexColor("#e0e0e0")
EPFO_BORDER = colors.HexColor("#cccccc")
EPFO_GREEN  = colors.HexColor("#1a6b3c")
EPFO_AMBER  = colors.HexColor("#b45309")
WHITE       = colors.white

W, H = A4
MARGIN = 1.5 * cm
TW = W - 2 * MARGIN   # usable text width


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", BODY), **kw)


def _inr(n: float) -> str:
    return f"₹{int(round(n)):,}"


def _trrn() -> str:
    """Generate a realistic-looking TRRN (Temporary Return Reference Number)."""
    return "TRRN" + "".join(random.choices(string.digits, k=16))


def _ack_no(est_id: str, month: int, year: int) -> str:
    prefix = est_id.replace("/", "").replace(" ", "")[:6].upper()
    return f"{prefix}{year}{month:02d}{''.join(random.choices(string.digits, k=6))}"


def generate_ecr_validation_pdf(
    results: List[PayrollResult],
    establishment_id: str,
    establishment_name: str,
    month: int,
    year: int,
    upload_datetime: Optional[datetime] = None,
) -> bytes:

    if upload_datetime is None:
        upload_datetime = datetime.now()

    trrn        = _trrn()
    ack_no      = _ack_no(establishment_id, month, year)
    upload_ts   = upload_datetime.strftime("%d-%b-%Y %H:%M:%S")
    due_date    = f"15-{MONTH_NAMES[month + 1 if month < 12 else 1][:3]}-{year if month < 12 else year + 1}"
    wage_month  = f"{MONTH_NAMES[month]}-{year}"

    # ── Aggregate stats ───────────────────────────────────────────────────────
    total_members   = len(results)
    total_epf_wages = sum(r.pf_wages     for r in results)
    total_eps_wages = sum(r.pf_wages     for r in results)
    total_edli_wages= sum(r.edli_wages   for r in results)
    total_emp_pf    = sum(r.employee_pf  for r in results)
    total_er_epf    = sum(r.employer_epf for r in results)
    total_er_eps    = sum(r.employer_eps for r in results)
    total_epf_cont  = total_emp_pf + total_er_epf      # A/c 1 total
    total_eps_cont  = total_er_eps
    total_epf_eps_diff = total_epf_cont - total_eps_cont
    total_ncp       = sum(r.ncp_days     for r in results)
    ncp_members     = sum(1 for r in results if r.ncp_days > 0)

    # EPFO admin charges
    edli_admin      = max(round(total_edli_wages * 0.005), 25 * total_members)
    epf_admin       = max(round(total_epf_wages  * 0.005), 500)
    total_challan   = total_epf_cont + total_eps_cont + edli_admin + epf_admin

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=MARGIN, bottomMargin=MARGIN + 0.5*cm,
        leftMargin=MARGIN, rightMargin=MARGIN,
    )
    story = []

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. EPFO PORTAL HEADER
    # ═══════════════════════════════════════════════════════════════════════════
    hdr_bg = Table(
        [[
            Paragraph("EMPLOYEES' PROVIDENT FUND ORGANISATION",
                       _s("h1", font=BOLD, fontSize=13, textColor=WHITE,
                          alignment=TA_CENTER)),
        ]],
        colWidths=[TW],
    )
    hdr_bg.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), EPFO_RED),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(hdr_bg)

    sub_hdr = Table(
        [[
            Paragraph("Ministry of Labour &amp; Employment, Government of India",
                       _s("h2", fontSize=8, textColor=WHITE, alignment=TA_CENTER)),
        ]],
        colWidths=[TW],
    )
    sub_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), EPFO_DKRED),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(sub_hdr)
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph(
        "ELECTRONIC CHALLAN CUM RETURN (ECR) — VALIDATION ACKNOWLEDGEMENT",
        _s("title", font=BOLD, fontSize=12, textColor=EPFO_NAVY,
           alignment=TA_CENTER, spaceAfter=2),
    ))
    story.append(Paragraph(
        "Unified Portal · epfindia.gov.in · ECR 2.0",
        _s("sub", fontSize=8, textColor=colors.grey, alignment=TA_CENTER),
    ))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EPFO_RED))
    story.append(Spacer(1, 4*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. VALIDATION STATUS BANNER
    # ═══════════════════════════════════════════════════════════════════════════
    status_tbl = Table(
        [[
            Paragraph("✓  ECR FILE VALIDATED SUCCESSFULLY",
                       _s("vs", font=BOLD, fontSize=11, textColor=WHITE)),
            Paragraph(f"Uploaded: {upload_ts}",
                       _s("vd", fontSize=8, textColor=colors.HexColor("#bbf7d0"),
                          alignment=TA_RIGHT)),
        ]],
        colWidths=[TW * 0.65, TW * 0.35],
    )
    status_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), EPFO_GREEN),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(status_tbl)
    story.append(Spacer(1, 5*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. TRRN / REFERENCE BLOCK
    # ═══════════════════════════════════════════════════════════════════════════
    def _ref_cell(label, value, bold_value=True):
        return [
            Paragraph(label, _s("rl", fontSize=7.5, textColor=colors.grey)),
            Paragraph(value,  _s("rv", font=BOLD if bold_value else BODY,
                                  fontSize=9, textColor=EPFO_NAVY)),
        ]

    ref_data = [
        _ref_cell("TRRN (Temporary Return Reference Number)", trrn),
        _ref_cell("Acknowledgement Number", ack_no),
        _ref_cell("Establishment ID", establishment_id),
        _ref_cell("Establishment Name", establishment_name),
        _ref_cell("Wage Month", wage_month),
        _ref_cell("Challan Due Date", due_date),
    ]

    # Arrange in 2 columns
    ref_rows = []
    for i in range(0, len(ref_data), 2):
        left  = ref_data[i]
        right = ref_data[i+1] if i+1 < len(ref_data) else ["", ""]
        ref_rows.append([left[0], left[1], right[0], right[1]])

    ref_tbl = Table(ref_rows, colWidths=[3.5*cm, 5.8*cm, 3.5*cm, 5.8*cm])
    ref_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,-1), BODY),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("BACKGROUND",    (0,0), (-1,-1), EPFO_LGREY),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [EPFO_LGREY, WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.4, EPFO_BORDER),
    ]))
    story.append(ref_tbl)
    story.append(Spacer(1, 5*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. ECR SUMMARY — WAGE & CONTRIBUTION TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    def _section_bar(text):
        t = Table([[text]], colWidths=[TW])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), EPFO_NAVY),
            ("TEXTCOLOR",     (0,0), (-1,-1), WHITE),
            ("FONTNAME",      (0,0), (-1,-1), BOLD),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ]))
        return t

    story.append(_section_bar("A.  ECR SUMMARY"))
    story.append(Spacer(1, 2*mm))

    summary_rows = [
        ["Description",                      "Amount (₹)"],
        ["Total Members in ECR",             str(total_members)],
        ["Total EPF Wages",                  f"{int(total_epf_wages):,}"],
        ["Total EPS Wages",                  f"{int(total_eps_wages):,}"],
        ["Total EDLI Wages",                 f"{int(total_edli_wages):,}"],
        ["Total Employee PF Contribution (12%)",    _inr(total_emp_pf)],
        ["Total Employer EPF Contribution (3.67%)", _inr(total_er_epf)],
        ["Total Employer EPS Contribution (8.33%)", _inr(total_er_eps)],
        ["Total EPF Contribution (Emp + Employer)", _inr(total_epf_cont)],
        ["EPF – EPS Difference",             _inr(total_epf_eps_diff)],
        ["Total NCP Days",                   f"{total_ncp} days ({ncp_members} members)"],
        ["Total Refund of Advances",         "₹0"],
    ]

    summ_tbl = Table(summary_rows, colWidths=[TW * 0.72, TW * 0.28])
    summ_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  EPFO_RED),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  BOLD),
        ("FONTSIZE",      (0,0), (-1,0),  8.5),
        ("FONTNAME",      (0,1), (-1,-1), BODY),
        ("FONTSIZE",      (0,1), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, EPFO_LGREY]),
        ("ALIGN",         (1,0), (1,-1),  "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("LINEBELOW",     (0,0), (-1,0),  1,   EPFO_RED),
        ("LINEBELOW",     (0,1), (-1,-2), 0.3, EPFO_BORDER),
        ("BOX",           (0,0), (-1,-1), 0.8, EPFO_BORDER),
    ]))
    story.append(summ_tbl)
    story.append(Spacer(1, 5*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. ACCOUNT-WISE CHALLAN BREAKUP
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(_section_bar("B.  ACCOUNT-WISE CHALLAN BREAKUP"))
    story.append(Spacer(1, 2*mm))

    challan_rows = [
        ["A/c No.", "Head",                           "Description",                      "Amount (₹)"],
        ["A/c No. 1",  "EPF",  "Employee PF (12%) + Employer EPF (3.67%)",   _inr(total_epf_cont)],
        ["A/c No. 10", "EPS",  "Employer EPS Contribution (8.33%)",           _inr(total_eps_cont)],
        ["A/c No. 2",  "EDLI Admin",  "EDLI Admin Charges (0.5%, min ₹25/member)", _inr(edli_admin)],
        ["A/c No. 22", "EPF Admin",   "EPF Admin Charges (0.5%, min ₹500)",        _inr(epf_admin)],
        ["A/c No. 21", "EDLI",        "EDLI Contribution (0% — NIL)",               "₹0"],
        ["",           "",     "TOTAL CHALLAN AMOUNT",                         _inr(total_challan)],
    ]

    chal_cw = [2.2*cm, 2.2*cm, TW - 2.2*cm - 2.2*cm - 3.2*cm, 3.2*cm]
    chal_tbl = Table(challan_rows, colWidths=chal_cw)
    chal_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  EPFO_RED),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  BOLD),
        ("FONTSIZE",      (0,0), (-1,0),  8.5),
        ("FONTNAME",      (0,1), (-1,-2), BODY),
        ("FONTSIZE",      (0,1), (-1,-2), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [WHITE, EPFO_LGREY]),
        # Total row
        ("BACKGROUND",    (0,-1), (-1,-1), EPFO_NAVY),
        ("TEXTCOLOR",     (0,-1), (-1,-1), WHITE),
        ("FONTNAME",      (0,-1), (-1,-1), BOLD),
        ("FONTSIZE",      (0,-1), (-1,-1), 9),
        ("SPAN",          (0,-1), (2,-1)),
        ("ALIGN",         (3,0),  (3,-1),  "RIGHT"),
        ("ALIGN",         (2,-1), (2,-1),  "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("LINEBELOW",     (0,0), (-1,0),  1,   EPFO_RED),
        ("LINEBELOW",     (0,1), (-1,-2), 0.3, EPFO_BORDER),
        ("BOX",           (0,0), (-1,-1), 0.8, EPFO_BORDER),
    ]))
    story.append(chal_tbl)
    story.append(Spacer(1, 5*mm))

    # ── Total challan highlight box ───────────────────────────────────────────
    tc_tbl = Table(
        [[
            Paragraph("TOTAL AMOUNT TO BE DEPOSITED",
                       _s("tl", font=BOLD, fontSize=11, textColor=WHITE)),
            Paragraph(_inr(total_challan),
                       _s("ta", font=BOLD, fontSize=16, textColor=WHITE,
                          alignment=TA_RIGHT)),
            Paragraph(f"Due by: {due_date}",
                       _s("td", fontSize=8, textColor=colors.HexColor("#fde68a"),
                          alignment=TA_RIGHT)),
        ]],
        colWidths=[TW * 0.45, TW * 0.32, TW * 0.23],
    )
    tc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), EPFO_RED),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tc_tbl)
    story.append(Spacer(1, 6*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. MEMBER-WISE CONTRIBUTION TABLE (page break if many members)
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(_section_bar(f"C.  MEMBER-WISE CONTRIBUTION DETAILS  ({total_members} Members)"))
    story.append(Spacer(1, 2*mm))

    mem_header = [
        "UAN", "Member Name", "EPF\nWages", "EPS\nWages",
        "EPF\nContrib", "EPS\nContrib", "Diff\n(EPF-EPS)", "NCP\nDays",
    ]
    mem_rows = [mem_header]
    for r in results:
        epf_c = r.employee_pf + r.employer_epf
        eps_c = r.employer_eps
        mem_rows.append([
            str(r.uan) if r.uan and r.uan not in ("", "nan") else "—",
            r.name,
            f"{int(r.pf_wages):,}",
            f"{int(r.pf_wages):,}",
            f"{int(epf_c):,}",
            f"{int(eps_c):,}",
            f"{int(epf_c - eps_c):,}",
            str(r.ncp_days),
        ])

    # Footer totals row
    mem_rows.append([
        "TOTAL", "",
        f"{int(total_epf_wages):,}",
        f"{int(total_eps_wages):,}",
        f"{int(total_epf_cont):,}",
        f"{int(total_eps_cont):,}",
        f"{int(total_epf_eps_diff):,}",
        str(total_ncp),
    ])

    UAN_W   = 2.8 * cm
    NAME_W  = 5.0 * cm
    NUM_W   = (TW - UAN_W - NAME_W) / 6

    mem_tbl = Table(mem_rows, colWidths=[UAN_W, NAME_W] + [NUM_W]*6, repeatRows=1)
    mem_tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND",    (0,0), (-1,0),  EPFO_RED),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  BOLD),
        ("FONTSIZE",      (0,0), (-1,0),  7.5),
        ("ALIGN",         (2,0), (-1,0),  "CENTER"),
        # Data
        ("FONTNAME",      (0,1), (-1,-2), BODY),
        ("FONTSIZE",      (0,1), (-1,-2), 7),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [WHITE, EPFO_LGREY]),
        ("ALIGN",         (2,1), (-1,-1), "RIGHT"),
        # Total row
        ("BACKGROUND",    (0,-1), (-1,-1), EPFO_NAVY),
        ("TEXTCOLOR",     (0,-1), (-1,-1), WHITE),
        ("FONTNAME",      (0,-1), (-1,-1), BOLD),
        ("FONTSIZE",      (0,-1), (-1,-1), 7.5),
        # Common
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("LINEBELOW",     (0,0), (-1,0),  1,   EPFO_RED),
        ("LINEBELOW",     (0,1), (-1,-2), 0.25, EPFO_BORDER),
        ("BOX",           (0,0), (-1,-1), 0.8, EPFO_BORDER),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(mem_tbl)
    story.append(Spacer(1, 5*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. INSTRUCTIONS & NEXT STEPS
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(_section_bar("D.  PAYMENT INSTRUCTIONS & NEXT STEPS"))
    story.append(Spacer(1, 2*mm))

    steps = [
        ["Step 1", f"Log in to the EPFO Unified Portal (epfindia.gov.in) and navigate to Establishment → ECR / Return Filing."],
        ["Step 2", f"Search for TRRN: {trrn}. Verify member count ({total_members}) and challan amount ({_inr(total_challan)})."],
        ["Step 3", f"Click 'Pay' and choose your payment mode: Net Banking (SBI / HDFC / ICICI / Axis) or NEFT/RTGS using the generated Challan."],
        ["Step 4", f"Complete payment before the due date ({due_date}). Late payment attracts interest @ 12% p.a. u/s 7Q of the EPF Act."],
        ["Step 5", "After payment confirmation, download the Final Challan Receipt (TRRN Payment Receipt) from the portal for your records."],
        ["Step 6", "File the ECR on the portal using the same TRRN. The ECR is deemed filed only after payment is confirmed."],
    ]

    steps_tbl = Table(steps, colWidths=[2*cm, TW - 2*cm])
    steps_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,-1), BODY),
        ("FONTNAME",      (0,0), ( 0,-1), BOLD),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("TEXTCOLOR",     (0,0), ( 0,-1), EPFO_RED),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, EPFO_LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LINEBELOW",     (0,0), (-1,-2), 0.3, EPFO_BORDER),
        ("BOX",           (0,0), (-1,-1), 0.8, EPFO_BORDER),
    ]))
    story.append(steps_tbl)
    story.append(Spacer(1, 5*mm))

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. PORTAL FOOTER
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width="100%", thickness=1, color=EPFO_RED))
    story.append(Spacer(1, 3*mm))

    footer_rows = [[
        Paragraph(f"TRRN: {trrn}", _s("ft", fontSize=7, textColor=EPFO_NAVY, font=BOLD)),
        Paragraph(f"Generated: {upload_ts}",
                   _s("ft2", fontSize=7, textColor=colors.grey, alignment=TA_CENTER)),
        Paragraph("epfindia.gov.in  ·  Helpdesk: 1800-118-005",
                   _s("ft3", fontSize=7, textColor=colors.grey, alignment=TA_RIGHT)),
    ]]
    ft_tbl = Table(footer_rows, colWidths=[TW/3, TW/3, TW/3])
    ft_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(ft_tbl)
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "DISCLAIMER: This document is a system-generated validation acknowledgement. "
        "It does not constitute proof of payment. The employer must complete challan payment "
        "on the EPFO Unified Portal before the due date to ensure compliance.",
        _s("disc", fontSize=6.5, textColor=colors.grey, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
