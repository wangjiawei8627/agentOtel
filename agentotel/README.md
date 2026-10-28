# AgentOTel

> OpenTelemetry 原生、可插拔的 AI Agent 埋点监控框架。一行初始化，给任意现有 Agent（LangGraph / LangChain / LlamaIndex / 自研 Agent）接入标准化的链路追踪、指标统计与成本监控。

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-green.svg)]()
[![Version](https://img.shields.io/badge/version-0.3.0-orange.svg)]()

## 为什么需要 AgentOTel

Agent 是**非确定性循环系统**：一次用户提问，内部可能经历「意图识别 → 规划 → 检索 → 多次 LLM 调用 → 多次工具调用 → 反思」。普通接口日志无法回答：

- Agent 这一步为什么选了这个工具？
- 哪一次 LLM 调用慢了、token 爆了？
- 工具调用失败、重试、死循环发生在哪里？
- 一次任务的真实成本（token 费用）是多少？

现有方案的问题：

| 方案 | 问题 |
|---|---|
| LangSmith / Langfuse 原生 SDK | 强绑定各自后端与 LangChain 生态，难接入自研 Agent，与企业内部 OTel 体系割裂 |
| OpenTelemetry 官方 | 只有基础 GenAI 属性定义，缺少 Agent 插桩、节点封装、开箱看板 |

**AgentOTel 不重造协议，而是做 OTel GenAI 语义约定的上层编排与增强层**，底层完全复用官方 OTel SDK 与 Collector，数据可投递到任意 OTel 后端（Jaeger / Tempo / Grafana / Langfuse / Signoz）。

## 核心特性

- **零侵入自动插桩**：`LangGraphInstrumentor / OpenAIInstrumentor / LlamaIndexInstrumentor`，业务代码不动
- **网关无代码插桩**：FastAPI 挂载 `AgentOTelMiddleware`，自动记录每个 HTTP 请求
- **极简手动埋点**：`@agent_span / @llm_span / @tool_span / @retrieval_span`，覆盖自研 Agent
- **标准对齐**：全面对齐 2026 最新 OTel GenAI Semantic Conventions，自动屏蔽框架字段差异
- **插件化增强**：PII 脱敏、本地 token 估算、可自定义插件
- **告警开箱**：7 条 Prometheus 告警 + Alertmanager 分组/静默/钉钉/飞书通知
- **智能尾采样**：保留错误/慢链路，正常链路按比例采样，降本不丢关键问题
- **质量评估**：规则评分（可靠性/效率）+ 可插拔 LLM 裁判，质量趋势可观测
- **轻量管理后台**：内置只读 Web 控制台，成功率/耗时/token/质量一屏总览
- **测试完善**：52 个 pytest 用例覆盖配置/映射/指标/告警/质量
- **合规友好**：消息原文默认不采集，敏感内容采集全部显式 opt-in
- **开箱即用**：一键启动 Collector + Jaeger + Prometheus + Alertmanager + Grafana

## 快速开始

### 1. 安装

```bash
# 核心 + LangGraph + OpenAI 插桩
pip install -e ".[langgraph,openai,token]"
# 或 LlamaIndex / FastAPI
pip install -e ".[llamaindex]"
pip install -e ".[fastapi]"
```

### 2. 启动可观测后端

```bash
cd deploy
docker compose up -d
```

一键启动四个组件：

| 组件 | 地址 | 用途 |
|---|---|---|
| Jaeger | http://127.0.0.1:16686 | 链路追踪 |
| Prometheus | http://127.0.0.1:9090 | 指标存储 |
| Grafana | http://127.0.0.1:3000 | 看板（admin/admin） |
| Collector | 4317 / 4318 | 数据网关 |

### 3. 两行代码接入

```python
from agentotel import init_agentotel, LangGraphInstrumentor, OpenAIInstrumentor

init_agentotel(service_name="my-agent", capture_message_content=True)
LangGraphInstrumentor().instrument()
OpenAIInstrumentor().instrument()
```

### 4. 查看链路

打开 Jaeger UI：<http://127.0.0.1:16686>，选择服务 `my-agent`，即可看到完整链路树：

```
invoke_agent langgraph                    # 一次 Agent 任务
├── node llm                              # LangGraph 节点
│   └── chat openai gpt-4o-mini           # LLM 调用（model / tokens / finish_reason）
├── node tools                            # 工具节点
│   └── execute_tool retrieve             # 工具调用
└── node llm
    └── chat openai gpt-4o-mini
```

### 5. 查看 Grafana 看板

打开 <http://127.0.0.1:3000>（admin/admin），进入 **AgentOTel → AgentOTel Overview**，预制看板包含四个区块：

- **概览**：Agent 调用数、成功率、总 Token、工具成功率、估算成本
- **Token 与成本**：输入/输出吞吐、按模型分布；顶部可填每百万 token 单价自动换算成本
- **耗时 P95**：LLM（P50/P95/P99）、工具（按工具）、Agent 端到端
- **工具调用**：成功率、调用次数、状态分布

完整可运行示例见 [`examples/langgraph_demo.py`](examples/langgraph_demo.py)。

## 手动埋点（自研 Agent）

```python
from agentotel.sdk import agent_span, llm_span, tool_span

@agent_span(agent_name="my-agent")
def run(query):
    return chat(query)

@llm_span(model="gpt-4o-mini", provider="openai")
def chat(prompt):
    return llm_client.chat.completions.create(...)

@tool_span(tool_name="search")
def search(q):
    ...
```

## 网关插桩（FastAPI 无代码）

```python
from fastapi import FastAPI
from agentotel.middleware import AgentOTelMiddleware

app = FastAPI()
app.add_middleware(AgentOTelMiddleware, capture_request_body=True)
```

每个 HTTP 请求自动生成一个 `http <method> <path>` Span，记录方法、状态码、耗时，并上报 `agentotel_http_*` 指标；内部若同时插桩，Agent 节点自动成为子 Span。

## LlamaIndex 插桩

```python
from agentotel import init_agentotel, LlamaIndexInstrumentor

init_agentotel(service_name="llamaindex-app")
LlamaIndexInstrumentor().instrument()
```

自动覆盖 LLM（chat/complete）、Retriever、Tool 调用。

## 告警

预制 Prometheus 告警规则（`deploy/alert_rules.yml`，共 7 条）：

| 告警 | 触发条件 | 级别 |
|---|---|---|
| AgentSuccessRateLow | 成功率 < 90% 持续 5m | critical |
| AgentErrorBurst | 每分钟错误 > 6 | warning |
| LLMP95LatencyHigh | LLM P95 > 3s | warning |
| ToolP95LatencyHigh | 工具 P95 > 5s | warning |
| ToolFailureRateHigh | 工具失败率 > 10% | critical |
| TokenUsageSpike | Token 速率 > 3 倍 1h 基线 | warning |
| TokenBudgetGuard | 5 分钟 token > 100 万 | warning |

## 配置

支持代码配置与环境变量（容器化友好）：

| 配置项 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `service_name` | `AGENTOTEL_SERVICE_NAME` | agentotel-app | 服务名 |
| `otlp_endpoint` | `AGENTOTEL_OTLP_ENDPOINT` | 127.0.0.1:4317 | collector 地址 |
| `sampler_ratio` | `AGENTOTEL_SAMPLER_RATIO` | 1.0 | 采样比例 |
| `capture_message_content` | `AGENTOTEL_CAPTURE_MESSAGE_CONTENT` | false | 采集消息原文 |
| `capture_tool_content` | `AGENTOTEL_CAPTURE_TOOL_CONTENT` | false | 采集工具内容 |
| `pii_mask_enabled` | `AGENTOTEL_PII_MASK` | false | PII 脱敏 |
| `token_estimate_enabled` | `AGENTOTEL_TOKEN_ESTIMATE` | false | 本地 token 估算 |

## 项目结构

```
agentotel/
├── src/agentotel/
│   ├── config.py              # 全局配置（dataclass + 环境变量）
│   ├── context.py             # 异步安全的 Agent 会话上下文
│   ├── semconv/               # GenAI 标准属性常量 + 框架字段映射
│   ├── plugins/               # 插件基类、PII 脱敏、token 估算
│   ├── instrumentors/         # 自动插桩：LangGraph / OpenAI / LlamaIndex
│   ├── middleware/            # 网关中间件：FastAPI
│   ├── sdk/                   # 手动埋点装饰器
│   ├── metrics/               # Metrics 上报（Counter/Histogram）
│   └── otel/                  # OTel 初始化与全局门面
├── examples/                  # 接入示例（langgraph / llamaindex / fastapi）
├── deploy/                    # collector + Jaeger + Prometheus + Grafana 一键部署
└── docs/                      # 架构文档、接口规范
```

## 文档

- [架构文档](docs/architecture.md)
- [接口规范](docs/api-reference.md)

## 运行测试

```bash
pip install -e ".[dev]"
python3 -m pytest -q          # 52 passed
```

## 通知与 Alertmanager

- `deploy/alertmanager.yml`：按 `alertname/category` 分组，critical 抑制 warning，重复提醒 2h
- 钉钉：`prometheus-webhook-dingtalk` 中转（配置见 `deploy/dingtalk/config.yml`）
- 飞书：`deploy/notify/feishu_adapter.py`（标准库实现，支持加签）
- 启动前在对应配置中填入真实机器人 token / secret

## 尾采样

Collector 端 `tail_sampling`：错误链路、慢链路（>5s）全保留，正常链路 10% 采样。阈值在 `deploy/otel-collector-config.yaml` 调整。

## 质量评估

```python
from agentotel.quality import RuleBasedQualityEvaluator, QualitySignals

ev = RuleBasedQualityEvaluator()
result = ev.evaluate(QualitySignals(success=True, tool_calls=2, tool_errors=0))
print(result.score, result.grade, result.deductions)
```

也可用 `LLMJudgeEvaluator(judge_fn=...)` 注入更强模型做内容评分。

## 管理后台

```bash
uvicorn agentotel.console.app:console_app --port 8080
# 打开 http://127.0.0.1:8080
```

## 版本路线

- **V0.1**：LangGraph + OpenAI 自动插桩、手动埋点 SDK、PII/token 插件、Metrics、Grafana 看板
- **V0.2**：LlamaIndex 插桩、FastAPI 网关中间件、Prometheus 告警规则
- **V0.3（当前）**：Alertmanager 钉钉/飞书、尾采样、质量评估、轻量管理后台
- **V0.4**：多 Agent 协作链路、成本账单、压测联动

## License

Apache-2.0
