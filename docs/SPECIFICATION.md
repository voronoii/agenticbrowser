# Agentic Browser — 기술 명세서

> **버전**: Phase 1-A (2026-02-26)
> **관련 문서**: `agentic-crawler-plan-v2.md` (전체 로드맵)

---

## 목차

- [1. 프로젝트 개요](#1-프로젝트-개요)
- [2. 아키텍처](#2-아키텍처)
- [3. 모듈 상세](#3-모듈-상세)
  - [3.1 config.py — 환경 설정](#31-configpy--환경-설정)
  - [3.2 core/browser.py — BrowserManager](#32-corebrowserpy--browsermanager)
  - [3.3 core/state.py — 페이지 상태 추출](#33-corestatepy--페이지-상태-추출)
  - [3.4 core/actions.py — 액션 파싱 및 실행](#34-coreactionspy--액션-파싱-및-실행)
  - [3.5 core/agent_loop.py — 에이전트 핵심 루프](#35-coreagent_looppy--에이전트-핵심-루프)
  - [3.6 llm/client.py — LLM 클라이언트](#36-llmclientpy--llm-클라이언트)
  - [3.7 server.py — FastAPI 서버](#37-serverpy--fastapi-서버)
  - [3.8 main.html — 프론트엔드 UI](#38-mainhtml--프론트엔드-ui)
- [4. 데이터 흐름](#4-데이터-흐름)
- [5. 지원 액션 목록](#5-지원-액션-목록)
- [6. WebSocket 프로토콜](#6-websocket-프로토콜)
- [7. 환경 변수](#7-환경-변수)
- [8. Docker 배포](#8-docker-배포)
- [9. 의존성](#9-의존성)
- [10. 관리 포인트 및 알려진 제한사항](#10-관리-포인트-및-알려진-제한사항)
- [11. 로드맵 (Phase 1-B 이후)](#11-로드맵-phase-1-b-이후)

---

## 1. 프로젝트 개요

Agentic Browser는 사용자가 자연어로 태스크(Goal)를 입력하면, LLM이 브라우저를 자율적으로 조작하여 태스크를 수행하는 범용 웹 자동화 에이전트임

### 핵심 설계 원리

```
사용자 입력 (Goal + Direction + Context)
  → Observation (DOM 기반 상태 추출)
    → LLM Decision (다음 액션 결정)
      → Action Execution (Playwright 명령 실행)
        → 반복 (태스크 완료 또는 종료 조건까지)
```

### 지원 태스크 유형

| 유형 | 예시 |
|---|---|
| 데이터 수집 | "호갱노노에서 강남구 아파트 리뷰 수집" |
| 폼 작성/제출 | "이 지원서 양식을 작성해줘" |
| 네비게이션/조작 | "네이버 카페에서 새 글 작성" |
| 리서치 | "3개 사이트에서 제품 가격 비교" |

### Phase 1-A 범위

- 단일 `agent_loop()` 루프가 동작하는 최소 시스템
- 기본 액션 6개 + 제어 액션 4개
- 단일 브라우저 + 단일 페이지
- WebSocket 기반 실시간 UI

---

## 2. 아키텍처

### 디렉토리 구조

```
agentic_crawler/
├── src/
│   ├── config.py              # 환경 변수 로드
│   ├── server.py              # FastAPI + WebSocket 서버
│   ├── main.html              # 프론트엔드 UI (SPA)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── browser.py         # BrowserManager 클래스
│   │   ├── state.py           # DOM 기반 상태 추출
│   │   ├── actions.py         # 액션 파싱 + Playwright 실행
│   │   ├── agent_loop.py      # Observation → LLM → Action 루프
│   │   └── failed_page.html   # 에러 페이지 템플릿
│   └── llm/
│       ├── __init__.py
│       └── client.py          # LangChain LLM 래퍼
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env / .env.example
├── logs/                      # 런타임 로그 (gitignore)
└── screenshots/               # 스크린샷 저장 (gitignore)
```

### 모듈 의존성 그래프

```
server.py
  ├── core/browser.py      → config.py
  ├── core/agent_loop.py   → core/browser.py
  │                        → core/state.py
  │                        → core/actions.py  → core/state.py
  │                        → llm/client.py    → config.py
  │                        → config.py
  └── llm/client.py        → config.py
```

### 실행 흐름 (단일 태스크)

```
1. server.py:  WebSocket 수신 → run_agent_task() 생성
2. browser.py: BrowserManager.start() → Chromium 브라우저 기동
3. llm/client.py: create_llm() → LangChain LLM 인스턴스 생성
4. agent_loop.py: run_agent_loop() 진입
   ├── [start_url이 있으면] browser.navigate() → dismiss_overlays()
   └── 스텝 루프 (최대 MAX_STEPS 회):
       ├── state.py:   get_indexed_state(page) → PageState
       ├── llm:        invoke_llm(state_text, goal, ...) → JSON 응답
       ├── actions.py: parse_action(response) → AgentAction
       ├── actions.py: execute_action(page, action, state) → ActionResult
       ├── screenshot: browser.screenshot_base64()
       ├── callback:   on_step(step_log) → WebSocket broadcast
       └── 종료 조건: done / ask_human / max_failures / stuck_abort
5. server.py: 결과 broadcast → browser.close()
```

---

## 3. 모듈 상세

### 3.1 config.py — 환경 설정

**파일**: `src/config.py` (32줄)
**역할**: `.env` 파일에서 환경 변수를 로드하고 전역 상수를 제공한다.

| 상수 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `OPENAI_API_KEY` | str | `""` | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | str | `""` | Anthropic API 키 |
| `DEFAULT_LLM_PROVIDER` | str | `"openai"` | LLM 프로바이더 (`openai` / `anthropic`) |
| `DEFAULT_MODEL` | str | `"gpt-5-mini"` | 기본 모델 ID |
| `HEADLESS` | bool | `True` | 브라우저 헤드리스 모드 |
| `BROWSER_TIMEOUT` | int | `30000` | 브라우저 기본 타임아웃 (ms) |
| `SCREENSHOT_DIR` | Path | `{PROJECT_ROOT}/screenshots` | 스크린샷 저장 경로 |
| `MAX_STEPS` | int | `50` | 에이전트 최대 스텝 수 |
| `MAX_FAILURES` | int | `5` | 최대 연속 실패 허용 수 |
| `SERVER_HOST` | str | `"0.0.0.0"` | 서버 바인드 주소 |
| `SERVER_PORT` | int | `1234` | 서버 포트 |

---

### 3.2 core/browser.py — BrowserManager

**파일**: `src/core/browser.py` (215줄)
**역할**: Playwright 브라우저의 생명주기(생성 → 사용 → 종료)를 관리한다.

#### 클래스: `BrowserManager`

| 메서드 | 반환값 | 설명 |
|---|---|---|
| `__init__(headless)` | - | 상태 초기화 |
| `start()` | `Page` | Chromium 실행 → 컨텍스트 생성 → 페이지 반환 |
| `page` (property) | `Page` | 현재 활성 페이지 (미시작 시 RuntimeError) |
| `navigate(url)` | `None` | URL로 이동 (`domcontentloaded` 대기) |
| `screenshot_base64()` | `str` | JPEG 60% 품질 → base64 인코딩 |
| `screenshot_file(name)` | `Path` | PNG 파일로 스크린샷 저장 |
| `dismiss_overlays()` | `int` | 팝업/오버레이 자동 제거 → 제거된 수 반환 |
| `close()` | `None` | 브라우저 전체 종료 |
| `__aenter__` / `__aexit__` | - | async context manager 지원 |

#### 브라우저 설정

```python
chromium.launch(
    headless=HEADLESS,
    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
)
new_context(
    viewport={"width": 1280, "height": 720},
    locale="ko-KR",
    timezone_id="Asia/Seoul"
)
```

#### dismiss_overlays() 상세

3단계로 팝업/오버레이를 자동 제거한다:

| 단계 | 방법 | 대상 |
|---|---|---|
| **1단계** | CSS 셀렉터 매칭 → 클릭 | 쿠키 동의(OneTrust, CMP), 한국어/영어 닫기 버튼, 모달/팝업 내 버튼 |
| **2단계** | 텍스트 기반 탐색 → 클릭 | `×`, `X`, `✕`, `✖`, `✗` 문자를 가진 버튼 (fixed/absolute 부모 소속) |
| **3단계** | DOM 직접 제거 | `position:fixed`, `z-index≥100`, 화면 80%+ 차지, 인터랙티브 자식 없음, 반투명 배경 (backdrop) |

**보수적 전략**: 인터랙티브 요소가 있는 모달은 제거하지 않음 (콘텐츠 모달 보호).

---

### 3.3 core/state.py — 페이지 상태 추출

**파일**: `src/core/state.py` (343줄)
**역할**: 브라우저 DOM에서 상호작용 가능한 요소를 추출하여 인덱싱한다.

#### 추출 방식: DOM 기반 + cursor:pointer 하이브리드

Playwright의 `page.evaluate()`로 JavaScript를 브라우저에서 직접 실행한다.

**Phase 1~3**: 표준 인터랙티브 요소 수집

```
a[href], button, input, select, textarea, summary
[role="button"], [role="tab"], [role="checkbox"], [role="radio"],
[role="link"], [role="menuitem"], [role="option"], [role="switch"],
[role="slider"], [role="combobox"], [role="searchbox"],
[role="spinbutton"], [role="treeitem"],
[tabindex]:not([tabindex="-1"])
```

**Phase 4**: cursor:pointer 감지

표준 셀렉터에 잡히지 않는 `div`, `span` 등에서 `getComputedStyle(el).cursor === "pointer"`인 요소를 추가 수집한다. 이미 수집된 요소의 자식은 제외.

**Phase 5**: 가시성 필터링 + DOM 순서 정렬

- `offsetParent === null` (hidden) 제외 (단, `position:fixed/sticky`는 허용)
- `display:none`, `visibility:hidden` 제외
- 크기 0 제외 (`width < 1 || height < 1`)
- DOM 순서 기준 정렬 (`compareDocumentPosition`)

**Phase 6~7**: data-aidx 주입 + 결과 배열 생성

- 각 요소에 `data-aidx="N"` 속성 주입 (1부터 순서대로)
- `actions.py`에서 `[data-aidx="N"]` CSS 셀렉터로 요소를 안정적으로 찾음

#### 요소 이름 추출 우선순위 (extractName)

1. `aria-label` / `aria-labelledby` → 참조 요소 텍스트 결합
2. `<label for="id">` 매칭
3. `a`, `button`, `summary` → 직접 자식 텍스트 노드만
4. `innerText` (전체, 80자 잘라서)
5. `placeholder` / `title` / `alt` / `value`
6. 폴백: `(tag.className)`

#### 역할 추론 (inferRole)

1. 명시적 `role` 속성 → 그대로 사용
2. 태그 기반 추론: `a` → `link`, `button/summary` → `button`, `input` → `type별`, `select` → `combobox`, `textarea` → `textbox`
3. cursor:pointer div → `"button"` (클릭 핸들러)
4. 폴백: `"generic"`

#### 데이터 클래스

```python
@dataclass
class IndexedElement:
    index: int           # 1부터 시작하는 요소 인덱스
    role: str            # 추론된 ARIA 역할
    name: str            # 추출된 요소 이름 (최대 80자)
    tag: str             # HTML 태그명 (e.g. "button", "div")
    nth: int = 0         # 하위 호환성 (현재 미사용)
    value: str           # input/select의 현재 값
    description: str     # 추가 설명
    checked: bool | None # 체크박스/라디오 체크 상태
    disabled: bool       # 비활성화 여부
    selector: str        # '[data-aidx="N"]' CSS 셀렉터

@dataclass
class PageState:
    url: str
    title: str
    elements: list[IndexedElement]
    page_text: str       # 페이지 가시 텍스트 요약 (최대 2000자)

    def to_prompt_text() -> str    # LLM 프롬프트용 전체 상태 텍스트
    def find_by_index(int) -> IndexedElement | None
```

#### 성능 참고

- subwayyy.kr: 97개 요소 추출 (기존 aria_snapshot 방식의 5개 대비 19배 개선)
- 태그 분포 예시: div 85개, button 6개, a 4개, input 2개

---

### 3.4 core/actions.py — 액션 파싱 및 실행

**파일**: `src/core/actions.py` (315줄)
**역할**: LLM 응답(JSON)을 파싱하여 `AgentAction`으로 변환하고, Playwright 명령으로 실행한다.

#### 데이터 클래스

```python
@dataclass
class AgentAction:
    action: str                # 액션명 (click, input, scroll, ...)
    index: int | None          # 대상 요소 인덱스
    text: str | None           # 입력 텍스트 (input, wait)
    url: str | None            # 이동할 URL (navigate)
    combo: str | None          # 키보드 조합 (keys)
    option: str | None         # 선택 옵션 (select)
    direction: str | None      # 스크롤 방향 (scroll)
    amount: int | None         # 스크롤 양 / 대기 시간
    result: Any                # 태스크 결과 (done)
    question: str | None       # 질문 텍스트 (ask_human)
    reason: str                # LLM이 밝힌 액션 이유
    extra: dict                # 위 필드에 안 잡힌 추가 데이터

@dataclass
class ActionResult:
    success: bool
    action: str
    message: str
    data: Any = None           # 결과 데이터 (screenshot base64, done result 등)
    error: str | None = None
```

#### parse_action(llm_response) → AgentAction

1. `\`\`\`json ... \`\`\`` 또는 `{ ... }` 블록 추출
2. JSON 파싱
3. **함수 호출 형태 분해**: `"scroll(down, 800)"` → `action="scroll", direction="down", amount=800`
   - `click(N)`, `input(N, text)`, `keys(combo)`, `navigate(url)`, `wait(seconds)`, `done(result)` 지원
4. `AgentAction` 생성

#### _get_element_locator(page, state, index) → (Locator, IndexedElement)

요소 찾기 전략 (2단계 폴백):

| 순서 | 방법 | 조건 |
|---|---|---|
| 1차 | `page.locator('[data-aidx="N"]')` | `element.selector` 존재 시 (가장 안정적) |
| 2차 | `page.get_by_role(role, name=name)` | data-aidx가 없는 경우 폴백 |

#### execute_action(page, action, state) → ActionResult

`match/case` 패턴으로 10개 액션을 디스패치한다.

| 액션 | Playwright 명령 | 특이사항 |
|---|---|---|
| `click` | `locator.click()` | 실패 시 `force=True`로 재시도 |
| `input` | `locator.click()` → `locator.fill(text)` | 기존 내용 대체 |
| `keys` | `page.keyboard.press(combo)` | Enter, Tab, Control+a 등 |
| `select` | `locator.select_option(option)` | 드롭다운 선택 |
| `scroll` | `page.mouse.wheel(0, dy)` | up/down + 픽셀 양 |
| `navigate` | `page.goto(url)` | `domcontentloaded` 대기 |
| `screenshot` | `page.screenshot(jpeg, 60%)` → base64 | 데이터 반환 |
| `wait` | `page.wait_for_selector()` / `asyncio.sleep()` | 셀렉터 또는 초 단위 |
| `done` | - | 태스크 완료 신호 |
| `ask_human` | - | 사용자 개입 요청 |

---

### 3.5 core/agent_loop.py — 에이전트 핵심 루프

**파일**: `src/core/agent_loop.py` (265줄)
**역할**: Observation → LLM → Action 루프를 실행하고 결과를 반환한다.

#### 데이터 클래스

```python
@dataclass
class StepLog:
    step: int                         # 스텝 번호
    timestamp: str                    # HH:MM:SS
    url: str                          # 현재 URL
    action: str                       # 실행한 액션명
    detail: str                       # 액션 결과 메시지
    success: bool                     # 성공 여부
    screenshot_b64: str | None = None # 스크린샷 (base64)

@dataclass
class AgentResult:
    success: bool                     # 태스크 성공 여부
    message: str                      # 결과 메시지
    steps: list[StepLog]              # 전체 스텝 로그
    data: Any = None                  # done/ask_human 결과 데이터
    total_steps: int = 0              # 총 스텝 수
    failure_count: int = 0            # 총 실패 횟수
```

#### run_agent_loop() 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `browser` | `BrowserManager` | (필수) | 이미 `start()` 호출된 브라우저 |
| `llm` | `BaseChatModel` | (필수) | LangChain LLM 인스턴스 |
| `goal` | `str` | (필수) | 수행할 태스크 |
| `direction` | `str \| None` | `None` | 경로 힌트 |
| `start_url` | `str \| None` | `None` | 시작 URL |
| `max_steps` | `int` | `MAX_STEPS` (50) | 최대 스텝 수 |
| `max_failures` | `int` | `MAX_FAILURES` (5) | 최대 연속 실패 |
| `on_step` | `StepCallback \| None` | `None` | 스텝 완료 콜백 (UI용) |

#### Stuck 감지

에이전트가 동일 액션을 반복하면서 진전이 없는 상태를 감지한다:

| 조건 | 임계값 | 동작 |
|---|---|---|
| 동일 액션 시그니처 N회 반복 + URL 변경 없음 | `STUCK_THRESHOLD = 3` | `is_stuck=True` → LLM에 경고 전달 |
| 동일 액션 시그니처 N회 반복 + URL 변경 없음 | `STUCK_ABORT_THRESHOLD = 6` | 자동 종료 (AgentResult.success=False) |

- **액션 시그니처**: `"{action}"` 또는 `"{action}:{index}"` (동일 요소 반복 클릭 등)
- URL이 변경되면 `recent_actions` 히스토리 리셋

#### 종료 조건

| 조건 | AgentResult.success |
|---|---|
| `action == "done"` | `True` |
| `action == "ask_human"` | `True` |
| `failure_count >= max_failures` | `False` |
| `step_num >= max_steps` | `False` |
| Stuck abort (6회 반복) | `False` |

---

### 3.6 llm/client.py — LLM 클라이언트

**파일**: `src/llm/client.py` (160줄)
**역할**: LangChain을 통해 다양한 LLM에 접근하는 단일 인터페이스를 제공한다.

#### create_llm(provider, model) → BaseChatModel

| 프로바이더 | 클래스 | 기본 모델 |
|---|---|---|
| `"openai"` | `ChatOpenAI` | `gpt-5-mini` |
| `"anthropic"` | `ChatAnthropic` | (설정에 따라) |

공통 설정: `max_tokens=1024`, `temperature=0`

#### invoke_llm() 파라미터

| 파라미터 | 설명 |
|---|---|
| `llm` | LangChain LLM 인스턴스 |
| `state_text` | `PageState.to_prompt_text()` 결과 |
| `task` | Goal 텍스트 |
| `direction_hint` | Direction 텍스트 (선택) |
| `step_history` | 이전 스텝 이력 (최근 10개) |
| `is_stuck` | Stuck 감지 시 True → 경고 메시지 추가 |

#### 시스템 프롬프트 (SYSTEM_PROMPT) 핵심 규칙

1. **반드시 JSON 형식**으로만 응답
2. **한 번에 하나의 액션**만 결정
3. **index는 제공된 요소 목록의 번호**를 정확히 사용
4. 태스크 완료 시 `done` 액션 사용
5. 확신 없으면 `ask_human` 사용
6. **팝업/모달/오버레이가 보이면 태스크 전에 먼저 제거**

#### Stuck 경고 시그널

`is_stuck=True`일 때 프롬프트에 추가:

```
⚠️ STUCK 경고
동일한 액션을 여러 번 반복하고 있습니다.
반드시 다른 접근법을 시도하세요.
```

---

### 3.7 server.py — FastAPI 서버

**파일**: `src/server.py` (230줄)
**역할**: UI와 에이전트를 연결하는 백엔드. 정적 HTML 서빙 + WebSocket 실시간 스트리밍.

#### 엔드포인트

| 경로 | 메서드 | 설명 |
|---|---|---|
| `/` | GET | `main.html` 서빙 (HTMLResponse) |
| `/ws` | WebSocket | 실시간 양방향 통신 |

#### 서버 시작

```bash
# 개발 모드 (reload 활성화)
python -m uvicorn src.server:app --host 0.0.0.0 --port 1234

# 또는 직접 실행
python src/server.py
```

**reload 설정**: `reload_dirs=["src"]`, `reload_excludes=["logs/*", "*.log", "__pycache__/*"]`

#### run_agent_task() 수명 주기

```
1. broadcast(status: "running")
2. BrowserManager() 생성
3. create_llm() → LLM 인스턴스
4. browser.start()
5. run_agent_loop(browser, llm, goal, direction, start_url, on_step)
6. broadcast(result: {success, message, total_steps, ...})
7. [CancelledError] → broadcast(status: "cancelled")
8. [Exception] → broadcast(error: message)
9. [finally] → browser.close() → broadcast(status: "idle")
```

#### 로깅

- 파일: `logs/agent_{YYYYMMDD_HHMMSS}.log`
- 콘솔: stderr
- 포맷: `%(asctime)s [%(name)s] %(levelname)s: %(message)s`
- 핸들러 직접 등록 (중복 방지)

---

### 3.8 main.html — 프론트엔드 UI

**파일**: `src/main.html` (427줄)
**역할**: WebSocket 기반 SPA. 태스크 입력 → 에이전트 실시간 모니터링.

#### 레이아웃

```
+-----------------------------+------------------------------------------+
|  좌측 사이드바 (w-80)       |  메인 콘텐츠                              |
|                             |                                          |
|  Task Control               |  Browser View (스크린샷 실시간 표시)      |
|  ├─ Goal (textarea)         |  ├─ 브라우저 헤더 (URL 표시)              |
|  ├─ Start URL (input)       |  └─ 스크린샷 / 대기 placeholder           |
|  ├─ Direction (textarea)    |                                          |
|  ├─ Context Assets          +------------------------------------------+
|  └─ [Execute Agent Task]    |  Agent Logic Stream (터미널)              |
|                             |  ├─ 타임스탬프 + 에이전트명 + 메시지      |
+-----------------------------+  └─ 런타임 카운터                         |
                              +------------------------------------------+
```

#### 기술 스택

- **CSS**: Tailwind CSS (CDN), Inter 폰트, Material Symbols
- **WebSocket**: 네이티브 `WebSocket` API
- **다크 모드**: `class="dark"` 기본 활성화

#### 에이전트 색상 매핑

| 에이전트 | 색상 | 용도 |
|---|---|---|
| System | slate | 시스템 메시지 |
| Scout | blue | (Phase 1-B) 정찰 에이전트 |
| Planner | purple | (Phase 1-B) 계획 에이전트 |
| Auth | emerald | (Phase 1-B) 인증 에이전트 |
| Executor | amber | 실행 스텝 로그 |
| Validator | cyan | (Phase 1-B) 검증 에이전트 |
| Observer | rose | (Phase 1-B) 관찰 에이전트 |

#### 상태 표시

| 상태 | 색상 | 의미 |
|---|---|---|
| `idle` | 초록 | Agent Online, 대기 중 |
| `running` | 주황 (ping 애니메이션) | 에이전트 실행 중 |
| `offline` | 빨강 | 서버 연결 끊김 |

#### WebSocket 재연결

연결 끊김 시 3초 후 자동 재연결 시도.

---

## 4. 데이터 흐름

### 전체 흐름 다이어그램

```
┌─────────┐  WebSocket   ┌──────────┐  create_llm()   ┌──────────┐
│  UI     │ ──────────── │ server.py│ ───────────────→ │ llm/     │
│ (HTML)  │  run/stop    │          │                  │ client.py│
└─────────┘              └──────────┘                  └──────────┘
     ↑                        │                             │
     │ step/result/status     │ run_agent_loop()            │ invoke_llm()
     │                        ↓                             ↓
     │                   ┌──────────────┐   get_indexed  ┌──────────┐
     │                   │ agent_loop.py│ ─────────────→ │ state.py │
     │                   │              │   state()      └──────────┘
     │                   │              │                      │
     │                   │              │   execute_action()   │
     │  broadcast()      │              │ ─────────────→ ┌──────────┐
     └───────────────────│              │                │actions.py│
                         └──────────────┘                └──────────┘
                              │                               │
                              │ browser.start/navigate/       │ page.locator()
                              │ screenshot/dismiss_overlays   │ page.fill()
                              ↓                               │ page.keyboard
                         ┌──────────────┐                     │ page.mouse
                         │ browser.py   │ ←───────────────────┘
                         │ (Playwright) │
                         └──────────────┘
```

### WebSocket 메시지 흐름

```
UI → Server:
  { type: "run",  goal: "...", start_url: "...", direction: "..." }
  { type: "stop" }

Server → UI:
  { type: "status",  status: "running" | "idle" | "cancelled", message }
  { type: "log",     agent: "System", message }
  { type: "step",    step, timestamp, url, action, detail, success, screenshot }
  { type: "result",  success, message, total_steps, failure_count, data }
  { type: "error",   message }
```

---

## 5. 지원 액션 목록

### 기본 액션 (6개)

| 액션 | 설명 | 필수 필드 | 선택 필드 |
|---|---|---|---|
| `click` | 요소 클릭 | `index` | `reason` |
| `input` | 텍스트 입력 (기존 내용 대체) | `index`, `text` | `reason` |
| `keys` | 키보드 입력 | `combo` | `reason` |
| `select` | 드롭다운 옵션 선택 | `index`, `option` | `reason` |
| `scroll` | 페이지 스크롤 | - | `direction` (기본: down), `amount` (기본: 500), `reason` |
| `navigate` | URL 직접 이동 | `url` | `reason` |

### 제어 액션 (4개)

| 액션 | 설명 | 필수 필드 | 효과 |
|---|---|---|---|
| `screenshot` | 현재 화면 캡처 | - | `data`에 base64 반환 |
| `wait` | 대기 | `amount`(초) 또는 `text`(셀렉터) | 시간 대기 또는 셀렉터 출현 대기 |
| `done` | 태스크 완료 선언 | `result` | 루프 종료 (success=True) |
| `ask_human` | 사용자 개입 요청 | `question` | 루프 종료 (success=True) |

### LLM 응답 형식

```json
{ "action": "click", "index": 5, "reason": "검색 버튼 클릭" }
{ "action": "input", "index": 3, "text": "검색어", "reason": "검색어 입력" }
{ "action": "scroll", "direction": "down", "amount": 500, "reason": "아래로 스크롤" }
{ "action": "keys", "combo": "Enter", "reason": "검색 실행" }
{ "action": "done", "result": "검색 결과 3건 확인 완료", "reason": "태스크 완료" }
```

---

## 6. WebSocket 프로토콜

### 클라이언트 → 서버

| type | 필드 | 설명 |
|---|---|---|
| `run` | `goal` (필수), `start_url`, `direction` | 에이전트 태스크 실행 |
| `stop` | - | 현재 태스크 취소 |

### 서버 → 클라이언트

| type | 필드 | 설명 |
|---|---|---|
| `status` | `status`, `message` | 상태 변경 알림 (running/idle/cancelled/stopped) |
| `log` | `agent`, `message` | 시스템 로그 메시지 |
| `step` | `step`, `timestamp`, `url`, `action`, `detail`, `success`, `screenshot` | 스텝 완료 알림 |
| `result` | `success`, `message`, `total_steps`, `failure_count`, `data` | 태스크 완료 결과 |
| `error` | `message` | 오류 알림 |

---

## 7. 환경 변수

`.env` 파일에 설정하며, `config.py`에서 `python-dotenv`로 로드한다.

| 변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `OPENAI_API_KEY` | ◯ (OpenAI 사용 시) | `""` | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | ◯ (Anthropic 사용 시) | `""` | Anthropic API 키 |
| `DEFAULT_LLM_PROVIDER` | | `"openai"` | `openai` 또는 `anthropic` |
| `DEFAULT_MODEL` | | `"gpt-5-mini"` | LLM 모델 ID |
| `HEADLESS` | | `true` | 브라우저 헤드리스 모드 |
| `BROWSER_TIMEOUT` | | `30000` | 브라우저 기본 타임아웃 (ms) |
| `MAX_STEPS` | | `50` | 에이전트 최대 스텝 수 |
| `MAX_FAILURES` | | `5` | 최대 연속 실패 허용 |
| `SERVER_HOST` | | `0.0.0.0` | 서버 바인드 주소 |
| `SERVER_PORT` | | `1234` | 서버 포트 |

---

## 8. Docker 배포

### Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.51.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
COPY src/ src/
EXPOSE 1234
ENV HEADLESS=true PYTHONUNBUFFERED=1
CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "1234"]
```

- **베이스 이미지**: Playwright 공식 Python 이미지 (Chromium + 시스템 의존성 내장)
- **레이어 캐싱**: `requirements.txt` → `pip install` → `src/` 순서
- **reload 비활성화**: 프로덕션 배포용

### docker-compose.yml

```yaml
services:
  agentic-browser:
    build: .
    ports:
      - "1234:1234"
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
    restart: unless-stopped
```

### 실행 명령

```bash
# 빌드 + 실행
docker compose up --build -d

# 로그 확인
docker compose logs -f

# 중지
docker compose down
```

---

## 9. 의존성

### Python 패키지 (requirements.txt)

| 패키지 | 버전 | 용도 |
|---|---|---|
| `playwright` | ≥1.49.0 | 브라우저 자동화 (Chromium) |
| `fastapi` | ≥0.104.0 | HTTP + WebSocket 서버 |
| `uvicorn[standard]` | ≥0.24.0 | ASGI 서버 |
| `websockets` | ≥12.0 | WebSocket 프로토콜 |
| `langchain` | ≥0.3.0 | LLM 프레임워크 |
| `langchain-openai` | ≥0.2.0 | OpenAI LLM 어댑터 |
| `langchain-anthropic` | ≥0.2.0 | Anthropic LLM 어댑터 |
| `langchain-core` | ≥0.3.0 | LangChain 핵심 (BaseChatModel, Messages) |
| `pydantic` | ≥2.5.0 | 데이터 검증 (FastAPI 의존) |
| `python-dotenv` | ≥1.0.0 | .env 파일 로드 |

### 프론트엔드 (CDN)

| 라이브러리 | 용도 |
|---|---|
| Tailwind CSS (CDN + forms/container-queries 플러그인) | 유틸리티 CSS |
| Inter 폰트 (Google Fonts) | 본문 타이포그래피 |
| Material Symbols Outlined (Google Fonts) | 아이콘 |

---

## 10. 관리 포인트 및 알려진 제한사항

### 관리 포인트

| # | 항목 | 위치 | 설명 | 우선순위 |
|---|---|---|---|---|
| 1 | **LLM API 키 관리** | `.env` | 키 노출 방지, 로테이션 정책 | 높음 |
| 2 | **dismiss_overlays 셀렉터** | `browser.py:87~112` | 사이트별 새로운 패턴 발견 시 추가 필요 | 중간 |
| 3 | **SYSTEM_PROMPT 튜닝** | `llm/client.py:21~58` | 에이전트 성능의 핵심. 액션 가이드/제약조건 변경 시 여기 수정 | 높음 |
| 4 | **Stuck 임계값** | `agent_loop.py:82~83` | `STUCK_THRESHOLD=3`, `STUCK_ABORT_THRESHOLD=6`. 태스크 유형에 따라 조정 필요 | 중간 |
| 5 | **스크린샷 품질** | `browser.py:59` | JPEG 60% 품질. 대역폭 vs 가독성 트레이드오프 | 낮음 |
| 6 | **step_history 크기** | `llm/client.py:128` | 최근 10스텝. 토큰 소비 vs 컨텍스트 품질 트레이드오프 | 중간 |
| 7 | **로그 파일 관리** | `server.py:27~29` | 매 실행마다 새 로그 파일 생성. 정리 정책 필요 | 낮음 |
| 8 | **`_EXTRACT_JS` SyntaxWarning** | `state.py:21` | `\s` 이스케이프 경고. `r"""..."""` raw string 사용 권장 | 낮음 |
| 9 | **모델 변경** | `config.py:19` | `DEFAULT_MODEL` 변경 시 토큰 한도·비용·응답 형식 확인 | 중간 |
| 10 | **Docker 이미지 크기** | `Dockerfile` | 현재 ~3.4GB (Playwright 이미지). multi-stage build로 최적화 가능 | 낮음 |

### 알려진 제한사항 (Phase 1-A)

| # | 제한사항 | 영향 | 해결 계획 |
|---|---|---|---|
| 1 | **단일 브라우저/페이지** | 탭 전환, 팝업 윈도우 처리 불가 | Phase 1-B: 멀티탭 지원 |
| 2 | **사람 → 에이전트 개입이 stop만 가능** | Pause/Resume, 지시 주입 불가 | Phase 1-B: 3가지 개입 모드 |
| 3 | **파일 다운로드/업로드 미지원** | 첨부 파일 조작 불가 | Phase 1-B: File Handling |
| 4 | **인증/로그인 수동** | 로그인 상태 유지 불가 | Phase 1-B: Auth Agent |
| 5 | **VLM 미도입** | 시각 정보 활용 불가 (텍스트만) | Phase 2: VLM A/B 테스트 |
| 6 | **패턴 학습 없음** | 매번 처음부터 탐색 | Phase 2: Pattern Compiler |
| 7 | **단일 태스크 실행** | 병렬/스케줄 실행 불가 | Phase 3: 스케줄러 + 분산 |
| 8 | **LLM 응답 검증 미흡** | JSON 형식 오류 시 `error` 액션 | Phase 1-B: JSON Schema 검증 + 재요청 |

---

## 11. 로드맵 (Phase 1-B 이후)

### Phase 1-B: Human-in-the-Loop + 서브에이전트 (1~2개월)

- Pause/Resume/Instruct 3가지 사람 개입 모드
- Observer 서브에이전트 (오버레이 감지, 상태 변화 모니터링)
- Auth Agent (로그인 자동화)
- LLM 응답 JSON Schema 검증 + 재요청
- 멀티탭 지원
- 파일 다운로드/업로드

### Phase 2: 자가학습 + VLM 실험 

- Pattern Compiler (성공 패턴 → 결정론적 코드)
- VLM A/B 테스트 (Accessibility Tree Only vs + Screenshot)
- Evaluation Harness (자동 테스트)
- Tiered Escalation (CDP → LLM → VLM → Human)
- 서브에이전트 병렬 실행

### Phase 3: 스케일 

- 스케줄러 (반복 크롤링 자동화)
- 분산 실행 (Celery/Ray)
- 계정 풀 관리
- 100만 페이지/월 목표


