# ─── Agentic Browser Docker Image ───
# Playwright 공식 이미지: Chromium + 시스템 의존성 내장
FROM mcr.microsoft.com/playwright/python:v1.51.0-noble

WORKDIR /app

# 의존성 먼저 복사 (레이어 캐싱)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치 (Chromium만)
RUN playwright install chromium

# 소스 복사
COPY src/ src/

# 포트
EXPOSE 1234

# 컨테이너 내부에서는 항상 headless
ENV HEADLESS=true
ENV PYTHONUNBUFFERED=1

# 서버 실행 (reload 끄기 — 프로덕션 배포용)
CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "1234"]
