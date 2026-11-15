#!/usr/bin/env python3
"""Rebuild long-run price charts with FT-style date+event callout arrows."""
from __future__ import annotations

import csv
import html as H
import json
import math
import re
from datetime import datetime
from pathlib import Path

ROOT = Path("/agent/cycle-peaks")
PRICES = ROOT / "data" / "prices"
NASDAQ_PEAK = "2000-03-10"


def load_px(name):
    rows = []
    with (PRICES / f"{name}.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append((r["date"], float(r["adj_close"])))
    return rows


def filter_range(rows, a, b):
    return [(d, v) for d, v in rows if a <= d <= b]


def downsample(rows, n=280):
    if len(rows) <= n:
        return rows
    step = max(1, len(rows) // n)
    out = rows[::step]
    if out[-1] != rows[-1]:
        out.append(rows[-1])
    return out


def normalize(rows):
    if not rows:
        return []
    b = rows[0][1]
    return [(d, 100 * v / b) for d, v in rows]


def parse(d):
    return datetime.strptime(d, "%Y-%m-%d")


def to_x(d, d0, d1, x0, x1):
    t0, t1 = parse(d0).timestamp(), parse(d1).timestamp()
    t = parse(d).timestamp()
    return x0 + (x1 - x0) * (t - t0) / (t1 - t0)


def nearest_on_or_after(rows, date):
    for d, v in rows:
        if d >= date:
            return d, v
    return None, None


def zh_date(d: str) -> str:
    y, m, day = d.split("-")
    if day == "01" or day in ("02", "03") and int(day) <= 3:
        # month-level if early month mark often month-ish; still show month
        return f"{int(y)}年{int(m)}月"
    return f"{int(y)}年{int(m)}月{int(day)}日"


def est_label_size(lines, size=11):
    w = max(sum((size if ord(c) > 0x2E80 else size * 0.58) for c in line) for line in lines)
    h = 13 * len(lines) + 2
    return w, h


def build_chart(
    *,
    case: str,
    title: str,
    start: str,
    end: str,
    series_spec,
    events,
    market_ref=None,
    w=1000,
    h=440,
    year_range=None,
):
    """events: list of dicts with file, mark_date, color, lines (label), show_label, tip, zoom, eid"""
    pl, pr, pt, pb = 54, 28, 48, 78
    series = []
    raw_map = {}
    full_map = {}
    for name, file, color in series_spec:
        raw = filter_range(load_px(file), start, end)
        raw_map[file] = dict(raw)
        full = normalize(raw)
        full_map[file] = full
        series.append((name, downsample(full), full, color, file))

    vals = [v for _, n, _, _, _ in series for _, v in n]
    ymin, ymax = min(vals), max(vals)
    span = ymax - ymin or 1
    ymin -= span * 0.10
    ymax += span * 0.22  # extra headroom for callouts
    iw, ih = w - pl - pr, h - pt - pb

    def x(d):
        return to_x(d, start, end, pl, w - pr)

    def y(v):
        return pt + ih * (1 - (v - ymin) / (ymax - ymin))

    parts = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" '
        f'class="long-price-svg" data-case="{case}" data-start="{start}" data-end="{end}" overflow="visible">'
    ]
    # arrow marker (per chart unique id)
    mid = f"arr-{case}"
    parts.append(
        f'<defs><marker id="{mid}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
        f'<path d="M0,0 L7,3.5 L0,7 Z" fill="#374151"/></marker></defs>'
    )
    parts.append(
        f'<text x="{pl}" y="18" fill="#5c5a55" font-size="12" font-family="sans-serif">{H.escape(title)}</text>'
    )
    for g in range(5):
        gy = pt + ih * g / 4
        gv = ymax - (ymax - ymin) * g / 4
        parts.append(f'<line x1="{pl}" y1="{gy:.1f}" x2="{w-pr}" y2="{gy:.1f}" stroke="#e8e4da"/>')
        parts.append(
            f'<text x="{pl-6}" y="{gy+4:.1f}" text-anchor="end" fill="#8a867c" font-size="10" font-family="monospace">{gv:.0f}</text>'
        )

    years = year_range or range(int(start[:4]), int(end[:4]) + 1)
    for yy in years:
        d = f"{yy}-01-01"
        if start <= d <= end:
            parts.append(f'<line x1="{x(d):.1f}" y1="{pt}" x2="{x(d):.1f}" y2="{h-pb}" stroke="#f0ebe3"/>')
            parts.append(f'<text x="{x(d):.1f}" y="{h-14}" text-anchor="middle" fill="#5c5a55" font-size="10">{yy}</text>')

    for name, plot, full, color, file in series:
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in plot)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{pts}"/>')

    # Market reference (Nasdaq): light gray vertical + on-curve callout optional
    if market_ref:
        md = market_ref["date"]
        mfile = market_ref["file"]
        nx = x(md)
        parts.append(
            f'<line class="market-ref" x1="{nx:.1f}" y1="{pt}" x2="{nx:.1f}" y2="{h-pb}" '
            f'stroke="#9ca3af" stroke-width="1.2" stroke-dasharray="5 4" opacity="0.85"/>'
        )
        # place as an event on index curve
        events = list(events) + [
            {
                "eid": "nasdaq_peak",
                "file": mfile,
                "mark_date": md,
                "color": "#374151",
                "lines": market_ref["lines"],
                "show_label": True,
                "zoom": "",
                "tip": market_ref.get("tip", {"company": "纳斯达克", "event": "综合指数收盘见顶", "mark_date": md}),
            }
        ]

    # Resolve event positions
    placements = []
    for e in events:
        full = full_map.get(e["file"])
        if not full:
            continue
        td, nv = nearest_on_or_after(full, e["mark_date"])
        if td is None:
            continue
        raw = raw_map[e["file"]].get(td)
        tip = dict(e.get("tip") or {})
        tip.setdefault("mark_date", td)
        if raw is not None:
            tip.setdefault("price", round(raw, 2))
        placements.append(
            {
                **e,
                "td": td,
                "xx": x(td),
                "yy": y(nv),
                "tip": tip,
            }
        )

    # Place labels for show_label events
    boxes = []
    labeled = [p for p in placements if p.get("show_label")]
    unlabeled = [p for p in placements if not p.get("show_label")]

    def overlaps(b, pad=4):
        x0, y0, x1, y1 = b
        for a0, a1, a2, a3 in boxes:
            if not (x1 + pad < a0 or x0 - pad > a2 or y1 + pad < a1 or y0 - pad > a3):
                return True
        return False

    for p in labeled:
        lines = p["lines"]
        lw, lh = est_label_size(lines)
        # candidate offsets: (dx_center, dy_top) relative to point — prefer above then below
        cands = []
        for dx, dy in [
            (0, -lh - 28),
            (0, 22),
            (-lw * 0.35, -lh - 36),
            (lw * 0.1, -lh - 40),
            (-lw * 0.5, 26),
            (20, -lh - 20),
            (-lw - 20, -lh - 20),
            (24, 18),
            (-lw - 24, 18),
            (0, -lh - 56),
            (0, 40),
            (-lw * 0.2, -lh - 72),
        ]:
            lx0 = p["xx"] + dx
            ly0 = p["yy"] + dy
            lx1, ly1 = lx0 + lw, ly0 + lh
            if ly0 < pt + 2 or ly1 > h - pb - 4 or lx0 < pl + 2 or lx1 > w - 6:
                continue
            cands.append((lx0, ly0, lx1, ly1))

        chosen = None
        for b in cands:
            if not overlaps(b):
                chosen = b
                break
        if not chosen and cands:
            chosen = cands[0]
        if not chosen:
            chosen = (p["xx"] + 12, max(pt + 2, p["yy"] - lh - 20), p["xx"] + 12 + lw, max(pt + 2, p["yy"] - lh - 20) + lh)
        boxes.append(chosen)
        p["box"] = chosen
        # arrow attaches to nearest box edge toward the point
        bx0, by0, bx1, by1 = chosen
        cx = (bx0 + bx1) / 2
        cy = (by0 + by1) / 2
        # pick attachment on box boundary
        if abs(p["yy"] - cy) >= abs(p["xx"] - cx):
            ax = min(max(p["xx"], bx0), bx1)
            ay = by1 if p["yy"] > cy else by0
        else:
            ay = min(max(p["yy"], by0), by1)
            ax = bx1 if p["xx"] > cx else bx0
        # stop arrow slightly short of the dot
        vx, vy = p["xx"] - ax, p["yy"] - ay
        dist = math.hypot(vx, vy) or 1
        end_x = p["xx"] - vx / dist * 7
        end_y = p["yy"] - vy / dist * 7
        p["arrow"] = (ax, ay, end_x, end_y)

    # Draw unlabeled first (dots only), then labeled on top
    for p in unlabeled + labeled:
        tip_json = H.escape(json.dumps(p["tip"], ensure_ascii=False), quote=True)
        zoom = p.get("zoom") or ""
        cls = "ev-marker us-ev" if case == "us" or p.get("tipjson_class") else "ev-marker us-ev"
        # Always us-ev for rich tooltip handler
        parts.append(
            f'<g class="{cls}" data-eid="{p["eid"]}" data-zoom="{zoom}" data-tipjson="{tip_json}" style="cursor:pointer">'
        )
        # hidden vertical guide — shown on hover/pulse
        parts.append(
            f'<line class="vguide" x1="{p["xx"]:.1f}" y1="{pt}" x2="{p["xx"]:.1f}" y2="{h-pb}" '
            f'stroke="{p["color"]}" stroke-width="1.1" stroke-dasharray="3 3" opacity="0"/>'
        )
        if p.get("show_label") and "arrow" in p:
            ax, ay, ex, ey = p["arrow"]
            bx0, by0, bx1, by1 = p["box"]
            parts.append(
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                f'stroke="#374151" stroke-width="1.15" marker-end="url(#{mid})"/>'
            )
            # label text
            ty = by0 + 11
            for i, line in enumerate(p["lines"]):
                weight = "700" if i == 0 else "500"
                fill = "#111827" if i == 0 else "#374151"
                parts.append(
                    f'<text x="{bx0:.1f}" y="{ty:.1f}" fill="{fill}" font-size="11" '
                    f'font-family="sans-serif" font-weight="{weight}">{H.escape(line)}</text>'
                )
                ty += 13
        parts.append(
            f'<circle cx="{p["xx"]:.1f}" cy="{p["yy"]:.1f}" r="4.5" fill="{p["color"]}" stroke="#fff" stroke-width="1.5"/>'
        )
        parts.append("</g>")

    # legend
    lx, ly = pl, h - pb + 22
    for name, plot, full, color, file in series:
        need = 14 + sum((11 if ord(c) > 0x2E80 else 6.5) for c in name) + 16
        if lx + need > w - pr:
            lx = pl
            ly += 15
        parts.append(f'<rect x="{lx}" y="{ly-9}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly}" fill="#333" font-size="11" font-family="sans-serif">{H.escape(name)}</text>')
        lx += need

    parts.append("</svg>")
    return "\n".join(parts)


def load_us_tips():
    tips = {}
    path = ROOT / "data" / "events" / "us_bubble_warning_events.csv"
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                tips[r["eid"]] = {
                    "company": r["company"],
                    "layer": r.get("layer", ""),
                    "event": r["short"],
                    "fiscal": r["fiscal"],
                    "disclose": r["disclose"],
                    "confirm": r["confirm"],
                    "mark_date": r["mark_date"],
                    "metric": r["metric"],
                    "prev2": [r["prev2_a"], r["prev2_b"]],
                    "curr": r["curr"],
                    "source": r["source"],
                    "vs_nasdaq": r.get("nasdaq_lag_note", "").split("；")[0].replace("相对纳指见顶：", "")
                    if r.get("nasdaq_lag_note")
                    else "",
                    "lag_nasdaq": "",
                    "company_peak": "",
                    "lag_company_peak": "",
                }
    return tips


def main():
    tips = load_us_tips()

    us_events = [
        dict(
            eid="cisco_gm_peak",
            file="CSCO",
            mark_date="1998-08-04",
            color="#0b5f6b",
            lines=["1998年8月", "思科毛利率见顶"],
            show_label=True,
            zoom="cisco_gm_peak",
            tip=tips.get("cisco_gm_peak", {}),
        ),
        dict(
            eid="cisco_gm_confirm",
            file="CSCO",
            mark_date="1998-11-10",
            color="#0b5f6b",
            lines=["1998年11月", "毛利率高点确认"],
            show_label=False,
            zoom="cisco_gm_peak",
            tip=tips.get("cisco_gm_confirm", {}),
        ),
        dict(
            eid="amzn_fcf_neg",
            file="AMZN",
            mark_date="1999-10-29",
            color="#166534",
            lines=["1999年10月", "亚马逊FCF持续为负"],
            show_label=True,
            zoom="",
            tip=tips.get("amzn_fcf_neg", {}),
        ),
        dict(
            eid="cisco_gp_peak_print",
            file="CSCO",
            mark_date="2001-02-07",
            color="#0b5f6b",
            lines=["2001年2月", "思科毛利额峰值披露"],
            show_label=True,
            zoom="cisco_rev_peak",
            tip=tips.get("cisco_gp_peak_print", {}),
        ),
        dict(
            eid="corning_earn_peak",
            file="GLW",
            mark_date="2001-01-24",
            color="#b45309",
            lines=["2001年1月", "康宁分部盈利峰值"],
            show_label=False,
            zoom="",
            tip=tips.get("corning_earn_peak", {}),
        ),
        dict(
            eid="corning_earn_confirm",
            file="GLW",
            mark_date="2001-04-26",
            color="#b45309",
            lines=["2001年4月", "康宁盈利高点确认"],
            show_label=False,
            zoom="",
            tip=tips.get("corning_earn_confirm", {}),
        ),
        dict(
            eid="bs_fcf_neg",
            file="VZ",
            mark_date="2001-05-07",
            color="#9f1239",
            lines=["2001年5月", "BellSouth FCF首次转负"],
            show_label=True,
            zoom="verizon_fcf_proxy",
            tip=tips.get("bs_fcf_neg", {}),
        ),
        dict(
            eid="cisco_gp_confirm_yoy",
            file="CSCO",
            mark_date="2001-05-09",
            color="#b45309",
            lines=["2001年5月", "思科毛利额确认/同比降"],
            show_label=False,
            zoom="cisco_rev_peak",
            tip=tips.get("cisco_gp_confirm_yoy", {}),
        ),
        dict(
            eid="vz_fcf_ongoing",
            file="VZ",
            mark_date="2001-05-15",
            color="#9f1239",
            lines=["2001年5月", "Verizon FCF持续为负"],
            show_label=False,
            zoom="verizon_fcf_proxy",
            tip=tips.get("vz_fcf_ongoing", {}),
        ),
    ]

    us_svg = build_chart(
        case="us",
        title="美国互联网周期：复权股价归一化（起点=100）· 1998–2002",
        start="1998-01-01",
        end="2002-12-31",
        series_spec=[
            ("Cisco 卖方", "CSCO", "#0b5f6b"),
            ("Corning 上游", "GLW", "#b45309"),
            ("Verizon 买方", "VZ", "#9f1239"),
            ("亚马逊 应用", "AMZN", "#166534"),
            ("纳斯达克基准", "IXIC", "#6b7280"),
        ],
        events=us_events,
        market_ref={
            "date": NASDAQ_PEAK,
            "file": "IXIC",
            "lines": ["2000年3月10日", "纳斯达克见顶"],
            "tip": {
                "company": "纳斯达克综合指数",
                "event": "收盘见顶",
                "fiscal": "—",
                "disclose": "2000-03-10",
                "confirm": "2000-03-10",
                "mark_date": "2000-03-10",
                "metric": "收盘点位",
                "prev2": ["—", "—"],
                "curr": "5048.62",
                "source": "Yahoo Finance IXIC",
                "vs_nasdaq": "同日",
            },
        },
        w=1000,
        h=460,
    )

    cn_events = [
        dict(
            eid="china_infra_pulse",
            file="000001SS",
            mark_date="2004-01-29",
            color="#b45309",
            lines=["2004年1月", "基建投资脉冲"],
            show_label=True,
            zoom="",
            tip={
                "company": "宏观/上证代理",
                "event": "基建投资脉冲",
                "fiscal": "2003FY",
                "disclose": "2004-01-20",
                "mark_date": "2004-01-29",
                "source": "宏观序列；股价落点用上证综指代理",
            },
        ),
        dict(
            eid="conch_gm_peak",
            file="0914HK",
            mark_date="2004-09-15",
            color="#166534",
            lines=["2004年9月", "海螺毛利率见顶"],
            show_label=True,
            zoom="conch_gm_peak",
            tip={
                "company": "海螺水泥",
                "event": "毛利率阶段高点",
                "fiscal": "2004H1",
                "disclose": "2004-09-15",
                "mark_date": "2004-09-15",
                "source": "data/conch_cement.csv",
            },
        ),
        dict(
            eid="china_sales_crash",
            file="000001SS",
            mark_date="2008-12-15",
            color="#9f1239",
            lines=["2008年12月", "销售面积转负"],
            show_label=True,
            zoom="",
            tip={
                "company": "宏观/上证代理",
                "event": "商品房销售面积转负",
                "fiscal": "2008FY",
                "disclose": "2008-12-15",
                "mark_date": "2008-12-15",
                "source": "宏观销售面积序列",
            },
        ),
    ]

    # Check which China price files exist
    cn_series = []
    for name, file, color in [
        ("海螺水泥 卖方", "0914HK", "#0b5f6b"),
        ("华润置地 买方代理", "1109HK", "#9f1239"),
        ("上证综指基准", "000001SS", "#6b7280"),
    ]:
        if (PRICES / f"{file}.csv").exists():
            cn_series.append((name, file, color))

    cn_svg = build_chart(
        case="cn",
        title="中国建设/地产周期：复权股价归一化（起点=100）· 2002–2008",
        start="2002-01-01",
        end="2008-12-31",
        series_spec=cn_series,
        events=cn_events,
        w=980,
        h=420,
    )

    ai_events = [
        dict(
            eid="nvda_gm_high",
            file="NVDA",
            mark_date="2024-05-22",
            color="#0b5f6b",
            lines=["2024年5月", "英伟达毛利率阶段高点"],
            show_label=True,
            zoom="nvda_gm_stage_high",
            tip={
                "company": "NVIDIA",
                "event": "毛利率阶段高点",
                "fiscal": "FY25Q1",
                "disclose": "2024-05-22",
                "mark_date": "2024-05-22",
                "source": "data/nvidia.csv",
            },
        ),
        dict(
            eid="googl_fcf_neg",
            file="GOOGL",
            mark_date="2026-07-23",
            color="#9f1239",
            lines=["2026年7月", "Alphabet单季FCF转负"],
            show_label=True,
            zoom="googl_fcf_first_neg",
            tip={
                "company": "Alphabet",
                "event": "单季 FCF 转负",
                "fiscal": "2026Q2",
                "disclose": "2026-07-23",
                "mark_date": "2026-07-23",
                "prev2": ["2026Q1 FCF $10.1B", "2025Q4 FCF $24.6B"],
                "curr": "2026Q2 FCF −$5.9B",
                "ocf": "OCF $39.1B",
                "capex": "现金 CapEx $44.9B",
                "driver": "CapEx 增加（OCF 仍正）",
                "source": "Alphabet 2026Q2；data/alphabet.csv",
            },
        ),
        dict(
            eid="googl_fcf_neg2",
            file="GOOGL",
            mark_date="2026-10-29",
            color="#9f1239",
            lines=["2026年10月", "单季FCF连续转负"],
            show_label=False,
            zoom="",
            tip={
                "company": "Alphabet",
                "event": "单季 FCF 连续转负",
                "fiscal": "2026Q3",
                "disclose": "2026-10-29",
                "mark_date": "2026-10-29",
                "prev2": ["2026Q2 FCF −$5.9B", "2026Q1 FCF $10.1B"],
                "curr": "2026Q3 FCF −$9.1B",
                "ocf": "OCF $42.3B",
                "capex": "现金 CapEx $51.4B",
                "driver": "CapEx 继续上升",
                "source": "Alphabet 2026Q3；data/alphabet.csv",
            },
        ),
    ]

    ai_series = []
    for name, file, color in [
        ("NVIDIA 卖方", "NVDA", "#0b5f6b"),
        ("Alphabet 买方", "GOOGL", "#9f1239"),
        ("Microsoft 买方交叉", "MSFT", "#b45309"),
        ("标普500基准", "GSPC", "#6b7280"),
    ]:
        if (PRICES / f"{file}.csv").exists():
            ai_series.append((name, file, color))

    # AI end date from available data
    ai_end = "2026-12-31"
    ai_svg = build_chart(
        case="ai",
        title="AI 周期：复权股价归一化（起点=100）· 2020–最新",
        start="2020-01-01",
        end=ai_end,
        series_spec=ai_series,
        events=ai_events,
        w=980,
        h=440,
    )

    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")

    for cid, svg in [("chart-us", us_svg), ("chart-cn", cn_svg), ("chart-ai", ai_svg)]:
        html = re.sub(
            rf'(<div class="chart long-chart" id="{cid}">).*?(</div>)',
            lambda m, s=svg: m.group(1) + s + m.group(2),
            html,
            count=1,
            flags=re.S,
        )

    # CSS: hide vguide unless hover/pulse; style callouts
    css = """
.long-chart .ev-marker .vguide{opacity:0;transition:opacity .15s}
.long-chart .ev-marker:hover .vguide,
.long-chart .ev-marker.pulse .vguide,
.long-chart .ev-marker:focus-within .vguide{opacity:.75}
.long-chart .ev-marker text{pointer-events:none}
.long-chart .market-ref{pointer-events:none}
"""
    if ".ev-marker .vguide" not in html:
        html = html.replace("</style>", css + "\n</style>")

    # Update US caption toward callout reading style
    html = re.sub(
        r'(id="chart-us">.*?</div>\s*)<p class="caption">.*?</p>',
        r'\1<p class="caption">默认视图直接显示<strong>日期＋关键事件</strong>；短箭头指向该公司股价曲线上的圆点。密集区间其余事件仅保留可悬停圆点；竖线在悬停/选中时出现。浅灰虚线为纳指见顶参照。</p>',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'(id="chart-cn">.*?</div>\s*)<p class="caption">.*?</p>',
        r'\1<p class="caption">标签为日期＋事件，箭头指向对应曲线圆点。华润置地为开发商买方股价代理；宏观事件圆点落在上证综指代理曲线。</p>',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'(id="chart-ai">.*?</div>\s*)<p class="caption">.*?</p>',
        r'\1<p class="caption">默认显示英伟达毛利率阶段高点与 Alphabet 单季 FCF 转负；连续转负保留为可悬停圆点。悬停/点击查看财季、OCF/CapEx 与来源。</p>',
        html,
        count=1,
        flags=re.S,
    )

    html_path.write_text(html, encoding="utf-8")
    Path("/cursor/stores/self/docs/cycle-peak-framework.html").write_text(html, encoding="utf-8")
    print("US labels", sum(1 for e in us_events if e["show_label"]) + 1)  # +nasdaq
    print("done", html_path.stat().st_size)


if __name__ == "__main__":
    main()
