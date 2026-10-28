# -*- coding: utf-8 -*-
"""AgentOTel 轻量 Web 管理后台（只读）。

提供一个 FastAPI 应用：
- ``/``            概览页面（单页 HTML）
- ``/api/overview`` 关键指标聚合（成功率 / 调用量 / P95 / token / 质量）
- ``/api/health``  健康检查

启动：
    uvicorn agentotel.console.app:console_app --port 8080
或通过 ``create_console_app`` 自定义 Prometheus 地址。

定位：轻量、只读、零前端构建；复杂分析仍建议用 Grafana。
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from . import prom_client as pc

# 概览页用到的 PromQL（与 Grafana / 告警口径保持一致）
DEFAULT_PROM_URL = os.environ.get("AGENTOTEL_PROM_URL", "http://127.0.0.1:9090")


def create_console_app(prometheus_url: str = DEFAULT_PROM_URL) -> FastAPI:
    """构造管理后台应用。"""
    app = FastAPI(title="AgentOTel Console", version="0.3.0")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/overview")
    def overview():
        """聚合关键指标；Prometheus 不可用时对应字段为 null。"""
        q = lambda promql: pc.scalar(prometheus_url, promql)
        data = {
            "success_rate": q(
                "sum(rate(agentotel_agent_calls_total{status='ok'}[5m]))"
                " / clamp_min(sum(rate(agentotel_agent_calls_total[5m])), 1)"
            ),
            "agent_rpm": q(
                "sum(rate(agentotel_agent_calls_total[5m])) * 60"
            ),
            "llm_p95_ms": q(
                "histogram_quantile(0.95, "
                "sum(rate(agentotel_llm_duration_ms_bucket[5m])) by (le))"
            ),
            "tokens_5m": q(
                "sum(increase(agentotel_llm_tokens_total[5m]))"
            ),
            "tool_success_rate": q(
                "sum(rate(agentotel_tool_calls_total{status='ok'}[5m]))"
                " / clamp_min(sum(rate(agentotel_tool_calls_total[5m])), 1)"
            ),
            "quality_avg": q(
                "sum(agentotel_quality_score_sum)"
                " / clamp_min(sum(agentotel_quality_score_count), 1)"
            ),
        }
        return JSONResponse(data)

    @app.get("/api/by-model")
    def by_model():
        """按模型统计 5 分钟 token 与 P95。"""
        tokens = pc.labeled(
            prometheus_url,
            "sum by (model)(increase(agentotel_llm_tokens_total[5m]))",
            "model",
        )
        return {"tokens": tokens}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _index_html()

    return app


def _index_html() -> str:
    """内联单页：纯静态 HTML + 少量 JS，无需构建。"""
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AgentOTel Console</title>
<style>
  body { font-family: -apple-system, "Segoe UI", sans-serif; margin: 0;
         background: #0f172a; color: #e2e8f0; }
  header { padding: 20px 28px; background: #1e293b; }
  h1 { font-size: 18px; margin: 0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(200px,1fr));
          gap: 16px; padding: 28px; }
  .card { background: #1e293b; border-radius: 10px; padding: 18px; }
  .card .label { font-size: 13px; color: #94a3b8; }
  .card .value { font-size: 28px; font-weight: 600; margin-top: 8px; }
  .good { color: #4ade80; } .warn { color: #fbbf24; } .bad { color: #f87171; }
  footer { padding: 0 28px 24px; color: #64748b; font-size: 12px; }
</style>
</head>
<body>
<header><h1>AgentOTel 管理后台 · 概览</h1></header>
<div class="grid" id="grid"></div>
<footer>数据每 10s 自动刷新；复杂分析请使用 Grafana。</footer>
<script>
const pct = v => v == null ? "—" : (v * 100).toFixed(1) + "%";
const num = v => v == null ? "—" : Math.round(v);
const CARDS = [
  { key: "success_rate", label: "Agent 成功率", fmt: pct },
  { key: "agent_rpm", label: "调用量 (次/分)", fmt: num },
  { key: "llm_p95_ms", label: "LLM P95 (ms)", fmt: num },
  { key: "tokens_5m", label: "近5分钟 Token", fmt: num },
  { key: "tool_success_rate", label: "工具成功率", fmt: pct },
  { key: "quality_avg", label: "平均质量分", fmt: num },
];
async function load() {
  let d = {};
  try { d = await (await fetch("/api/overview")).json(); } catch(e) {}
  document.getElementById("grid").innerHTML = CARDS.map(c => `
    <div class="card"><div class="label">${c.label}</div>
      <div class="value">${c.fmt(d[c.key])}</div></div>`).join("");
}
load(); setInterval(load, 10000);
</script>
</body>
</html>
"""


# 供 uvicorn 直接引用：uvicorn agentotel.console.app:console_app
console_app: Optional[FastAPI] = create_console_app()
#（注：内容由AI生成）
