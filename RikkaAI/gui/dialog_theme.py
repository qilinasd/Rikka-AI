"""Shared seasonal visual tokens for transient RikkaAI dialogs.

Dialogs are created outside the main page stack, so they cannot inherit the
page-specific QSS automatically.  This small adapter keeps their glass shell,
fields and actions aligned with the active four-season appearance.
"""

import gui.theme_manager as theme_manager


def colors():
    """Return dialog-safe colors for the currently active appearance."""
    appearance = theme_manager.current_appearance()
    tokens = theme_manager.appearance_tokens(appearance)
    return {
        "accent": appearance.accent,
        "accent_hover": appearance.accent_hover,
        "accent_soft": appearance.accent_soft,
        "text": tokens.get("text", appearance.text),
        "muted": tokens.get("muted", "#756a80"),
        "subtle": tokens.get("subtle", "#9a8fa2"),
        "surface": tokens.get("surface", appearance.card),
        "surface_strong": tokens.get("surface_strong", "rgba(255,255,255,0.94)"),
        "surface_soft": tokens.get("surface_soft", "rgba(255,255,255,0.68)"),
        "field": tokens.get("field", "rgba(255,255,255,0.90)"),
        "border": tokens.get("border", "rgba(255,255,255,0.76)"),
        "border_accent": tokens.get("border_accent", appearance.accent_soft),
        "nav": tokens.get("nav", "rgba(255,255,255,0.78)"),
        "nav_text": tokens.get("nav_text", appearance.text),
        "chart": tokens.get("chart", appearance.accent),
        "danger": "#d05268",
        "success": "#2f9d6b",
    }


def stylesheet():
    """Base stylesheet for dialogs and their common controls."""
    c = colors()
    return f"""
    QDialog {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 {c['surface_soft']}, stop:0.52 {c['surface']}, stop:1 {c['surface_soft']});
        color: {c['text']};
    }}
    QLabel {{ color: {c['text']}; }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
        background: {c['field']}; color: {c['text']};
        border: 1px solid {c['border_accent']}; border-radius: 12px;
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        background: {c['surface_strong']}; border-color: {c['accent']};
    }}
    QScrollArea, QListWidget, QScrollBar {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ width: 7px; margin: 4px 1px; }}
    QScrollBar::handle:vertical {{ background: {c['border_accent']}; border-radius: 3px; min-height: 32px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: transparent; }}
    QPushButton {{
        min-height: 32px; padding: 0 14px; border-radius: 11px;
        background: {c['surface_strong']}; border: 1px solid {c['border_accent']}; color: {c['nav_text']};
    }}
    QPushButton:hover {{ background: {c['accent_soft']}; border-color: {c['accent']}; color: {c['text']}; }}
    QPushButton:pressed {{ background: {c['accent']}; color: #ffffff; }}
    """


def apply(widget):
    """Apply the shared shell to a dialog without replacing scoped styles."""
    widget.setStyleSheet(stylesheet() + "\n" + (widget.styleSheet() or ""))
