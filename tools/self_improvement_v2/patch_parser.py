"""Structural Git unified-diff parser for Self-Improvement Loop V2."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

OCTAL_ESCAPE_RE = re.compile(r"\\([0-7]{1,3})")
DIFF_GIT_RE = re.compile(r"^diff --git (.+)$")


def unescape_git_path(token: str) -> str:
    token = token.strip()
    quoted = False
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        quoted = True
        token = token[1:-1]

    def _oct(m: re.Match[str]) -> str:
        return chr(int(m.group(1), 8))

    out = OCTAL_ESCAPE_RE.sub(_oct, token)
    out = out.replace("\\t", "\t").replace("\\n", "\n").replace("\\\\", "\\").replace('\\"', '"')
    if quoted and (".." in out or out.startswith("/") or "\\" in out):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
            f"unsafe quoted path: {token}",
            state="PATCH_REJECTED",
        )
    return out


def split_diff_git_paths(rest: str) -> tuple[str, str]:
    # Forms: a/foo b/foo  or  "a/foo bar" "b/foo bar"
    rest = rest.strip()
    if rest.startswith('"'):
        # parse two quoted paths
        paths: list[str] = []
        i = 0
        while i < len(rest) and len(paths) < 2:
            if rest[i] != '"':
                raise WorkerError(
                    ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
                    f"malformed quoted diff path: {rest}",
                    state="PATCH_REJECTED",
                )
            j = i + 1
            buf = ['"']
            while j < len(rest):
                ch = rest[j]
                buf.append(ch)
                if ch == '"' and rest[j - 1] != "\\":
                    break
                j += 1
            else:
                raise WorkerError(
                    ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
                    "unclosed quoted path",
                    state="PATCH_REJECTED",
                )
            paths.append(unescape_git_path("".join(buf)))
            i = j + 1
            while i < len(rest) and rest[i].isspace():
                i += 1
        if len(paths) != 2:
            raise WorkerError(
                ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
                "expected two quoted paths",
                state="PATCH_REJECTED",
            )
        return paths[0], paths[1]

    # unquoted: a/path b/path — strip a/ and b/ prefixes later
    parts = rest.split(" ")
    if len(parts) < 2:
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "malformed diff --git header", state="PATCH_REJECTED")
    # Join conservatively: last token is b-path, remainder is a-path after first
    # Standard: two tokens a/X b/Y without spaces in paths
    if len(parts) == 2:
        return unescape_git_path(parts[0]), unescape_git_path(parts[1])
    # paths with spaces are required to be quoted in Git; reject ambiguous
    raise WorkerError(
        ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
        "ambiguous unquoted path with spaces",
        state="PATCH_REJECTED",
    )


def strip_ab_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


@dataclass
class ParsedPatch:
    old_path: str
    new_path: str
    is_create: bool = False
    is_delete: bool = False
    is_rename: bool = False
    is_copy: bool = False
    is_binary: bool = False
    is_symlink: bool = False
    is_submodule: bool = False
    modes: list[str] = field(default_factory=list)
    raw: str = ""


def parse_unified_diff(unified_diff: str) -> ParsedPatch:
    if not isinstance(unified_diff, str) or not unified_diff.strip():
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "empty diff", state="PATCH_REJECTED")
    if "\x00" in unified_diff:
        raise WorkerError(ERROR_CODES["BINARY_PATCH"], "NUL in diff", state="PATCH_REJECTED")

    lines = unified_diff.splitlines()
    old_path = ""
    new_path = ""
    is_create = False
    is_delete = False
    is_rename = False
    is_copy = False
    is_binary = False
    is_symlink = False
    is_submodule = False
    modes: list[str] = []

    for line in lines:
        if line.startswith("diff --git "):
            a, b = split_diff_git_paths(line[len("diff --git ") :])
            old_path = strip_ab_prefix(a)
            new_path = strip_ab_prefix(b)
        elif line.startswith("new file mode "):
            is_create = True
            mode = line.split()[-1]
            modes.append(mode)
            if mode == "120000":
                is_symlink = True
            if mode == "160000":
                is_submodule = True
        elif line.startswith("deleted file mode "):
            is_delete = True
            mode = line.split()[-1]
            modes.append(mode)
        elif line.startswith("old mode ") or line.startswith("new mode "):
            mode = line.split()[-1]
            modes.append(mode)
            if mode == "120000":
                is_symlink = True
            if mode == "160000":
                is_submodule = True
        elif line.startswith("rename from ") or line.startswith("rename to "):
            is_rename = True
            if line.startswith("rename from "):
                old_path = unescape_git_path(line[len("rename from ") :])
            else:
                new_path = unescape_git_path(line[len("rename to ") :])
        elif line.startswith("copy from ") or line.startswith("copy to "):
            is_copy = True
            if line.startswith("copy from "):
                old_path = unescape_git_path(line[len("copy from ") :])
            else:
                new_path = unescape_git_path(line[len("copy to ") :])
        elif line.startswith("GIT binary patch") or line.startswith("Binary files "):
            is_binary = True
        elif line.startswith("--- "):
            token = line[4:].strip()
            if token != "/dev/null":
                old_path = strip_ab_prefix(unescape_git_path(token))
            else:
                is_create = True
        elif line.startswith("+++ "):
            token = line[4:].strip()
            if token != "/dev/null":
                new_path = strip_ab_prefix(unescape_git_path(token))
            else:
                is_delete = True
        elif "160000" in line and ("mode" in line or line.startswith("index ")):
            is_submodule = True

    if not old_path and not new_path:
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "diff missing paths", state="PATCH_REJECTED")
    if not old_path:
        old_path = new_path
    if not new_path:
        new_path = old_path

    return ParsedPatch(
        old_path=old_path,
        new_path=new_path,
        is_create=is_create,
        is_delete=is_delete,
        is_rename=is_rename,
        is_copy=is_copy,
        is_binary=is_binary,
        is_symlink=is_symlink,
        is_submodule=is_submodule,
        modes=modes,
        raw=unified_diff,
    )


def reject_forbidden_patch_ops(parsed: ParsedPatch) -> None:
    if parsed.is_delete:
        raise WorkerError(ERROR_CODES["DELETION_PROHIBITED"], "DELETE rejected", state="PATCH_REJECTED")
    if parsed.is_rename:
        raise WorkerError(ERROR_CODES["RENAME_PROHIBITED"], "RENAME rejected", state="PATCH_REJECTED")
    if parsed.is_copy:
        raise WorkerError(ERROR_CODES["COPY_PROHIBITED"], "COPY rejected", state="PATCH_REJECTED")
    if parsed.is_binary:
        raise WorkerError(ERROR_CODES["BINARY_PATCH"], "BINARY rejected", state="PATCH_REJECTED")
    if parsed.is_submodule:
        raise WorkerError(ERROR_CODES["SI2-PATH-SUBMODULE"], "SUBMODULE rejected", state="PATCH_REJECTED")
    if parsed.is_symlink:
        raise WorkerError(ERROR_CODES["SI2-PATH-SYMLINK"], "SYMLINK rejected", state="PATCH_REJECTED")


def paths_from_parsed(parsed: ParsedPatch) -> list[str]:
    out: list[str] = []
    for p in (parsed.old_path, parsed.new_path):
        if p and p not in out and p != "/dev/null":
            out.append(p)
    return out
