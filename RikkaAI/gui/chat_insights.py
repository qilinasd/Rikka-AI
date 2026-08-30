"""Real conversation metrics and a lightweight seven-day trend chart."""

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brain import history


class StatCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("ChatStatTitle")
        layout.addWidget(title_label)

        self.value = QLabel("0")
        self.value.setObjectName("ChatStatValue")
        layout.addWidget(self.value)

        caption = QLabel("本地记录")
        caption.setObjectName("ChatStatCaption")
        layout.addWidget(caption)


class ConversationTrendChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = []
        self._values = []
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, labels, values):
        self._labels = list(labels)
        self._values = [int(value) for value in values]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        chart = QRectF(31, 16, max(1, self.width() - 43), max(1, self.height() - 43))
        line_color = QColor(121, 80, 223)
        grid_color = QColor(112, 86, 151, 35)
        text_color = QColor(103, 92, 119)

        painter.setPen(QPen(grid_color, 1))
        for index in range(4):
            y = chart.top() + chart.height() * index / 3
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

        max_value = max(self._values, default=0)
        painter.setPen(text_color)
        painter.drawText(QRectF(0, chart.top() - 7, 27, 16), Qt.AlignRight, str(max_value))
        painter.drawText(
            QRectF(0, chart.center().y() - 8, 27, 16),
            Qt.AlignRight,
            str(max_value // 2),
        )
        painter.drawText(QRectF(0, chart.bottom() - 8, 27, 16), Qt.AlignRight, "0")

        if not self._values:
            painter.drawText(chart, Qt.AlignCenter, "暂无趋势数据")
            return

        scale_max = max(1, max_value)
        step = chart.width() / max(1, len(self._values) - 1)
        points = [
            QPointF(
                chart.left() + step * index,
                chart.bottom() - chart.height() * value / scale_max,
            )
            for index, value in enumerate(self._values)
        ]

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)

        fill = QPainterPath(path)
        fill.lineTo(points[-1].x(), chart.bottom())
        fill.lineTo(points[0].x(), chart.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(0, chart.top(), 0, chart.bottom())
        gradient.setColorAt(0, QColor(138, 92, 232, 105))
        gradient.setColorAt(1, QColor(138, 92, 232, 8))
        painter.fillPath(fill, gradient)

        painter.setPen(QPen(line_color, 2))
        painter.drawPath(path)
        painter.setBrush(QColor(255, 255, 255))
        for point in points:
            painter.drawEllipse(point, 2.8, 2.8)

        painter.setPen(text_color)
        label_width = max(28, chart.width() / max(1, len(self._labels)))
        for index, label in enumerate(self._labels):
            if len(self._labels) > 4 and index not in {0, 2, 4, len(self._labels) - 1}:
                continue
            x = chart.left() + step * index - label_width / 2
            painter.drawText(
                QRectF(x, chart.bottom() + 7, label_width, 16),
                Qt.AlignCenter,
                label,
            )


class ChatInsightsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInsightsPanel")
        self.setFixedWidth(250)
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel("数据概览")
        title.setObjectName("ChatInsightsTitle")
        heading.addWidget(title)
        heading.addStretch()
        period = QLabel("近 7 天")
        period.setObjectName("ChatInsightsPeriod")
        heading.addWidget(period)
        layout.addLayout(heading)

        stats = QWidget()
        stats.setObjectName("ChatStatsGrid")
        grid = QGridLayout(stats)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(7)
        self.today_sessions = StatCard("今日对话")
        self.today_messages = StatCard("今日消息")
        self.total_sessions = StatCard("累计对话")
        self.total_messages = StatCard("累计消息")
        grid.addWidget(self.today_sessions, 0, 0)
        grid.addWidget(self.today_messages, 0, 1)
        grid.addWidget(self.total_sessions, 1, 0)
        grid.addWidget(self.total_messages, 1, 1)
        layout.addWidget(stats)

        trend_card = QFrame()
        trend_card.setObjectName("ChatTrendCard")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(10, 10, 10, 9)
        trend_layout.setSpacing(5)
        trend_heading = QHBoxLayout()
        trend_title = QLabel("对话趋势")
        trend_title.setObjectName("ChatTrendTitle")
        trend_heading.addWidget(trend_title)
        trend_heading.addStretch()
        unit = QLabel("消息数")
        unit.setObjectName("ChatTrendUnit")
        trend_heading.addWidget(unit)
        trend_layout.addLayout(trend_heading)
        self.chart = ConversationTrendChart()
        trend_layout.addWidget(self.chart)
        layout.addWidget(trend_card)

        summary = QFrame()
        summary.setObjectName("ChatInsightSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(11, 10, 11, 10)
        summary_layout.setSpacing(7)
        summary_title = QLabel("近 7 天活跃")
        summary_title.setObjectName("ChatTrendTitle")
        summary_layout.addWidget(summary_title)
        self.week_total = QLabel("消息 0 条")
        self.week_total.setObjectName("ChatInsightRow")
        summary_layout.addWidget(self.week_total)
        self.active_day = QLabel("最活跃日期  -")
        self.active_day.setObjectName("ChatInsightRow")
        summary_layout.addWidget(self.active_day)
        layout.addWidget(summary)
        layout.addStretch()

    def refresh_data(self):
        data = history.get_chat_analytics(7)
        self.today_sessions.value.setText(f"{data['today_sessions']:,}")
        self.today_messages.value.setText(f"{data['today_messages']:,}")
        self.total_sessions.value.setText(f"{data['total_sessions']:,}")
        self.total_messages.value.setText(f"{data['total_messages']:,}")
        self.chart.set_data(data["labels"], data["values"])

        week_total = sum(data["values"])
        self.week_total.setText(f"消息 {week_total:,} 条")
        if data["values"] and max(data["values"]) > 0:
            index = data["values"].index(max(data["values"]))
            self.active_day.setText(
                f"最活跃日期  {data['labels'][index]} · {data['values'][index]} 条"
            )
        else:
            self.active_day.setText("最活跃日期  暂无记录")


class ConversationOverviewPanel(ChatInsightsPanel):
    """Compact reusable overview for the home right rail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeOverviewPanel")
        self.setFixedWidth(268)
        self.chart.setMinimumHeight(132)
        self.chart.setMaximumHeight(132)
