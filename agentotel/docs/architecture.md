# AgentOTel 架构文档

> 版本：V0.1 ｜ 更新：2026-10

## 1. 设计目标

构建一个**中立、标准 OTel 原生、跨框架通用**的 Agent 可观测框架，使任意现有 Agent 能以极低改造成本接入统一的链路追踪、指标统计与成本监控。

四条核心设计原则：

1. **最小侵入**：自动插桩优先，一行初始化接入；无法自动插桩时提供极简手动埋点
2. **规范收敛**：所有 LLM / Tool / Retrieval / Agent 节点统一对齐 OTel GenAI 最新语义约定
3. **插件化扩展**：脱敏、token 计算、自定义增强均为可插拔插件
4. **解耦**：采集层、处理层、存储展示层分离，不绑定任何后端

## 2. 分层架构

```
┌─────────────────────────────────────────────────────────┐
│  接入层                                                  │
│  ├─ 自动 Instrumentor（LangGraph / OpenAI / ...）        │
│  ├─ 手动埋点 SDK（@agent_span / @llm_span / ...）        │
│  └─ 网关侧埋点（V0.2）                                    │
└───────────────────────────┬─────────────────────────────┘
                            │ 标准 OTel Signal
┌─────────────────────────────────────────────────────────┐
│  核心内核层                                              │
│  ├─ SemConv 适配器（框架字段 -> gen_ai.* 映射）          │
│  ├─ 插件管道（PII / token / 自定义）                     │
│  ├─ AgentContext（会话上下文透传）                       │
│  └─ 配置管理（采样 / 开关 / 合规）                       │
└───────────────────────────┬─────────────────────────────┘
                            │ OTLP
┌─────────────────────────────────────────────────────────┐
│  数据网关层：OTel Collector                             │
│  接收 → 限流/批量 → 分发                                │
└───────────────────────────┬─────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  存储展示层（可替换）                                    │
│  Jaeger / Tempo（Trace）+ Prometheus（Metric）+ Grafana │
└─────────────────────────────────────────────────────────┘
```

**关键取舍**：内核不重复实现 OTLP exporter，直接复用官方 OTel SDK 与 Collector。框架的价值在于「Agent 领域的插桩、语义对齐、增强处理、开箱看板」。

## 3. 核心模块职责

### 3.1 接入层

| 模块 | 职责 |
|---|---|
| `instrumentors/langgraph.py` | patch `StateGraph.add_node`（节点 Span）与 `CompiledStateGraph.invoke/ainvoke`（根 Span） |
| `instrumentors/openai.py` | patch `chat.completions.create`（同步/异步），采集 model、usage、finish_reason |
| `instrumentors/base.py` | 统一生命周期、幂等保护、依赖检查 |
| `sdk/decorators.py` | 装饰器形式手动埋点，自动适配同步/异步 |

### 3.2 内核层

| 模块 | 职责 |
|---|---|
| `semconv/attributes.py` | 标准属性 key 常量，规范升级只改一处 |
| `semconv/mapping.py` | 声明式映射表 + 路径取值，把框架响应翻译成标准属性 |
| `plugins/base.py` | 插件基类与链式管道，单插件失败不影响主流程 |
| `plugins/pii_filter.py` | 手机号/身份证/银行卡/邮箱正则脱敏 |
| `plugins/token_estimator.py` | 缺 usage 时用 tiktoken/字符数估算 token |
| `context.py` | 基于 contextvars 的异步安全会话上下文 |
| `config.py` | 不可变配置 + 环境变量覆盖 |
| `otel/setup.py` | 组装 Resource/采样器/导出器/插件，提供全局单例 |

## 4. Span 模型

AgentOTel 生成的标准 Span 树：

| Span | operation.name | 关键属性 |
|---|---|---|
| `invoke_agent <name>` | invoke_agent | workflow.name、app.agent_name、app.user_query |
| `node <key>` | —（业务节点） | app.node.name、app.duration_ms |
| `chat <provider> <model>` | chat | provider.name、request.model、usage.*、response.finish_reasons |
| `execute_tool <tool>` | execute_tool | tool.name、tool.call.arguments/result |
| `retrieval <ds>` | retrieval | data_source.id、app.retrieval.doc_count |

**父子关系**：由 OTel Context 自动维护（`start_as_current_span` 自动挂到当前 Span 下）。

## 5. 数据流

1. 业务触发 Agent（`graph.invoke` / 装饰器包裹的函数）
2. Instrumentor 创建 Span，写入框架原始数据
3. `semconv.mapping` 把框架字段映射为标准属性
4. 节点/调用结束时，插件管道依次执行（脱敏、补 token）
5. Span 经 `BatchSpanProcessor` 异步通过 OTLP 发送
6. Collector 限流、批量后转发到 Jaeger
7. 前端按 trace_id / session_id / node 检索与可视化

## 6. 关键设计决策

### 6.1 为什么自动插桩 + 手动埋点并存
- 自动插桩只能 Hook 框架暴露的入口，自定义调度、记忆、缓存、业务分支抓不到
- 手动埋点用于补齐这些节点，二者互补；生产推荐「自动兜底 + 手动补关键节点」

### 6.2 为什么敏感内容默认不采集
- prompt / completion / tool 参数含用户 PII，规范明确要求 opt-in
- 由 `capture_message_content` / `capture_tool_content` 独立开关控制

### 6.3 为什么用 contextvars
- Agent 多为 asyncio 并发，threading.local 会在协程间串号
- contextvars 每个任务独立，保证 session_id / user_id 不串

### 6.4 规范演进的应对
- GenAI SemConv 仍在 development 阶段，字段会变
- 所有 key 收敛到 `semconv/attributes.py`，并通过 `OTEL_SEMCONV_STABILITY_OPT_IN` 锁定版本

## 7. 非功能性约束

- **性能**：所有上报异步化；插件开销可控；支持采样降低量
- **隔离**：插件异常被捕获，不影响 Agent 主流程
- **可观测自洽**：插件错误自身以 Span Event 记录
- **可替换**：后端切换只改 Collector 配置，业务代码零改动
