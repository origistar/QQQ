#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取 5 位知名投资者的最新两期 13F-HR 持仓，输出 superinvestors_data.json。
数据来源：美国 SEC EDGAR（官方、免费、权威）。
- 通过 data.sec.gov/submissions 取最近两期 13F-HR 及报告期(reportDate)
- 通过 Archives 取 information table XML 解析持仓
仅用标准库（urllib/xml/json），便于 GitHub Actions 直接运行。
"""
import urllib.request, urllib.error, json, xml.etree.ElementTree as ET, time, sys, re, datetime

UA = {"User-Agent": "Mozilla/5.0 (compatible; superinvestor-tracker/1.0; contact investor@example.com)"}

FILERS = [
    {"key": "buffett",  "cn": "巴菲特", "en": "Warren Buffett",        "entity": "Berkshire Hathaway Inc.",            "cik": "0001067983"},
    {"key": "duan",     "cn": "段永平", "en": "Duan Yongping",        "entity": "H&H International Investment, LLC",  "cik": "0001759760"},
    {"key": "danbin",   "cn": "但斌",   "en": "Danbin",               "entity": "Oriental Harbor Inv. Master Fund",   "cik": "0002046333"},
    {"key": "lilu",     "cn": "李录",   "en": "Li Lu",                "entity": "Himalaya Capital Mgmt LLC",          "cik": "0001709323"},
    {"key": "zhanglei", "cn": "张磊",   "en": "Zhang Lei (Hillhouse)","entity": "HHLR Advisors, Ltd.",                 "cik": "0001762304"},
]

def get_bytes(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

def get_text(url):
    return get_bytes(url).decode("utf-8", "replace")

def get_json(url):
    return json.loads(get_bytes(url))

def local(tag):
    return tag.split("}")[-1]

def child_text(el, name):
    for c in el:
        if local(c.tag) == name and c.text and c.text.strip():
            return c.text.strip()
    return None

def descend_text(el, name):
    for e in el.iter():
        if local(e.tag) == name and e.text and e.text.strip():
            return e.text.strip()
    return None

def get_recent_13fhr(cik, n=2):
    """返回 [(accession_with_dash, report_date, filing_date), ...] 最新的在前"""
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    d = get_json(url)
    rec = d["filings"]["recent"]
    forms = rec["form"]; accs = rec["accessionNumber"]; dates = rec["filingDate"]; reps = rec.get("reportDate", rec["filingDate"])
    out = []
    for a, fd, f, rp in zip(accs, dates, forms, reps):
        if f == "13F-HR":
            out.append((a, rp, fd))
    # 按报告期倒序
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:n]

def find_infotable_url(cik, accession):
    cikp = str(int(cik))
    folder = accession.replace("-", "")
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{cikp}/{folder}/{accession}-index.htm"
    html = get_text(idx_url)
    links = re.findall(r'href="([^"]+\.xml)"', html)
    candidates = []
    for ln in links:
        if ln.lower().endswith("primary_doc.xml"):
            continue
        if ln.startswith("/"):
            ln = "https://www.sec.gov" + ln
        elif not ln.startswith("http"):
            ln = f"https://www.sec.gov/Archives/edgar/data/{cikp}/{folder}/{ln}"
        candidates.append(ln)
    for u in candidates:
        try:
            data = get_bytes(u)
            root = ET.fromstring(data)
            if local(root.tag) == "informationTable":
                return u
        except Exception:
            continue
    return None

def parse_infotable(url):
    data = get_bytes(url)
    root = ET.fromstring(data)
    rows = []
    for it in root.iter():
        if local(it.tag) != "infoTable":
            continue
        name = child_text(it, "nameOfIssuer") or ""
        cusip = (child_text(it, "cusip") or "").strip()
        val = child_text(it, "value") or "0"
        put = child_text(it, "putCall") or ""
        # shares: prefer inside shrsOrPrnAmt
        shp = None
        for c in it:
            if local(c.tag) == "shrsOrPrnAmt":
                shp = descend_text(c, "sshPrnamt")
        if shp is None:
            shp = descend_text(it, "sshPrnamt")
        try:
            val_i = int(val)
        except Exception:
            val_i = 0
        try:
            sh_i = int(shp) if shp else 0
        except Exception:
            sh_i = 0
        if not cusip:
            continue
        rows.append({"name": name.strip(), "cusip": cusip, "value": val_i, "shares": sh_i, "putCall": put})
    # 合并同一 CUSIP 的拆分行（个别基金如伯克希尔会把同一标的拆多行）
    merged = {}
    for r in rows:
        c = r["cusip"]
        if c in merged:
            merged[c]["value"] += r["value"]
            merged[c]["shares"] += r["shares"]
        else:
            merged[c] = dict(r)
    return list(merged.values())

def build_filer(f):
    print(f"  -> {f['cn']} ({f['entity']}) CIK={f['cik']}")
    pairs = get_recent_13fhr(f["cik"], 2)
    if not pairs:
        print("     无 13F-HR 记录")
        return None
    periods = []
    for acc, rp, fd in pairs:
        u = find_infotable_url(f["cik"], acc)
        if not u:
            print(f"     找不到信息表: {acc}")
            continue
        h = parse_infotable(u)
        total = sum(x["value"] for x in h)  # $000
        periods.append({"period": rp, "filingDate": fd, "total_value": total, "holdings": h})
        print(f"     期 {rp} 持仓 {len(h)} 项 总值 ${total/1000:,.0f}亿" if total >= 1e6 else f"     期 {rp} 持仓 {len(h)} 项 总值 ${total*1000:,.0f}")
        time.sleep(0.3)
    if not periods:
        return None
    periods.sort(key=lambda x: x["period"], reverse=True)
    latest = periods[0]
    prev = periods[1] if len(periods) > 1 else None
    return {"latest": latest, "prev": prev}

def short_name(n):
    # 轻量清洗用于显示
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"\b(INC|CORP|CO|LTD|PLC|LP|LLC|DEL|NEW|SPONSORED ADS|CLASS A|CLASS B|CLASS C|CL A|CL B|CL C)\b\.?", "", n, flags=re.I)
    n = re.sub(r"[.,]+$", "", n).strip()
    return n

def main():
    out = {"generated": datetime.date.today().isoformat(), "filers": []}
    cross = {}  # cusip -> {name, holders:[key]}
    for f in FILERS:
        b = build_filer(f)
        if not b:
            continue
        latest = b["latest"]; prev = b["prev"]
        # 计算环比
        prev_map = {h["cusip"]: h for h in prev["holdings"]} if prev else {}
        latest_map = {h["cusip"]: h for h in latest["holdings"]}
        new_, exited, inc, dec = [], [], [], []
        for h in latest["holdings"]:
            if h["cusip"] not in prev_map:
                new_.append(h)
            else:
                pv = prev_map[h["cusip"]]["value"]
                if h["value"] > pv:
                    inc.append({"name": h["name"], "cusip": h["cusip"], "value": h["value"], "delta": h["value"] - pv})
                elif h["value"] < pv:
                    dec.append({"name": h["name"], "cusip": h["cusip"], "value": h["value"], "delta": h["value"] - pv})
        for h in prev["holdings"] if prev else []:
            if h["cusip"] not in latest_map:
                exited.append(h)
        # 横向交集
        for h in latest["holdings"]:
            c = cross.setdefault(h["cusip"], {"name": h["name"], "holders": []})
            c["name"] = h["name"]
            c["holders"].append(f["key"])
        out["filers"].append({
            "key": f["key"], "cn": f["cn"], "en": f["en"], "entity": f["entity"],
            "latest": latest, "prev": prev,
            "changes": {
                "new": sorted(new_, key=lambda x: -x["value"]),
                "exited": sorted(exited, key=lambda x: -x["value"]),
                "increased": sorted(inc, key=lambda x: -x["delta"]),
                "decreased": sorted(dec, key=lambda x: x["delta"]),
            },
        })
    # 共识标的
    consensus = []
    for cusip, c in cross.items():
        if len(c["holders"]) >= 2:
            consensus.append({"cusip": cusip, "name": c["name"], "holders": c["holders"], "count": len(c["holders"])})
    consensus.sort(key=lambda x: -x["count"])
    out["cross"] = consensus
    json.dump(out, open("superinvestors_data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n完成。{len(out['filers'])} 位投资者，共识标的 {len(consensus)} 个。输出 superinvestors_data.json")

if __name__ == "__main__":
    main()
