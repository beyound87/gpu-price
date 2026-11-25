"""GPU 型号注册表：统一 id（沿用 gpurentalprices 的 id 体系）、显示名、档次、架构、排序。"""
import re

# 非 NVIDIA 或无意义条目，直接排除
EXCLUDE = re.compile(r"^(mi\d|gaudi|cpu|unknown)")

# 国内特供/国内渠道常见型号（海外云与经销商基本没有）
CN_ONLY = {"h20", "h800", "a800", "l20", "rtx-5090d", "rtx-4090d", "rtx-4090d-48g", "rtx-4090-48g", "rtx-pro-6000d"}

NAME_OVERRIDES = {
    "h100": "H100（未注明规格）", "h100-sxm": "H100 SXM", "h100-pcie": "H100 PCIe", "h100-nvl": "H100 NVL",
    "h200": "H200", "h200-nvl": "H200 NVL", "b200": "B200", "b300": "B300",
    "gb200": "GB200", "gb300": "GB300", "gh200": "GH200", "rubin": "Rubin",
    "a100": "A100（未注明规格）", "a100-sxm-80": "A100 SXM 80GB", "a100-sxm-40": "A100 SXM 40GB",
    "a100-pcie-80": "A100 PCIe 80GB", "a100-pcie-40": "A100 PCIe 40GB",
    "rtx-pro-6000": "RTX PRO 6000", "rtx-pro-6000-server": "RTX PRO 6000 服务器版",
    "rtx-pro-6000-wk": "RTX PRO 6000 工作站版", "rtx-pro-6000-maxq": "RTX PRO 6000 Max-Q",
    "rtx-pro-6000d": "RTX PRO 6000D", "rtx-5090d": "RTX 5090D", "rtx-4090d": "RTX 4090D",
    "rtx-4090d-48g": "RTX 4090D 48G 改", "rtx-4090-48g": "RTX 4090 48G 改",
    "h20": "H20", "h800": "H800", "a800": "A800", "l20": "L20", "dgx-spark": "DGX Spark",
}

# 档次排序：越靠前越高端
FAMILY_ORDER = [
    "rubin", "gb300", "b300", "gb200", "b200", "h200", "gh200", "h100", "h800", "h20",
    "a100", "a800", "l40s", "l40", "l20", "l4", "a40", "a30", "a10", "a16", "v100", "t4",
    "rtx-pro-6000", "rtx-pro-5000", "rtx-pro-4500", "rtx-pro-4000", "rtx-6000-ada", "rtx-5000-ada",
    "rtx-4000", "rtx-2000-ada", "rtx-a6000", "rtx-a5000", "rtx-a4500", "rtx-a4000", "rtx-a2000",
    "quadro", "dgx-spark",
    "rtx-5090", "rtx-5080", "rtx-5070-ti", "rtx-5070", "rtx-5060", "rtx-4090", "rtx-4080", "rtx-4070",
    "rtx-4060", "rtx-3090", "rtx-3080", "rtx-3070",
]

ARCH = [
    (r"^rubin", "Rubin"), (r"^(gb300|b300)", "Blackwell Ultra"), (r"^(gb200|b200|rtx-pro|rtx-50|dgx-spark)", "Blackwell"),
    (r"^(h|gh)\d", "Hopper"), (r"^(a\d|rtx-a)", "Ampere"), (r"^(l\d|rtx-40|.*-ada)", "Ada Lovelace"),
    (r"^rtx-30", "Ampere"), (r"^(t4|quadro)", "Turing"), (r"^v100", "Volta"),
]


def tier(gid):
    if gid in CN_ONLY:
        return "cn"
    if re.match(r"^rtx-(30|40|50)\d\d", gid) and "ada" not in gid:
        return "gaming"
    if re.match(r"^(rtx-pro|rtx-a|rtx-\d000-|rtx-\d000$|quadro|dgx-spark)", gid) or "ada" in gid:
        return "ws"
    return "dc"


def arch(gid):
    for pat, name in ARCH:
        if re.match(pat, gid):
            return name
    return ""


def rank(gid):
    for i, fam in enumerate(FAMILY_ORDER):
        if gid == fam or gid.startswith(fam + "-") or gid.startswith(fam):
            return i
    return len(FAMILY_ORDER)


def pretty(gid, known_names=None):
    if gid in NAME_OVERRIDES:
        return NAME_OVERRIDES[gid]
    if known_names and gid in known_names:
        return known_names[gid]
    out = []
    for p in gid.split("-"):
        if p == "ti":
            out.append("Ti")
        elif p in ("ada", "super", "laptop", "server"):
            out.append(p.capitalize())
        else:
            out.append(p.upper())
    return " ".join(out)


def family(gid):
    """把规格变体归到家族：h100-sxm / a100-pcie-80 / h200-nvl / rtx-pro-6000-server -> h100 / a100 / h200 / rtx-pro-6000。"""
    f = re.sub(r"-(sxm\d?|pcie)(-\d+)?$", "", gid)
    f = re.sub(r"-(nvl|server|wk|maxq)$", "", f)
    return f


def family_name(fid, known_names=None):
    return pretty(fid, known_names).replace("（未注明规格）", "")


def excluded(gid):
    return bool(EXCLUDE.match(gid or ""))


# 国内商品名 -> 统一 id（按顺序匹配，先具体后笼统）
CN_PATTERNS = [
    (r"dgx\s*spark", "dgx-spark"),
    (r"pro\s*6000\s*d", "rtx-pro-6000d"),
    (r"pro\s*6000", "rtx-pro-6000"),
    (r"pro\s*5000", "rtx-pro-5000"),
    (r"pro\s*4500", "rtx-pro-4500"),
    (r"pro\s*4000", "rtx-pro-4000"),
    (r"5090\s*d", "rtx-5090d"),
    (r"5090", "rtx-5090"),
    (r"5080", "rtx-5080"),
    (r"5070\s*ti", "rtx-5070-ti"),
    (r"5070", "rtx-5070"),
    (r"5060\s*ti", "rtx-5060-ti-16gb"),
    (r"5060", "rtx-5060"),
    (r"4090\s*d.*48", "rtx-4090d-48g"),
    (r"4090.*48", "rtx-4090-48g"),
    (r"4090\s*d", "rtx-4090d"),
    (r"4090", "rtx-4090"),
    (r"4080", "rtx-4080"),
    (r"4060", "rtx-4060"),
    (r"3090", "rtx-3090"),
    (r"\bb300\b", "b300"), (r"\bb200\b", "b200"), (r"\bh200\b", "h200"), (r"\bh100\b", "h100"),
    (r"\bh800\b", "h800"), (r"\bh20\b", "h20"), (r"\ba800\b", "a800"), (r"\ba100\b", "a100"),
    (r"\bl40s\b", "l40s"), (r"\bl20\b", "l20"), (r"\bl40\b", "l40"),
    (r"\ba10\b", "a10"), (r"\ba30\b", "a30"), (r"\bv100\b", "v100"),
    (r"\ba6000\b", "rtx-a6000"), (r"\ba5000\b", "rtx-a5000"), (r"\ba4000\b", "rtx-a4000"), (r"\ba2000\b", "rtx-a2000"),
]


def match_cn(name):
    s = name.lower()
    for pat, gid in CN_PATTERNS:
        if re.search(pat, s):
            return gid
    return None
