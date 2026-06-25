FROM python:3.11-slim

WORKDIR /app

# 系统依赖（Playwright Chromium 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# Playwright Chromium
RUN playwright install chromium

# 应用代码
COPY python/ ./python/
COPY alembic/ ./alembic/
COPY alembic.ini .

ENV PYTHONPATH=/app/python
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

EXPOSE 8000

CMD ["uvicorn", "python.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
