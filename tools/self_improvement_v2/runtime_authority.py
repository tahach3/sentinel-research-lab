"""SRL_RUNTIME_MODE is configuration, never authority."""

from __future__ import annotations

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError


def refuse_mode_as_authority(runtime_mode: str | None, *, live_authorized: bool, p3c1_authorized: bool) -> None:
    if (runtime_mode or "").strip().upper() == "P3C1" and not (live_authorized and p3c1_authorized):
        raise WorkerError(
            ERROR_CODES["RUNTIME_MODE_NOT_AUTHORITY"],
            "SRL_RUNTIME_MODE=P3C1 is configuration, never authority",
            state="POLICY_REJECTED",
        )


def require_hmac_artifacts(*, live_path_exists: bool, p3c1_path_exists: bool) -> None:
    if not live_path_exists or not p3c1_path_exists:
        raise WorkerError(
            ERROR_CODES["RUNTIME_MODE_NOT_AUTHORITY"],
            "LIVE_AUTHORIZED.json / P3C1_AUTHORIZED.json required for activation",
            state="POLICY_REJECTED",
        )
