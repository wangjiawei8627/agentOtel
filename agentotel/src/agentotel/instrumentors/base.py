"""Instrumentor 抽象基类。

定义统一的 ``instrument() / uninstrument()`` 生命周期，并提供：
- 幂等保护（重复 instrument 不重复 patch）
- 依赖检查（目标框架未安装时给出清晰错误）
- 共享的 tracer / config / 插件管道访问

子类只需实现 ``_instrument()`` 与 ``_uninstrument()``。
"""

from __future__ import annotations

import abc
import importlib
from typing import Optional

from ..otel.setup import get_agentotel


class BaseAgentInstrumentor(abc.ABC):
    """所有自动插桩器的基类。"""

    # 目标依赖，形如 ("langgraph>=0.2",)；V0.1 仅做模块存在性检查
    instrumentation_dependencies: tuple = ()

    def __init__(self) -> None:
        self._instrumented = False
        self._sdk = get_agentotel()

    # ------------------------------------------------------------------
    @property
    def tracer(self):
        """快捷访问全局 tracer。"""
        return self._sdk.tracer

    @property
    def config(self):
        """快捷访问全局配置。"""
        return self._sdk.config

    @property
    def plugins(self):
        """快捷访问插件管道。"""
        return self._sdk.plugins

    # ------------------------------------------------------------------
    def _check_dependencies(self) -> None:
        """检查目标模块是否可导入；缺失时抛出明确错误。"""
        for dep in self.instrumentation_dependencies:
            module = dep.split(">=")[0].split("==")[0].strip()
            try:
                importlib.import_module(module)
            except ImportError as exc:
                raise ModuleNotFoundError(
                    f"{type(self).__name__} 需要安装依赖：{dep}。"
                    f"可执行 `pip install agentotel[{module}]`。"
                ) from exc

    # ------------------------------------------------------------------
    def instrument(self, **kwargs) -> "BaseAgentInstrumentor":
        """执行插桩（幂等）。"""
        if self._instrumented:
            return self
        self._check_dependencies()
        self._instrument(**kwargs)
        self._instrumented = True
        return self

    def uninstrument(self, **kwargs) -> "BaseAgentInstrumentor":
        """撤销插桩（幂等）。"""
        if not self._instrumented:
            return self
        self._uninstrument(**kwargs)
        self._instrumented = False
        return self

    # ------------------------------------------------------------------
    @abc.abstractmethod
    def _instrument(self, **kwargs) -> None:
        """子类实现：真正的 monkey patch 逻辑。"""

    @abc.abstractmethod
    def _uninstrument(self, **kwargs) -> None:
        """子类实现：撤销 patch。"""
