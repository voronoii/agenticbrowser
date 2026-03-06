"""Agentic Browser v2 — 브라우저 도구 정의

기존 actions.py의 execute_action() match/case를 개별 @tool 함수로 분리.
BrowserManager와 PageState를 클로저로 캡처하여 LangGraph 도구로 제공.
"""

import asyncio
import base64
import logging
from typing import Optional

from langchain_core.tools import tool

from src.core.browser import BrowserManager
from src.core.state import PageState, IndexedElement, get_indexed_state

logger = logging.getLogger(__name__)


async def _get_element_locator(page, state: PageState, index: int):
    """인덱스로 요소를 찾아 Playwright Locator 반환

    state.py가 주입한 data-aidx 속성을 사용하여 요소를 찾는다.
    data-aidx가 없는 경우 get_by_role() 폴백.
    """
    element = state.find_by_index(index)
    if element is None:
        raise ValueError(f"인덱스 {index}에 해당하는 요소 없음. observe_page를 다시 호출하세요.")

    # 1차: data-aidx CSS 셀렉터
    if element.selector:
        locator = page.locator(element.selector)
        count = await locator.count()
        if count > 0:
            return locator.first, element

    # 2차 폴백: get_by_role
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
        f"[{index}] {element.role} <{element.tag}> \"{element.name}\" 요소를 페이지에서 찾을 수 없음. "
        f"observe_page를 다시 호출하여 최신 상태를 확인하세요."
    )


class BrowserToolState:
    """도구 간 공유 상태"""

    def __init__(self):
        self.page_state: Optional[PageState] = None
        self.memos: list[str] = []
        self.task_complete: bool = False
        self.task_result: Optional[str] = None


def create_browser_tools(browser: BrowserManager) -> list:
    """BrowserManager 인스턴스를 바인딩한 도구 목록 생성

    Returns:
        LangGraph에 바인딩할 도구 리스트
    """

    shared = BrowserToolState()

    @tool
    async def observe_page() -> str:
        """현재 페이지의 상태를 관찰합니다.
        인터랙티브 요소 목록과 페이지 콘텐츠(Accessibility Tree)를 반환합니다.
        브라우저 액션을 취하기 전에 반드시 이 도구를 호출하여 페이지 상태를 확인하세요.
        이 도구를 호출하지 않으면 browser_click, browser_input 등이 실패합니다."""
        page = browser.page
        if page is None:
            return "오류: 브라우저가 시작되지 않았습니다."

        try:
            shared.page_state = await get_indexed_state(page)
            result = shared.page_state.to_prompt_text()

            # 수집된 메모가 있으면 함께 표시
            if shared.memos:
                memo_text = "\n".join(f"  - {m}" for m in shared.memos)
                result += f"\n\n## 수집된 정보 ({len(shared.memos)}건)\n{memo_text}"

            return result
        except Exception as e:
            logger.error(f"observe_page 실패: {e}")
            return f"페이지 상태 관찰 실패: {e}"

    @tool
    async def browser_click(index: int, memo: str = "") -> str:
        """페이지의 인터랙티브 요소를 클릭합니다.

        Args:
            index: observe_page에서 확인한 요소 번호 [N]
            memo: (선택) 현재 페이지에서 수집한 핵심 정보. 실제 데이터(이름, 수치, 사실)만 기록하세요.
        """
        if memo:
            shared.memos.append(memo)

        page = browser.page
        if shared.page_state is None:
            return "오류: observe_page를 먼저 호출하세요."

        try:
            handle, elem = await _get_element_locator(page, shared.page_state, index)
        except ValueError as e:
            return str(e)

        # 일반 클릭 시도
        try:
            await handle.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        try:
            await handle.click(timeout=5000)
            return f'[{index}] {elem.role} "{elem.name}" 클릭 완료'
        except Exception as click_err:
            logger.warning(f"[{index}] 일반 클릭 실패: {click_err}")

        # dispatchEvent 폴백
        try:
            await handle.evaluate("""(el) => {
                ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach(t => {
                    el.dispatchEvent(new MouseEvent(t, {
                        bubbles: true, cancelable: true, view: window
                    }));
                });
            }""")
            return f'[{index}] {elem.role} "{elem.name}" 클릭 완료 (dispatchEvent)'
        except Exception:
            pass

        # force click 최후 수단
        try:
            await handle.click(force=True, timeout=5000)
            return f'[{index}] {elem.role} "{elem.name}" 클릭 완료 (force)'
        except Exception as e:
            return f'[{index}] "{elem.name}" 클릭 실패: {e}. observe_page로 상태를 재확인하세요.'

    @tool
    async def browser_input(index: int, text: str, memo: str = "") -> str:
        """입력 필드에 텍스트를 입력합니다.

        Args:
            index: observe_page에서 확인한 입력 필드 번호 [N]
            text: 입력할 텍스트
            memo: (선택) 현재 페이지에서 수집한 핵심 정보
        """
        if memo:
            shared.memos.append(memo)

        page = browser.page
        if shared.page_state is None:
            return "오류: observe_page를 먼저 호출하세요."

        try:
            handle, elem = await _get_element_locator(page, shared.page_state, index)
        except ValueError as e:
            return str(e)

        try:
            await handle.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        # 활성화 클릭
        try:
            await handle.click(timeout=5000)
        except Exception:
            try:
                await handle.click(force=True, timeout=5000)
            except Exception:
                pass

        # 텍스트 입력
        try:
            await handle.fill(text)
            return f'[{index}] "{text}" 입력 완료'
        except Exception as e:
            return f'[{index}] 텍스트 입력 실패: {e}'

    @tool
    async def browser_navigate(url: str) -> str:
        """지정한 URL로 이동합니다.

        Args:
            url: 이동할 URL (https://로 시작)
        """
        page = browser.page
        try:
            await page.goto(url, wait_until="domcontentloaded")
            return f"URL 이동 완료: {url}"
        except Exception as e:
            return f"URL 이동 실패: {e}"

    @tool
    async def browser_scroll(direction: str = "down", amount: int = 500) -> str:
        """페이지를 스크롤합니다.

        Args:
            direction: 스크롤 방향 (up, down, left, right)
            amount: 스크롤 양 (픽셀, 기본값 500)
        """
        page = browser.page
        try:
            if direction in ("down", "up"):
                dy = amount if direction == "down" else -amount
                await page.mouse.wheel(0, dy)
            elif direction in ("left", "right"):
                dx = amount if direction == "right" else -amount
                await page.mouse.wheel(dx, 0)
            return f"스크롤 {direction} {amount}px 완료"
        except Exception as e:
            return f"스크롤 실패: {e}"

    @tool
    async def browser_keys(combo: str) -> str:
        """키보드 단축키를 입력합니다.

        Args:
            combo: 키 조합 (예: Enter, Escape, Tab, Control+a, Backspace)
        """
        page = browser.page
        try:
            await page.keyboard.press(combo)
            return f"키보드 입력 완료: {combo}"
        except Exception as e:
            return f"키보드 입력 실패: {e}"

    @tool
    async def browser_select(index: int, option: str) -> str:
        """드롭다운에서 옵션을 선택합니다.

        Args:
            index: observe_page에서 확인한 드롭다운 요소 번호 [N]
            option: 선택할 옵션 값 또는 텍스트
        """
        page = browser.page
        if shared.page_state is None:
            return "오류: observe_page를 먼저 호출하세요."

        try:
            handle, elem = await _get_element_locator(page, shared.page_state, index)
            await handle.select_option(option)
            return f'[{index}] 옵션 "{option}" 선택 완료'
        except Exception as e:
            return f'[{index}] 옵션 선택 실패: {e}'

    @tool
    async def browser_screenshot() -> str:
        """현재 페이지의 스크린샷을 저장합니다.
        스크린샷이 필요한 경우 호출하세요."""
        page = browser.page
        try:
            raw = await page.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(raw).decode("utf-8")
            return f"스크린샷 캡처 완료 (base64 길이: {len(b64)})"
        except Exception as e:
            return f"스크린샷 실패: {e}"

    @tool
    async def browser_wait(seconds: int = 2) -> str:
        """지정한 시간만큼 대기합니다. 페이지 로딩이나 애니메이션을 기다릴 때 사용합니다.

        Args:
            seconds: 대기 시간 (초, 기본값 2, 최대 30)
        """
        seconds = min(seconds, 30)
        await asyncio.sleep(seconds)
        return f"{seconds}초 대기 완료"

    @tool
    async def record_memo(info: str) -> str:
        """수집한 정보를 메모에 기록합니다.
        다른 페이지로 이동하면 현재 페이지의 정보를 볼 수 없으므로,
        유용한 정보를 발견하면 즉시 이 도구로 기록하세요.

        반드시 실제 데이터(이름, 주소, 수치, 사실)만 기록하세요.
        "~할 예정", "~하겠습니다" 같은 의도나 계획은 기록하지 마세요.

        Args:
            info: 기록할 핵심 정보 (구체적인 데이터)
        """
        shared.memos.append(info)
        return f"메모 기록됨 (총 {len(shared.memos)}건). 기록된 내용: {info[:100]}"

    @tool
    async def complete_task(result: str) -> str:
        """태스크를 완료하고 최종 결과를 반환합니다.
        수집한 모든 정보를 종합하여 구조화된 완성된 답변을 작성해야 합니다.

        Args:
            result: 수집한 정보를 종합한 완성된 답변.
                    record_memo로 기록한 모든 정보를 포함하여 작성하세요.
                    "태스크 완료", "정보 수집 완료" 같은 빈 결과는 절대 금지입니다.
        """
        # ensureDone 패턴: 메모가 있는데 result가 너무 짧으면 거부
        if len(result) < 50 and shared.memos:
            memo_list = "\n".join(f"- {m}" for m in shared.memos)
            return (
                f"결과가 너무 짧습니다. 수집된 메모 {len(shared.memos)}건을 종합하여 "
                f"상세한 답변을 작성해주세요.\n\n수집된 메모:\n{memo_list}"
            )

        shared.task_complete = True
        shared.task_result = result
        return f"__TASK_COMPLETE__\n{result}"

    return {
        "tools": [
            observe_page, browser_click, browser_input, browser_navigate,
            browser_scroll, browser_keys, browser_select, browser_screenshot,
            browser_wait, record_memo, complete_task,
        ],
        "shared": shared,
    }
