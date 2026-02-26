"""액션 실행 모듈

LLM이 결정한 액션을 Playwright 명령으로 변환하여 실행한다.
Phase 1-A에서는 기본 액션 6개 + 제어 액션 4개를 지원.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from playwright.async_api import Page

from src.core.state import PageState, IndexedElement

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """액션 실행 결과"""
    success: bool
    action: str
    message: str
    data: Any = None
    error: str | None = None


@dataclass
class AgentAction:
    """LLM이 결정한 액션"""
    action: str
    index: int | None = None
    text: str | None = None
    url: str | None = None
    combo: str | None = None
    option: str | None = None
    direction: str | None = None
    amount: int | None = None
    result: Any = None
    question: str | None = None
    reason: str = ""
    extra: dict = field(default_factory=dict)


def parse_action(llm_response: str) -> AgentAction:
    """LLM 응답에서 JSON 액션을 파싱

    LLM은 다음 형식으로 응답:
    { "action": "click", "index": 5, "reason": "로그인 버튼 클릭" }
    """
    text = llm_response.strip()

    # JSON 블록 추출 (```json ... ``` 또는 { ... })
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    # { } 블록만 추출
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start:brace_end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}\n원문: {text}")
        return AgentAction(action="error", reason=f"JSON 파싱 실패: {e}")

    # LLM이 "action": "scroll(down, 800)" 처럼 함수 호출 형태로 응답하는 경우 분해
    raw_action = data.get("action", "error")
    if "(" in raw_action and raw_action.endswith(")"):
        func_name = raw_action[:raw_action.index("(")].strip()
        args_str = raw_action[raw_action.index("(") + 1:-1]
        args = [a.strip().strip('"').strip("'") for a in args_str.split(",")]

        if func_name == "scroll" and len(args) >= 2:
            data["action"] = "scroll"
            data.setdefault("direction", args[0])
            try:
                data.setdefault("amount", int(args[1]))
            except ValueError:
                pass
        elif func_name == "keys" and args:
            data["action"] = "keys"
            data.setdefault("combo", args[0])
        elif func_name == "navigate" and args:
            data["action"] = "navigate"
            data.setdefault("url", args[0])
        elif func_name == "wait" and args:
            data["action"] = "wait"
            try:
                data.setdefault("amount", int(args[0]))
            except ValueError:
                pass
        elif func_name == "input" and len(args) >= 2:
            data["action"] = "input"
            try:
                data.setdefault("index", int(args[0]))
            except ValueError:
                pass
            data.setdefault("text", args[1])
        elif func_name == "click" and args:
            data["action"] = "click"
            try:
                data.setdefault("index", int(args[0]))
            except ValueError:
                pass
        elif func_name == "done" and args:
            data["action"] = "done"
            data.setdefault("result", args[0])
        else:
            data["action"] = func_name

    return AgentAction(
        action=data.get("action", "error"),
        index=data.get("index"),
        text=data.get("text"),
        url=data.get("url"),
        combo=data.get("combo"),
        option=data.get("option"),
        direction=data.get("direction", "down"),
        amount=data.get("amount", 500),
        result=data.get("result"),
        question=data.get("question"),
        reason=data.get("reason", ""),
        extra={k: v for k, v in data.items()
               if k not in ("action", "index", "text", "url", "combo",
                            "option", "direction", "amount", "result",
                            "question", "reason")},
    )


async def _get_element_locator(page: Page, state: PageState, index: int):
    """인덱스로 요소를 찾아 Playwright Locator 반환

    state.py가 주입한 data-aidx 속성을 사용하여 요소를 찾는다.
    data-aidx가 없는 경우 get_by_role() 폴백.
    """
    element = state.find_by_index(index)
    if element is None:
        raise ValueError(f"인덱스 {index}에 해당하는 요소 없음")

    # 1차: data-aidx CSS 셀렉터 (가장 안정적)
    if element.selector:
        locator = page.locator(element.selector)
        count = await locator.count()
        if count > 0:
            return locator.first, element

    # 2차 폴백: get_by_role (data-aidx가 제거된 경우 등)
    try:
        locator = page.get_by_role(element.role, name=element.name, exact=True)
        count = await locator.count()
        if count == 0:
            locator = page.get_by_role(element.role, name=element.name)
            count = await locator.count()
        if count > 0:
            return locator.first if count == 1 else locator.nth(element.nth), element
    except Exception:
        pass

    raise ValueError(
        f"[{index}] {element.role} <{element.tag}> \"{element.name}\" 요소를 페이지에서 찾을 수 없음"
    )

async def execute_action(
    page: Page,
    action: AgentAction,
    state: PageState,
) -> ActionResult:
    """에이전트 액션을 Playwright 명령으로 변환하여 실행"""
    try:
        match action.action:
            # === 기본 액션 (6개) ===
            case "click":
                handle, elem = await _get_element_locator(page, state, action.index)
                try:
                    await handle.click(timeout=5000)
                except Exception:
                    # 오버레이 등으로 클릭이 차단되면 force 클릭
                    logger.warning(f"[{action.index}] 일반 클릭 실패 → force 클릭 재시도")
                    await handle.click(force=True, timeout=5000)
                return ActionResult(
                    success=True,
                    action="click",
                    message=f"[{action.index}] {elem.role} \"{elem.name}\" 클릭 완료",
                )

            case "input":
                handle, elem = await _get_element_locator(page, state, action.index)
                try:
                    await handle.click(timeout=5000)
                except Exception:
                    logger.warning(f"[{action.index}] 일반 클릭 실패 → force 클릭 재시도")
                    await handle.click(force=True, timeout=5000)
                await handle.fill(action.text or "")
                return ActionResult(
                    success=True,
                    action="input",
                    message=f"[{action.index}] \"{action.text}\" 입력 완료",
                )

            case "keys":
                await page.keyboard.press(action.combo or "")
                return ActionResult(
                    success=True,
                    action="keys",
                    message=f"키보드 입력: {action.combo}",
                )

            case "select":
                handle, elem = await _get_element_locator(page, state, action.index)
                await handle.select_option(action.option or "")
                return ActionResult(
                    success=True,
                    action="select",
                    message=f"[{action.index}] 옵션 \"{action.option}\" 선택 완료",
                )

            case "scroll":
                direction = action.direction or "down"
                amount = action.amount or 500
                dy = amount if direction == "down" else -amount
                await page.mouse.wheel(0, dy)
                return ActionResult(
                    success=True,
                    action="scroll",
                    message=f"스크롤 {direction} {amount}px",
                )

            case "navigate":
                await page.goto(action.url or "", wait_until="domcontentloaded")
                return ActionResult(
                    success=True,
                    action="navigate",
                    message=f"URL 이동: {action.url}",
                )

            # === 제어 액션 (4개) ===
            case "screenshot":
                import base64
                raw = await page.screenshot(type="jpeg", quality=60)
                b64 = base64.b64encode(raw).decode("utf-8")
                return ActionResult(
                    success=True,
                    action="screenshot",
                    message="스크린샷 캡처 완료",
                    data=b64,
                )

            case "wait":
                import asyncio
                if action.text:
                    # 셀렉터 대기
                    await page.wait_for_selector(action.text, timeout=10000)
                    return ActionResult(
                        success=True,
                        action="wait",
                        message=f"셀렉터 대기 완료: {action.text}",
                    )
                else:
                    seconds = action.amount or 2
                    await asyncio.sleep(seconds)
                    return ActionResult(
                        success=True,
                        action="wait",
                        message=f"{seconds}초 대기 완료",
                    )

            case "done":
                return ActionResult(
                    success=True,
                    action="done",
                    message="태스크 완료",
                    data=action.result,
                )

            case "ask_human":
                return ActionResult(
                    success=True,
                    action="ask_human",
                    message=f"사용자 개입 요청: {action.question}",
                    data=action.question,
                )

            case "error":
                return ActionResult(
                    success=False,
                    action="error",
                    message=action.reason,
                    error=action.reason,
                )

            case _:
                return ActionResult(
                    success=False,
                    action=action.action,
                    message=f"알 수 없는 액션: {action.action}",
                    error=f"Unsupported action: {action.action}",
                )

    except Exception as e:
        logger.error(f"액션 실행 실패 [{action.action}]: {e}")
        return ActionResult(
            success=False,
            action=action.action,
            message=f"액션 실행 실패: {e}",
            error=str(e),
        )
