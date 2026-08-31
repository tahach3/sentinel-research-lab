# Self-Improvement V2 worker. Source is bind-mounted read-only at runtime.
# Image digest is pinned in docker-compose.yml as tag@sha256:<D>.

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

COPY docker/srl-worker/requirements.txt /etc/srl-worker-requirements.txt
RUN pip install --no-cache-dir -r /etc/srl-worker-requirements.txt \
    && rm /etc/srl-worker-requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1

WORKDIR /srl/sentinel-research-lab

# Interpreter bytecode disabled at the CLI as well as via env.
CMD ["python", "-B", "-m", "tools.self_improvement_v2.runtime_bridge"]
