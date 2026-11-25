"""国内现货行情（人民币含税）：航业算力 ai.olbaba.com、宽泛采销 qudao.co。"""
import html
import json
import re

from ..gpus import match_cn
from ..net import get_text


def fetch_olbaba():
    url = "https://ai.olbaba.com/market/gpu.html"
    s = get_text(url)
    date = re.search(r"更新至\s*(\d{4}-\d{2}-\d{2})", s)
    offers = []
    for href, name, price, cnt in re.findall(
            r"<tr><td><a href='([^']+)'>(.*?)</a></td><td class='n'>¥([\d,]+)</td><td class='n'>(\d+)</td></tr>", s):
        name = html.unescape(name).strip()
        gid = match_cn(name)
        if not gid:
            continue
        offers.append({
            "g": gid, "type": "cn", "src": "olbaba", "provider": "航业算力",
            "cny": float(price.replace(",", "")), "cfg": name, "kind": "今日均价",
            "stock": f"{cnt} 条报价", "url": "https://ai.olbaba.com" + href,
            "at": date.group(1) if date else "",
        })
    if not offers:
        raise ValueError("olbaba: no rows parsed (layout changed?)")
    return offers, {"rows": len(offers)}


def _num(v):
    """qudao 无报价时为 '--'。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_qudao():
    s = get_text("https://qudao.co/")
    # Next.js RSC 负载中内嵌 initialProducts，先还原转义再解析
    chunks = "".join(json.loads(f'"{c}"') for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', s, re.S))
    key = '"initialProducts":'
    pos = chunks.find(key)
    if pos < 0:
        raise ValueError("initialProducts not found")
    items, _ = json.JSONDecoder().raw_decode(chunks, pos + len(key))
    offers = []
    for p in items:
        if p.get("category_code") != "gpu":
            continue
        gid = match_cn(p.get("name", ""))
        supply, demand = _num(p.get("currentMinSupply")), _num(p.get("currentMaxDemand"))
        if not gid or not supply:
            continue
        offers.append({
            "g": gid, "type": "cn", "src": "qudao", "provider": "宽泛采销",
            "cny": supply, "cny_hi": demand,
            "cfg": p["name"], "kind": "供货价",
            "stock": (p.get("spec_attributes") or {}).get("外部状况说明", ""),
            "url": f"https://qudao.co/sku/{p['id']}", "at": p.get("latestQuoteDate", ""),
        })
    if not offers:
        raise ValueError("qudao: no GPU rows parsed")
    return offers, {"rows": len(offers)}
