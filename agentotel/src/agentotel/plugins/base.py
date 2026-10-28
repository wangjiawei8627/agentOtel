"""插件基类与插件执行管道。

插件是“链式增强器”，在 Span 即将结束、属性落盘前依次执行：
- 可新增属性（如自动补 token、补业务标签）
- 可改写/脱敏属性（如把手机号替换成 ***）
- 不应抛异常影响主业务，管道会统一兜底捕获。
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:  # 避免运行期循环导入，仅类型检查时引入 Span
    from opentelemetry.trace import Span


class AgentotelPlugin:
    """所有插件的抽象基类。子类通过设置 ``name`` 并实现 ``process`` 接入。"""

    name: str = "base"

    def process(self, span: "Span", attributes: Dict[str, Any]) -> Dict[str, Any]:
        """处理属性并返回更新后的属性字典。

        :param span: 当前 Span（可用于额外 record_event，一般只改属性）
        :param attributes: 已收集的属性副本
        :return: 处理后的属性字典
        """
        return attributes


class PluginPipeline:
    """有序插件链：按注册顺序依次执行，单个插件失败不影响其他插件。"""

    def __init__(self, plugins: List[AgentotelPlugin] | None = None) -> None:
        self._plugins: List[AgentotelPlugin] = list(plugins or [])

    def add(self, plugin: AgentotelPlugin) -> "PluginPipeline":
        """追加一个插件，返回自身，便于链式调用。"""
        self._plugins.append(plugin)
        return self

    @property
    def plugins(self) -> List[AgentotelPlugin]:
        """只读暴露已注册插件。"""
        return list(self._plugins)

    def run(self, span: "Span", attributes: Dict[str, Any]) -> Dict[str, Any]:
        """依次执行全部插件；任何插件抛错都被吞掉并降级为原属性。"""
        result = dict(attributes)
        for plugin in self._plugins:
            try:
                result = plugin.process(span, result) or result
            except Exception as exc:  # noqa: BLE001 - 插件是增强能力，不能拖垮埋点
                span.record_event(
                    "agentotel.plugin_error",
                    {"plugin": plugin.name, "error": repr(exc)},
                )
        return result
