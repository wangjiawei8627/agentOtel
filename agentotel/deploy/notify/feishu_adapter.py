# -*- coding: utf-8 -*-
"""飞书自定义机器人适配器（Alertmanager -> 飞书）。

Alertmanager 原生 webhook 是 Prometheus 格式，飞书自定义机器人要求
特定的消息体，因此需要本适配器做格式转换。

零额外依赖（仅标准库），运行：
    FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx \
    FEISHU_SECRET=SECxxx \
    python feishu_adapter.py   # 监听 8061

加签说明：飞书机器人若开启“签名校验”，需提供 FEISHU_SECRET，
适配器会按 timestamp + secret 计算 HMAC-SHA256 签名。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET", "")
LISTEN_PORT = int(os.environ.get("PORT", "8061"))


def _sign(timestamp: int, secret: str) -> str:
    """飞书加签：HMAC-SHA256(timestamp + '\\n' + secret)，再 base64。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def build_feishu_card(payload: dict) -> dict:
    """把 Alertmanager payload 转成飞书 interactive 卡片。"""
    alerts = payload.get("alerts", [])
    status = payload.get("status", "firing")
    color = "red" if status == "firing" else "green"

    lines = []
    for a in alerts:
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        name = labels.get("alertname", "unknown")
        sev = labels.get("severity", "-")
        desc = ann.get("description", ann.get("summary", ""))
        st = a.get("startsAt", "")
        lines.append(f"**{name}** [{sev}]\n{desc}\n触发: {st}")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"AgentOTel 告警: {status}",
                },
                "template": color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n\n".join(lines) or "（无告警内容）",
                    },
                }
            ],
        },
    }


def send_to_feishu(card: dict) -> None:
    """把卡片 POST 到飞书；若配置 secret 则加签。"""
    url = FEISHU_WEBHOOK
    if FEISHU_SECRET:
        ts = int(time.time())
        sign = _sign(ts, FEISHU_SECRET)
        card["timestamp"] = str(ts)
        card["sign"] = sign
    body = json.dumps(card).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静音默认日志
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            card = build_feishu_card(payload)
            if FEISHU_WEBHOOK:
                send_to_feishu(card)
            code, msg = 200, b"ok"
        except Exception as exc:
            code, msg = 500, str(exc).encode("utf-8")
        self.send_response(code)
        self.end_headers()
        self.wfile.write(msg)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    print(f"feishu adapter listening on :{LISTEN_PORT}")
    server.serve_forever()
