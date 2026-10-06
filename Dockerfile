# Multi-stage build for Python FastAPI application

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies (curl: healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# /app 및 SQLite 데이터 디렉토리 쓰기 권한
RUN mkdir -p /app/data && chown appuser:appuser /app /app/data

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Change ownership
RUN chown -R appuser:appuser /home/appuser/.local

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
