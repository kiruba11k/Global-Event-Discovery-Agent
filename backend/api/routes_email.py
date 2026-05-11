"""
Email Report — POST /api/email-report
Flow:
  1. Frontend sends events + company context in request body
  2. Backend generates PDF from HTML template (in memory only)
  3. Backend sends PDF as attachment via Resend
  4. PDF bytes go out of scope → garbage collected
  5. Nothing written to disk. No S3, no R2, no Render disk.

Dependencies:
  pip install weasyprint resend
  apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0
  (see render.yaml buildCommand)
"""
import base64
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from config import get_settings
from loguru import logger

router   = APIRouter()
settings = get_settings()

# ── Pydantic models ────────────────────────────────────────

class EventForReport(BaseModel):
    event_name:    str
    date:          str = ""
    place:         str = ""
    event_link:    str = ""
    what_its_about:str = ""
    key_numbers:   str = ""
    industry:      str = ""
    buyer_persona: str = ""
    pricing:       str = ""
    fit_verdict:   str = "CONSIDER"
    verdict_notes: str = ""
    est_attendees: int = 0
    relevance_score: float = 0.0


class ProfileSummary(BaseModel):
    company_name:        str = ""
    company_description: str = ""
    target_industries:   List[str] = []
    target_personas:     List[str] = []
    target_geographies:  List[str] = []
    deal_size_category:  str = ""
    date_from:           Optional[str] = None
    date_to:             Optional[str] = None


class EmailReportRequest(BaseModel):
    email:           str
    events:          List[EventForReport]
    profile:         ProfileSummary
    deal_size_category: str = "medium"


# ── Pricing matrix (same as frontend) ─────────────────────

PRICING_MATRIX = {
    "low":        {5: 2.25, 10: 3.75, 15: 5.00, 20: 6.50},
    "medium":     {5: 2.75, 10: 4.50, 15: 6.00, 20: 7.75},
    "high":       {5: 3.25, 10: 5.25, 15: 7.00, 20: 9.00},
    "enterprise": {5: 3.75, 10: 6.00, 15: 8.00, 20: 10.50},
}

DEAL_LABELS = {
    "low": "Low (< $10K)",
    "medium": "Medium ($10K–$25K)",
    "high": "High ($25K–$75K)",
    "enterprise": "Enterprise (> $75K)",
}


def _get_packages(attendees: int) -> list:
    if attendees >= 5000: return [5, 10, 15, 20]
    if attendees >= 3000: return [5, 10, 15]
    if attendees >= 1000: return [5, 10]
    if attendees > 0:     return [5]
    return []


def _verdict_color(verdict: str) -> str:
    return {"GO": "#10b981", "CONSIDER": "#f59e0b", "SKIP": "#f43f5e"}.get(verdict, "#6b7280")


def _verdict_bg(verdict: str) -> str:
    return {"GO": "#f0fdf4", "CONSIDER": "#fffbeb", "SKIP": "#fff1f2"}.get(verdict, "#f9fafb")


# ── HTML → PDF template ────────────────────────────────────

def _build_html(request: EmailReportRequest) -> str:
    p          = request.profile
    events     = request.events
    deal_cat   = request.deal_size_category or "medium"
    prices     = PRICING_MATRIX.get(deal_cat, PRICING_MATRIX["medium"])
    deal_label = DEAL_LABELS.get(deal_cat, "Medium")
    go_events  = [e for e in events if e.fit_verdict == "GO"]
    con_events = [e for e in events if e.fit_verdict == "CONSIDER"]
    gen_date   = datetime.utcnow().strftime("%d %B %Y")

    def event_cards(ev_list: List[EventForReport]) -> str:
        if not ev_list:
            return "<p style='color:#6b7280;font-size:13px;'>No events in this category.</p>"
        cards = []
        for ev in ev_list:
            color   = _verdict_color(ev.fit_verdict)
            bg      = _verdict_bg(ev.fit_verdict)
            pkgs    = _get_packages(ev.est_attendees)
            pkg_rows = ""
            for m in pkgs:
                pkg_rows += f"""
                <tr>
                  <td style="padding:5px 10px;font-size:12px;color:#374151;">{m} meetings</td>
                  <td style="padding:5px 10px;font-size:12px;font-weight:700;color:#3b82f6;">₹{prices.get(m, "—")}L</td>
                </tr>"""

            pricing_section = ""
            if pkg_rows:
                pricing_section = f"""
                <div style="margin-top:12px;">
                  <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">
                    LeadStrategus Meeting Packages ({deal_label})
                  </div>
                  <table style="border-collapse:collapse;width:100%;background:#f8faff;border-radius:6px;overflow:hidden;">
                    <tr style="background:#eff6ff;">
                      <th style="padding:5px 10px;font-size:10px;color:#6b7280;text-align:left;font-weight:700;">Package</th>
                      <th style="padding:5px 10px;font-size:10px;color:#6b7280;text-align:left;font-weight:700;">Investment</th>
                    </tr>
                    {pkg_rows}
                  </table>
                </div>"""

            cards.append(f"""
            <div style="background:{bg};border:1.5px solid {color}30;border-radius:10px;padding:18px 20px;margin-bottom:16px;break-inside:avoid;">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px;">
                <div>
                  <div style="font-size:15px;font-weight:700;color:#0f172a;">{ev.event_name}</div>
                  <div style="font-size:11px;color:#6b7280;margin-top:3px;">{ev.date} &nbsp;·&nbsp; {ev.place}</div>
                </div>
                <span style="background:{color};color:#fff;font-size:10px;font-weight:800;padding:3px 10px;border-radius:100px;letter-spacing:0.06em;white-space:nowrap;margin-left:12px;">
                  {ev.fit_verdict}
                </span>
              </div>
              {'<div style="font-size:12px;color:#374151;line-height:1.6;margin-bottom:8px;">' + ev.what_its_about[:200] + '</div>' if ev.what_its_about else ''}
              {'<div style="font-size:11px;color:#06b6d4;font-weight:600;margin-bottom:6px;">📊 ' + ev.key_numbers + '</div>' if ev.key_numbers else ''}
              <div style="background:#fff8;border-radius:6px;padding:10px 14px;font-size:11px;color:#374151;line-height:1.65;font-style:italic;margin-bottom:8px;">
                "{ev.verdict_notes}"
              </div>
              <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#6b7280;">
                {'<span>🏭 ' + ev.industry[:50] + '</span>' if ev.industry else ''}
                {'<span>🎟 ' + ev.pricing + '</span>' if ev.pricing else ''}
                {'<span>🔗 <a href="' + ev.event_link + '" style="color:#3b82f6;">' + ev.event_link[:50] + '…</a></span>' if ev.event_link else ''}
              </div>
              {pricing_section}
            </div>""")
        return "".join(cards)

    industries_str  = ", ".join(p.target_industries[:5]) if p.target_industries else "—"
    personas_str    = ", ".join(p.target_personas[:5])   if p.target_personas   else "—"
    geographies_str = ", ".join(p.target_geographies)    if p.target_geographies else "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', Helvetica, Arial, sans-serif; color: #0f172a; background: #fff; }}

    /* Cover header */
    .header {{
      background: linear-gradient(135deg, #0369a1 0%, #06b6d4 50%, #3b82f6 100%);
      padding: 40px 48px; color: white;
    }}
    .header-logo {{ font-size: 13px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.85; margin-bottom: 20px; }}
    .header-title {{ font-size: 28px; font-weight: 800; line-height: 1.2; margin-bottom: 8px; }}
    .header-subtitle {{ font-size: 13px; opacity: 0.8; }}
    .header-meta {{ display: flex; gap: 24px; margin-top: 20px; flex-wrap: wrap; }}
    .header-meta-item {{ font-size: 11px; opacity: 0.75; }}
    .header-meta-item strong {{ display: block; font-size: 13px; opacity: 1; font-weight: 700; margin-top: 2px; }}

    /* Body */
    .body {{ padding: 32px 48px; }}

    /* ICP Summary */
    .icp-box {{
      background: #f8faff; border: 1px solid #dce6f3;
      border-radius: 10px; padding: 18px 22px; margin-bottom: 28px;
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;
    }}
    .icp-item-label {{ font-size: 9px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.08em; }}
    .icp-item-value {{ font-size: 12px; color: #1e293b; margin-top: 3px; font-weight: 500; }}

    /* Section headings */
    .section-heading {{
      font-size: 16px; font-weight: 800; color: #0f172a;
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 14px; padding-bottom: 8px;
      border-bottom: 2px solid #e2eaf4;
    }}
    .verdict-dot-go      {{ width:10px;height:10px;border-radius:50%;background:#10b981;flex-shrink:0; }}
    .verdict-dot-consider{{ width:10px;height:10px;border-radius:50%;background:#f59e0b;flex-shrink:0; }}

    /* Cashback */
    .cashback-box {{
      background: #f0fdf4; border: 1.5px solid #86efac;
      border-radius: 8px; padding: 12px 18px;
      font-size: 12px; color: #166534; font-weight: 600;
      margin: 20px 0; display: flex; align-items: center; gap: 10px;
    }}

    /* Disclaimer */
    .disclaimer {{
      background: #f8fafc; border: 1px solid #e2eaf4;
      border-radius: 8px; padding: 14px 18px;
      font-size: 10px; color: #6b7280; line-height: 1.6;
      margin-top: 28px;
    }}

    /* Footer */
    .footer {{
      background: #0f172a; color: #94a3b8;
      padding: 20px 48px; font-size: 10px;
      display: flex; justify-content: space-between; align-items: center;
    }}
    .footer strong {{ color: #f1f5f9; }}

    /* Page break */
    .page-break {{ page-break-before: always; }}

    @media print {{
      .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    }}
  </style>
</head>
<body>

<!-- ══════════ COVER HEADER ══════════ -->
<div class="header">
  <div class="header-logo">⚡ LeadStrategus · Event Intelligence</div>
  <div class="header-title">Event Strategy Report<br/>{p.company_name or "Your Company"}</div>
  <div class="header-subtitle">AI-ranked event recommendations matched to your ICP</div>
  <div class="header-meta">
    <div class="header-meta-item">
      Generated
      <strong>{gen_date}</strong>
    </div>
    <div class="header-meta-item">
      Total Events Ranked
      <strong>{len(events)}</strong>
    </div>
    <div class="header-meta-item">
      Strong Matches (GO)
      <strong>{len(go_events)}</strong>
    </div>
    <div class="header-meta-item">
      Deal Size Category
      <strong>{deal_label}</strong>
    </div>
  </div>
</div>

<!-- ══════════ BODY ══════════ -->
<div class="body">

  <!-- ICP Summary -->
  <div class="icp-box">
    <div>
      <div class="icp-item-label">Company</div>
      <div class="icp-item-value">{p.company_name or "—"}</div>
    </div>
    <div>
      <div class="icp-item-label">Target Industries</div>
      <div class="icp-item-value">{industries_str}</div>
    </div>
    <div>
      <div class="icp-item-label">Target Personas</div>
      <div class="icp-item-value">{personas_str}</div>
    </div>
    <div>
      <div class="icp-item-label">Geographies</div>
      <div class="icp-item-value">{geographies_str}</div>
    </div>
    <div>
      <div class="icp-item-label">Date Range</div>
      <div class="icp-item-value">{p.date_from or "Any"} → {p.date_to or "Any"}</div>
    </div>
    <div>
      <div class="icp-item-label">Deal Size</div>
      <div class="icp-item-value">{deal_label}</div>
    </div>
  </div>

  <!-- Cashback guarantee -->
  <div class="cashback-box">
    🛡 LeadStrategus Cashback Guarantee — If we don't deliver the promised meetings at any event below, you receive a full cashback. No questions asked.
  </div>

  <!-- GO Events -->
  <div class="section-heading">
    <div class="verdict-dot-go"></div>
    GO — Strong Matches ({len(go_events)} events)
  </div>
  {event_cards(go_events)}

  <!-- CONSIDER Events -->
  <div style="margin-top:32px;">
    <div class="section-heading">
      <div class="verdict-dot-consider"></div>
      CONSIDER — Worth Evaluating ({len(con_events)} events)
    </div>
    {event_cards(con_events)}
  </div>

  <!-- Disclaimer -->
  <div class="disclaimer">
    <strong>Disclaimer:</strong> This report was generated by LeadStrategus Event Intelligence on {gen_date}.
    Event details are sourced from public directories and APIs; always verify dates, locations, and pricing
    on the official event website before registering. Meeting package pricing shown is indicative and based
    on the LeadStrategus internal pricing matrix v1 ({deal_label} deal size category).
    Actual engagement fees may vary. Pipeline estimates assume a 40% qualification rate and 25% close rate
    on your stated deal size. Please request a formal quote at <strong>leadstrategus.com/contact</strong>
    for firm pricing and SLA terms. LeadStrategus is not affiliated with any of the events listed.
  </div>

</div><!-- /body -->

<!-- ══════════ FOOTER ══════════ -->
<div class="footer">
  <span>© {datetime.utcnow().year} <strong>LeadStrategus</strong> · Event Intelligence · leadstrategus.com</span>
  <span>Confidential — prepared for <strong>{p.company_name or "your company"}</strong></span>
</div>

</body>
</html>"""


# ── Generate PDF bytes in memory ───────────────────────────

def _generate_pdf(html: str) -> bytes:
    """
    Convert HTML → PDF in memory using WeasyPrint.
    Falls back to fpdf2 if WeasyPrint system libraries are unavailable.
    Nothing is written to disk.
    """
    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html).write_pdf()
        logger.info(f"PDF generated via WeasyPrint: {len(pdf_bytes):,} bytes")
        return pdf_bytes
    except Exception as e:
        logger.warning(f"WeasyPrint failed ({e}) — falling back to fpdf2")
        return _generate_pdf_fpdf(html)


def _generate_pdf_fpdf(html: str) -> bytes:
    """
    Pure-Python fallback: generate a simpler PDF using fpdf2.
    No system dependencies needed — always works on Render free tier.
    """
    from fpdf import FPDF
    from html import unescape
    import re

    # Strip HTML tags for plain text rendering
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "LeadStrategus — Event Intelligence Report", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean[:8000])

    return bytes(pdf.output())


# ── Send via Resend ────────────────────────────────────────

def _send_email(to: str, pdf_bytes: bytes, company_name: str) -> None:
    try:
        import resend  # pip install resend
        resend.api_key = settings.resend_api_key
        if not resend.api_key:
            raise ValueError("RESEND_API_KEY not configured in .env")

        from_addr = settings.resend_from_email or "reports@leadstrategus.com"
        subject   = f"LeadStrategus Event Intelligence Report — {company_name or 'Your Company'}"

        # Encode PDF as base64 for attachment
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        params = {
            "from":    from_addr,
            "to":      [to],
            "subject": subject,
            "html": f"""
<p>Hi there,</p>
<p>Please find attached your <strong>LeadStrategus Event Intelligence Report</strong>
for <strong>{company_name or 'your company'}</strong>.</p>
<p>The report includes AI-ranked event recommendations, meeting package pricing,
and pipeline projections based on your ICP.</p>
<p>
  <a href="https://leadstrategus.com/contact/" style="
    display:inline-block;background:linear-gradient(135deg,#06b6d4,#3b82f6);
    color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">
    Schedule a Strategy Call →
  </a>
</p>
<p style="font-size:12px;color:#6b7280;">
  LeadStrategus · Event Intelligence<br/>
  <a href="https://leadstrategus.com">leadstrategus.com</a>
</p>""",
            "attachments": [{
                "filename": f"LeadStrategus-Event-Report-{company_name or 'report'}.pdf".replace(" ", "-"),
                "content":  pdf_b64,
            }],
        }
        resend.Emails.send(params)
        logger.info(f"Email sent to {to} via Resend ({len(pdf_bytes):,} byte PDF).")
        # pdf_bytes goes out of scope immediately — GC'd, never written to disk

    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        raise


# ── FastAPI route ──────────────────────────────────────────

@router.post("/email-report")
async def email_report(request: EmailReportRequest):
    """
    Generate a PDF report in memory and email it via Resend.
    The PDF is never written to disk, S3, R2, or any storage.
    """
    if not request.email or "@" not in request.email:
        raise HTTPException(status_code=422, detail="Invalid email address.")

    if not request.events:
        raise HTTPException(status_code=400, detail="No events provided for the report.")

    if not settings.resend_api_key:
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Add RESEND_API_KEY to your environment."
        )

    try:
        # 1. Build HTML in memory
        html = _build_html(request)

        # 2. Convert to PDF in memory (WeasyPrint → fpdf2 fallback)
        pdf_bytes = _generate_pdf(html)

        # 3. Send via Resend — pdf_bytes freed immediately after
        company_name = request.profile.company_name or "your company"
        _send_email(request.email, pdf_bytes, company_name)

        # 4. pdf_bytes goes out of scope here — no storage, no disk write
        del pdf_bytes

        return {
            "success": True,
            "message": f"Report sent to {request.email}. Check your inbox.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email report error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send report: {str(e)}")
