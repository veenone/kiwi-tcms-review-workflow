"""PDF renderer for review reports.

Uses reportlab's Platypus layout engine. Produces a document that mirrors
the DOCX renderer's structure so the two formats feel like siblings.
"""
from io import BytesIO


def _fmt_dt(value):
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _fmt_td(td):
    if td is None:
        return "—"
    total_ms = int(td.total_seconds() * 1000)
    if total_ms < 0:
        total_ms = 0
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    seconds, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s {ms:03d}ms"


def _escape_xml(text):
    """Escape minimal XML special chars for reportlab Paragraph flowables."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _review_flowables(review, items, votes, metrics=None):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle  # noqa: WPS433
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: WPS433
    from reportlab.lib import colors  # noqa: WPS433
    from reportlab.lib.units import inch  # noqa: WPS433

    styles = getSampleStyleSheet()
    flowables = []

    flowables.append(Paragraph(
        f"Review #{review['id']} — {_escape_xml(review['title'])}",
        styles["Heading2"],
    ))

    kv_rows = [
        ["State", review["state_display"]],
        ["Requester", review["requester"]],
        ["Reviewers", ", ".join(review.get("reviewers", [])) or "—"],
        ["Created", _fmt_dt(review["created_at"])],
        ["Due date", _fmt_dt(review.get("due_date"))],
        ["Last updated", _fmt_dt(review.get("updated_at"))],
    ]
    kv_table = Table(kv_rows, colWidths=[1.8 * inch, 4.5 * inch])
    kv_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flowables.append(kv_table)
    flowables.append(Spacer(1, 0.1 * inch))

    if review.get("description"):
        flowables.append(Paragraph("<b>Description</b>", styles["Normal"]))
        flowables.append(Paragraph(
            _escape_xml(review["description"]).replace("\n", "<br/>"),
            styles["Normal"],
        ))
        flowables.append(Spacer(1, 0.1 * inch))

    if metrics:
        flowables.append(Paragraph("<b>Metrics</b>", styles["Normal"]))
        votes_breakdown = metrics.get("votes", {})
        metric_rows = [
            ["Approvals", str(votes_breakdown.get("approved", 0))],
            ["Rejections", str(votes_breakdown.get("rejected", 0))],
            ["Changes requested", str(votes_breakdown.get("needs_changes", 0))],
            ["Participation", f"{int(metrics.get('participation', 0) * 100)}%"],
            ["Time to decision", _fmt_td(metrics.get("time_to_decision"))],
        ]
        metric_table = Table(metric_rows, colWidths=[1.8 * inch, 4.5 * inch])
        metric_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        flowables.append(metric_table)
        flowables.append(Spacer(1, 0.1 * inch))

    # Cases
    flowables.append(Paragraph(
        f"<b>Cases under review ({len(items)})</b>", styles["Normal"],
    ))
    if items:
        header = ["#", "Summary", "Decision", "Comment"]
        rows = [header]
        for it in items:
            rows.append([
                str(it["case_id"]),
                _escape_xml(it["summary"])[:60],
                it["decision_display"],
                _escape_xml(it.get("comment") or "—")[:60],
            ])
        case_table = Table(rows, colWidths=[0.5 * inch, 3.2 * inch, 1.2 * inch, 1.4 * inch])
        case_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7e7e7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flowables.append(case_table)
    else:
        flowables.append(Paragraph("<i>No cases attached.</i>", styles["Normal"]))
    flowables.append(Spacer(1, 0.1 * inch))

    # Votes
    flowables.append(Paragraph(
        f"<b>Votes ({len(votes)})</b>", styles["Normal"],
    ))
    if votes:
        header = ["Reviewer", "Decision", "Comment", "Voted at"]
        rows = [header]
        for v in votes:
            rows.append([
                _escape_xml(v["reviewer"]),
                v["decision_display"],
                _escape_xml(v.get("comment") or "—")[:50],
                _fmt_dt(v["voted_at"]),
            ])
        vote_table = Table(rows, colWidths=[1.2 * inch, 1.3 * inch, 2.5 * inch, 1.3 * inch])
        vote_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7e7e7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flowables.append(vote_table)
    else:
        flowables.append(Paragraph("<i>No votes cast yet.</i>", styles["Normal"]))

    flowables.append(Spacer(1, 0.2 * inch))
    return flowables


def _footer_flowables(generated_at):
    from reportlab.platypus import Paragraph, Spacer  # noqa: WPS433
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: WPS433
    from reportlab.lib.units import inch  # noqa: WPS433

    styles = getSampleStyleSheet()
    return [
        Spacer(1, 0.3 * inch),
        Paragraph(
            f"<i>Generated by kiwitcms-review at {_fmt_dt(generated_at)}</i>",
            styles["Normal"],
        ),
    ]


def render_single_review(data):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak  # noqa: WPS433
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: WPS433
    from reportlab.lib.pagesizes import A4  # noqa: WPS433
    from reportlab.lib.units import inch  # noqa: WPS433

    styles = getSampleStyleSheet()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )

    flowables = [
        Paragraph(
            f"Review Request #{data['review']['id']}",
            styles["Title"],
        ),
        Paragraph(
            f"<i>{_escape_xml(data['review']['title'])}</i>",
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
    ]
    flowables += _review_flowables(
        data["review"],
        data["items"],
        data["votes"],
        metrics=data.get("metrics"),
    )
    flowables += _footer_flowables(data["generated_at"])

    doc.build(flowables)
    buf.seek(0)
    return buf


def render_consolidated(data):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle  # noqa: WPS433
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: WPS433
    from reportlab.lib.pagesizes import A4  # noqa: WPS433
    from reportlab.lib import colors  # noqa: WPS433
    from reportlab.lib.units import inch  # noqa: WPS433

    styles = getSampleStyleSheet()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )

    flowables = [
        Paragraph(_escape_xml(data["title"]), styles["Title"]),
    ]
    date_range = data.get("date_range") or {}
    if date_range.get("start") or date_range.get("end"):
        flowables.append(Paragraph(
            f"<i>Date range: {_fmt_dt(date_range.get('start'))} — "
            f"{_fmt_dt(date_range.get('end'))}</i>",
            styles["Normal"],
        ))
    flowables.append(Spacer(1, 0.2 * inch))

    flowables.append(Paragraph("Summary", styles["Heading1"]))
    summary = data.get("summary", {})
    rows = [
        ["Total reviews", str(summary.get("total_reviews", 0))],
        ["Total cases in scope", str(summary.get("total_cases", 0))],
    ]
    for state_label, count in (summary.get("by_state") or {}).items():
        rows.append([f"State — {state_label}", str(count)])
    summary_table = Table(rows, colWidths=[2.5 * inch, 4.0 * inch])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    flowables.append(summary_table)

    flowables.append(PageBreak())
    flowables.append(Paragraph("Reviews", styles["Heading1"]))

    reviews = data.get("reviews", [])
    if not reviews:
        flowables.append(Paragraph(
            "<i>No review requests matched this scope.</i>", styles["Normal"],
        ))
    else:
        for review in reviews:
            flowables += _review_flowables(
                review,
                review.get("items", []),
                review.get("votes", []),
            )
            flowables.append(PageBreak())

    flowables += _footer_flowables(data["generated_at"])
    doc.build(flowables)
    buf.seek(0)
    return buf
