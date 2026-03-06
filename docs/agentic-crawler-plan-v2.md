# Agentic Browser v2 - 수정 계획서

> **날짜**: 2026-02-23
> **이전 문서**: agentic-crawler-brainstorming.md (2026-02-19)
> **변경 사유**: Bowser, Anchor Browser, Browser-use 등 유사 프로젝트 조사 결과 반영 + 구체적 워크플로우 설계
> **범위 변경**: 데이터 수집 전용 → **범용 브라우저 자동화 에이전트** (데이터 수집은 하위 유스케이스)

---

## 목차

- [I. 방향 전환 요약](#i-방향-전환-요약)
- [II. UI/UX 설계](#ii-uiux-설계)
- [III. 기술 스택](#iii-기술-스택)
- [IV. 에이전트 워크플로우](#iv-에이전트-워크플로우)
- [V. 계층 아키텍처 (Bowser 참고)](#v-계층-아키텍처-bowser-참고)
- [VI. 브라우저 상호작용 패턴 (Browser-use 차용)](#vi-브라우저-상호작용-패턴-browser-use-차용)
- [VII. 이전 계획에서 유지하는 것](#vii-이전-계획에서-유지하는-것)
- [VIII. 이전 계획에서 변경/보류하는 것](#viii-이전-계획에서-변경보류하는-것)
- [IX. 실행 로드맵](#ix-실행-로드맵)

---

## I. 방향 전환 요약

### 이전 계획의 핵심 (v1)

```
다계층 + API-First 사고
→ Structured Data First → Hidden API → DOM → CDP Diagnostics → VLM+LLM Dual
→ 대규모 (100만 페이지/월), 장기 운영 (6개월+), 완전 자율
```

### 변경된 방향 (v2)

```
1. 범용 브라우저 자동화: 데이터 수집뿐 아니라 모든 웹 기반 태스크 수행
2. PoC 우선: 대규모 아키텍처 전에 동작하는 프로토타입부터
3. UI 추가: Anchor처럼 브라우저 시각화 + 로그 + 개입 포인트 가시화
4. Browser-use 패턴 차용: accessibility tree → LLM → action 루프
5. 추후 VLM 도입 : 초기에는 아키텍처에 포함하지 않고 실험을 거쳐 도입 예정
6. 구조화된 입력: Goal(목표) + Direction(경로 힌트) + Context(부가 정보) 3-field 입력
7. 사용자 중심 워크플로우: 자연어 입력 → 에이전트 자율 실행
```

### 핵심 사고 전환

```
v1: "어떻게 100만 페이지를 자율적으로 크롤링할까?"
v2: "사용자가 Goal + Direction을 입력하면 에이전트가 브라우저에서 알아서 수행하는 시스템"

→ Goal = 무엇을 달성할 것인가 (필수)
→ Direction = 대략 어떤 경로로 (선택 — 있으면 빠르고 정확, 없으면 자율 탐색)
→ Context = 로그인 정보, 파일, 제약조건 등 부가 정보 (선택)
→ 데이터 수집은 여러 태스크 유형 중 하나
→ 폼 작성, 주문, 모니터링, 리서치 등 모든 웹 작업 포괄
→ 단일 태스크 완료가 먼저, 자동화/스케일은 그 다음
```

### 지원하는 태스크 유형

| 유형 | 예시 |
|---|---|
| **데이터 수집** | "호갱노노에서 강남구 아파트 리뷰 수집" |
| **폼 작성/제출** | "이 지원서 양식을 내 이력서 기반으로 작성해줘" |
| **네비게이션/조작** | "네이버 카페에서 새 글 작성하고 이미지 첨부해줘" |
| **모니터링** | "이 상품 가격이 10만원 이하로 떨어지면 알려줘" |
| **리서치** | "이 3개 사이트에서 동일 제품 가격 비교해줘" |
| **트랜잭션** | "이 항공편 예약 진행해줘 (결제 전 확인)" |
| **반복 작업** | "매일 출근 전에 이 사이트에서 출석체크 해줘" |

---

## II. UI/UX 설계

### 레이아웃 (Anchor Browser 참고)

```
+------------------------------------------------------------------+
|                        Agentic Browser                            |
+-----------------------------+------------------------------------+
|                             |                                    |
|  [Task Input]               |                                    |
|                             |        Browser View               |
|  Goal (필수):               |        (실시간 브라우저 화면)       |
|  +------------------------+ |                                    |
|  | 호갱노노에서 강남구     | |                                    |
|  | 아파트 리뷰 전체 수집   | |                                    |
|  +------------------------+ |                                    |
|                             |                                    |
|  Direction (선택):          |                                    |
|  +------------------------+ |                                    |
|  | 로그인 → 검색창에       | |                                    |
|  | 아파트명 입력 → 리뷰 탭 | |                                    |
|  | → 스크롤 다운하며 수집  | |                                    |
|  +------------------------+ |                                    |
|                             |                                    |
|  Context (선택):            |                                    |
|  +------------------------+ |                                    |
|  | 📎 apt_ids.csv         | |                                    |
|  | 🔑 로그인 정보 저장됨   | |                                    |
|  +------------------------+ |                                    |
|  [실행]                     |                                    |
|                             |                                    |
+-----------------------------+                                    |
|                             |                                    |
|  Agent Log                  |                                    |
|  (에이전트 판단/행동 로그)   |                                    |
|                             |                                    |
|  > Scout: 사이트 분석 중... |                                    |
|  > Scout: Hidden API 발견   |                                    |
|  > Planner: Goal 분석 완료  |                                    |
|  > Planner: Direction 기반  |                                    |
|    4단계 계획 수립           |                                    |
|  > Planner: 체크포인트 1개  |  ← 되돌릴 수 없는 액션 전          |
|  > Auth: Context에서 인증   |                                    |
|    정보 로드 → 로그인 성공   |                                    |
|  > Executor: Direction 힌트 |                                    |
|    따라 네비게이션 중        |                                    |
|  > [확인] 게시 전 미리보기  |  ← 체크포인트 하이라이트           |
|  > [!] 개입 필요: CAPTCHA   |  ← 에러 하이라이트                |
|                             |                                    |
+-----------------------------+------------------------------------+
|  Session History  |  세션 자동 저장/녹화  |  데이터 미리보기     |
+------------------------------------------------------------------+
```

### 핵심 UI 원칙

1. **Goal/Direction/Context 분리 입력**: 목적, 경로 힌트, 부가 정보를 구조화하여 입력
2. **Direction은 선택적**: 비워두면 에이전트가 자율 탐색, 채우면 빠르고 정확
3. **브라우저 실시간 표시**: 에이전트가 무엇을 보고 있는지 사용자도 볼 수 있음
4. **개입 포인트 명시**: CAPTCHA, 로그인 실패 등 사람이 필요한 순간을 하이라이트
5. **세션 자동 녹화**: 모든 세션은 Playwright Tracing으로 자동 저장
6. **결과 미리보기**: 수집된 데이터 또는 액션 결과를 실시간으로 확인

---

## III. 기술 스택

### 확정

| 구성요소 | 기술 | 이유 |
|---|---|---|
| 브라우저 엔진 | **Playwright (Python)** | CDP 접근, headless/headed 전환, tracing 내장 |
| LLM 인터페이스 | **LangChain** | 모델 교체 자유 (Claude, GPT-4o, Gemini, 로컬) |
| 기본 LLM | **Claude claude-sonnet-4-6 / GPT-4o** | 한국어 지원, multimodal 내장 |
| 세션 관리 | **Playwright storageState** | 인증 상태 저장/공유 |
| 세션 녹화 | **Playwright Tracing** | 스크린샷 + 네트워크 + DOM 타임라인 |
| 패턴 저장 | **SQLite** | 경량, 로컬 우선 |

### 검토 중

| 구성요소 | 후보 | 결정 시점 |
|---|---|---|
| UI 프레임워크 | Streamlit / Gradio / 커스텀 웹앱 | Phase 1 |
| VLM | Claude claude-sonnet-4-6 (multimodal) / GPT-4o vision | Phase 2 (실험 후 결정) |
| 분산 실행 | Celery / Ray | Phase 3 (스케일 필요 시) |

---

## IV. 에이전트 워크플로우

### 설계 원칙

```
이 시스템은 "데이터 수집기"가 아니라 "범용 브라우저 자동화 에이전트"다.
사용자가 자연어로 입력한 어떤 웹 작업이든 에이전트가 자율적으로 수행한다.

핵심: Planner가 태스크를 분석 → 태스크 유형에 맞는 실행 전략 결정
```

### 태스크 입력 구조 (Goal + Direction + Context)

사용자의 태스크 입력을 3개 필드로 구조화한다.
"무엇을 할 것인가"와 "어떻게 접근할 것인가"를 분리하여, 에이전트가 더 정확하고 효율적으로 태스크를 수행할 수 있게 한다.

#### 입력 필드 정의

| 필드 | 필수 | 설명 | 사용 에이전트 |
|---|---|---|---|
| **Goal** (목표) | 필수 | 최종적으로 달성해야 할 결과 | Planner → 전략 수립, Validator → 완료 판정 |
| **Direction** (방향) | 선택 | 목표에 도달하기 위한 대략적 경로 힌트 | Planner → 계획 참고, Executor → 네비게이션 가이드 |
| **Context** (맥락) | 선택 | 로그인 정보, 첨부 파일, 제약조건 등 | Auth → 인증 처리, Executor → 데이터 활용 |

#### 각 필드의 역할

```
Goal (필수) — "무엇을"
├─ 에이전트가 태스크 완료를 판단하는 기준
├─ Planner가 전략을 세울 때 최우선 참조
├─ Validator가 "이 결과가 맞는가?" 검증할 때 사용
└─ 예: "강남구 아파트 리뷰 500건 수집"

Direction (선택) — "대략 어떻게"
├─ 경로 힌트이지, 명령이 아님 (에이전트가 더 나은 경로를 찾으면 무시 가능)
├─ 있으면: Planner가 계획 시 참고 → Executor가 네비게이션에 활용
├─ 없으면: Scout가 사이트 분석 → Planner가 자체 경로 결정
├─ 구체적일수록 스텝 수 감소, 비용 절약
└─ 예: "hogangnono.com → 로그인 → 검색창에 아파트명 입력 → 리뷰 탭"

Context (선택) — "이것도 참고해"
├─ 인증 정보: 아이디, 비밀번호 (암호화 저장)
├─ 입력 데이터: 첨부 파일, 텍스트, 이미지
├─ 제약 조건: "15만원 이하만", "최근 1년", "한국어만"
├─ 출력 형식: "CSV로 저장", "이메일로 전송"
└─ 예: { id: "010XXXX", pw: "XXXX", apt_list: "apt_ids.csv" }
```

#### Direction 상세도에 따른 에이전트 행동 변화

```
Direction 없음 (자율 모드):
├─ Scout: 사이트 전체 탐색 (느리지만 철저)
├─ Planner: 자체 경로 결정 (LLM 판단에 의존)
├─ Executor: 매 스텝 accessibility tree 분석 → LLM이 다음 액션 결정
└─ 비용: 높음 (탐색 스텝 多)

Direction 대략적 ("로그인 후 리뷰 페이지"):
├─ Scout: 힌트된 영역 우선 탐색
├─ Planner: Direction을 골격으로 세부 스텝 보강
├─ Executor: 힌트 방향으로 우선 탐색, 막히면 대안 경로
└─ 비용: 중간

Direction 구체적 ("hogangnono.com → 사람 아이콘 클릭 → 휴대전화 로그인 → ..."):
├─ Scout: 최소 탐색 (Direction 경로 검증만)
├─ Planner: Direction을 거의 그대로 계획으로 변환
├─ Executor: Direction 스텝 순서대로 실행, 일치하는 요소 바로 액션
└─ 비용: 낮음 (최소 스텝)
```

#### Direction 기반 실행 루프 (Executor)

```
Executor가 Direction 힌트를 활용하는 방식:

Direction: "검색창에 아파트명 입력 → 리뷰 탭 클릭 → 스크롤 다운"

Step 1: "검색창에 아파트명 입력"
├─ Accessibility Tree에서 "검색" 관련 요소 탐색
├─ 매칭: <input role="searchbox" name="search"> 발견
├─ → type(searchbox, "래미안 강남")
└─ ✅ Direction 힌트와 일치 — 다음 스텝으로

Step 2: "리뷰 탭 클릭"
├─ Accessibility Tree에서 "리뷰" 텍스트 포함 요소 탐색
├─ 매칭 실패: "리뷰" 탭 없음, 대신 "거주자 평가" 탭 존재
├─ → LLM 판단: "거주자 평가 ≈ 리뷰" → click("거주자 평가")
└─ ⚠️ Direction과 정확히 일치하지 않지만 의미적으로 매칭

Step 3: "스크롤 다운"
├─ 리뷰 목록 로드 확인
├─ → scroll(down) 반복 (더 이상 새 항목 없을 때까지)
└─ ✅ 직관적 실행

핵심: Direction은 "참고"이지 "명령"이 아님
├─ 매칭되면 → 빠르게 실행 (탐색 생략)
├─ 매칭 안 되면 → LLM이 의미적 유사 요소 탐색
└─ 아예 다른 경로가 효율적이면 → Direction 무시하고 최적 경로 선택
```

#### 입력 예시

```
예시 1: 데이터 수집 (구체적 Direction)
─────────────────────────────────
Goal:      "호갱노노에서 강남구 아파트 리뷰 전체 수집"
Direction: "hogangnono.com → 로그인 → 검색창에 아파트명 입력
            → 리뷰 탭 → 스크롤 다운하며 전부 수집"
Context:   { id: "010XXXXXXXX", pw: "XXXXXX", apt_list: "apt_ids.csv" }

예시 2: 액션 실행 (대략적 Direction)
─────────────────────────────────
Goal:      "네이버 카페에 관리비 공지 글 작성"
Direction: "카페 → 글쓰기 → 제목/본문 입력 → 이미지 첨부 → 등록"
Context:   { title: "2월 관리비 공지", body: "notice.txt",
             images: ["img1.jpg", "img2.jpg", "img3.jpg"] }

예시 3: 모니터링 (Direction 없음)
─────────────────────────────────
Goal:      "에어팟 프로 2 가격이 15만원 이하면 알려줘"
Direction: (없음 — 에이전트가 알아서 최적 경로 탐색)
Context:   { threshold: 150000, check_interval: "daily 09:00" }

예시 4: 리서치 (대략적 Direction)
─────────────────────────────────
Goal:      "이 3개 사이트에서 RTX 5080 가격 비교표 만들어줘"
Direction: "각 사이트에서 검색 → 최저가 확인"
Context:   { sites: ["coupang.com", "11st.co.kr", "gmarket.co.kr"],
             output_format: "csv" }
```

### 전체 흐름

```
사용자 입력: Goal + Direction(선택) + Context(선택)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  1. Scout Agent (사이트 정찰)                     │
│                                                   │
│  URL 방문 → 사이트 환경 분석:                      │
│  ├─ Accessibility Tree 스냅샷 (페이지 구조 파악)   │
│  ├─ CDP 네트워크 모니터링 → Hidden API 발견        │
│  ├─ Schema.org / JSON-LD / RSS 존재 여부          │
│  ├─ 로그인/인증 필요 여부                          │
│  ├─ Anti-bot 방어 수준 파악                        │
│  ├─ 인터랙션 가능한 요소 목록 (버튼, 폼, 링크)     │
│  └─ 사이트 기술 스택 추정 (SPA/SSR/정적)           │
│                                                   │
│  출력: Site Analysis Report                       │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  2. Planner Agent (실행 계획 수립)                 │
│                                                   │
│  입력: Goal + Direction + Context + Site Report    │
│                                                   │
│  Step 1 — Goal 분석 → 태스크 분류:                 │
│  ├─ Goal에서 최종 결과물 식별                      │
│  ├─ 데이터 수집형? (리뷰 수집, 가격 비교 등)       │
│  ├─ 액션 실행형? (폼 작성, 글 등록, 주문 등)       │
│  ├─ 모니터링형? (가격 변동 감시, 재고 확인 등)      │
│  └─ 복합형? (로그인 → 검색 → 수집 → 제출)         │
│                                                   │
│  Step 2 — Direction 활용 → 실행 전략 결정:         │
│  ├─ Direction 있음 → 힌트를 골격으로 세부 계획 보강│
│  ├─ Direction 없음 → Scout 리포트 기반 자체 결정   │
│  ├─ Direction vs Scout 결과 충돌 시:               │
│  │   └─ Scout이 더 효율적 경로 발견 → Direction 무시│
│  ├─ API 직접 호출 가능? → 브라우저 없이 처리       │
│  ├─ 브라우저 조작 필요? → 액션 시퀀스 설계         │
│  ├─ 로그인 필요? → Context에서 인증 정보 확인      │
│  ├─ 반복 작업? → 서브에이전트 병렬화 결정          │
│  └─ 위험한 작업? → 사용자 확인 체크포인트 삽입     │
│                                                   │
│  Step 3 — 체크포인트 설정:                         │
│  ├─ 결제/제출 등 되돌릴 수 없는 액션 전 → 사용자 확인 │
│  ├─ 민감 정보 입력 시 → 마스킹 + 확인              │
│  └─ 예상 밖 상황 시 → 자동 일시정지               │
│                                                   │
│  출력: Execution Plan (태스크 유형 + 전략 + 스텝)  │
│  ※ Goal → 완료 기준, Direction → 스텝 골격        │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  3. Auth Agent (인증 처리) — 필요 시에만            │
│                                                   │
│  ■ 인증 전략 선택 (Context의 auth_method 참조):    │
│  ├─ 전략 1 "login" (기본):                         │
│  │   ├─ 브라우저에서 로그인 플로우 직접 실행        │
│  │   ├─ Context의 id/pw 사용                      │
│  │   └─ 가장 범용적, 모든 사이트에서 동작           │
│  ├─ 전략 2 "profile_sync" (browser-use 차용):      │
│  │   ├─ 로컬 Chrome 프로필에서 쿠키/세션 가져오기  │
│  │   ├─ 사용자가 이미 로그인한 세션 재사용          │
│  │   ├─ 로그인 플로우 생략 → 빠름, 2FA 우회        │
│  │   └─ Context: { auth_method: "profile_sync",   │
│  │        profile: "Default", domain: "naver.com" }│
│  └─ 전략 3 "cookie_import":                        │
│      ├─ 저장된 쿠키/토큰 파일에서 직접 로드         │
│      └─ Context: { auth_method: "cookie_import",  │
│           cookie_file: "naver_cookies.json" }      │
│                                                   │
│  ■ 공통:                                           │
│  ├─ storageState 저장 → 다른 에이전트와 공유       │
│  ├─ 세션 만료 시 자동 갱신                         │
│  └─ 실패 시 → 사용자에게 개입 요청                 │
│                                                   │
│  출력: auth_state.json (인증 세션)                 │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  4. Executor Agent(s) (태스크 실행)               │
│                                                   │
│  입력: Execution Plan + Direction + Context        │
│  Planner의 계획에 따라 실행, Direction을 네비게이션│
│  가이드로 활용                                     │
│                                                   │
│  ■ Direction 기반 네비게이션 루프:                  │
│  ├─ Direction 스텝 파싱 → 순서대로 실행 시도       │
│  ├─ 각 스텝에서:                                   │
│  │   1. Accessibility Tree에서 힌트 매칭 요소 탐색 │
│  │   2. 매칭 성공 → 바로 액션 (탐색 생략, 빠름)   │
│  │   3. 매칭 실패 → LLM이 의미적 유사 요소 탐색   │
│  │   4. 유사 요소도 없음 → 자율 탐색 모드 전환    │
│  ├─ Direction 없으면 → 전체 자율 모드              │
│  └─ Context에서 필요한 데이터 참조 (파일, 텍스트)  │
│                                                   │
│  ■ 데이터 수집형:                                  │
│  ├─ API 직접 호출 (Scout이 발견한 엔드포인트)      │
│  ├─ 브라우저 DOM 추출 (Accessibility Tree 기반)    │
│  └─ 스크롤 + 페이지네이션 자동 처리                │
│                                                   │
│  ■ 액션 실행형:                                    │
│  ├─ 폼 필드 식별 → Context에서 데이터 로드 → 입력 │
│  ├─ 버튼 클릭, 드롭다운 선택, 파일 업로드          │
│  ├─ 체크포인트에서 사용자 확인 대기                 │
│  └─ 결과 스크린샷 + 완료 확인                      │
│                                                   │
│  ■ 모니터링형:                                     │
│  ├─ 주기적 체크 (스케줄러 연동)                    │
│  ├─ Context의 조건 충족 시 알림                    │
│  └─ 변경 이력 저장                                 │
│                                                   │
│  ■ 공통:                                           │
│  ├─ Accessibility Tree → LLM → Action 루프        │
│  ├─ 각 스텝마다 Observer Hooks 호출 (아래 참조)    │
│  ├─ 다수 항목 → 독립 서브에이전트로 병렬 실행      │
│  └─ auth_state.json 공유                          │
│                                                   │
│  ■ 에러 복구 (browser-use 차용 — 다층 폴백):        │
│  ├─ max_failures = 5 (한도 초과 시 부분 결과 반환) │
│  ├─ 1차: 같은 액션 재시도 (네트워크 일시 오류 등)  │
│  ├─ 2차: LLM에게 대안 액션 요청                    │
│  ├─ 3차: 페이지 새로고침 후 재시도                  │
│  ├─ 4차: Direction 무시 → Goal 기반 자율 탐색      │
│  ├─ 5차: 현재 스텝 건너뛰고 다음 Direction으로     │
│  ├─ 한도 초과: 수집한 데이터까지 반환 + 사용자 알림│
│  └─ 상세 구현: VI장 "패턴 4. 다층 에러 복구" 참조  │
└──────────────────────┬──────────────────────────┘
                       │
                       │ ◀── Observer Agent가 매 스텝 감시
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  4.5 Observer Agent (실시간 감시 — Lifecycle Hooks)│
│  (browser-use on_step_start/end 패턴 차용)        │
│                                                   │
│  ■ 독립 에이전트가 아닌 Executor에 내장된 Hook:    │
│  ├─ Executor의 매 스텝 전/후에 자동 호출           │
│  ├─ Executor 코드를 수정하지 않고 감시 로직 교체 가능│
│  └─ 설정으로 Hook 활성화/비활성화 가능             │
│                                                   │
│  ■ on_step_start (스텝 실행 전):                   │
│  ├─ 위험 액션 감지 → 일시정지 + 사용자 승인 대기  │
│  │   (결제, 삭제, 탈퇴, 구매, 송금 등 키워드)     │
│  ├─ 무한루프 감지 → 같은 URL 5회 반복 시 중단     │
│  └─ 스텝 시작 로깅                                 │
│                                                   │
│  ■ on_step_end (스텝 실행 후):                     │
│  ├─ 실시간 UI 업데이트 (WebSocket → Agent Log)    │
│  │   → step 번호, 실행 액션, URL, 스크린샷, 상태  │
│  ├─ 수집 진행률 계산 + UI 프로그레스 바 갱신      │
│  └─ 스텝 결과 로깅 (소요 시간, 성공/실패)         │
│                                                   │
│  ■ 상세 구현: VI장 "패턴 3. Lifecycle Hooks" 참조  │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  5. Validator Agent (결과 검증)                    │
│                                                   │
│  태스크 유형별 검증:                                │
│                                                   │
│  ■ 데이터 수집형:                                  │
│  ├─ Pydantic 스키마 검증 (browser-use 차용):       │
│  │   ├─ Goal에서 기대 출력 → Pydantic 모델 정의    │
│  │   ├─ model_validate()로 타입/필수필드 자동 검증 │
│  │   └─ 검증 실패 → 누락 필드 식별 → 재수집 요청  │
│  ├─ Constraint 검증 (도메인 규칙)                  │
│  ├─ Differential 검증 (이전 결과 대비 급변 감지)    │
│  └─ 의심 데이터 → 격리큐 (사용자 확인)             │
│                                                   │
│  ■ 액션 실행형:                                    │
│  ├─ 액션 완료 여부 확인 (성공 페이지? 에러 메시지?) │
│  ├─ 기대 결과와 실제 결과 비교                      │
│  └─ 스크린샷으로 최종 상태 기록                     │
│                                                   │
│  ■ 공통:                                           │
│  ├─ 태스크 완료율 리포트                            │
│  └─ 실패 항목 → 재시도 큐 또는 사용자 알림          │
│                                                   │
│  출력: 검증 리포트 + 최종 결과                      │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  6. Pattern Compiler (학습)                       │
│                                                   │
│  ├─ 성공한 워크플로우를 결정론적 코드로 저장        │
│  ├─ 사이트 + 태스크 유형별 패턴 분류               │
│  ├─ 신뢰도 점수 부여                               │
│  └─ 다음에 같은 사이트/태스크 → 즉시 재생          │
└─────────────────────────────────────────────────┘
```

### 시나리오 A: 데이터 수집형 — 호갱노노 아파트 리뷰 수집

```
사용자 입력:
Goal:      "호갱노노에서 apt 파일의 각 아파트별 리뷰 전체 수집"
Direction: "hogangnono.com → 로그인 버튼 → 휴대전화 로그인
            → 검색창에 아파트명 입력 → 리뷰 섹션 → 스크롤 다운하며 수집"
Context:   { id: "010XXXXXXXX", pw: "XXXXXX", apt_list: "apt_ids.csv" }

→ Planner 분류: 데이터 수집형 (복합 — 로그인 + 반복 수집)
==================================================

Step 1. Scout Agent
├─ hogangnono.com 방문
├─ Accessibility Tree 스냅샷 → "사람 모양 로그인 버튼" 위치 확인
├─ CDP 네트워크 감시 → 내부 API 엔드포인트 탐색
│   └─ 발견: /api/v1/reviews?apt_id={id}&page={n} (JSON 응답!)
├─ 로그인 필요 확인 (인증 후 API 접근 가능 여부)
└─ 리포트: "SPA 사이트, 내부 API 존재, 로그인 필요"

Step 2. Planner Agent
├─ 판단: API 발견됨 → 하이브리드 전략
│   └─ 로그인은 브라우저로 (UI 플로우 필요)
│   └─ 리뷰 데이터는 API 직접 호출 (100x 빠름)
├─ 계획:
│   1. Auth Agent → 브라우저 로그인
│   2. 인증 토큰/쿠키 캡처
│   3. apt 파일 읽기 → id 목록 추출
│   4. 각 id별 /api/v1/reviews?apt_id={id} 호출
│   5. 페이지네이션 처리 (page=1,2,3...)
├─ 체크포인트: 없음 (수집은 비파괴적)
└─ 예상: 브라우저 스크롤링 불필요, API로 전량 수집 가능

Step 3. Auth Agent
├─ 브라우저 실행 → hogangnono.com 이동
├─ Accessibility Tree에서 로그인 버튼 찾기
├─ 클릭 → 휴대전화 로그인 선택
├─ 아이디/비밀번호 입력 → 로그인
├─ storageState 저장 → auth_hogangnono.json
└─ 인증 쿠키/토큰 추출

Step 4. Executor Agent(s)
├─ apt 파일에서 id 목록 로드 (예: 500개)
├─ 방법: API 직접 호출 (Scout이 발견한 엔드포인트)
│   └─ 인증 헤더 포함하여 /api/v1/reviews?apt_id={id}
│   └─ 500개 × 평균 3페이지 = 1,500 API 호출
│   └─ 브라우저 불필요 → 빠르고 안정적
├─ API 실패 시 폴백:
│   └─ 브라우저로 직접 접근 → 스크롤 + DOM 추출
└─ 결과: 아파트별 리뷰 JSON 수집

Step 5. Validator Agent
├─ 각 리뷰의 필수 필드 확인 (텍스트, 날짜, 평점 등)
├─ 이전 수집 데이터와 비교 (급격한 변화 감지)
└─ 검증 완료 → 최종 데이터 저장

Step 6. Pattern Compiler
├─ 호갱노노 패턴 저장:
│   "login: browser → /api/v1/reviews: direct API"
└─ 다음에 같은 요청 → 즉시 실행 (Scout/Planner 생략)
```

### 시나리오 B: 액션 실행형 — 네이버 카페 글 작성

```
사용자 입력:
Goal:      "네이버 카페 'XX 아파트 주민 모임'에 관리비 공지 글 작성"
Direction: "카페 접속 → 로그인 → 글쓰기 → 제목/본문 입력
            → 이미지 첨부 → 미리보기 확인 → 등록"
Context:   { title: "2월 관리비 공지", body: "notice.txt",
             images: ["img1.jpg", "img2.jpg", "img3.jpg"] }

→ Planner 분류: 액션 실행형 (로그인 + 폼 작성 + 파일 업로드)
==================================================

Step 1. Scout Agent
├─ cafe.naver.com 방문
├─ Accessibility Tree → 글쓰기 버튼, 에디터 구조 파악
├─ 로그인 필요 확인
└─ 리포트: "네이버 카페, 로그인 필수, 에디터는 iframe 기반"

Step 2. Planner Agent
├─ 분류: 액션 실행형
├─ 계획:
│   1. Auth Agent → 네이버 로그인
│   2. 카페 이동 → 글쓰기 버튼 클릭
│   3. 제목 입력
│   4. 본문 입력 (텍스트 파일 읽기)
│   5. 이미지 3장 첨부
│   6. [체크포인트] 미리보기 스크린샷 → 사용자 확인
│   7. 사용자 확인 후 → 등록 버튼 클릭
├─ 체크포인트: Step 6 (게시 전 최종 확인 — 되돌릴 수 없음)
└─ 위험 플래그: "글 등록은 비가역적 → 반드시 사용자 확인"

Step 3. Auth Agent
├─ 네이버 로그인 실행
└─ storageState 저장

Step 4. Executor Agent
├─ 카페 이동 → 글쓰기 클릭
├─ 제목 필드에 "2월 관리비 공지" 입력
├─ 본문 에디터에 텍스트 파일 내용 붙여넣기
├─ 이미지 업로드 (파일 3장)
├─ ★ 체크포인트: 미리보기 스크린샷 캡처
│   └─ Agent Log: "[확인 필요] 글 작성 완료. 등록하시겠습니까?"
│   └─ 사용자: "확인" → 등록 버튼 클릭
│   └─ 사용자: "수정" → 사용자 지시에 따라 수정
└─ 등록 완료 → 게시된 URL 반환

Step 5. Validator Agent
├─ 게시된 글 URL 방문
├─ 제목/본문/이미지가 의도대로 등록되었는지 확인
└─ 검증 완료 → 결과 리포트

Step 6. Pattern Compiler
├─ 네이버 카페 글쓰기 패턴 저장
└─ 다음에 같은 카페 글쓰기 → Auth + 폼 입력 즉시 재생
```

### 시나리오 C: 모니터링형 — 상품 가격 추적

```
사용자 입력:
Goal:      "에어팟 프로 2 가격이 15만원 이하로 떨어지면 알려줘"
Direction: (없음 — 에이전트 자율 탐색)
Context:   { site: "coupang.com", threshold: 150000,
             check_interval: "daily 09:00" }

→ Planner 분류: 모니터링형 (반복 체크 + 조건부 알림)
==================================================

Step 1. Scout Agent
├─ coupang.com 방문 → "에어팟 프로 2" 검색
├─ CDP 네트워크 감시 → 상품 API 발견 여부 확인
├─ 가격 표시 위치 파악 (Accessibility Tree)
└─ 리포트: "SPA 사이트, 검색 API 존재, 로그인 불필요"

Step 2. Planner Agent
├─ 분류: 모니터링형
├─ 계획:
│   1. 상품 페이지 특정 (검색 → 최적 매칭 상품)
│   2. 가격 추출 방법 결정 (API or DOM)
│   3. 스케줄 등록: 매일 09:00
│   4. 조건: price < 150,000 → 알림
├─ 체크포인트: 없음 (조회만, 비파괴적)
└─ 스케줄러 연동 필요 → Layer 4

Step 3~4. Executor Agent (매일 반복)
├─ 상품 페이지 접근 → 가격 추출
├─ 150,000원 이상 → 로그 기록, 다음 스케줄 대기
├─ 150,000원 미만 → ★ 사용자 알림 발송
└─ 가격 이력 DB에 저장

Step 5. Validator Agent
├─ 추출된 가격이 실제와 일치하는지 (스크린샷 대조)
└─ 이상 감지 시 → 재확인 후 알림
```

---

## V. 계층 아키텍처 (Bowser 참고)

Bowser의 4-layer 구조를 우리 프로젝트에 맞게 변형:

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 4 — Scheduler (재사용/자동화)                          │
│  크론 스케줄, 반복 실행, 배치 처리                             │
│  "매일 오전 9시에 호갱노노 리뷰 업데이트"                      │
├──────────────────────────────────────────────────────────────┤
│  Layer 3 — Orchestrator (오케스트레이션)                       │
│  TASK 분석 → 에이전트 배치 → 결과 취합 → 검증                 │
│  = Planner + Validator + Pattern Compiler                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 2 — Agents (병렬 실행 단위)                            │
│  Scout, Auth, Executor — 각각 독립 브라우저 세션              │
│  에이전트간 auth_state 공유, 그 외 완전 격리                   │
├──────────────────────────────────────────────────────────────┤
│  Layer 1 — Browser Skills (브라우저 조작 능력)                │
│  Playwright API + Accessibility Tree → LLM → Action          │
│  CDP 이벤트 감시, 스크린샷, 네트워크 인터셉트                  │
└──────────────────────────────────────────────────────────────┘
```

### 각 레이어는 독립 테스트 가능

```
Layer 1 테스트: "이 URL에서 accessibility tree 추출해봐"
Layer 2 테스트: "Scout Agent 혼자서 이 사이트 분석해봐"
Layer 3 테스트: "이 TASK에 대해 전체 워크플로우 실행해봐"
Layer 4 테스트: "스케줄 등록 후 반복 실행 확인"
```

---

## VI. 브라우저 상호작용 패턴 (Browser-use 차용)

### browser-use CLI 분석 결과

browser-use CLI의 핵심 아키텍처를 분석하고, 우리 프로젝트에 적용할 패턴을 도출했다.

#### browser-use vs 우리 계획 비교

| 항목 | browser-use CLI | 우리 프로젝트 (v2) |
|---|---|---|
| **페이지 상태 표현** | `state` → 인덱스 번호 + 클릭 가능 요소 목록 | Accessibility Tree 전체 스냅샷 |
| **요소 식별** | 숫자 인덱스 (`click 5`) | CSS/ARIA selector (`getByRole`) |
| **브라우저 엔진** | Playwright (내부) | Playwright (직접 사용) |
| **LLM 역할** | CLI를 호출하는 외부 에이전트가 판단 | 내장 루프에서 다음 액션 결정 |
| **세션 유지** | CLI 프로세스간 세션 공유 | Playwright storageState |
| **인증** | Chrome 프로필 직접 사용 / 쿠키 동기화 | Auth Agent가 매번 로그인 플로우 실행 |
| **병렬 실행** | 클라우드 세션 (Session = Agent) | 독립 브라우저 컨텍스트 |
| **CDP 접근** | 제한적 (CLI 추상화 뒤) | 직접 접근 (Hidden API, Diagnostics) |

#### 차용할 패턴 5가지

```
1. State-First 인덱싱 — 토큰 절약 + LLM 판단 명확화
   ────────────────────────────────────────────────
   browser-use: `state` → 클릭 가능 요소만 인덱스로 반환
   차용: Accessibility Tree에서 상호작용 가능 요소만 추출 → 인덱스 부여
   효과: LLM이 "5번 클릭" vs "role=button, name='로그인' 요소 클릭"
         → 토큰 50%↓, 응답 명확도↑, 파싱 에러↓

   구현:
   ├─ page.accessibility.snapshot()에서 interactable 요소만 필터
   ├─ 각 요소에 [1], [2], [3]... 인덱스 부여
   ├─ LLM에 인덱싱된 목록 전달
   └─ LLM 응답: { action: "click", index: 5 } → 즉시 실행

2. 3-Tier 브라우저 모드 — 유연한 실행 환경
   ────────────────────────────────────────────────
   browser-use:
   ├─ chromium: headless, 빠름, 격리 (기본)
   ├─ real: 로컬 Chrome + 사용자 프로필 (로그인 세션 재사용)
   └─ remote: 클라우드 브라우저 (프록시 + 병렬)

   차용:
   ├─ 기본: Playwright headless Chromium (현재 계획 유지)
   ├─ 추가: 로컬 Chrome 프로필 모드 → Auth Agent 없이 인증 해결
   └─ Phase 3: 클라우드 브라우저 모드 (스케일 시)

   핵심 인사이트: real 모드(로컬 Chrome 프로필)는 Auth Agent를
   완전히 건너뛸 수 있는 강력한 패턴. 사용자가 이미 로그인한
   Chrome 세션을 에이전트가 그대로 사용.

3. 프로필 + 쿠키 동기화 — Auth 전략 다양화
   ────────────────────────────────────────────────
   browser-use:
   ├─ profile cookies "Default" → 어떤 사이트에 로그인되어 있는지 확인
   ├─ profile sync --from "Default" --domain github.com → 특정 도메인만
   └─ cookies export/import → 세밀한 쿠키 관리

   차용: Auth Agent에 3가지 인증 전략 추가
   ├─ 전략 1: 로그인 플로우 실행 (현재 계획, 기본)
   ├─ 전략 2: 로컬 Chrome 프로필에서 세션 가져오기 (신규)
   ├─ 전략 3: 저장된 쿠키/토큰 파일에서 로드 (신규)
   └─ Context에서 선택: { auth_method: "login" | "profile_sync" | "cookie_import" }

4. 서브에이전트 병렬 패턴 — Session = Agent
   ────────────────────────────────────────────────
   browser-use:
   ├─ 각 태스크가 독립 세션에서 병렬 실행
   ├─ keep-alive로 세션 재사용 (순차 태스크)
   └─ session-id로 기존 세션에 새 태스크 주입

   차용: Layer 2 에이전트 관리에 적용
   ├─ 병렬: 아파트 500개 → 각각 독립 Executor 세션
   ├─ 순차: 로그인 → (같은 세션) → 데이터 수집
   ├─ 세션 재사용: 한 번 인증한 세션을 여러 Executor가 공유
   └─ 핵심: 세션 ID 기반 관리 → auth_state.json 보다 유연

5. 확장된 Action Space — 실전 부족분 보완
   ────────────────────────────────────────────────
   browser-use에 있고 현재 계획에 없는 액션:
   ├─ hover → CSS :hover 트리거 (드롭다운 메뉴, 툴팁)
   ├─ dblclick → 텍스트 선택, 편집 모드 진입
   ├─ rightclick → 컨텍스트 메뉴 조작
   ├─ keys "Control+a" → 키보드 조합 (복사, 붙여넣기, 단축키)
   ├─ eval "JS코드" → JavaScript 직접 실행 (Hidden API 호출 등)
   ├─ get value → input/textarea 현재 값 확인
   ├─ get attributes → 요소의 모든 속성 조회
   └─ get bbox → 요소 위치/크기 (VLM 좌표 매칭 시 유용)
```

#### Phase별 적용 전략

```
Phase 0 (PoC) — browser-use CLI 직접 사용
├─ browser-use CLI를 Layer 1으로 사용하여 빠르게 프로토타입 구현
├─ LLM → browser-use 명령 생성 → CLI 실행 → 결과 파싱
├─ 장점: 이미 구현된 도구, 바로 사용 가능, 세션 관리 내장
├─ 단점: CDP 직접 접근 불가, Hidden API Interception 제한
└─ 목적: 핵심 가설 검증 (LLM이 한국어 사이트를 이해하는가?)

Phase 1 (MVP) — Playwright 자체 구현으로 전환
├─ browser-use의 패턴을 차용하여 Playwright로 직접 구현
├─ state 함수: accessibility.snapshot() + 인덱싱
├─ 액션 함수: page.click(), page.fill() 등 래핑
├─ 세션 관리: storageState + 브라우저 컨텍스트
├─ 장점: CDP 완전 접근, Hidden API, 커스터마이징 자유
└─ browser-use에서 가져올 것: 인덱싱, 세션 패턴, Action Space

전환 비용 최소화:
├─ Phase 0에서 browser-use CLI로 검증한 워크플로우를
│   Phase 1에서 Playwright 코드로 1:1 변환
├─ Action Space 동일 유지 → LLM 프롬프트 재사용 가능
└─ 인덱싱 방식 동일 → 에이전트 로직 변경 불필요
```

### browser-use Python API에서 차용할 패턴 7가지

browser-use의 Python API (v0.11.x) 워크플로우를 분석하여, **설계 패턴과 아키텍처 아이디어**만 차용한다.
우리는 browser-use를 직접 사용하지 않고 Playwright 기반으로 자체 구현하되, 아래 패턴들을 적용한다.

> **참고**: browser-use는 v0.6.0에서 Playwright를 제거하고 직접 CDP를 사용하는 방식으로 전환했다.
> 이는 그들의 아키텍처 사정이며, 우리는 Playwright의 성숙한 추상화 (자동 대기, 셀렉터, 에러 처리)가
> Pattern Compiler와의 궁합, 개발 생산성 면에서 유리하므로 Playwright를 유지한다.
> 필요 시 Playwright 내에서 CDP 직접 접근도 가능하다 (`page.context.new_cdp_session()`).

```
패턴 1. 순차 체이닝 — Direction 기반 스텝 실행
────────────────────────────────────────────────
browser-use 원본: keep_alive=True + add_new_task()로 브라우저 세션 유지하며 태스크 순차 실행
차용 대상: Executor Agent의 Direction 스텝별 실행

구현:
├─ 브라우저 세션(Playwright page)을 유지한 채 Direction의 각 스텝을 순차 실행
├─ 스텝 간 상태 공유 (로그인 세션, 이전 스텝 결과 등)
├─ 스텝 실패 시 → 자율 모드로 전환 (Direction 힌트 무시, Goal 기반 탐색)
└─ 의사코드:

   class DirectionExecutor:
       def __init__(self, browser, llm):
           self.browser = browser  # Playwright browser, 세션 유지
           self.page = None

       async def execute_direction(self, goal, directions, context):
           self.page = await self.browser.new_page()
           for i, step in enumerate(directions):
               result = await self.execute_step(
                   task=step, goal=goal, step_index=i,
                   total_steps=len(directions), context=context,
               )
               if result.status == "blocked":
                   result = await self.autonomous_step(goal, context)
           return self.collect_results()

패턴 2. 병렬 에이전트 — 멀티사이트 동시 수집
────────────────────────────────────────────────
browser-use 원본: asyncio.gather() + 사이트별 독립 Browser 인스턴스
차용 대상: Planner가 멀티사이트 태스크를 분배할 때

구현:
├─ 각 사이트별 독립 Playwright 브라우저 인스턴스 생성
├─ asyncio.gather(*agents, return_exceptions=True)로 병렬 실행
├─ 하나 실패해도 나머지 계속 진행 (부분 실패 허용)
├─ 실패한 것만 선별 재시도
└─ 의사코드:

   async def parallel_collect(tasks):
       agents = []
       for task in tasks:
           browser = await playwright.chromium.launch()
           agent = SiteAgent(goal=task["goal"], browser=browser, ...)
           agents.append(agent)
       results = await asyncio.gather(
           *[a.run() for a in agents],
           return_exceptions=True,  # 부분 실패 허용
       )
       failed = [(i, r) for i, r in enumerate(results) if isinstance(r, Exception)]
       for i, error in failed:
           results[i] = await agents[i].retry(max_attempts=2)
       return results

패턴 3. Lifecycle Hooks — Observer Agent 핵심 메커니즘
────────────────────────────────────────────────
browser-use 원본: on_step_start / on_step_end 콜백으로 매 스텝 모니터링, 일시정지/재개
차용 대상: Observer Agent (UI 실시간 업데이트 + 위험 감지 + 무한루프 방지)

구현:
├─ on_step_start(state): 스텝 실행 전 호출
│   ├─ 위험 액션 감지 → 일시정지 + 사용자 승인 대기
│   │   (결제, 삭제, 탈퇴 등 키워드 탐지)
│   ├─ 무한루프 감지 → 같은 URL 5회 반복 시 에러 발생
│   └─ 스텝 로깅 (시작 시각, 계획된 액션)
│
├─ on_step_end(state): 스텝 실행 후 호출
│   ├─ 실시간 UI 업데이트 (WebSocket 브로드캐스트)
│   │   → { step, action, url, screenshot, status }
│   ├─ 스텝 결과 로깅 (소요 시간, 성공/실패)
│   └─ 수집 진행률 계산 + UI 표시
│
└─ 의사코드:

   class ObserverHooks:
       dangerous_keywords = ["결제", "삭제", "탈퇴", "구매", "송금"]

       async def on_step_start(self, state):
           # 위험 액션 감지
           if any(kw in state.planned_action for kw in self.dangerous_keywords):
               self.paused = True
               await self.notify_user(f"위험 액션 감지: {state.planned_action}")
               await self.wait_for_approval()
           # 무한루프 감지
           recent_urls = [s.url for s in self.step_log[-5:]]
           if len(set(recent_urls)) == 1 and len(recent_urls) == 5:
               raise LoopDetectedError(f"같은 페이지 5회 반복: {recent_urls[0]}")

       async def on_step_end(self, state):
           self.step_log.append(state)
           await self.broadcast({
               "step": state.step_number, "action": state.executed_action,
               "url": state.current_url, "screenshot": state.screenshot_base64,
           })

패턴 4. 다층 에러 복구 — 단계적 폴백
────────────────────────────────────────────────
browser-use 원본: max_failures + fallback_llm + final_response_after_failure
차용 대상: Executor Agent의 에러 처리 (기존 "CDP → LLM → VLM → Human" 대체)

구현:
├─ max_failures 한도 설정 (기본 5회) → 무한 재시도 방지
├─ 실패 횟수에 따라 복구 전략 단계적 에스컬레이션:
│
│   실패 1회차 → retry_same_action (단순 재시도, 네트워크 일시 오류 등)
│   실패 2회차 → try_alternative_action (LLM에게 대안 액션 요청)
│   실패 3회차 → reload_and_retry (페이지 새로고침 후 재시도)
│   실패 4회차 → fallback_to_autonomous (Direction 무시, Goal 기반 자율 탐색)
│   실패 5회차 → skip_and_continue (현재 스텝 건너뛰고 다음으로)
│   한도 초과  → abort (부분 결과 반환 + 사용자 알림)
│
├─ 핵심: 실패해도 그때까지 수집한 데이터는 보존하여 반환
│   → final_response_after_failure = True
│
└─ 의사코드:

   class ErrorRecovery:
       recovery_strategies = [
           retry_same_action,       # 1차: 같은 액션 재시도 (1초 대기)
           try_alternative_action,  # 2차: LLM에게 대안 요청
           reload_and_retry,        # 3차: 페이지 리로드
           fallback_to_autonomous,  # 4차: 자율 탐색 모드 전환
           skip_and_continue,       # 5차: 스텝 건너뛰기
       ]

       async def handle_failure(self, error, context):
           self.failure_count += 1
           if self.failure_count > self.max_failures:
               return RecoveryResult(
                   status="aborted",
                   partial_result=context.collected_so_far,
               )
           strategy = self.recovery_strategies[min(
               self.failure_count - 1, len(self.recovery_strategies) - 1
           )]
           return await strategy(error, context)

패턴 5. 민감 데이터 플레이스홀더 — Auth 보안 강화
────────────────────────────────────────────────
browser-use 원본: sensitive_data={} + allowed_domains=[]로 LLM에 비밀번호 노출 방지
차용 대상: Auth Agent + Context의 자격증명 처리

구현:
├─ Context의 credentials를 플레이스홀더로 치환
│   예: { id: "010XXX", pw: "secret" }
│   → LLM에게는 "x]{{id}}로 로그인"이라고 전달
│   → 브라우저 input 시점에만 실제 값 대입
│
├─ allowed_domains: 자격증명이 입력될 수 있는 도메인 제한
│   → 피싱 사이트로 리다이렉트되더라도 비밀번호 미입력
│
└─ 의사코드:

   class SecureContextHandler:
       def mask_for_llm(self, text):
           """LLM 프롬프트에서 실제 값을 플레이스홀더로 치환"""
           for key, placeholder in self.placeholders.items():
               text = text.replace(self.real_values[placeholder], placeholder)
           return text

       def unmask_for_browser(self, action):
           """브라우저 실행 직전에 플레이스홀더를 실제 값으로 복원"""
           if "text" in action:
               for placeholder, real in self.real_values.items():
                   action["text"] = action["text"].replace(placeholder, real)
           return action

패턴 6. 구조화된 출력 — Validator 연동
────────────────────────────────────────────────
browser-use 원본: output_model_schema (Pydantic) → 수집 결과를 사전 정의된 스키마로 검증
차용 대상: Validator Agent의 스키마 검증 핵심 로직

구현:
├─ Goal에서 기대 출력 형태를 Pydantic 모델로 사전 정의
│   예: Goal "아파트 리뷰 수집"
│   → schema: { items: list[{text, date, rating}], total_count, source_url }
│
├─ Executor 수집 결과를 schema.model_validate()로 자동 검증
├─ 검증 실패 시 → 누락 필드 식별 → Executor에게 재수집 요청
└─ 의사코드:

   class Validator:
       def __init__(self, schema: type[BaseModel]):
           self.schema = schema

       def validate(self, raw_result):
           try:
               parsed = self.schema.model_validate(raw_result)
               return ValidationResult(valid=True, data=parsed)
           except ValidationError as e:
               return ValidationResult(valid=False, errors=e.errors())

패턴 7. Tools 데코레이터 — 커스텀 액션 확장 구조
────────────────────────────────────────────────
browser-use 원본: @tools.action(description='...') 데코레이터로 커스텀 액션 등록
차용 대상: Action Space 확장 (기본 19개 + 사이트/태스크별 커스텀 액션)

구현:
├─ ActionRegistry 클래스로 커스텀 액션 등록/관리
├─ 데코레이터로 쉽게 추가 → LLM 프롬프트에 자동 포함
├─ 사이트별/태스크별 특화 액션을 플러그인처럼 추가 가능
│   예: save_to_db, export_csv, send_notification 등
│
└─ 의사코드:

   registry = ActionRegistry()

   @registry.action("save_to_db", "수집한 데이터를 DB에 저장")
   async def save_to_db(data: dict):
       await db.insert(data)
       return "저장 완료"

   @registry.action("export_csv", "결과를 CSV로 내보내기")
   async def export_csv(data: list, filename: str):
       # CSV 생성 로직
       return f"{filename} 저장 완료"

   # LLM 프롬프트에 자동 포함:
   # registry.get_action_descriptions()
   # → "- save_to_db: 수집한 데이터를 DB에 저장\n- export_csv: ..."
```

#### 차용 패턴 요약

| # | 차용 패턴 | browser-use 출처 | 우리 프로젝트 적용 대상 |
|---|----------|-----------------|----------------------|
| 1 | 순차 체이닝 (`keep_alive` + `add_new_task`) | 멀티에이전트 패턴 B | Executor — Direction 스텝별 실행 |
| 2 | 병렬 수집 (`asyncio.gather` + 독립 브라우저) | 멀티에이전트 패턴 A | Planner — 멀티사이트 태스크 분배 |
| 3 | Lifecycle Hooks (`on_step_start/end`) | Lifecycle Hooks | Observer Agent — 위험 감지, 무한루프 방지, UI 업데이트 |
| 4 | 다층 에러 복구 (단계적 폴백) | Error Recovery | Executor — 5단계 복구 전략 |
| 5 | 민감 데이터 플레이스홀더 | Sensitive Data | Auth Agent — 자격증명 LLM 미노출 |
| 6 | 구조화된 출력 (Pydantic 스키마) | Structured Output | Validator Agent — 스키마 기반 검증 |
| 7 | Tools 데코레이터 (커스텀 액션) | Tools API | Action Space — 플러그인 확장 구조 |

### 핵심 루프: Observation → LLM → Action

```python
# Browser-use에서 차용하는 핵심 패턴 (인덱스 기반 state 방식)

async def get_indexed_state(page):
    """Accessibility Tree에서 상호작용 가능 요소만 추출 → 인덱스 부여"""
    snapshot = await page.accessibility.snapshot()
    elements = []
    index = 1

    def extract_interactable(node, depth=0):
        nonlocal index
        role = node.get("role", "")
        name = node.get("name", "")
        # 상호작용 가능한 요소만 필터
        interactable_roles = {
            "link", "button", "textbox", "searchbox",
            "combobox", "checkbox", "radio", "tab",
            "menuitem", "option"
        }
        if role in interactable_roles:
            elements.append({
                "index": index,
                "role": role,
                "name": name,
                "value": node.get("value", ""),
            })
            index += 1
        for child in node.get("children", []):
            extract_interactable(child, depth + 1)

    extract_interactable(snapshot)
    return elements

async def agent_step(page, task, direction_hint, llm):
    # 1. Observation: 인덱싱된 상태 수집
    url = page.url
    state = await get_indexed_state(page)
    state_text = "\n".join(
        f"[{e['index']}] {e['role']}: \"{e['name']}\""
        + (f" (value: {e['value']})" if e['value'] else "")
        for e in state
    )

    # 2. LLM에게 다음 액션 결정 요청
    prompt = f"""
    현재 URL: {url}

    현재 페이지 요소 (인덱스 → 역할: 텍스트):
    {state_text}

    수행할 작업: {task}
    """
    # Direction 힌트가 있으면 추가
    if direction_hint:
        prompt += f"\n    경로 힌트: {direction_hint}"

    prompt += """

    가능한 액션:
    - click(index): 요소 클릭       - hover(index): 마우스 오버
    - input(index, text): 텍스트 입력 - select(index, option): 드롭다운 선택
    - keys(combo): 키보드 입력       - scroll(direction, amount): 스크롤
    - extract(index): 데이터 추출    - navigate(url): URL 이동
    - eval(js): JavaScript 실행     - screenshot(): 화면 캡처
    - wait(selector/seconds): 대기   - api_call(url, method, ...): API 직접 호출
    - done(result): 작업 완료        - ask_human(question): 사용자 개입 요청

    다음에 수행할 액션을 JSON으로 응답:
    { "action": "click", "index": 5, "reason": "로그인 버튼 클릭" }
    """

    response = await llm.invoke(prompt)

    # 3. Action: LLM이 결정한 액션 실행
    action = parse_action(response)
    result = await execute_action(page, action, state)

    return result
```

**인덱싱 방식의 이점 (browser-use에서 차용):**
```
AS-IS (Accessibility Tree 전체 전달):
├─ 토큰 多 — 트리 전체가 수백~수천 라인
├─ LLM 응답 모호 — "role=button, name='로그인' 클릭" → 파싱 복잡
└─ 비용 높음

TO-BE (인덱싱된 상태 전달):
├─ 토큰 少 — 상호작용 가능 요소만 (보통 20~50개)
├─ LLM 응답 명확 — { "action": "click", "index": 5 } → 즉시 실행
├─ 비용 50%↓
└─ Direction 힌트와 결합 → "검색창" ≈ [3] searchbox: "검색" → 매칭 용이
```

### Action Space 정의

browser-use CLI의 명령어 세트를 분석하여 확장한 Action Space:

#### 기본 액션

| 액션 | 설명 | 파라미터 | Playwright 매핑 |
|---|---|---|---|
| `click` | 요소 클릭 | index | `page.locator(...).click()` |
| `input` | 요소 클릭 후 텍스트 입력 | index, text | `page.locator(...).fill(text)` |
| `keys` | 키보드 입력 (단일/조합) | combo | `page.keyboard.press("Control+a")` |
| `select` | 드롭다운 옵션 선택 | index, option | `page.locator(...).select_option(option)` |
| `scroll` | 스크롤 | direction, amount | `page.mouse.wheel(0, amount)` |
| `navigate` | URL 이동 | url | `page.goto(url)` |

#### 확장 액션 (browser-use에서 차용)

| 액션 | 설명 | 파라미터 | 용도 |
|---|---|---|---|
| `hover` | 마우스 오버 | index | 드롭다운 메뉴, 툴팁 트리거 |
| `dblclick` | 더블클릭 | index | 텍스트 선택, 편집 모드 진입 |
| `rightclick` | 우클릭 | index | 컨텍스트 메뉴 조작 |
| `eval` | JavaScript 직접 실행 | js_code | Hidden API 호출, DOM 조작 |
| `get_value` | input/textarea 현재 값 | index | 폼 상태 확인 |
| `get_attributes` | 요소 속성 전체 조회 | index | 동적 속성 파악 |
| `get_bbox` | 요소 위치/크기 | index | VLM 좌표 매칭 (Phase 2) |

#### 제어 액션

| 액션 | 설명 | 파라미터 | 용도 |
|---|---|---|---|
| `extract` | 데이터 추출 | index, schema | 구조화된 데이터 수집 |
| `screenshot` | 화면 캡처 | path (선택) | 상태 기록, 체크포인트 |
| `wait` | 대기 | selector / seconds | 로딩, 동적 렌더링 대기 |
| `api_call` | 직접 API 호출 | url, method, headers, body | Scout이 발견한 Hidden API |
| `done` | 작업 완료 | result | 태스크 종료 신호 |
| `ask_human` | 사용자 개입 요청 | question | CAPTCHA, 확인 필요 시 |

#### 인덱스 기반 vs 셀렉터 기반

```
browser-use 방식 (인덱스 — Phase 0~1에서 기본):
├─ LLM 응답: { "action": "click", "index": 5 }
├─ 장점: 간단, 토큰 절약, 파싱 에러 적음
└─ 단점: 페이지 변경 시 인덱스 재매핑 필요

Playwright 방식 (셀렉터 — 고급/Pattern Compiler용):
├─ LLM 응답: { "action": "click", "selector": "getByRole('button', name='로그인')" }
├─ 장점: 페이지 구조 변경에 강건, 패턴 저장에 적합
└─ 단점: 토큰 多, 파싱 복잡

하이브리드 전략:
├─ Executor: 인덱스 기반 (실시간 루프, 빠름)
├─ Pattern Compiler: 성공한 인덱스 액션 → 셀렉터로 변환하여 저장
└─ Replay: 저장된 셀렉터 기반 패턴으로 결정론적 실행
```

### Accessibility Tree 우선 (VLM 아님)

```
우선순위:
1. Accessibility Tree (텍스트, 무료, 빠름)
   → 대부분의 요소 식별 가능
   → LLM이 텍스트로 페이지 구조 이해

2. getByRole / getByText / getByLabel (Playwright 내장)
   → CSS 셀렉터보다 robust
   → 사이트 리디자인에도 잘 유지됨

3. [Phase 2] Screenshot + VLM (비쌈, 느림)
   → 위 두 방법으로 안 될 때만
   → A/B 테스트로 효과 검증 후 결정
```

---

## VII. 이전 계획에서 유지하는 것

다음 아이디어들은 v1에서 검증되었으며 v2에도 그대로 유지:

### 최우선 (Phase 1에 포함)

| 아이디어 | 위치 | 비고 |
|---|---|---|
| **Playwright headless 기본** | Layer 1 | 변경 없음 |
| **Hidden API Interception** | Scout Agent | CDP 네트워크 감시로 API 자동 발견 |
| **Structured Data First** | Scout Agent | Schema.org, RSS, JSON-LD 확인 |
| **CDP Diagnostics** | Executor Agent 에러 처리 | 에러 80% 무료 진단 |
| **Quality Firewall** | Validator Agent | Silent Error 방지 |
| **Cost Circuit Breaker** | Orchestrator | 비용 폭발 방지 |

### 1차 (Phase 2에 포함)

| 아이디어 | 위치 | 비고 |
|---|---|---|
| **Pattern Compiler** | 학습 단계 | 성공 패턴 → 결정론적 코드 |
| **Auth Agent 분리** | 독립 에이전트 | storageState 기반 세션 공유 |
| **Tiered Escalation** | Executor Agent | CDP → LLM → VLM → Human |
| **Evaluation Harness** | Validator Agent 확장 | 자동화 CI 개념 |

---

## VIII. 이전 계획에서 변경/보류하는 것

### 변경

| 항목 | v1 | v2 | 이유 |
|---|---|---|---|
| **VLM 역할** | 듀얼 분석의 핵심 축 | 선택적 실험 대상 | Accessibility Tree + LLM으로 대부분 해결 가능. 실증 후 결정 |
| **진입점** | 대규모 자동화 시스템 | 단일 TASK 완료 시스템 + UI | PoC 먼저, 스케일은 나중 |
| **UI** | 없음 (백엔드 파이프라인) | Anchor 스타일 시각화 UI | 개입 포인트 가시화 + 디버깅 |
| **브라우저 조작** | L0~L3 에스컬레이션 | Browser-use 스타일 루프 | Observation → LLM → Action 패턴 차용 |

### 보류 (Phase 3 이후)

| 항목 | 이유 |
|---|---|
| **AgentSymbiotic (대형+소형 모델)** | PoC 이후 비용 최적화 단계에서 검토 |
| **Swarm Micro-Crawlers** | 스케일아웃 필요 시 |
| **Time-Travel Differential** | 장기 운영 데이터 축적 후 |
| **World Model** | 연구 단계 |
| **Site Archetype 분류** | Pattern DB 축적 후 자연스럽게 |

---

## IX. 실행 로드맵

### Phase 1-A: 핵심 루프 구현 (1~2주)

**목표**: 단일 agent_step() 루프가 동작하는 최소 시스템 + 기존 UI 연결

```
프로젝트 구조:
agentic_crawler/
├─ src/
│   ├─ main.html                    ← 기존 UI (Tailwind CSS)
│   ├─ server.py                    ← FastAPI 백엔드 (WebSocket)
│   ├─ core/
│   │   ├─ browser.py               ← Playwright 브라우저 관리
│   │   ├─ state.py                 ← get_indexed_state()
│   │   ├─ actions.py               ← execute_action() + Action Space
│   │   └─ agent_loop.py            ← agent_step() 핵심 루프
│   ├─ llm/
│   │   └─ client.py                ← LLM 클라이언트 (Claude/GPT-4o)
│   └─ config.py                    ← 설정 (API 키, 브라우저 옵션)
├─ requirements.txt
└─ .env                             ← API 키 (gitignore)

구현 순서:
├─ 1. Layer 1 — 브라우저 + 상태 추출
│   ├─ browser.py: Playwright 브라우저 시작/종료/스크린샷
│   ├─ state.py: get_indexed_state() (Accessibility Tree → 인덱싱)
│   └─ actions.py: execute_action() (기본 6개 액션: click, input, keys, select, scroll, navigate)
│
├─ 2. LLM 연결
│   ├─ client.py: LangChain + Claude claude-sonnet-4-6 / GPT-4o
│   └─ 프롬프트 템플릿 (인덱싱된 state + task → JSON 액션 응답)
│
├─ 3. 핵심 루프 통합
│   ├─ agent_loop.py: agent_step() = state → LLM → action → 반복
│   └─ 종료 조건: LLM이 done() 액션 반환 시
│
├─ 4. UI 연결
│   ├─ server.py: FastAPI + WebSocket
│   ├─ main.html → 실행 버튼 클릭 → API 호출 → 에이전트 시작
│   ├─ Agent Logic Stream → WebSocket 실시간 로그
│   └─ Browser View → 스텝별 스크린샷 표시
│
└─ 5. 검증
    ├─ 단순 사이트 네비게이션 (예: 구글 검색)
    ├─ 한국어 사이트 인덱싱 확인 (예: naver.com)
    ├─ LLM이 인덱싱된 state를 이해하고 올바른 액션을 반환하는가?
    └─ 측정: 스텝 수, 성공률, 응답 시간, 토큰 사용량
```


**Accessibility Tree 추출 검토**

**초기 접근 (aria_snapshot 방식)**
- Playwright의 `page.accessibility.snapshot()` 사용 시도
- 문제점: subwayyy.kr에서 **단 5개 요소**만 추출되는 문제 발생
- 대부분의 인터랙티브 요소가 누락됨 (한국 사이트들이 ARIA 속성을 제대로 구현하지 않음)
- 특히 `div`에 클릭 핸들러만 붙인 경우 접근성 트리에 나타나지 않음

**해결책 (DOM 기반 + cursor:pointer 하이브리드)**
- `state.py`를 전면 재작성하여 DOM 기반 추출로 변경
- 표준 인터랙티브 요소 (button, a, input 등) + ARIA role 요소 수집
- **cursor:pointer** 스타일이 있는 div도 추가 수집 (클릭 핸들러가 있는 요소 감지)
- 각 요소에 `data-aidx` 속성 주입하여 안정적 참조 가능
- 결과: subwayyy.kr에서 **97개 요소** 추출 (19배 개선)

**구현 세부사항**
- JavaScript를 통해 브라우저에서 직접 실행 (`page.evaluate()`)
- 가시성 필터링: `offsetParent === null`, `display:none`, `visibility:hidden` 제외
- DOM 순서 정렬: `compareDocumentPosition` 기준
- 요소 이름 추출 우선순위: aria-label → label태그 → 직접 텍스트 → innerText → placeholder/title/alt
- 역할 추론: 명시적 role 속성 → 태그 기반 추론 → cursor:pointer div는 'button'으로 처리


### Phase 1-B: 에이전트 분리 (2~3주)

**목표**: 단일 루프를 역할별 에이전트로 분리 + 전체 워크플로우 완성

```
구현:
├─ Scout Agent (사이트 분석)
│   ├─ Accessibility Tree 스냅샷 → 사이트 구조 리포트
│   ├─ CDP 네트워크 감시 → Hidden API 발견
│   └─ 로그인/인증 필요 여부 판단
│
├─ Planner Agent (실행 계획 수립)
│   ├─ Goal 분석 → 태스크 유형 분류
│   ├─ Direction 활용 → 스텝 계획 생성
│   └─ 체크포인트 설정 (위험 액션 전)
│
├─ Auth Agent (인증 처리)
│   ├─ 전략 1: 로그인 플로우 실행
│   ├─ 전략 2: Chrome 프로필 세션 재사용
│   ├─ 전략 3: 쿠키/토큰 파일 로드
│   └─ storageState 저장/공유
│
├─ Executor Agent (태스크 실행)
│   ├─ Direction 기반 순차 체이닝
│   ├─ Observer Hooks (on_step_start/end)
│   └─ 다층 에러 복구 (5단계 폴백)
│
├─ 민감 데이터 플레이스홀더 (Auth 보안)
│
└─ 검증: 시나리오 A (호갱노노 전체 흐름) 완료
    ├─ Scout → Planner → Auth → Executor 파이프라인
    ├─ Direction 유무에 따른 스텝 수 비교
    └─ Hidden API 발견 + 활용 성공 여부
```

### Phase 1-C: 품질 + 안정화 (1~2주)

**목표**: 검증, 에러 복구, 멀티사이트 지원

```
구현:
├─ Validator Agent (결과 검증)
│   ├─ Pydantic 스키마 기반 자동 검증
│   ├─ Constraint 검증 (도메인 규칙)
│   └─ 검증 실패 → Executor에게 재수집 요청
│
├─ 확장 액션 추가
│   ├─ hover, dblclick, eval, extract 등
│   └─ Tools 데코레이터 기반 확장 구조
│
├─ 안정화
│   ├─ 세션 자동 녹화 (Playwright Tracing)
│   ├─ Cost Circuit Breaker (비용 한도)
│   └─ 에러 복구 전체 테스트
│
└─ 검증: 시나리오 B (네이버 카페 글 작성) + 멀티사이트
    ├─ 액션 실행형 태스크 완료
    ├─ 복수 사이트 테스트 (호갱노노, 네이버부동산, 직방 등)
    └─ 체크포인트 (위험 액션 전 사용자 확인) 동작 확인
```

---

## X. Phase 1-A 구현 중 발견 사항 (2026-02-24)

Phase 1-A 구현 및 테스트 과정에서 발견한 문제와 해결 패턴을 기록한다.
후속 Phase에서 반드시 고려해야 할 항목들이다.

### 1. 오버레이/팝업 요소의 클릭 차단 문제

**현상**: 호갱노노 등 SPA 사이트에서 지도 레이어, 모달, 쿠키 동의 배너 등의 오버레이 `<div>`가
인터랙티브 요소 위를 덮어 Playwright `handle.click()`이 타임아웃 발생.

```
<div class="css-1sry7v"></div> subtree intercepts pointer events
→ ElementHandle.click: Timeout 5000ms exceeded
```

**해결 (Phase 1-A)**: 일반 클릭 → 실패 시 `force=True` 재시도

```python
try:
    await handle.click(timeout=5000)
except Exception:
    await handle.click(force=True, timeout=5000)
```

**Phase 1-B 이후 개선 방향**:
- Observer Agent에서 오버레이 자동 감지 → 닫기 버튼 클릭 또는 overlay dismiss
- force 클릭 사용 시 로그 기록 → 통계 수집 (어떤 사이트에서 빈번한지)
- CDP `DOM.removeNode()`로 오버레이 레이어 직접 제거하는 전략 추가

### 2. 컨테이너 요소의 텍스트 합산 문제

**현상**: `get_indexed_state()`에서 `textContent`가 모든 하위 요소의 텍스트를 합쳐서 가져옴.
부모 `<button>` 안에 자식 `<button>`이 중첩된 구조에서 부모가 수백 자 텍스트로 추출됨.

```
[1] button: "검색검색하기매매유형평형가격세대수입주년차..."  ← 잘못된 추출
```

**해결 (Phase 1-A)**: 두 가지 필터 적용
1. 내부에 인터랙티브 자식이 있는 컨테이너는 건너뜀: `if (el.querySelector(selector)) return;`
2. 직접 자식 텍스트 노드만 먼저 추출, 없으면 `textContent` fallback

**Phase 1-B 이후 개선 방향**:
- `aria-label` 우선도를 더 높이고, `textContent` 대신 `innerText` 사용 검토
- Shadow DOM 내부 요소 탐색 지원
- iframe 내부 요소 탐색 지원

### 3. Playwright API 호환성

**현상**: Playwright 1.57에서 `page.accessibility.snapshot()` API 제거됨.
기존 browser-use 방식의 Accessibility Tree 기반 추출이 동작하지 않음.

**해결 (Phase 1-A)**: JavaScript `page.evaluate()`로 `document.querySelectorAll()` 기반 직접 추출로 전환.
Playwright 버전에 관계없이 안정적으로 동작.

**Phase 1-B 이후 개선 방향**:
- CDP `Accessibility.getFullAXTree`로 더 풍부한 접근성 정보 획득 검토
- ARIA 속성(aria-expanded, aria-selected 등) 추출 확대

### 4. SPA(Single Page Application) 페이지 전환 감지

**현상**: 호갱노노 같은 SPA에서는 검색 실행 후 URL이 변경되지 않음.
`wait_for_url()` 기반 페이지 전환 감지가 동작하지 않음.

**Phase 1-B 이후 개선 방향**:
- DOM 변경 감지 (MutationObserver) 기반 페이지 전환 판단
- 요소 수 변화량 비교 (이전 state vs 현재 state)
- URL + DOM 변화 복합 판단 로직

### 5. Headless 모드 기본값 문제

**현상**: Linux 서버 환경(X server 없음)에서 `HEADLESS` 기본값이 `false`이므로
Chromium이 headed 모드로 실행을 시도하여 `Missing X server or $DISPLAY` 오류 발생.

```
browserType.launch: Target page, context or browser has been closed
→ Missing X server or $DISPLAY
```

**해결 (Phase 1-A)**: 테스트 시 `BrowserManager(headless=True)` 명시 또는 `HEADLESS=true` 환경변수 설정.

**Phase 1-B 이후 개선 방향**:
- 서버 환경 자동 감지: `$DISPLAY` 미설정 시 자동으로 headless 전환
- config.py에서 환경별 기본값 분기 (로컬 개발 vs 서버 배포)

### 6. Playwright evaluate_handle 인자 전달 제한

**현상**: `page.evaluate_handle(js_code, index, selector)` 호출 시
Playwright가 positional argument 2~3개만 허용하여 오류 발생.

```
Page.evaluate_handle() takes from 2 to 3 positional arguments but 4 were given
```

**해결 (Phase 1-A)**: 여러 인자를 배열 하나로 래핑하고, JS 측에서 구조분해.

```python
# 수정 전 (오류)
handle = await page.evaluate_handle(js, index, selector)

# 수정 후
handle = await page.evaluate_handle(js, [index, selector])
# JS: ([targetIndex, selector]) => { ... }
```

**Phase 1-B 이후 개선 방향**:
- 유틸 함수로 래핑하여 일관된 인자 전달 패턴 강제
- Playwright API 변경 시 영향 최소화

### 7. JavaScript 문자열 내 이스케이프 시퀀스 경고

**현상**: `page.evaluate()` 인자로 전달하는 JavaScript 코드에 정규식 `\s`가 포함되면
Python 3.12+ 에서 `SyntaxWarning: invalid escape sequence '\s'` 발생.

**해결 (Phase 1-A)**: 문자열을 raw string으로 변경.

```python
# 수정 전 (경고)
await page.evaluate("""...\s...""")

# 수정 후
await page.evaluate(r"""...\s...""")
```

**Phase 1-B 이후 개선 방향**:
- 모든 JavaScript 코드 블록을 별도 `.js` 파일로 분리하거나 raw string 사용 통일
- linter 룰 추가로 일반 문자열 내 `\s`, `\d` 등 감지

### 8. UI WebSocket 메시지에 start_url 미전달

**현상**: `main.html`의 Execute 버튼 클릭 시 WebSocket 메시지에 `start_url` 필드가 없어서
서버가 `start_url=None`으로 수신. 브라우저가 `about:blank`에 머무른 채 LLM이 빈 URL로
navigate를 시도하여 반복 오류 발생.

```
Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log: - navigating to "", waiting until "domcontentloaded"
```

**해결 (Phase 1-A)**: UI에 Start URL 입력 필드 추가 및 WebSocket 메시지에 `start_url` 포함.

```javascript
// main.html — Start URL input 추가
<input id="start-url-input" type="url" placeholder="https://example.com"/>

// WebSocket 메시지에 start_url 포함
ws.send(JSON.stringify({
    type: 'run',
    goal: goal,
    start_url: startUrlInput.value.trim() || null,
    direction: directionInput.value.trim() || null,
}));
```

**Phase 1-B 이후 개선 방향**:
- Goal 텍스트에서 URL 자동 추출 (정규식 또는 LLM 파싱)
- start_url 없이도 LLM이 자체적으로 검색엔진부터 시작하는 전략
- 최근 사용한 URL 히스토리 드롭다운

### 9. 팝업/오버레이 자동 제거 전략 (2-레이어)

**현상**: start_url 접속 시 사이트마다 쿠키 동의 배너, 광고 팝업, 모달, 뉴스레터 구독 등
예측 불가능한 오버레이가 등장하여 태스크 수행을 방해함.

**해결 (Phase 1-A)**: 코드 레벨 + 프롬프트 레벨 2중 방어 적용.

**레이어 1 — 코드 레벨 자동 제거 (`BrowserManager.dismiss_overlays()`)**:
- start_url 이동 직후 자동 실행 (LLM 호출 전)
- 공통 닫기 버튼 셀렉터 매칭: 쿠키 프레임워크(OneTrust, CMP 등), 한국어/영어 닫기 버튼
- position:fixed + z-index≥100 + 화면 50% 이상 차지하는 요소 DOM 직접 제거
- LLM 토큰 소모 없이 즉시 처리

**레이어 2 — 프롬프트 레벨 (SYSTEM_PROMPT 규칙 6)**:
- "팝업, 모달, 쿠키 동의 배너, 광고 오버레이가 보이면 태스크 전에 먼저 닫기"
- 코드 레벨에서 놓친 비정형 오버레이를 LLM이 유연하게 처리
- LLM 스텝 1~2회 소모되지만 다양한 패턴에 대응 가능

**Phase 1-B 이후 개선 방향**:
- Observer Agent에서 오버레이 자동 감지 → 닫기 전략 학습
- 사이트별 오버레이 패턴 캐시 (한 번 발견한 패턴을 재방문 시 즉시 적용)
- dismiss_overlays() 셀렉터를 사이트별로 확장 가능한 설정 파일로 분리
- CDP `DOM.removeNode()`로 더 정밀한 오버레이 제거

### 10. LLM 액션 응답 형식 불일치

**현상**: LLM이 `{"action": "scroll(down, 800)"}` 처럼 함수 호출 형태로 응답하여
`execute_action()`의 `case "scroll"`에 매칭되지 않음. `Unsupported action: scroll(down, 800)` 오류 반복.

**해결 (Phase 1-A)**: `parse_action()`에서 `action(args)` 형태를 분해하는 로직 추가.
`scroll(down, 800)` → `action="scroll", direction="down", amount=800`. click, input, keys, navigate, wait, done 모두 지원.

또한 SYSTEM_PROMPT를 개선:
- JSON 응답 예시를 필드 분리 형식으로 명시
- "검색은 keys Enter가 가장 확실" 팁 추가
- "같은 액션 3회 반복 금지" 규칙 추가

**Phase 1-B 이후 개선 방향**:
- LLM 응답 검증 레이어 (JSON Schema 기반 validation)
- 응답 형식 오류 시 자동 재요청 (retry with format correction)

### 11. Human-in-the-Loop (사람 개입) 설계

**현상**: Phase 1-A에서 에이전트가 팝업을 못 찾거나 잘못된 액션을 반복할 때,
사람이 개입할 방법이 없음. 현재 `stop`은 완전 취소만 가능.

**현재 상태 (Phase 1-A)**:
- 에이전트 → 사람: `ask_human` 액션 존재 (LLM이 자발적으로 결정할 때만)
- 사람 → 에이전트: `stop`(완전 취소)만 가능, 일시정지/지시 주입 불가
- 사람의 브라우저 조작 감지: 이미 동작 (매 스텝마다 `get_indexed_state()` 재실행)

**Phase 1-B 구현 계획 — 3가지 개입 모드**:

```
[모드 1] Pause/Resume — 에이전트 일시정지 후 사람이 브라우저 직접 조작
  사람: [Pause] → 에이전트 대기 → 사람이 팝업 닫기 → [Resume] → 다음 스텝에서 변경 감지

[모드 2] Instruct — 멈추지 않고 다음 스텝에 지시 주입
  사람: { type: "instruct", hint: "검색버튼 대신 Enter 키를 사용해" }
  → 다음 invoke_llm() 호출 시 human_hint로 전달

[모드 3] Pause + Instruct — 정지 후 지시와 함께 재개
  사람: [Pause] → 브라우저 조작 + 지시 작성 → [Resume + hint]
```

**구현에 필요한 변경 (3곳)**:

1. **server.py**: WebSocket 메시지 타입 추가 (pause, resume, instruct)
   → `asyncio.Queue`로 agent_loop에 전달

2. **agent_loop.py**: 매 스텝 시작 전 개입 포인트 체크
   ```python
   human_hint = await check_human_intervention(queue)
   state = await get_indexed_state(page)  # 사람 조작 결과 자동 반영
   llm_response = await invoke_llm(..., human_hint=human_hint)
   ```

3. **main.html**: Pause/Resume 버튼 + 지시 입력 필드 UI 추가

**핵심 설계 원칙**:
- 사람의 브라우저 조작은 별도 감지 로직 불필요 (Observation 단계에서 자동 반영)
- 사람의 텍스트 지시는 `invoke_llm()`의 `human_hint` 파라미터로 LLM에게 전달
- Pause 중에도 브라우저는 열려있어 사람이 자유롭게 조작 가능

### 12. Obstruction 기반 클릭 아키텍처 — elementFromPoint + 5-Phase Click + State Fingerprint (2026-03-06)

**현상**: 호갱노노 등 실제 사이트에서 로그인 버튼 클릭 시 sticky 배너(div.css-1sry7v, position:fixed, z-index:15)가
버튼 위를 덮고 있어 Playwright `click()`이 배너를 클릭함. 이를 해결하려 `force: True`로 전환하면
이벤트 버블링이 생략되어 React/Vue 이벤트 핸들러가 동작하지 않음. 결과적으로 로그인 모달이 열리지 않는데,
LLM은 상태 변화 없이도 "모달이 열렸다"고 hallucinate하며 존재하지 않는 input에 타이핑을 시도함.

**문제 체인**:
```
sticky 배너가 버튼 덮음 → normal click이 배너에 도달
→ force click으로 전환 → React 핸들러 무시됨 → 모달 안 열림
→ 상태 변화 없음 → LLM이 모달 열렸다고 hallucinate
→ 존재하지 않는 input에 타이핑 시도 → 무한 반복
```

**근본 원인 분석**: 기존 `dismiss_overlays()`는 z-index≥100 + 화면 50%+ 요소만 제거하므로
z-index:15의 작은 sticky 배너는 탐지 불가. 또한 "클릭 전에 방해물이 있는지 확인"하는 메커니즘 자체가 없었음.
force click은 방해물을 우회하지만 SPA 이벤트 시스템도 우회하는 부작용이 있음.

**해결 (Phase 1-A) — 3-Pillar 아키텍처**:

#### Pillar 1: Pre-Click Obstruction Detection (`browser.py`)

`elementFromPoint()` API를 사용하여 클릭 대상 요소의 3개 지점(중앙, 좌상단+5px, 우하단-5px)에서
실제로 어떤 요소가 최상위에 있는지 검사. ARIA 속성이나 z-index 임계값에 의존하지 않으므로
모든 종류의 overlapping 요소를 탐지 가능.

```python
# browser.py — check_obstruction(page, aidx)
_CHECK_OBSTRUCTION_JS = '''
(aidx) => {
    const el = document.querySelector(`[data-aidx="${aidx}"]`);
    if (!el) return { obstructed: false };
    const rect = el.getBoundingClientRect();
    const points = [
        [rect.left + rect.width/2, rect.top + rect.height/2],  // 중앙
        [rect.left + 5, rect.top + 5],                          // 좌상단
        [rect.right - 5, rect.bottom - 5],                      // 우하단
    ];
    for (const [x, y] of points) {
        const top = document.elementFromPoint(x, y);
        if (top && top !== el && !el.contains(top) && !top.contains(el)) {
            return {
                obstructed: true,
                blocker_tag: top.tagName,
                blocker_class: top.className,
                blocker_style: {
                    position: getComputedStyle(top).position,
                    zIndex: getComputedStyle(top).zIndex
                }
            };
        }
    }
    return { obstructed: false };
}
'''
```

**Obstruction 해결 4단계** (`resolve_obstruction()`):
1. **dismiss_button** — 방해 요소 내부의 닫기 버튼 탐색 (✕, 닫기, close 등)
2. **css_hide** — `display: none !important` 적용 (DOM 유지, 레이아웃만 제거)
3. **scroll** — `scrollIntoView({ block: 'center' })` 후 재검사
4. **dom_removal** — `element.remove()`로 DOM에서 완전 제거 (최후 수단)

#### Pillar 2: 5-Phase Click Strategy (`actions.py`)

기존의 `force: True` 단일 전략을 5단계 점진적 전략으로 교체:

```python
# actions.py — execute_action() 내 click 처리
# Phase 1: Modal Scope Check
#   → 모달이 열려있으면 모달 내부 요소만 클릭 허용

# Phase 2: Obstruction Detection + Resolution
#   → check_obstruction() → 방해물 발견 시 resolve_obstruction()
#   → 해결 후 재검사 (obstructed: false 확인)

# Phase 3: Normal Click (scrollIntoView + click)
#   → scrollIntoView({ block: 'center', behavior: 'instant' })
#   → el.click() — React/Vue 이벤트 체인 정상 동작

# Phase 4: dispatchEvent Fallback
#   → new MouseEvent('click', { bubbles: true, cancelable: true })
#   → mousedown → mouseup → click 전체 시퀀스 dispatch
#   → Phase 3 실패 시 (예: Shadow DOM, custom element)

# Phase 5: Force Click (최후 수단)
#   → page.locator(...).click(force=True)
#   → SPA 핸들러 우회 가능성 있지만, 위 4단계 모두 실패 시에만
```

**핵심 원칙**: normal click을 최우선으로 시도하여 SPA 이벤트 시스템을 존중.
force click은 모든 수단이 실패한 최후에만 사용.

#### Pillar 3: Post-Action State Fingerprint (`agent_loop.py` + `client.py`)

클릭 전후의 페이지 상태를 구조적으로 비교하여 "실제로 변화가 발생했는지" 판별:

```python
# browser.py — get_state_fingerprint(page)
_STATE_FINGERPRINT_JS = '''
() => ({
    url: location.href,
    title: document.title,
    has_modal: !!(document.querySelector('[role=dialog]') ||
              document.querySelector('.modal.show')),
    focus_tag: document.activeElement?.tagName || '',
    interactive_count: document.querySelectorAll(
        'a,button,input,select,textarea,[role=button],[onclick]'
    ).length
})
'''

# agent_loop.py — 매 액션 전후 비교
prev_fp = await browser.get_state_fingerprint(page)
await execute_action(action, page, browser=browser)
post_fp = await browser.get_state_fingerprint(page)

state_changed = (prev_fp != post_fp)
if not state_changed:
    no_change_count += 1
if no_change_count >= 2:
    # invoke_llm()에 경고 전달
    no_state_change_warning = True
```

**LLM Anti-Hallucination 규칙** (`client.py` SYSTEM_PROMPT Rule 8):
```
Rule 8: 직전 액션 이후 페이지 상태가 변하지 않았다면,
같은 액션을 반복하지 마세요. 특히 모달/폼이 실제로 열렸는지
확인 없이 input 액션을 시도하지 마세요.
```
→ `no_state_change_warning=True`일 때 LLM 프롬프트에 주입되어
   상태 변화 없는 상황에서의 hallucination 차단.

**검증 결과 (hogangnono.com)**:
```
1. resolve_blocker() → "게이트웨이 광고" 팝업 제거 (dom_removal) ✅
2. check_obstruction(aidx=116) → div.css-1sry7v (fixed, z-index:15) 탐지 ✅
3. resolve_obstruction() → css_hide (display:none) 적용 ✅
4. 재검사 → obstructed: false ✅
5. Normal click (force 없이!) → 성공 ✅
6. State fingerprint → interactive_count 76→88, state_changed=True ✅
```

**변경 파일 (6개)**:
| 파일 | 변경 내용 |
|------|----------|
| `src/core/browser.py` | `check_obstruction()`, `resolve_obstruction()`, `get_state_fingerprint()` 추가 |
| `src/core/actions.py` | force click → 5-Phase 전략으로 전면 교체 |
| `src/core/agent_loop.py` | fingerprint 비교 + `no_state_change_warning` 전달 |
| `src/llm/client.py` | SYSTEM_PROMPT Rule 8 + `no_state_change_warning` 파라미터 |
| `src/core/state.py` | Interaction Scope (Phase 7-A 모달 감지) — 이전 세션 구현 |
| `test_obstruction.py` | hogangnono.com 통합 테스트 (신규) |

**Phase 1-B 이후 개선 방향**:
- 로그인 모달 감지 강화: ARIA 속성 없는 모달도 탐지 (visibility/display 변화 감시, MutationObserver)
- Obstruction 패턴 캐시: 사이트별로 발견된 blocker 셀렉터를 저장하여 재방문 시 즉시 제거
- resolve_obstruction 전략 우선순위 학습: 사이트별 성공률 기반 전략 순서 최적화
- interactive_count 외 추가 fingerprint: DOM 트리 해시, scroll position, network idle 상태
- Phase 4 (dispatchEvent) 고도화: PointerEvent 지원, Touch 이벤트 시뮬레이션 (모바일 뷰)

### 13. `asyncio` 변수 스코핑 버그 — click/input 액션 실행 실패 (2026-03-06)

**현상**: Obstruction 기반 아키텍처(Section 12) 적용 후, 차단 해소까지는 성공하지만
그 직후 `await asyncio.sleep(0.3)` 호출 시 `cannot access local variable 'asyncio' where it is not associated with a value` 에러 발생.
click 액션은 차단이 이미 제거된 재시도에서 해당 라인을 타지 않아 우연히 성공하지만,
input 액션은 매번 차단 해소 → sleep 경로를 거쳐 5회 연속 실패.

**근본 원인**: `execute_action()` 함수 내 `case "wait":` 블록(line 366)에 `import asyncio`가 중복 존재.
Python은 함수 컴파일 시 해당 import를 **함수 전체의 로컬 변수 할당**으로 인식.
`match/case`는 별도 스코프가 아닌 동일 함수 스코프이므로,
`case "click"`이나 `case "input"`에서 `asyncio.sleep()`을 호출할 때
아직 할당되지 않은 로컬 변수에 접근 → `UnboundLocalError`.

```
actions.py 내 asyncio 참조 구조:

line  12: import asyncio              ← 모듈 레벨 (정상)
line 215: await asyncio.sleep(0.3)    ← case "click" 내부 (모듈 레벨 참조 기대)
line 290: await asyncio.sleep(0.3)    ← case "input" 내부 (모듈 레벨 참조 기대)
line 366: import asyncio              ← case "wait" 내부 (❌ 함수 전체를 오염)

→ Python 컴파일러: line 366 때문에 asyncio를 로컬로 판단
→ line 215, 290 실행 시 로컬 asyncio가 아직 바인딩 안 됨 → UnboundLocalError
```

**해결**: `case "wait":` 내부의 중복 `import asyncio` (line 366) 삭제.
모듈 레벨 import (line 12)로 충분.

**변경 파일 (1개)**:
| 파일 | 변경 내용 |
|------|----------|
| `src/core/actions.py` | `case "wait":` 내부의 `import asyncio` 1줄 삭제 |

**Phase 1-B 이후 개선 방향**:
- 함수 내부 import 패턴 전수 검사 (같은 유형의 스코핑 버그 예방)
- `import base64` (line 355, `case "screenshot"`)도 동일 패턴이나 다른 case에서 base64를 참조하지 않아 현재는 무해. 향후 참조 추가 시 같은 버그 발생 가능

### Phase 2: 자가학습 + VLM 실험 (2-4개월)

**목표**: 패턴 학습으로 반복 비용 감소 + VLM 효과 실증

```
구현:
├─ Pattern Compiler (성공 패턴 → 결정론적 코드)
├─ VLM A/B 테스트 실행:
│   ├─ Accessibility Tree만 → 성공률 X%
│   └─ Accessibility Tree + Screenshot → 성공률 Y%
│   → 차이가 유의미하면 VLM 정식 도입, 아니면 보류
├─ Evaluation Harness (크롤러 CI)
├─ Tiered Escalation 완성 (CDP → LLM → VLM → Human)
├─ 서브에이전트 병렬 실행
└─ 데이터: "VLM이 실제로 필요한 비율은?" 정량 리포트
```

### Phase 3: 스케일 (4-6개월)

**목표**: 대규모 운영 + 비용 최적화

```
구현:
├─ 스케줄러 (Layer 4) — 반복 크롤링 자동화
├─ 분산 실행 (Celery/Ray)
├─ 계정 풀 관리 (Auth Agent 확장)
├─ AgentSymbiotic (경량 모델로 일상 크롤링)
├─ Micro-Task Queue (5% 어려운 케이스 → 사람)
└─ 100만 페이지/월 목표
```

---

## 참고 프로젝트

| 프로젝트 | 참고 포인트 | 차용한 것 | URL |
|---|---|---|---|
| **Browser-use** | CLI: state 인덱싱, Action Space, 프로필 동기화 / Python API: 멀티에이전트, Lifecycle Hooks, 에러 복구, Sensitive Data, Structured Output, Tools 데코레이터 | **CLI 차용 5가지**: 인덱스 기반 상태, 확장 Action Space, Auth 전략 다양화, 3-Tier 브라우저 모드, 서브에이전트 병렬 / **API 차용 7가지**: 순차 체이닝, 병렬 수집, Observer Hooks, 다층 에러 복구, 민감 데이터 플레이스홀더, Pydantic 스키마 검증, 커스텀 액션 확장 | github.com/browser-use/browser-use |
| **Bowser** | 4-layer 아키텍처, playwright-cli | Layer 1~4 계층 구조 | github.com/disler/bowser |
| **Anchor Browser** | UI/UX (브라우저 시각화 + 로그), 세션 녹화 | 레이아웃 설계, 개입 포인트 가시화 | anchorbrowser.io |
| **Crawl4AI** | 오픈소스 LLM 크롤러 구조 | (참고만) | github.com/unclecode/crawl4ai |
| **Skyvern** | VLM 기반 자동화 (비용 문제의 반면교사) | (반면교사 — VLM 보류 근거) | github.com/Skyvern-AI/skyvern |
