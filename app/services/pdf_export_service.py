"""
Playwright-based PDF rendering service for YouTube prospect audits.

Renders high-fidelity, light-mode, paginated A4 PDFs with exact CSS, gradients,
flexbox/grid layouts, and crisp branding headers and footers.
"""

import html
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Formatting Helpers ────────────────────────────────────────────────────────

def _fmt_num(val: Any) -> str:
    if val is None:
        return "—"
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_compact(val: Any) -> str:
    if val is None:
        return "—"
    try:
        n = float(val)
        if n >= 1_000_000:
            s = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
            return f"{s}M"
        if n >= 1_000:
            s = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
            return f"{s}K"
        return str(int(n))
    except (ValueError, TypeError):
        return str(val)


def _fmt_duration(seconds: Any) -> str:
    if not seconds:
        return "—"
    try:
        sec = float(seconds)
        if sec <= 0:
            return "—"
        mins = sec / 60
        if mins < 1:
            return f"{int(sec)}s"
        if mins >= 60:
            hrs = int(mins // 60)
            rem = int(round(mins % 60))
            return f"{hrs}h {rem}m"
        s = f"{mins:.1f}".rstrip("0").rstrip(".")
        return f"{s} min"
    except (ValueError, TypeError):
        return "—"


def _fmt_date(iso_str: Any) -> str:
    if not iso_str:
        return "—"
    try:
        if isinstance(iso_str, str):
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        elif isinstance(iso_str, datetime):
            dt = iso_str
        else:
            return str(iso_str)
        return dt.strftime("%d %b %Y")
    except Exception:
        return str(iso_str)[:10]


# ── Standalone HTML Template Generator ────────────────────────────────────────

def build_report_html(report: Dict[str, Any]) -> str:
    """Build a standalone, high-contrast, light-mode HTML document for A4 PDF rendering."""
    channel = report.get("channel") or {}
    metrics = report.get("metrics") or {}
    audit = report.get("audit") or {}
    roadmap = report.get("roadmap") or {}
    # One cadence for the whole document, authored in Python. The roadmap dict
    # carries it too, but report["cadence"] is the source both the web view and
    # this export read, so they cannot state it differently.
    _cad = report.get("cadence") or {}
    cadence_label = _cad.get("label") or roadmap.get("cadence") or ""
    publish_days_label = " & ".join(_cad.get("publish_days") or [])
    headline = report.get("headline")
    similar_channels = report.get("similar_channels") or metrics.get("similar_channels") or []
    breakout_videos = metrics.get("breakout_videos") or []
    weeks = roadmap.get("weeks") or []
    # No model name is rendered into the PDF, by design. Which model wrote a
    # report is internal operational detail: a client has no use for it, and
    # printing it invites exactly the comparison ("mine says Gemini, yours says
    # Qwen") that the export gate exists to make unnecessary. The gate already
    # guarantees this document came from a client-grade tier. The dashboard's
    # own internal view still shows the model.
    settings = get_settings()
    brand_name = html.escape(getattr(settings, "report_brand_name", "") or "Growth Intelligence")
    brand_initial = brand_name[0].upper() if brand_name else "G"
    gen_date = _fmt_date(report.get("generated_at") or datetime.utcnow())

    channel_title = html.escape(channel.get("title") or "YouTube Creator")
    channel_handle = html.escape(channel.get("handle") or "")
    thumbnail_url = channel.get("thumbnail_url") or ""
    sub_count = _fmt_compact(channel.get("subscriber_count"))
    view_count = _fmt_compact(channel.get("view_count"))
    video_count = _fmt_compact(metrics.get("video_count_analyzed") or channel.get("video_count"))

    avg_duration = _fmt_duration(
        metrics.get("avg_video_length_seconds") or metrics.get("avg_long_form_length_seconds")
    )
    roadmap_pages = max(1, (len(weeks) + 1) // 2)
    total_pages = 2 + roadmap_pages

    # ── Page Header / Footer helper ──
    def page_header(page_num: int) -> str:
        return f"""
        <div class="header-strip">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div class="logo-box">{brand_initial}</div>
                <div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="brand-title">{brand_name.upper()}</span>
                        <span class="badge-audit">Channel Intelligence Audit</span>
                    </div>
                    <p class="header-sub">Prepared for <strong>{channel_title}</strong> {f"({channel_handle})" if channel_handle else ""}</p>
                </div>
            </div>
            <div style="text-align: right;">
                <div class="page-counter">PAGE {page_num} OF {total_pages}</div>
                <div class="date-stamp">{gen_date}</div>
            </div>
        </div>
        """

    def page_footer(page_num: int) -> str:
        return f"""
        <div class="footer-strip">
            <div>
                <strong style="color: #7c3aed; letter-spacing: 0.5px;">{brand_name.upper()}</strong>
                <span> · Confidential Growth Intelligence Report</span>
            </div>
            <div>
                <span>Prepared for {channel_title} · </span>
                <strong>Page {page_num} of {total_pages}</strong>
            </div>
        </div>
        """

    # ── Section 1 Strategy Bullets ──
    def render_list(title: str, items: List[str], tint_color: str, is_ordered: bool = False) -> str:
        if not items:
            return ""
        lis = []
        for i, it in enumerate(items):
            escaped_it = html.escape(str(it))
            if is_ordered:
                prefix = f'<span style="color: {tint_color}; font-weight: 800; width: 16px; flex-shrink: 0;">{i+1}.</span>'
            else:
                prefix = f'<span style="background: {tint_color}; width: 6px; height: 6px; border-radius: 50%; margin-top: 6px; flex-shrink: 0;"></span>'
            lis.append(f'<li style="display: flex; gap: 8px; font-size: 11px; color: #334155; line-height: 1.45;">{prefix}<span>{escaped_it}</span></li>')
        
        return f"""
        <div class="card" style="padding: 10px 12px; margin-bottom: 8px;">
            <div style="font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: {tint_color}; margin-bottom: 6px;">
                {title}
            </div>
            <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 5px;">
                {"".join(lis)}
            </ul>
        </div>
        """

    # ── Timeframe Analytics Cards ──
    timeframe_html = ""
    tf = metrics.get("timeframe_analytics")
    if tf:
        l7 = tf.get("last_7d") or {}
        l28 = tf.get("last_28d") or {}
        l1y = tf.get("last_1y") or {}
        timeframe_html = f"""
        <div style="margin-bottom: 10px;">
            <div class="section-label" style="color: #2563eb;">📊 Timeframe Analytics</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                <div class="card" style="padding: 8px 10px; background: #f8fafc;">
                    <div style="display: flex; justify-content: space-between; font-size: 9px; font-weight: 800; color: #2563eb; text-transform: uppercase;">
                        <span>Last 7 Days</span>
                        <span style="background: #dbeafe; color: #1e40af; padding: 1px 4px; border-radius: 4px;">Weekly</span>
                    </div>
                    <div style="font-size: 13px; font-weight: 900; color: #0f172a; margin-top: 3px;">+{_fmt_num(l7.get('views'))} views</div>
                    <div style="font-size: 9px; color: #64748b; margin-top: 1px;">{l7.get('uploads', 0)} uploads · {l7.get('est_earnings') or '—'}</div>
                </div>
                <div class="card" style="padding: 8px 10px; background: #f8fafc;">
                    <div style="display: flex; justify-content: space-between; font-size: 9px; font-weight: 800; color: #7c3aed; text-transform: uppercase;">
                        <span>Last 28 Days</span>
                        <span style="background: #ede9fe; color: #5b21b6; padding: 1px 4px; border-radius: 4px;">Monthly</span>
                    </div>
                    <div style="font-size: 13px; font-weight: 900; color: #0f172a; margin-top: 3px;">+{_fmt_num(l28.get('views'))} views</div>
                    <div style="font-size: 9px; color: #64748b; margin-top: 1px;">{l28.get('uploads', 0)} uploads · {l28.get('est_earnings') or '—'}</div>
                </div>
                <div class="card" style="padding: 8px 10px; background: #f8fafc;">
                    <div style="display: flex; justify-content: space-between; font-size: 9px; font-weight: 800; color: #059669; text-transform: uppercase;">
                        <span>Annual (365d)</span>
                        <span style="background: #d1fae5; color: #065f46; padding: 1px 4px; border-radius: 4px;">1 Year</span>
                    </div>
                    <div style="font-size: 13px; font-weight: 900; color: #0f172a; margin-top: 3px;">+{_fmt_num(l1y.get('views'))} views</div>
                    <div style="font-size: 9px; color: #64748b; margin-top: 1px;">{l1y.get('uploads', 0)} uploads · {l1y.get('est_earnings') or '—'}</div>
                </div>
            </div>
        </div>
        """

    # ── Key Highlight Banner ──
    headline_html = ""
    if headline:
        hl_kind = headline.get("kind")
        hl_label = html.escape(str(headline.get("label") or ""))
        hl_val = _fmt_num(headline.get("value"))
        hl_base = _fmt_num(headline.get("baseline"))
        hl_mult = headline.get("multiple")
        hl_sample = headline.get("sample")
        
        # ``value``/``baseline`` are medians on the bucket and keyword paths, so
        # the statistic has to be named — this banner is read next to the length
        # chart, which prints the mean for the same bucket.
        hl_stat = headline.get("value_kind") or "median"
        hl_base_stat = headline.get("baseline_kind") or "median"
        hl_avg = headline.get("avg_value")
        hl_chan_avg = headline.get("channel_avg_views")

        if hl_kind == "cadence":
            text = f"<strong>{headline.get('value')} days</strong> since last upload, following <strong>{hl_base}</strong> in the previous 90."
        else:
            subj = f"{hl_label} videos" if hl_kind == "duration_bucket" else f'Videos about "{hl_label}"'
            text = (
                f"<strong>{subj}</strong>: {hl_stat} of <strong>{hl_val}</strong> views — "
                f"<strong style='color: #065f46;'>{hl_mult}× the {hl_base_stat} of {hl_base}</strong> (n={hl_sample})."
            )
            if hl_avg and hl_chan_avg:
                text += f" Mean {_fmt_num(hl_avg)} vs channel average {_fmt_num(hl_chan_avg)}."
            
        headline_html = f"""
        <div class="highlight-banner">
            <span style="font-size: 14px; margin-right: 6px;">📈</span>
            <span>{text}</span>
        </div>
        """



    # ── Top Breakout Outlier Videos (Page 2) ──
    breakout_vids_html = ""
    if breakout_videos:
        v_cards = []
        for v in breakout_videos[:3]:
            v_id = v.get("video_id")
            v_title = html.escape(v.get("title") or "")
            v_views = _fmt_num(v.get("views"))
            v_mult = v.get("multiplier", 1.0)
            v_dur = _fmt_duration(v.get("duration_seconds"))
            v_cards.append(f"""
            <div class="card" style="padding: 8px; background: #f8fafc;">
                <div style="position: relative; aspect-ratio: 16/9; background: #0f172a; border-radius: 6px; overflow: hidden; margin-bottom: 6px;">
                    <img src="https://i.ytimg.com/vi/{v_id}/hqdefault.jpg" style="width: 100%; height: 100%; object-fit: cover;" />
                    <div style="position: absolute; top: 4px; right: 4px; background: #ea580c; color: #ffffff; font-size: 8px; font-weight: 800; padding: 1px 5px; border-radius: 4px;">{v_mult}× Breakout</div>
                    <div style="position: absolute; bottom: 4px; right: 4px; background: rgba(0,0,0,0.8); color: #ffffff; font-size: 7px; padding: 1px 3px; border-radius: 2px;">{v_dur}</div>
                </div>
                <div style="font-size: 10px; font-weight: 800; color: #0f172a; line-height: 1.3; max-height: 26px; overflow: hidden;">{v_title}</div>
                <div style="display: flex; justify-content: space-between; font-size: 9px; color: #64748b; margin-top: 4px;">
                    <span style="font-weight: bold; color: #c2410c;">{v_views} views</span>
                    <span>{v.get('published_at', '')}</span>
                </div>
            </div>
            """)
        breakout_vids_html = f"""
        <div style="margin-bottom: 10px;">
            <div class="section-label" style="color: #ea580c;">🔥 Top Breakout Outlier Videos</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                {"".join(v_cards)}
            </div>
        </div>
        """

    # ── Upload Timing (Page 2) ──
    timing_html = ""
    ut = metrics.get("upload_timing")
    if ut and ut.get("has_timing_data"):
        bw = ut.get("best_window") or {}
        days = ut.get("days") or []
        bw_label = html.escape(bw.get("combined_label") or "")
        bw_rec = html.escape(bw.get("recommendation") or "")
        # Separate statistics, separate samples. The PDF must not print one
        # number standing for both, and must not print a window at all when the
        # validator dropped it for want of evidence.
        bw_day_mult = bw.get("day_multiplier", 1.0)
        bw_slot_mult = bw.get("slot_multiplier")
        bw_lift = bw.get("day_lift_pct", 0)
        bw_days = " & ".join(bw.get("best_days") or [])
        bw_proof = html.escape(bw.get("top_video_proof") or "")

        day_bars = "".join([
            f"""
            <div style="border: 1px solid {'#f59e0b' if d.get('is_best') else '#e2e8f0'}; background: {'#fef3c7' if d.get('is_best') else '#f8fafc'}; border-radius: 6px; padding: 4px; text-align: center;">
                <div style="font-size: 8px; font-weight: bold; color: #64748b; text-transform: uppercase;">{d.get('day_short')}</div>
                <div style="font-size: 10px; font-weight: 900; color: #0f172a; margin: 2px 0;">{d.get('multiplier')}×</div>
                <div style="font-size: 7px; color: #94a3b8;">n={d.get('video_count')}</div>
            </div>
            """
            for d in days
        ])

        timing_html = f"""
        <div style="margin-bottom: 10px;">
            <div class="section-label" style="color: #d97706;">⏰ Optimal Upload Timing & Peak Velocity</div>
            <div class="card" style="background: #fffbeb; border-color: #fcd34d; padding: 8px 10px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="background: #fde68a; color: #92400e; font-size: 8px; font-weight: 800; padding: 1px 5px; border-radius: 4px; text-transform: uppercase;">Peak Slot</span>
                        <span style="font-size: 11px; font-weight: 800; color: #0f172a;">{bw_label}</span>
                        {f'<span style="font-size: 9px; font-weight: 800; color: #059669;">+{bw_lift}% on {html.escape(bw_days)}</span>' if bw_lift > 0 and bw_days else ''}
                    </div>
                    <div style="font-size: 9px; color: #475569; margin-top: 2px;">{bw_rec}</div>
                    {f'<div style="font-size: 8px; color: #92400e; margin-top: 2px;">{bw_proof}</div>' if bw_proof else ''}
                </div>
                <div style="background: #ffffff; border: 1px solid #fef3c7; border-radius: 6px; padding: 4px 8px; text-align: center; flex-shrink: 0;">
                    <div style="font-size: 7px; font-weight: bold; color: #94a3b8; text-transform: uppercase;">Day · Window</div>
                    <div style="font-size: 13px; font-weight: 900; color: #92400e;">{bw_day_mult}×{f' · {bw_slot_mult}×' if bw_slot_mult else ' · —'}</div>
                    <div style="font-size: 7px; color: #94a3b8;">vs channel median</div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px;">
                {day_bars}
            </div>
        </div>
        """

    # ── Similar Channels (Page 2) ──
    similar_html = ""
    if similar_channels:
        sim_cards = "".join([
            f"""
            <div class="card" style="padding: 6px 8px; display: flex; align-items: center; gap: 6px; background: #ffffff;">
                <div style="width: 24px; height: 24px; border-radius: 50%; background: #ede9fe; color: #6d28d9; font-weight: bold; font-size: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                    {html.escape(c.get('title','C')[:1])}
                </div>
                <div style="overflow: hidden; flex: 1;">
                    <div style="font-size: 10px; font-weight: 800; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{html.escape(c.get('title',''))}</div>
                    <div style="font-size: 8px; color: #64748b;">{_fmt_compact(c.get('subscriber_count'))} subs</div>
                </div>
            </div>
            """
            for c in similar_channels[:4]
        ])
        similar_html = f"""
        <div>
            <div class="section-label" style="color: #7c3aed;">👥 Benchmark Peer Channels</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px;">
                {sim_cards}
            </div>
        </div>
        """

    # ── Roadmap Pages (Pages 3+) ──
    roadmap_pages_html = []
    for p_idx in range(roadmap_pages):
        page_num = 3 + p_idx
        slice_weeks = weeks[p_idx * 2 : p_idx * 2 + 2]
        
        week_blocks = []
        for w in slice_weeks:
            w_num = w.get("week_number", 1)
            w_start = _fmt_date(w.get("start_date"))
            w_focus = html.escape(w.get("focus") or "")
            w_items = w.get("items") or []

            item_lis = []
            for item in w_items:
                i_title = html.escape(item.get("title") or "")
                i_fmt = html.escape(item.get("format") or "Standard")
                i_date = _fmt_date(item.get("date")) if item.get("date") else ""
                i_theme = html.escape(item.get("theme") or "")
                i_rat = html.escape(item.get("rationale") or "")

                item_lis.append(f"""
                <li style="border-left: 2px solid #8b5cf6; padding: 4px 8px; background: #f8fafc; border-radius: 0 6px 6px 0; margin-bottom: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                        <span style="font-size: 11px; font-weight: 800; color: #0f172a; line-height: 1.3;">{i_title}</span>
                        <span style="background: #ede9fe; color: #5b21b6; border: 1px solid #ddd6fe; font-size: 8px; font-weight: bold; padding: 1px 5px; border-radius: 10px; flex-shrink: 0;">{i_fmt}</span>
                    </div>
                    <div style="font-size: 9px; color: #64748b; margin-top: 2px;">
                        {f'<span>📅 {i_date}</span>' if i_date else ''}
                        {f' · <span>Theme: <strong>{i_theme}</strong></span>' if i_theme else ''}
                    </div>
                    {f'<div style="font-size: 9px; color: #475569; margin-top: 2px; line-height: 1.35;">{i_rat}</div>' if i_rat else ''}
                </li>
                """)

            week_blocks.append(f"""
            <div class="card" style="padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="background: #ede9fe; color: #6d28d9; font-size: 10px; font-weight: 900; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">Week {w_num}</span>
                        <span style="font-size: 11px; font-weight: 800; color: #0f172a;">{w_focus}</span>
                    </div>
                    <div style="font-size: 10px; color: #64748b;">📅 Start: <strong>{w_start}</strong></div>
                </div>
                <ul style="list-style: none; padding: 0; margin: 0;">
                    {"".join(item_lis)}
                </ul>
            </div>
            """)

        cta_block = ""
        if page_num == total_pages:
            cta_block = f"""
            <div class="card" style="background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%); border-color: #ddd6fe; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; margin-top: auto;">
                <div>
                    <div style="font-size: 11px; font-weight: 900; color: #4c1d95;">✨ Ready to Put this Content Engine to Work?</div>
                    <div style="font-size: 9px; color: #6d28d9; margin-top: 1px;">{brand_name} automates research, script generation, and publication tracking.</div>
                </div>
                <div style="font-size: 11px; font-weight: 900; color: #6d28d9; letter-spacing: 0.5px;">{brand_name.upper()}</div>
            </div>
            """

        roadmap_pages_html.append(f"""
        <div class="page page-break">
            {page_header(page_num)}
            <div class="page-content">
                <div class="card" style="background: #fdf4ff; border-color: #f5d0fe; padding: 10px 12px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 12px; font-weight: 900; color: #701a75;">🗺️ 30-Day Content Roadmap {f'(Part {p_idx+1})' if roadmap_pages > 1 else ''}</div>
                        <div style="font-size: 9px; color: #86198f; margin-top: 2px;">Strategic video concepts and release schedule tuned for maximum audience retention.</div>
                    </div>
                    {f'<div style="background:#ffffff; border:1px solid #f5d0fe; border-radius:6px; padding:3px 8px; font-size:9px; font-weight:bold; color:#701a75;">Cadence: {html.escape(cadence_label)}{f" &middot; {html.escape(publish_days_label)}" if publish_days_label else ""}</div>' if cadence_label else ''}
                </div>
                {"".join(week_blocks)}
                {cta_block}
            </div>
            {page_footer(page_num)}
        </div>
        """)

    # ── Final Assembled HTML Document ──
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{brand_name} - Channel Intelligence Audit - {channel_title}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 0;
        }}
        * {{
            box-sizing: border-box;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #ffffff;
            color: #0f172a;
            margin: 0;
            padding: 0;
            font-size: 11px;
            line-height: 1.4;
        }}
        .page {{
            width: 210mm;
            min-height: 297mm;
            padding: 12mm 14mm;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background-color: #ffffff;
            position: relative;
        }}
        .page-break {{
            page-break-before: always;
            break-before: page;
        }}
        .page-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
        }}
        .header-strip {{
            border-bottom: 2px solid #c4b5fd;
            padding-bottom: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .logo-box {{
            width: 28px;
            height: 28px;
            border-radius: 6px;
            background: linear-gradient(135deg, #7c3aed, #4f46e5);
            color: #ffffff;
            font-weight: 900;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .brand-title {{
            font-size: 11px;
            font-weight: 900;
            letter-spacing: 0.8px;
            color: #4c1d95;
        }}
        .badge-audit {{
            font-size: 9px;
            font-weight: 700;
            background: #ede9fe;
            color: #6d28d9;
            padding: 1px 6px;
            border-radius: 10px;
            border: 1px solid #ddd6fe;
        }}
        .header-sub {{
            font-size: 10px;
            color: #64748b;
            margin: 2px 0 0 0;
        }}
        .page-counter {{
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: #64748b;
        }}
        .date-stamp {{
            font-size: 9px;
            color: #94a3b8;
            margin-top: 1px;
        }}
        .footer-strip {{
            border-top: 1px solid #e2e8f0;
            padding-top: 6px;
            margin-top: auto;
            display: flex;
            justify-content: space-between;
            font-size: 9px;
            color: #64748b;
        }}
        .card {{
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #ffffff;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }}
        .stat-box {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        .stat-label {{
            font-size: 8px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            color: #64748b;
        }}
        .stat-value {{
            font-size: 14px;
            font-weight: 900;
            color: #0f172a;
            margin-top: 1px;
        }}
        .stat-hint {{
            font-size: 8px;
            color: #94a3b8;
            margin-top: 1px;
        }}
        .section-label {{
            font-size: 9px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .highlight-banner {{
            border: 1px solid #a7f3d0;
            background: #ecfdf5;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 10px;
            color: #064e3b;
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }}
        .pill {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 6px;
            border-radius: 5px;
            background: #ffffff;
            border: 1px solid #fde68a;
            font-size: 9px;
        }}
    </style>
</head>
<body>
    <!-- ──────────────────────────────────────────────────────────── -->
    <!-- PAGE 1: Channel Overview + Core Benchmarks + Strategy Audit -->
    <!-- ──────────────────────────────────────────────────────────── -->
    <div class="page">
        {page_header(1)}
        <div class="page-content">
            <!-- Channel Header & Vitals -->
            <div class="card" style="padding: 10px 12px; background: #f8fafc; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 8px;">
                    <div>
                        <div style="font-size: 14px; font-weight: 900; color: #0f172a;">{channel_title}</div>
                        <div style="font-size: 10px; color: #64748b; margin-top: 1px;">
                            {channel_handle} · {sub_count} subscribers · {view_count} views · {video_count} uploads
                        </div>
                    </div>
                    <span class="badge-audit" style="background: #ede9fe; color: #6d28d9; border-color: #ddd6fe; font-weight: 800;">
                        ✨ Full Growth Audit
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; text-align: center;">
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 6px;">
                        <div class="stat-label">Avg Length</div>
                        <div style="font-size: 11px; font-weight: 900; color: #2563eb;">{avg_duration}</div>
                    </div>
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 6px;">
                        <div class="stat-label">Upload Cadence</div>
                        <div style="font-size: 11px; font-weight: 900; color: #7c3aed;">{metrics.get('upload_frequency') or '—'}</div>
                    </div>
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 6px;">
                        <div class="stat-label">Est. Monthly</div>
                        <div style="font-size: 11px; font-weight: 900; color: #059669;">{metrics.get('est_monthly_earnings') or '—'}</div>
                    </div>
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 6px;">
                        <div class="stat-label">30d Velocity</div>
                        <div style="font-size: 11px; font-weight: 900; color: #0f172a;">{_fmt_compact(metrics.get('est_monthly_views') or metrics.get('views_last_30d'))}/mo</div>
                    </div>
                </div>
            </div>

            <!-- Core Benchmarks -->
            <div style="margin-bottom: 10px;">
                <div class="section-label" style="color: #7c3aed;">⚡ Core Channel Benchmarks</div>
                <div class="stat-grid">
                    <div class="stat-box">
                        <div class="stat-label">Average Views</div>
                        <div class="stat-value" style="color: #4c1d95;">{_fmt_num(metrics.get('avg_views'))}</div>
                        <div class="stat-hint">across {metrics.get('video_count_analyzed', 0)} videos</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Median Views</div>
                        <div class="stat-value">{_fmt_num(metrics.get('median_views'))}</div>
                        <div class="stat-hint">typical upload baseline</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Engagement</div>
                        <div class="stat-value" style="color: #059669;">{metrics.get('engagement_rate', 'n/a')}%</div>
                        <div class="stat-hint">likes + comments / views</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Upload Pace</div>
                        <div class="stat-value">{metrics.get('uploads_last_30', 0)} in 30d</div>
                        <div class="stat-hint">{metrics.get('days_since_upload', 0)}d since last upload</div>
                    </div>
                </div>
            </div>

            {headline_html}
            {timeframe_html}

            <!-- AI Strategy Analysis 2x2 Grid -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                {render_list("What's Working", audit.get("whats_working", []), "#059669")}
                {render_list("Underperforming Formats", audit.get("underperforming", []), "#dc2626")}
                {render_list("Format & Cadence", audit.get("format_insights", []), "#2563eb")}
                {render_list("Identified Content Gaps", audit.get("content_gaps", []), "#d97706")}
            </div>

            <!-- Priority Actions -->
            {render_list("Strategic Priorities & Action Plan", audit.get("priorities", []), "#7c3aed", is_ordered=True)}
        </div>
        {page_footer(1)}
    </div>

    <!-- ──────────────────────────────────────────────────────────── -->
    <!-- PAGE 2: Breakout Videos, Timing & Topic Intelligence         -->
    <!-- ──────────────────────────────────────────────────────────── -->
    <div class="page page-break">
        {page_header(2)}
        <div class="page-content">
            {breakout_vids_html}
            {timing_html}
            {similar_html}
        </div>
        {page_footer(2)}
    </div>

    <!-- ──────────────────────────────────────────────────────────── -->
    <!-- PAGES 3+: 30-Day Content Roadmap (2 Weeks per Page)          -->
    <!-- ──────────────────────────────────────────────────────────── -->
    {"".join(roadmap_pages_html)}
</body>
</html>
"""


# ── PDF Render Executor ───────────────────────────────────────────────────────

async def generate_prospect_pdf(report: Dict[str, Any]) -> bytes:
    """Render a prospect report dict to A4 PDF bytes using headless Playwright Chromium."""
    html_content = build_report_html(report)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        try:
            page = await browser.new_page(
                viewport={"width": 1200, "height": 1600},
                device_scale_factor=2,
            )
            # Set HTML content and wait for images / web fonts
            await page.set_content(html_content, wait_until="networkidle")
            await page.emulate_media(media="print")

            # Generate exact A4 PDF
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
            )
            return pdf_bytes
        finally:
            await browser.close()
