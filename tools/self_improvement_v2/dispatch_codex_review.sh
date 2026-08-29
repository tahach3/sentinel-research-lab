#!/usr/bin/env bash
# Harness: freeze tip from rev-parse, embed suite artifacts into the brief, dispatch Codex.
# Usage: ./tools/self_improvement_v2/dispatch_codex_review.sh [brief.md]
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
CODEX_BIN="${CODEX_BIN:-$(command -v codex || true)}"
if [[ -z "$CODEX_BIN" ]]; then
  CODEX_BIN="/home/ubuntu/.npm/_npx/c8ab89660c602c20/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
fi
BRIEF_SRC="${1:-docs/SELF_IMPROVEMENT_V2_CODEX_BRIEF_1c8e2b9_PARSE_STRICT.md}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ART="/tmp/codex-wide-review-${STAMP}"
SUITE_ART="/tmp/si2-suite-harness-${STAMP}"
mkdir -p "$ART" "$SUITE_ART"

TIP="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "refuse: dirty worktree; commit before harness suite + dispatch" >&2
  exit 2
fi

# --- suite emit (R0 pattern: harness totals + hashes) ---
{
  echo "TIP=$TIP"
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "worktree_dirty_lines=0"
} >"$SUITE_ART/meta.txt"
set +e
python -m pytest tests/self_improvement_v2/ -q --tb=line \
  >"$SUITE_ART/stdout.txt" 2>"$SUITE_ART/stderr.txt"
EC=$?
set -e
{
  echo "exit_code=$EC"
  echo "finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "SUMMARY<<EOF"
  tail -n 5 "$SUITE_ART/stdout.txt"
  echo "EOF"
} >>"$SUITE_ART/meta.txt"
(
  cd "$SUITE_ART"
  sha256sum stdout.txt stderr.txt >SHA256SUMS
)
mkdir -p /opt/cursor/artifacts/si2-suite-harness 2>/dev/null || true
cp -a "$SUITE_ART"/. /opt/cursor/artifacts/si2-suite-harness/ 2>/dev/null || true

# --- freeze ---
{
  echo "TIP=$TIP"
  echo "BRANCH=$(git rev-parse --abbrev-ref HEAD)"
  echo "WORKDIR=$ROOT"
  echo "SUITE_ART=$SUITE_ART"
  echo "CODEX_LOGIN_STATUS=$("$CODEX_BIN" login status 2>&1 | tr '\n' ' ')"
  echo "STATUS_SHORT<<EOF"
  git status --porcelain
  echo "EOF"
} >"$ART/freeze.txt"

# --- brief with tip substituted + suite block (Python avoids shell brace expansion) ---
export ART SUITE_ART BRIEF_SRC TIP
python3 - <<'PY'
import os
from pathlib import Path

art = Path(os.environ["ART"])
suite = Path(os.environ["SUITE_ART"])
tip = os.environ["TIP"].strip()
src = Path(os.environ["BRIEF_SRC"])
text = src.read_text(encoding="utf-8")
text = text.replace("*(substituted from `git rev-parse HEAD` at send)*", tip)
text = text.replace("*(paste `git rev-parse HEAD` at send)*", tip)
text = text.replace("<rev-parse tip>", tip)
text = text.replace("..<rev-parse tip>", f"..{tip}")
meta = (suite / "meta.txt").read_text(encoding="utf-8")
sums = (suite / "SHA256SUMS").read_text(encoding="utf-8")
block = (
    "\n\n---\n\n## HARNESS SUITE ARTIFACT (Cursor-emitted; spot-check required)\n\n"
    "```text\n"
    f"{meta}"
    "SHA256SUMS:\n"
    f"{sums}"
    f"artifact_dir: {suite}\n"
    "also_copied: /opt/cursor/artifacts/si2-suite-harness/\n"
    "```\n\n"
    "Targeted spot-check suggestions:\n"
    "- tests/self_improvement_v2/test_workflow_validator.py\n"
    "- tests/self_improvement_v2/test_r1_non_main_attachments.py::"
    "test_r1_positive_control_legitimate_ai_language_model_still_passes\n"
)
wrapper = f"""SENTINEL RESEARCH LAB — WIDE PRE-DEPLOYMENT SECURITY REVIEW

CONTEXT AND AUTHORIZATION
Read-only review of the owner's own local repository. Constraints: no file
changes, no commits, no deployment, no merge. Write throwaway scripts in temp
only. No live authorization exists.

Repository:  sentinel-research-lab
Branch:      research-lab-self-improvement-v2-v3-gates
Baseline:    e85c42ee434cf93346f14f3a890e5fb1385cb06d
Prior tip:   481ac490bc17db0112dd2084c6f5d9fe96c0801b  (REPAIR_REQUIRED — link fields)
Reviewed:    {tip}
Range:       e85c42ee434cf93346f14f3a890e5fb1385cb06d..{tip}
Code focus:  1a1c48e6fcf1abffebfefd1001505aaf83c02cf3..{tip}

Follow the structured brief below. End with exactly one of:
PASS / REPAIR_REQUIRED / ESCALATE.

"""
(art / "brief.txt").write_text(wrapper + text + block, encoding="utf-8")
print(f"brief_bytes={(art / 'brief.txt').stat().st_size} tip={tip} art={art}")
PY

# --- trivial auth probe ---
printf 'Reply with exactly the word PONG and nothing else.\n' | "$CODEX_BIN" exec \
  -m gpt-5.6-sol -s read-only -c 'approval_policy="never"' --ephemeral \
  -o "$ART/auth_pong.txt" >/dev/null 2>"$ART/auth_stderr.txt" || true
echo "auth_pong=$(tr -d '\n' <"$ART/auth_pong.txt" 2>/dev/null || true)"

# --- dispatch ---
set +e
"$CODEX_BIN" exec \
  -m gpt-5.6-sol \
  -s read-only \
  -c 'approval_policy="never"' \
  -C "$ROOT" \
  --ephemeral \
  -o "$ART/last_message.txt" \
  <"$ART/brief.txt" \
  >"$ART/stdout.bin" 2>"$ART/stderr.bin"
EC=$?
set -e
echo "$EC" >"$ART/exit_code.txt"
cp "$ART/stdout.bin" "$ART/stdout.utf8.txt"
cp "$ART/stderr.bin" "$ART/stderr.utf8.txt"
git rev-parse HEAD >"$ART/tip_after.txt"
git status --porcelain >"$ART/status_after.txt"
mkdir -p "/opt/cursor/artifacts/codex-wide-review-${STAMP}" 2>/dev/null || true
cp -a "$ART"/. "/opt/cursor/artifacts/codex-wide-review-${STAMP}/" 2>/dev/null || true
echo "exit=$EC art=$ART"
tail -n 5 "$ART/last_message.txt" || true
