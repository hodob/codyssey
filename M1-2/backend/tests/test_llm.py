import json
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import config
from services import llm


def msg(content="", calls=None):
    return NS(content=content, tool_calls=calls)


def call(id, name, args):
    return NS(id=id, function=NS(name=name, arguments=json.dumps(args)))


def response(message, p=10, c=5):
    return NS(choices=[NS(message=message)], usage=NS(prompt_tokens=p, completion_tokens=c))


class FakeClient:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        return self.responses.pop(0)


SUMMARY = {"period": "1958-03 ~ 2026-09", "count": 818,
           "metrics": {"average": 361.5, "median": 356.5, "stdev": 33.4, "max": 432.0, "max_date": "2026-05-15",
                       "min": 313.2, "min_date": "1958-09-15", "recent_annual_growth_ppm": 2.62},
           "latest": {"date": "2026-09-15", "value": 425.61},
           "trend": {"direction": "상승", "change": 1.92, "change_pct": 0.45}}


class PromptTest(unittest.TestCase):
    def test_compact_prompt_has_all_key_facts(self):
        p = llm.build_system_prompt(SUMMARY)
        for needle in ("1958-03 ~ 2026-09", "818개월", "361.5", "432.0 (2026-05-15)", "425.61 (2026-09-15)", "상승", "2.62"):
            self.assertIn(needle, p)
        self.assertLess(len(p), 1100)                      # 컨텍스트 예산
        self.assertIn("오늘 날짜(KST)", p)
        self.assertIn("1~2일 늦게", p)
        self.assertIn("다시 호출하지 말고", p)       # 이전 답변의 값은 재사용
        self.assertTrue(p.index("get_recent_daily") < p.index("[사용자 데이터 요약"))  # 고정 지침이 앞

    def test_prompt_uses_given_today(self):
        from datetime import date
        self.assertIn("2026-11-20", llm.build_system_prompt(SUMMARY, today=date(2026, 11, 20)))

    def test_prompt_survives_empty_summary(self):
        p = llm.build_system_prompt({"period": None, "count": 0, "metrics": {}, "latest": None,
                                     "trend": {"direction": "판단불가"}})
        self.assertIn("없음", p)


class TrimHistoryTest(unittest.TestCase):
    def h(self, n, size=50):
        return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"{i}:" + "x" * size, "tools": ["t"]}
                for i in range(n)]

    def test_limits_count_and_strips_extra_keys(self):
        out = llm.trim_history(self.h(30))
        self.assertLessEqual(len(out), config.CHAT_HISTORY_LIMIT)
        self.assertTrue(all(set(m) == {"role", "content"} for m in out))

    def test_char_budget_keeps_newest(self):
        hist = self.h(10, size=1500)
        out = llm.trim_history(hist)
        self.assertLessEqual(sum(len(m["content"]) for m in out), config.HISTORY_MAX_CHARS + 50)
        self.assertTrue(out[-1]["content"].startswith("9:"))

    def test_old_long_message_is_truncated_but_latest_is_not(self):
        hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a" * 3000},
                {"role": "user", "content": "u" * 2000}]
        out = llm.trim_history(hist)
        self.assertLessEqual(len(out[-1]["content"]), 2000)
        self.assertEqual(len(out[-1]["content"]), 2000)
        self.assertTrue(any(m["content"].endswith("…") for m in out[:-1]))

    def test_starts_with_user_turn(self):
        hist = [{"role": "assistant", "content": "a"}, {"role": "user", "content": "u"}]
        self.assertEqual(llm.trim_history(hist)[0]["role"], "user")
        self.assertEqual(llm.trim_history([]), [])


@mock.patch.object(config, "OPENAI_API_KEY", "k")
class AskTest(unittest.TestCase):
    def test_tool_loop_executes_and_sums_usage(self):
        client = FakeClient([
            response(msg("", [call("c1", "get_recent_daily", {"days": 3})]), p=100, c=20),
            response(msg("최근 3일 평균은 428입니다."), p=150, c=30)])
        seen = []
        with mock.patch.object(llm, "OpenAI", return_value=client):
            out = llm.ask(SUMMARY, [], "최근 3일 어때?", run_tool=lambda n, a: seen.append((n, a)) or '{"avg":428}')
        self.assertEqual(seen, [("get_recent_daily", {"days": 3})])
        self.assertEqual(out["tools_used"], ["get_recent_daily(days=3)"])
        self.assertEqual(out["usage"], {"prompt_tokens": 250, "completion_tokens": 50})
        self.assertIn("428", out["reply"])
        second = client.requests[1]["messages"]
        self.assertEqual(second[-1], {"role": "tool", "tool_call_id": "c1", "content": '{"avg":428}'})
        self.assertEqual(second[-2]["tool_calls"][0]["function"]["name"], "get_recent_daily")
        self.assertIn("tools", client.requests[0])

    def test_no_tool_needed(self):
        client = FakeClient([response(msg("평균은 361.5입니다."))])
        with mock.patch.object(llm, "OpenAI", return_value=client):
            out = llm.ask(SUMMARY, [], "평균?", run_tool=lambda n, a: "{}")
        self.assertEqual(out["tools_used"], [])

    def test_round_cap_forces_final_answer_without_tools(self):
        loop = [response(msg("", [call(f"c{i}", "get_today_highlights", {})])) for i in range(config.MAX_TOOL_ROUNDS)]
        client = FakeClient(loop + [response(msg("정리하면 이렇습니다."))])
        with mock.patch.object(llm, "OpenAI", return_value=client):
            out = llm.ask(SUMMARY, [], "q", run_tool=lambda n, a: "{}")
        self.assertEqual(len(out["tools_used"]), config.MAX_TOOL_ROUNDS)
        self.assertNotIn("tools", client.requests[-1])   # 마지막 왕복은 도구 비활성
        self.assertEqual(out["reply"], "정리하면 이렇습니다.")

    def test_bad_tool_arguments_do_not_crash(self):
        bad = NS(id="c1", function=NS(name="get_recent_daily", arguments="{not json"))
        client = FakeClient([response(msg("", [bad])), response(msg("죄송합니다."))])
        got = []
        with mock.patch.object(llm, "OpenAI", return_value=client):
            llm.ask(SUMMARY, [], "q", run_tool=lambda n, a: got.append(a) or "{}")
        self.assertEqual(got, ["bad"])

    def test_openai_error_becomes_llm_error(self):
        from openai import OpenAIError
        client = FakeClient([])
        client._create = mock.Mock(side_effect=OpenAIError("boom"))
        client.chat = NS(completions=NS(create=client._create))
        with mock.patch.object(llm, "OpenAI", return_value=client):
            with self.assertRaises(llm.LLMError):
                llm.ask(SUMMARY, [], "q")

    def test_complete(self):
        client = FakeClient([response(msg(" 요약 "))])
        with mock.patch.object(llm, "OpenAI", return_value=client):
            out = llm.complete("s", "u", model="m", max_tokens=9)
        self.assertEqual(out["text"], "요약")
        self.assertEqual(client.requests[0]["model"], "m")
        self.assertEqual(client.requests[0]["max_completion_tokens"], 9)

    def test_missing_key(self):
        with mock.patch.object(config, "OPENAI_API_KEY", ""):
            with self.assertRaises(llm.LLMError):
                llm.ask(SUMMARY, [], "q")


if __name__ == "__main__":
    unittest.main()
