Agentic Crawler v2: LLM-Driven Agent Loop with LangGraph + deepagents
Context
현재 에이전틱 크롤러(src/)는 코드가 루프를 제어하는 구조입니다:


while not done:
    state = get_indexed_state(page)   # 코드가 매번 자동 호출
    response = invoke_llm(state)      # 코드가 LLM 호출
    action = parse_action(response)   # 코드가 JSON 파싱
    result = execute_action(action)   # 코드가 액션 실행
이 구조에서 LLM은 "한 번에 하나의 액션을 JSON으로 반환"하는 역할만 합니다. 모든 제어 흐름(관찰 시점, 종료 판단, 에러 복구)이 코드에 하드코딩되어 있어, 복잡한 태스크(정보 수집, 로그인 등)를 유연하게 수행하지 못합니다.

목표: Stagehand처럼 LLM이 루프를 제어하는 구조로 전환합니다. LLM이 어떤 도구를 어떤 순서로 호출할지 스스로 결정합니다. create_deep_agent()(deepagents SDK) + LangGraph를 사용합니다.

디렉토리 구조
기존 src/는 유지하고, src/v2/에 새 구현을 만듭니다:


src/v2/
  __init__.py
  agent.py          # NEW: create_deep_agent 기반 에이전트 생성
  tools.py           # NEW: 브라우저 도구 10개 정의 (@tool)
  prompts.py         # NEW: 시스템 프롬프트
  server.py          # NEW: FastAPI + WebSocket (v2용)
  config.py          # NEW: v2 설정

src/core/            # 기존 — 재사용
  browser.py         # 그대로 사용 (BrowserManager)
  state.py           # 그대로 사용 (get_indexed_state, PageState)
파일별 구현 계획
1. src/v2/tools.py — 브라우저 도구 10개
기존 actions.py의 execute_action() match/case를 개별 @tool 함수로 분리합니다.
각 도구는 BrowserManager와 PageState를 클로저로 캡처합니다.


from langchain_core.tools import tool

def create_browser_tools(browser: BrowserManager) -> list:
    """BrowserManager 인스턴스를 바인딩한 도구 목록 생성"""

    # 공유 상태 (클로저)
    _state: PageState | None = None  # 마지막 observe 결과
    _memos: list[str] = []           # 수집된 정보 누적

    @tool
    async def observe_page() -> str:
        """현재 페이지의 상태를 관찰합니다.
        인터랙티브 요소 목록과 페이지 콘텐츠(Accessibility Tree)를 반환합니다.
        액션을 취하기 전에 반드시 이 도구를 호출하여 페이지 상태를 확인하세요."""
        nonlocal _state
        page = browser.page
        _state = await get_indexed_state(page)
        return _state.to_prompt_text()

    @tool
    async def browser_click(index: int, memo: str = "") -> str:
        """페이지의 인터랙티브 요소를 클릭합니다.
        Args:
            index: observe_page에서 확인한 요소 번호 [N]
            memo: (선택) 현재 페이지에서 수집한 핵심 정보. 실제 데이터만 기록."""
        # _state에서 요소 찾기 → locator → click
        # 기존 actions.py의 click case 로직 재사용
        if memo: _memos.append(memo)
        ...
        return f"[{index}] 클릭 완료"

    @tool
    async def browser_input(index: int, text: str, memo: str = "") -> str:
        """입력 필드에 텍스트를 입력합니다.
        Args:
            index: observe_page에서 확인한 입력 필드 번호 [N]
            text: 입력할 텍스트
            memo: (선택) 수집한 핵심 정보"""
        if memo: _memos.append(memo)
        ...

    @tool
    async def browser_navigate(url: str) -> str:
        """지정한 URL로 이동합니다."""

    @tool
    async def browser_scroll(direction: str = "down", amount: int = 500) -> str:
        """페이지를 스크롤합니다. direction: up/down/left/right"""

    @tool
    async def browser_keys(combo: str) -> str:
        """키보드 단축키를 입력합니다. 예: Enter, Escape, Tab"""

    @tool
    async def browser_select(index: int, option: str) -> str:
        """드롭다운에서 옵션을 선택합니다."""

    @tool
    async def browser_screenshot() -> str:
        """현재 페이지 스크린샷을 저장합니다."""

    @tool
    async def browser_wait(seconds: int = 2) -> str:
        """지정한 시간만큼 대기합니다."""

    @tool
    async def record_memo(info: str) -> str:
        """수집한 정보를 메모에 기록합니다.
        반드시 실제 데이터(이름, 수치, 사실)만 기록하세요.
        "~할 예정", "~하겠습니다" 같은 의도/계획은 기록하지 마세요.
        Args:
            info: 기록할 핵심 정보"""
        _memos.append(info)
        return f"메모 기록됨 (총 {len(_memos)}건)"

    @tool
    async def complete_task(result: str) -> str:
        """태스크를 완료하고 최종 결과를 반환합니다.
        Args:
            result: 수집한 정보를 종합한 완성된 답변.
                    지금까지의 메모를 모두 종합하여 구조화된 답변을 작성하세요.
                    "태스크 완료", "정보 수집 완료" 같은 빈 결과는 절대 금지."""
        # Stagehand ensureDone 패턴: result가 너무 짧으면 거부
        if len(result) < 50 and _memos:
            return (f"결과가 너무 짧습니다. 수집된 메모 {len(_memos)}건을 종합하여 "
                    f"상세한 답변을 작성해주세요. 메모 목록:\n" +
                    "\n".join(f"- {m}" for m in _memos))
        return f"__TASK_COMPLETE__\n{result}"

    return [observe_page, browser_click, browser_input, browser_navigate,
            browser_scroll, browser_keys, browser_select, browser_screenshot,
            browser_wait, record_memo, complete_task]
핵심 설계 결정:

memo는 click/input의 선택적 파라미터 + 별도 record_memo 도구 양쪽 지원
observe_page는 LLM이 명시적으로 호출 (코드가 자동 호출하지 않음)
complete_task에서 결과 길이 검증 (ensureDone 패턴)
__TASK_COMPLETE__ 마커로 agent_loop에서 종료 감지
2. src/v2/prompts.py — 시스템 프롬프트

BROWSER_AGENT_PROMPT = """당신은 웹 브라우저를 조작하여 사용자의 태스크를 수행하는 AI 에이전트입니다.

## 사용 가능한 도구
- observe_page: 현재 페이지 상태 확인 (요소 목록 + 콘텐츠)
- browser_click: 요소 클릭 (index 필요)
- browser_input: 텍스트 입력 (index + text 필요)
- browser_navigate: URL로 이동
- browser_scroll: 페이지 스크롤
- browser_keys: 키보드 입력
- browser_select: 드롭다운 선택
- browser_screenshot: 스크린샷 저장
- browser_wait: 대기
- record_memo: 수집한 정보 메모
- complete_task: 태스크 완료 + 결과 제출

## 핵심 규칙
1. 액션 전에 반드시 observe_page로 페이지 상태를 확인하세요.
2. observe_page 결과의 [N] 번호를 사용하여 요소를 조작하세요.
3. 페이지에서 유용한 정보를 발견하면 record_memo 또는 memo 파라미터로 기록하세요.
4. memo에는 실제 데이터만 기록하세요 (이름, 수치, 사실). 계획이나 의도는 금지.
5. 태스크 완료 시 complete_task에 수집된 모든 정보를 종합한 답변을 작성하세요.
6. 팝업이나 모달이 보이면 닫기/X/확인 버튼을 직접 클릭하여 처리하세요.
7. 이미 메모한 정보와 동일한 페이지를 재방문하지 마세요.

## 정보 수집 워크플로우
1. 검색 또는 목록 페이지에서 관련 링크를 찾아 방문
2. 페이지 내용을 읽고 핵심 정보를 record_memo로 기록
3. 뒤로 가거나 다음 링크로 이동하여 추가 정보 수집
4. 충분한 정보가 모이면 complete_task로 종합 답변 제출

## 페이지 콘텐츠
- "페이지 콘텐츠"는 Accessibility Tree 구조로 제공됩니다.
- heading, paragraph, link 등 역할을 참고하여 내용을 이해하세요.
"""
3. src/v2/agent.py — deepagents 기반 에이전트 생성

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from src.core.browser import BrowserManager
from src.v2.tools import create_browser_tools
from src.v2.prompts import BROWSER_AGENT_PROMPT

def create_browser_agent(
    browser: BrowserManager,
    model: str = "gpt-4o",
    max_steps: int = 50,
):
    """LLM이 루프를 제어하는 브라우저 에이전트 생성"""

    tools = create_browser_tools(browser)

    llm = ChatOpenAI(model=model, temperature=0)
    # SummarizationMiddleware를 위한 토큰 프로필
    llm.profile = {"max_input_tokens": 128000}

    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=BROWSER_AGENT_PROMPT,
        checkpointer=MemorySaver(),
        # filesystem backend 불필요 (브라우저 도구만 사용)
        # subagents 불필요 (단일 에이전트)
    )

    return agent


async def run_browser_agent(
    agent,
    goal: str,
    start_url: str | None = None,
    direction: str | None = None,
    thread_id: str = "default",
    on_tool_call=None,  # 콜백: WebSocket 스트리밍용
) -> dict:
    """브라우저 에이전트 실행"""

    # 초기 메시지 구성
    instruction = f"## 태스크\n{goal}"
    if start_url:
        instruction += f"\n\n## 시작 URL\n{start_url}"
    if direction:
        instruction += f"\n\n## 추가 지시\n{direction}"

    config = {"configurable": {"thread_id": thread_id}}

    # astream_events로 실시간 도구 호출 스트리밍
    result = None
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": instruction}]},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_tool_start" and on_tool_call:
            await on_tool_call({
                "type": "tool_start",
                "tool": event["name"],
                "input": event["data"].get("input", {}),
            })

        elif kind == "on_tool_end" and on_tool_call:
            output = event["data"].get("output", "")
            await on_tool_call({
                "type": "tool_end",
                "tool": event["name"],
                "output": str(output)[:500],
            })

            # complete_task 감지
            if isinstance(output, str) and "__TASK_COMPLETE__" in output:
                result = output.replace("__TASK_COMPLETE__\n", "")

    return {
        "success": result is not None,
        "message": result or "태스크 완료 실패 (max_steps 도달)",
    }
4. src/v2/server.py — WebSocket 서버
기존 server.py 구조를 유지하되, run_agent_task()를 run_browser_agent()로 교체합니다.


async def run_agent_task(goal, direction, start_url):
    async with BrowserManager(headless=HEADLESS) as browser:
        page = await browser.start()
        if start_url:
            await browser.navigate(start_url)

        agent = create_browser_agent(browser, model=DEFAULT_MODEL)

        async def on_tool_call(event):
            await broadcast({"type": "step", **event})

        result = await run_browser_agent(
            agent, goal, start_url, direction,
            on_tool_call=on_tool_call,
        )

        await broadcast({
            "type": "result",
            "success": result["success"],
            "message": result["message"],
        })
5. src/v2/config.py — 설정

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o")
MAX_STEPS = int(os.getenv("MAX_STEPS", "50"))  # recursion_limit으로 매핑
기존 코드 재사용 매핑
기존 파일	재사용 방식
src/core/browser.py	그대로 import — BrowserManager, check_obstruction, resolve_blocker, JS 블롭
src/core/state.py	그대로 import — get_indexed_state, PageState, _EXTRACT_JS, _get_aria_snapshot
src/core/actions.py	로직 추출 — _get_element_locator(), click/input/scroll 실행 로직을 tools.py로 이동
src/core/agent_loop.py	사용 안 함 — LangGraph가 대체
src/llm/client.py	사용 안 함 — deepagents가 대체
src/server.py	구조 복사 — WebSocket 패턴 동일, 내부 호출만 교체
Stagehand에서 채택한 패턴
패턴	구현 위치	설명
LLM이 루프 제어	agent.py	create_deep_agent의 tool-calling 루프가 전체 제어
ensureDone	tools.py complete_task	result 길이 검증, 메모 미종합 시 거부
메시지 압축	deepagents SummarizationMiddleware	컨텍스트 윈도우 초과 시 자동 요약
observe를 도구로	tools.py observe_page	LLM이 필요할 때만 페이지 관찰 (Stagehand의 ariaTree 도구)
LLM이 모달 처리	시스템 프롬프트	코드 레벨 모달 감지/해소 제거, LLM이 직접 닫기
제거되는 v1 복잡도
기존 기능	v2에서	이유
5-Phase 클릭 전략	단순 click + self-heal	LLM이 실패 시 재시도 판단
Interaction Scope (모달 필터링)	제거	LLM이 직접 모달 처리
Obstruction Architecture	제거	LLM이 장애물 인식 + 대응
State Fingerprint / no_change_count	제거	LLM이 도구 결과로 변화 판단
stuck detection (recent_actions)	제거	LangGraph recursion_limit이 무한루프 방지
parse_action() JSON 파싱	제거	tool calling이 구조화된 파라미터 제공
step_history 수동 관리	제거	LangGraph 메시지 히스토리가 자동 관리
구현 순서 (5단계)
Step 1: 프로젝트 셋업
src/v2/ 디렉토리 생성
src/v2/__init__.py, src/v2/config.py 작성
requirements.txt에 langgraph>=0.2.0 추가
deepagents import 확인
Step 2: 도구 정의 (tools.py)
create_browser_tools() 함수 작성
기존 actions.py에서 click/input/scroll/navigate/keys/select/screenshot/wait 로직 추출
_get_element_locator() 재사용
observe_page, record_memo, complete_task 신규 작성
Step 3: 에이전트 생성 (agent.py + prompts.py)
시스템 프롬프트 작성
create_browser_agent() 작성 (create_deep_agent 래핑)
run_browser_agent() 작성 (astream_events 기반)
Step 4: 서버 통합 (server.py)
기존 server.py 구조 복사
run_agent_task() 내부를 v2 에이전트로 교체
WebSocket 메시지 포맷 유지 (UI 호환)
Step 5: 테스트
단순 네비게이션 테스트 (네이버 검색)
정보 수집 테스트 ("한남동 맛집 3곳")
로그인 테스트 (hogangnono.com)
검증 방법
cd /DATA3/users/mj/spatial/agentic_crawler && python -m src.v2.server 로 v2 서버 시작
브라우저에서 localhost:1235 접속 (v1과 다른 포트)
"한남동 맛집 3곳을 네이버 블로그에서 찾아줘" 입력
Agent Logic Stream에서 도구 호출 로그 확인:
observe_page → browser_navigate → observe_page → browser_click → record_memo → ... → complete_task
최종 결과에 실제 맛집 정보가 포함되는지 확인
리스크
리스크	영향	대응
deepagents의 FilesystemMiddleware가 불필요한 도구 추가	도구 목록 혼잡	backend=None 또는 최소 backend 설정
LLM이 observe_page 호출 안 함	요소 번호 없이 클릭 시도 → 에러	시스템 프롬프트 강조 + click/input에서 _state 없으면 자동 observe
토큰 비용 증가 (tool calling 오버헤드)	v1 대비 ~2배	저렴한 모델(gpt-4o-mini) 옵션 제공
LLM이 모달을 무시	이전 v1과 동일 문제 재발	관찰 후 경험적으로 코드 안전장치 추가 판단
