"""server.State 는 core.Stage 에 이 앱의 것을 꽂는 배선이다 — 도메인이 서버에 다시 생기면 안 된다.

두 앱의 State 는 21개 메서드 중 20개가 글자 하나까지 같았고 다른 건 하나씩이었다. 그 20개가 core/stage.py 로
갔다. 서버의 State 가 그중 하나를 다시 정의하면 조용히 도메인을 덮어쓰고, 두 앱이 다시 갈라진다 —
8/31 에 display.html 이 그렇게 갈렸다.
"""

import inspect
import unittest

import server
from core.stage import Stage

# 이 앱에만 있는 메서드. RcBackend 를 만든다.
# 어댑터를 아는 일이라 core 에 둘 수 없다.
APP_ONLY = {"set_rc_mode"}


class WiringTest(unittest.TestCase):
    def test_state_is_a_stage(self):
        self.assertIs(server.State.__mro__[1], Stage)

    def test_state_defines_nothing_but_init_and_the_app_only_method(self):
        own = {n for n, v in vars(server.State).items()
               if not (n.startswith("__") and n.endswith("__")) and callable(v)}
        self.assertEqual(own, APP_ONLY, "서버의 State 가 Stage 의 메서드를 다시 정의했거나 새 메서드를 들였다")

    def test_no_stage_method_is_shadowed(self):
        """**메서드**만 본다. 클래스 상수(DANCE_LEAD_SEC 등)는 다르다 — test_rc_backend 가 그것을 덮어쓰고
        "복원"하는데 복원이 대입이라 State 에 자기 속성이 남는다. 그래서 이 테스트는 전체 실행에서만 실패했고
        단독으로 돌리면 통과했다(순서 의존). 상수를 바꿔 끼우는 것은 정상이고 메서드를 다시 정의하는 것만 문제다."""
        shadowed = {n for n, v in vars(server.State).items()
                    if callable(v) and n in vars(Stage) and not n.startswith("__")}
        self.assertEqual(shadowed, set())

    def test_init_takes_what_callers_pass(self):
        """main() 과 테스트가 이 이름들로 부른다. Stage 가 키워드 전용으로 바뀌어도 이 표면은 그대로여야 한다."""
        params = list(inspect.signature(server.State.__init__).parameters)
        self.assertEqual(params, ["self", "backend", "ready_only", "access_token", "llm_allowlist",
                                  "session_log", "pad_allowlist", "pad_llm_exclude", "api_allowlist"])


if __name__ == "__main__":
    unittest.main()
