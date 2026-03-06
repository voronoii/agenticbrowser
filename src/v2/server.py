"""Agentic Browser v2 — FastAPI + WebSocket 서버

v1 서버와 동일한 WebSocket 프로토콜을 사용하되,
내부적으로 deepagents 기반 에이전트 루프를 실행한다.

실행:
    python -m src.v2.server
    또는
    HEADLESS=true uvicorn src.v2.server:app --host 0.0.0.0 --port 1235
"""

import asyncio
import base64
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from src.core.browser import BrowserManager
from src.v2.agent import create_browser_agent, run_browser_agent
from src.v2.config import (
    SERVER_HOST, SERVER_PORT, HEADLESS, DEFAULT_MODEL, LOG_DIR,
)

# 로그 설정
_log_file = LOG_DIR / f"agent_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_file_handler)
logging.root.addHandler(_console_handler)

logger = logging.getLogger(__name__)
logger.info(f"v2 로그 파일: {_log_file}")

app = FastAPI(title="Agentic Browser v2")

# UI 파일 경로 (v1과 공유)
UI_PATH = Path(__file__).parent.parent / "main.html"

# 활성 WebSocket 연결
active_connections: list[WebSocket] = []

# 현재 실행 중인 태스크
current_task: asyncio.Task | None = None


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
    if UI_PATH.exists():
        html = UI_PATH.read_text(encoding="utf-8")
        return HTMLResponse(content=html)
    return HTMLResponse(content="<h1>Agentic Browser v2</h1><p>UI 파일을 찾을 수 없습니다.</p>")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 연결 — 에이전트 도구 호출 실시간 스트리밍"""
    await ws.accept()
    active_connections.append(ws)
    logger.info(f"WebSocket 연결 (총 {len(active_connections)}개)")

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "run":
                goal = message.get("goal", "")
                direction = message.get("direction", "") or None
                start_url = message.get("start_url", "") or None
                preview = message.get("preview", False)

                if not goal:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": "Goal이 비어있습니다.",
                    }))
                    continue

                # 이전 태스크 취소
                global current_task
                if current_task and not current_task.done():
                    current_task.cancel()
                    await broadcast({"type": "status", "status": "cancelled"})

                current_task = asyncio.create_task(
                    run_agent_task(goal, direction, start_url, preview)
                )

            elif msg_type == "ui_log":
                # UI에서 전송한 로그를 Python logger로 기록
                agent = message.get("agent", "Unknown")
                log_msg = message.get("message", "")
                is_error = message.get("is_error", False)
                if is_error:
                    logger.error(f"main.html -> [{agent}] {log_msg}")
                else:
                    logger.info(f"main.html -> [{agent}] {log_msg}")

            elif msg_type == "stop":
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
    preview: bool = False,
) -> None:
    """에이전트 태스크 실행 및 WebSocket 스트리밍"""

    await broadcast({
        "type": "status",
        "status": "running",
        "message": f"v2 에이전트 시작: {goal}",
    })

    browser = BrowserManager(headless=HEADLESS)

    try:
        await browser.start()
        await broadcast({
            "type": "log",
            "agent": "System",
            "message": f"브라우저 시작 완료 (프리뷰: {'ON' if preview else 'OFF'})",
        })

        # 시작 URL이 있으면 먼저 이동
        if start_url:
            await browser.navigate(start_url)
            await broadcast({
                "type": "log",
                "agent": "System",
                "message": f"시작 URL 이동: {start_url}",
            })

        # 에이전트 생성
        agent, shared = create_browser_agent(browser, model=DEFAULT_MODEL)

        # 도구 호출 콜백
        async def on_tool_call(event: dict):
            msg = {"type": "step", "event": event["type"], "tool": event["tool"]}

            if event["type"] == "tool_start":
                msg["input"] = event.get("input", {})
            elif event["type"] == "tool_end":
                msg["output"] = event.get("output", "")

                # 현재 URL 전달
                page = browser.page
                if page:
                    try:
                        msg["url"] = page.url
                    except Exception:
                        pass

                # 프리뷰 모드: 도구 완료 후 스크린샷 자동 캡처
                if preview and page:
                    try:
                        raw = await page.screenshot(type="jpeg", quality=50)
                        msg["screenshot"] = base64.b64encode(raw).decode("utf-8")
                    except Exception as e:
                        logger.debug(f"프리뷰 스크린샷 실패: {e}")

            await broadcast(msg)

        # 에이전트 실행
        result = await run_browser_agent(
            agent=agent,
            shared=shared,
            goal=goal,
            start_url=start_url,
            direction=direction,
            on_tool_call=on_tool_call,
        )

        await broadcast({
            "type": "result",
            "success": result["success"],
            "message": result["message"],
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
    """v2 서버 시작"""
    import uvicorn
    uvicorn.run(
        "src.v2.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
        reload_dirs=["src"],
        reload_excludes=["logs/*", "*.log", "__pycache__/*", "*.pyc", ".omc/*"],
    )


if __name__ == "__main__":
    main()
