"""
RikkaAI - 升级特性开关（Phase 0-5 的统一入口）

所有新能力都挂在 config 的升级开关上，`features.is_enabled("xxx")` 取布尔值。
这样每个新特性可以单独打开/关闭、独立回滚，不影响现有对话/主动/记忆主链路。

开关来自 config.UPGRADE_FLAGS_DEFAULTS（默认值）叠加 user_config.json 里的覆盖值。
"""
import config as cfg


def get(name: str, default=None):
    """取单个升级开关的值。未配置/未知 key 时回退到默认。
    布尔型开关没给默认时默认 False（不开），保证新特性默认不影响现有行为。"""
    if default is not None:
        return cfg.get_upgrade_flag(name, default)
    return cfg.get_upgrade_flag(name, False) is True


def is_enabled(name: str) -> bool:
    """布尔开关：True = 开启。"""
    return bool(cfg.get_upgrade_flag(name, False))


def flag(name: str, default=None):
    """原生取值（可能是 int/str/bool/dict）。"""
    return cfg.get_upgrade_flag(name, default)


def all_flags() -> dict:
    """返回当前所有升级开关的取值快照（供设置页/调试/持久化）。"""
    return cfg.get_all_upgrade_flags()


def set_flags(updates: dict) -> bool:
    """更新并持久化一批开关。返回是否成功。"""
    return cfg.save_upgrade_flags(updates)
