"""最小 HTTP 工具：标准库实现，支持 gzip，统一 UA 与超时。"""
import gzip
import json
import urllib.request

UA = "gpu-price-dashboard/1.0"


def get(url, payload=None, headers=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Encoding", "gzip")
    if data:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body


def get_text(url, **kw):
    return get(url, **kw).decode("utf-8", errors="replace")


def get_json(url, **kw):
    return json.loads(get(url, **kw))
