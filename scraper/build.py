"""每日构建入口：python -m scraper.build
抓取各数据源 -> 归一合并 -> 统计 -> 写 site/data/latest.json、history.json 与 data/snapshots/。
单个数据源失败时沿用上次数据（标记为过期），不影响整体。"""
import gzip
import json
import statistics
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import gpus as G
from .net import get_json
from .sources import cn, grp, shadeform, vast

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site" / "data"
LATEST = SITE_DATA / "latest.json"
HISTORY = SITE_DATA / "history.json"
SNAP_DIR = ROOT / "data" / "snapshots"
MANUAL = ROOT / "data" / "manual.json"

ON_DEMAND = {"on-demand", "secure"}  # 按需价；走势也只用这一口径
CHEAP = {"community", "spot", "marketplace"}  # 低价但无保障


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def fx_rate(prev):
    try:
        d = get_json("https://open.er-api.com/v6/latest/USD")
        return {"usdcny": round(d["rates"]["CNY"], 4), "at": d["time_last_update_utc"], "src": "exchangerate-api.com"}
    except Exception as e:
        print(f"[fx] failed: {e}", file=sys.stderr)
        return prev.get("fx") or {"usdcny": 7.1, "at": "", "src": "fallback"}


def run_sources(prev):
    prev_offers = prev.get("offers", [])
    status, offers = [], []
    ctx = {"providers": {}, "gpu_names": {}, "history_rows": [], "grp_keys": set()}

    try:
        ctx["history_rows"], ctx["providers"], ctx["gpu_names"] = grp.provider_names()
    except Exception as e:
        print(f"[grp names] failed: {e}", file=sys.stderr)

    def grp_rent():
        o, meta = grp.fetch_rent(ctx["providers"])
        ctx["grp_keys"] = meta["keys"]
        meta["keys"] = sorted(meta["keys"])  # 持久化，供下次 grp_rent 失败时给 Shadeform 去重
        return o, meta

    def grp_buy():
        o, meta = grp.fetch_buy()
        failed = set(meta["failed"])
        carried = [dict(x, stale=True) for x in prev_offers if x.get("sid") == "grp_buy" and x["g"] in failed]
        return o + carried, meta

    prev_keys = set(next((s.get("meta", {}).get("keys", []) for s in prev.get("sources", []) if s["id"] == "grp_rent"), []))

    runners = [
        ("grp_rent", "GPU Rental Prices · 租用", "https://gpurentalprices.com/data", grp_rent),
        ("grp_buy", "GPU Rental Prices · 购买", "https://gpurentalprices.com/buy", grp_buy),
        ("shadeform", "Shadeform", "https://www.shadeform.ai/", lambda: shadeform.fetch(ctx["grp_keys"] or prev_keys)),
        ("vast", "Vast.ai", "https://vast.ai/", vast.fetch),
        ("olbaba", "航业算力", "https://ai.olbaba.com/market/gpu.html", cn.fetch_olbaba),
        ("qudao", "宽泛采销", "https://qudao.co/", cn.fetch_qudao),
    ]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for sid, name, url, fn in runners:
        st = {"id": sid, "name": name, "url": url}
        try:
            got, meta = fn()
            for o in got:
                o["sid"] = sid
                o.setdefault("at", today)
            offers += got
            st.update(ok=True, count=len(got), meta=meta, at=today)
        except Exception as e:
            traceback.print_exc()
            old = [o for o in prev_offers if o.get("sid") == sid]
            for o in old:
                o["stale"] = True
            offers += old
            last = next((s.get("at") for s in prev.get("sources", []) if s["id"] == sid), "")
            st.update(ok=False, count=len(old), error=str(e)[:200], at=last)
        status.append(st)
        print(f"[{sid}] ok={st['ok']} count={st['count']}")

    manual = load(MANUAL, {"offers": []})["offers"]
    for o in manual:
        o["sid"] = "manual"
    offers += manual
    status.append({"id": "manual", "name": "手工参考价", "url": "", "ok": True, "count": len(manual), "at": today})
    return offers, status, ctx


def drop_outliers(offers):
    """租用价中明显的占位值（低于同型号中位数 25%）剔除。"""
    by = {}
    for o in offers:
        if o["type"] == "rent":
            by.setdefault(o["g"], []).append(o["usd"])
    med = {g: statistics.median(v) for g, v in by.items() if len(v) >= 4}
    return [o for o in offers if not (o["type"] == "rent" and o["g"] in med and o["usd"] < med[o["g"]] * 0.25)]


def _min(items, key):
    items = [i for i in items if i.get(key)]
    return min(items, key=lambda i: i[key]) if items else None


def _max(items, key):
    items = [i for i in items if i.get(key)]
    return max(items, key=lambda i: i[key]) if items else None


def summarize(offers, gpu_names):
    """按家族汇总；variants 列出家族下各规格 id 与显示名。"""
    groups = {}
    for o in offers:
        groups.setdefault(G.family(o["g"]), []).append(o)
    out = []
    for fid, items in groups.items():
        rent = [o for o in items if o["type"] == "rent"]
        od = [o for o in rent if o.get("kind") in ON_DEMAND]
        priced = [o for o in items if not o.get("ref")]  # 官方建议价不参与最低价
        buy = [o for o in priced if o["type"] == "buy"]
        cards = [o for o in buy if not o.get("server")]
        servers = [o for o in buy if o.get("server")]
        cny = [o for o in priced if o["type"] == "cn" and not o.get("server")]  # 整机报道价不算单卡最低
        vram = [o.get("vram") for o in items if o.get("vram")]
        od_min, any_min = _min(od, "usd"), _min(rent, "usd")
        cheap_min = _min([o for o in rent if o.get("kind") in CHEAP], "usd")
        card_min, srv_min, cn_min = _min(cards, "usd"), _min(servers, "per"), _min(cny, "cny")
        od_max, card_max, srv_max, cn_max = _max(od, "usd"), _max(cards, "usd"), _max(servers, "per"), _max(cny, "cny")
        variants = sorted({o["g"] for o in items})
        out.append({
            "id": fid, "name": G.family_name(fid, gpu_names), "tier": G.tier(fid), "arch": G.arch(fid), "rank": G.rank(fid),
            "variants": [{"id": v, "name": G.pretty(v, gpu_names)} for v in variants],
            "vram": max(vram) if vram else None,
            "rent": {
                "od_min": od_min and od_min["usd"], "od_min_p": od_min and od_min["provider"],
                "od_max": od_max and od_max["usd"], "od_max_p": od_max and od_max["provider"],
                "median": round(statistics.median([o["usd"] for o in od]), 4) if od else None,
                "any_min": any_min and any_min["usd"], "any_min_p": any_min and any_min["provider"],
                "cheap_min": cheap_min and cheap_min["usd"], "cheap_min_p": cheap_min and cheap_min["provider"],
                "n": len(rent), "providers": len({o["provider"] for o in rent}),
            },
            "buy": {
                "card_min": card_min and card_min["usd"], "card_min_p": card_min and card_min["provider"],
                "srv_per_min": srv_min and srv_min["per"], "srv_min": srv_min and srv_min["usd"],
                "srv_min_p": srv_min and srv_min["provider"], "srv_n": srv_min and srv_min.get("n"),
                "card_max": card_max and card_max["usd"], "card_max_p": card_max and card_max["provider"],
                "srv_per_max": srv_max and srv_max["per"], "srv_max_p": srv_max and srv_max["provider"],
                "n": len(buy),
            },
            "cn": {"min": cn_min and cn_min["cny"], "min_p": cn_min and cn_min["provider"],
                   "max": cn_max and cn_max["cny"], "max_p": cn_max and cn_max["provider"], "n": len(cny)},
        })
    out.sort(key=lambda g: (g["rank"], -(g["rent"]["median"] or 0), g["id"]))
    return out


def update_history(summary, offers, ctx, today):
    """走势只用 gpurentalprices 同口径数据（种子历史也来自它），避免新增数据源造成的假涨跌。"""
    trend = {}
    for o in offers:
        if o.get("sid") == "grp_rent" and not o.get("stale") and o.get("kind") in ON_DEMAND:
            f = G.family(o["g"])
            trend[f] = min(trend.get(f, o["usd"]), o["usd"])
    hist = load(HISTORY, {})
    if not hist.get("_seeded") and ctx["history_rows"]:  # 用 gpurentalprices 每日最低价历史作种子（成功一次即止）
        seed = {}
        for r in ctx["history_rows"]:
            if r.get("kind") not in ON_DEMAND or G.excluded(r["gpu"]) or not r.get("usd_per_gpu_hr"):
                continue
            series = seed.setdefault(G.family(r["gpu"]), {})
            p = float(r["usd_per_gpu_hr"])
            series[r["date"]] = [min(p, series.get(r["date"], [p])[0]), None, None]
        for g, s in seed.items():
            have = {row[0] for row in hist.get(g, [])}
            hist[g] = sorted(hist.get(g, []) + [[d, *v] for d, v in s.items() if d not in have])
        hist["_seeded"] = True
    for g in summary:
        row = [today, trend.get(g["id"]), g["rent"]["median"], g["buy"]["card_min"] or g["buy"]["srv_per_min"]]
        if not any(row[1:]):
            continue
        series = [r for r in hist.get(g["id"], []) if r[0] != today]
        series.append(row)
        hist[g["id"]] = series[-400:]
    return hist


def main():
    prev = load(LATEST, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fx = fx_rate(prev)
    offers, status, ctx = run_sources(prev)

    offers = [o for o in offers if not G.excluded(o["g"])]
    offers = drop_outliers(offers)
    for o in offers:
        o.pop("pkey", None)
    summary = summarize(offers, ctx["gpu_names"])

    data = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "date": today, "fx": fx, "sources": status, "gpus": summary, "offers": offers,
        "credits": [grp.CREDIT],
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    LATEST.write_text(text, encoding="utf-8")
    (SNAP_DIR / f"{today}.json.gz").write_bytes(gzip.compress(text.encode("utf-8")))
    HISTORY.write_text(json.dumps(update_history(summary, offers, ctx, today), separators=(",", ":")), encoding="utf-8")

    ok = sum(s["ok"] for s in status)
    print(f"done: {len(summary)} GPUs, {len(offers)} offers, sources ok {ok}/{len(status)}")
    if not any(s["ok"] for s in status if s["id"] in ("grp_rent", "grp_buy")):
        sys.exit(1)  # 主干数据源全挂时让 CI 显红


if __name__ == "__main__":
    main()
