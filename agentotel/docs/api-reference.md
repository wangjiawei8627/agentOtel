# AgentOTel 接口规范

> 版本：V0.1 ｜ 更新：2026-10

本规范描述 AgentOTel 对外暴露的全部公共接口。所有接口均为同步/异步双兼容。

---

## 1. 初始化

### `init_agentotel(config=None, **kwargs) -> AgentOTel`

初始化全局单例（幂等，重复调用返回同一实例）。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| config | AgentOTelConfig | None | 完整配置对象；提供时忽略 kwargs |
| **kwargs | - | - | 透传给 `AgentOTelConfig.from_env` 覆盖 |

```python
init_agentotel(service_name="my-agent", sampler_ratio=0.5)
```

### `get_agentotel() -> AgentOTel`

获取已初始化单例；未初始化时用默认配置兜底。

### `AgentOTel` 方法

| 方法 | 说明 |
|---|---|
| `add_plugin(plugin)` | 运行期追加插件，返回自身 |
| `shutdown()` | flush 批量处理器，进程退出前调用 |

---

## 2. 配置：`AgentOTelConfig`

不可变 dataclass，支持 `AgentOTelConfig.from_env(**overrides)`。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| service_name | str | agentotel-app | 服务名 |
| service_version | str | 0.0.0 | 服务版本 |
| environment | str | dev | 环境标识 |
| otlp_endpoint | str | 127.0.0.1:4317 | collector gRPC 地址 |
| insecure | bool | True | 禁用 TLS |
| sampler_ratio | float | 1.0 | 头部采样比例 [0,1] |
| enabled_plugins | tuple | () | 启用插件名 |
| capture_message_content | bool | False | 采集消息原文（opt-in） |
| capture_tool_content | bool | False | 采集工具内容（opt-in） |
| pii_mask_enabled | bool | False | PII 脱敏 |
| token_estimate_enabled | bool | False | 本地 token 估算 |
| default_session_id | str/None | None | 默认会话 ID |
| default_user_id | str/None | None | 默认用户 ID |

---

## 3. 自动插桩

所有 Instrumentor 继承 `BaseAgentInstrumentor`，统一接口：

```python
inst = XxxInstrumentor().instrument(**kwargs)   # 插桩（幂等）
inst.uninstrument(**kwargs)                      # 撤销（幂等）
```

### 3.1 `LangGraphInstrumentor`

| 被 patch 目标 | 生成 Span |
|---|---|
| `StateGraph.add_node` | `node <key>`（自动识别同步函数/异步函数/Runnable） |
| `CompiledStateGraph.invoke` | `invoke_agent langgraph` |
| `CompiledStateGraph.ainvoke` | `invoke_agent langgraph` |

节点 Span 属性：`app.node.name`、`app.duration_ms`、状态。

### 3.2 `OpenAIInstrumentor`

| 被 patch 目标 | 生成 Span |
|---|---|
| `chat.completions.Completions.create` | `chat openai <model>` |
| `chat.completions.AsyncCompletions.create` | `chat openai <model>` |

Chat Span 属性：`gen_ai.request.model`、`gen_ai.request.temperature`、`gen_ai.request.max_tokens`、`gen_ai.request.stream`、`gen_ai.usage.*`、`gen_ai.response.finish_reasons`、`gen_ai.response.id`，以及 opt-in 的 `gen_ai.input.messages / output.messages`。

### 3.3 `LlamaIndexInstrumentor`

| 被 patch 目标 | 生成 Span |
|---|---|
| `LLM.chat / complete` | `chat llamaindex <model>` |
| `LLM.achat / acomplete` | `chat llamaindex <model>` |
| `BaseRetriever._retrieve / _aretrieve` | `retrieval llamaindex` |
| `BaseTool.call / AsyncBaseTool.acall` | `execute_tool <tool>` |

检索 Span 属性：`app.retrieval.doc_count`；token 缺失时由 token 估算插件兜底。

### 3.4 自定义 Instrumentor

继承 `BaseAgentInstrumentor`，设置 `instrumentation_dependencies`，实现 `_instrument` / `_uninstrument`：

```python
class MyInstrumentor(BaseAgentInstrumentor):
    instrumentation_dependencies = ("mylib",)
    def _instrument(self, **kw):
        wrapt.wrap_function_wrapper("mylib", "run", self._wrapped)
    def _uninstrument(self, **kw):
        import mylib
        wrapt.unwrap(mylib, "run")
```

---

## 4. 手动埋点装饰器

装饰器自动适配同步/异步函数，返回值与原函数一致。

### `@agent_span(agent_name="agent", **extra)`
根 Span `invoke_agent <name>`，属性 `app.agent_name`。

### `@llm_span(model, provider="openai", **extra)`
Span `chat <provider> <model>`，属性 `gen_ai.provider.name`、`gen_ai.request.model`。

### `@tool_span(tool_name, tool_type="function", **extra)`
Span `execute_tool <tool_name>`，属性 `gen_ai.tool.name`、`gen_ai.tool.type`；开 `capture_tool_content` 时记录结果。

### `@retrieval_span(data_source_id="knowledge_base", **extra)`
Span `retrieval <ds>`，属性 `gen_ai.data_source.id`。

### `@span(name, **extra)`
通用 Span，用于规划/反思/重排等任意步骤。

---

## 4.5 网关中间件：`AgentOTelMiddleware`

纯 ASGI 中间件，FastAPI / Starlette 通用。

```python
app.add_middleware(AgentOTelMiddleware, capture_request_body=False, body_max_length=2000)
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| capture_request_body | bool | False | 是否记录请求体（读取后重放，不影响下游） |
| body_max_length | int | 2000 | 请求体最大记录长度 |

生成 Span `http <method> <path>`，属性：`http.request.method`、`http.response.status_code`、`url.path`、`app.duration_ms`；同时上报 `agentotel_http_calls_total` 与 `agentotel_http_duration_ms_bucket`。

---

## 5. 会话上下文

| 接口 | 说明 |
|---|---|
| `AgentContext.new(session_id, user_id, agent_name)` | 构造上下文，缺省自动生成 session_id |
| `use_context(ctx)` | 上下文管理器，退出自动恢复 |
| `get_context()` | 取当前上下文（可能为 None） |
| `set_context / reset_context` | 底层手动控制 |

```python
from agentotel import AgentContext, use_context
with use_context(AgentContext.new(user_id="u1")):
    graph.invoke(...)
```

---

## 6. 插件接口

### 基类 `AgentotelPlugin`

```python
class MyPlugin(AgentotelPlugin):
    name = "my-plugin"
    def process(self, span, attributes: dict) -> dict:
        attributes["app.custom"] = "v"
        return attributes
```

注册：`get_agentotel().add_plugin(MyPlugin())`。

约束：
- `process` 必须返回属性字典
- 插件异常会被管道捕获并记录为 `agentotel.plugin_error` 事件，不影响其他插件与主流程
- 管道按注册顺序执行

---

## 7. 语义映射

| 函数 | 说明 |
|---|---|
| `get_mapping(framework)` | 取框架映射表 |
| `apply_mapping(framework, source) -> dict` | 把框架响应翻译成标准属性 |

支持的路径语法：`a.b.c`、`choices[].finish_reason`（取首个）。

---

## 8. 标准属性速查

完整常量见 `src/agentotel/semconv/attributes.py`，分组：

- 操作：`gen_ai.operation.name`（chat / execute_tool / retrieval / invoke_agent ...）
- 服务商：`gen_ai.provider.name`
- 请求：`gen_ai.request.model / temperature / max_tokens / top_p / stream ...`
- 响应：`gen_ai.response.id / model / finish_reasons`
- 用量：`gen_ai.usage.input_tokens / output_tokens / total_tokens`
- 工具：`gen_ai.tool.name / call.id / call.arguments / call.result / type`
- 消息：`gen_ai.input.messages / output.messages`（opt-in）
- 数据源：`gen_ai.data_source.id`
- 业务：统一 `app.*` 前缀
