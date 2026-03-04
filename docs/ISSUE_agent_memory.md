# 에이전트 루프 문제 진단: 임무 완수 실패

> 작성일: 2026-03-03
> 최종 업데이트: 2026-03-04
> 대상 파일: `src/core/agent_loop.py`, `src/llm/client.py`, `src/core/actions.py`, `src/core/state.py`, `src/server.py`, `src/main.html`

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

**가능한 개선 방향:**
- Accessibility Tree의 `dialog` 역할이 팝업 컨텍스트를 제공할 수 있음
- `get_indexed_state`에서 팝업/오버레이 요소를 별도 그룹으로 표시
- `z-index` / `position: fixed` 기반 레이어 분리

### 3. dismiss_overlays() 경량화

현재 3단계(셀렉터 클릭 → 텍스트 스캔 → DOM 제거)가 과도하게 공격적.

**제안:**
- 1단계(셀렉터 클릭)에서 확실한 패턴만 유지
- 2단계(텍스트 스캔), 3단계(DOM 제거) 제거 — 오탐/부작용 위험
- 나머지는 에이전트 AI가 상황 판단해서 처리

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
