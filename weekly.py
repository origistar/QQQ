#!/usr/bin/env python3
"""纳指100定投周报长图 —— 自动化生成（数据来自 state.json，文案可补 weekly_events.json）

- 数值（PE/VIX/评分/回撤/金额/NDX/分位）100% 取自仓库每日更新的 state.json（history 数组）
- 大事件 / 速览 / 下周建议：优先读 weekly_events.json 中当前周号对应的条目；缺省则自动兜底
- 渲染：Playwright 全页截图（本地可用系统 Chrome，云端用 playwright 自带 chromium + 中文字体）
- 产物：weekly/周报.png（长图） + weekly/index.html（网页展示，可右键保存）
"""
import json
import os
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
EVENTS = ROOT / "weekly_events.json"
TPL = ROOT / "weekly_template.html"
OUT_DIR = ROOT / "weekly"
OUT_PNG = OUT_DIR / "周报.png"
OUT_HTML = OUT_DIR / "index.html"

TIER_CN = {"low": "低估", "mid_low": "合理偏低", "mid": "合理", "high": "偏高", "sell": "高估"}
SEMANTIC = {
    "pe":    {"up": "走高", "down": "走低"},
    "vix":   {"up": "升温", "down": "缓解"},
    "score": {"up": "抬升", "down": "回落"},
    "dd":    {"up": "反弹", "down": "扩大"},
}


def load_json(p):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print("读取 JSON 失败:", p, e)
    return {}


def parse_date(s):
    return datetime.date.fromisoformat(s)


def get_week_range(today):
    # 周一~周日。若 today 是周日（Actions 周日跑），today 即本周日
    monday = today - datetime.timedelta(days=today.weekday())  # Mon=0
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def pe_to_left(pe):
    """把 PE 值映射到进度条百分比位置（刻度: 25.5→10.4%, 30.1→43.6%, 37.1→93.4%）"""
    pts = [(25.5, 10.4), (30.1, 43.6), (37.1, 93.4)]
    if pe <= pts[0][0]:
        slope = (pts[1][1] - pts[0][1]) / (pts[1][0] - pts[0][0])
        return max(2.0, pts[0][1] + slope * (pe - pts[0][0]))
    if pe >= pts[-1][0]:
        slope = (pts[-1][1] - pts[-2][1]) / (pts[-1][0] - pts[-2][0])
        return min(98.0, pts[-1][1] + slope * (pe - pts[-1][0]))
    for a, b in zip(pts, pts[1:]):
        if a[0] <= pe <= b[0]:
            t = (pe - a[0]) / (b[0] - a[0])
            return a[1] + t * (b[1] - a[1])
    return 50.0


def _pair(e):
    if isinstance(e, dict):
        return e.get("title", ""), e.get("desc", "")
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        return str(e[0]), str(e[1])
    return str(e), ""


def chg_cell(mon, sun, kind):
    if kind == "score":
        eps, fmt = 0.5, "{:.0f}"
    else:
        eps, fmt = 0.05, "{:.2f}"
    delta = sun - mon
    if abs(delta) < eps:
        return '<td class="flat">持平</td>'
    up = delta > 0
    cls = "up" if up else "down"
    arrow = "↑" if up else "↓"
    word = SEMANTIC[kind]["up" if up else "down"]
    return f'<td class="{cls}">{arrow} {fmt.format(abs(delta))} {word}</td>'


def main():
    today = datetime.date.today()
    monday, sunday = get_week_range(today)
    week_num = today.isocalendar()[1]
    date_range = f"{monday.strftime('%Y.%m.%d')} — {sunday.strftime('%m.%d')}"
    print(f"周报周期: {date_range} · 第 {week_num} 周")

    state = load_json(STATE)
    history = state.get("history", [])
    if not history:
        raise SystemExit("state.json 无 history 数据，无法生成周报")
    recs = [r for r in history if monday <= parse_date(r["date"]) <= sunday]
    if not recs:  # 兜底：最近 7 条
        recs = sorted(history, key=lambda r: r["date"])[-7:]
        print("本周无完整数据，使用最近 7 条兜底")
    mon_rec, sun_rec = recs[0], recs[-1]

    pe_mon, pe_sun = mon_rec["pe"], sun_rec["pe"]
    vix_mon, vix_sun = mon_rec["vix"], sun_rec["vix"]
    score_mon, score_sun = mon_rec["score"], sun_rec["score"]
    dd_mon, dd_sun = mon_rec["dd_pct"], sun_rec["dd_pct"]
    ndx_mon, ndx_sun = mon_rec["ndx"], sun_rec["ndx"]
    pe_pct = sun_rec["pe_pct"]
    daily = sun_rec["daily"]
    premium = sun_rec.get("premium")
    tier = sun_rec.get("tier", "mid_low")
    tier_cn = TIER_CN.get(tier, "合理偏低")

    pe_left = round(pe_to_left(pe_sun), 1)

    # ---- 核心数据表 ----
    rows = [
        f"<tr><td>PE</td><td>{pe_mon:.2f}</td><td>{pe_sun:.2f}</td>{chg_cell(pe_mon, pe_sun, 'pe')}</tr>",
        f"<tr><td>VIX</td><td>{vix_mon:.2f}</td><td>{vix_sun:.2f}</td>{chg_cell(vix_mon, vix_sun, 'vix')}</tr>",
        f"<tr><td>评分</td><td>{score_mon}</td><td>{score_sun}</td>{chg_cell(score_mon, score_sun, 'score')}</tr>",
        f"<tr><td>回撤</td><td>{dd_mon:.2f}%</td><td>{dd_sun:.2f}%</td>{chg_cell(dd_mon, dd_sun, 'dd')}</tr>",
        f"<tr><td>日定投</td><td>{daily} 牛牛币</td><td>{daily} 牛牛币</td><td class='flat'>不变</td></tr>",
    ]
    table_rows = "\n".join(rows)

    # ---- 文案（优先 weekly_events.json 当前周）----
    ev = load_json(EVENTS).get(str(week_num), {})

    speed = ev.get("speed")
    if not speed:
        ndx_chg = (ndx_sun / ndx_mon - 1) * 100
        vix_word = "退潮" if vix_sun < vix_mon else "升温"
        speed = (f"纳指100本周累涨 <b>{ndx_chg:+.2f}%</b>，情绪温和修复。"
                 f"PE 稳守 {pe_sun:.1f} 区间，处于 <b>{tier_cn}</b> 档位（近十年 {pe_pct:.1f}% 分位）。"
                 f"VIX 从 {vix_mon:.1f} 到 {vix_sun:.1f}，恐慌{vix_word}。")

    evts = ev.get("events") or [("本周事件", "本周大事件待补充，可在 weekly_events.json 按周号录入（标题+解读）。")]
    events_html = "\n".join(
        f'<div class="evt"><div class="num">{i+1}</div><div class="body"><span class="t">{t}</span>：{d}</div></div>'
        for i, (t, d) in enumerate(_pair(e) for e in evts[:4])
    )

    exec_html = (f"整周维持 <b>{daily} 牛牛币 / 日</b>，5 个交易日合计投入约 <b>{daily*5} 牛牛币</b>。"
                 f"档位始终处于「{tier_cn}」，未触发加减仓。")

    advs = ev.get("advices")
    if not advs:
        advs = []
        if premium and premium > 8:
            advs.append(f"场内 ETF 溢价率 {premium:.1f}% 仍超 8%，建议分批卖回场外")
        advs.append(f"纳指定投维持 {daily} 牛牛币 / 日，节奏不变")
        advs.append("若 VIX 重回 18+ 或宏观走弱扩散，重新评估档位")
    advices_html = "\n".join(
        f'<div class="adv"><div class="num">{i+1}</div><div class="body">{a}</div></div>'
        for i, a in enumerate(advs[:3])
    )

    # ---- 注入模板 ----
    tpl = TPL.read_text(encoding="utf-8")
    html = (tpl
            .replace("__DATE_RANGE__", date_range)
            .replace("__WEEK_NUM__", str(week_num))
            .replace("__SPEED__", speed)
            .replace("__PE_VAL__", f"{pe_sun:.2f}")
            .replace("__PE_PCT__", f"{pe_pct:.1f}")
            .replace("__PE_MARKER__", f"{pe_left}")
            .replace("__TABLE_ROWS__", table_rows)
            .replace("__EVENTS__", events_html)
            .replace("__EXEC__", exec_html)
            .replace("__ADVICES__", advices_html))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 渲染截图 ----
    from playwright.sync_api import sync_playwright
    chrome = os.environ.get("CHROME_PATH")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 2400})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=str(OUT_PNG), full_page=True)
        browser.close()
    print("长图已生成:", OUT_PNG)

    # ---- 网页展示页 ----
    viewer = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>纳指100定投周报 · 第 {week_num} 周</title>
<style>
body{{margin:0;background:#eef1f6;font-family:-apple-system,'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:20px}}
h1{{font-size:20px;color:#12264a;text-align:center;margin:4px 0 2px}}
.sub{{text-align:center;color:#6b7280;font-size:13px;margin-bottom:14px}}
img{{width:100%;height:auto;display:block;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.12)}}
.tip{{text-align:center;color:#6b7280;font-size:13px;margin:14px 0}}
</style></head>
<body><div class="wrap">
<h1>纳指100 定投周报 · 第 {week_num} 周</h1>
<div class="sub">{date_range}</div>
<img src="周报.png" alt="周报长图">
<div class="tip">长按 / 右键图片即可保存 · 数据来源：蛋卷基金 · yfinance · 公开财经资讯 · 仅供参考不构成投资建议</div>
</div></body></html>"""
    OUT_HTML.write_text(viewer, encoding="utf-8")
    print("网页已生成:", OUT_HTML)


if __name__ == "__main__":
    main()
