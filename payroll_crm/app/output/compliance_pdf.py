import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

STATUS_COLORS = {"pass": colors.green, "partial": colors.orange, "fail": colors.red}


def generate_compliance_pdf(findings: list[dict], client_name: str, month: int, year: int) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Compliance Report — {client_name} — {month:02d}/{year}", styles["Title"]))
    story.append(Spacer(1, 12))

    for f in findings:
        status = f.get("status", "")
        color = STATUS_COLORS.get(status, colors.black)
        story.append(Paragraph(
            f'<font color="{color.hexval()}">[{status.upper()}]</font> '
            f'<b>{f.get("act", "")}</b> — {f.get("section", "")}',
            styles["Heading3"]
        ))
        story.append(Paragraph(f.get("reason", ""), styles["Normal"]))
        if f.get("next_steps"):
            story.append(Paragraph(f"<i>Next steps:</i> {f['next_steps']}", styles["Normal"]))
        story.append(Spacer(1, 8))

    doc.build(story)
    return buf.getvalue()
