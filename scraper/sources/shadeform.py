"""Shadeform 聚合 API（免登录）。hourly_price 单位为美分、按整机计，需 /100 /num_gpus。
只保留 gpurentalprices 未覆盖的云厂商，避免重复。"""
from ..net import get_json

URL = "https://api.shadeform.ai/v1/instances/types"

# Shadeform cloud 名 -> gpurentalprices provider key（已覆盖则跳过）
SAME_AS = {"lambdalabs": "lambda", "verda": "datacrunch"}
CLOUD_NAMES = {
    "massedcompute": "Massed Compute", "excesssupply": "Excess Supply", "paperspace": "Paperspace",
    "imwt": "IMWT", "denvr": "Denvr Dataworks", "boostrun": "Boostrun", "horizon": "Horizon",
    "phyntec": "Phyntec", "latitude": "Latitude.sh", "scaleway": "Scaleway",
}


def _gid(t, interconnect):
    sxm = (interconnect or "").lower() == "sxm"
    m = {
        "H100": "h100-sxm" if sxm else "h100-pcie", "H100_nvl": "h100-nvl",
        "A100_80G": "a100-sxm-80" if sxm else "a100-pcie-80", "A100": "a100-sxm-40" if sxm else "a100-pcie-40",
        "H200": "h200", "B200": "b200", "B300": "b300", "GH200": "gh200",
        "L40S": "l40s", "L40": "l40", "L4": "l4", "A40": "a40", "A30": "a30", "A10": "a10", "A16": "a16",
        "V100": "v100", "V100_32G": "v100",
        "A6000": "rtx-a6000", "A5000": "rtx-a5000", "A4000": "rtx-a4000",
        "RTXPro6000": "rtx-pro-6000", "RTX6000Ada": "rtx-6000-ada", "RTX4000Ada": "rtx-4000-ada",
        "RTX6000": "quadro-rtx-6000", "RTX4090": "rtx-4090", "RTX5090": "rtx-5090",
    }
    return m.get(t)


def fetch(covered_keys):
    d = get_json(URL)
    offers = []
    for it in d["instance_types"]:
        cloud = it["cloud"]
        if SAME_AS.get(cloud, cloud) in covered_keys:
            continue
        gid = _gid(it["gpu_type"], it.get("interconnect"))
        n = it.get("num_gpus") or 0
        if not gid or not n or not it.get("hourly_price"):
            continue
        av = it.get("availability") or []
        kinds = {a.get("rental_type") for a in av}
        regions = sorted({a.get("display_name") for a in av if a.get("available")})
        offers.append({
            "g": gid, "type": "rent", "src": "shadeform",
            "provider": CLOUD_NAMES.get(cloud, cloud.capitalize()), "pkey": cloud,
            "kind": "spot" if kinds == {"spot"} else "on-demand",
            "usd": round(it["hourly_price"] / 100 / n, 4),
            "n": n,
            "cfg": f"{n}× {it['gpu_type']} · {it.get('vcpus')} vCPU · {it.get('memory_in_gb')}GB RAM",
            "region": regions[0] + (f" 等{len(regions)}地" if len(regions) > 1 else "") if regions else "",
            "stock": "有货" if regions else "暂无库存",
            "url": "https://www.shadeform.ai/",
        })
    return offers, {"instance_types": len(d["instance_types"])}
