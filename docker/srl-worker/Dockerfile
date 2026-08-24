# Self-Improvement V2 worker. Source is bind-mounted read-only at runtime.
# Image digest is pinned in docker-compose.yml as tag@sha256:<D>.

FROM python:3.12-slim-bookworm@sha256:8fe03caf00223c1a52c4a0b32f670e6957a90f32a1d7673c3e10319d1a0cd6b3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1

WORKDIR /srl/sentinel-research-lab

# Interpreter bytecode disabled at the CLI as well as via env.
CMD ["python", "-B", "-m", "tools.self_improvement_v2.runtime_bridge"]
