# -*- coding: utf-8 -*-
"""LangGraph Agent 接入 AgentOTel 的最小示例（自动插桩）。

运行步骤：
1. 先在 deploy/ 目录启动： docker-compose up -d
2. 设置 OpenAI Key：        export OPENAI_API_KEY=sk-xxx
3. 运行本示例：             python examples/langgraph_demo.py
4. 打开 Jaeger UI：         http://127.0.0.1:16686
   选择服务 agentotel-langgraph-demo，即可看到完整 Agent 链路树。
"""

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode

# 从框架包导入初始化与插桩器
from agentotel import init_agentotel, LangGraphInstrumentor, OpenAIInstrumentor

# 1) 初始化 AgentOTel（全局单例）
#    capture_message_content=True 表示同时采集 prompt/回答原文（调试用）
init_agentotel(
    service_name="agentotel-langgraph-demo",
    capture_message_content=True,
    pii_mask_enabled=True,
    token_estimate_enabled=True,
)

# 2) 自动插桩：LangGraph 负责图与节点，OpenAI 负责 LLM 调用
LangGraphInstrumentor().instrument()
OpenAIInstrumentor().instrument()


# 3) 一个普通的 LangGraph Agent（业务代码无需任何埋点改动）
@tool
def search(query: str) -> str:
    """模拟联网搜索。"""
    import time
    time.sleep(0.2)
    return f"关于 {query} 的模拟搜索结果。"


@tool
def retrieve(query: str) -> str:
    """模拟知识库检索。"""
    import time
    time.sleep(0.2)
    return "知识片段：OpenTelemetry 是 CNCF 可观测性标准。"


tools = [search, retrieve]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).bind_tools(tools)


def call_llm(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


def route(state: MessagesState):
    return "tools" if state["messages"][-1].tool_calls else "__end__"


builder = StateGraph(MessagesState)
builder.add_node("llm", call_llm)
builder.add_node("tools", tool_node)
builder.add_edge(START, "llm")
builder.add_conditional_edges("llm", route)
builder.add_edge("tools", "llm")
graph = builder.compile()


if __name__ == "__main__":
    answer = graph.invoke({"messages": [("user", "介绍一下 OpenTelemetry，先检索再搜索。")]})
    print("===== 最终回答 =====")
    print(answer["messages"][-1].content)
