#!/usr/bin/env python3
"""Rebuild US internet multi-year price chart with pre-bubble warning annotations."""
from __future__ import annotations

import csv
import html as H
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/agent/cycle-peaks")
PRICES = ROOT / "data" / "prices"
DATA = ROOT / "data"
NASDAQ_PEAK = "2000-03-10"


def load_px(name: str):
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


def days_between(a, b):
    return (parse(b) - parse(a)).days


def fmt_days(n):
    if n is None:
        return "—"
    q = n / 91.25
    if n < 0:
        lead = "领先"
    elif n > 0:
        lead = "滞后"
    else:
        lead = "同日"
    return f"{lead} {abs(n)} 日（约 {abs(q):.1f} 季）"


def est_w(s, size=10):
    return sum(size if ord(c) > 0x2E80 else size * 0.62 for c in s)


def peak_date(file, a, b):
    rows = filter_range(load_px(file), a, b)
    return max(rows, key=lambda x: x[1])[0]


CSCO_PEAK = peak_date("CSCO", "1998-01-01", "2002-12-31")
GLW_PEAK = peak_date("GLW", "1998-01-01", "2002-12-31")
VZ_PEAK = peak_date("VZ", "1998-01-01", "2002-12-31")
AMZN_PEAK = peak_date("AMZN", "1998-01-01", "2002-12-31")

events = [
    # Cisco GM% — visible well before Nasdaq peak
    dict(
        eid="cisco_gm_peak",
        zoom="cisco_gm_peak",
        file="CSCO",
        color="#166534",
        short="毛利率峰值",
        company="Cisco",
        layer="上游卖方",
        fiscal="FY1998 Q4（截止 1998-07-25）",
        disclose="1998-08-04",
        confirm="1998-11-10",
        confirm_note="峰值数值当日已披露；下一季 FY1999 Q1 GM% 65.46% < 65.73% 后，阶段高点可确认",
        mark_date="1998-08-04",
        metric="GAAP 毛利率 %",
        prev2=("FY1998 Q3 65.67%", "FY1998 Q2 65.44%"),
        curr="FY1998 Q4 65.73%",
        source="Cisco newsroom FY1998 Q4（1998-08-04）；data/cisco.csv",
    ),
    dict(
        eid="cisco_gm_confirm",
        zoom="cisco_gm_peak",
        file="CSCO",
        color="#166534",
        short="毛利率高点确认",
        company="Cisco",
        layer="上游卖方",
        fiscal="峰值财季 FY1998 Q4",
        disclose="1998-08-04",
        confirm="1998-11-10",
        confirm_note="确认信息公开日=下一季披露日；图上按确认后首个可交易日标注",
        mark_date="1998-11-10",
        metric="GAAP 毛利率 %",
        prev2=("峰值季 65.73%", "确认季 FY1999 Q1 65.46%"),
        curr="确认：未再创新高",
        source="Cisco 季报序列 / data/cisco.csv",
    ),
    # Amazon FCF persistent negative — further worsening visible near late-1999
    dict(
        eid="amzn_fcf_neg",
        zoom="",
        file="AMZN",
        color="#166534",
        short="FCF持续为负",
        company="Amazon",
        layer="互联网应用",
        fiscal="1999Q3（进一步恶化可见）",
        disclose="1999-10-28",
        confirm="1999-11-15",
        confirm_note="自上市后至泡沫前后经营现金流长期为负，不是“首次由正转负”。1999-10-28 盘后业绩稿已显示扩张期亏损加深；完整现金流量表见 1999-11-15 10-Q。标注日取盘后披露后的首个可交易日 1999-10-29。",
        mark_date="1999-10-29",
        metric="FCF=OCF−购建固定资产",
        prev2=("1998Q1 FCF≈−$8.6M", "1999Q3 OCF −$75.6M / Capex $70.8M（对比表）"),
        curr="1999Q3 FCF≈−$146.3M（进一步恶化）",
        source="SEC 10-Q / 1999-10-28 业绩披露；1999-11-15 Form 10-Q",
    ),
    # Cisco GP$ peak — fiscal peak AFTER Nasdaq; disclose then confirm
    dict(
        eid="cisco_gp_peak_print",
        zoom="cisco_rev_peak",
        file="CSCO",
        color="#0b5f6b",
        short="毛利额峰值披露",
        company="Cisco",
        layer="上游卖方",
        fiscal="FY2001 Q2（截止 2001-01-27）",
        disclose="2001-02-06",
        confirm="2001-05-08",
        confirm_note="当日披露毛利额 $4167M，当时尚不知是否为高点；下一季骤降后才确认。盘后披露→标注 2001-02-07。",
        mark_date="2001-02-07",
        metric="GAAP 毛利额（GROSS MARGIN $）",
        prev2=("FY2001 Q1 $4141M", "FY2000 Q4 $3662M"),
        curr="FY2001 Q2 $4167M（窗口峰值）",
        source="Cisco newsroom 2001-02-06；SEC 8-K；data/cisco.csv",
    ),
    dict(
        eid="corning_earn_peak",
        zoom="",
        file="GLW",
        color="#b45309",
        short="分部盈利峰值",
        company="Corning 电信分部",
        layer="上游的上游/光纤",
        fiscal="2000Q4（截止 2000-12-31）",
        disclose="2001-01-24",
        confirm="2001-04-26",
        confirm_note="分部无完整 GM%；以分部盈利为利润代理。峰值披露时点已在纳指见顶之后。",
        mark_date="2001-01-24",
        metric="电信分部盈利",
        prev2=("2000Q3 $203M", "2000Q2 $181M"),
        curr="2000Q4 $212M",
        source="Corning 8-K / press release 2001-01-24；data/corning_telecom.csv",
    ),
    dict(
        eid="corning_earn_confirm",
        zoom="",
        file="GLW",
        color="#b45309",
        short="分部盈利高点确认",
        company="Corning 电信分部",
        layer="上游的上游/光纤",
        fiscal="峰值财季 2000Q4",
        disclose="2001-01-24",
        confirm="2001-04-26",
        confirm_note="2001Q1 分部盈利 $177M < 峰值 $212M，高点确认",
        mark_date="2001-04-26",
        metric="电信分部盈利",
        prev2=("峰值 $212M", "确认季 $177M"),
        curr="高点确认",
        source="Corning 8-K 2001-04-26；data/corning_telecom.csv",
    ),
    dict(
        eid="bs_fcf_neg",
        zoom="verizon_fcf_proxy",
        file="VZ",
        color="#9f1239",
        short="FCF首次转负",
        company="BellSouth（买方样本）",
        layer="电信运营商买方",
        fiscal="2001Q1（截止 2001-03-31）",
        disclose="2001-05-07",
        confirm="2001-05-07",
        confirm_note="样本自 2000Q1 起有季频；1998–99 连续季频未齐。BellSouth 已退市，圆点落在同相位 Verizon 股价。",
        mark_date="2001-05-07",
        metric="FCF=OCF−现金CapEx",
        prev2=("2000Q2 FCF +$743M", "2000Q1 FCF +$787M"),
        curr="2001Q1 FCF −$86M",
        source="BellSouth Form 10-Q filed 2001-05-07；data/bellsouth.csv",
    ),
    dict(
        eid="cisco_gp_confirm_yoy",
        zoom="cisco_rev_peak",
        file="CSCO",
        color="#b45309",
        short="毛利额确认/同比降",
        company="Cisco",
        layer="上游卖方",
        fiscal="峰值 FY2001 Q2；确认/同比 FY2001 Q3（截止 2001-04-28）",
        disclose="2001-02-06",
        confirm="2001-05-08",
        confirm_note="同一披露日同时完成两件事：(1) 确认毛利额阶段高点；(2) 首次同比大幅下降（含 $2.25B 存货计提）。盘后披露→标注 2001-05-09。",
        mark_date="2001-05-09",
        metric="GAAP 毛利额 / YoY",
        prev2=("峰值季 $4167M", "去年同期 FY2000 Q3 $3171M"),
        curr="确认季 $328M（同比约 −90%）",
        source="Cisco newsroom 2001-05-08；data/cisco.csv",
    ),
    dict(
        eid="vz_fcf_ongoing",
        zoom="verizon_fcf_proxy",
        file="VZ",
        color="#9f1239",
        short="FCF持续为负(样本)",
        company="Verizon",
        layer="电信运营商买方",
        fiscal="样本起点 2001Q1（持续为负）",
        disclose="2001-05-15",
        confirm="2001-08-03",
        confirm_note="观察窗内首个可得季度已为负（−$1376M），不能判断泡沫前“由正转负”。FCF 明细以 10-Q 现金流量表为准（filed 2001-05-15）；Q2 10-Q（约 2001-08）仍为负，进一步确认样本内持续为负。",
        mark_date="2001-05-15",
        metric="FCF",
        prev2=("更早季频：缺可比", "2001Q2 FCF −$129M"),
        curr="2001Q1 FCF −$1376M",
        source="Verizon Form 10-Q filed 2001-05-15；data/verizon.csv",
    ),
]


def main():
    out_csv = DATA / "events" / "us_bubble_warning_events.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "eid",
                "short",
                "company",
                "layer",
                "fiscal",
                "disclose",
                "confirm",
                "mark_date",
                "metric",
                "prev2_a",
                "prev2_b",
                "curr",
                "source",
                "file",
                "nasdaq_lag_note",
            ],
        )
        w.writeheader()
        for e in events:
            file = e["file"]
            cpeak = {"CSCO": CSCO_PEAK, "GLW": GLW_PEAK, "VZ": VZ_PEAK, "AMZN": AMZN_PEAK}[file]
            d_mark = e["mark_date"]
            lag_nq = days_between(NASDAQ_PEAK, d_mark)
            lag_co = days_between(cpeak, d_mark)
            note = []
            note.append("相对纳指见顶：" + ("见顶后确认/披露" if lag_nq > 0 else "见顶前已公开"))
            note.append(f"vs纳指 {fmt_days(lag_nq)}")
            note.append(f"vs本公司股价高点 {fmt_days(lag_co)}")
            e["lag_note"] = "；".join(note)
            e["company_peak"] = cpeak
            w.writerow(
                {
                    "eid": e["eid"],
                    "short": e["short"],
                    "company": e["company"],
                    "layer": e["layer"],
                    "fiscal": e["fiscal"],
                    "disclose": e["disclose"],
                    "confirm": e["confirm"],
                    "mark_date": e["mark_date"],
                    "metric": e["metric"],
                    "prev2_a": e["prev2"][0],
                    "prev2_b": e["prev2"][1],
                    "curr": e["curr"],
                    "source": e["source"],
                    "file": e["file"],
                    "nasdaq_lag_note": e["lag_note"],
                }
            )

    start, end = "1998-01-01", "2002-12-31"
    wsvg, h = 1000, 440
    pl, pr, pt, pb = 54, 28, 48, 70
    series_spec = [
        ("Cisco 卖方", "CSCO", "#0b5f6b"),
        ("Corning 上游", "GLW", "#b45309"),
        ("Verizon 买方", "VZ", "#9f1239"),
        ("亚马逊 应用", "AMZN", "#166534"),
        ("纳斯达克基准", "IXIC", "#6b7280"),
    ]
    series = []
    raw_map = {}
    for name, file, color in series_spec:
        raw = filter_range(load_px(file), start, end)
        raw_map[file] = dict(raw)
        full_norm = normalize(raw)
        plot_norm = downsample(full_norm)
        series.append((name, plot_norm, full_norm, color, file))

    vals = [v for _, n, _, _, _ in series for _, v in n]
    ymin, ymax = min(vals), max(vals)
    span = ymax - ymin or 1
    ymin -= span * 0.08
    ymax += span * 0.16
    iw, ih = wsvg - pl - pr, h - pt - pb

    def x(d):
        return to_x(d, start, end, pl, wsvg - pr)

    def y(v):
        return pt + ih * (1 - (v - ymin) / (ymax - ymin))

    parts = [
        f'<svg viewBox="0 0 {wsvg} {h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" class="long-price-svg" data-case="us" overflow="visible">'
    ]
    parts.append(
        f'<text x="{pl}" y="18" fill="#5c5a55" font-size="12" font-family="sans-serif">美国互联网周期：复权股价归一化（起点=100）· 1998–2002 · 泡沫前预警检验</text>'
    )
    for g in range(5):
        gy = pt + ih * g / 4
        gv = ymax - (ymax - ymin) * g / 4
        parts.append(f'<line x1="{pl}" y1="{gy:.1f}" x2="{wsvg - pr}" y2="{gy:.1f}" stroke="#e8e4da"/>')
        parts.append(
            f'<text x="{pl - 6}" y="{gy + 4:.1f}" text-anchor="end" fill="#8a867c" font-size="10" font-family="monospace">{gv:.0f}</text>'
        )
    for yy in range(1998, 2003):
        d = f"{yy}-01-01"
        parts.append(f'<line x1="{x(d):.1f}" y1="{pt}" x2="{x(d):.1f}" y2="{h - pb}" stroke="#f0ebe3"/>')
        parts.append(f'<text x="{x(d):.1f}" y="{h - 12}" text-anchor="middle" fill="#5c5a55" font-size="10">{yy}</text>')

    for name, plot_norm, full_norm, color, file in series:
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in plot_norm)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{pts}"/>')

    nx = x(NASDAQ_PEAK)
    parts.append(
        f'<line x1="{nx:.1f}" y1="{pt}" x2="{nx:.1f}" y2="{h - pb}" stroke="#111827" stroke-width="1.8" stroke-dasharray="6 4"/>'
    )
    parts.append(
        f'<text x="{nx + 6:.1f}" y="{pt + 14}" fill="#111827" font-size="11" font-family="sans-serif">纳指见顶 2000-03-10</text>'
    )

    lx, ly = pl, h - pb + 18
    for name, plot_norm, full_norm, color, file in series:
        need = 14 + sum((11 if ord(c) > 0x2E80 else 6.5) for c in name) + 16
        if lx + need > wsvg - pr:
            lx = pl
            ly += 15
        parts.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx + 14}" y="{ly}" fill="#333" font-size="11" font-family="sans-serif">{name}</text>')
        lx += need

    by_file = {f: (name, full, color) for name, _, full, color, f in series}
    placements = []
    tooltip_payload = {}
    for e in events:
        file = e["file"]
        name, full, color = by_file[file]
        td, nv = nearest_on_or_after(full, e["mark_date"])
        if td is None:
            continue
        raw = raw_map[file].get(td)
        xx, yy = x(td), y(nv)
        lag_nq = days_between(NASDAQ_PEAK, td)
        cpeak = {"CSCO": CSCO_PEAK, "GLW": GLW_PEAK, "VZ": VZ_PEAK, "AMZN": AMZN_PEAK}[file]
        lag_co = days_between(cpeak, td)
        vs_nq = "见顶后确认" if lag_nq > 0 else "见顶前已公开"
        tip = {
            "company": e["company"],
            "layer": e["layer"],
            "event": e["short"],
            "fiscal": e["fiscal"],
            "disclose": e["disclose"],
            "confirm": e["confirm"],
            "confirm_note": e.get("confirm_note", ""),
            "mark_date": td,
            "metric": e["metric"],
            "prev2": list(e["prev2"]),
            "curr": e["curr"],
            "price": None if raw is None else round(raw, 2),
            "source": e["source"],
            "vs_nasdaq": vs_nq,
            "lag_nasdaq": fmt_days(lag_nq),
            "company_peak": cpeak,
            "lag_company_peak": fmt_days(lag_co),
        }
        tooltip_payload[e["eid"]] = tip
        placements.append(
            {
                "eid": e["eid"],
                "lab": e["short"],
                "xx": xx,
                "yy": yy,
                "color": e["color"],
                "zoom": e.get("zoom", ""),
                "td": td,
            }
        )

    placements.sort(key=lambda p: (p["xx"], p["yy"]))
    boxes = []
    for p in placements:
        lw = est_w(p["lab"]) + 8
        lh = 14
        prefer_right = p["xx"] + 14 + lw < wsvg - pr - 6
        cands = []
        for side in [1, -1] if prefer_right else [-1, 1]:
            for dy in [0, -16, 16, -32, 32, -48, 48, 64, -64, 80, -80]:
                if side > 0:
                    lx0 = p["xx"] + 12
                    ly0 = p["yy"] - 4 + dy
                    lx1 = lx0 + lw
                    ly1 = ly0 + lh
                else:
                    lx1 = p["xx"] - 12
                    ly0 = p["yy"] - 4 + dy
                    lx0 = lx1 - lw
                    ly1 = ly0 + lh
                if ly0 < pt + 2 or ly1 > h - pb - 2 or lx0 < pl + 2 or lx1 > wsvg - 4:
                    continue
                cands.append((side, lx0, ly0, lx1, ly1))

        def overlap(b):
            x0, y0, x1, y1 = b
            for a0, a1, a2, a3 in boxes:
                if not (x1 < a0 or x0 > a2 or y1 < a1 or y0 > a3):
                    return True
            return False

        chosen = None
        for side, lx0, ly0, lx1, ly1 in cands:
            if not overlap((lx0, ly0, lx1, ly1)):
                chosen = (side, lx0, ly0, lx1, ly1)
                break
        if not chosen and cands:
            chosen = (cands[0][0], *cands[0][1:])
        if not chosen:
            side = -1
            lx1 = p["xx"] - 12
            lx0 = lx1 - lw
            ly0 = max(pt + 2, p["yy"] - 24)
            lx1 = lx0 + lw
            ly1 = ly0 + lh
            chosen = (side, lx0, ly0, lx1, ly1)
        side, lx0, ly0, lx1, ly1 = chosen
        boxes.append((lx0 - 2, ly0 - 2, lx1 + 2, ly1 + 2))
        p.update(
            side=side,
            label_x=(lx0 if side > 0 else lx1),
            label_y=ly0 + 11,
            anchor=("start" if side > 0 else "end"),
            lead_x=(lx0 if side > 0 else lx1),
            lead_y=ly0 + lh / 2,
        )

    for p in placements:
        parts.append(
            f'<line x1="{p["xx"]:.1f}" y1="{pt}" x2="{p["xx"]:.1f}" y2="{h - pb}" stroke="{p["color"]}" stroke-width="1.15" stroke-dasharray="4 3" opacity="0.7"/>'
        )

    for p in placements:
        tip = tooltip_payload[p["eid"]]
        tip_json = H.escape(json.dumps(tip, ensure_ascii=False), quote=True)
        parts.append(
            f'<g class="ev-marker us-ev" data-eid="{p["eid"]}" data-zoom="{p["zoom"]}" data-tipjson="{tip_json}" style="cursor:pointer">'
            f'<line x1="{p["xx"]:.1f}" y1="{p["yy"]:.1f}" x2="{p["lead_x"]:.1f}" y2="{p["lead_y"]:.1f}" stroke="{p["color"]}" stroke-width="1" opacity="0.75"/>'
            f'<circle cx="{p["xx"]:.1f}" cy="{p["yy"]:.1f}" r="5.5" fill="{p["color"]}" stroke="#fff" stroke-width="1.6"/>'
            f'<text x="{p["label_x"]:.1f}" y="{p["label_y"]:.1f}" text-anchor="{p["anchor"]}" fill="{p["color"]}" font-size="10" font-family="sans-serif">{H.escape(p["lab"])}</text>'
            f"</g>"
        )

    parts.append("</svg>")
    us_svg = "\n".join(parts)

    verdict = f"""
<div class="answer" id="us-bubble-verdict">
  <h3>泡沫前预警检验（对照纳指见顶 {NASDAQ_PEAK}）</h3>
  <ul>
    <li><strong>见顶前已公开：</strong>Cisco <em>毛利率%</em> 峰值于 <strong>1998-08-04</strong> 披露（约领先纳指见顶 19 个月）；1998-11-10 下一季确认阶段高点。但同期毛利额与收入仍升，单独 GM% 信号未被定价为周期顶部。</li>
    <li><strong>见顶前未出现：</strong>Cisco <em>毛利额</em> 在 2000-03-10 前仍逐季上升；窗口毛利额峰值在 FY2001 Q2，<strong>2001-02-06</strong> 才披露（图上标注盘后次日），属<strong>见顶后确认</strong>（相对纳指滞后约 11 个月；相对 Cisco 股价高点 {CSCO_PEAK} 亦滞后）。</li>
    <li><strong>毛利额高点确认 + 首次同比下降：</strong>FY2001 Q3（<strong>2001-05-08</strong> 披露，标注 05-09）毛利额坍塌后，峰值与同比下降信号同日可确认。</li>
    <li><strong>Corning：</strong>分部盈利峰值财季为 2000Q4（披露 2001-01-24），确认 2001-04-26，均在纳指见顶之后。</li>
    <li><strong>买方 FCF：</strong>BellSouth 首次转负在 2001Q1（10-Q 2001-05-07，见顶后）。Verizon 样本自 2001Q1 起已为负，标<strong>持续为负（样本）</strong>，无法还原泡沫前“由正转负”。</li>
    <li><strong>应用层 Amazon：</strong>FCF 在泡沫前后<strong>持续为负</strong>；1999-10-28/29 可见扩张期进一步恶化，但不是新的“首次转负”拐点。</li>
  </ul>
</div>
"""

    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    html = re.sub(
        r'(<div class="chart long-chart" id="chart-us">)(.*?)(</div>)',
        lambda m: m.group(1) + us_svg + m.group(3),
        html,
        count=1,
        flags=re.S,
    )

    # Replace caption + verdict after chart-us (drop old verdict if present)
    html = re.sub(
        r'(id="chart-us">.*?</div>\s*)(<p class="caption">.*?</p>\s*)(<div class="answer" id="us-bubble-verdict">.*?</div>\s*)?',
        r"\1"
        + '<p class="caption">圆点落在对应公司股价曲线与<strong>标注日（披露/确认后首个可交易日；盘后披露取次日）</strong>交点；黑色虚线为纳指见顶 2000-03-10。悬停或点击圆点查看财季、前后两期数值、相对纳指/本公司股价高点的领先滞后与来源。BellSouth 已退市，其 FCF 事件圆点落在同相位 Verizon 曲线。图上默认短标签；毛利率峰值与毛利额峰值分开标注。</p>\n'
        + verdict
        + "\n",
        html,
        count=1,
        flags=re.S,
    )

    tip_css = """
  #ev-tooltip{display:none;position:fixed;z-index:40;max-width:340px;background:#111827;color:#f9fafb;padding:12px 14px;border-radius:10px;font-size:12.5px;line-height:1.45;box-shadow:0 10px 30px rgba(0,0,0,.25);pointer-events:none}
  #ev-tooltip strong{color:#fff}
  #ev-tooltip .k{color:#9ca3af;margin-top:6px}
  #ev-tooltip.show{display:block}
"""
    if "#ev-tooltip{" not in html:
        html = html.replace("</style>", tip_css + "\n</style>")

    # Remove prior tip blocks to avoid duplicates
    html = re.sub(r'<div id="ev-tooltip"[^>]*>.*?</div>\s*', "", html, flags=re.S)
    html = re.sub(
        r"<script>\s*\(function\(\)\{\s*const tip=document\.getElementById\('ev-tooltip'\);.*?\}\)\(\);\s*</script>\s*",
        "",
        html,
        flags=re.S,
    )

    tip_js = r"""
<div id="ev-tooltip" role="tooltip"></div>
<script>
(function(){
  const tip=document.getElementById('ev-tooltip');
  function render(data){
    tip.innerHTML =
      '<div><strong>'+data.company+'</strong> · '+data.event+'</div>'+
      '<div class="k">层级</div><div>'+data.layer+'</div>'+
      '<div class="k">财季 / 指标</div><div>'+data.fiscal+'<br>'+data.metric+'</div>'+
      '<div class="k">前后两期 → 当期</div><div>'+data.prev2[0]+'<br>'+data.prev2[1]+'<br><strong>'+data.curr+'</strong></div>'+
      '<div class="k">披露 / 确认 / 标注日</div><div>披露 '+data.disclose+'<br>确认 '+data.confirm+'<br>图上标注 '+data.mark_date+(data.price!=null?' · 股价 '+data.price:'')+'</div>'+
      (data.confirm_note?('<div class="k">确认说明</div><div>'+data.confirm_note+'</div>'):'')+
      '<div class="k">相对纳指见顶 2000-03-10</div><div><strong>'+data.vs_nasdaq+'</strong> · '+data.lag_nasdaq+'</div>'+
      '<div class="k">相对本公司股价阶段高点 '+data.company_peak+'</div><div>'+data.lag_company_peak+'</div>'+
      '<div class="k">来源</div><div>'+data.source+'</div>';
  }
  function showAt(evt, data){
    render(data); tip.classList.add('show');
    const cx=(evt.clientX!=null?evt.clientX:(evt.touches&&evt.touches[0]?evt.touches[0].clientX:0));
    const cy=(evt.clientY!=null?evt.clientY:(evt.touches&&evt.touches[0]?evt.touches[0].clientY:0));
    const x=Math.min(window.innerWidth-360, Math.max(8, cx+14));
    const y=Math.min(window.innerHeight-20, Math.max(8, cy+14));
    tip.style.left=x+'px'; tip.style.top=y+'px';
  }
  function hide(){ tip.classList.remove('show'); }
  document.querySelectorAll('#chart-us .us-ev').forEach(g=>{
    const raw=g.getAttribute('data-tipjson'); if(!raw) return;
    let data; try{ data=JSON.parse(raw); }catch(e){ return; }
    g.addEventListener('mouseenter', e=>showAt(e,data));
    g.addEventListener('mousemove', e=>showAt(e,data));
    g.addEventListener('mouseleave', hide);
    g.addEventListener('click', e=>{
      e.preventDefault(); e.stopPropagation();
      showAt(e,data);
      const z=g.getAttribute('data-zoom');
      if(z){
        const btn=document.querySelector('#zoom-tabs a[data-zoom="'+z+'"]');
        if(btn) btn.click();
      }
      setTimeout(hide, 8000);
    });
  });
  document.addEventListener('click', e=>{ if(!e.target.closest('.us-ev') && !e.target.closest('#ev-tooltip')) hide(); });
})();
</script>
"""
    html = html.replace("</body>", tip_js + "\n</body>")
    html_path.write_text(html, encoding="utf-8")

    store = Path("/cursor/stores/self/docs")
    store.mkdir(parents=True, exist_ok=True)
    (store / "cycle-peak-framework.html").write_text(html, encoding="utf-8")
    (store / "cycle-peak-comparison.html").write_text(html, encoding="utf-8")
    (store / "data" / "events").mkdir(parents=True, exist_ok=True)
    (store / "data" / "events" / "us_bubble_warning_events.csv").write_text(out_csv.read_text(), encoding="utf-8")

    print("events", len(events))
    for p in placements:
        print(p["eid"], p["lab"], p["td"], tooltip_payload[p["eid"]]["vs_nasdaq"])
    print("wrote", html_path, html_path.stat().st_size)


if __name__ == "__main__":
    main()
