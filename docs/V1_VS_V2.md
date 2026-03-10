v1 에이전트 동작 흐름 (상세)
1단계: 사용자 입력 (동일)

Goal: "토스증권에서 ACE 글로벌반도체TOP4 Plus ETF 정보를 찾아줘"
시작 URL: https://tossinvest.com
2단계: Python 코드(agent_loop.py)가 while 루프 시작
run_agent_loop() 함수가 매 스텝을 코드가 직접 제어합니다:


while step < max_steps and failure_count < max_failures:
    # 1. 코드가 자동으로 페이지 관찰 (매번 무조건)
    state = await get_indexed_state(page)
    
    # 2. 코드가 LLM 호출 (상태 + 히스토리를 넘김)
    response = await invoke_llm(llm, state, goal, step_history)
    
    # 3. 코드가 JSON 파싱
    action = parse_action(response)
    
    # 4. 코드가 액션 실행
    result = await execute_action(browser, state, action)
    
    # 5. 코드가 성공/실패 판단
    if action.action == "done":
        break
    if not result.success:
        failure_count += 1
3단계: 매 스텝의 실제 흐름
스텝 1:


[코드] get_indexed_state(page) → 209개 요소 추출
[코드] invoke_llm() → 상태 + "이 태스크를 수행하세요" 전달
[LLM]  → {"action": "click", "index": 7, "reason": "검색 버튼 클릭"} 반환
[코드] parse_action() → JSON 파싱하여 AgentAction 객체 생성
[코드] execute_action() → index 7 요소 클릭 실행
스텝 2:


[코드] get_indexed_state(page) → 다시 전체 페이지 관찰 (무조건)
[코드] invoke_llm() → 새 상태 + 이전 히스토리 전달
[LLM]  → {"action": "input", "index": 1, "text": "ACE ...", "reason": "검색어 입력"} 반환
[코드] parse_action() → JSON 파싱
[코드] execute_action() → index 1 요소에 텍스트 입력
스텝 3, 4, 5... 동일 패턴 반복

마지막 스텝:


[코드] get_indexed_state(page) → 페이지 관찰
[코드] invoke_llm() → 상태 전달
[LLM]  → {"action": "done", "result": "ETF 정보: ..."} 반환
[코드] action.action == "done" → while 루프 탈출
핵심 차이 요약
v1	v2
루프 주체	Python while 루프 (agent_loop.py)	LangGraph 프레임워크 루프
페이지 관찰	코드가 매 스텝 자동 호출	LLM이 필요할 때만 호출
LLM 역할	JSON 한 줄 반환 ({"action":"click","index":5})	도구를 자유롭게 선택·호출
LLM 응답 처리	parse_action()으로 JSON 파싱 (파싱 실패 가능)	tool calling이 구조화된 파라미터 자동 제공
한 턴에 할 수 있는 일	액션 1개	제한 없음 (observe → click → memo 연속 가능)
에러 대응	failure_count 증가 → 상한 도달 시 강제 종료	LLM이 에러 메시지를 보고 다른 전략 시도
종료 판단	"done" 액션 감지 또는 max_steps 도달	complete_task 도구 호출 또는 recursion_limit 도달
한마디로, v1에서 LLM은 "이번 턴에 뭘 할까요?"라는 질문에 한 번 대답하는 자문역이고, v2에서 LLM은 처음부터 끝까지 직접 운전하는 운전자입니다.


v2 에이전트 동작 흐름 (상세)
1단계: 사용자 입력
사용자가 UI에서 태스크를 입력합니다.


Goal: "토스증권에서 ACE 글로벌반도체TOP4 Plus ETF 정보를 찾아줘"
시작 URL: https://tossinvest.com
2단계: 에이전트 생성
서버가 create_deep_agent()를 호출하여 LangGraph 기반 에이전트를 생성합니다.

LLM 모델(gpt-5-mini 등)에 시스템 프롬프트와 11개 브라우저 도구를 바인딩
LangGraph가 "LLM 호출 → 도구 실행 → 결과를 LLM에 반환" 루프를 자동 관리
3단계: LLM이 자율적으로 도구 호출 루프 실행
여기서부터 코드가 아닌 LLM이 판단합니다. LLM은 매 턴마다 "다음에 어떤 도구를 호출할지"를 스스로 결정합니다.

턴 1 — LLM 판단: "먼저 페이지 상태를 봐야 한다"


LLM → observe_page() 호출
결과 → "209개 요소: [1] link '토스증권', [2] button ..., [7] button '검색하세요' ..."
턴 2 — LLM 판단: "검색 버튼을 눌러야 한다"


LLM → browser_click(index=7) 호출
결과 → "[7] button '검색하세요' 클릭 완료"
턴 3 — LLM 판단: "클릭 후 페이지가 바뀌었을 테니 다시 관찰"


LLM → observe_page() 호출
결과 → "⚠️ 팝업 활성화. 37개 요소: [1] searchbox '검색어를 입력해주세요' ..."
턴 4 — LLM 판단: "검색창에 ETF 이름을 입력"


LLM → browser_input(index=1, text="ACE 글로벌반도체TOP4 Plus") 호출
결과 → "[1] 입력 완료"
턴 5 — LLM 판단: "엔터를 눌러 검색 실행"


LLM → browser_keys(combo="Enter") 호출
결과 → "키보드 입력 완료: Enter"
턴 6 — LLM 판단: "검색 결과 확인"


LLM → observe_page() 호출
결과 → "검색 결과: [3] link 'ACE 글로벌반도체TOP4 Plus' ..."
턴 7 — LLM 판단: "결과 링크 클릭 + 지금 보이는 정보 메모"


LLM → browser_click(index=3, memo="ACE 글로벌반도체TOP4 Plus ETF 검색 결과 확인") 호출
결과 → "[3] 클릭 완료"
턴 8~N — 정보 수집 반복


LLM → observe_page()    → 페이지 내용 확인
LLM → record_memo(...)  → 핵심 정보 기록 (가격, 수익률 등)
LLM → browser_scroll()  → 추가 정보 확인을 위해 스크롤
LLM → observe_page()    → 스크롤 후 새로운 내용 확인
LLM → record_memo(...)  → 추가 정보 기록
마지막 턴 — LLM 판단: "충분한 정보를 모았다"


LLM → complete_task(result="ACE 글로벌반도체TOP4 Plus ETF 정보:
  - 현재가: 15,230원
  - 수익률: +2.3%
  - 운용사: 한국투자신탁운용
  - ...") 호출
4단계: 종료 감지
complete_task가 __TASK_COMPLETE__ 마커를 반환하면, run_browser_agent()가 이를 감지하고 LangGraph 루프가 종료됩니다. 결과가 WebSocket을 통해 UI로 전송됩니다.

핵심 포인트
위 과정에서 "턴 N에서 어떤 도구를 호출할지"를 결정하는 Python 코드는 없습니다. v1에서는 "매번 observe → LLM에 질문 → 응답 파싱 → 액션 실행"이 코드에 고정되어 있었지만, v2에서는 LLM이:

observe를 건너뛸 수도 있고 (이미 상태를 알고 있다면)
observe를 연속 2번 호출할 수도 있고 (스크롤 후 재확인)
에러가 나면 다른 접근법으로 전환할 수도 있고 (click 실패 → navigate로 우회)
정보가 충분하면 일찍 종료할 수도 있습니다
이 자율성이 v1 대비 v2의 핵심 차이입니다.