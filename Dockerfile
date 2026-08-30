FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CHESSLAB_ENV=production CHESSLAB_AUTH_MODE=supabase
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY chesslab ./chesslab
COPY migrations ./migrations
COPY data/openings ./data/openings
RUN useradd --create-home appuser
USER appuser
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
