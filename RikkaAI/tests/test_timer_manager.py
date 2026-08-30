import unittest

from PyQt5.QtWidgets import QApplication

from main_window import TimerManager


class TimerManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_by_type_removes_matching_entries_only(self):
        manager = TimerManager()
        manager.schedule("proactive", 60)
        manager.schedule("follow_up", 60)
        manager.cancel_by_type("proactive")
        self.assertEqual([item["type"] for item in manager.list_pending()], ["follow_up"])
        manager.deleteLater()


if __name__ == "__main__":
    unittest.main()
