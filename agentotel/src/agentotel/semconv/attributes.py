"""OpenTelemetry GenAI 语义约定标准属性常量。

对齐 2026-10 官方 registry（semantic-conventions-genai）。
所有 Instrumentor / SDK 都应引用这里的常量，而不是直接写字符串，
这样当规范升级时，只需改这一处。

字段分四组：
1. 操作与服务商
2. 请求参数（request.*）
3. 响应与用量（response.* / usage.*）
4. 工具 / 消息 / 数据源 / 记忆
"""

from __future__ import annotations

# =============================================================================
# 1. 操作类型（gen_ai.operation.name 的取值）
# =============================================================================
OPERATION_NAME = "gen_ai.operation.name"
OPERATION_CHAT = "chat"                    # 对话补全
OPERATION_TEXT_COMPLETION = "text_completion"
OPERATION_GENERATE_CONTENT = "generate_content"
OPERATION_EMBEDDINGS = "embeddings"
OPERATION_RETRIEVAL = "retrieval"          # 检索（RAG）
OPERATION_INVOKE_AGENT = "invoke_agent"    # 调用 Agent
OPERATION_EXECUTE_TOOL = "execute_tool"    # 执行工具
OPERATION_INVOKE_WORKFLOW = "invoke_workflow"
OPERATION_PLAN = "plan"                    # 规划 / 任务分解
OPERATION_SEARCH_MEMORY = "search_memory"
OPERATION_CREATE_MEMORY = "create_memory"
OPERATION_UPSERT_MEMORY = "upsert_memory"

# =============================================================================
# 2. 服务商
# =============================================================================
PROVIDER_NAME = "gen_ai.provider.name"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_AWS_BEDROCK = "aws.bedrock"
PROVIDER_AZURE_OPENAI = "azure.ai.openai"
PROVIDER_GEMINI = "gcp.gemini"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_MOONSHOT = "moonshot_ai"

# =============================================================================
# 3. 请求参数（gen_ai.request.*）
# =============================================================================
REQUEST_MODEL = "gen_ai.request.model"
REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
REQUEST_TEMPERATURE = "gen_ai.request.temperature"
REQUEST_TOP_P = "gen_ai.request.top_p"
REQUEST_TOP_K = "gen_ai.request.top_k"
REQUEST_SEED = "gen_ai.request.seed"
REQUEST_STREAM = "gen_ai.request.stream"
REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"
REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
REQUEST_CHOICE_COUNT = "gen_ai.request.choice.count"
REQUEST_REASONING_LEVEL = "gen_ai.request.reasoning.level"

# =============================================================================
# 4. 响应与用量（gen_ai.response.* / gen_ai.usage.*）
# =============================================================================
RESPONSE_ID = "gen_ai.response.id"
RESPONSE_MODEL = "gen_ai.response.model"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"

USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
USAGE_CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
USAGE_REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"

# =============================================================================
# 5. 工具（gen_ai.tool.*）
# =============================================================================
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"
TOOL_DESCRIPTION = "gen_ai.tool.description"
TOOL_TYPE = "gen_ai.tool.type"
TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
TOOL_CALL_RESULT = "gen_ai.tool.call.result"
TOOL_DEFINITIONS = "gen_ai.tool.definitions"

# 工具类型（gen_ai.tool.type 取值）
TOOL_TYPE_FUNCTION = "function"
TOOL_TYPE_EXTENSION = "extension"
TOOL_TYPE_DATASTORE = "datastore"

# =============================================================================
# 6. 消息（opt-in，敏感）
# =============================================================================
INPUT_MESSAGES = "gen_ai.input.messages"
OUTPUT_MESSAGES = "gen_ai.output.messages"
SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"

# =============================================================================
# 7. 数据源 / 记忆 / 工作流
# =============================================================================
DATA_SOURCE_ID = "gen_ai.data_source.id"
MEMORY_QUERY_TEXT = "gen_ai.memory.query.text"
MEMORY_RECORDS = "gen_ai.memory.records"
WORKFLOW_NAME = "gen_ai.workflow.name"

# =============================================================================
# 8. 业务自定义属性统一前缀（不要使用 gen_ai 前缀，避免污染标准语义）
# =============================================================================
APP_PREFIX = "app."
APP_USER_QUERY = "app.user_query"
APP_FINAL_ANSWER = "app.final_answer"
APP_SESSION_ID = "app.session_id"
APP_USER_ID = "app.user_id"
APP_AGENT_NAME = "app.agent_name"
APP_NODE_NAME = "app.node.name"
APP_DURATION_MS = "app.duration_ms"
APP_RETRIEVAL_DOC_COUNT = "app.retrieval.doc_count"
