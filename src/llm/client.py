"""LLM 클라이언트 모듈

LangChain을 통해 Claude / GPT-4o 등 다양한 LLM에 접근한다.
에이전트 루프에서 사용하는 단일 인터페이스를 제공.
"""

import logging
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from src.config import (
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_MODEL,
)

logger = logging.getLogger(__name__)

# 에이전트 시스템 프롬프트
SYSTEM_PROMPT = """\
당신은 웹 브라우저를 조작하는 에이전트입니다.
사용자의 태스크를 수행하기 위해 브라우저 페이지의 요소를 분석하고 적절한 액션을 결정합니다.

## 규칙
1. 반드시 JSON 형식으로만 응답하세요.
2. 한 번에 하나의 액션만 결정하세요.
3. index는 제공된 요소 목록의 번호를 정확히 사용하세요.
4. 태스크가 완료되면 반드시 done 액션을 사용하세요.
5. 막히거나 확신이 없으면 ask_human 액션을 사용하세요.
6. 페이지에 팝업, 모달, 쿠키 동의 배너, 광고 오버레이 등이 보이면 태스크 수행 전에 먼저 닫기(X 버튼, "닫기", "Close", "동의" 등) 버튼을 클릭하여 제거하세요. 오버레이가 태스크 수행을 방해할 수 있습니다.

## 응답 형식
action 필드에는 액션명만 쓰고, 파라미터는 별도 필드로 지정하세요.
```json
{ "action": "click", "index": 5, "reason": "검색 버튼 클릭" }
{ "action": "input", "index": 3, "text": "검색어", "reason": "검색어 입력" }
{ "action": "scroll", "direction": "down", "amount": 500, "reason": "아래로 스크롤" }
{ "action": "keys", "combo": "Enter", "reason": "검색 실행" }
```

## 사용 가능한 액션
- click: 요소 클릭. 필드: index
- input: 텍스트 입력 (기존 내용 대체). 필드: index, text
- keys: 키보드 입력. 필드: combo (예: "Enter", "Control+a")
- select: 드롭다운 옵션 선택. 필드: index, option
- scroll: 스크롤. 필드: direction ("up"/"down"), amount (픽셀)
- navigate: URL로 이동. 필드: url
- screenshot: 현재 화면 캡처
- wait: 대기. 필드: amount (초)
- done: 태스크 완료. 필드: result (결과 요약 텍스트). **중요**: result에 반드시 수집된 정보를 포함한 완성된 답변을 작성하세요. "태스크 완료"만 쓰지 마세요.
- ask_human: 사용자에게 질문. 필드: question. **주의**: 스스로 판단할 수 있는 것은 질문하지 마세요. 정말 사용자만 결정할 수 있는 것만 물어보세요.

## memo 필드 (선택적)
모든 액션에 "memo" 필드를 추가로 포함할 수 있습니다.
현재 페이지에서 태스크에 관련된 핵심 정보를 발견했다면, 다음 액션과 함께 memo에 기록하세요.
memo에 기록한 내용은 이후 스텝에서 "수집된 정보"로 계속 제공됩니다.

중요: memo에는 반드시 실제 데이터를 기록하세요.
- 좋은 memo: "맛집A: 한남동 OO로, 평점 4.5, 파스타 전문점, 1인당 2만원"
- 나쁜 memo: "맛집 정보를 수집하겠습니다", "상세 내용 확인 예정"
"~할 예정", "~하겠습니다" 같은 계획이나 의도는 memo가 아닙니다.
페이지에서 실제로 읽은 구체적인 정보(이름, 수치, 사실)만 기록하세요.

예시:
```json
{ "action": "click", "index": 8, "reason": "다음 블로그로 이동", "memo": "맛집A: 한남동 OO로, 평점 4.5, 파스타 전문점" }
{ "action": "scroll", "direction": "down", "amount": 500, "reason": "더 읽기", "memo": "가격대: 1만원~2만원, 주차 가능" }
```

## 정보 수집 태스크 수행 가이드
정보를 찾아 정리해야 하는 태스크(예: "맛집 3곳 찾기", "비교 분석")의 경우:
1. 검색 또는 목록 페이지에서 관련 링크를 찾아 방문합니다.
2. 페이지 내용을 읽고, 태스크에 필요한 핵심 정보를 memo에 기록합니다.
3. 뒤로 가거나 다음 링크로 이동하여 추가 정보를 수집합니다.
4. 충분한 정보가 모이면 done 액션의 result에 수집된 정보를 종합하여 최종 답변을 작성합니다.
   - result에는 수집한 모든 정보를 구조화하여 포함하세요 (예: 제목, URL, 요약, 수치 등)
   - "태스크 완료", "정보 수집 완료" 같은 빈 결과는 절대 금지입니다
   - "수집된 정보" 섹션의 memo 내용을 반드시 종합하여 result에 포함하세요

중요: 페이지를 떠나면 해당 페이지의 내용은 사라집니다. 반드시 떠나기 전에 memo로 기록하세요.

중요: 이미 수집된 정보에 있는 내용과 동일한 링크/페이지를 다시 방문하지 마세요.
새로운 정보를 수집하기 위해 아직 방문하지 않은 링크를 선택하세요.

## 팁
- 검색창에 텍스트를 입력한 후 검색 실행은 keys("Enter")가 가장 확실합니다.
- 버튼 클릭이 반복 실패하면 다른 방법을 시도하세요 (예: keys 사용).
- 같은 액션을 3회 이상 반복하지 마세요. 다른 접근법을 선택하세요.
- "페이지 콘텐츠"는 Accessibility Tree 구조로 제공됩니다. heading, paragraph, link 등 역할을 참고하여 페이지 내용을 이해하세요.
- ask_human은 최후의 수단입니다. "기간을 선택해주세요", "진행해도 될까요?" 같은 불필요한 질문은 하지 마세요. 합리적인 판단으로 스스로 결정하고 진행하세요.
"""


def create_llm(
    provider: str | None = None,
    model: str | None = None,
) -> BaseChatModel:
    """LLM 인스턴스 생성

    Args:
        provider: "openai" 또는 "anthropic" (기본: config 설정)
        model: 모델 ID (기본: config 설정)
    """
    provider = provider or DEFAULT_LLM_PROVIDER
    model = model or DEFAULT_MODEL

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return ChatAnthropic(
            model=model,
            api_key=ANTHROPIC_API_KEY,
            max_tokens=2048,
            temperature=0,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        return ChatOpenAI(
            model=model,
            api_key=OPENAI_API_KEY,
            max_tokens=2048,
            temperature=0,
        )
    else:
        raise ValueError(f"지원하지 않는 LLM provider: {provider}")


async def invoke_llm(
    llm: BaseChatModel,
    state_text: str,
    task: str,
    direction_hint: str | None = None,
    step_history: list[str] | None = None,
    is_stuck: bool = False,
    collected_info: list[str] | None = None,
) -> str:
    """LLM에게 다음 액션을 요청

    Args:
        llm: LangChain LLM 인스턴스
        state_text: 인덱싱된 페이지 상태 텍스트
        task: 수행할 태스크
        direction_hint: Direction 경로 힌트 (선택)
        step_history: 이전 스텝 이력 (선택)
        is_stuck: 반복 패턴 감지 시 True
        collected_info: 이전 스텝에서 memo로 수집된 정보 목록 (선택)

    Returns:
        LLM 응답 텍스트 (JSON 액션)
    """
    user_prompt_parts = [
        f"## 현재 페이지 상태\n{state_text}",
        f"\n## 수행할 태스크\n{task}",
    ]

    if direction_hint:
        user_prompt_parts.append(f"\n## 경로 힌트 (Direction)\n{direction_hint}")

    if step_history:
        recent = step_history[-10:]  # 최근 10스텝으로 확대 (기존 5)
        history_text = "\n".join(f"- {s}" for s in recent)
        user_prompt_parts.append(f"\n## 이전 스텝 이력 (최근 {len(recent)}개)\n{history_text}")

    # 수집된 정보 (memo 누적)
    if collected_info:
        info_text = "\n".join(f"- {info}" for info in collected_info)
        user_prompt_parts.append(f"\n## 수집된 정보 (이전 스텝에서 memo로 기록)\n{info_text}")

    # Stuck 경고 시그널
    if is_stuck:
        user_prompt_parts.append(
            "\n## ⚠️ STUCK 경고\n"
            "동일한 액션을 여러 번 반복하고 있습니다. "
            "진전이 없으므로 반드시 다른 접근법을 시도하세요:\n"
            "- 다른 요소를 클릭해 보세요\n"
            "- 스크롤 대신 특정 요소를 클릭하세요\n"
            "- 현재 페이지에서 태스크를 수행할 수 없다면 done 또는 ask_human을 사용하세요"
        )

    user_prompt_parts.append(
        "\n## 지시\n"
        "위 페이지 상태를 분석하고, 태스크 수행을 위한 다음 액션을 JSON으로 응답하세요."
    )

    user_prompt = "\n".join(user_prompt_parts)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    logger.debug(f"LLM 요청 (토큰 절약을 위해 프롬프트 생략)")
    response = await llm.ainvoke(messages)
    result = response.content

    logger.debug(f"LLM 응답: {result[:200]}...")
    return result
