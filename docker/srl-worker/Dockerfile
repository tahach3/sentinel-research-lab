# srl-worker base. Image digest D is attested live (INV-TOPO), not by tag.
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp/srl-zone-p \
    SRL_RUNTIME_MODE=P3C1

WORKDIR /srl
# Reviewed source is mounted read-only at /srl/sentinel-research-lab
# Execution root is /tmp/srl-exec/<id>/ (tmpfs / container RW).
CMD ["python", "-m", "tools.self_improvement_v2.runtime_bridge"]
