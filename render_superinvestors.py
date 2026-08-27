#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据 superinvestors_data.json 生成 superinvestors.html：
1) 五人横向共识（置顶）
2) 分析结论（第二段，结构化重排）
3) 每位投资者「最新 vs 上一期」持仓变动（占比增减，去市值）
股票名统一「中文 + 代码」，每季度自动更新。
"""
import json

# 股票名（SEC 原始大写）-> 中文+代码 展示串
NAME_MAP = {
    "ADVANCED MICRO DEVICES INC": "超威半导体AMD",
    "ALAMAR BIOSCIENCES INC": "阿拉玛生物ALMS",
    "ALIBABA GROUP HLDG LTD": "阿里巴巴BABA",
    "ALPHABET INC": "谷歌GOOGL",
    "AMAZON COM INC": "亚马逊AMZN",
    "AMERICAN EXPRESS CO": "美国运通AXP",
    "APPLE INC": "苹果AAPL",
    "ARM HOLDINGS PLC": "安谋ARM",
    "ARRIVENT BIOPHARMA INC": "雅睿生物ARVN",
    "BANK OF AMER CORP": "美国银行BAC",
    "BARRICK MNG CORP": "巴里克黄金GOLD",
    "BEONE MEDICINES LTD": "百济神州ONC",
    "BERKSHIRE HATHAWAY INC DEL": "伯克希尔BRK.B",
    "BK OF AMERICA CORP": "美国银行BAC",
    "BLOCK H & R INC": "BlockXYZ",
    "BROADCOM INC": "博通AVGO",
    "CENTRAIS ELET BRAS SA": "巴西电力EBR",
    "CHEVRON CORPORATION": "雪佛龙CVX",
    "CHUBB LIMITED": "丘博保险CB",
    "CIRCLE INTERNET GROUP INC": "CircleCRCL",
    "CLEARWATER ANALYTICS HLDGS I": "清水分析CWAN",
    "COCA COLA CO": "可口可乐KO",
    "CONSTELLATION BRANDS INC": "星座品牌STZ",
    "CONTINEUM THERAPEUTICS INC": "康蒂纽姆CTNM",
    "CREDO TECHNOLOGY GROUP HOLDI": "Credo科技CRDO",
    "CROCS INC": "卡骆驰CROX",
    "CROWDSTRIKE HLDGS INC": "CrowdStrikeCRWD",
    "CYTEK BIOSCIENCES INC": "Cytek生物CTKB",
    "D R HORTON INC": "霍顿建筑DHI",
    "DAVITA INC": "达维塔DVA",
    "DELTA AIR LINES INC": "达美航空DAL",
    "DINGDONG CAYMAN LTD": "叮咚买菜DDL",
    "DIREXION SHS ETF TR": "Direxion杠杆ETF",
    "DISNEY WALT CO": "迪士尼DIS",
    "EAST WEST BANCORP INC": "华美银行EWBC",
    "FUTU HLDGS LTD": "富途控股FUTU",
    "INTEL CORP": "英特尔INTC",
    "ISHARES INC": "iShares贝莱德ETF",
    "KE HLDGS INC": "贝壳BEKE",
    "KRAFT HEINZ CO": "卡夫亨氏KHC",
    "KROGER CO": "克罗格KR",
    "LEGEND BIOTECH CORP": "传奇生物LEGN",
    "LUMENTUM HLDGS INC": "LumentumLITE",
    "MARVELL TECHNOLOGY INC": "迈威科技MRVL",
    "MAZE THERAPEUTICS INC": "Maze生物MAZE",
    "META PLATFORMS INC": "MetaMETA",
    "MICRON TECHNOLOGY INC": "美光科技MU",
    "MICROSOFT CORP": "微软MSFT",
    "MOODYS CORP": "穆迪MCO",
    "MSCI INC": "MSCI明晟MSCI",
    "NETEASE COM INC": "网易NTES",
    "NOVABRIDGE BIOSCIENCES": "诺瓦布里奇生物",
    "NVIDIA CORPORATION": "英伟达NVDA",
    "OCCIDENTAL PETE CORP": "西方石油OXY",
    "ODYSSEY THERAPEUTICS INC": "奥德赛生物ODYS",
    "PALANTIR TECHNOLOGIES INC": "PalantirPLTR",
    "PDD HOLDINGS INC": "拼多多PDD",
    "PROSHARES TR": "ProSharesETF",
    "RIDGETECH INC": "里奇科技",
    "S&P GLOBAL INC": "标普全球SPGI",
    "SANDISK CORP": "闪迪SNDK",
    "SIRIUSXM HOLDINGS INC": "SiriusXMSIRI",
    "SYNOPSYS INC": "新思科技SNPS",
    "TAIWAN SEMICONDUCTOR MANUFAC": "台积电TSM",
    "TENCENT MUSIC ENTERTAINM": "腾讯音乐TME",
    "TESLA INC": "特斯拉TSLA",
    "TEXAS INSTRS INC": "德州仪器TXN",
    "UNITEDHEALTH GROUP INC": "联合健康UNH",
    "UXIN LTD": "优信UXIN",
    "VERISIGN INC": "威瑞信VRSN",
    "VIPSHOP HLDGS LTD": "唯品会VIPS",
    "VNET GROUP INC": "世纪互联VNET",
    "YATSEN HLDG LTD": "逸仙电商YSG",
    "ZOOM COMMUNICATIONS INC": "ZoomZM",
}
KEY2CN = {}

def cn_name(raw):
    k = raw.strip().upper()
    return NAME_MAP.get(k, raw.strip().title())

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def fmt_pct(d):
    """占比增减展示：正 ▲+x.xpct，负 ▼x.xpct"""
    if d is None:
        return ""
    if d > 0:
        return "▲+%.1fpct" % d
    return "▼%.1fpct" % d

def load():
    with open("superinvestors_data.json", "r", encoding="utf-8") as f:
        return json.load(f)

def build_valmap(filer):
    vm = {}
    for h in filer["latest"]["holdings"]:
        vm[h["cusip"]] = vm.get(h["cusip"], 0) + h["value"]
    return vm

def build_prev_valmap(filer):
    vm = {}
    for h in filer.get("prev", {}).get("holdings", []):
        vm[h["cusip"]] = vm.get(h["cusip"], 0) + h["value"]
    return vm

def merged_consensus(data):
    bykey = {f["key"]: f for f in data["filers"]}
    for f in data["filers"]:
        f["_valmap"] = build_valmap(f)
    groups = {}
    for c in data.get("cross", []):
        nm = c["name"].strip().upper()
        g = groups.setdefault(nm, {"name": c["name"], "cusips": set(), "holders": set()})
        g["cusips"].add(c["cusip"])
        for h in c["holders"]:
            g["holders"].add(h)
    out = []
    for g in groups.values():
        holder_vals = {}
        tot = 0
        for hk in g["holders"]:
            v = sum(bykey[hk]["_valmap"].get(cu, 0) for cu in g["cusips"])
            holder_vals[hk] = v
            tot += v
        out.append({
            "name": g["name"], "count": len(g["holders"]),
            "holders": sorted(g["holders"]), "holder_vals": holder_vals, "total": tot,
        })
    out.sort(key=lambda x: (-x["count"], -x["total"]))
    return out

def render_investor_card(f):
    KEY2CN[f["key"]] = f["cn"]
    latest = f["latest"]
    total = latest["total_value"]
    n_hold = len(latest["holdings"])
    prev_vm = build_prev_valmap(f)
    prev_total = f.get("prev", {}).get("total_value", 0) or 1
    new_cusips = {h["cusip"] for h in f.get("changes", {}).get("new", [])}

    holdings = sorted(latest["holdings"], key=lambda h: -h["value"])[:15]
    rows = []
    for i, h in enumerate(holdings, 1):
        cu = h["cusip"]
        cur_w = h["value"] / total * 100 if total else 0
        prev_w = prev_vm.get(cu, 0) / prev_total * 100 if prev_total else 0
        d = cur_w - prev_w
        if cu not in prev_vm:
            badge = '<span class="badge new">新进 +%.1fpct</span>' % cur_w
        elif d > 0.05:
            badge = '<span class="badge up">%s</span>' % fmt_pct(d)
        elif d < -0.05:
            badge = '<span class="badge down">%s</span>' % fmt_pct(d)
        else:
            badge = ""
        rows.append(
            '<tr><td class="rk">%d</td><td class="nm">%s</td>'
            '<td class="pc">%.1f%%</td><td class="ch">%s</td></tr>'
            % (i, esc(cn_name(h["name"])), cur_w, badge)
        )

    chips = (
        '<span class="chip">报告期 <b>%s</b></span>'
        '<span class="chip">申报 <b>%s</b></span>'
        '<span class="chip">持仓 <b>%d</b> 只</span>'
        % (latest["period"], latest["filingDate"], n_hold)
    )
    n_new = len(new_cusips)
    n_exit = len(f.get("changes", {}).get("exited", []))
    n_inc = len(f.get("changes", {}).get("increased", []))
    n_dec = len(f.get("changes", {}).get("decreased", []))
    move = (
        '<span class="mv new">新进 %d</span><span class="mv out">清仓 %d</span>'
        '<span class="mv up">增持 %d</span><span class="mv down">减持 %d</span>'
        % (n_new, n_exit, n_inc, n_dec)
    )

    exited = f.get("changes", {}).get("exited", [])
    exit_list = ""
    if exited:
        names = "、".join(esc(cn_name(h["name"])) for h in sorted(exited, key=lambda x: -x["value"])[:8])
        exit_list = '<div class="exited">本季清仓：%s</div>' % names

    return """
    <div class="card">
      <div class="inv-head"><div class="cn">%(cn)s</div>
        <div class="en">%(en)s · %(entity)s</div></div>
      <div class="meta">%(chips)s</div>
      <div class="moves">%(move)s</div>
      <div class="tablewrap"><table>
        <thead><tr><th class="rk">#</th><th>标的（前15大）</th><th>占比</th><th>占比增减</th></tr></thead>
        <tbody>%(rows)s</tbody></table></div>
      %(exit_list)s
    </div>""" % {
        "cn": esc(f["cn"]), "en": esc(f["en"]), "entity": esc(f["entity"]),
        "chips": chips, "move": move, "rows": "".join(rows), "exit_list": exit_list,
    }

def render_consensus(data, consensus):
    bykey = {f["key"]: f for f in data["filers"]}
    rows = []
    for g in consensus:
        if g["count"] < 2:
            continue
        holder_cn = "、".join(esc(bykey[h]["cn"]) for h in g["holders"])
        strong = ' class="strong"' if g["count"] >= 3 else ""
        rows.append(
            '<tr%(strong)s><td class="cnt">%(cnt)d/5</td>'
            '<td class="nm">%(nm)s</td><td class="hd">%(hd)s</td></tr>'
            % {"strong": strong, "cnt": g["count"],
               "nm": esc(cn_name(g["name"])), "hd": holder_cn}
        )
    if not rows:
        return ""
    return """
    <div class="card">
      <h2>五人横向共识 <span class="meta">最新报告期共同持有的标的（按持有人数排序）</span></h2>
      <div class="tablewrap"><table>
        <thead><tr><th>共识度</th><th>标的</th><th>持有人</th></tr></thead>
        <tbody>%(rows)s</tbody></table></div>
      <div class="hint">绿色高亮 = 被 ≥3 人持有（强共识）。</div>
    </div>""" % {"rows": "".join(rows)}

def render_analysis(data, consensus):
    bykey = {f["key"]: f for f in data["filers"]}
    strong = [g for g in consensus if g["count"] >= 3]
    parts = []
    for g in strong:
        holder_cn = "、".join(bykey[h]["cn"] for h in g["holders"])
        parts.append("<b>%s</b>（%d/5：%s）" % (esc(cn_name(g["name"])), g["count"], holder_cn))
    strong_html = '<div class="strong-box">【强共识】%s</div>' % "；".join(parts) if parts else ""

    blocks = []
    for f in data["filers"]:
        total = f["latest"]["total_value"]
        prev_vm = build_prev_valmap(f)
        prev_total = f.get("prev", {}).get("total_value", 0) or 1
        ch = f.get("changes", {})

        def pct_of(item):
            cu = item["cusip"]
            cur_w = item["value"] / total * 100 if total else 0
            prev_w = prev_vm.get(cu, 0) / prev_total * 100 if prev_total else 0
            return cur_w - prev_w

        inc = sorted(ch.get("increased", []), key=lambda x: -pct_of(x))[:3]
        dec = sorted(ch.get("decreased", []), key=lambda x: pct_of(x))[:3]
        newl = sorted(ch.get("new", []), key=lambda x: -x["value"])[:4]
        exl = sorted(ch.get("exited", []), key=lambda x: -x["value"])[:4]

        lines = []
        if inc:
            lines.append('<div class="arow up">▲ 增持：%s</div>' % "、".join(
                "%s %s" % (esc(cn_name(h["name"])), fmt_pct(pct_of(h))) for h in inc))
        if dec:
            lines.append('<div class="arow down">▼ 减持：%s</div>' % "、".join(
                "%s %s" % (esc(cn_name(h["name"])), fmt_pct(pct_of(h))) for h in dec))
        if newl:
            lines.append('<div class="arow new">🆕 新进：%s</div>' % "、".join(
                esc(cn_name(h["name"])) for h in newl))
        if exl:
            lines.append('<div class="arow out">🗑 清仓：%s</div>' % "、".join(
                esc(cn_name(h["name"])) for h in exl))
        blocks.append(
            '<div class="inv-block"><div class="inv-name">%s <span class="ic">持仓 %d 只</span></div>%s</div>'
            % (esc(f["cn"]), len(f["latest"]["holdings"]), "".join(lines))
        )

    return """
    <div class="card analysis">
      <h2>分析结论 <span class="meta">数据驱动自动生成</span></h2>
      %(strong_html)s
      %(blocks)s
      <div class="disc">口径：13F-HR 仅披露<b>美股多头</b>持仓，不含空仓/债券/非美资产；申报有 ≤45 天滞后（本页取各人最近一期官方申报）。「占比增减」= 该标的在本组合权重较上一期的变动。仅供研究参考，<b>不构成任何投资建议</b>。</div>
    </div>""" % {"strong_html": strong_html, "blocks": "".join(blocks)}

def main():
    data = load()
    consensus = merged_consensus(data)
    consensus_html = render_consensus(data, consensus)
    analysis_html = render_analysis(data, consensus)
    cards = "".join(render_investor_card(f) for f in data["filers"])
    gen = data.get("generated", "")

    html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>顶级投资者 13F 持仓对比</title>
<style>
 * { box-sizing:border-box; }
 body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6f8; color:#10151a; margin:0; padding:14px; }
 h1 { font-size:20px; margin:0 0 2px; }
 .sub { color:#5b6b75; font-size:12px; margin-bottom:14px; }
 .card { background:#fff; border-radius:14px; padding:14px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
 h2 { font-size:16px; margin:0 0 10px; }
 .meta { font-weight:400; font-size:11px; color:#7a8794; display:block; margin-top:3px; }
 .inv-head .cn { font-size:18px; font-weight:700; }
 .inv-head .en { font-size:11px; color:#7a8794; margin-top:2px; }
 .meta { margin:8px 0 6px; }
 .chip { display:inline-block; background:#eef3f8; color:#3c4950; font-size:11px; border-radius:8px; padding:3px 8px; margin:0 5px 5px 0; }
 .chip b { color:#10151a; }
 .moves { margin:2px 0 10px; }
 .mv { display:inline-block; font-size:12px; font-weight:600; margin:0 10px 4px 0; }
 .mv.new { color:#15803d; } .mv.out { color:#b91c1c; } .mv.up { color:#15803d; } .mv.down { color:#b91c1c; }
 .tablewrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
 table { border-collapse:collapse; width:100%%; min-width:520px; font-size:13px; }
 th,td { border:1px solid #eef1f4; padding:6px 7px; text-align:left; white-space:nowrap; }
 thead th { background:#eef3f8; font-size:11px; color:#3c4950; position:sticky; top:0; }
 td.rk, th.rk { background:#fafbfc; color:#9aa6b0; width:26px; text-align:center; }
 td.nm { font-weight:600; }
 td.pc { color:#7a8794; font-size:11px; }
 .badge { font-size:9px; border-radius:4px; padding:1px 5px; margin-left:3px; vertical-align:middle; white-space:nowrap; }
 .badge.new { color:#fff; background:#15803d; }
 .badge.up { color:#15803d; background:#e7f5ec; }
 .badge.down { color:#b91c1c; background:#fdeaea; }
 .exited { font-size:11px; color:#b91c1c; margin-top:8px; line-height:1.5; }
 .hint { font-size:11px; color:#7a8794; margin-top:8px; }
 tr.strong td.cnt { background:#e7f5ec; color:#15803d; font-weight:700; }
 .analysis .strong-box { background:#e7f5ec; border:1px solid #bfe3cb; border-radius:12px; padding:10px 12px; font-size:13px; line-height:1.7; margin-bottom:12px; }
 .analysis .strong-box b { color:#15803d; }
 .inv-block { border-top:1px solid #eef1f4; padding:10px 0 2px; }
 .inv-block:first-of-type { border-top:none; }
 .inv-name { font-size:14px; font-weight:700; margin-bottom:4px; }
 .inv-name .ic { font-size:11px; font-weight:400; color:#9aa6b0; margin-left:6px; }
 .arow { font-size:12.5px; line-height:1.7; }
 .arow.up { color:#15803d; } .arow.down { color:#b91c1c; }
 .arow.new { color:#15803d; } .arow.out { color:#b91c1c; }
 .disc { background:#fff8ec; border:1px solid #f3e2bf; border-radius:12px; padding:12px; font-size:12px; color:#7a5b1a; line-height:1.6; margin-top:12px; }
 .disc b { color:#5b4310; }
</style></head><body>
<h1>顶级投资者 13F 持仓对比</h1>
<div class="sub">巴菲特 · 段永平 · 但斌 · 李录 · 张磊（HHLR）· 五人横向共识 + 分析结论 + 各人最新 vs 上一期 · 生成 %(gen)s · 每季度更新</div>
%(consensus_html)s
%(analysis_html)s
%(cards)s
</body></html>""" % {
        "gen": esc(gen), "consensus_html": consensus_html,
        "analysis_html": analysis_html, "cards": cards,
    }
    with open("superinvestors.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote superinvestors.html (%d bytes)" % len(html))

if __name__ == "__main__":
    main()
