"""에이전트 핵심 루프 모듈

Observation → LLM → Action 루프를 실행한다.
Phase 1-A에서는 단일 루프만 지원. Phase 1-B에서 에이전트 분리.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Callable, Awaitable, Any

from langchain_core.language_models import BaseChatModel

from src.core.browser import BrowserManager
from src.core.state import get_indexed_state, PageState
from src.core.actions import parse_action, execute_action, ActionResult, AgentAction
from src.llm.client import invoke_llm
from src.config import MAX_STEPS, MAX_FAILURES

logger = logging.getLogger(__name__)


@dataclass
class StepLog:
    """단일 스텝 로그"""
    step: int
    timestamp: str
    url: str
    action: str
    detail: str
    success: bool
    screenshot_b64: str | None = None


@dataclass
class AgentResult:
    """에이전트 실행 최종 결과"""
    success: bool
    message: str
    steps: list[StepLog] = field(default_factory=list)
    data: Any = None
    total_steps: int = 0
    failure_count: int = 0
    collected_info: list[str] = field(default_factory=list)  # 수집된 메모 이력


# 콜백 타입: UI로 스텝 로그를 실시간 전송할 때 사용
StepCallback = Callable[[StepLog], Awaitable[None]]

# 콜백 타입: ask_human 액션 시 사용자 응답을 받아오는 콜백
# 질문 문자열을 받아 사용자 응답 문자열을 반환
AskHumanCallback = Callable[[str], Awaitable[str]]


async def run_agent_loop(
    browser: BrowserManager,
    llm: BaseChatModel,
    goal: str,
    direction: str | None = None,
    start_url: str | None = None,
    max_steps: int = MAX_STEPS,
    max_failures: int = MAX_FAILURES,
    on_step: StepCallback | None = None,
    on_ask_human: AskHumanCallback | None = None,
) -> AgentResult:
    """에이전트 핵심 루프 실행

    Args:
        browser: 브라우저 매니저 (이미 start() 호출된 상태)
        llm: LLM 인스턴스
        goal: 수행할 태스크 (Goal)
        direction: 경로 힌트 (Direction, 선택)
        start_url: 시작 URL (선택)
        max_steps: 최대 스텝 수
        max_failures: 최대 연속 실패 허용 수
        on_step: 스텝 완료 시 호출되는 콜백 (UI 업데이트용)
        on_ask_human: ask_human 액션 시 사용자 응답을 받아오는 콜백 (없으면 루프 종료)

    Returns:
        AgentResult: 실행 결과
    """
    page = browser.page
    steps: list[StepLog] = []
    step_history: list[str] = []
    collected_info: list[str] = []  # 에이전트 작업 메모리 (memo 필드 누적)
    failure_count = 0

    # ── Stuck 감지용 변수 ──
    STUCK_THRESHOLD = 3       # 동일 패턴 반복 N회 → stuck 경고
    STUCK_ABORT_THRESHOLD = 6  # N회 이상 → 자동 종료
    recent_actions: list[str] = []  # 최근 액션 시그니처
    prev_url = ""
    prev_element_count = -1
    # 시작 URL이 있으면 이동
    if start_url:
        await browser.navigate(start_url)
        logger.info(f"시작 URL로 이동: {start_url}")

        # 팝업/오버레이 자동 제거
        dismissed = await browser.dismiss_overlays()
        if dismissed > 0:
            logger.info(f"시작 페이지에서 오버레이 {dismissed}개 자동 제거")

    for step_num in range(1, max_steps + 1):
        timestamp = datetime.now().strftime("%H:%M:%S")

        try:
            # 1. Observation: 페이지 상태 추출
            state = await get_indexed_state(page)
            element_count = len(state.elements)
            logger.info(
                f"Step {step_num}: {state.url} "
                f"({element_count}개 요소)"
            )

            # ── Stuck 감지 ──
            is_stuck = False
            if len(recent_actions) >= STUCK_THRESHOLD:
                last_n = recent_actions[-STUCK_THRESHOLD:]
                if len(set(last_n)) == 1 and state.url == prev_url:
                    is_stuck = True
                    logger.warning(
                        f"Stuck 감지: '{last_n[0]}' 액션이 {STUCK_THRESHOLD}회 반복"
                    )

            # Stuck이 ABORT 임계치를 넘으면 자동 종료
            if len(recent_actions) >= STUCK_ABORT_THRESHOLD:
                last_n = recent_actions[-STUCK_ABORT_THRESHOLD:]
                if len(set(last_n)) == 1 and state.url == prev_url:
                    logger.error(
                        f"Stuck abort: '{last_n[0]}' 액션이 "
                        f"{STUCK_ABORT_THRESHOLD}회 반복 → 자동 종료"
                    )
                    return AgentResult(
                        success=False,
                        message=(
                            f"Stuck 감지로 자동 종료: '{last_n[0]}' 액션이 "
                            f"{STUCK_ABORT_THRESHOLD}회 반복"
                        ),
                        steps=steps,
                        total_steps=step_num,
                        failure_count=failure_count,
                        collected_info=collected_info,
                    )

            prev_url = state.url
            prev_element_count = element_count

            # 2. LLM: 다음 액션 결정
            llm_response = await invoke_llm(
                llm=llm,
                state_text=state.to_prompt_text(),
                task=goal,
                direction_hint=direction,
                step_history=step_history,
                is_stuck=is_stuck,
                collected_info=collected_info,
            )

            # 3. 액션 파싱
            action = parse_action(llm_response)
            logger.info(f"Step {step_num} 액션: {action.action} (reason: {action.reason})")

            # 4. 액션 실행
            result = await execute_action(page, action, state)

            # 스텝 로그 기록
            step_log = StepLog(
                step=step_num,
                timestamp=timestamp,
                url=state.url,
                action=action.action,
                detail=result.message,
                success=result.success,
            )

            # 스크린샷 (매 스텝)
            try:
                step_log.screenshot_b64 = await browser.screenshot_base64()
            except Exception:
                pass

            steps.append(step_log)

            # 액션 시그니처 기록 (stuck 감지용)
            action_sig = action.action
            if action.index is not None:
                action_sig += f":{action.index}"
            recent_actions.append(action_sig)

            step_history.append(f"Step {step_num}: {action.action} → {result.message}")

            # memo 필드가 있으면 작업 메모리에 누적
            if action.memo:
                collected_info.append(action.memo)
                logger.info(f"Step {step_num} memo 저장: {action.memo[:80]}")

            # 콜백 호출 (UI 업데이트)
            if on_step:
                await on_step(step_log)

            # 5. 종료 조건 확인
            if action.action == "done":
                logger.info(f"태스크 완료 (Step {step_num}): {result.message}")
                return AgentResult(
                    success=True,
                    message=result.message,
                    steps=steps,
                    data=result.data,
                    total_steps=step_num,
                    failure_count=failure_count,
                    collected_info=collected_info,
                )

            if action.action == "ask_human":
                question = str(result.data)
                logger.info(f"사용자 개입 요청: {question}")

                if on_ask_human:
                    # 콜백으로 사용자 응답 대기 → 응답 받으면 루프 계속
                    human_response = await on_ask_human(question)
                    logger.info(f"사용자 응답 수신: {human_response}")
                    step_history.append(
                        f"Step {step_num}: ask_human → 사용자 응답: {human_response}"
                    )
                    collected_info.append(f"사용자 지시: {human_response}")
                    await asyncio.sleep(0.5)
                    continue
                else:
                    # 콜백 없으면 기존 동작: 루프 종료
                    return AgentResult(
                        success=True,
                        message=f"사용자 개입 필요: {question}",
                        steps=steps,
                        data=result.data,
                        total_steps=step_num,
                        failure_count=failure_count,
                        collected_info=collected_info,
                    )

            # 6. 실패 처리
            if not result.success:
                failure_count += 1
                logger.warning(
                    f"Step {step_num} 실패 ({failure_count}/{max_failures}): "
                    f"{result.error}"
                )
                if failure_count >= max_failures:
                    return AgentResult(
                        success=False,
                        message=f"최대 실패 횟수 초과 ({max_failures}회)",
                        steps=steps,
                        total_steps=step_num,
                        failure_count=failure_count,
                        collected_info=collected_info,
                    )
            else:
                failure_count = 0  # 성공 시 카운터 리셋
                # URL이 바뀌면 stuck 히스토리도 리셋
                if state.url != prev_url:
                    recent_actions.clear()
            # 페이지 로딩 대기
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Step {step_num} 예외: {e}")
            failure_count += 1
            step_log = StepLog(
                step=step_num,
                timestamp=timestamp,
                url=page.url,
                action="error",
                detail=str(e),
                success=False,
            )
            steps.append(step_log)
            if on_step:
                await on_step(step_log)

            if failure_count >= max_failures:
                return AgentResult(
                    success=False,
                    message=f"예외로 인한 종료: {e}",
                    steps=steps,
                    total_steps=step_num,
                    failure_count=failure_count,
                    collected_info=collected_info,
                )

    # 최대 스텝 도달
    return AgentResult(
        success=False,
        message=f"최대 스텝 수 도달 ({max_steps})",
        steps=steps,
        total_steps=max_steps,
        failure_count=failure_count,
        collected_info=collected_info,
    )
