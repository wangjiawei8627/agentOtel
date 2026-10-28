"""轻量 Web 管理后台子包。

- ``create_console_app(prometheus_url)``：构造 FastAPI 应用
- ``console_app``：默认实例，可直接用 uvicorn 启动
"""

from .app import create_console_app, console_app

__all__ = ["create_console_app", "console_app"]
