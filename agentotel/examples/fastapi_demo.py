# -*- coding: utf-8 -*-
"""FastAPI Agent 服务接入 AgentOTel 网关中间件的最小示例（V0.2）。

运行：
1. cd deploy && docker-compose up -d
2. pip install -e ".[fastapi]"
3. uvicorn examples.fastapi_demo:app --port 8000
4. 发请求：
   curl -X POST http://127.0.0.1:8000/agent -H 'Content-Type: application/json' \
        -d '{"query":"你好"}'
5. 打开 http://127.0.0.1:16686 查看每个 HTTP 请求的链路
"""

from fastapi import FastAPI
from pydantic import BaseModel

from agentotel import init_agentotel
from agentotel.middleware import AgentOTelMiddleware

# 1) 初始化（网关侧无需采集消息内容也可，这里开启便于演示）
init_agentotel(
    service_name="agentotel-fastapi-demo",
    capture_message_content=True,
)

# 2) 定义应用
app = FastAPI(title="Agent FastAPI Demo")

# 3) 挂载网关中间件（无代码埋点）
#    capture_request_body=True 会记录请求体并重放，不影响下游
app.add_middleware(AgentOTelMiddleware, capture_request_body=True)


class AgentRequest(BaseModel):
    query: str


class AgentResponse(BaseModel):
    answer: str


@app.post("/agent", response_model=AgentResponse)
def agent_endpoint(req: AgentRequest):
    """一个普通的 Agent 端点（业务代码无任何埋点）。"""
    # 真实场景这里调用 graph.invoke / agent.run
    return AgentResponse(answer=f"收到你的问题：{req.query}")


@app.get("/health")
def health():
    return {"status": "ok"}
