# -*- coding: utf-8 -*-
"""LlamaIndex Agent 接入 AgentOTel 的最小示例（V0.2 自动插桩）。

运行：
1. cd deploy && docker-compose up -d
2. pip install -e ".[llamaindex]"
3. python examples/llamaindex_demo.py
4. 打开 http://127.0.0.1:16686 查看链路
"""

from agentotel import init_agentotel, LlamaIndexInstrumentor

# 1) 初始化
init_agentotel(
    service_name="agentotel-llamaindex-demo",
    capture_message_content=True,
    token_estimate_enabled=True,
)

# 2) 对 LlamaIndex 自动插桩（LLM / Retriever / Tool 全覆盖）
LlamaIndexInstrumentor().instrument()

# 3) 正常使用 LlamaIndex（业务代码无埋点）
#    下面用内置的 Mock LLM 演示，无需外部 API Key；
#    真实场景替换成 OpenAI / 其他 LLM 即可。
from llama_index.core.llms import MockLLM
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.tools import FunctionTool

llm = MockLLM()  # 演示用：返回固定文本

# 一个简单工具
def add(a: int, b: int) -> int:
    """两数相加。"""
    return a + b

tool = FunctionTool.from_defaults(fn=add)

# 一个最小索引与检索
documents = [Document(text="OpenTelemetry 是 CNCF 可观测性标准。")]
index = VectorStoreIndex.from_documents(documents)
retriever = index.as_retriever()

if __name__ == "__main__":
    # 触发 LLM 调用（生成 chat span）
    print("LLM:", llm.complete("介绍 OpenTelemetry"))
    # 触发检索（生成 retrieval span）
    print("Retrieved:", [n.get_content() for n in retriever.retrieve("OpenTelemetry")])
    # 触发工具（生成 execute_tool span）
    print("Tool:", tool.call(1, 2))
