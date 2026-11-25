"""国内云 GPU 租用价（人民币/卡·时，按当日汇率折美元）：共绩算力、阿里云、算家云、矩池云。
腾讯云、火山引擎文档页只有规格无价格；AutoDL 需登录；智星云、优云智算为纯前端渲染，暂不抓。"""
import html
import re

from ..gpus import match_cn
from ..net import get_text


def _text_cells(s):
    """去脚本/样式后按标签切分为文本单元。"""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = html.unescape(re.sub(r"(?s)<[^>]+>", "\x00", s))
    return [c.strip() for c in s.split("\x00") if c.strip()]


def _offer(gid, provider, cny, fx, cfg, url, kind="on-demand", n=1):
    return {
        "g": gid, "type": "rent", "provider": provider, "kind": kind, "region": "中国",
        "usd": round(cny / fx, 4), "cny_hr": cny, "n": n, "cfg": cfg, "url": url, "cn": True,
    }


def _require(offers, name):
    if not offers:
        raise ValueError(f"{name}: no prices parsed (layout changed?)")
    return offers, {"rows": len(offers)}


def fetch_suanli(fx):
    url = "https://suanli.cn/product/server/"
    c = _text_cells(get_text(url))
    offers = []
    # 表格序列：卡型 | 显存 | x.xx 元/小时
    for i in range(len(c) - 2):
        m = re.match(r"^([\d.]+)\s*元/小时$", c[i + 2])
        if m and re.match(r"^\d+\s*G$", c[i + 1]):
            gid = match_cn(f"{c[i]} {c[i + 1]}")
            if gid:
                offers.append(_offer(gid, "共绩算力", float(m.group(1)), fx, f"{c[i]} · {c[i + 1].replace(' ', '')} · 云主机按时计费", url))
    return _require(offers, "suanli")


def fetch_aliyun(fx):
    url = "https://help.aliyun.com/zh/rds/apsaradb-rds-for-mysql/scheduled-scaling-for-rds-custom-ai-nodes"
    s = get_text(url)
    offers = []
    for row in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", s):
        c = [html.unescape(re.sub(r"(?s)<[^>]+>", "", x)).strip() for x in re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", row)]
        # 地域 | 卡型 | ACU_Type | 单卡元/小时 | 整机配置 | 单卡配置
        if len(c) >= 6 and re.match(r"^[\d.]+$", c[3]):
            gid = match_cn(c[1])
            if gid:
                offers.append(_offer(gid, "阿里云", float(c[3]), fx,
                                     f"RDS Custom AI 节点 {c[1]}（{c[2]}）按量 · 单卡 {c[5]}", url))
    return _require(offers, "aliyun")


def fetch_suanjia(fx):
    url = "https://suanjiayun.com"
    c = _text_cells(get_text(url))
    offers, seen = [], set()
    # 首页卡片：RTX 5090 | 描述 | 32 GB | 显存 | ... | 2.68 元 | / 小时起
    for i, cell in enumerate(c):
        m = re.match(r"^([\d.]+)\s*元$", cell)
        if not (m and i + 1 < len(c) and c[i + 1].replace(" ", "").startswith("/小时")):
            continue
        name = next((c[j] for j in range(i - 1, max(i - 14, -1), -1) if re.match(r"^(RTX|A|H|L)\s?\w*\d", c[j])), None)
        gid = match_cn(name or "")
        if gid and gid not in seen:
            seen.add(gid)
            offers.append(_offer(gid, "算家云", float(m.group(1)), fx, f"{name} · 首页起价", url))
    return _require(offers, "suanjia")


def fetch_matpool(fx):
    url = "https://matpool.com/host-market/gpu"
    s = get_text(url)
    s = re.sub(r'<span class="invisible[^"]*"[^>]*>[^<]*</span>', "", s)  # 去掉数字滚动的占位位
    t = "|".join(_text_cells(s))
    offers = []
    for m in re.finditer(r"\|最多\|(\d+)\|卡\|可用\|(\d+)卡\|([^|]+)\|([^|]+)\|(\d+GB)\|(.*?)¥\|?([\d.|]+)\|?/小时", t):
        gid = match_cn(m.group(3))
        if gid:
            spec = " · ".join(x for x in m.group(6).split("|") if re.search(r"核|内存|硬盘", x) and not re.search(r"核心数|系统内存|SSD", x))
            o = _offer(gid, "矩池云", float(m.group(7).replace("|", "")), fx,
                       f"{m.group(3)} {m.group(5)} · {spec}", url)
            o["region"] = f"中国 · {m.group(4)}"
            o["stock"] = f"最多 {m.group(1)} 卡可用"
            offers.append(o)
    return _require(offers, "matpool")
