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

    # ── 모달 감지 JS (시맨틱 + 휴리스틱) ──
    _DETECT_MODAL_JS = r"""() => {
        // 모달 감지용: opacity 무시 (애니메이션 진입 중인 모달도 감지)
        function isVis(el) {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }
        const cands = [];
        for (const d of document.querySelectorAll('dialog[open]')) { if (isVis(d)) cands.push(d); }
        for (const d of document.querySelectorAll('[role="dialog"]')) { if (isVis(d) && !cands.includes(d)) cands.push(d); }
        for (const d of document.querySelectorAll('[role="alertdialog"]')) { if (isVis(d) && !cands.includes(d)) cands.push(d); }
        for (const d of document.querySelectorAll('[aria-modal="true"]')) { if (isVis(d) && !cands.includes(d)) cands.push(d); }
        // 휴리스틱: 고 z-index + fixed/absolute + 뷰포트 대부분 차지하는 오버레이
        if (cands.length === 0) {
            const vw = window.innerWidth, vh = window.innerHeight;
            const hCands = [];
            for (const el of document.body.children) {
                if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'LINK') continue;
                const cs = window.getComputedStyle(el);
                const pos = cs.position;
                if (pos !== 'fixed' && pos !== 'absolute') continue;
                const z = parseInt(cs.zIndex) || 0;
                if (z < 999) continue;
                if (!isVis(el)) continue;
                const r = el.getBoundingClientRect();
                if ((r.width * r.height) / (vw * vh) < 0.15) continue;
                const hasContent = el.querySelector('button, a, input, [role="button"], h1, h2, h3, h4, img');
                if (!hasContent) continue;
                hCands.push({ el, z: z, area: r.width * r.height });
            }
            if (hCands.length > 0) {
                hCands.sort((a, b) => b.z - a.z || b.area - a.area);
                cands.push(hCands[0].el);
            }
        }
        if (cands.length === 0) return null;
        let top = cands[0], topZ = -Infinity;
        for (const m of cands) {
            const z = parseInt(window.getComputedStyle(m).zIndex) || 0;
            if (z >= topZ) { topZ = z; top = m; }
        }
        const name = top.getAttribute('aria-label')
            || (top.getAttribute('aria-labelledby') && document.getElementById(top.getAttribute('aria-labelledby'))?.textContent?.trim())
            || top.querySelector('h1,h2,h3,h4,[class*="title"],[class*="header"]')?.textContent?.trim()
            || top.tagName.toLowerCase();
        let sel = top.tagName.toLowerCase();
        if (top.id) {
            // CSS.escape()로 특수문자(콜론 등) 이스케이프
            sel = '#' + CSS.escape(top.id);
        }
        else if (top.getAttribute('role')) sel = '[role="' + top.getAttribute('role') + '"]';
        else if (top.tagName.toLowerCase() === 'dialog') sel = 'dialog[open]';
        return { name: (name || '').substring(0, 80), selector: sel };
    }"""

    # ── 클릭 대상 요소의 차단(obstruction) 감지 JS ──
    _CHECK_OBSTRUCTION_JS = r"""(aidx) => {
        const target = document.querySelector('[data-aidx="' + aidx + '"]');
        if (!target) return { obstructed: false, reason: 'target_not_found' };

        const rect = target.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return { obstructed: false, reason: 'zero_size' };

        // 여러 지점에서 elementFromPoint를 체크 (중심 + 4사분면)
        const points = [
            { x: rect.left + rect.width * 0.5, y: rect.top + rect.height * 0.5 },
            { x: rect.left + rect.width * 0.3, y: rect.top + rect.height * 0.3 },
            { x: rect.left + rect.width * 0.7, y: rect.top + rect.height * 0.7 },
        ];

        let blockerEl = null;
        let hitCount = 0;

        for (const pt of points) {
            const topEl = document.elementFromPoint(pt.x, pt.y);
            if (!topEl) continue;
            // target 자신이거나 target의 자손이면 OK
            if (target === topEl || target.contains(topEl)) {
                hitCount++;
                continue;
            }
            // topEl이 target의 조상이면 OK (클릭 이벤트가 버블링됨)
            if (topEl.contains(target)) {
                hitCount++;
                continue;
            }
            // 차단 요소 발견
            if (!blockerEl) blockerEl = topEl;
        }

        if (hitCount === points.length || !blockerEl) {
            return { obstructed: false, reason: 'clear' };
        }

        // 차단 요소 정보 수집
        const bs = window.getComputedStyle(blockerEl);
        const br = blockerEl.getBoundingClientRect();
        const text = (blockerEl.textContent || '').trim().substring(0, 120);
        const tag = blockerEl.tagName.toLowerCase();

        // 간단한 셀렉터 생성
        let sel = tag;
        if (blockerEl.id) sel = '#' + CSS.escape(blockerEl.id);
        else if (blockerEl.className && typeof blockerEl.className === 'string') {
            const cls = blockerEl.className.trim().split(/\s+/)[0];
            if (cls) sel = tag + '.' + CSS.escape(cls);
        }

        return {
            obstructed: true,
            reason: 'blocked',
            blocker: {
                selector: sel,
                tag: tag,
                text: text,
                position: bs.position,
                zIndex: parseInt(bs.zIndex) || 0,
                rect: { x: br.x, y: br.y, w: br.width, h: br.height },
            },
            target_rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        };
    }"""

    # ── 상태 핑거프린트 JS (post-action 변경 감지용) ──
    _STATE_FINGERPRINT_JS = r"""() => {
        // URL
        const url = window.location.href;

        // 활성 모달 존재 여부
        const hasModal = !!(
            document.querySelector('dialog[open]') ||
            document.querySelector('[role="dialog"]') ||
            document.querySelector('[role="alertdialog"]') ||
            document.querySelector('[aria-modal="true"]')
        );

        // 포커스된 요소
        const focused = document.activeElement;
        const focusTag = focused ? focused.tagName.toLowerCase() : '';
        const focusId = focused ? (focused.id || '') : '';

        // DOM 요소 수 (인터랙티브 요소만)
        const interactiveCount = document.querySelectorAll(
            'a[href], button, input, select, textarea, [role="button"], [role="tab"], [role="link"]'
        ).length;

        // 페이지 제목
        const title = document.title;

        return {
            url,
            title,
            has_modal: hasModal,
            focus_tag: focusTag,
            focus_id: focusId,
            interactive_count: interactiveCount,
        };
    }"""

    async def check_obstruction(self, aidx: int) -> dict:
        """클릭 대상 요소가 다른 요소에 가려져 있는지 확인

        Args:
            aidx: data-aidx 인덱스

        Returns:
            {
                'obstructed': bool,
                'reason': str,
                'blocker': { 'selector', 'tag', 'text', 'position', 'zIndex', 'rect' } | None,
                'target_rect': { 'x', 'y', 'w', 'h' } | None,
            }
        """
        return await self.page.evaluate(self._CHECK_OBSTRUCTION_JS, str(aidx))

    async def get_state_fingerprint(self) -> dict:
        """현재 페이지 상태 핑거프린트 반환 (post-action 변경 감지용)"""
        return await self.page.evaluate(self._STATE_FINGERPRINT_JS)

    async def resolve_obstruction(self, obstruction: dict) -> dict:
        """elementFromPoint로 감지된 차단 요소를 제거/숨기기

        Args:
            obstruction: check_obstruction()의 반환값 (obstructed=True)

        Returns:
            {
                'resolved': bool,
                'method': str,  # 'dismiss_button' | 'css_hide' | 'scroll' | 'dom_removal'
                'blocker_text': str,
            }
        """
        page = self.page
        blocker = obstruction.get('blocker', {})
        blocker_sel = blocker.get('selector', '')
        blocker_text = blocker.get('text', '')[:80]
        blocker_position = blocker.get('position', '')
        no_resolve = {'resolved': False, 'method': 'none', 'blocker_text': blocker_text}

        if not blocker_sel:
            return no_resolve

        logger.info(f"차단 요소 해소 시도: {blocker_sel} (text: {blocker_text[:40]}...)")

        # ── 1단계: 차단 요소 내 닫기/dismiss 버튼 클릭 ──
        closed = await page.evaluate(r"""(sel) => {
            const blocker = document.querySelector(sel);
            if (!blocker) return false;
            const closeBtns = blocker.querySelectorAll('button, a, [role="button"]');
            for (const btn of closeBtns) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.textContent || '').trim().toLowerCase();
                const isClose =
                    aria.includes('닫기') || aria.includes('close') || aria.includes('dismiss') ||
                    text === '닫기' || text === 'close' || text === 'x' || text === '×' ||
                    text === '✕' || text === '✖' || text === '✗' ||
                    text === '확인' || text === 'ok' || text === 'got it';
                if (isClose && btn.offsetParent !== null) {
                    try { btn.click(); return true; } catch(e) {}
                }
            }
            return false;
        }""", blocker_sel)

        if closed:
            await asyncio.sleep(0.5)
            return {'resolved': True, 'method': 'dismiss_button', 'blocker_text': blocker_text}

        # ── 2단계: CSS 숨김 (display:none + pointer-events:none) ──
        # position이 fixed/sticky인 경우 (배너류)에만 적용
        if blocker_position in ('fixed', 'sticky'):
            hidden = await page.evaluate(r"""(sel) => {
                const blocker = document.querySelector(sel);
                if (!blocker) return false;
                blocker.style.setProperty('display', 'none', 'important');
                return true;
            }""", blocker_sel)

            if hidden:
                await asyncio.sleep(0.3)
                return {'resolved': True, 'method': 'css_hide', 'blocker_text': blocker_text}

        # ── 3단계: 스크롤하여 대상 요소를 차단 영역 밖으로 이동 ──
        target_rect = obstruction.get('target_rect', {})
        blocker_rect = blocker.get('rect', {})
        if target_rect and blocker_rect:
            # 차단 요소가 하단 고정 배너인 경우, 대상을 위로 스크롤
            blocker_top = blocker_rect.get('y', 0)
            target_bottom = target_rect.get('y', 0) + target_rect.get('h', 0)
            if blocker_top > 0 and target_bottom > blocker_top:
                scroll_amount = int(target_bottom - blocker_top + 100)
                await page.mouse.wheel(0, -scroll_amount)  # 위로 스크롤
                await asyncio.sleep(0.5)
                return {'resolved': True, 'method': 'scroll', 'blocker_text': blocker_text}

        # ── 4단계: DOM 제거 (최후 수단) ──
        removed = await page.evaluate(r"""(sel) => {
            const blocker = document.querySelector(sel);
            if (!blocker) return false;
            blocker.remove();
            return true;
        }""", blocker_sel)

        if removed:
            await asyncio.sleep(0.3)
            return {'resolved': True, 'method': 'dom_removal', 'blocker_text': blocker_text}

        return no_resolve

    async def resolve_blocker(self) -> dict:
        """활성 모달/팝업을 감지하고 닫기를 시도

        단계별로 시도하고 매 시도 후 검증한다.

        Returns:
            {
                'resolved': bool,        # 성공적으로 닫았는지
                'had_blocker': bool,      # 블로커가 있었는지
                'blocker_name': str,      # 블로커 이름/설명
                'method': str,            # 사용된 방법
                'attempts': int,          # 시도 횟수
            }
        """
        page = self.page
        no_blocker = {'resolved': False, 'had_blocker': False, 'blocker_name': '', 'method': 'none', 'attempts': 0}

        # 페이지 로딩 안정화 대기
        await asyncio.sleep(1)

        # 쿠키 배너 먼저 처리
        await self._dismiss_cookie_banners()

        # 활성 모달 감지
        modal_info = await page.evaluate(self._DETECT_MODAL_JS)
        if not modal_info:
            return no_blocker

        blocker_name = modal_info.get('name', '')
        modal_selector = modal_info.get('selector', '')
        logger.info(f"활성 모달 감지: {blocker_name} ({modal_selector})")

        attempts = 0

        # ── 1단계: 모달 내부 닫기 버튼 클릭 ──
        attempts += 1
        closed = await page.evaluate(r"""(modalSel) => {
            const modal = document.querySelector(modalSel);
            if (!modal) return false;
            // 닫기 버튼 찾기: aria-label, 텍스트 내용 기반
            const closeBtns = modal.querySelectorAll('button, a, [role="button"]');
            for (const btn of closeBtns) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.textContent || '').trim().toLowerCase();
                const isClose = 
                    aria.includes('닫기') || aria.includes('close') || aria.includes('dismiss') ||
                    text === '닫기' || text === 'close' || text === 'x' || text === '×' ||
                    text === '✕' || text === '✖' || text === '✗' ||
                    text === '확인' || text === 'ok' || text === 'got it';
                if (isClose && btn.offsetParent !== null) {
                    try { btn.click(); return true; } catch(e) {}
                }
            }
            return false;
        }""", modal_selector)

        if closed:
            await asyncio.sleep(0.5)
            verify = await page.evaluate(self._DETECT_MODAL_JS)
            if not verify:
                logger.info(f"모달 닫기 성공 (close_button): {blocker_name}")
                return {'resolved': True, 'had_blocker': True, 'blocker_name': blocker_name, 'method': 'close_button', 'attempts': attempts}

        # ── 2단계: Escape 키 ──
        attempts += 1
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)
        verify = await page.evaluate(self._DETECT_MODAL_JS)
        if not verify:
            logger.info(f"모달 닫기 성공 (escape): {blocker_name}")
            return {'resolved': True, 'had_blocker': True, 'blocker_name': blocker_name, 'method': 'escape', 'attempts': attempts}

        # ── 3단계: backdrop 클릭 (모달 외부) ──
        attempts += 1
        try:
            modal_box = await page.evaluate(r"""(modalSel) => {
                const m = document.querySelector(modalSel);
                if (!m) return null;
                const r = m.getBoundingClientRect();
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            }""", modal_selector)
            if modal_box:
                # 모달 외부 좌상단에 클릭 (10, 10 또는 모달 오른쪽 + 20)
                click_x = modal_box['x'] + modal_box['w'] + 20
                click_y = 10
                if click_x > 1260:  # 뷰포트 밖이면 좌상단
                    click_x = 10
                    click_y = 10
                await page.mouse.click(click_x, click_y)
                await asyncio.sleep(0.5)
                verify = await page.evaluate(self._DETECT_MODAL_JS)
                if not verify:
                    logger.info(f"모달 닫기 성공 (backdrop): {blocker_name}")
                    return {'resolved': True, 'had_blocker': True, 'blocker_name': blocker_name, 'method': 'backdrop', 'attempts': attempts}
        except Exception:
            pass

        # ── 4단계: DOM 제거 (최후 수단) ──
        attempts += 1
        removed = await page.evaluate(r"""(modalSel) => {
            const modal = document.querySelector(modalSel);
            if (!modal) return false;
            modal.remove();
            // backdrop 제거 (반투명 fixed 요소)
            for (const el of document.querySelectorAll('*')) {
                const s = window.getComputedStyle(el);
                if (s.position !== 'fixed') continue;
                const bg = s.backgroundColor;
                const isBackdrop = bg.includes('rgba') && parseFloat(bg.split(',')[3]) < 0.9;
                if (isBackdrop) {
                    const r = el.getBoundingClientRect();
                    const cover = (r.width * r.height) / (window.innerWidth * window.innerHeight);
                    if (cover > 0.5) { el.remove(); }
                }
            }
            return true;
        }""", modal_selector)

        if removed:
            await asyncio.sleep(0.3)
            verify = await page.evaluate(self._DETECT_MODAL_JS)
            if not verify:
                logger.info(f"모달 닫기 성공 (dom_removal): {blocker_name}")
                return {'resolved': True, 'had_blocker': True, 'blocker_name': blocker_name, 'method': 'dom_removal', 'attempts': attempts}

        # 모든 단계 실패
        logger.warning(f"모달 닫기 실패: {blocker_name} ({attempts}회 시도)")
        return {'resolved': False, 'had_blocker': True, 'blocker_name': blocker_name, 'method': 'none', 'attempts': attempts}

    async def _dismiss_cookie_banners(self) -> int:
        """쿠키 동의 배너 등 일반 셀렉터 기반 오버레이 제거"""
        page = self.page
        return await page.evaluate(r"""() => {
            let count = 0;
            const closeSelectors = [
                '#onetrust-accept-btn-handler',
                '.cmp-btn-accept',
                '.cc-btn.cc-dismiss',
                '[class*="cookie"] button[class*="accept"]',
                '[class*="cookie"] button[class*="close"]',
                '[id*="cookie"] button[class*="accept"]',
                '[id*="cookie"] button[class*="close"]',
                'button[aria-label="Close"]',
                'button[aria-label="Dismiss"]',
            ];
            for (const sel of closeSelectors) {
                for (const btn of document.querySelectorAll(sel)) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    const isClose = !text ||
                        ['x', '×', '닫기', 'close', 'dismiss', 'ok', '확인',
                         '동의', 'accept', 'agree', 'got it'].includes(text) ||
                        text.includes('닫기') || text.includes('close') || text.includes('accept') || text.includes('동의');
                    if (isClose && btn.offsetParent !== null) {
                        try { btn.click(); count++; } catch(e) {}
                    }
                }
            }
            return count;
        }""")

    async def dismiss_overlays(self) -> int:
        """하위 호환용 래퍼"""
        result = await self.resolve_blocker()
        return 1 if result['resolved'] else 0

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
