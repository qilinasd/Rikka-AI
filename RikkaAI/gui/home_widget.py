"""Home widget exports and WebEngine-to-native fallback factory."""

import os

from gui.home.page import HomeWidget


def create_home_widget(parent=None):
    """Prefer the local WebEngine home while keeping native PyQt as fallback."""
    if os.environ.get("RIKKAAI_NATIVE_HOME") == "1":
        return HomeWidget(parent)
    try:
        from gui.web_home_widget import WebHomeWidget

        return WebHomeWidget(parent)
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"[RikkaAI] Web home unavailable, using native home: {exc}")
        return HomeWidget(parent)


__all__ = ["HomeWidget", "create_home_widget"]
