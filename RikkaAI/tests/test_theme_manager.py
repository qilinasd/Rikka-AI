import os
import sys
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication

from gui import theme_manager


class SeasonalCalendarTests(unittest.TestCase):
    def test_season_boundaries(self):
        cases = {
            date(2024, 2, 29): "winter",
            date(2026, 3, 1): "spring",
            date(2026, 5, 31): "spring",
            date(2026, 6, 1): "summer",
            date(2026, 8, 31): "summer",
            date(2026, 9, 1): "autumn",
            date(2026, 11, 30): "autumn",
            date(2026, 12, 1): "winter",
        }
        for day, expected in cases.items():
            with self.subTest(day=day):
                self.assertEqual(theme_manager.season_for_date(day), expected)

    def test_next_transition_including_cross_year(self):
        cases = {
            date(2026, 1, 15): date(2026, 3, 1),
            date(2026, 3, 1): date(2026, 6, 1),
            date(2026, 8, 31): date(2026, 9, 1),
            date(2026, 11, 30): date(2026, 12, 1),
            date(2026, 12, 15): date(2027, 3, 1),
        }
        for day, expected in cases.items():
            with self.subTest(day=day):
                self.assertEqual(theme_manager.next_season_transition(day), expected)

    def test_untouched_config_defaults_to_seasonal_auto(self):
        self.assertEqual(theme_manager.configured_appearance_mode({}), "seasonal_auto")
        resolved = theme_manager.resolve_appearance({}, date(2026, 7, 10))
        self.assertEqual(resolved.key, "seasonal_auto:summer")
        self.assertEqual(resolved.display_name, "夏季主题")

    def test_saved_legacy_appearance_stays_manual(self):
        values = {
            "appearance_theme": "星夜静谧",
            "appearance_background": "城市夜景",  # ignored legacy option
        }
        self.assertEqual(theme_manager.configured_appearance_mode(values), "manual")
        resolved = theme_manager.resolve_appearance(values, date(2026, 7, 10))
        self.assertEqual(resolved.theme_id, "星夜静谧")
        self.assertEqual(resolved.fallback_background, "樱花湖畔")

    def test_manual_seasonal_theme_uses_its_palette_and_ignores_legacy_wallpaper(self):
        values = {
            "appearance_mode": "manual",
            "appearance_theme": "autumn",
            "appearance_background": "城市夜景",
        }
        resolved = theme_manager.resolve_appearance(values, date(2026, 4, 1))
        autumn = theme_manager.SEASONAL_THEMES["autumn"]
        self.assertEqual(resolved.theme_id, "autumn")
        self.assertEqual(resolved.display_name, "秋季主题")
        self.assertEqual(resolved.accent, autumn.accent)
        self.assertEqual(resolved.fallback_background, autumn.fallback_background)

    def test_each_season_can_be_selected_manually(self):
        for theme_id, seasonal in theme_manager.SEASONAL_THEMES.items():
            with self.subTest(theme_id=theme_id):
                resolved = theme_manager.resolve_appearance({
                    "appearance_mode": "manual",
                    "appearance_theme": theme_id,
                })
                self.assertEqual(resolved.theme_id, theme_id)
                self.assertEqual(resolved.accent, seasonal.accent)

    def test_explicit_auto_does_not_overwrite_manual_preferences(self):
        values = {
            "appearance_mode": "seasonal_auto",
            "appearance_theme": "深色优雅",
            "appearance_background": "自定义上传",
            "appearance_background_custom": r"C:\wallpapers\rikka.png",
        }
        automatic = theme_manager.resolve_appearance(values, date(2026, 10, 1))
        self.assertEqual(automatic.theme_id, "autumn")
        manual = theme_manager.resolve_appearance(
            {**values, "appearance_mode": "manual"}, date(2026, 10, 1)
        )
        self.assertEqual(manual.theme_id, "深色优雅")
        self.assertEqual(manual.fallback_background, "樱花湖畔")

    def test_wallpaper_only_legacy_config_defaults_to_seasonal_auto(self):
        values = {
            "appearance_background": "古风庭院",
            "appearance_background_custom": r"C:\wallpapers\rikka.png",
        }
        self.assertEqual(theme_manager.configured_appearance_mode(values), "seasonal_auto")

    def test_key_is_stable_inside_a_season(self):
        first = theme_manager.resolve_appearance({}, date(2026, 6, 1))
        later = theme_manager.resolve_appearance({}, date(2026, 8, 31))
        changed = theme_manager.resolve_appearance({}, date(2026, 9, 1))
        self.assertEqual(first.key, later.key)
        self.assertNotEqual(first.key, changed.key)

    def test_each_season_builds_a_complete_stylesheet_override(self):
        for theme_id in theme_manager.SEASONAL_THEMES:
            with self.subTest(theme_id=theme_id):
                appearance = theme_manager.resolve_appearance({
                    "appearance_mode": "manual",
                    "appearance_theme": theme_id,
                })
                stylesheet = theme_manager.theme_override(appearance)
                self.assertIn(appearance.accent, stylesheet)
                self.assertIn("Seasonal glass system", stylesheet)
                self.assertIn("#SettingsMainPanel", stylesheet)


class SeasonalBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_each_season_has_a_nonblank_background(self):
        for month in (3, 6, 9, 12):
            with self.subTest(month=month):
                appearance = theme_manager.resolve_appearance({}, date(2026, month, 1))
                pixmap = theme_manager.load_theme_background(
                    appearance, QSize(320, 180)
                )
                self.assertFalse(pixmap.isNull())
                image = pixmap.toImage()
                samples = {
                    image.pixelColor(
                        min(image.width() - 1, x), min(image.height() - 1, y)
                    ).name()
                    for x, y in ((0, 0), (80, 45), (160, 90), (319, 179))
                }
                self.assertGreater(len(samples), 1)

    def test_missing_seasonal_file_uses_procedural_fallback(self):
        appearance = theme_manager.resolve_appearance({}, date(2026, 4, 1))
        missing = replace(
            appearance,
            background_path=str(PROJECT_ROOT / "missing-theme-background.png"),
        )
        pixmap = theme_manager.load_theme_background(missing, QSize(160, 90))
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.size(), QSize(160, 90))

    def test_all_season_page_assets_exist_and_load(self):
        for theme_id in theme_manager.SEASONAL_THEMES:
            appearance = theme_manager.resolve_appearance({
                "appearance_mode": "manual",
                "appearance_theme": theme_id,
            })
            loaded_keys = set()
            for page_id in theme_manager.THEME_PAGE_IDS:
                with self.subTest(theme_id=theme_id, page_id=page_id):
                    path = Path(theme_manager.seasonal_background_path(theme_id, page_id))
                    self.assertTrue(path.is_file(), path)
                    pixmap = theme_manager.load_theme_background(
                        appearance, page_id=page_id
                    )
                    self.assertFalse(pixmap.isNull())
                    self.assertEqual(pixmap.size(), QSize(2048, 1152))
                    loaded_keys.add(pixmap.cacheKey())
            self.assertEqual(len(loaded_keys), len(theme_manager.THEME_PAGE_IDS))

    def test_page_alias_and_unknown_page_validation(self):
        self.assertEqual(theme_manager.normalize_page_id("surf"), "surfing")
        self.assertEqual(theme_manager.normalize_page_id("surf_history"), "surfing")
        with self.assertRaises(ValueError):
            theme_manager.normalize_page_id("not-a-page")
        with self.assertRaises(ValueError):
            theme_manager.normalize_page_id("knowledge")


if __name__ == "__main__":
    unittest.main()
