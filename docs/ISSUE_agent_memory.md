# 에이전트 루프 문제 진단: 임무 완수 실패

> 작성일: 2026-03-03
> 최종 업데이트: 2026-03-05
> 대상 파일: `src/core/agent_loop.py`, `src/llm/client.py`, `src/core/actions.py`, `src/core/state.py`, `src/core/browser.py`, `src/server.py`, `src/main.html`

## 증상

사용자가 "한남동의 맛집 3곳을 네이버 블로그에서 찾아줘"와 같은 정보 수집형 태스크를 요청하면,
에이전트가 블로그에서 검색하고 페이지를 방문하는 **브라우저 조작까지는 수행**하지만,
**최종 결과를 도출하지 못하고** 종료된다.

---

## 핵심 문제 3가지

### 1. 페이지 간 정보 축적 불가 (가장 치명적)

**위치:** `agent_loop.py:182`

```python
step_history.append(f"Step {step_num}: {action.action} → {result.message}")
```

`step_history`에는 **액션 결과 요약만** 저장된다.
- 예: `"Step 5: click → [3] link '맛집 추천' 클릭 완료"`

에이전트가 블로그 게시물 A를 방문해서 맛집 정보를 확인한 뒤, 게시물 B로 이동하면
**A의 콘텐츠는 완전히 사라진다.**

LLM은 매 스텝마다 `현재 페이지 상태 + 액션 로그`만 받기 때문에,
이전에 방문한 페이지의 콘텐츠를 기억할 수 없다.

> **[해결됨]** `collected_info` 리스트 도입 + `memo` 선택적 필드로 페이지 간 정보 축적 가능. 아래 "구현 완료" 섹션 참조.

### 2. 정보 수집/저장 액션 부재

**위치:** `client.py:43-52`

사용 가능한 액션 목록:
```
click, input, keys, select, scroll, navigate, screenshot, wait, done, ask_human
```

`extract`나 `save_note` 같은 **정보를 수집·저장하는 액션이 없다.**
에이전트가 페이지에서 유용한 정보를 발견해도 이를 명시적으로 "메모"할 방법이 전혀 없다.

> **[해결됨]** 독립 액션 대신 `memo` 선택적 필드 방식 채택. 모든 액션에 `"memo": "..."` 필드를 추가할 수 있음. 아래 "구현 완료" 섹션 참조.

### 3. 시스템 프롬프트에 정보 수집 워크플로우 가이드 부재

**위치:** `client.py:21-58`

시스템 프롬프트는 **브라우저 조작 방법만** 설명하고,
"여러 페이지를 방문하며 정보를 모아 최종 결과를 도출하라"는 가이드가 없다.
LLM이 `done` 액션을 호출할 때 `result`에 무엇을 넣어야 하는지 명확하지 않다.

> **[해결됨]** 시스템 프롬프트에 "정보 수집 태스크 수행 가이드" 섹션 추가. 아래 "구현 완료" 섹션 참조.

---

## 부가 문제

| 문제 | 위치 | 설명 | 상태 |
|------|------|------|------|
| 페이지 텍스트 2000자 제한 | `state.py:232` | 블로그 글의 핵심 정보가 잘릴 수 있음 | **해결됨** — Accessibility Tree 도입 (4000자) |
| max_tokens=1024 | `client.py:83` | `done` 시 풍부한 결과 요약에 부족할 수 있음 | **해결됨** — 2048로 상향 |
| LLM 호출이 무상태(stateless) | `client.py:150-156` | 매번 새 메시지 리스트를 만들어 호출 — 이전 대화 맥락 없음 | **해결됨** — `collected_info`로 상태 유지 |
| ask_human 시 루프 종료 | `agent_loop.py` | 에이전트가 질문해도 사용자 응답 대기 없이 종료 | **해결됨** — 콜백 기반 대기 패턴 |
| 페이지 구조 정보 부재 | `state.py` | 네비/본문/사이드바가 뒤섞인 평면 텍스트 | **해결됨** — Accessibility Tree YAML 구조 |

---

## 구현 완료 (2026-03-03 ~ 03-04)

### A. memo 선택적 필드 + collected_info 메모리

#### 설계 결정: 독립 액션 vs 선택적 필드

| 방식 | 스텝 소비 | 구현 복잡도 |
|------|-----------|------------|
| memo를 독립 액션으로 | 메모당 1스텝 추가 | 낮음 |
| **memo를 선택적 필드로 (채택)** | **추가 소비 없음** | 낮음 |

#### 변경 파일

**`src/core/actions.py`** — `AgentAction`에 memo 필드 추가 (line 42)
```python
memo: str | None = None  # 선택적 메모: 현재 페이지에서 수집한 핵심 정보
```
`parse_action()`에서 `data.get("memo")` 파싱 추가 (line 133).

**`src/core/agent_loop.py`** — collected_info 누적 + LLM 전달
```python
collected_info: list[str] = []  # 에이전트 작업 메모리 (memo 필드 누적)

# 매 스텝에서:
if action.memo:
    collected_info.append(action.memo)

# LLM 호출 시:
llm_response = await invoke_llm(..., collected_info=collected_info)
```

**`src/llm/client.py`** — invoke_llm에 collected_info 파라미터 추가
```python
async def invoke_llm(..., collected_info: list[str] | None = None) -> str:
    # 수집된 정보 (memo 누적)
    if collected_info:
        info_text = "\n".join(f"- {info}" for info in collected_info)
        user_prompt_parts.append(f"\n## 수집된 정보 (이전 스텝에서 memo로 기록)\n{info_text}")
```

#### 동작 흐름
```
검색 → 블로그1 방문 → click(뒤로가기, memo="맛집A: 한남동 OO로, 평점 4.5")
     → 블로그2 방문 → click(뒤로가기, memo="맛집B: 한남동 XX길, 분위기 좋음")
     → 블로그3 방문 → done(result="한남동 맛집 3곳: 1. 맛집A... 2. 맛집B... 3. 맛집C...")
```

---

### B. Accessibility Tree 도입 (page_text 대체)

#### 문제 (agent_20260303_165941.log에서 확인)

memo 기능이 코드상 작동하지만, **LLM이 기사 본문을 읽을 수 없어** memo에 실제 데이터 대신 의도만 기록됨:

```
Step 7 memo: "기사 본문 하단의 상세 내용과 관련 링크·사진 캡션 등을 수집할 예정"  ← 계획만
Step 9 memo: "목표 기사 상세내용 수집 예정: 작성시간, 주요 내용..."              ← 또 계획
```

**인과 관계:**
```
page_text가 기사 본문을 포함하지 못함 (네비/광고에 2000자 소진)
  → LLM이 기사 내용을 읽을 수 없음
    → memo에 "수집하겠습니다" 같은 의도만 기록
      → collected_info에 실질적 정보 없음
        → 재방문 방지 불가 → 무한 루프
```

#### 해결: Playwright `locator.aria_snapshot()`

기존 `document.body.innerText` (2000자) 대신 Chrome Accessibility Tree의 YAML 표현 (4000자)을 사용.

**Before (innerText 2000자):**
```
한남동 맛집 TOP5 메뉴 홈 블로그 카페 뉴스 검색 로그인 ... 한남동에서 꼭 가봐야 할 맛집을 소개합니다 1. 파스타
```

**After (Accessibility Tree YAML):**
```yaml
- main:
  - heading "한남동 맛집 추천 TOP5" [level=1]
  - paragraph: 한남동에서 꼭 가봐야 할 맛집을 소개합니다...
  - heading "1. 파스타 전문점 OO" [level=2]
  - paragraph: 한남동 OO로에 위치한 이 가게는 평점 4.5...
```

#### 변경 파일

**`src/config.py`** — 상수 추가 (line 31)
```python
A11Y_TEXT_LIMIT = int(os.getenv("A11Y_TEXT_LIMIT", "4000"))
```

**`src/core/state.py`** — 핵심 변경 3곳

1. `_truncate_yaml()` 함수 추가 (line 240-253): YAML을 줄 단위로 안전하게 자름
2. `_get_aria_snapshot()` 함수 추가 (line 256-286): 3단계 폴백
   - 1차: `main` / `[role="main"]` / `article` 영역만 추출 (본문 집중)
   - 2차: `body` 전체 추출
   - 3차: 기존 `innerText` 폴백
3. `get_indexed_state()` 수정 (line 371): `page.evaluate(_PAGE_TEXT_JS)` → `_get_aria_snapshot(page, A11Y_TEXT_LIMIT)`
4. `to_prompt_text()` 라벨 변경 (line 342): `"페이지 텍스트 (요약)"` → `"페이지 콘텐츠 (Accessibility Tree)"`

#### 기존 코드와의 관계

| 항목 | 변경 여부 | 이유 |
|------|-----------|------|
| `_EXTRACT_JS` (인터랙티브 요소 추출) | 유지 | data-aidx 주입 + 클릭/입력에 필수 |
| `_PAGE_TEXT_JS` (innerText) | 유지 | `_get_aria_snapshot()` 최종 폴백으로 사용 |
| `IndexedElement` 데이터 클래스 | 유지 | 변경 불필요 |
| `PageState.page_text` 필드명 | 유지 | 필드명 유지, 내용만 a11y tree로 교체 |

#### 토큰 예산 영향

| 항목 | Before | After |
|------|--------|-------|
| page_text 최대 크기 | 2,000자 (~500 토큰) | 4,000자 (~1,000 토큰) |
| 스텝당 총 입력 토큰 (추정) | ~1,200 토큰 | ~1,700 토큰 |
| LLM 비용 증가 | - | ~40% (입력 부분만) |

환경변수 `A11Y_TEXT_LIMIT`으로 런타임에 조절 가능.

---

### C. 시스템 프롬프트 보강 (`src/llm/client.py`)

#### C-1. memo 품질 지시 강화 (line 59-63)
```
중요: memo에는 반드시 실제 데이터를 기록하세요.
- 좋은 memo: "맛집A: 한남동 OO로, 평점 4.5, 파스타 전문점, 1인당 2만원"
- 나쁜 memo: "맛집 정보를 수집하겠습니다", "상세 내용 확인 예정"
"~할 예정", "~하겠습니다" 같은 계획이나 의도는 memo가 아닙니다.
페이지에서 실제로 읽은 구체적인 정보(이름, 수치, 사실)만 기록하세요.
```

#### C-2. done 액션 결과 품질 강제 (line 51)
```
- done: 태스크 완료. 필드: result (결과 요약 텍스트).
  **중요**: result에 반드시 수집된 정보를 포함한 완성된 답변을 작성하세요. "태스크 완료"만 쓰지 마세요.
```

#### C-3. 정보 수집 가이드 강화 (line 71-84)
```
## 정보 수집 태스크 수행 가이드
1. 검색 또는 목록 페이지에서 관련 링크를 찾아 방문합니다.
2. 페이지 내용을 읽고, 태스크에 필요한 핵심 정보를 memo에 기록합니다.
3. 뒤로 가거나 다음 링크로 이동하여 추가 정보를 수집합니다.
4. 충분한 정보가 모이면 done 액션의 result에 수집된 정보를 종합하여 최종 답변을 작성합니다.
   - result에는 수집한 모든 정보를 구조화하여 포함하세요
   - "태스크 완료", "정보 수집 완료" 같은 빈 결과는 절대 금지입니다
   - "수집된 정보" 섹션의 memo 내용을 반드시 종합하여 result에 포함하세요
```

#### C-4. 재방문 방지 규칙 추가 (line 83-84)
```
중요: 이미 수집된 정보에 있는 내용과 동일한 링크/페이지를 다시 방문하지 마세요.
새로운 정보를 수집하기 위해 아직 방문하지 않은 링크를 선택하세요.
```

#### C-5. ask_human 사용 제한 (line 52, 91)
```
- ask_human: 사용자에게 질문. 필드: question. **주의**: 스스로 판단할 수 있는 것은 질문하지 마세요.
  정말 사용자만 결정할 수 있는 것만 물어보세요.

- ask_human은 최후의 수단입니다. "기간을 선택해주세요", "진행해도 될까요?" 같은
  불필요한 질문은 하지 마세요. 합리적인 판단으로 스스로 결정하고 진행하세요.
```

#### C-6. Accessibility Tree 팁 추가 (line 90)
```
- "페이지 콘텐츠"는 Accessibility Tree 구조로 제공됩니다.
  heading, paragraph, link 등 역할을 참고하여 페이지 내용을 이해하세요.
```

---

### D. ask_human 대기 패턴 (사용자 응답 후 재개)

#### 문제

에이전트가 `ask_human` 액션을 사용하면 루프가 즉시 종료되어 사용자가 응답할 방법이 없었음.

#### 해결: asyncio.Future 기반 대기 패턴

**`src/core/agent_loop.py`** — 콜백 기반 대기
```python
# 콜백 타입 정의
AskHumanCallback = Callable[[str], Awaitable[str]]

# run_agent_loop에 on_ask_human 파라미터 추가
async def run_agent_loop(..., on_ask_human: AskHumanCallback | None = None) -> AgentResult:

# ask_human 처리: 콜백이 있으면 대기 후 재개, 없으면 기존대로 종료
if action.action == "ask_human":
    if on_ask_human:
        human_response = await on_ask_human(question)
        step_history.append(f"Step {step_num}: ask_human → 사용자 응답: {human_response}")
        collected_info.append(f"사용자 지시: {human_response}")
        continue  # 루프 계속
    else:
        return AgentResult(...)  # 기존 동작: 루프 종료
```

**`src/server.py`** — WebSocket 기반 응답 수신
```python
# 모듈 레벨 변수
pending_human_future: asyncio.Future | None = None

# WebSocket에서 human_response 메시지 처리
elif msg_type == "human_response":
    if pending_human_future and not pending_human_future.done():
        pending_human_future.set_result(response_text)

# on_ask_human 콜백: 질문을 UI로 보내고 Future로 대기
async def on_ask_human(question: str) -> str:
    pending_human_future = asyncio.get_event_loop().create_future()
    await broadcast({"type": "ask_human", "question": question})
    response = await pending_human_future  # 사용자 응답까지 대기
    return response
```

**`src/main.html`** — UI 입력 박스 동적 생성
- `ask_human` 메시지 수신 시 `showHumanInput(question)` 호출
- Agent Logic Stream 영역 내부에 입력 박스 + 전송 버튼 생성
- 전송 시 `{ type: "human_response", response: "..." }` WebSocket 메시지 발송 후 입력 박스 제거
- 대기 상태(`waiting`) 시 실행 버튼 비활성화 + 파란색 표시 + ping 애니메이션

#### 동작 흐름
```
에이전트 ask_human 발동
  → server.py: broadcast(ask_human) + Future 생성
    → main.html: 입력 박스 표시, 버튼 비활성화
      → 사용자 텍스트 입력 후 전송
        → server.py: Future.set_result(응답)
          → agent_loop.py: 응답을 step_history + collected_info에 추가, 루프 재개
```

---

## 미해결 / 추가 개선 대상

### 1. 아이콘 전용 버튼 인식 불가

**증상:** 텍스트 라벨이 없는 아이콘 버튼(사람 모양 로그인 버튼, 돋보기 검색 버튼 등)을 LLM이 구분하지 못함.

**원인:** 요소 정보가 텍스트 기반이라 `[45] button: ""` 처럼 이름이 비어있음. 사람은 아이콘 모양으로 판단하지만 LLM은 텍스트만 볼 수 있음.

**가능한 개선 방향:**
- Accessibility Tree로 `aria-label`이 있는 사이트에서는 자동 개선됨
- 스크린샷 + 멀티모달 LLM (GPT-4V/Claude Vision) 활용 — 토큰 비용 대폭 증가
- CSS 클래스/ID 힌트(`login_btn`, `user-icon`)에서 의미 추론

### 2. 팝업/오버레이 문맥 오인식

**증상:** 호갱노노(hogangnono.com) 앱 설치 팝업의 전화번호 입력창에 로그인 정보를 입력하는 등, 팝업과 본문 요소를 혼동.

**원인:** 팝업 내부 요소와 본문 요소가 동일한 평면 리스트에 나열되어 LLM이 어느 요소가 팝업에 속하는지 구분 불가.

> **[해결됨]** "Interaction Scope" 도입 — 활성 모달 감지 시 모달 내부 요소만 LLM에 전달. 아래 "구현 완료" 섹션 E 참조.
> 단, 실전 테스트(호갱노노 재실행)는 미완료. 엣지 케이스(중첩 모달, iframe 내 모달, ARIA 미사용 팝업 등) 검증 필요.

### 3. dismiss_overlays() → resolve_blocker() 재설계

기존 3단계(셀렉터 클릭 → 텍스트 스캔 → DOM 제거)가 과도하게 공격적이었음.

> **[해결됨]** `dismiss_overlays()` → `resolve_blocker()` 재설계 — 4단계 검증형 처리(닫기 버튼 → Escape → backdrop 클릭 → DOM 제거)로 전환. 매 시도 후 모달 실제 소멸 검증. 아래 "구현 완료" 섹션 E 참조.
> 단, 실전 테스트 미완료. `_dismiss_cookie_banners()`로 분리한 쿠키 배너 처리가 기존 사이트들에서 정상 작동하는지 확인 필요.

---

## 참고: Stagehand와의 비교

### extract 방식

```
Stagehand:  페이지 → [별도 LLM 호출] → 구조화 데이터 반환  (비용 2배)
우리 방식:  페이지 → 에이전트가 page_text를 봄 → memo 필드 → 메모리에 누적  (추가 비용 없음)
```

### Accessibility Tree 활용

```
Stagehand:  observe() → [별도 LLM 호출로 관찰] → 액션 결정  (호출 2회)
우리 방식:  aria_snapshot() → LLM에 직접 전달 → 액션 결정  (호출 1회)
```

Stagehand가 `observe()` 내부에서 쓰는 핵심 기술(Chrome Accessibility Tree)만 가져와서,
LLM 추가 호출 없이 추출 품질을 개선하는 접근.

### 구조 비교 (get_indexed_state vs Accessibility Tree)

| 항목 | get_indexed_state (유지) | Accessibility Tree (추가) |
|------|-------------------------|--------------------------|
| 출처 | 커스텀 JS (DOM 파싱) | 브라우저 내장 (OS 접근성 API) |
| 구조 | 평면 리스트 | 계층 트리 (heading/paragraph/link) |
| 이름 | 자체 추출 (폴백 시 className) | 브라우저 계산 accessible name |
| 텍스트 | innerText 2000자 → **대체됨** | role별 의미 있는 텍스트 (4000자) |
| 요소 클릭 | data-aidx로 안정적 | 클릭에 사용하지 않음 |
| 역할 | 인터랙티브 요소 인덱싱 | 페이지 콘텐츠 이해 |

**결론:** 둘은 상호 보완 관계. `get_indexed_state`는 요소 조작용, Accessibility Tree는 페이지 이해용.

---

### E. Interaction Scope 도입 (2026-03-05)

#### 핵심 컨셉

모달/팝업이 활성화되면 **모달 내부 요소만** LLM에 전달하여, LLM이 팝업 뒤 요소를 클릭하는 실수 자체를 원천 차단.

기존 방식은 `[팝업]` 태그를 표시만 하고 전체 요소를 LLM에 전달했기 때문에, LLM이 태그를 무시하고 팝업 뒤 요소를 force click으로 관통하는 문제가 있었음.

| 대안 | 채택 여부 | 이유 |
|------|-----------|------|
| LLM에 `[팝업]` 태그만 표시 | ❌ 기존 방식 | LLM이 무시하고 뒤 요소 클릭 |
| dismiss_overlays() 패턴 보강 | ❌ | 모든 사이트의 모든 팝업 커버 불가 |
| 스크린샷 기반 멀티모달 | ❌ | 토큰 비용 폭증, 근본 해결 아님 |
| **모달 활성 시 요소 필터링 (채택)** | ✅ | LLM 입력 자체를 정확하게 → 잘못된 선택 불가 |

#### 변경 파일 요약

| 파일 | 변경량 | 역할 |
|------|--------|------|
| `src/core/state.py` | +185 | 모달 감지 + 요소 필터링 + PageState 확장 |
| `src/core/browser.py` | +284 | `resolve_blocker()` 재설계 + 쿠키 배너 분리 |
| `src/core/agent_loop.py` | +39 | resolve_blocker 통합 + blocked_by_modal 자동 재시도 |
| `src/core/actions.py` | +24 | force click 게이팅 (모달 밖 요소 차단) |
| `src/llm/client.py` | +1 | 시스템 프롬프트 규칙 7 추가 |

#### E-1. `state.py` — 모달 감지 + 요소 스코프 필터링

**`_EXTRACT_JS` 내부에 Phase 7-A 추가 (활성 모달 감지)**

감지 우선순위:
1. `<dialog open>` — 네이티브 HTML dialog
2. `[role="dialog"]` — ARIA dialog
3. `[role="alertdialog"]` — ARIA alert dialog
4. `[aria-modal="true"]` — ARIA modal 속성
5. **휴리스틱** — z-index ≥ 999 + fixed/absolute + 뷰포트 15% 이상 차지 + 내부에 인터랙티브 요소 있음

5단계 휴리스틱은 호갱노노처럼 ARIA 속성 없이 `<div>`로 팝업을 만드는 사이트를 위한 폴백.

```javascript
// 모달 감지 후 요소 필터링
if (activeModalRoot) {
    if (!activeModalRoot.contains(el)) continue;  // 모달 밖 요소 스킵
}
```

**반환 구조 변경:**
```javascript
// Before
return results;  // IndexedElement[]

// After
return { elements: results, activeModal: activeModalInfo };
// activeModalInfo: { detected: bool, name: string, selector: string }
```

**PageState 확장:**
```python
class PageState:
    ...
    active_modal: bool = False          # 활성 모달 존재 여부
    modal_description: str = ""         # 모달 이름/설명
```

**to_prompt_text() 분기:**
- 모달 활성 시: `"⚠️ 팝업이 활성화되어 있습니다: {name}"` + `"팝업 내 상호작용 가능 요소 (N개)"` 형식
- 모달 비활성 시: 기존 `"상호작용 가능 요소 (N개)"` 형식 유지

**_get_aria_snapshot() 확장:**
- `modal_selector` 파라미터 추가
- 모달 활성 시 모달 영역에서 a11y 스냅샷 추출 (main/article 대신)
- 모달 비활성 시 기존 main → body → innerText 폴백 유지

#### E-2. `browser.py` — resolve_blocker() 재설계

기존 `dismiss_overlays()` → `resolve_blocker()` + `_dismiss_cookie_banners()` 분리.

**resolve_blocker() 4단계 검증형 처리:**

```
활성 모달 감지 (_DETECT_MODAL_JS)
  → 1단계: 모달 내부 닫기 버튼 클릭 (aria-label/텍스트 매칭: 닫기/close/x/×/확인)
    → 검증: 모달 소멸 확인
  → 2단계: Escape 키
    → 검증: 모달 소멸 확인
  → 3단계: backdrop 클릭 (모달 외부 영역)
    → 검증: 모달 소멸 확인
  → 4단계: DOM 제거 (최후 수단, backdrop도 함께 제거)
    → 검증: 모달 소멸 확인
  → 전부 실패 시: had_blocker=True, resolved=False 반환
```

**반환 구조:**
```python
{
    'resolved': bool,        # 닫기 성공 여부
    'had_blocker': bool,      # 블로커 존재 여부
    'blocker_name': str,      # 블로커 이름
    'method': str,            # 사용된 방법 (close_button/escape/backdrop/dom_removal/none)
    'attempts': int,          # 시도 횟수
}
```

**_dismiss_cookie_banners() 분리:**
- 기존 `dismiss_overlays()`의 1단계(셀렉터 기반 쿠키 배너 제거)만 유지
- 2단계(텍스트 스캔), 3단계(DOM 제거) 삭제 — 오탐/부작용 제거
- `resolve_blocker()` 시작 시 먼저 실행

**dismiss_overlays() 하위 호환:**
```python
async def dismiss_overlays(self) -> int:
    """하위 호환용 래퍼"""
    result = await self.resolve_blocker()
    return 1 if result['resolved'] else 0
```

#### E-3. `actions.py` — force click 게이팅

모달이 활성화된 상태에서 모달 밖(main layer) 요소를 클릭/입력하려 하면 force click을 차단하고 `blocked_by_modal` 에러 반환.

```python
# click/input 액션 모두 동일 로직 적용
if state.active_modal and elem.layer == "main":
    return ActionResult(
        success=False,
        action="click",
        message='요소가 팝업에 가려져 클릭할 수 없습니다. 먼저 팝업을 닫아주세요.',
        error="blocked_by_modal",
    )
```

**기존 문제점:** 클릭 실패 → 무조건 force click → 팝업 뒤 요소 관통 → 상태 오염
**변경 후:** 클릭 실패 + 모달 밖 타겟 → `blocked_by_modal` 에러 → LLM이 팝업 우선 처리

#### E-4. `agent_loop.py` — resolve_blocker 통합

**시작 시:**
```python
# Before
dismissed = await browser.dismiss_overlays()

# After
blocker_result = await browser.resolve_blocker()
# 성공/실패 로깅 포함
```

**액션 실패 시 자동 재시도:**
```python
if result.error == "blocked_by_modal":
    blocker_result = await browser.resolve_blocker()
    if blocker_result['resolved']:
        # 실패 카운트 증가 없이 다음 스텝으로 (재시도 유도)
        continue
```

이로써 LLM이 팝업 뒤 요소를 클릭 → blocked_by_modal → 자동으로 resolve_blocker() 호출 → 성공 시 재시도하는 자동 복구 루프가 형성됨.

#### E-5. `client.py` — 시스템 프롬프트 규칙 7 추가

```
7. "⚠️ 팝업이 활성화되어 있습니다"라는 안내가 보이면, 아래 나열된 요소는 팝업 내부 요소입니다.
   이 상태에서는 반드시 팝업 내부 요소만 사용하세요.
   팝업 닫기가 필요하면 "닫기", "X", "확인" 등의 버튼을 클릭하세요.
```

#### 동작 흐름 (전체)

```
페이지 로드
  → resolve_blocker(): 쿠키 배너 제거 + 모달 닫기 시도
  → get_indexed_state():
      활성 모달 감지? ──Yes──→ 모달 내부 요소만 인덱싱 + a11y 모달에서 추출
                     └─No──→ 전체 요소 인덱싱 + a11y main/body에서 추출
  → LLM 호출:
      모달 활성? ──Yes──→ "⚠️ 팝업이 활성화" + 팝업 내 요소만 표시
               └─No──→ 기존 형식
  → 액션 실행:
      클릭 실패 + 모달 밖 타겟? ──Yes──→ blocked_by_modal 반환
                              └─No──→ force click 허용
  → blocked_by_modal 발생 시:
      resolve_blocker() 자동 호출 → 성공 시 다음 스텝에서 재시도
```

#### 미검증 사항 / 잠재 리스크

| 항목 | 상태 | 설명 |
|------|------|------|
| 호갱노노 실전 테스트 | ❌ 미실행 | Interaction Scope 적용 후 로그인 시나리오 재테스트 필요 |
| 중첩 모달 | ⚠️ 부분 대응 | 최상위 z-index 모달만 스코프 — 중첩 2단계 이상 미검증 |
| iframe 내 모달 | ❌ 미대응 | 호갱노노 광고 팝업이 iframe 포함 — 프레임별 처리 미구현 |
| ARIA 미사용 사이트 | ⚠️ 휴리스틱 의존 | z-index + fixed + 면적 기반 감지 — 오탐/미탐 가능 |
| 닫을 수 없는 모달 | ⚠️ 부분 대응 | resolve_blocker 4단계 모두 실패 시 모달 내부에서 작업 유도 |
| 미명명 요소 필터링 강화 | ⚠️ 부작용 가능 | `isFallbackName && !isNative` 조건 완화로 cursor:pointer div도 제거 — 일부 사이트에서 클릭 가능 요소 누락 가능 |
| _dismiss_cookie_banners 축소 | ⚠️ 확인 필요 | 기존 2·3단계 제거 — 셀렉터에 안 잡히는 쿠키 배너가 남을 수 있음 |

---

### Section F: Obstruction-Based Architecture (2026-03-06)

#### 문제 분석

Section E의 Interaction Scope 구현 후에도 동일한 실패 체인이 반복됨:

1. resolve_blocker()가 "게이트웨이 광고" 팝업을 DOM 제거로 성공적으로 처리
2. BUT 하단 앱 설치 배너("호갱노노의 강력한 기능을...")가 지속 — z-index < 999이라 _DETECT_MODAL_JS 미감지
3. 배너가 "로그인" 버튼을 물리적으로 가림 → 일반 클릭 실패 → force click 발동
4. force click이 React 이벤트 핸들러를 제대로 트리거하지 못함 → 로그인 모달 미오픈
5. 페이지 상태 동일(121개 요소, 모두 layer='main') → LLM이 로그인 폼 진입을 환각
6. 검색 박스에 전화번호 입력 + ask_human 남발

**핵심 인사이트**: 문제는 Interaction Scope 이전 단계에서 발생. 로그인 모달이 열리지 않으면 Interaction Scope가 활성화될 수 없음.

#### 근본 원인

| 원인 | 설명 |
|------|------|
| 모달 전용 감지 | _DETECT_MODAL_JS가 dialog/role=dialog/z-index>=999만 감지. sticky footer 배너는 미감지 |
| force click 의존 | 일반 클릭 실패 시 바로 force:true 시도. force click은 Playwright actionability 우회하지만 React 이벤트 체인을 제대로 트리거 못함 |
| 상태 변경 미검증 | 클릭 후 페이지가 실제로 변했는지 확인 안 함. LLM이 변화 없는 페이지에서 환각 |

#### 아키텍처 변경: Obstruction-Based Detection

Oracle 분석 결과를 기반으로 "모달 감지"에서 "차단 요소 감지"로 패러다임 전환:

##### 1. Pre-click Obstruction Check (browser.py)

```
새 JS: _CHECK_OBSTRUCTION_JS
- elementFromPoint()로 클릭 대상의 3개 지점 확인
- 대상이 아닌 다른 요소가 최상위에 있으면 obstructed=true 반환
- 차단 요소의 selector, tag, text, position, zIndex, rect 수집
```

##### 2. Obstruction Resolver (browser.py)

```
새 메서드: resolve_obstruction(obstruction)
4단계 해소:
1. 차단 요소 내 닫기 버튼 클릭
2. CSS display:none (fixed/sticky 요소에만)
3. 스크롤하여 대상을 차단 영역 밖으로 이동
4. DOM 제거 (최후 수단)
```

##### 3. 5-Phase Click Strategy (actions.py)

```
Phase 1: 모달 스코프 검사 (기존 blocked_by_modal 로직 유지)
Phase 2: elementFromPoint 차단 검사 → 자동 해소 시도
Phase 3: scrollIntoView + 일반 클릭
Phase 4: dispatchEvent 폴백 (mouseenter→mouseover→mousedown→mouseup→click 체인)
Phase 5: force click (최후 수단)
```

##### 4. Post-action State Fingerprint (agent_loop.py + browser.py)

```
새 JS: _STATE_FINGERPRINT_JS
- URL, title, has_modal, focus_tag, focus_id, interactive_count 캡처
- 클릭/입력 전후로 비교하여 변경 감지
- 연속 2회 이상 미변경 시 LLM에 경고 전달
```

##### 5. No-State-Change LLM Policy (client.py + agent_loop.py)

```
- no_change_count >= 2일 때 LLM에 경고 삽입:
  "⚠️ 상태 미변경 경고: 직전 액션이 페이지에 아무 변화를 일으키지 못했습니다"
  "절대로 양식 입력(input)을 시도하지 마세요 — 양식이 열리지 않았습니다"
- 시스템 프롬프트 규칙 8 추가: 상태 미변경 시 환각 방지 지시
```

#### 코드 변경 내역

| 파일 | 변경 | 라인 수 |
|------|------|---------|
| src/core/browser.py | +_CHECK_OBSTRUCTION_JS, +_STATE_FINGERPRINT_JS, +check_obstruction(), +get_state_fingerprint(), +resolve_obstruction() | +214 |
| src/core/actions.py | click/input 케이스를 5-phase 전략으로 교체, +asyncio import, +BrowserManager import | +65 |
| src/core/agent_loop.py | +prev_fingerprint/no_change_count 변수, +pre/post 핑거프린트 비교, +no_state_change_warning LLM 전달, execute_action에 browser= 전달 | +69 |
| src/llm/client.py | +시스템 프롬프트 규칙 8, +no_state_change_warning 파라미터, LLM 프롬프트에 경고 삽입 | +10 |

#### 기대 효과 (hogangnono 시나리오)

```
기존 흐름:
1. 배너 미감지 → 클릭 실패 → force click → 모달 미오픈 → 환각

새 흐름:
1. 로그인 버튼 클릭 시도
2. Phase 2: elementFromPoint가 하단 배너를 차단 요소로 감지
3. resolve_obstruction()이 배너를 CSS hide (display:none)
4. Phase 3: 일반 클릭 성공 → 로그인 모달 오픈
5. Interaction Scope 활성화 → 모달 내부 요소만 표시
6. LLM이 모달 내 전화번호/비밀번호 필드에 정확히 입력
```

#### 미검증 사항 / 잠재 리스크

| 항목 | 상태 | 설명 |
|------|------|------|
| 호갱노노 실전 테스트 | ❌ 미실행 | Obstruction Architecture 적용 후 로그인 시나리오 재테스트 필요 |
| dispatchEvent React 호환성 | ⚠️ 이론적 | MouseEvent 체인이 모든 React 버전에서 동작하는지 미검증 |
| CSS hide 부작용 | ⚠️ 확인 필요 | display:none이 React/Vue 상태에 영향줄 수 있음 (DOM 제거보다 안전하지만) |
| 핑거프린트 오탐 | ⚠️ 가능 | interactive_count 변화 임계값(>3)이 너무 관대/엄격할 수 있음 |
| elementFromPoint 정확도 | ⚠️ 확인 필요 | iframe, shadow DOM 내부 요소에서는 정확하지 않을 수 있음 |

---

### Section G: `asyncio` 변수 스코핑 버그 — click/input 액션 실행 실패 (2026-03-06)

#### 현상

Section F의 Obstruction Architecture 적용 후 실전 테스트(agent_20260306_011254.log)에서:
- 차단 감지 + 해소까지는 성공하지만, 직후 `await asyncio.sleep(0.3)` 호출 시 에러 발생
- 에러 메시지: `cannot access local variable 'asyncio' where it is not associated with a value`
- click 액션: Step 1에서 실패 → Step 2에서 차단이 이미 제거되어 sleep 경로 미도달 → 우연히 성공
- input 액션: Step 3~7에서 매번 차단 해소 → sleep 경로 → **5회 연속 실패**

```
Step 1: click [119] → 차단 해소(css_hide) → asyncio.sleep → ❌ UnboundLocalError
Step 2: click [119] → 차단 없음 (sleep 안 탐) → ✅ 로그인 모달 열림
Step 3: input [117] → 차단 해소 → asyncio.sleep → ❌ UnboundLocalError
Step 4: input [117] → 차단 해소 → asyncio.sleep → ❌ UnboundLocalError
Step 5~7: 동일 패턴 반복 → ❌ ❌ ❌
```

#### 근본 원인

`actions.py`의 `execute_action()` 함수 내부 Python 변수 스코핑 문제:

```python
# actions.py
import asyncio                          # line 12: 모듈 레벨 ✅

async def execute_action(...):
    match action.action:
        case "click":
            await asyncio.sleep(0.3)    # line 215: 모듈 레벨 참조 기대 → ❌ 로컬로 취급됨
        case "input":
            await asyncio.sleep(0.3)    # line 290: 동일 문제 → ❌
        case "wait":
            import asyncio               # line 366: ❌ 이게 함수 전체 오염
            await asyncio.sleep(seconds)
```

Python은 함수 컴파일 시 `import asyncio`(line 366)를 함수 전체의 로컬 변수 할당으로 인식한다.
`match/case`는 별도 스코프가 아닌 동일 함수 스코프이므로, `case "click"`이나 `case "input"`에서
`asyncio`를 참조할 때 아직 할당되지 않은 로컬 변수에 접근하여 `UnboundLocalError` 발생.

#### 해결

`case "wait":` 내부의 중복 `import asyncio` (line 366) **1줄 삭제**.
모듈 레벨 import (line 12)로 충분.

```diff
 # actions.py
             case "wait":
-                import asyncio
                 if action.text:
```

#### 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/core/actions.py` | `case "wait":` 내부의 `import asyncio` 1줄 삭제 |

#### 잠재 리스크 / 추가 검토

| 항목 | 상태 | 설명 |
|------|------|------|
| `import base64` (line 355, `case "screenshot"`) | ⚠️ 잠재 | 동일 패턴이나 다른 case에서 base64 미참조로 현재는 무해. 향후 참조 추가 시 동일 버그 발생 가능 |
| 실전 로그인 테스트 | ❌ 미실행 | 수정 후 input 액션이 정상 동작하는지 hogangnono.com 재테스트 필요 |



### 이제까지 시도들에 대한 평가
검토 결과
근본 해결이 잘 된 부분
Section A (memo/collected_info) — 근본적 해결 맞습니다. 무상태 LLM 호출에 크로스-페이지 메모리를 추가한 것은 정확한 접근입니다. 코드에서도 agent_loop.py에서 누적, client.py에서 매 스텝 LLM에 전달까지 확인됩니다.

Section B (Accessibility Tree) — 근본적 해결 맞습니다. innerText가 네비/광고에 2000자를 소진하는 문제를 aria_snapshot()의 구조화된 YAML로 대체한 것은 올바릅니다. main/article 우선 추출 → body 폴백 → innerText 폴백 3단계도 적절합니다.

Section G (asyncio 스코핑 버그) — 근본적 해결 맞습니다. Python의 함수-레벨 스코핑 문제를 정확히 진단하고 1줄 삭제로 해결했습니다.

근본 해결이 불완전한 부분
1. prev_url 비교 버그 — 문서에 미기록, stuck detection이 사실상 작동하지 않음
agent_loop.py 에서:


# line 165: 스텝 시작 시 prev_url을 현재 URL로 설정
prev_url = state.url

# ... (액션 실행) ...

# line 324: 성공 후 URL 변경 체크
if state.url != prev_url:   # ← 항상 False!
    recent_actions.clear()
prev_url이 이미 현재 state.url로 덮어쓰여진 뒤에 비교하므로 항상 False입니다. recent_actions.clear()가 절대 실행되지 않아, 다른 URL로 이동해도 이전 URL에서의 반복 액션 기록이 남습니다. 이는 오탐 stuck abort를 유발할 수 있습니다.

수정: prev_url 갱신을 스텝 끝으로 이동하거나, 비교 시 get_indexed_state() 이전에 저장해둔 값을 사용해야 합니다.

2. 핑거프린트의 has_modal 불일치
_STATE_FINGERPRINT_JS는 dialog[open], [role="dialog"] 등 시맨틱 셀렉터만 사용하지만, _EXTRACT_JS의 모달 감지(Phase 7-A)는 z-index ≥ 999 휴리스틱도 사용합니다. 호갱노노처럼 ARIA 없이 <div>로 팝업을 만드는 사이트에서:

_EXTRACT_JS: 모달 감지 → 요소 필터링 작동
_STATE_FINGERPRINT_JS: has_modal = false → 상태 변경 미감지 → no-change 경고 오발
이는 Section F의 상태 핑거프린트가 Section E의 모달 감지와 일관성이 없는 문제입니다.

3. Section E/F의 실전 미검증 — 근본 해결 여부를 판단할 수 없음
문서에도 명시되어 있지만, Section E(Interaction Scope)와 Section F(Obstruction Architecture)는 실전 테스트 없이 이론적으로만 설계되었습니다. logs/ 디렉토리가 비어있고, test_obstruction.py도 실행 기록이 없습니다. 특히 Section F는 Section E 적용 후에도 실패한 시나리오에 대한 추가 대응인데, F까지 적용 후 호갱노노 재테스트가 없으면 해결 여부를 확인할 수 없습니다.

4. collected_info가 UI에 전달되지 않음
server.py의 결과 브로드캐스트에서 collected_info가 빠져있습니다:


# server.py lines 219-227
await broadcast({
    "type": "result",
    "success": result.success,
    "message": result.message,
    # collected_info 없음!
})
에이전트가 memo를 열심히 수집해도 사용자에게는 result.message만 전달됩니다. done 액션의 result 필드에 모든 수집 정보를 종합하라는 프롬프트 지시에 의존하고 있는데, LLM이 이를 충실히 따르지 않으면 수집 정보가 유실됩니다.

5. import base64 잠재 버그 — 문서에 기록되어 있지만 미수정
Section G에서 import asyncio 패턴을 수정하면서 동일 패턴인 import base64(actions.py line 355, case "screenshot" 내부)를 수정하지 않았습니다. 문서에도 "잠재"로 표시만 해뒀는데, 향후 다른 case에서 base64를 참조하면 동일 UnboundLocalError가 재발합니다. 발견 시 바로 수정하는 것이 맞습니다.

설계 수준의 우려
근본적 질문: "LLM 프롬프트 지시에 대한 과도한 의존"
현재 해결책 다수가 시스템 프롬프트에 행동 규칙을 추가하는 방식입니다:

프롬프트 규칙	의존하는 LLM 행동
memo에 실제 데이터만 기록하라	LLM이 의도 vs 데이터를 구분
done에 완성된 답변을 작성하라	LLM이 수집 정보를 빠짐없이 종합
이미 방문한 링크를 재방문하지 마라	LLM이 collected_info를 대조
상태 미변경 시 같은 액션 반복하지 마라	LLM이 경고를 준수
팝업 내부 요소만 사용하라	LLM이 팝업 안내를 준수
ask_human을 남발하지 마라	LLM이 자율 판단
이것들은 코드 수준 안전장치 없이 LLM 준수에 의존합니다. 실제 로그(Section B에 인용된 agent_20260303_165941.log)에서 이미 LLM이 프롬프트 규칙을 무시하고 "수집 예정" 같은 계획만 memo에 기록한 사례가 확인됩니다.

반면 Section E(모달 시 요소 필터링)와 Section F(obstruction 차단)는 코드 수준에서 잘못된 행동 자체를 불가능하게 만드는 접근으로, 이것이 더 근본적입니다. 가능한 한 프롬프트 규칙은 코드 수준 강제로 대체하는 것이 좋습니다. 예를 들어:

memo 검증: memo 내용에 "예정", "하겠습니다" 등 의도 표현이 포함되면 코드에서 거부하고 LLM에 재작성 요청
done 결과 검증: collected_info가 있는데 result가 짧으면(예: 50자 미만) 코드에서 거부
asyncio.get_event_loop() 사용 (server.py line 188)
Python 3.10+에서 deprecated입니다. asyncio.get_running_loop().create_future()로 교체해야 합니다.

요약
영역	근본적 해결?	비고
A. memo/collected_info	예	핵심 아키텍처 잘 설계됨
B. Accessibility Tree	예	innerText 한계를 정확히 해결
C. 시스템 프롬프트	부분적	LLM 준수에 의존, 코드 강제 보완 필요
D. ask_human 대기	예	Future 패턴 적절
E. Interaction Scope	설계 적절, 미검증	실전 테스트 필수
F. Obstruction Architecture	설계 적절, 미검증	실전 테스트 필수
G. asyncio 버그	예	import base64 동일 패턴 잔존
prev_url 버그	문서 미기록	stuck detection 무력화
핑거프린트 has_modal 불일치	문서 미기록	휴리스틱 모달 변경 미감지
전반적으로 문제 진단 능력과 해결 방향은 정확합니다. 다만 실전 테스트 부재, prev_url 비교 버그, 핑거프린트 불일치, 프롬프트 의존 과다가 근본 해결을 위해 추가로 다뤄져야 할 부분입니다.