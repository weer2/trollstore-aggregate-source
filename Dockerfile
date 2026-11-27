FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
# 容器启动：先更新一次源，再启动 Web 状态站
CMD ["sh", "-c", "python scripts/daily_update.py && python web/app.py"]
