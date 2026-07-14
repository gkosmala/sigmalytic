from __future__ import annotations

import html
import json
import math
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


BACKEND = os.getenv("SIGMALYTIC_BACKEND_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
ENDPOINT = "/api/campaigns/read-only/full-universe-enriched-campaign-table?limit=100"

REPORT_TITLE = "Sigmalytic Quant Corporation - Nightly Intelligence Report"
REPORT_SUBTITLE = "V2 Campaign Intelligence - 100-row, 7-year formal ODS subscriber edition"
COPYRIGHT = "Copyright © 2026 Sigmalytic Quant Corporation. All rights reserved. Confidential and proprietary."

MARKER = "SIGMALYTIC_STEP91B_FULL_UNIVERSE_NIGHTLY_REPORT_GENERATOR"
MARKDOWN_QUALITY_MARKER = "SIGMALYTIC_STEP91D_MARKDOWN_QUALITY_REPAIR"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def fmt(value: Any, digits: int = 2) -> str:
    x = safe_float(value)
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def esc(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return html.escape(", ".join(str(x) for x in value))
    return html.escape(str(value))


def fetch_json(url: str, timeout: int = 900) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-Step91B-Nightly-Report-Generator",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def score(row: Dict[str, Any]) -> float:
    for key in ("ods_score", "score", "composite_score", "cohort_match_count"):
        x = safe_float(row.get(key))
        if x is not None:
            return x
    return -1.0


def row_symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper()


def is_bullish(row: Dict[str, Any]) -> bool:
    return str(row.get("bias") or row.get("watch_bias") or "").upper() == "BULLISH"


def missing_components(row: Dict[str, Any]) -> List[str]:
    raw = row.get("ods_missing_components")
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if raw:
        return [str(raw)]
    return []


def component_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        for item in missing_components(row):
            counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def top_rows(rows: List[Dict[str, Any]], n: int = 20) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: (score(r), safe_float(r.get("cohort_match_count")) or 0), reverse=True)[:n]


def table_html(rows: List[Dict[str, Any]], title: str, note: str = "", limit: int = 25) -> str:
    shown = rows[:limit]
    if not shown:
        return f"""
        <section class="section">
          <h2>{esc(title)}</h2>
          <p class="muted">No rows met this section's criteria in tonight's review.</p>
        </section>
        """

    body = []
    for row in shown:
        body.append(f"""
        <tr>
          <td><strong>{esc(row_symbol(row))}</strong></td>
          <td>{esc(row.get("state") or row.get("status"))}</td>
          <td>{esc(row.get("bias") or row.get("watch_bias"))}</td>
          <td>{esc(row.get("ods_status"))}</td>
          <td>{esc(row.get("ods_label"))}</td>
          <td class="num">{fmt(row.get("ods_score"), 0)}</td>
          <td>{esc(row.get("lifecycle_maturity"))}</td>
          <td>{esc(row.get("cohort_status"))}</td>
          <td class="num">{fmt(row.get("expected_return_pct"), 2)}</td>
          <td class="num">{fmt(row.get("target_1_price"), 2)}</td>
          <td class="num">{fmt(row.get("failure_price"), 2)}</td>
          <td>{esc(missing_components(row))}</td>
        </tr>
        """)

    return f"""
    <section class="section">
      <h2>{esc(title)}</h2>
      {f'<p class="note">{esc(note)}</p>' if note else ''}
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>State</th>
            <th>Bias</th>
            <th>ODS</th>
            <th>ODS Label</th>
            <th>ODS Score</th>
            <th>Lifecycle</th>
            <th>Cohort</th>
            <th>Exp. Ret.</th>
            <th>Target 1</th>
            <th>Failure</th>
            <th>Missing ODS Evidence</th>
          </tr>
        </thead>
        <tbody>
          {''.join(body)}
        </tbody>
      </table>
    </section>
    """


def card_grid(rows: List[Dict[str, Any]], title: str, note: str = "", limit: int = 12) -> str:
    shown = rows[:limit]
    if not shown:
        return f"""
        <section class="section">
          <h2>{esc(title)}</h2>
          <p class="muted">No names met this section's criteria in tonight's review.</p>
        </section>
        """

    cards = []
    for row in shown:
        symbol = row_symbol(row)
        missing = missing_components(row)
        cards.append(f"""
        <div class="card">
          <div class="card-title">{esc(symbol)} <span>{esc(row.get("bias") or "WATCH")}</span></div>
          <div class="card-line">State: <strong>{esc(row.get("state") or row.get("status"))}</strong></div>
          <div class="card-line">ODS: <strong>{esc(row.get("ods_status"))}</strong> | Score: <strong>{fmt(row.get("ods_score"), 0)}</strong></div>
          <div class="card-line">Lifecycle: <strong>{esc(row.get("lifecycle_maturity"))}</strong> | Cohort: <strong>{esc(row.get("cohort_status"))}</strong></div>
          <p>{esc(symbol)} is included because the full-universe 7-year campaign review surfaced it within the current ranked campaign universe. Missing ODS evidence: {esc(missing) if missing else "none recorded"}.</p>
        </div>
        """)

    return f"""
    <section class="section">
      <h2>{esc(title)}</h2>
      {f'<p class="note">{esc(note)}</p>' if note else ''}
      <div class="grid">
        {''.join(cards)}
      </div>
    </section>
    """


def markdown_table(rows: List[Dict[str, Any]], title: str, limit: int = 25) -> str:
    lines = [f"## {title}", ""]
    if not rows:
        lines += ["No rows met this section's criteria in tonight's review.", ""]
        return "\n".join(lines)

    lines.append("| Symbol | State | Bias | ODS | ODS Score | Lifecycle | Cohort | Expected Return | Missing ODS Evidence |")
    lines.append("|---|---|---|---|---:|---|---|---:|---|")
    for row in rows[:limit]:
        lines.append(
            f"| {row_symbol(row)} | {row.get('state') or row.get('status') or ''} | {row.get('bias') or row.get('watch_bias') or ''} | "
            f"{row.get('ods_status') or ''} | {fmt(row.get('ods_score'), 0)} | {row.get('lifecycle_maturity') or ''} | "
            f"{row.get('cohort_status') or ''} | {fmt(row.get('expected_return_pct'), 2)} | {', '.join(missing_components(row))} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_pdf_with_edge(html_path: pathlib.Path, pdf_path: pathlib.Path) -> Dict[str, Any]:
    candidates = [
        os.environ.get("EDGE_EXE"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    exe = None
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).exists():
            exe = candidate
            break

    if not exe:
        return {"ok": False, "error": "No Edge/Chrome executable found for headless PDF export."}

    file_url = html_path.resolve().as_uri()
    args = [
        exe,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={str(pdf_path.resolve())}",
        file_url,
    ]

    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
    ok = pdf_path.exists() and pdf_path.stat().st_size > 1000
    return {
        "ok": ok,
        "exe": exe,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
        "pdf_path": str(pdf_path),
        "pdf_size": pdf_path.stat().st_size if pdf_path.exists() else 0,
    }


def main() -> int:
    start = time.time()
    now = utc_now()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    report_dir = pathlib.Path("daily_reports") / f"Sigmalytic_Nightly_Intelligence_Report_Full_Universe_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    url = f"{BACKEND}{ENDPOINT}"
    payload = fetch_json(url, timeout=900)
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        raise RuntimeError("live enriched campaign endpoint did not return rows list")

    rows = [r for r in rows if isinstance(r, dict)]
    market = payload.get("market_data_status") or {}

    confirmed = [r for r in rows if r.get("ods_status") == "CONFIRMED"]
    pending = [r for r in rows if r.get("ods_status") == "PENDING"]
    not_confirmed = [r for r in rows if r.get("ods_status") == "NOT_CONFIRMED"]
    long_watch = [r for r in rows if is_bullish(r)]
    neutral_watch = [r for r in rows if not is_bullish(r)]
    mature = [r for r in rows if r.get("lifecycle_maturity") in ("MATURE", "LONG_MATURE")]
    cohort_ready = [r for r in rows if r.get("cohort_status") == "COHORT_READY"]

    risk_watch = [
        r for r in rows
        if r.get("ods_status") in ("PENDING", "NOT_CONFIRMED")
        and (
            "demand_support_validation" in missing_components(r)
            or "structurally_meaningful_location" in missing_components(r)
            or r.get("ods_status") == "NOT_CONFIRMED"
        )
    ]

    missing_counts = component_counts(pending)

    raw_path = report_dir / "raw_full_universe_enriched_campaign_table.json"
    raw_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    index = {
        "marker": MARKER,
        "created_utc": now.isoformat(),
        "backend": BACKEND,
        "endpoint": ENDPOINT,
        "row_count": len(rows),
        "history_years": market.get("history_years"),
        "total_bars": market.get("total_bars"),
        "symbols_with_bars": market.get("symbols_with_bars"),
        "pages_fetched": market.get("pages_fetched"),
        "ods_confirmed": len(confirmed),
        "ods_pending": len(pending),
        "ods_not_confirmed": len(not_confirmed),
        "cohort_ready": len(cohort_ready),
        "mature_or_long_mature": len(mature),
        "missing_component_counts": missing_counts,
    }

    css = """
    body { font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; background: #f3f4f6; }
    .page { max-width: 1120px; margin: 0 auto; background: white; padding: 40px 46px; }
    .cover { border-bottom: 4px solid #111827; padding-bottom: 24px; margin-bottom: 28px; }
    h1 { font-size: 30px; margin: 0 0 8px 0; letter-spacing: -0.02em; }
    h2 { font-size: 21px; margin: 24px 0 10px 0; border-bottom: 1px solid #d1d5db; padding-bottom: 6px; }
    h3 { margin: 16px 0 8px 0; }
    .subtitle { font-size: 15px; color: #374151; margin-bottom: 16px; }
    .meta { display: grid; grid-template-columns: 210px 1fr; gap: 6px 14px; font-size: 13px; }
    .label { color: #6b7280; font-weight: bold; }
    .section { margin: 26px 0; page-break-inside: avoid; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }
    .metric { border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }
    .metric .num { font-size: 24px; font-weight: bold; }
    .metric .txt { color: #4b5563; font-size: 12px; }
    .note { color: #374151; font-size: 13px; }
    .muted { color: #6b7280; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 10px; }
    th { background: #111827; color: white; text-align: left; padding: 7px; }
    td { border-bottom: 1px solid #e5e7eb; padding: 6px; vertical-align: top; }
    .num { text-align: right; }
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .card { border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; page-break-inside: avoid; }
    .card-title { font-size: 15px; font-weight: bold; display: flex; justify-content: space-between; }
    .card-title span { font-size: 11px; color: #374151; }
    .card-line { font-size: 12px; margin-top: 5px; }
    .card p { font-size: 12px; color: #374151; line-height: 1.35; }
    .footer { margin-top: 34px; border-top: 1px solid #d1d5db; padding-top: 14px; font-size: 11px; color: #4b5563; }
    @media print {
      body { background: white; }
      .page { max-width: none; padding: 24px; }
      .section { page-break-inside: avoid; }
      h2 { page-break-after: avoid; }
    }
    """

    executive = f"""
    <section class="section">
      <h2>Executive Market Review</h2>
      <p>
        Tonight's V2 review uses the live full-universe Campaign Engine source: 100 ranked campaign rows,
        seven years of daily historical bars, formal ODS evidence evaluation, lifecycle maturity, cohort readiness,
        target/failure levels, and risk/reward context. The review identified {len(confirmed)} formally ODS-confirmed
        campaigns, {len(pending)} ODS-pending campaigns with specific missing evidence components, and
        {len(cohort_ready)} cohort-ready names.
      </p>
      <p>
        ODS pending does not mean missing data. It means the seven-year record was evaluated but one or more
        required operator-control evidence components was absent.
      </p>
    </section>
    """

    missing_html = "".join(
        f"<tr><td>{esc(k)}</td><td class='num'>{v}</td></tr>"
        for k, v in missing_counts.items()
    ) or "<tr><td>No missing components recorded</td><td class='num'>0</td></tr>"

    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(REPORT_TITLE)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="page">
    <div class="cover">
      <h1>SIGMALYTIC QUANT CORPORATION</h1>
      <div class="subtitle">{esc(REPORT_SUBTITLE)}</div>
      <div class="meta">
        <div class="label">Prepared date</div><div>{esc(now.strftime("%B %d, %Y %I:%M %p UTC"))}</div>
        <div class="label">Application</div><div>Sigmalytic Quant Corporation - Version 2</div>
        <div class="label">Audience</div><div>Subscribers, trial users, and market-intelligence readers</div>
        <div class="label">Live source</div><div>{esc(ENDPOINT)}</div>
        <div class="label">Important boundary</div><div>Stock-intelligence review and decision support only; not personalized financial advice.</div>
      </div>
    </div>

    {executive}

    <section class="section">
      <h2>Coverage Summary</h2>
      <div class="summary">
        <div class="metric"><div class="num">{len(rows)}</div><div class="txt">Campaign rows reviewed</div></div>
        <div class="metric"><div class="num">{esc(market.get("history_years"))}</div><div class="txt">Years of daily history</div></div>
        <div class="metric"><div class="num">{esc(market.get("total_bars"))}</div><div class="txt">Daily bars evaluated</div></div>
        <div class="metric"><div class="num">{len(cohort_ready)}</div><div class="txt">Cohort-ready names</div></div>
      </div>
      <table>
        <thead><tr><th>Metric</th><th>Value</th></tr></thead>
        <tbody>
          <tr><td>Symbols with bars</td><td>{esc(market.get("symbols_with_bars"))}</td></tr>
          <tr><td>Alpaca pages fetched</td><td>{esc(market.get("pages_fetched"))}</td></tr>
          <tr><td>ODS confirmed</td><td>{len(confirmed)}</td></tr>
          <tr><td>ODS pending with missing evidence detail</td><td>{len(pending)}</td></tr>
          <tr><td>ODS not confirmed</td><td>{len(not_confirmed)}</td></tr>
          <tr><td>Mature or long-mature campaigns</td><td>{len(mature)}</td></tr>
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>ODS Pending by Missing Evidence Component</h2>
      <p class="note">Formal ODS confirmation requires tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure.</p>
      <table>
        <thead><tr><th>Missing Evidence Component</th><th>Rows</th></tr></thead>
        <tbody>{missing_html}</tbody>
      </table>
    </section>

    {table_html(top_rows(confirmed, 20), "Formal ODS Confirmed Campaigns", "Confirmed only when all formal evidence components are present.", 20)}
    {card_grid(top_rows(long_watch, 20), "Long Watchlist", "Bullish watch candidates from the 100-row full-universe source.", 12)}
    {table_html(top_rows(neutral_watch, 25), "Neutral / Watch-Only Universe", "Rows not classified as bullish in the current source.", 25)}
    {table_html(top_rows(mature, 25), "Mature Campaign Leaders", "Campaigns with mature or long-mature lifecycle status.", 25)}
    {table_html(top_rows(cohort_ready, 25), "Cohort-Ready Campaigns", "Rows where seven-year structural analogs were sufficient for cohort readiness.", 25)}
    {table_html(top_rows(risk_watch, 25), "Deterioration / Risk Watch", "Rows with missing demand/support validation, structural location, or explicit non-confirmation.", 25)}

    <section class="section">
      <h2>Gamma Intelligence</h2>
      <p class="muted">Gamma-specific source was not used as a standalone reason for action in this report. Campaign context remains primary.</p>
    </section>

    <section class="section">
      <h2>Divergence Intelligence</h2>
      <p class="muted">Divergence-specific source was not used as a standalone reason for action in this report. Campaign context remains primary.</p>
    </section>

    {table_html(top_rows(rows, 20), "Tomorrow Focus List", "Highest-priority names by ODS/campaign evidence, lifecycle, and cohort context.", 20)}

    <section class="section">
      <h2>Closing Market View</h2>
      <p>
        Tomorrow's focus should be on whether cohort-ready and mature campaigns continue to defend support,
        whether ODS-pending names complete their missing evidence components, and whether any formally confirmed
        ODS rows expand without contrary failure.
      </p>
    </section>

    <section class="section">
      <h2>Important Subscriber Notes</h2>
      <p>
        This report is a nightly stock-intelligence review generated from Sigmalytic V2 campaign, formal ODS,
        lifecycle, cohort, and market-structure evidence. The long, short, neutral, pending, and confirmed classifications
        are watchlist categories, not personalized investment advice.
      </p>
    </section>

    <div class="footer">
      {esc(COPYRIGHT)}<br>
      Sigmalytic Quant Corporation | V2 Campaign Intelligence | Nightly Intelligence Report
    </div>
  </div>
</body>
</html>
"""

    html_path = report_dir / "Sigmalytic_Nightly_Intelligence_Report_Full_Universe.html"
    md_path = report_dir / "Sigmalytic_Nightly_Intelligence_Report_Full_Universe.md"
    pdf_path = report_dir / "Sigmalytic_Nightly_Intelligence_Report_Full_Universe.pdf"
    index_path = report_dir / "REPORT_INDEX.json"

    html_path.write_text(html_doc, encoding="utf-8")

    md = [
        "# Sigmalytic Quant Corporation - Nightly Intelligence Report",
        "",
        f"Prepared UTC: {now.isoformat()}",
        f"Live source: `{ENDPOINT}`",
        "",
        "## Executive Market Review",
        "",
        "Tonight's V2 review uses the live full-universe Campaign Engine source: 100 ranked campaign rows, seven years of daily historical bars, formal ODS evidence evaluation, lifecycle maturity, cohort readiness, target/failure levels, and risk/reward context.",
        "",
        "ODS pending does not mean missing data. It means the seven-year record was evaluated but one or more required operator-control evidence components was absent.",
        "",
        "## Coverage Summary",
        "",
        f"- Campaign rows reviewed: {len(rows)}",
        f"- Years of daily history: {market.get('history_years')}",
        f"- Total bars evaluated: {market.get('total_bars')}",
        f"- Symbols with bars: {market.get('symbols_with_bars')}",
        f"- Pages fetched: {market.get('pages_fetched')}",
        f"- ODS confirmed: {len(confirmed)}",
        f"- ODS pending: {len(pending)}",
        f"- ODS not confirmed: {len(not_confirmed)}",
        f"- Cohort ready: {len(cohort_ready)}",
        f"- Mature or long-mature: {len(mature)}",
        "",
        "## ODS Pending by Missing Evidence Component",
        "",
    ]

    if missing_counts:
        for k, v in missing_counts.items():
            md.append(f"- {k}: {v}")
    else:
        md.append("- None recorded")

    md.append("")
    md.append(markdown_table(top_rows(confirmed, 20), "Formal ODS Confirmed Campaigns", 20))
    md.append(markdown_table(top_rows(long_watch, 25), "Long Watchlist", 25))
    md.append(markdown_table(top_rows(neutral_watch, 25), "Neutral / Watch-Only Universe", 25))
    md.append(markdown_table(top_rows(mature, 25), "Mature Campaign Leaders", 25))
    md.append(markdown_table(top_rows(cohort_ready, 25), "Cohort-Ready Campaigns", 25))
    md.append(markdown_table(top_rows(risk_watch, 25), "Deterioration / Risk Watch", 25))
    md.append(markdown_table(top_rows(rows, 20), "Tomorrow Focus List", 20))
    md.append("")
    md.append("## Gamma Intelligence")
    md.append("")
    md.append("Gamma-specific source was not used as a standalone reason for action in this report. Campaign context remains primary.")
    md.append("")
    md.append("## Divergence Intelligence")
    md.append("")
    md.append("Divergence-specific source was not used as a standalone reason for action in this report. Campaign context remains primary.")
    md.append("")
    md.append("## Closing Market View")
    md.append("")
    md.append("Tomorrow's focus should be on whether cohort-ready and mature campaigns continue to defend support, whether ODS-pending names complete their missing evidence components, and whether any formally confirmed ODS rows expand without contrary failure.")
    md.append("")
    md.append("## Important Subscriber Notes")
    md.append("")
    md.append("This report is a nightly stock-intelligence review generated from Sigmalytic V2 campaign, formal ODS, lifecycle, cohort, and market-structure evidence. The long, short, neutral, pending, and confirmed classifications are watchlist categories, not personalized investment advice.")
    md.append("")
    md.append(COPYRIGHT)

    md_path.write_text("\n".join(md), encoding="utf-8")

    pdf_result = write_pdf_with_edge(html_path, pdf_path)
    index["files"] = {
        "html": str(html_path),
        "markdown": str(md_path),
        "pdf": str(pdf_path) if pdf_result.get("ok") else None,
        "raw_json": str(raw_path),
    }
    index["pdf_result"] = pdf_result
    index["elapsed_seconds"] = round(time.time() - start, 2)
    index_path.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")

    print("============================================================")
    print("PASS: STEP91B REPORT GENERATED")
    print(f"MARKER: {MARKER}")
    print(f"REPORT_DIR: {report_dir}")
    print(f"HTML: {html_path}")
    print(f"MD: {md_path}")
    print(f"PDF_OK: {pdf_result.get('ok')}")
    if pdf_result.get("ok"):
        print(f"PDF: {pdf_path}")
    else:
        print(f"PDF_ERROR: {pdf_result.get('error')}")
    print(f"RAW_JSON: {raw_path}")
    print(f"INDEX: {index_path}")
    print("============================================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
