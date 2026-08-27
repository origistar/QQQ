#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据 superinvestors_data.json 生成 superinvestors.html：
1) 每位投资者「最新 vs 上一期」持仓变动（新进/清仓/增持/减持 + 最新持仓榜）
2) 五人横向共识对比（被多人持有的标的）
3) 自动生成的分析总结
风格：iOS 质感、移动端优先，与 momentum_changes.html 一致。
"""
import json

KEY2CN = {}

def fmt_usd(v):
    if v is None:
        return "-"
    if v >= 1e9:
        return "$%.2fB" % (v / 1e9)
    if v >= 1e6:
        return "$%.1fM" % (v / 1e6)
    if v >= 1e3:
        return "$%.0fK" % (v / 1e3)
    return "$%.0f" % v

def fmt_delta(d):
    if d is None:
        return ""
    s = "+" if d >= 0 else "-"
    a = abs(d)
    if a >= 1e9:
        return "%s$%.2fB" % (s, a / 1e9)
    if a >= 1e6:
        return "%s$%.1fM" % (s, a / 1e6)
    return "%s$%.0fK" % (s, a / 1e3)

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def load():
    with open("superinvestors_data.json", "r", encoding="utf-8") as f:
        return json.load(f)

def build_valmap(filer):
    vm = {}
    for h in filer["latest"]["holdings"]:
        vm[h["cusip"]] = vm.get(h["cusip"], 0) + h["value"]
    return vm

def changes_maps(filer):
    ch = filer.get("changes", {})
    new = {h["cusip"]: h for h in ch.get("new", [])}
    exited = {h["cusip"]: h for h in ch.get("exited", [])}
    inc = {}
    for h in ch.get("increased", []):
        inc[h["cusip"]] = h.get("delta")
    dec = {}
    for h in ch.get("decreased", []):
        dec[h["cusip"]] = h.get("delta")
    return new, exited, inc, dec

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
            f = bykey[hk]
            v = sum(f["_valmap"].get(cu, 0) for cu in g["cusips"])
            holder_vals[hk] = v
            tot += v
        out.append({
            "name": g["name"],
            "count": len(g["holders"]),
            "holders": sorted(g["holders"]),
            "holder_vals": holder_vals,
            "total": tot,
        })
    out.sort(key=lambda x: (-x["count"], -x["total"]))
    return out

def render_investor_card(f):
    KEY2CN[f["key"]] = f["cn"]
    new, exited, inc, dec = changes_maps(f)
    latest = f["latest"]
    total = latest["total_value"]
    n_hold = len(latest["holdings"])

    # top holdings by value
    holdings = sorted(latest["holdings"], key=lambda h: -h["value"])[:15]

    rows = []
    for i, h in enumerate(holdings, 1):
        cu = h["cusip"]
        pct = h["value"] / total * 100 if total else 0
        badge = ""
        if cu in new:
            badge = '<span class="badge new">新进</span>'
        elif cu in inc and inc[cu] is not None:
            badge = '<span class="badge up">▲%s</span>' % fmt_delta(inc[cu])
        elif cu in dec and dec[cu] is not None:
            badge = '<span class="badge down">▼%s</span>' % fmt_delta(dec[cu])
        rows.append(
            '<tr><td class="rk">%d</td><td class="nm">%s</td>'
            '<td class="rv">%s</td><td class="pc">%.1f%%</td>'
            '<td class="ch">%s</td></tr>'
            % (i, esc(h["name"].title()), fmt_usd(h["value"]), pct, badge)
        )

    n_new = len(new)
    n_exit = len(exited)
    n_inc = len(inc)
    n_dec = len(dec)
    chips = (
        '<span class="chip">报告期 <b>%s</b></span>'
        '<span class="chip">申报 <b>%s</b></span>'
        '<span class="chip">市值 <b>%s</b></span>'
        '<span class="chip">持仓 <b>%d</b> 只</span>'
        % (latest["period"], latest["filingDate"], fmt_usd(total), n_hold)
    )
    move = (
        '<span class="mv new">新进 %d</span>'
        '<span class="mv out">清仓 %d</span>'
        '<span class="mv up">增持 %d</span>'
        '<span class="mv down">减持 %d</span>'
        % (n_new, n_exit, n_inc, n_dec)
    )

    exit_list = ""
    if exited:
        names = "、".join(esc(h["name"].title()) for h in sorted(exited.values(), key=lambda x: -x["value"])[:8])
        exit_list = '<div class="exited">本季清仓：%s</div>' % names

    return """
    <div class="card">
      <div class="inv-head">
        <div class="cn">%(cn)s</div>
        <div class="en">%(en)s · %(entity)s</div>
      </div>
      <div class="meta">%(chips)s</div>
      <div class="moves">%(move)s</div>
      <div class="tablewrap">
        <table>
          <thead><tr><th class="rk">#</th><th>标的（前15大）</th><th>市值</th><th>占比</th><th>本季变动</th></tr></thead>
          <tbody>%(rows)s</tbody>
        </table>
      </div>
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
        # per-holder values
        hv = " · ".join(
            "%s %s" % (esc(bykey[h]["cn"]), fmt_usd(g["holder_vals"][h]))
            for h in g["holders"]
        )
        rows.append(
            '<tr%(strong)s><td class="cnt">%(cnt)d/5</td>'
            '<td class="nm">%(nm)s</td>'
            '<td class="hd">%(hd)s</td>'
            '<td class="rv">%(rv)s</td></tr>'
            % {"strong": strong, "cnt": g["count"], "nm": esc(g["name"].title()),
               "hd": holder_cn, "rv": fmt_usd(g["total"])}
        )
    if not rows:
        return ""
    return """
    <div class="card">
      <h2>五人横向共识 <span class="meta">最新报告期共同持有的标的（按持有人数排序）</span></h2>
      <div class="tablewrap">
        <table>
          <thead><tr><th>共识度</th><th>标的</th><th>持有人</th><th>合计市值</th></tr></thead>
          <tbody>%(rows)s</tbody>
        </table>
      </div>
      <div class="hint">绿色高亮 = 被 ≥3 人持有（强共识）。</div>
    </div>""" % {"rows": "".join(rows)}

def render_analysis(data, consensus):
    bykey = {f["key"]: f for f in data["filers"]}
    strong = [g for g in consensus if g["count"] >= 3]
    lines = []

    if strong:
        parts = []
        for g in strong:
            holder_cn = "、".join(bykey[h]["cn"] for h in g["holders"])
            parts.append("<b>%s</b>（%d/5：%s，合计 %s）" % (
                esc(g["name"].title()), g["count"], holder_cn, fmt_usd(g["total"])))
        lines.append("【强共识（≥3 人持有）】" + "；".join(parts) + "。")

    # per investor qualitative
    for f in data["filers"]:
        new, exited, inc, dec = changes_maps(f)
        inc_top = sorted(
            [h for h in f["changes"].get("increased", []) if h.get("delta")],
            key=lambda x: -x["delta"])[:3]
        dec_top = sorted(
            [h for h in f["changes"].get("decreased", []) if h.get("delta")],
            key=lambda x: x["delta"])[:3]
        dv = f["latest"]["total_value"] - f["prev"]["total_value"]
        dv_s = fmt_delta(dv)
        bits = []
        if inc_top:
            bits.append("重点增持 " + "、".join(
                "%s(%s)" % (esc(h["name"].title()), fmt_delta(h["delta"])) for h in inc_top))
        if dec_top:
            bits.append("重点减持 " + "、".join(
                "%s(%s)" % (esc(h["name"].title()), fmt_delta(h["delta"])) for h in dec_top))
        if new:
            newnames = "、".join(esc(h["name"].title()) for h in sorted(new.values(), key=lambda x: -x["value"])[:4])
            bits.append("新进 " + newnames)
        if exited:
            exnames = "、".join(esc(h["name"].title()) for h in sorted(exited.values(), key=lambda x: -x["value"])[:4])
            bits.append("清仓 " + exnames)
        sent = "%s：组合市值 %s（%s），%s。" % (
            esc(f["cn"]), fmt_usd(f["latest"]["total_value"]),
            dv_s, "；".join(bits))
        lines.append(sent)

    analysis = "\n".join('<div class="aline">%s</div>' % l for l in lines)
    return """
    <div class="card analysis">
      <h2>分析总结 <span class="meta">数据驱动自动生成</span></h2>
      %(analysis)s
      <div class="disc">口径：13F-HR 仅披露<b>美股多头</b>持仓，不含空仓/债券/非美资产；申报有 ≤45 天滞后（本页取各人最近一期官方申报）。仅供研究参考，<b>不构成任何投资建议</b>。</div>
    </div>""" % {"analysis": analysis}

def main():
    data = load()
    consensus = merged_consensus(data)
    cards = "".join(render_investor_card(f) for f in data["filers"])
    consensus_html = render_consensus(data, consensus)
    analysis_html = render_analysis(data, consensus)

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
 table { border-collapse:collapse; width:100%%; min-width:560px; font-size:13px; }
 th,td { border:1px solid #eef1f4; padding:6px 7px; text-align:left; white-space:nowrap; }
 thead th { background:#eef3f8; font-size:11px; color:#3c4950; position:sticky; top:0; }
 td.rk, th.rk { background:#fafbfc; color:#9aa6b0; width:26px; text-align:center; }
 td.nm { font-weight:600; }
 td.rv { color:#3c4950; } td.pc { color:#7a8794; font-size:11px; }
 .badge { font-size:9px; border-radius:4px; padding:1px 5px; margin-left:3px; vertical-align:middle; white-space:nowrap; }
 .badge.new { color:#fff; background:#15803d; }
 .badge.up { color:#15803d; background:#e7f5ec; }
 .badge.down { color:#b91c1c; background:#fdeaea; }
 .exited { font-size:11px; color:#b91c1c; margin-top:8px; line-height:1.5; }
 .hint { font-size:11px; color:#7a8794; margin-top:8px; }
 tr.strong td.cnt { background:#e7f5ec; color:#15803d; font-weight:700; }
 .analysis .aline { font-size:13px; line-height:1.7; margin:6px 0; }
 .disc { background:#fff8ec; border:1px solid #f3e2bf; border-radius:12px; padding:12px; font-size:12px; color:#7a5b1a; line-height:1.6; margin-top:12px; }
 .disc b { color:#5b4310; }
</style></head><body>
<h1>顶级投资者 13F 持仓对比</h1>
<div class="sub">巴菲特 · 段永平 · 但斌 · 李录 · 张磊（HHLR）· 最新 vs 上一期 + 五人横向共识 · 生成 %(gen)s · 每季度更新</div>
%(cards)s
%(consensus_html)s
%(analysis_html)s
</body></html>""" % {
        "gen": esc(gen), "cards": cards,
        "consensus_html": consensus_html, "analysis_html": analysis_html,
    }
    with open("superinvestors.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote superinvestors.html (%d bytes)" % len(html))

if __name__ == "__main__":
    main()
