#!/usr/bin/env python3
"""Reorganize #prices by chain role; rebuild Alphabet FCF with Q/TTM + zero line."""
from __future__ import annotations

import csv
import html as H
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/agent/cycle-peaks")
DATA = ROOT / "data"
PRICES = DATA / "prices"


def load_metric_csv(path: Path, period_key="period", sample_filter=None):
    tmp = defaultdict(dict)
    meta = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            if sample_filter and r.get("sample") not in sample_filter and r.get("sample") != sample_filter:
                # allow substring match via set
                if isinstance(sample_filter, (set, list, tuple)):
                    if r.get("sample") not in sample_filter:
                        continue
                else:
                    continue
            p = r.get("period_end") or r.get(period_key)
            metric = r["metric"]
            try:
                tmp[p][metric] = float(r["value"])
            except (TypeError, ValueError):
                continue
            meta[(p, metric)] = r
    return tmp, meta


def parse_d(d):
    return datetime.strptime(d, "%Y-%m-%d")


def nearest_on_or_after(rows, date):
    for d, v in rows:
        if d >= date:
            return d, v
    return None, None


def load_px(name):
    rows = []
    with (PRICES / f"{name}.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append((r["date"], float(r["adj_close"])))
    return rows


def q_label(period_end: str) -> str:
    y, m, _ = period_end.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y[2:]}Q{q}"


def svg_series_chart(
    title,
    series,
    *,
    w=860,
    h=300,
    zero_line=False,
    annotations=None,
    x_labels=None,
    unit_note="",
    chart_id="",
    mode_attr="",
):
    """series: list of (name, color, values list[float|None])."""
    annotations = annotations or []
    n = max(len(s[2]) for s in series)
    vals = [v for _, _, vs in series for v in vs if v is not None]
    if zero_line:
        vals = vals + [0.0]
    ymin, ymax = min(vals), max(vals)
    span = ymax - ymin or 1
    ymin -= span * 0.08
    ymax += span * 0.12
    pl, pr, pt, pb = 48, 24, 36, 70
    iw, ih = w - pl - pr, h - pt - pb

    def x(i):
        return pl if n == 1 else pl + iw * i / (n - 1)

    def y(v):
        return pt + ih * (1 - (v - ymin) / (ymax - ymin))

    parts = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet"'
        f' class="fund-svg" {("id=\""+chart_id+"\"") if chart_id else ""} {mode_attr} overflow="visible">'
    ]
    parts.append(f'<text x="{pl}" y="18" fill="#5c5a55" font-size="12" font-family="sans-serif">{H.escape(title)}</text>')
    for g in range(5):
        gy = pt + ih * g / 4
        gv = ymax - (ymax - ymin) * g / 4
        parts.append(f'<line x1="{pl}" y1="{gy:.1f}" x2="{w-pr}" y2="{gy:.1f}" stroke="#e8e4da"/>')
        parts.append(
            f'<text x="{pl-6}" y="{gy+4:.1f}" text-anchor="end" fill="#8a867c" font-size="10" font-family="monospace">{gv:.0f}</text>'
        )
    if zero_line and ymin < 0 < ymax:
        zy = y(0)
        parts.append(f'<line x1="{pl}" y1="{zy:.1f}" x2="{w-pr}" y2="{zy:.1f}" stroke="#9f1239" stroke-width="1.6" stroke-dasharray="5 4"/>')
        # Left-axis "0" tick only — no right-edge text that clips the chart
        parts.append(
            f'<text x="{pl-6}" y="{zy+4:.1f}" text-anchor="end" fill="#9f1239" font-size="10" font-family="monospace" font-weight="700">0</text>'
        )

    for name, color, vs in series:
        pts = []
        for i, v in enumerate(vs):
            if v is None:
                if len(pts) >= 2:
                    parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.3" points="{" ".join(pts)}"/>')
                pts = []
                continue
            pts.append(f"{x(i):.1f},{y(v):.1f}")
        if len(pts) >= 2:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.3" points="{" ".join(pts)}"/>')
        for i, v in enumerate(vs):
            if v is None:
                continue
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{color}"/>')

    # annotations on FCF points etc.
    for ann in annotations:
        i = ann["i"]
        v = ann["v"]
        color = ann.get("color", "#9f1239")
        tip = H.escape(json.dumps(ann.get("tip", {}), ensure_ascii=False), quote=True)
        parts.append(
            f'<g class="fcf-ann" data-tipjson="{tip}" style="cursor:pointer">'
            f'<line x1="{x(i):.1f}" y1="{pt}" x2="{x(i):.1f}" y2="{h-pb}" stroke="{color}" stroke-dasharray="4 3" opacity="0.65"/>'
            f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="6" fill="{color}" stroke="#fff" stroke-width="1.8"/>'
            f'<text x="{x(i)+8:.1f}" y="{y(v)-10:.1f}" fill="{color}" font-size="11">{H.escape(ann["label"])}</text>'
            f"</g>"
        )

    labels = x_labels or []
    for i, lab in enumerate(labels):
        parts.append(f'<text x="{x(i):.1f}" y="{h-14}" text-anchor="middle" fill="#5c5a55" font-size="10">{H.escape(lab)}</text>')

    lx, ly = pl, h - pb + 18
    for name, color, vs in series:
        need = 14 + sum((11 if ord(c) > 0x2E80 else 6.5) for c in name) + 14
        if lx + need > w - pr:
            lx = pl
            ly += 14
        parts.append(f'<rect x="{lx}" y="{ly-9}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly}" fill="#333" font-size="11" font-family="sans-serif">{H.escape(name)}</text>')
        lx += need
    if unit_note:
        parts.append(f'<text x="{w-pr}" y="{ly}" text-anchor="end" fill="#8a867c" font-size="10">{H.escape(unit_note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_alphabet_fcf():
    tmp, meta = load_metric_csv(DATA / "alphabet.csv", sample_filter={"Alphabet"})
    periods = sorted(tmp)
    labels = [q_label(p) for p in periods]
    ocf = [tmp[p]["operating_cash_flow"] / 1000 for p in periods]
    capex = [tmp[p]["cash_capex"] / 1000 for p in periods]
    fcf = [tmp[p]["free_cash_flow"] / 1000 for p in periods]
    discloses = [meta[(p, "free_cash_flow")]["first_disclose"] for p in periods]
    sources = [meta[(p, "free_cash_flow")].get("source_url", "") for p in periods]

    ttm_ocf, ttm_capex, ttm_fcf = [], [], []
    for i in range(len(periods)):
        if i < 3:
            ttm_ocf.append(None)
            ttm_capex.append(None)
            ttm_fcf.append(None)
        else:
            to = sum(ocf[j] for j in range(i - 3, i + 1))
            tc = sum(capex[j] for j in range(i - 3, i + 1))
            ttm_ocf.append(to)
            ttm_capex.append(tc)
            ttm_fcf.append(to - tc)

    googl = load_px("GOOGL")

    def tip_for(i, mode):
        if mode == "q":
            f0, f1 = (fcf[i - 1] if i else None), fcf[i]
            o, c = ocf[i], capex[i]
            metric = "单季 FCF"
        else:
            f0 = ttm_fcf[i - 1] if i and ttm_fcf[i - 1] is not None else None
            f1 = ttm_fcf[i]
            o, c = ttm_ocf[i], ttm_capex[i]
            metric = "滚动四季度 FCF"
        disc = discloses[i]
        mark, price = nearest_on_or_after(googl, disc)
        return {
            "company": "Alphabet",
            "event": metric,
            "fiscal": labels[i],
            "period_end": periods[i],
            "disclose": disc,
            "mark_date": mark,
            "price": None if price is None else round(price, 2),
            "prev_fcf": None if f0 is None else round(f0, 2),
            "curr_fcf": None if f1 is None else round(f1, 2),
            "ocf": None if o is None else round(o, 2),
            "capex": None if c is None else round(c, 2),
            "formula": "FCF = OCF − 现金 CapEx（正值=支出）",
            "driver": "CapEx 上升主导（OCF 仍强）" if (o is not None and o > 0 and c is not None and f1 is not None and f1 < f0 if f0 is not None else True) else "",
            "source": sources[i] or "Alphabet 季报 / data/alphabet.csv",
            "filing": sources[i],
        }

    # Q annotations: first negative + second negative
    q_anns = []
    first_neg = next((i for i, v in enumerate(fcf) if v < 0), None)
    if first_neg is not None:
        tip = tip_for(first_neg, "q")
        tip["event"] = "单季 FCF 转负"
        q_anns.append({"i": first_neg, "v": fcf[first_neg], "label": "单季 FCF 转负", "color": "#9f1239", "tip": tip})
        # next continuous negative
        if first_neg + 1 < len(fcf) and fcf[first_neg + 1] < 0:
            tip2 = tip_for(first_neg + 1, "q")
            tip2["event"] = "单季 FCF 连续转负"
            q_anns.append({"i": first_neg + 1, "v": fcf[first_neg + 1], "label": "连续转负", "color": "#9f1239", "tip": tip2})

    # TTM: still positive but sharp drop at latest — annotate decline at 26Q3 and softening at 25Q2 / 26Q2
    ttm_anns = []
    # annotate latest TTM as FCF下降 (still positive)
    last = len(ttm_fcf) - 1
    if ttm_fcf[last] is not None and ttm_fcf[last] > 0:
        tip = tip_for(last, "ttm")
        tip["event"] = "滚动四季 FCF 下降（仍为正）"
        ttm_anns.append({"i": last, "v": ttm_fcf[last], "label": "滚动四季仍为正·下降", "color": "#a16207", "tip": tip})
    # also mark single-q turn timing on TTM chart for cross-ref (vertical only on Q chart)

    q_svg = svg_series_chart(
        "Alphabet：单季度 OCF / 现金 CapEx / FCF（十亿美元）",
        [
            ("OCF ($B)", "#0b5f6b", ocf),
            ("现金 CapEx ($B)", "#6b7280", capex),
            ("FCF ($B)", "#9f1239", fcf),
        ],
        zero_line=True,
        annotations=q_anns,
        x_labels=labels,
        unit_note="FCF=OCF−现金CapEx",
        chart_id="alphabet-fcf-q",
        mode_attr='data-mode="q"',
    )
    ttm_svg = svg_series_chart(
        "Alphabet：滚动四季度 OCF / 现金 CapEx / FCF（十亿美元）",
        [
            ("滚动OCF ($B)", "#0b5f6b", ttm_ocf),
            ("滚动现金 CapEx ($B)", "#6b7280", ttm_capex),
            ("滚动 FCF ($B)", "#9f1239", ttm_fcf),
        ],
        zero_line=True,
        annotations=ttm_anns,
        x_labels=labels,
        unit_note="前三季滚动值缺，断点保留",
        chart_id="alphabet-fcf-ttm",
        mode_attr='data-mode="ttm"',
    )

    block = f"""
<div class="fcf-panel" id="alphabet-fcf-panel">
  <div class="tabs fcf-tabs" role="tablist">
    <a href="#alphabet-fcf-panel" class="on" data-fcf-mode="q">单季度</a>
    <a href="#alphabet-fcf-panel" data-fcf-mode="ttm">滚动四季度</a>
  </div>
  <div class="chart fcf-chart" data-fcf-view="q">{q_svg}</div>
  <div class="chart fcf-chart" data-fcf-view="ttm" hidden>{ttm_svg}</div>
  <p class="caption">公式 <span class="mono">FCF = OCF − 现金 CapEx</span>（CapEx 以正值表示支出）。核对结果：<strong>单季 FCF 于 2026Q2 首次转负</strong>（−$5.9B），2026Q3 再负（−$9.1B）；同期 OCF 仍为正，主因 CapEx 加速。<strong>滚动四季度 FCF 至 2026Q3 仍为正</strong>（约 $19.7B），但已较 2026Q2 的 $53.3B 明显下降。悬停/点击红点查看财季、披露日、前后 FCF、OCF/CapEx 与股价。</p>
  <div class="table-wrap"><table>
    <thead><tr><th>标记</th><th>单季度</th><th>滚动四季度</th><th>状态</th></tr></thead>
    <tbody>
      <tr><td>FCF 开始转弱</td><td>2025Q2 $5.3B（相对 2024Q4 $24.8B）</td><td>2025Q2 起滚动高位回落</td><td>已观察</td></tr>
      <tr class="neg"><td>首次转负</td><td>2026Q2（披露 2026-07-23）</td><td>—</td><td>单季已确认；滚动四季未转负</td></tr>
      <tr class="neg"><td>连续转负</td><td>2026Q3（披露 2026-10-29）</td><td>—</td><td>单季已确认</td></tr>
      <tr class="open"><td>滚动四季转负</td><td>—</td><td>至 2026Q3 仍为正（$19.7B）</td><td>尚未；标注为下降</td></tr>
      <tr class="open"><td>CapEx 指引下调 / 实际收缩</td><td>—</td><td>—</td><td>尚未；现金 CapEx 仍升</td></tr>
    </tbody>
  </table></div>
  <p class="footnote">表中「—」= 该口径下未发生或缺少可比结论。滚动四季前三个观察点因窗口不足而断点留空，不插值。</p>
</div>
"""
    return block, {
        "first_neg_disclose": discloses[first_neg] if first_neg is not None else None,
        "first_neg_label": labels[first_neg] if first_neg is not None else None,
        "ttm_still_positive": True,
        "ttm_latest": ttm_fcf[-1],
    }


def build_cisco_fund():
    tmp, _ = load_metric_csv(DATA / "cisco.csv", period_key="period", sample_filter=None)
    # cisco.csv may not have sample column
    if not tmp:
        tmp = defaultdict(dict)
        with (DATA / "cisco.csv").open() as f:
            for r in csv.DictReader(f):
                tmp[r["period"]][r["metric"]] = float(r["value"])
    periods = [p for p in sorted(tmp) if "1998" <= p[:4] <= "2002"]
    labels = []
    gm, gp = [], []
    for p in periods:
        y, m, d = p.split("-")
        # cisco fiscal quirks — use short period
        labels.append(p[2:7])
        gm.append(tmp[p].get("gross_margin_pct"))
        g = tmp[p].get("gross_profit")
        if g is None and tmp[p].get("operating_revenue") and tmp[p].get("COGS"):
            g = tmp[p]["operating_revenue"] - tmp[p]["COGS"]
        gp.append(None if g is None else g / 1000)
    # two charts stacked conceptually — GM% and GP$
    svg_gm = svg_series_chart(
        "上游卖方 Cisco：GAAP 毛利率 %",
        [("毛利率 %", "#166534", gm)],
        x_labels=labels,
        h=240,
        chart_id="fund-cisco-gm",
    )
    svg_gp = svg_series_chart(
        "上游卖方 Cisco：GAAP 毛利额（十亿美元）",
        [("毛利额 $B", "#0b5f6b", gp)],
        x_labels=labels,
        h=240,
        chart_id="fund-cisco-gp",
    )
    return svg_gm, svg_gp


def build_bellsouth_fcf():
    tmp = defaultdict(dict)
    with (DATA / "bellsouth.csv").open() as f:
        for r in csv.DictReader(f):
            tmp[r["period"]][r["metric"]] = float(r["value"])
    periods = sorted(tmp)
    labels = [q_label(p) for p in periods]
    fcf = [tmp[p].get("free_cash_flow") for p in periods]
    anns = []
    for i, v in enumerate(fcf):
        if v is not None and v < 0:
            anns.append({"i": i, "v": v, "label": "FCF首次转负", "color": "#9f1239", "tip": {
                "company": "BellSouth", "event": "FCF首次转负", "fiscal": labels[i],
                "curr_fcf": v, "formula": "FCF=OCF−现金CapEx", "source": "data/bellsouth.csv / SEC 10-Q"
            }})
            break
    return svg_series_chart(
        "采购/建设方 BellSouth：季度 FCF（百万美元）",
        [("FCF ($M)", "#9f1239", fcf)],
        zero_line=True,
        annotations=anns,
        x_labels=labels,
        h=250,
        chart_id="fund-bs-fcf",
    )


def build_conch_gm():
    tmp = defaultdict(dict)
    with (DATA / "conch_cement.csv").open() as f:
        for r in csv.DictReader(f):
            tmp[r["period"]][r["metric"]] = float(r["value"])
    periods = [p for p in sorted(tmp) if "2002" <= p[:4] <= "2008"]
    labels = [p[2:7] for p in periods]
    gm = [tmp[p].get("gross_margin_pct") for p in periods]
    return svg_series_chart(
        "上游供应商 海螺水泥：毛利率 %",
        [("毛利率 %", "#0b5f6b", gm)],
        x_labels=labels,
        h=240,
        chart_id="fund-conch-gm",
    )


def build_nvidia_gm():
    tmp = defaultdict(dict)
    with (DATA / "nvidia.csv").open() as f:
        for r in csv.DictReader(f):
            p = r.get("period_end") or r.get("period")
            tmp[p][r["metric"]] = float(r["value"])
            if "first_disclose" in r:
                tmp[p]["_disc"] = r["first_disclose"]
    periods = sorted(tmp)
    labels = []
    gm = []
    for p in periods:
        lab = tmp[p].get("fiscal_label")  # may not exist
        labels.append(q_label(p))
        gm.append(tmp[p].get("gross_margin_pct"))
    # find stage high
    anns = []
    if gm:
        # known stage high FY25Q1 ~ 78.4 around 2024-04-28 period
        peak_i = max(range(len(gm)), key=lambda i: gm[i] if gm[i] is not None else -1)
        anns.append({"i": peak_i, "v": gm[peak_i], "label": "毛利率阶段高点", "color": "#b45309", "tip": {
            "company": "NVIDIA", "event": "毛利率阶段高点", "fiscal": labels[peak_i],
            "curr": gm[peak_i], "source": "data/nvidia.csv"
        }})
    return svg_series_chart(
        "上游卖方 NVIDIA：GAAP 毛利率 %",
        [("毛利率 %", "#0b5f6b", gm)],
        annotations=anns,
        x_labels=labels,
        h=240,
        chart_id="fund-nvda-gm",
    )


def extract_div(html: str, div_id: str) -> str:
    m = re.search(rf'<div class="chart long-chart" id="{div_id}">.*?</div>', html, re.S)
    if not m:
        raise SystemExit(f"missing {div_id}")
    return m.group(0)


def extract_between(html, start_pat, end_pat):
    m = re.search(start_pat, html)
    if not m:
        return None
    start = m.start()
    m2 = re.search(end_pat, html[m.end():])
    if not m2:
        return html[start:]
    return html[start : m.end() + m2.start()]


def main():
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")

    alphabet_block, alpha_meta = build_alphabet_fcf()
    cisco_gm, cisco_gp = build_cisco_fund()
    bs_fcf = build_bellsouth_fcf()
    conch_gm = build_conch_gm()
    nvda_gm = build_nvidia_gm()

    chart_us = extract_div(html, "chart-us")
    chart_cn = extract_div(html, "chart-cn")
    chart_ai = extract_div(html, "chart-ai")

    # pull existing US verdict if present
    verdict_m = re.search(r'<div class="answer" id="us-bubble-verdict">.*?</div>', html, re.S)
    us_verdict = verdict_m.group(0) if verdict_m else ""

    # zoom panel: keep from existing
    zoom_m = re.search(
        r'(<h3>6\.5.*?</h3>.*?<div class="tabs" id="zoom-tabs">.*?</script>\s*)',
        html,
        re.S,
    )
    # Better: capture from 6.4 or 6.5 through end of prices section scripts related to zoom
    # We'll rebuild zoom section by extracting from h3 6.4 to just before </section> of prices
    prices_sec = re.search(r'<section class="block" id="prices">(.*?)</section>', html, re.S)
    if not prices_sec:
        raise SystemExit("no prices section")
    old_prices = prices_sec.group(1)
    zoom_part = ""
    zm = re.search(r'(<h3>6\.[45].*股价高点.*?</h3>.*)$', old_prices, re.S)
    # Keep lag table + zoom from old: from "6.4" heading
    zm = re.search(r'(<h3>6\.4.*)', old_prices, re.S)
    if zm:
        zoom_part = zm.group(1)
        # trim trailing us-bubble leftover etc already not there
        # remove any duplicate 6.x headers we'll replace — keep as-is but renumber later lightly

    # CSS inject
    extra_css = """
.case-panel{margin:22px 0 28px;padding-top:4px}
.timeline{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px;align-items:center}
.timeline .tl-label{font-size:12px;color:var(--muted);margin-right:4px}
.timeline a.tl{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;border:1px solid var(--line);background:#fff;color:var(--accent);text-decoration:none;font-size:12.5px;line-height:1.3}
.timeline a.tl:hover,.timeline a.tl:focus{background:#eef6f6;border-color:#9ec5c9}
.timeline a.tl .t{font-family:var(--mono);font-size:11px;color:var(--muted)}
.layer-block{margin:14px 0;padding:12px 14px;border:1px dashed var(--line);border-radius:12px;background:#fffcf7}
.layer-block h4{margin:0 0 8px;font-size:0.98rem;color:#243}
details.more{margin:8px 0 0;font-size:13.5px;color:var(--muted)}
details.more summary{cursor:pointer;color:var(--accent)}
.footnote{font-size:11.5px;color:#6b7280;line-height:1.45;margin:6px 0 10px;overflow-wrap:anywhere}
.footnote + .footnote{margin-top:2px}
.sync-line{stroke:#111827;stroke-width:1;stroke-dasharray:3 2;opacity:0.45;pointer-events:none}
.fcf-tabs{margin-bottom:6px}
"""
    if ".case-panel{" not in html:
        html = html.replace("</style>", extra_css + "\n</style>")
    # soften gap callouts → keep class but style as footnote-adjacent
    html = html.replace(
        ".gap{border-left:3px solid var(--danger);background:#fff1f2;padding:10px 12px;margin:12px 0;font-size:14px}",
        ".gap{display:none} /* replaced by .footnote */\n.footnote strong{color:#4b5563;font-weight:600}",
    )

    # Replace Alphabet section 4.2
    html = re.sub(
        r'<h3>4\.2 买方 — Alphabet 集团（OCF / CapEx / FCF）</h3>.*?(?=<section class="block" id="hist">)',
        '<h3 id="ai-buyer-alphabet">4.2 买方 — Alphabet 集团（OCF / CapEx / FCF）</h3>\n'
        + alphabet_block
        + "\n</section>\n\n",
        html,
        count=1,
        flags=re.S,
    )

    # Fix accidental double </section> if any — the ai section should close once
    # After replacement we may have closed ai section early. Check structure.
    # Original had </section> after alphabet table closing the #ai section.
    # Our replacement includes </section> — good if hist follows.

    # Update watch table TTM cell
    html = html.replace(
        "；滚动四季 FCF 仍待表内核算标注",
        "；滚动四季至 2026Q3 <strong>仍为正</strong>（约 $19.7B，已下降）",
    )
    html = html.replace(
        "<tr class=\"open\"><td>滚动四季转负</td><td>—</td><td>待表内确认后标注</td></tr>",
        "<tr class=\"open\"><td>滚动四季转负</td><td>至 2026Q3 仍为正（$19.7B）</td><td>尚未转负；图上标下降</td></tr>",
    )

    # Layers gap → footnote
    html = html.replace(
        '<div class="gap"><strong>缺数清单：</strong>预制棒/光模块外售连续季；中国螺纹与沥青可核对季/月序列；上市开发商统一 FCF；HBM/CoWoS 出货与利用率；AI 应用付费单量与扣推理成本毛利；亚马逊 1998–2004 应用层季报对齐。</div>',
        '<p class="footnote"><strong>缺数（不影响主文已列结论）：</strong>预制棒/光模块外售连续季；中国螺纹与沥青可核对季/月序列；上市开发商统一 FCF；HBM/CoWoS 出货与利用率；AI 应用付费单量与扣推理成本毛利。亚马逊 1998–2004 应用层季报仅部分对齐，FCF 标为持续为负样本。</p>',
    )

    # Build new prices section
    new_prices = f"""
<section class="block" id="prices">
  <h2>6. 股价与事件：上游盈利 → 买方现金流 → 采购预算 → 股价反应</h2>
  <p>每个案例先给<strong>覆盖整段观察期的股价主图</strong>，再按<strong>上游供应商 → 采购/建设方 → 下游应用或终端需求</strong>排列基本面。共享实际日期轴；拐点时间线点击可跳到股价图与对应基本面图。研究问题：财务信号何时公开，各层股价是领先还是滞后。</p>
  <div class="note">读图顺序：① 时间线上的拐点先后；② 股价曲线谁先见顶；③ 基本面图上同一信号是否已可确认；④ 悬停比较披露日与标注日。</div>

  <div class="case-panel" id="case-us" data-case="us">
    <h3>6.1 美国互联网周期（1998–2002）</h3>
    <div class="timeline" id="tl-us">
      <span class="tl-label">拐点时间线</span>
      <a class="tl" href="#chart-us" data-jump="fund-cisco-gm" data-eid="cisco_gm_peak"><span class="t">1998-08</span> Cisco 毛利率见顶</a>
      <a class="tl" href="#chart-us" data-jump="fund-cisco-gm" data-eid="cisco_gm_confirm"><span class="t">1998-11</span> 毛利率高点确认</a>
      <a class="tl" href="#chart-us" data-eid="nasdaq_peak"><span class="t">2000-03-10</span> 纳指见顶</a>
      <a class="tl" href="#chart-us" data-jump="fund-cisco-gp" data-eid="cisco_gp_peak_print"><span class="t">2001-02</span> 毛利额峰值披露</a>
      <a class="tl" href="#chart-us" data-jump="fund-bs-fcf" data-eid="bs_fcf_neg"><span class="t">2001-05</span> BellSouth FCF 转负</a>
      <a class="tl" href="#chart-us" data-jump="fund-cisco-gp" data-eid="cisco_gp_confirm_yoy"><span class="t">2001-05</span> 毛利额确认/同比降</a>
    </div>
    {chart_us}
    <p class="caption">圆点=披露/确认后首个可交易日与该公司股价曲线交点；黑色虚线=纳指见顶。悬停查看财季、前后两期、相对纳指/股价高点领先滞后。</p>
    {us_verdict}

    <div class="layer-block" id="fund-cisco-gm">
      <h4>上游供应商 — Cisco 毛利率 / 毛利额</h4>
      <div class="chart">{cisco_gm}</div>
      <div class="chart">{cisco_gp}</div>
      <p class="footnote">毛利率峰值（1998）与毛利额峰值（2001）分开标注。Corning 无完整分部 GM%，改用分部盈利作利润代理（见股价图标注）。</p>
    </div>
    <div class="layer-block" id="fund-bs-fcf">
      <h4>采购与建设方 — BellSouth FCF（Verizon 为同相位股价代理）</h4>
      <div class="chart">{bs_fcf}</div>
      <details class="more"><summary>展开：Verizon 样本与替换说明</summary>
        <p>BellSouth 已退市，股价图用 Verizon 同相位曲线承载买方事件圆点。Verizon 样本自 2001Q1 起 FCF 已为负，标「持续为负（样本）」，无法还原泡沫前由正转负时点。FCF 均按 <span class="mono">OCF − 现金 CapEx</span> 计算。</p>
      </details>
      <p class="footnote">BellSouth 1998–1999 连续季频现金流未齐，无法确认更早是否已转负；样本覆盖 2000Q1 起。表内缺季以断点保留。</p>
    </div>
    <div class="layer-block" id="fund-amzn">
      <h4>下游应用 — Amazon（FCF 持续为负）</h4>
      <p>观察期内 Amazon FCF <strong>持续为负</strong>（非「首次由正转负」）。1999Q3 扩张期进一步恶化，已在股价图标注。完整逐季对齐仍有缺口。</p>
      <p class="footnote">亚马逊 1998–2000 部分季度现金流量表未完全逐季对齐；拐点判断按「持续为负 + 恶化可见」处理，不用「首次转负」措辞。</p>
    </div>
  </div>

  <div class="case-panel" id="case-cn" data-case="cn">
    <h3>6.2 中国建设/地产周期（2002–2008）</h3>
    <div class="timeline" id="tl-cn">
      <span class="tl-label">拐点时间线</span>
      <a class="tl" href="#chart-cn" data-jump="fund-conch-gm"><span class="t">2004H1</span> 海螺毛利率阶段高点</a>
      <a class="tl" href="#chart-cn"><span class="t">2007-10</span> 海螺股价窗内高点</a>
      <a class="tl" href="#chart-cn"><span class="t">2007-11</span> 华润置地股价高点</a>
    </div>
    {chart_cn}
    <p class="caption">华润置地为开发商买方股价代理（非全国开发商统一 FCF）。沥青/钢筋上市公司连续行情未齐。</p>
    <div class="layer-block" id="fund-conch-gm">
      <h4>上游供应商 — 海螺水泥毛利率</h4>
      <div class="chart">{conch_gm}</div>
      <p class="footnote">买方宏观到位资金/新开工为年频代理，未见美式季度 FCF 转负序列；上市开发商统一 FCF 未齐。缺数不影响「材料 GM 先于收入见顶」的已核实结论。</p>
    </div>
    <div class="layer-block">
      <h4>采购与建设方 / 终端需求</h4>
      <p>建设与开发投资、商品房销售等以宏观年/月频代理观察需求，详见 <a href="./history.html">history.html</a> 与数据下载。本页优先保留对拐点判断最直接的海螺 GM 与股价对照。</p>
      <details class="more"><summary>展开：代理指标说明</summary>
        <p>开发投资 / 到位资金 / 新开工衡量「采购与建设」强度；商品房销售面积衡量终端需求。它们<strong>不是</strong>公司级 FCF，不能直接等同美国运营商现金流转负。</p>
      </details>
    </div>
  </div>

  <div class="case-panel" id="case-ai" data-case="ai">
    <h3>6.3 AI 周期（2020–最新，仍在演进）</h3>
    <div class="timeline" id="tl-ai">
      <span class="tl-label">拐点时间线</span>
      <a class="tl" href="#chart-ai" data-jump="fund-nvda-gm" data-eid="nvda_gm"><span class="t">2024-05-22</span> NVIDIA 毛利率阶段高点</a>
      <a class="tl" href="#chart-ai" data-jump="ai-buyer-alphabet" data-eid="googl_fcf_neg"><span class="t">2026-07-23</span> Alphabet 单季 FCF 转负</a>
      <a class="tl" href="#chart-ai" data-eid="googl_fcf_neg2"><span class="t">2026-10-29</span> 单季 FCF 连续转负</a>
      <a class="tl" href="#alphabet-fcf-panel"><span class="t">至 2026Q3</span> 滚动四季 FCF 仍为正·下降</a>
    </div>
    {chart_ai}
    <p class="caption">Alphabet 股价曲线上的圆点对应该季业绩披露后的首个可交易日（2026Q2/Q3 均为披露当日已大幅反应）。点击可放大 ±60 交易日。</p>
    <div class="layer-block" id="fund-nvda-gm">
      <h4>上游供应商 — NVIDIA 毛利率</h4>
      <div class="chart">{nvda_gm}</div>
      <p class="footnote">收入与数据中心收入至样本最新季仍升，不支持「收入已见顶」。毛利额序列部分季度待补，图中以断点保留。</p>
    </div>
    <div class="layer-block" id="fund-alphabet-fcf">
      <h4>采购与建设方 — Alphabet 集团 OCF / CapEx / FCF</h4>
      {alphabet_block}
      <details class="more"><summary>展开：Microsoft 交叉样本</summary>
        <p>Microsoft 现金 CapEx 升、FCF 仍正（FY26Q2 FCF 约 $5.9B）。与 Alphabet「已转负」不同步，作买方交叉对照，不替代 Alphabet 主样本。</p>
      </details>
    </div>
    <div class="layer-block">
      <h4>下游应用 / 终端需求</h4>
      <p>自动驾驶付费、机器人部署、AI 软件扣推理成本毛利等序列待补；本页不以猜测填空。</p>
      <p class="footnote">应用层缺数不影响已确认的 NVIDIA GM 阶段高点与 Alphabet 单季 FCF 转负结论。CapEx 指引下调尚未确认。</p>
    </div>
  </div>
"""

    # Append zoom_part if available, with light heading tweak
    if zoom_part:
        # Ensure zoom_part doesn't duplicate case closings
        new_prices += "\n  <h3 id=\"price-lags\">6.4 股价高点 vs 基本面：间隔与披露滞后</h3>\n"
        # strip the old h3 from zoom_part
        zoom_part2 = re.sub(r"^<h3>6\.4.*?</h3>\s*", "", zoom_part, count=1, flags=re.S)
        zoom_part2 = re.sub(r"<h3>6\.5", "<h3 id=\"zoom-panel\">6.5", zoom_part2, count=1)
        new_prices += zoom_part2
    new_prices += "\n</section>"

    html = re.sub(
        r'<section class="block" id="prices">.*?</section>',
        new_prices,
        html,
        count=1,
        flags=re.S,
    )

    # Enhance GOOGL markers tipjson on AI chart if still data-tip only
    googl_tip1 = H.escape(json.dumps({
        "company": "Alphabet",
        "event": "单季 FCF 转负",
        "fiscal": "2026Q2",
        "disclose": "2026-07-23",
        "mark_date": "2026-07-23",
        "prev2": ["2026Q1 FCF $10.1B", "2025Q4 FCF $24.6B"],
        "curr": "2026Q2 FCF −$5.9B",
        "ocf": "OCF $39.1B",
        "capex": "现金 CapEx $44.9B",
        "price": 317.49,
        "source": "Alphabet 2026Q2 业绩披露；data/alphabet.csv",
        "driver": "CapEx 增加（OCF 仍正）",
    }, ensure_ascii=False), quote=True)
    googl_tip2 = H.escape(json.dumps({
        "company": "Alphabet",
        "event": "单季 FCF 连续转负",
        "fiscal": "2026Q3",
        "disclose": "2026-10-29",
        "mark_date": "2026-10-29",
        "prev2": ["2026Q2 FCF −$5.9B", "2026Q1 FCF $10.1B"],
        "curr": "2026Q3 FCF −$9.1B",
        "ocf": "OCF $42.3B",
        "capex": "现金 CapEx $51.4B",
        "price": 283.82,
        "source": "Alphabet 2026Q3 业绩披露；data/alphabet.csv",
        "driver": "CapEx 继续上升",
    }, ensure_ascii=False), quote=True)

    html = re.sub(
        r'<g class="ev-marker" data-eid="googl_fcf_neg"[^>]*>',
        f'<g class="ev-marker us-ev" data-eid="googl_fcf_neg" data-zoom="googl_fcf_first_neg" data-tipjson="{googl_tip1}" style="cursor:pointer">',
        html,
        count=1,
    )
    html = re.sub(
        r'<g class="ev-marker" data-eid="googl_fcf_neg2"[^>]*>',
        f'<g class="ev-marker us-ev" data-eid="googl_fcf_neg2" data-zoom="" data-tipjson="{googl_tip2}" style="cursor:pointer">',
        html,
        count=1,
    )

    # JS: FCF toggle + timeline jump + enrich tooltip for fcf-ann + alphabet tips
    extra_js = r"""
<script>
(function(){
  // FCF Q / TTM toggle
  document.querySelectorAll('.fcf-panel').forEach(panel=>{
    const tabs=panel.querySelectorAll('[data-fcf-mode]');
    const views=panel.querySelectorAll('[data-fcf-view]');
    tabs.forEach(tab=>{
      tab.addEventListener('click', e=>{
        e.preventDefault();
        const mode=tab.getAttribute('data-fcf-mode');
        tabs.forEach(t=>t.classList.toggle('on', t===tab));
        views.forEach(v=>{ v.hidden = v.getAttribute('data-fcf-view')!==mode; });
      });
    });
  });

  // Timeline jump: highlight target + scroll
  document.querySelectorAll('.timeline a.tl').forEach(a=>{
    a.addEventListener('click', e=>{
      const jump=a.getAttribute('data-jump');
      const eid=a.getAttribute('data-eid');
      if(jump){
        const el=document.getElementById(jump);
        if(el){ setTimeout(()=>el.scrollIntoView({behavior:'smooth',block:'start'}), 50); }
      }
      if(eid){
        const g=document.querySelector('[data-eid="'+eid+'"]');
        if(g){
          g.classList.add('pulse');
          setTimeout(()=>g.classList.remove('pulse'), 1600);
        }
      }
    });
  });

  // Shared tooltip for FCF annotations
  const tip=document.getElementById('ev-tooltip');
  function showFcf(evt, data){
    if(!tip) return;
    tip.innerHTML =
      '<div><strong>'+(data.company||'')+'</strong> · '+(data.event||'')+'</div>'+
      '<div class="k">财季</div><div>'+(data.fiscal||'')+'</div>'+
      '<div class="k">披露 / 标注日</div><div>披露 '+(data.disclose||'—')+'<br>标注 '+(data.mark_date||'—')+(data.price!=null?' · 股价 '+data.price:'')+'</div>'+
      '<div class="k">前后 FCF → 当期</div><div>'+(data.prev_fcf!=null?data.prev_fcf:'—')+' → <strong>'+(data.curr_fcf!=null?data.curr_fcf:'—')+'</strong></div>'+
      '<div class="k">OCF / 现金 CapEx</div><div>OCF '+(data.ocf!=null?data.ocf:'—')+' · CapEx '+(data.capex!=null?data.capex:'—')+'</div>'+
      (data.driver?('<div class="k">驱动</div><div>'+data.driver+'</div>'):'')+
      '<div class="k">公式 / 来源</div><div>'+(data.formula||'')+'<br>'+(data.source||'')+'</div>'+
      (data.filing?('<div class="k">财报</div><div><a style="color:#93c5fd" href="'+data.filing+'" target="_blank" rel="noopener">打开来源</a></div>'):'');
    tip.classList.add('show');
    const cx=evt.clientX||0, cy=evt.clientY||0;
    tip.style.left=Math.min(window.innerWidth-360, Math.max(8, cx+14))+'px';
    tip.style.top=Math.min(window.innerHeight-20, Math.max(8, cy+14))+'px';
  }
  document.querySelectorAll('.fcf-ann').forEach(g=>{
    const raw=g.getAttribute('data-tipjson'); if(!raw) return;
    let data; try{data=JSON.parse(raw)}catch(e){return}
    g.addEventListener('mouseenter', e=>showFcf(e,data));
    g.addEventListener('mousemove', e=>showFcf(e,data));
    g.addEventListener('mouseleave', ()=>tip && tip.classList.remove('show'));
    g.addEventListener('click', e=>{e.preventDefault();e.stopPropagation();showFcf(e,data); setTimeout(()=>tip&&tip.classList.remove('show'), 8000);});
  });
})();
</script>
<style>
.ev-marker.pulse circle{r:8;stroke-width:2.4}
.layer-block:target{outline:2px solid #9ec5c9;outline-offset:2px}
</style>
"""
    if "data-fcf-mode" not in html.split("</body>")[0][-5000:]:
        html = html.replace("</body>", extra_js + "\n</body>")
    elif "FCF Q / TTM toggle" not in html:
        html = html.replace("</body>", extra_js + "\n</body>")

    # Deduplicate alphabet panels if both ai section and prices have identical ids — change prices copy ids
    # Second alphabet-fcf-panel in prices: rename ids to avoid duplicate
    # Find second occurrence of id="alphabet-fcf-panel"
    parts = html.split('id="alphabet-fcf-panel"')
    if len(parts) > 2:
        html = parts[0] + 'id="alphabet-fcf-panel"' + parts[1] + 'id="alphabet-fcf-panel-prices"' + "".join(parts[2:])
        # also fix duplicate chart ids in second block
        # Only replace within prices case — simpler: replace alphabet-fcf-q second occurrence
        for cid in ["alphabet-fcf-q", "alphabet-fcf-ttm"]:
            chunks = html.split(f'id="{cid}"')
            if len(chunks) > 2:
                html = chunks[0] + f'id="{cid}"' + chunks[1] + f'id="{cid}-prices"' + "".join(chunks[2:])

    # Update TOC wording
    html = html.replace(
        '<li><a href="#prices">多年股价与事件标注</a></li>',
        '<li><a href="#prices">股价与事件：产业链拐点</a></li>',
    )

    html_path.write_text(html, encoding="utf-8")
    store = Path("/cursor/stores/self/docs")
    store.mkdir(parents=True, exist_ok=True)
    (store / "cycle-peak-framework.html").write_text(html, encoding="utf-8")

    # sanity
    assert 'id="prices"' in html
    assert html.count('font-weight="700">0</text>') >= 1 or ">0</text>" in html
    assert "滚动四季度" in html
    assert "case-us" in html and "case-ai" in html
    assert html.count('id="alphabet-fcf-panel"') == 1
    print("ok", html_path.stat().st_size)
    print("alpha", alpha_meta)


if __name__ == "__main__":
    main()
