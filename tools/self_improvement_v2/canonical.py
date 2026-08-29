"""Canonical JSON serialization and SHA-256 content addressing for V2."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def canonical_dumps(value: Any) -> str:
    """Serialize to canonical JSON: UTF-8, sorted keys, no insignificant whitespace.

    Arrays retain semantic order. Unicode is emitted as UTF-8 JSON (ensure_ascii=False
    then encoded); hashing uses UTF-8 bytes of the canonical string. Callers that need
    NFC/NFD equality must normalize before hashing — this function does not rewrite
    Unicode forms.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_dumps(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))


def content_sha256(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def unicode_form(text: str) -> str:
    """Return Unicode normalization form name for explicit test/oracle use."""
    if unicodedata.is_normalized("NFC", text):
        return "NFC"
    if unicodedata.is_normalized("NFD", text):
        return "NFD"
    if unicodedata.is_normalized("NFKC", text):
        return "NFKC"
    if unicodedata.is_normalized("NFKD", text):
        return "NFKD"
    return "UNKNOWN"
