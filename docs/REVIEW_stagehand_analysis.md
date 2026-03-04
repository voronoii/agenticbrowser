# Stagehand (browserbase/stagehand) 분석 및 차용 검토

> 작성일: 2026-03-03
> 대상: https://github.com/browserbase/stagehand
> 목적: 우리 에이전틱 크롤러에 차용할 수 있는 아이디어 검토

---

## Stagehand 개요

Browserbase에서 만든 AI 웹 브라우저 자동화 프레임워크.
Playwright 위에 3+1개의 AI 프리미티브를 제공한다.

| 프리미티브 | 역할 | 설명 |
|-----------|------|------|
| `act()` | 행동 | 자연어로 브라우저 액션 실행 ("click the login button") | 
| `extract()` | 추출 | 페이지에서 구조화된 데이터 추출 (Zod 스키마로 타입 보장) |
| `observe()` | 관찰 | 현재 페이지에서 가능한 액션 목록 탐색 |
| `agent()` | 자율 | 위 3개를 조합해 복잡한 멀티스텝 워크플로우 자율 수행 |

핵심 철학: **"얼마나 AI에 맡길지 개발자가 제어한다"**
- 너무 에이전틱 → 예측 불가능
- 너무 결정론적 → 변화에 취약
- Stagehand → **atomic 프리미티브로 둘 사이의 균형**

---

## 아키텍처 비교

| 관점 | 우리 프로젝트 | Stagehand |
|------|-------------|-----------|
| 언어 | Python + Playwright | TypeScript + Playwright/CDP |
| 구조 | 단일 에이전트 루프 (Observation→LLM→Action) | 원자적 프리미티브 (act/extract/observe) + Agent |
| 상태 추출 | 커스텀 DOM JS + innerText (2000자) | Chrome Accessibility Tree |
| 데이터 추출 | **없음** (핵심 문제!) | `extract()` + Zod 스키마 |
| 페이지 관찰 | get_indexed_state (모든 요소) | `observe()` (지시어 기반 타겟 탐색) |
| LLM 호출 | 매 스텝 무상태 (stateless) | 컨텍스트 누적 |
| 액션 실행 | JSON 파싱 → Playwright | 자연어 → 내부 요소 해석 |
| 요소 식별 | data-aidx 인덱스 주입 | XPath / Accessibility Tree 기반 |

---

## 차용 검토 결과

### 차용 추천 (복잡성 대비 가치 높음)

#### 1. `extract` 액션 개념 — 가치: HIGH, 복잡도: LOW

**Stagehand 방식:**
```typescript
const product = await stagehand.extract(
  "extract product details",
  z.object({ name: z.string(), price: z.number() })
);
```

**우리 프로젝트에 적용:**
- Zod 스키마까지 도입할 필요 없음
- LLM에게 "현재 페이지에서 태스크 관련 핵심 정보를 요약해 메모하라"는 `extract` 액션 추가
- 추출된 정보를 `collected_info` 리스트에 누적 → 매 LLM 호출 시 컨텍스트로 전달
- **이것만으로 ISSUE_agent_memory.md의 핵심 문제 해결 가능**

```python
# 에이전트가 호출하는 형태
{ "action": "extract", "text": "맛집A: 한남동 OO로, 평점 4.5, 파스타 전문점", "reason": "블로그에서 맛집 정보 수집" }
```

#### 2. `observe` 분리 패턴 — 가치: MEDIUM, 복잡도: LOW

**Stagehand 방식:**
```typescript
const actions = await page.observe("find checkout elements");
// → [{selector: "...", description: "Buy button", method: "click"}, ...]
```

**우리 프로젝트에 적용:**
- 현재는 "관찰"과 "액션 결정"이 하나의 LLM 호출에서 동시에 발생
- 복잡한 페이지에서 LLM이 압도당할 수 있음
- `observe` 액션을 추가하면 "먼저 관찰하고, 그 다음 행동"이 가능
- 단, 현재 구조에서 get_indexed_state가 이미 관찰 역할을 하므로 우선순위는 낮음

#### 3. Scoped 추출 (셀렉터 범위 제한) — 가치: MEDIUM, 복잡도: LOW

**Stagehand 방식:**
```typescript
const data = await stagehand.extract(
  "extract product info",
  ProductSchema,
  { selector: "/html/body/div/div" }  // 특정 영역만
);
```

**우리 프로젝트에 적용:**
- 현재 `_PAGE_TEXT_JS`가 body 전체 innerText를 가져옴 (2000자 제한)
- 블로그 본문 영역만 타겟팅하면 불필요한 네비게이션/광고 텍스트 제거 가능
- `extract` 액션에 선택적 `selector` 필드를 추가하여 특정 영역의 텍스트만 추출

### 참고할 만하지만 당장 불필요

#### 4. Accessibility Tree 기반 상태 추출 — 가치: MEDIUM, 복잡도: MEDIUM

**Stagehand 방식:**
- Chrome Accessibility Tree를 사용하여 페이지 표현
- DOM 파싱보다 컴팩트하고 시맨틱한 표현
- 토큰 사용량 절감

**판단:**
- Playwright의 `page.accessibility.snapshot()`으로 구현 가능
- 하지만 우리의 현재 DOM 기반 추출 + data-aidx 주입 방식이 잘 작동하고 있음
- 요소 위치 확인(data-aidx)과 Accessibility Tree는 상호 보완적이므로 병행 가능
- **현재 핵심 문제(메모리 부재)가 해결된 후 2단계로 검토**

#### 5. 자연어 액션 해석 — 가치: LOW, 복잡도: HIGH

**Stagehand 방식:**
```typescript
await page.act("click the login button");
// → 내부적으로 요소를 찾아 클릭
```

**판단:**
- 우리의 인덱스 기반 접근 (`{ "action": "click", "index": 5 }`)이 더 결정론적
- 자연어 해석은 추가 LLM 호출이 필요해 비용과 지연 증가
- 현재 방식 유지가 더 적절

### 차용하지 않을 것

| 항목 | 이유 |
|------|------|
| TypeScript + Zod 스키마 시스템 | 우리는 Python 기반, 언어 전환 불필요 |
| Browserbase 클라우드 인프라 | 로컬 실행 기반으로 충분 |
| CDP 직접 통신 (v3) | Playwright 추상화가 유지보수에 유리 |
| CUA (Computer Use Agent) 모드 | 아키텍처 전면 재설계 필요, 과도한 변경 |
| 캐싱 시스템 | 현 단계에서 불필요한 최적화 |

---

## 적용 우선순위 및 구현 계획

### Phase 1: extract 액션 + 메모리 (ISSUE_agent_memory.md 해결)

수정 파일 4개, 예상 복잡도 낮음.

| 파일 | 변경 내용 |
|------|-----------|
| `actions.py` | `extract` 액션 케이스 추가 (페이지 텍스트를 data로 반환) |
| `agent_loop.py` | `collected_info: list[str]` 도입, extract 결과 누적, LLM 호출 시 전달 |
| `client.py` | 시스템 프롬프트에 extract 사용법 추가 + 수집된 정보 섹션 + max_tokens 상향 |
| `state.py` | 페이지 텍스트 제한 2000→4000자 상향 (선택) |

### Phase 2: 상태 추출 개선 (선택)

- Accessibility Tree 보조 활용 검토
- Scoped 추출 (셀렉터 기반 영역 제한)
- observe 액션 분리 (복잡한 페이지 대응)

---

## 핵심 인사이트 요약

> Stagehand에서 가장 차용 가치가 높은 것은 `extract()` 프리미티브의 **개념**이다.
> 이는 정확히 우리 에이전트의 핵심 문제(페이지 간 정보 축적 불가)를 해결한다.
>
> 다만 Stagehand의 extract는 "LLM이 페이지를 분석해 구조화 데이터를 반환"하는 방식이고,
> 우리는 "에이전트가 스스로 메모할 내용을 결정"하는 방식으로 더 가볍게 구현할 수 있다.
>
> Stagehand 전체를 차용하거나 대체하는 것이 아니라,
> **extract 개념 + 메모리 누적 패턴**만 최소한으로 가져오는 것이 최선이다.
