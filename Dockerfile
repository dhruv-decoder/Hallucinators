FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY controlplane ./controlplane
COPY policies ./policies
RUN pip install --no-cache-dir -e ".[serve]"
EXPOSE 8000
CMD ["python", "-m", "controlplane.proxy"]
