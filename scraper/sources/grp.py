"""gpurentalprices.com 公开数据（CC BY 4.0，需注明出处）。
租用：/api/latest.json；购买：/buy 及各型号 /{gpu}/buy 页面表格；历史：/gpu-price-history.csv。
"""
import csv
import html
import io
import re
import time
from datetime import datetime

from ..net import get_json, get_text

BASE = "https://gpurentalprices.com"
CREDIT = {"name": "GPU Rental Prices", "url": f"{BASE}/data", "license": "CC BY 4.0"}

# 历史 CSV 未收录显示名的厂商
PROVIDER_NAMES = {
    "aws": "AWS", "azure": "Azure", "gcp": "Google Cloud", "oracle": "Oracle Cloud", "coreweave": "CoreWeave",
    "crusoe": "Crusoe", "together": "Together AI", "baseten": "Baseten", "cerebrium": "Cerebrium", "fal": "fal.ai",
    "fireworks": "Fireworks AI", "gpuwerk": "GPUwerk", "hetzner": "Hetzner", "impossiblecloud": "Impossible Cloud",
    "koyeb": "Koyeb", "latitude": "Latitude.sh", "replicate": "Replicate", "scaleway": "Scaleway", "synteq": "Synteq",
}


def provider_names():
    """从历史 CSV 中取 provider 与 gpu 的显示名。"""
    text = get_text(f"{BASE}/gpu-price-history.csv")
    rows = list(csv.DictReader(io.StringIO(text)))
    providers = {r["provider"]: r["provider_name"] for r in rows}
    gpus = {r["gpu"]: r["gpu_name"] for r in rows}
    return rows, providers, gpus


def fetch_rent(provider_display):
    d = get_json(f"{BASE}/api/latest.json")
    offers = []
    for o in d["offers"]:
        offers.append({
            "g": o["gpu"], "type": "rent", "src": "grp",
            "provider": provider_display.get(o["provider"]) or PROVIDER_NAMES.get(o["provider"]) or o["provider"].capitalize(),
            "pkey": o["provider"],
            "kind": o.get("kind") or "on-demand",
            "usd": float(o["usd_hr"]),
            "vram": o.get("vram_gb"),
            "n": o.get("min_gpus"),
            "cfg": o.get("instance") or "",
            "region": o.get("region") or "",
            "stock": o.get("availability") if o.get("availability") not in (None, "not-reported") else "",
            "url": o.get("source_url") or "",
            "at": (o.get("fetched_at") or d["date"])[:10],
        })
    stale = d.get("meta", {}).get("stale_providers", [])
    return offers, {"date": d["date"], "providers": len(d.get("providers", {})), "stale": stale,
                    "keys": set(d.get("providers", {}).keys())}


def _cells(row):
    return [html.unescape(re.sub(r"(?s)<[^>]+>", "", c)).strip() for c in re.findall(r"(?s)<td[^>]*>(.*?)</td>", row)]


def _money(s):
    m = re.search(r"\$([\d,]+(?:\.\d+)?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def _date(s):
    try:
        return datetime.strptime(s.strip(), "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def fetch_buy(delay=0.6):
    index = get_text(f"{BASE}/buy")
    slugs = sorted(set(re.findall(r'href="/([a-z0-9-]+)/buy"', index)))
    offers, failed = [], []
    for slug in slugs:
        try:
            page = get_text(f"{BASE}/{slug}/buy")
        except Exception:  # 单页失败不影响其他型号，由 build 沿用该页旧数据
            failed.append(slug)
            continue
        for table in re.findall(r'(?s)<table class="prices[^"]*">(.*?)</table>', page):
            heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"(?s)<th[^>]*>(.*?)</th>", table)]
            if not heads or heads[0] != "Retailer" or "<tbody" not in table:
                continue
            idx = {h: i for i, h in enumerate(heads)}
            for row in re.findall(r"(?s)<tr>(.*?)</tr>", table.split("<tbody", 1)[1]):
                c = _cells(row)
                if len(c) < len(heads):
                    continue
                link = re.search(r'href="([^"]+)"', row)
                price = _money(c[idx["USD"]])
                if price is None:
                    continue
                per = _money(c[idx["Per GPU"]]) if "Per GPU" in idx else price
                product = c[idx["Exact product"]]
                n = round(price / per) if per else 1
                offers.append({
                    "g": slug, "type": "buy", "src": "grp",
                    "provider": c[idx["Retailer"]],
                    "usd": price, "per": per, "n": n,
                    "server": n > 1 or bool(re.search(r"server|workstation|system", product, re.I)),
                    "cfg": product,
                    "cond": c[idx["Condition"]] if "Condition" in idx else "",
                    "stock": c[idx["Stock"]] if "Stock" in idx else "",
                    "url": link.group(1) if link else f"{BASE}/{slug}/buy",
                    "at": _date(c[idx["Checked"]]) if "Checked" in idx else "",
                })
        time.sleep(delay)
    if not offers:  # 页面改版时报错，由 build 沿用旧数据
        raise ValueError(f"no buy listings parsed from {len(slugs)} pages")
    return offers, {"pages": len(slugs), "failed": failed}
