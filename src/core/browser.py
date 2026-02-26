"""Playwright 브라우저 관리 모듈

브라우저 인스턴스의 생성, 관리, 종료를 담당한다.
Phase 1-A에서는 단일 브라우저 + 단일 페이지만 지원.
"""

import asyncio
import base64
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from src.config import HEADLESS, BROWSER_TIMEOUT, SCREENSHOT_DIR

logger = logging.getLogger(__name__)


class BrowserManager:
    """Playwright 브라우저 생명주기 관리"""

    def __init__(self, headless: bool = HEADLESS):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        """브라우저 시작 → 페이지 반환"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(BROWSER_TIMEOUT)
        return self._page

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def navigate(self, url: str) -> None:
        """URL로 이동"""
        await self.page.goto(url, wait_until="domcontentloaded")

    async def screenshot_base64(self) -> str:
        """현재 페이지 스크린샷 → base64 문자열"""
        raw = await self.page.screenshot(type="jpeg", quality=60)
        return base64.b64encode(raw).decode("utf-8")

    async def screenshot_file(self, name: str = "screenshot") -> Path:
        """현재 페이지 스크린샷 → 파일 저장"""
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}.png"
        await self.page.screenshot(path=str(path))
        return path

    async def dismiss_overlays(self) -> int:
        """페이지의 팝업/오버레이/쿠키 배너 등을 자동으로 제거

        공통 패턴의 닫기 버튼을 찾아 클릭하고,
        남은 고정 오버레이는 DOM에서 직접 제거한다.

        Returns:
            제거된 오버레이 수
        """
        page = self.page

        # 페이지 로딩 안정화 대기
        await asyncio.sleep(1)

        dismissed = await page.evaluate(r"""() => {
            let count = 0;

            // 1단계: 공통 닫기 버튼 셀렉터로 클릭 시도
            const closeSelectors = [
                // 쿠키 동의 프레임워크
                '#onetrust-accept-btn-handler',
                '.cmp-btn-accept',
                '.cc-btn.cc-dismiss',
                '[class*="cookie"] button[class*="accept"]',
                '[class*="cookie"] button[class*="close"]',
                '[id*="cookie"] button[class*="accept"]',
                '[id*="cookie"] button[class*="close"]',
                // 한국어 패턴
                'button[aria-label="닫기"]',
                'button[aria-label="팝업 닫기"]',
                'a[class*="close"]',
                // 영어 패턴
                'button[aria-label="Close"]',
                'button[aria-label="Dismiss"]',
                // 모달/팝업 닫기
                '[class*="modal"] [class*="close"]',
                '[class*="popup"] [class*="close"]',
                '[class*="dialog"] [class*="close"]',
                '[class*="banner"] [class*="close"]',
                '[class*="overlay"] [class*="close"]',
                // 일반적 닫기 버튼 텍스트 매칭 (모달/팝업 내부만)
                '[class*="modal"] button',
                '[class*="popup"] button',
            ];

            for (const sel of closeSelectors) {
                const btns = document.querySelectorAll(sel);
                for (const btn of btns) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    const isClose = !text ||
                        ['x', '×', '닫기', 'close', 'dismiss', 'ok', '확인',
                         '동의', '동의하고 계속', 'accept', 'agree', 'got it'].includes(text) ||
                        text.includes('닫기') || text.includes('close') ||
                        text.includes('accept') || text.includes('동의');
                    if (isClose && btn.offsetParent !== null) {
                        try { btn.click(); count++; } catch(e) {}
                    }
                }
            }

            // 2단계: 텍스트 기반 닫기 버튼 탐색 (셀렉터에 안 잡힌 버튼)
            const allButtons = document.querySelectorAll('button, a, span, div');
            for (const btn of allButtons) {
                if (btn.offsetParent === null) continue;
                const text = (btn.textContent || '').trim();
                // "×", "X", "✕", "✖" 등 닫기 아이콘 문자
                if (text === '×' || text === 'X' || text === '✕' || text === '✖' || text === '✗') {
                    // 부모가 fixed/absolute 포지션인지 확인 (팝업/모달 소속)
                    let parent = btn.parentElement;
                    let isOverlay = false;
                    for (let i = 0; i < 5 && parent; i++) {
                        const ps = window.getComputedStyle(parent).position;
                        if (ps === 'fixed' || ps === 'absolute') { isOverlay = true; break; }
                        parent = parent.parentElement;
                    }
                    if (isOverlay) {
                        try { btn.click(); count++; } catch(e) {}
                    }
                }
            }

            // 3단계: 남은 배경 오버레이(backdrop)만 DOM 제거
            // 주의: 실제 콘텐츠 모달을 제거하지 않도록 보수적으로 접근
            const allFixed = document.querySelectorAll('*');
            for (const el of allFixed) {
                const style = window.getComputedStyle(el);
                if (style.position !== 'fixed' && style.position !== 'sticky') continue;
                if (style.display === 'none' || style.visibility === 'hidden') continue;

                const zIndex = parseInt(style.zIndex) || 0;
                if (zIndex < 100) continue;

                const rect = el.getBoundingClientRect();
                const viewW = window.innerWidth;
                const viewH = window.innerHeight;
                const coverageRatio = (rect.width * rect.height) / (viewW * viewH);

                // 화면의 80% 이상을 덮는 요소만 제거 (50% → 80% 상향)
                if (coverageRatio < 0.8) continue;

                // 내부에 인터랙티브 요소가 있으면 콘텐츠 모달이므로 제거하지 않음
                const hasInteractive = el.querySelector(
                    'a[href], button, input, select, textarea, [role="button"], [role="tab"]'
                );
                if (hasInteractive) continue;

                // 배경색이 반투명이거나 어두운 배경인 경우만 제거 (backdrop 특징)
                const bg = style.backgroundColor;
                const isBackdrop = (
                    bg.includes('rgba') && parseFloat(bg.split(',')[3]) < 0.9 ||
                    bg === 'rgba(0, 0, 0, 0)' ||
                    style.opacity !== '' && parseFloat(style.opacity) < 0.95
                );
                if (isBackdrop) {
                    el.remove();
                    count++;
                }
            }

            return count;
        }""")

        if dismissed > 0:
            logger.info(f"오버레이 {dismissed}개 자동 제거 완료")
            await asyncio.sleep(0.5)  # 제거 후 안정화 대기

        return dismissed

    async def close(self) -> None:
        """브라우저 종료"""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()
