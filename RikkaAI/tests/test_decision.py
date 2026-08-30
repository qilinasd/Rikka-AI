import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain.agent import AgentCore, _initial_tool_choice, _select_tools
from brain.decision import _rule_based_route, should_use_agent
from brain.tools import handle_tool_call


class DecisionRoutingTests(unittest.TestCase):
    def test_explicit_voice_request_uses_agent_route(self):
        text = "六花，发语音和我说话"
        self.assertEqual(_rule_based_route(text), "agent")
        self.assertTrue(should_use_agent(text))
        # 语音功能已下线：工具定义中没有 speak，强制调用不再触发
        names = {item["function"]["name"] for item in _select_tools(text)}
        self.assertNotIn("speak", names)

    def test_send_to_named_contact_injects_qq_tools(self):
        text = "发给雨心"
        self.assertEqual(_rule_based_route(text), "agent")
        names = {item["function"]["name"] for item in _select_tools(text)}
        self.assertIn("send_qq_message", names)
        self.assertEqual(
            _initial_tool_choice(text, _select_tools(text)),
            {"type": "function", "function": {"name": "query_qq_contacts"}},
        )

    def test_qq_number_follow_up_keeps_qq_tools_available(self):
        text = "10003"
        self.assertEqual(_rule_based_route(text), "agent")
        names = {item["function"]["name"] for item in _select_tools(text)}
        self.assertIn("send_qq_message", names)
        self.assertEqual(_initial_tool_choice(text, _select_tools(text)), "required")

    def test_tool_force_applies_only_to_initial_request(self):
        calls = []

        def chunk(content=None, tool_calls=None):
            delta = SimpleNamespace(content=content, tool_calls=tool_calls)
            return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

        tool_call = SimpleNamespace(
            index=0,
            id="call-1",
            function=SimpleNamespace(name="get_weather", arguments='{"location":"北京"}'),
        )

        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    return iter([chunk(tool_calls=[tool_call])])
                return iter([chunk(content="done")])

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        core = AgentCore()
        core._run_tool = lambda _name, _args: {"status": "success", "content": "ok"}
        output = []
        with patch.object(
            AgentCore, "_client", new_callable=PropertyMock, return_value=fake_client
        ):
            self.assertEqual(
                core._chat_impl("今天天气怎么样", output.append), "done"
            )

        self.assertEqual(calls[0]["tool_choice"]["function"]["name"], "get_weather")
        self.assertNotIn("tool_choice", calls[1])

    def test_tool_choice_falls_back_for_compatible_providers(self):
        calls = []

        def chunk(content):
            delta = SimpleNamespace(content=content, tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(kwargs)
                if "tool_choice" in kwargs:
                    raise RuntimeError("tool_choice is unsupported")
                return iter([chunk("fallback")])

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        core = AgentCore()
        with patch.object(
            AgentCore, "_client", new_callable=PropertyMock, return_value=fake_client
        ):
            self.assertEqual(
                core._chat_impl("今天天气怎么样", lambda _chunk: None),
                "fallback",
            )

        self.assertIn("tool_choice", calls[0])
        self.assertNotIn("tool_choice", calls[1])

    def test_streamed_tool_arguments_without_index_stay_on_active_call(self):
        calls = []
        executed = []

        def chunk(content=None, tool_calls=None):
            delta = SimpleNamespace(content=content, tool_calls=tool_calls)
            return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

        name_chunk = SimpleNamespace(
            index=None,
            id="call-1",
            function=SimpleNamespace(name="send_qq_message", arguments=None),
        )
        arguments_chunk = SimpleNamespace(
            index=None,
            id=None,
            function=SimpleNamespace(name=None, arguments='{"message":"hello"}'),
        )

        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    return iter([
                        chunk(tool_calls=[name_chunk]),
                        chunk(tool_calls=[arguments_chunk]),
                    ])
                return iter([chunk(content="done")])

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        core = AgentCore()
        core._run_tool = lambda name, args: (
            executed.append((name, args))
            or {"status": "success", "content": "ok"}
        )
        with patch.object(
            AgentCore, "_client", new_callable=PropertyMock, return_value=fake_client
        ):
            self.assertEqual(core._chat_impl("发消息", lambda _chunk: None), "done")

        self.assertEqual(executed, [("send_qq_message", {"message": "hello"})])

    def test_tool_text_failure_is_reported_as_failure(self):
        result = handle_tool_call("send_qq_message", {})
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["content"], "❌ 没有消息内容")


if __name__ == "__main__":
    unittest.main()
