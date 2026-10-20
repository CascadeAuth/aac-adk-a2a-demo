# The sample agents' image: Python, Google ADK with its A2A server, LiteLLM for the own-model run,
# AAC's pairing-authentication library and the example programs. `./demo up` builds it on your machine.
FROM python:3.12-slim
ARG AAC_INVOKE_AUTH_VERSION
RUN pip install --no-cache-dir "aac-invoke-auth[fastapi]==${AAC_INVOKE_AUTH_VERSION}" \
    "google-adk[a2a]==2.12.0" "litellm==1.106.0" "uvicorn==0.54.0" "httpx==0.28.1"
WORKDIR /app
COPY agent.py scripted_model.py client.py ./
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "agent:app", "--host", "127.0.0.1", "--port", "8000"]
