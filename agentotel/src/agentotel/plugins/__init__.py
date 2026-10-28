"""插件子包。

插件用于在 Span 生命周期中做增强处理（脱敏、token 估算、自定义标签等），
按需启用，不影响埋点主流程。
"""

from .base import AgentotelPlugin, PluginPipeline
from .pii_filter import PIIFilterPlugin
from .token_estimator import TokenEstimatorPlugin

__all__ = [
    "AgentotelPlugin",
    "PluginPipeline",
    "PIIFilterPlugin",
    "TokenEstimatorPlugin",
]
