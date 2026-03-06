"""Agentic Browser v2 — deepagents 기반 에이전트 생성 및 실행

create_deep_agent()를 사용하여 LLM이 루프를 제어하는 브라우저 에이전트를 생성.
LLM이 observe_page, browser_click 등의 도구를 자유롭게 호출하며,
complete_task 호출 시 __TASK_COMPLETE__ 마커로 종료를 감지한다.
"""

import logging
from typing import Optional, Callable, Any

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from src.core.browser import BrowserManager
from src.v2.tools import create_browser_tools
from src.v2.prompts import BROWSER_AGENT_PROMPT
from src.v2.config import DEFAULT_MODEL, MAX_STEPS

logger = logging.getLogger(__name__)


def create_browser_agent(
    browser: BrowserManager,
    model: str | None = None,
):
    """LLM이 루프를 제어하는 브라우저 에이전트 생성

    Args:
        browser: BrowserManager 인스턴스 (이미 start() 호출됨)
        model: LLM 모델명 (기본값: config.DEFAULT_MODEL)

    Returns:
        (agent, shared) 튜플
        - agent: CompiledStateGraph (LangGraph 에이전트)
        - shared: BrowserToolState (도구 간 공유 상태, 완료 감지용)
    """
    model = model or DEFAULT_MODEL
    tool_bundle = create_browser_tools(browser)

    # openai 모델은 "openai:모델명" 포맷으로 전달
    model_str = model if ":" in model else f"openai:{model}"

    agent = create_deep_agent(
        model=model_str,
        tools=tool_bundle["tools"],
        system_prompt=BROWSER_AGENT_PROMPT,
        checkpointer=MemorySaver(),
    )

    return agent, tool_bundle["shared"]


async def run_browser_agent(
    agent,
    shared,
    goal: str,
    start_url: str | None = None,
    direction: str | None = None,
    thread_id: str = "default",
    on_tool_call: Optional[Callable] = None,
) -> dict:
    """브라우저 에이전트 실행

    Args:
        agent: create_browser_agent()가 반환한 에이전트
        shared: BrowserToolState (완료 감지용)
        goal: 수행할 태스크
        start_url: 시작 URL (선택)
        direction: 추가 지시 (선택)
        thread_id: 대화 스레드 ID
        on_tool_call: 도구 호출 콜백 (WebSocket 스트리밍용)

    Returns:
        {"success": bool, "message": str}
    """
    # 초기 메시지 구성
    parts = [f"## 태스크\n{goal}"]
    if start_url:
        parts.append(f"\n## 시작 URL\n{start_url}")
    if direction:
        parts.append(f"\n## 추가 지시\n{direction}")
    instruction = "\n".join(parts)

    config = {"configurable": {"thread_id": thread_id}}

    result = None
    try:
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
                output_str = str(output)

                await on_tool_call({
                    "type": "tool_end",
                    "tool": event["name"],
                    "output": output_str[:500],
                })

                # complete_task의 __TASK_COMPLETE__ 마커 감지
                if "__TASK_COMPLETE__" in output_str:
                    result = output_str.replace("__TASK_COMPLETE__\n", "")

    except Exception as e:
        logger.error(f"에이전트 실행 오류: {e}")
        return {
            "success": False,
            "message": f"에이전트 오류: {str(e)}",
        }

    # shared 상태에서도 결과 확인 (이벤트 누락 대비)
    if result is None and shared.task_complete:
        result = shared.task_result

    return {
        "success": result is not None,
        "message": result or "태스크 완료 실패 (max_steps 도달 또는 에이전트가 complete_task를 호출하지 않음)",
    }
