"""Agentic Browser v2 설정"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = Path(__file__).parent

# LLM 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 기본 LLM 모델
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o")

# 브라우저 설정
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"

# 에이전트 설정
MAX_STEPS = int(os.getenv("MAX_STEPS", "50"))

# 페이지 콘텐츠 추출 설정
A11Y_TEXT_LIMIT = int(os.getenv("A11Y_TEXT_LIMIT", "4000"))

# 서버 설정 (v1과 다른 포트)
SERVER_HOST = os.getenv("V2_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("V2_SERVER_PORT", "1235"))

# 로그 디렉토리
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
