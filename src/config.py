"""Agentic Browser 설정"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = Path(__file__).parent

# LLM 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 기본 LLM 모델
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "openai")  # "openai" or "anthropic"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5-mini")

# 브라우저 설정
HEADLESS = True
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))  # ms
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"

# 에이전트 설정
MAX_STEPS = int(os.getenv("MAX_STEPS", "50"))
MAX_FAILURES = int(os.getenv("MAX_FAILURES", "5"))

# 서버 설정
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "1234"))
