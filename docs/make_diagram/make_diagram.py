"""The radar's flow as an animated SVG and a GIF: dots travel the connectors.

  python docs/make_diagram/make_diagram.py <oss-zh|oss-en> <out-basename> [--plain]

What 0.3 and 0.4 added is drawn in purple, with a NEW tag; --plain draws it like the rest.
rsvg-convert renders each frame (it does not run SVG animation) and ffmpeg joins them.
"""
import math, subprocess, sys, tempfile
from pathlib import Path

W, H = 760, 956
FONT = "Hiragino Sans GB, PingFang SC, Noto Sans CJK SC, sans-serif"
AMB = dict(fill="#FAECE7", stroke="#993C1D", title="#712B13", sub="#993C1D")
GRY = dict(fill="#F1EFE8", stroke="#5F5E5A", title="#444441", sub="#5F5E5A")
GRN = dict(fill="#E1F5EE", stroke="#0F6E56", title="#085041", sub="#0F6E56")
BLU = dict(fill="#E6F1FB", stroke="#185FA5", title="#0C447C", sub="#185FA5")
NEW = dict(fill="#EEEDFE", stroke="#534AB7", title="#3C3489", sub="#534AB7")
NEW_INK = "#534AB7"
CREDIT_TABLE = "子木 @CoderJeffLee"
CREDIT_SOURCE = "by 饭特稀 | Fentix @fantexi997"

# A line that starts with "+" is new in 0.3 / 0.4: drawn in purple, without the "+".
ZH = {
    "s1": ("① X 与 HF", "每次运行", "HF Spaces 热门 demo"), "s2": ("② GitHub", "爆发仓库"),
    "s3": ("③ sitemap 与新站", "新页 · 新域名", "8 个工具导航站"), "s4": ("④ 搜索控制台", "首次曝光的词 · 可选"),
    "s6": ("⑥ 收入 · ⑦ 求助", "TrustMRR · Reddit", "每周"),
    "s7": ("⑧⑨⑩ 官方 · HN · PH", "RSS · HN · Product Hunt", "每天"),
    "slow": ("慢线（每周）", "Google suggest → 组合词"),
    "judge": ("名字判断：是具体名字吗", "0.5 算名字 · 0.8 才读", "格式/⚡ 标记"),
    "known": ("剔除你已经覆盖的词",),
    "sources": ("源头报告（sources）", "X + HF · 有新名字才出"),
    "table": ("新词表：名字 + 它背后的通用词", "取证 → 提词 → 筛选 → 量 → Trends → 首页"),
    "page": ("首页竞争", "弱站 · KD · 广告 · 已有页面 · 在投广告", "首页挤满的「优先」降为「观察 ↓」"),
    "evidence": ("取证（AIsa）", "高赞推文 · README", "付费产品的自述"),
    "goany": ("GoAnyAPI（可选）", "相关查询 · 美国日走势", CREDIT_SOURCE),
    "daily": ("日报（每天一次）", "新词表 + 候选 + 复盘", "线索存入 radar.db", "+报告含精度段"),
    "review": ("复盘：快线 1/3/7/14 · 慢线 14/30", "1/3 天免费 · 7/14/30 天查 Trends", "命中率展示在日报"),
    "credit": f"建议：{CREDIT_TABLE}",
    "use_h": "三种接口 + 慢线周报",
    "use": [("命令行 + 定时任务", "daily · sources", "keywords · leads"), ("MCP 服务器", "查线索 · 出新词表", "跑一次"),
            ("慢线周报", "slow · 组合词", "--free 只列候选"), ("pains 痛点命令", "Chrome 低星评论", "Reddit · 教程评论")],
    "tag": "新增",
    "legend": ("信号与取证", "报告产出", "新词表", "后加（M3–M5）", "复盘结果进日报"),
}
EN = {
    "s1": ("① X and HF", "per run", "trending HF Spaces"), "s2": ("② GitHub", "breakout repos"),
    "s3": ("③ sitemaps", "new pages · new sites", "8 tool directories"), "s4": ("④ Search Console", "optional"),
    "s6": ("⑥ revenue · ⑦ asks", "TrustMRR · Reddit", "weekly"),
    "s7": ("⑧⑨⑩ official", "HN · Product Hunt", "daily"),
    "slow": ("Slow lane (weekly)", "Google suggest → combos"),
    "judge": ("Name judge: a name, or a word?", "0.5 names it · 0.8 reads it", "format/⚡ marks"),
    "known": ("Drop the terms you already cover",),
    "sources": ("Sources report (sources)", "X + HF · only on a new name"),
    "table": ("Keyword table: names + generic terms", "evidence → phrases → screen → volume → Trends → page one"),
    "page": ("Page one", "weak sites · KD · ads · pages built · advertisers", "a crowded \"prioritize\" becomes \"watch ↓\""),
    "evidence": ("Evidence (AIsa)", "top posts · README", "a paying product's own words"),
    "goany": ("GoAnyAPI (optional)", "related queries · US curve", CREDIT_SOURCE),
    "daily": ("Daily report (once a day)", "table + leads + review", "leads in radar.db", "+precision section"),
    "review": ("Review: fast 1/3/7/14 · slow 14/30", "1/3 free · 7/14/30 Trends", "hit rate in the daily"),
    "credit": f"Idea: {CREDIT_TABLE}",
    "use_h": "Three interfaces + slow weekly",
    "use": [("Command line", "daily · sources", "keywords · leads"), ("MCP server", "leads · keyword table", "run"),
            ("Slow lane weekly", "slow · combos", "--free lists them"), ("pains command", "Chrome reviews", "Reddit · tutorials")],
    "tag": "NEW",
    "legend": ("signals · evidence", "reports", "keyword table", "added M3–M5", "review in the daily"),
}
VARIANTS = {"oss-zh": ZH, "oss-en": EN}


def width(text, size):   # a CJK glyph is about a square, a Latin one about half
    return sum(size if ord(ch) > 0x2E7F else size * 0.6 for ch in text)


def tag(x, y, label):
    w = width(label, 10) + 10
    return (f'<rect x="{x - w:.0f}" y="{y - 8}" width="{w:.0f}" height="15" rx="7.5" fill="{NEW_INK}"/>'
            f'<text x="{x - w / 2:.0f}" y="{y + 3}" font-size="10" fill="#FFFFFF" font-weight="600">{label}</text>')


def box(x, y, w, h, c, lines, marks, dashed=False, new=False, title_dy=0):
    """A box; `new` draws it purple with a tag, a line starting with "+" is a new line inside an old box."""
    if new and marks:
        c = NEW
    title, *subs = lines
    cx = x + w / 2
    dash = ' stroke-dasharray="5 3"' if dashed else ""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{c["fill"]}" stroke="{c["stroke"]}" '
           f'stroke-width="{1.2 if new and marks else 1 if dashed else 0.5}"{dash}/>']
    ty = y + h / 2 + 5 - 9 * len(subs) + title_dy
    out.append(f'<text x="{cx}" y="{ty}" fill="{c["title"]}" font-weight="500">{title}</text>')
    for i, s in enumerate(subs):
        fresh = s.startswith("+")
        ink = NEW_INK if fresh and marks else c["sub"]
        text = s[1:] if fresh else s
        weight = ' font-weight="600"' if fresh and marks else ""
        out.append(f'<text x="{cx}" y="{ty + 19 + 16.5 * i}" fill="{ink}" font-size="{11 if "@" in s else 12}"{weight}>{text}</text>')
    if marks and (new or any(s.startswith("+") for s in subs)):
        out.append(tag(x + w - 4, y + 2, T_TAG[0]))
    return "\n".join(out)


T_TAG = ["NEW"]

# id, points, colour, dashed, new, dot duration (s), dot begin (s)
PATHS = [
    ("p1", [(110, 100), (330, 140)], "#D85A30", False, False, 2.4, 0.0),
    ("p2", [(290, 100), (360, 140)], "#D85A30", False, False, 2.4, 0.6),
    ("p3", [(470, 100), (400, 140)], "#D85A30", False, False, 2.4, 1.2),
    ("p4", [(650, 100), (430, 140)], "#D85A30", False, False, 2.4, 1.8),
    ("p6", [(220, 179), (240, 179)], "#D85A30", False, False, 1.2, 0.2),
    ("p7", [(540, 179), (520, 179)], "#7F77DD", False, True, 1.2, 0.8),
    ("p7b", [(730, 179), (748, 179), (748, 432), (730, 432)], "#7F77DD", False, True, 2.8, 0.4),
    ("p5", [(380, 218), (380, 246)], "#888780", False, False, 1.2, 0.3),
    ("p8", [(300, 290), (130, 318)], "#1D9E75", False, False, 1.6, 0.0),
    ("p9", [(440, 290), (495, 318)], "#378ADD", False, False, 1.6, 0.4),
    ("p10", [(370, 506), (370, 474)], "#D85A30", False, False, 1.4, 0.8),
    ("p11", [(615, 506), (615, 474)], "#378ADD", True, False, 1.4, 1.2),
    ("p12", [(130, 378), (130, 646), (170, 646)], "#1D9E75", False, False, 2.4, 0.2),
    ("p13", [(260, 446), (245, 446), (245, 610)], "#378ADD", False, False, 1.8, 0.6),
    ("p14", [(590, 738), (650, 738), (650, 646), (590, 646)], "#888780", True, False, 4.8, 0.0),
    ("p15", [(230, 268), (236, 268), (236, 310), (260, 318)], "#7F77DD", True, True, 2.0, 0.5),
]
DASH = ' stroke-dasharray="4 3"'


def scene(T, marks):
    T_TAG[0] = T["tag"]
    uses = [box(30 + 180 * i, 832, 160, 72, c, T["use"][i], marks, new=False) for i, c in enumerate((GRY, BLU, BLU, GRY))]
    boxes = "\n".join([
        box(30, 36, 160, 64, AMB, T["s1"], marks), box(210, 36, 160, 64, AMB, T["s2"], marks),
        box(390, 36, 160, 64, AMB, T["s3"], marks), box(570, 36, 160, 64, AMB, T["s4"], marks),
        box(30, 140, 190, 78, AMB, T["s6"], marks), box(240, 140, 280, 78, GRY, T["judge"], marks),
        box(540, 140, 190, 78, AMB, T["s7"], marks, new=True),
        box(240, 246, 280, 44, GRY, T["known"], marks),
        box(30, 246, 200, 44, AMB, T["slow"], marks, new=True),
        box(30, 318, 200, 60, GRN, T["sources"], marks),
        box(260, 318, 470, 156, BLU, T["table"], marks, title_dy=-48),
        box(276, 388, 438, 74, BLU, T["page"], marks),
        box(260, 506, 220, 72, AMB, T["evidence"], marks), box(500, 506, 230, 72, BLU, T["goany"], marks, dashed=True),
        box(170, 610, 420, 72, GRN, T["daily"], marks), box(170, 710, 420, 56, GRY, T["review"], marks),
        *uses,
    ])
    lines = "\n".join(f'<path id="{i}" d="M{" L".join(f"{x} {y}" for x, y in p)}" fill="none" stroke="{c if marks or not new else "#888780"}" '
                      f'stroke-width="{1.4 if new and marks else 1}"{DASH if dash else ""} marker-end="url(#arrow)"/>'
                      for i, p, c, dash, new, *_ in PATHS)
    use = (f'<path d="M30 808 H730" stroke="#D3D1C7" stroke-width="0.5" fill="none"/>'
           f'<text x="30" y="824" font-size="12" fill="#5F5E5A" font-weight="500">{T["use_h"]}</text>')
    notes = use + f'<text x="730" y="311" text-anchor="end" font-size="11" fill="#185FA5">{T["credit"]}</text>'
    legend_y = 924
    swatches = [f'fill="{AMB["fill"]}" stroke="{AMB["stroke"]}" stroke-width="0.5"', f'fill="{GRN["fill"]}" stroke="{GRN["stroke"]}" stroke-width="0.5"',
                f'fill="{BLU["fill"]}" stroke="{BLU["stroke"]}" stroke-width="0.5"', f'fill="{NEW["fill"]}" stroke="{NEW["stroke"]}" stroke-width="1.2"']
    labels = list(T["legend"]) if marks else [s for i, s in enumerate(T["legend"]) if i != 3]
    kinds = ["sw0", "sw1", "sw2", "sw3", "line"] if marks else ["sw0", "sw1", "sw2", "line"]
    widths = [22 + width(s, 12) if k != "line" else 38 + width(s, 12) for s, k in zip(labels, kinds)]
    gap = (W - 60 - sum(widths)) / (len(labels) - 1)
    x, legend = 30, ""
    for label, kind, w in zip(labels, kinds, widths):
        if kind == "line":
            legend += (f'<path d="M{x:.0f} {legend_y + 7} H{x + 30:.0f}" stroke="#888780" stroke-width="1" stroke-dasharray="4 3" fill="none"/>'
                       f'<text x="{x + 38:.0f}" y="{legend_y + 12}" font-size="12" fill="#444441">{label}</text>')
        else:
            legend += (f'<rect x="{x:.0f}" y="{legend_y}" width="14" height="14" rx="3" {swatches[int(kind[2])]}/>'
                       f'<text x="{x + 22:.0f}" y="{legend_y + 12}" font-size="12" fill="#444441">{label}</text>')
        x += w + gap
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * 2}" height="{H * 2}" viewBox="0 0 {W} {H}" font-family="{FONT}">\n'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>\n'
            f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>\n')
    return head, f'{lines}\n<g font-size="14" text-anchor="middle">\n{boxes}\n</g>\n{notes}\n{legend}\n'


def at(points, f):
    seg = [math.dist(a, b) for a, b in zip(points, points[1:])]
    left = f * sum(seg)
    for (a, b), s in zip(zip(points, points[1:]), seg):
        if left <= s:
            k = left / s if s else 0
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        left -= s
    return points[-1]


def main(variant, base, marks=True):
    head, body = scene(VARIANTS[variant], marks)
    colour = lambda c, new: c if marks or not new else "#888780"  # noqa: E731
    smil = "\n".join(f'<circle r="{4.5 if new and marks else 4}" fill="{colour(c, new)}"><animateMotion dur="{dur}s" repeatCount="indefinite" '
                     f'begin="{b}s"><mpath href="#{i}"/></animateMotion></circle>' for i, _, c, _, new, dur, b in PATHS)
    Path(base + ".svg").write_text(head + body + smil + "\n</svg>\n")
    fps, seconds = 15, 4.8
    with tempfile.TemporaryDirectory() as tmp:
        for n in range(int(fps * seconds)):
            tm = n / fps
            dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4.5 if new and marks else 4}" fill="{colour(c, new)}"/>'
                           for _, p, c, _, new, dur, b in PATHS for x, y in [at(p, ((tm - b) % dur) / dur)])
            f = Path(tmp) / f"f{n:03d}.svg"
            f.write_text(head.replace("context-stroke", "#888780") + body + dots + "\n</svg>\n")
            subprocess.run(["rsvg-convert", "-w", str(W * 2), "-b", "white", str(f), "-o", str(f.with_suffix(".png"))], check=True)
        frames = ["-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{tmp}/f%03d.png"]
        subprocess.run(["ffmpeg", *frames, "-vf", "scale=1140:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none",
                        base + ".gif"], check=True)
        subprocess.run(["cp", f"{tmp}/f030.png", base + ".png"], check=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], marks="--plain" not in sys.argv)
