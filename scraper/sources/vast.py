"""Vast.ai 竞价市场（免登录）。dph_total 为整机每小时，按每卡折算后取 P10 与中位数。
注意：不要伪装浏览器 UA，否则会 403。"""
import re
import statistics

from ..net import get_json

URL = "https://console.vast.ai/api/v0/bundles/"


def _gid(name):
    s = name.lower().strip()
    fixed = {"h100 sxm": "h100-sxm", "h100 pcie": "h100-pcie", "h100 nvl": "h100-nvl", "h200": "h200",
             "h200 nvl": "h200-nvl", "b200": "b200", "b300": "b300", "gh200": "gh200",
             "a100 sxm4": "a100-sxm-80", "a100 pcie": "a100-pcie-80", "a100x": "a100-pcie-80",
             "rtx pro 6000 s": "rtx-pro-6000-server", "rtx pro 6000 ws": "rtx-pro-6000-wk",
             "rtx 6000ada": "rtx-6000-ada", "rtx 5000ada": "rtx-5000-ada", "rtx 4000ada": "rtx-4000-ada",
             "rtx a6000": "rtx-a6000", "rtx a5000": "rtx-a5000", "rtx a4000": "rtx-a4000"}
    if s in fixed:
        return fixed[s]
    s = re.sub(r"\s+", "-", s)
    return s if re.match(r"^(rtx-\d{4}(-ti|-super)?|l40s?|l4|a40|a10|t4|v100)$", s) else None


def fetch():
    d = get_json(URL, payload={"type": "on-demand", "rentable": {"eq": True}, "verified": {"eq": True}, "limit": 5000})
    groups = {}
    for o in d.get("offers", []):
        gid = _gid(o.get("gpu_name") or "")
        n = o.get("num_gpus") or 0
        if gid and n and o.get("dph_total"):
            groups.setdefault(gid, []).append(o["dph_total"] / n)
    offers = []
    for gid, prices in groups.items():
        prices.sort()
        p10 = prices[int(len(prices) * 0.1)]
        offers.append({
            "g": gid, "type": "rent", "src": "vast", "provider": "Vast.ai", "pkey": "vast",
            "kind": "marketplace", "usd": round(p10, 4), "n": 1,
            "cfg": f"P10 价 · 中位 ${statistics.median(prices):.2f} · {len(prices)} 台在租",
            "region": "", "stock": f"{len(prices)} 台", "url": "https://vast.ai/pricing",
        })
    return offers, {"machines": sum(len(v) for v in groups.values())}
