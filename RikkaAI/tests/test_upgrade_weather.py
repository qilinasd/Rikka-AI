"""
测试：get_weather 现在返回"当前 + 未来几天预报"（不再依赖联网搜索）。
用 mock 替换 requests.get，验证对 wttr.in j1 JSON 的解析，不联网。
"""
import unittest


class _FakeResp:
    def __init__(self, data):
        self._data = data
    def json(self):
        return self._data


_SAMPLE = {
    "current_condition": [{
        "temp_C": "23", "FeelsLikeC": "23",
        "weatherDesc": [{"value": "多云"}],
        "humidity": "74", "windspeedKmph": "11",
    }],
    "nearest_area": [{"areaName": [{"value": "盐城"}], "country": [{"value": "中国"}]}],
    "weather": [
        {"date": "2026-05-01", "mintempC": "18", "maxtempC": "27", "weatherDesc": [{"value": "多云"}]},
        {"date": "2026-05-02", "mintempC": "19", "maxtempC": "29", "weatherDesc": [{"value": "晴"}]},
        {"date": "2026-05-03", "mintempC": "20", "maxtempC": "30", "weatherDesc": [{"value": "小雨"}]},
    ],
}


class WeatherTest(unittest.TestCase):
    def test_get_weather_includes_forecast(self):
        from brain import tools
        orig = tools._HTTP.get
        calls = {}
        def fake_get(url, **kw):
            calls["url"] = url
            return _FakeResp(_SAMPLE)
        try:
            tools._HTTP.get = fake_get
            out = tools._get_weather({"location": "盐城"})
        finally:
            tools._HTTP.get = orig
        self.assertIn("盐城", out)
        self.assertIn("未来几天", out)
        self.assertIn("05-01", out)     # 未来几天日期被解析
        self.assertIn("小雨", out)      # 未来几天的描述出现
        self.assertIn("23", out)        # 当前温度
        self.assertTrue(str(calls.get("url", "")).startswith("https://wttr.in/"))

    def test_weather_error_graceful(self):
        from brain import tools
        orig = tools._HTTP.get
        def fake_get(url, **kw):
            raise Exception("network down")
        try:
            tools._HTTP.get = fake_get
            out = tools._get_weather({"location": "x"})
        finally:
            tools._HTTP.get = orig
        self.assertTrue(str(out).startswith("天气查询失败"))


if __name__ == "__main__":
    unittest.main()
