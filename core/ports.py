"""백엔드(Transport)가 지켜야 할 계약.

로봇에 명령을 실어 나르는 경로가 다섯 개다 — MockBackend · RelayBackend · RobotBackend · RcBackend ·
RcFleetBackend. 이름도 파일도 서로 달라도 State 는 이 모양만 안다.

**ABC 가 아니라 Protocol 인 이유**: ABC 는 상속을 강요한다. 다섯 백엔드가 각자 다른 파일에 상속 관계
없이 있는데 억지로 공통 조상을 만들면 없던 결합이 생긴다. Protocol 은 "모양만 맞으면 된다"라서 기존
코드를 안 건드린다. 이미 하고 있는 덕 타이핑을 이름 붙여 문서화하는 것이다.

**isinstance 가 확인하는 것은 이름의 존재뿐이다** — 메서드 시그니처는 확인하지 않는다.
`hasattr` 와 정확히 같은 강도다. 시그니처는 test_ports.py 가 따로 지킨다.

`stop()` 은 백엔드가 쥔 자원(시리얼·스레드·ROS 노드)을 놓는 것이고, `stop_motion()` 은 **로봇을 세우는 것**
이다. 이름이 비슷해서 헷갈리지만 완전히 다른 일이다. 계획서 초안은 전자를 `close()` 라고 불렀는데 실제
다섯 백엔드는 전부 `stop()` 이라서 실제를 따랐다 — 이름을 바꾸려면 백엔드 다섯과 호출부를 같이 고쳐야 하고,
그건 이 계약을 문서화하는 일과 다른 일이다.

이 파일은 로봇 컨테이너에도 배포된다(core/stage.py 가 import 하고 server.py 가 stage 를 import 한다).
run.sh 의 DEPLOY_FILES 에 core/ports.py 가 있어야 하고, test_server_tools 의
test_deploy_list_covers_core_imports_transitively 가 그걸 전이 의존까지 따라가며 지킨다.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class _MotionResultRequired(TypedDict):
    ok: bool
    msg: str


class MotionResult(_MotionResultRequired, total=False):
    """submit() · stop_motion() 이 돌려주는 dict. ok 와 msg 만 반드시 있다."""
    status: str            # queued · recorded · rejected · … (백엔드마다 다르다)
    motion: str
    request_id: str | None


@runtime_checkable
class Transport(Protocol):
    """모든 백엔드가 가진 것. State 가 직접 부르는 전부다."""
    name: str

    def submit(self, motion: str, source: str, reason: str) -> MotionResult: ...

    def stop_motion(self, source: str, reason: str = "") -> MotionResult: ...

    def status(self) -> dict: ...

    def stop(self) -> None: ...


# ── 선택 능력 ─────────────────────────────────────────────────────────
# 일부 백엔드만 가진 것. 예전에는 State 가 hasattr(backend, "prepare") 로 물었다.
# isinstance(backend, SupportsPrepare) 는 같은 질문에 의도가 이름으로 드러난다.

@runtime_checkable
class SupportsPrepare(Protocol):
    """무대 발사 지터를 줄이려고 1.5초 전에 다이얼·게이트를 미리 잡는다 (RC 계열)."""

    def prepare(self, motion: str) -> bool: ...


@runtime_checkable
class SupportsDuration(Protocol):
    """로봇이 완료를 알려 주지 않는 경로가 동작 길이를 추정해 준다 (RC 계열).

    None 은 "길이를 모른다"이고 호출부가 기본값으로 떨어진다.
    """

    def motion_duration(self, motion: str) -> float | None: ...


@runtime_checkable
class SupportsDiscovery(Protocol):
    """물리 장치를 다시 찾는다 (RC 플릿). rescan 은 찾은 장치 이름의 목록을 돌려준다."""

    def rescan(self) -> list[str]: ...

    def connect_check(self) -> tuple[bool, str]: ...
