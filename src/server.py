"""Agentic Browser FastAPI 서버

UI와 에이전트를 연결하는 백엔드 서버.
- GET /: UI 페이지 서빙
- WebSocket /ws: 실시간 에이전트 로그 스트리밍
- POST /api/run: 에이전트 태스크 실행

HEADLESS=true python -m uvicorn src.server:app --host 0.0.0.0 --port 1234
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.core.browser import BrowserManager
from src.core.agent_loop import run_agent_loop, StepLog, AgentResult
from src.llm.client import create_llm
from src.config import SERVER_HOST, SERVER_PORT

# 로그 디렉토리 및 파일 설정
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
_log_file = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_file_handler)
logging.root.addHandler(_console_handler)

logger = logging.getLogger(__name__)
logger.info(f"로그 파일: {_log_file}")

app = FastAPI(title="Agentic Browser")

# UI 파일 경로
UI_PATH = Path(__file__).parent / "main.html"

# 활성 WebSocket 연결 목록
active_connections: list[WebSocket] = []

# 현재 실행 중인 에이전트 태스크
current_task: asyncio.Task | None = None

# ask_human 응답 대기용 Future
pending_human_future: asyncio.Future | None = None


async def broadcast(message: dict) -> None:
    """모든 WebSocket 클라이언트에 메시지 브로드캐스트"""
    text = json.dumps(message, ensure_ascii=False)
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        active_connections.remove(ws)


@app.get("/")
async def serve_ui():
    """UI 페이지 서빙"""
    html = UI_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 연결 — 에이전트 로그 실시간 스트리밍"""
    await ws.accept()
    active_connections.append(ws)
    logger.info(f"WebSocket 연결 (총 {len(active_connections)}개)")

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "run":
                # 에이전트 실행 요청
                goal = message.get("goal", "")
                direction = message.get("direction", "") or None
                start_url = message.get("start_url", "") or None

                if not goal:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": "Goal이 비어있습니다.",
                    }))
                    continue

                # 이전 태스크가 실행 중이면 취소
                global current_task
                if current_task and not current_task.done():
                    current_task.cancel()
                    await broadcast({"type": "status", "status": "cancelled"})

                # 새 태스크 시작
                current_task = asyncio.create_task(
                    run_agent_task(goal, direction, start_url)
                )

            elif msg_type == "human_response":
                # 사용자 응답 수신 → 대기 중인 Future 해제
                global pending_human_future
                response_text = message.get("response", "")
                if pending_human_future and not pending_human_future.done():
                    pending_human_future.set_result(response_text)
                    logger.info(f"사용자 응답 전달: {response_text[:100]}")
                else:
                    logger.warning("대기 중인 ask_human 요청이 없습니다.")

            elif msg_type == "stop":
                # 에이전트 중지 요청
                if current_task and not current_task.done():
                    current_task.cancel()
                    await broadcast({
                        "type": "status",
                        "status": "stopped",
                        "message": "에이전트가 중지되었습니다.",
                    })

    except WebSocketDisconnect:
        active_connections.remove(ws)
        logger.info(f"WebSocket 해제 (총 {len(active_connections)}개)")


async def run_agent_task(
    goal: str,
    direction: str | None = None,
    start_url: str | None = None,
) -> None:
    """에이전트 태스크를 실행하고 결과를 WebSocket으로 스트리밍"""

    # 시작 알림
    await broadcast({
        "type": "status",
        "status": "running",
        "message": f"에이전트 시작: {goal}",
    })

    browser = BrowserManager()

    try:
        # LLM 생성
        llm = create_llm()

        # 브라우저 시작
        await browser.start()
        await broadcast({
            "type": "log",
            "agent": "System",
            "message": "브라우저 시작 완료",
        })

        # 스텝 콜백: 매 스텝마다 UI로 전송
        async def on_step(step_log: StepLog):
            await broadcast({
                "type": "step",
                "step": step_log.step,
                "timestamp": step_log.timestamp,
                "url": step_log.url,
                "action": step_log.action,
                "detail": step_log.detail,
                "success": step_log.success,
                "screenshot": step_log.screenshot_b64,
            })

        # ask_human 콜백: 질문을 UI로 전송하고 사용자 응답 대기
        async def on_ask_human(question: str) -> str:
            global pending_human_future
            pending_human_future = asyncio.get_event_loop().create_future()
            await broadcast({
                "type": "ask_human",
                "question": question,
            })
            await broadcast({
                "type": "status",
                "status": "waiting",
                "message": f"사용자 응답 대기 중: {question[:50]}",
            })
            # 사용자가 응답할 때까지 대기
            response = await pending_human_future
            pending_human_future = None
            await broadcast({
                "type": "status",
                "status": "running",
                "message": "에이전트 재개",
            })
            return response

        # 에이전트 루프 실행
        result = await run_agent_loop(
            browser=browser,
            llm=llm,
            goal=goal,
            direction=direction,
            start_url=start_url,
            on_step=on_step,
            on_ask_human=on_ask_human,
        )

        # 완료 알림
        await broadcast({
            "type": "result",
            "success": result.success,
            "message": result.message,
            "total_steps": result.total_steps,
            "failure_count": result.failure_count,
            "data": result.data,
        })

    except asyncio.CancelledError:
        logger.info("에이전트 태스크 취소됨")
        await broadcast({
            "type": "status",
            "status": "cancelled",
            "message": "에이전트가 취소되었습니다.",
        })

    except Exception as e:
        logger.error(f"에이전트 실행 오류: {e}")
        await broadcast({
            "type": "error",
            "message": f"에이전트 오류: {str(e)}",
        })

    finally:
        await browser.close()
        await broadcast({
            "type": "status",
            "status": "idle",
            "message": "브라우저 종료, 대기 중",
        })


def main():
    """서버 시작"""
    import uvicorn
    uvicorn.run(
        "src.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
        reload_dirs=["src"],
        reload_excludes=["logs/*", "*.log", "__pycache__/*", "*.pyc", ".omc/*"],
    )


if __name__ == "__main__":
    main()
