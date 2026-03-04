"""페이지 상태 추출 모듈 (DOM 기반 + ARIA 보강 하이브리드)

브라우저 DOM에서 직접 상호작용 가능 요소를 추출한다.
1) 표준 인터랙티브 태그/role 셀렉터
2) cursor:pointer 감지 (div 클릭 핸들러 등)
3) ARIA 속성을 활용한 이름·역할 보강

각 요소에 data-aidx 속성을 주입하여 actions.py에서 안정적으로 위치를 찾는다.
"""

import logging
from dataclasses import dataclass
from playwright.async_api import Page

from src.config import A11Y_TEXT_LIMIT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JavaScript: 인터랙티브 요소 추출 + data-aidx 주입
# ---------------------------------------------------------------------------
_EXTRACT_JS = """() => {
    // ── Phase 1: 표준 인터랙티브 요소 수집 ──
    const INTERACTIVE_SELECTOR = [
        'a[href]', 'button', 'input', 'select', 'textarea', 'summary',
        '[role="button"]', '[role="tab"]', '[role="checkbox"]', '[role="radio"]',
        '[role="link"]', '[role="menuitem"]', '[role="option"]', '[role="switch"]',
        '[role="slider"]', '[role="combobox"]', '[role="searchbox"]',
        '[role="spinbutton"]', '[role="treeitem"]',
        '[tabindex]:not([tabindex="-1"])',
    ].join(', ');

    const interactiveSet = new Set();
    for (const el of document.querySelectorAll(INTERACTIVE_SELECTOR)) {
        interactiveSet.add(el);
    }

    // 가시성 검사 헬퍼
    function isVisible(el) {
        const style = window.getComputedStyle(el);
        // visibility: hidden / opacity: 0 체크
        if (style.visibility === 'hidden' || style.opacity === '0') return false;
        if (el.offsetParent === null) {
            // fixed/sticky는 offsetParent가 null이므로 별도 체크
            if (style.position !== 'fixed' && style.position !== 'sticky') return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    // Phase 1 결과 필터링 (가시 요소만)
    const phase1 = new Set();
    for (const el of interactiveSet) {
        if (isVisible(el)) phase1.add(el);
    }

    // ── Phase 2: cursor:pointer 요소 수집 (div 클릭 핸들러 등) ──
    const POINTER_TAGS = 'div, span, li, td, label, img, svg, i, p, h1, h2, h3, h4, h5, h6';
    const phase2 = new Set();

    for (const el of document.querySelectorAll(POINTER_TAGS)) {
        if (phase1.has(el)) continue;
        if (!isVisible(el)) continue;

        const cursor = window.getComputedStyle(el).cursor;
        if (cursor !== 'pointer') continue;

        const rect = el.getBoundingClientRect();
        if (rect.width < 10 || rect.height < 10) continue;

        // 내부에 Phase 1 인터랙티브 자식이 있으면 컨테이너이므로 스킵
        let hasInteractiveChild = false;
        for (const child of phase1) {
            if (el !== child && el.contains(child)) {
                hasInteractiveChild = true;
                break;
            }
        }
        if (hasInteractiveChild) continue;

        phase2.add(el);
    }

    // ── Phase 3: 합산 + 컨테이너 중복 제거 ──
    const merged = new Set([...phase1, ...phase2]);

    // 요소 A가 B를 포함할 때, A가 의미 없는 컨테이너면 제거 (더 구체적인 자식 유지)
    // 단, 네이티브 인터랙티브 요소(button, a 등)는 절대 제거하지 않음
    const toRemove = new Set();
    const NATIVE_INTERACTIVE = ['button', 'a', 'input', 'select', 'textarea', 'summary'];

    for (const a of merged) {
        for (const b of merged) {
            if (a === b) continue;
            if (a.contains(b)) {
                const tagA = a.tagName.toLowerCase();
                // 네이티브 인터랙티브 요소이거나 명시적 role이 있으면 제거하지 않음
                if (!NATIVE_INTERACTIVE.includes(tagA) && !a.getAttribute('role')) {
                    toRemove.add(a);
                    break;
                }
            }
        }
    }
    for (const el of toRemove) merged.delete(el);

    // ── Phase 4: DOM 순서 정렬 ──
    const sorted = [...merged].sort((a, b) =>
        a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
    );

    // ── Phase 5: 요소 정보 추출 ──
    // 태그 → 기본 role 매핑
    function inferRole(el) {
        const explicit = el.getAttribute('role');
        if (explicit) return explicit;

        const tag = el.tagName.toLowerCase();
        if (tag === 'a') return 'link';
        if (tag === 'button') return 'button';
        if (tag === 'select') return 'combobox';
        if (tag === 'textarea') return 'textbox';
        if (tag === 'summary') return 'button';
        if (tag === 'input') {
            const type = (el.type || 'text').toLowerCase();
            if (type === 'checkbox') return 'checkbox';
            if (type === 'radio') return 'radio';
            if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
            if (type === 'range') return 'slider';
            if (type === 'number') return 'spinbutton';
            if (type === 'search') return 'searchbox';
            return 'textbox';
        }
        // cursor:pointer div/span 등 → generic 'button'
        if (window.getComputedStyle(el).cursor === 'pointer') return 'button';
        return 'generic';
    }

    // 이름 추출 (우선순위 — W3C Accessible Name 계산 기반)
    function extractName(el) {
        const tag = el.tagName.toLowerCase();

        // 1. aria-label (최우선: 개발자가 명시적으로 지정한 접근성 이름)
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim().substring(0, 80);

        // 2. aria-labelledby
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const parts = [];
            for (const id of labelledBy.split(/\s+/)) {
                const ref = document.getElementById(id);
                if (ref) parts.push(ref.textContent.trim());
            }
            const joined = parts.join(' ').trim();
            if (joined) return joined.substring(0, 80);
        }

        // 3. <label for="id">
        if (el.id) {
            const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (label) {
                const lt = label.textContent.trim();
                if (lt) return lt.substring(0, 80);
            }
        }

        // 4. 직접 자식 텍스트 노드만 (중첩 컴포넌트 텍스트 방지)
        if (tag === 'a' || tag === 'button' || tag === 'summary') {
            const directText = [];
            for (const node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const t = node.textContent.trim();
                    if (t) directText.push(t);
                }
            }
            const joined = directText.join(' ').trim();
            if (joined) return joined.substring(0, 80);
        }

        // 5. 자식 요소의 접근성 이름 (아이콘 전용 버튼 대응)
        //    <img alt>, <svg aria-label>, <svg><title>, <i aria-label>
        const childImg = el.querySelector(':scope > img[alt], :scope > svg img[alt]');
        if (childImg) {
            const alt = childImg.getAttribute('alt').trim();
            if (alt) return alt.substring(0, 80);
        }
        const childSvg = el.querySelector(':scope > svg[aria-label]');
        if (childSvg) {
            const svgLabel = childSvg.getAttribute('aria-label').trim();
            if (svgLabel) return svgLabel.substring(0, 80);
        }
        const svgTitle = el.querySelector(':scope > svg > title');
        if (svgTitle) {
            const st = svgTitle.textContent.trim();
            if (st) return st.substring(0, 80);
        }
        const childIcon = el.querySelector(':scope > i[aria-label], :scope > span[aria-label]');
        if (childIcon) {
            const iconLabel = childIcon.getAttribute('aria-label').trim();
            if (iconLabel) return iconLabel.substring(0, 80);
        }

        // 6. innerText (전체, 잘라서)
        const inner = (el.innerText || '').trim();
        if (inner) return inner.substring(0, 80);

        // 7. title / placeholder / alt / value (최후 수단 — W3C 스펙 준수)
        for (const attr of ['title', 'placeholder', 'alt', 'value']) {
            const v = el.getAttribute(attr);
            if (v && v.trim()) return v.trim().substring(0, 80);
        }

        // 8. 폴백: (tag.className)
        const cls = (el.className && typeof el.className === 'string')
            ? el.className.split(' ')[0] || 'unknown'
            : 'unknown';
        return '(' + tag + '.' + cls + ')';
    }

    // ── Phase 6: Viewport 필터링 ──
    // 현재 화면에 보이는 요소만 추출하여 LLM 입력 토큰을 절감한다.
    // 스크롤 후 매 스텝마다 재추출하므로 뷰포트 밖 요소는 스크롤 시 자연히 포함됨.
    function inViewport(el) {
        const rect = el.getBoundingClientRect();
        const winH = window.innerHeight || document.documentElement.clientHeight;
        const winW = window.innerWidth || document.documentElement.clientWidth;
        const margin = 50; // 경계에 걸친 요소 보호
        return (
            rect.bottom >= -margin &&
            rect.right >= -margin &&
            rect.top <= winH + margin &&
            rect.left <= winW + margin &&
            rect.width > 0 &&
            rect.height > 0
        );
    }

    // ── Phase 6-B: Layer 태깅 (휴리스틱 기반) ──
    // 팝업/오버레이 요소를 식별하여 LLM에 맥락 힌트를 제공한다.
    // z-index는 CSS Stacking Context 때문에 정확한 계산이 불가하므로,
    // dialog/aria-modal + position:fixed 휴리스틱으로 판정한다.
    function getLayerContext(el) {
        let parent = el;
        while (parent && parent !== document.body && parent !== document.documentElement) {
            const tag = parent.tagName.toLowerCase();
            const role = parent.getAttribute('role');

            // 1. 명시적 다이얼로그/모달
            if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog'
                || parent.getAttribute('aria-modal') === 'true') {
                return 'popup';
            }

            // 2. position:fixed + z-index >= 10 → 오버레이 (헤더/플로팅 버튼 등)
            const style = window.getComputedStyle(parent);
            if (style.position === 'fixed') {
                const z = parseInt(style.zIndex);
                if (!isNaN(z) && z >= 10) {
                    return 'overlay';
                }
            }

            parent = parent.parentElement;
        }
        return 'main';
    }

    // ── Phase 7: data-aidx 주입 + 결과 배열 생성 ──
    const results = [];
    let index = 1;

    for (const el of sorted) {
        // 뷰포트 밖 요소는 건너뜀
        if (!inViewport(el)) continue;

        const tag = el.tagName.toLowerCase();
        const role = inferRole(el);
        const name = extractName(el);

        // 미명명 요소 제거: "(tag.class)" 폴백 이름 + 네이티브 인터랙티브 아님 + generic role
        // → LLM에 가치 없는 노이즈이므로 제거
        const isFallbackName = name.startsWith('(') && name.endsWith(')');
        const isNative = ['button', 'input', 'select', 'textarea', 'a', 'summary'].includes(tag);
        if (isFallbackName && !isNative && role === 'generic') {
            continue;
        }

        // 필터 통과 후 인덱스 부여 (연속적 번호 유지)
        el.setAttribute('data-aidx', String(index));

        const layer = getLayerContext(el);
        const info = { index, tag, role, name, layer };

        // value (input/textarea/select)
        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            info.value = el.value || '';
        }

        // checked (checkbox/radio)
        if (el.type === 'checkbox' || el.type === 'radio' ||
            role === 'checkbox' || role === 'radio' || role === 'switch') {
            info.checked = !!el.checked;
        } else {
            info.checked = null;
        }

        // disabled
        info.disabled = el.disabled === true ||
                        el.getAttribute('aria-disabled') === 'true';

        results.push(info);
        index++;
    }

    return results;
}"""

# ---------------------------------------------------------------------------
# JavaScript: 페이지 텍스트 요약 추출
# ---------------------------------------------------------------------------
_PAGE_TEXT_JS = """() => {
    const raw = (document.body.innerText || '').trim();
    // 연속 공백/줄바꿈을 하나로 축소
    const collapsed = raw.replace(/[\\s\\n]+/g, ' ');
    return collapsed.substring(0, 2000);
}"""


# ---------------------------------------------------------------------------
# Accessibility Tree 추출 함수
# ---------------------------------------------------------------------------
def _truncate_yaml(yaml_text: str, max_chars: int) -> str:
    """YAML 텍스트를 줄 단위로 안전하게 잘라냄"""
    if len(yaml_text) <= max_chars:
        return yaml_text
    lines = yaml_text.split('\n')
    result = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_chars:
            break
        result.append(line)
        current_len += len(line) + 1
    result.append("  ... (truncated)")
    return '\n'.join(result)


async def _get_aria_snapshot(page: Page, max_chars: int) -> str:
    """Accessibility Tree YAML 스냅샷 추출

    1차: main/article 영역만 추출 (본문 집중)
    2차: body 전체 추출 (main이 없는 페이지)
    3차: 기존 innerText 폴백
    """
    # 1차: main 영역 우선
    for selector in ['main', '[role="main"]', 'article']:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                snapshot = await locator.aria_snapshot()
                if snapshot and len(snapshot.strip()) > 50:
                    return _truncate_yaml(snapshot, max_chars)
        except Exception:
            continue

    # 2차: body 전체
    try:
        snapshot = await page.locator('body').aria_snapshot()
        if snapshot:
            return _truncate_yaml(snapshot, max_chars)
    except Exception:
        pass

    # 3차: 기존 innerText 폴백
    try:
        return await page.evaluate(_PAGE_TEXT_JS)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------
@dataclass
class IndexedElement:
    """인덱싱된 페이지 요소"""

    index: int
    role: str
    name: str
    tag: str = ""  # HTML 태그명 (e.g. "button", "div", "a")
    layer: str = "main"  # 레이어: "main" | "overlay" | "popup"
    nth: int = 0  # 하위 호환성 유지 (현재 미사용, 항상 0)
    value: str = ""
    description: str = ""
    checked: bool | None = None
    disabled: bool = False
    selector: str = ""  # '[data-aidx="N"]' CSS 셀렉터

    def to_display(self) -> str:
        """LLM에게 보여줄 한 줄 텍스트"""
        # 본문(main) 요소는 레이어 태그 생략 (토큰 절약)
        # 오버레이/팝업만 명시하여 LLM에 맥락 힌트 제공
        layer_tag = ""
        if self.layer == "popup":
            layer_tag = "[팝업] "
        elif self.layer == "overlay":
            layer_tag = "[오버레이] "

        parts = [f'[{self.index}] {layer_tag}{self.role} <{self.tag}>: "{self.name}"']
        if self.value:
            parts.append(f'(value: "{self.value}")')
        if self.checked is not None:
            parts.append(f"(checked: {self.checked})")
        if self.disabled:
            parts.append("(disabled)")
        return " ".join(parts)


@dataclass
class PageState:
    """현재 페이지 상태"""

    url: str
    title: str
    elements: list[IndexedElement]
    page_text: str = ""  # 페이지 가시 텍스트 요약 (최대 2000자)

    def to_prompt_text(self) -> str:
        """LLM 프롬프트에 삽입할 전체 상태 텍스트"""
        if not self.elements:
            return f"URL: {self.url}\n제목: {self.title}\n\n(상호작용 가능한 요소 없음)"

        elements_text = "\n".join(e.to_display() for e in self.elements)
        text = (
            f"URL: {self.url}\n"
            f"제목: {self.title}\n"
            f"상호작용 가능 요소 ({len(self.elements)}개):\n"
            f"{elements_text}"
        )

        if self.page_text:
            text += f"\n\n페이지 콘텐츠 (Accessibility Tree):\n{self.page_text}"

        return text

    def find_by_index(self, index: int) -> IndexedElement | None:
        """인덱스로 요소 검색"""
        for e in self.elements:
            if e.index == index:
                return e
        return None


# ---------------------------------------------------------------------------
# 메인 추출 함수
# ---------------------------------------------------------------------------
async def get_indexed_state(page: Page) -> PageState:
    """페이지에서 상호작용 가능 요소를 DOM 기반으로 추출 → 인덱스 부여

    1) 표준 인터랙티브 요소 (a, button, input 등 + ARIA role)
    2) cursor:pointer 요소 (div 클릭 핸들러 등)
    3) data-aidx 속성 주입으로 안정적 요소 위치 확보
    """
    try:
        raw_elements = await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        logger.warning(f"DOM 요소 추출 실패: {e}")
        raw_elements = []

    try:
        page_text = await _get_aria_snapshot(page, A11Y_TEXT_LIMIT)
    except Exception:
        page_text = ""

    elements = []
    for item in raw_elements:
        elements.append(
            IndexedElement(
                index=item["index"],
                role=item["role"],
                name=item["name"],
                tag=item.get("tag", ""),
                layer=item.get("layer", "main"),
                value=item.get("value", ""),
                checked=item.get("checked"),
                disabled=item.get("disabled", False),
                selector=f'[data-aidx="{item["index"]}"]',
            )
        )

    logger.info(f"DOM 추출 완료: {len(elements)}개 요소")

    return PageState(
        url=page.url,
        title=await page.title(),
        elements=elements,
        page_text=page_text,
    )
