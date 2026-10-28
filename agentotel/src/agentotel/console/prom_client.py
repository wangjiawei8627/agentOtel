# -*- coding: utf-8 -*-
"""Prometheus 查询客户端（标准库实现，零额外依赖）。

封装 Prometheus HTTP API 的 instant query，供管理后台取数。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, List, Optional


def _instant_query(base_url: str, promql: str,
                   timeout: float = 5.0) -> List[dict]:
    """执行 instant query，返回 result 列表（vector 为各 series）。"""
    url = f"{base_url.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode(
        {"query": promql})
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != "success":
        return []
    return payload["data"].get("result", [])


def scalar(base_url: str, promql: str) -> Optional[float]:
    """取单值（聚合查询）。无数据返回 None。"""
    result = _instant_query(base_url, promql)
    if not result:
        return None
    try:
        # vector 结果：{"value": [ts, "123.4"]}
        return float(result[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return None


def labeled(base_url: str, promql: str,
            label: str) -> List[dict]:
    """取带标签的多 series，返回 [{"name": label值, "value": 数值}]。"""
    out = []
    for item in _instant_query(base_url, promql):
        try:
            out.append({
                "name": item["metric"].get(label, ""),
                "value": float(item["value"][1]),
            })
        except (KeyError, IndexError, ValueError):
            continue
    return out
