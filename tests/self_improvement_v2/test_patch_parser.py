import pytest

from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.patch_parser import parse_unified_diff, reject_forbidden_patch_ops


def test_rename_rejected():
    diff = (
        "diff --git a/docs/a.md b/docs/b.md\n"
        "rename from docs/a.md\n"
        "rename to docs/b.md\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/b.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    parsed = parse_unified_diff(diff)
    with pytest.raises(WorkerError) as ei:
        reject_forbidden_patch_ops(parsed)
    assert ei.value.code == "RENAME_PROHIBITED"


def test_copy_rejected():
    diff = (
        "diff --git a/docs/a.md b/docs/b.md\n"
        "copy from docs/a.md\n"
        "copy to docs/b.md\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/b.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    parsed = parse_unified_diff(diff)
    with pytest.raises(WorkerError) as ei:
        reject_forbidden_patch_ops(parsed)
    assert ei.value.code == "COPY_PROHIBITED"


def test_binary_rejected():
    diff = "diff --git a/docs/a.bin b/docs/a.bin\nGIT binary patch\nliteral 1\n"
    parsed = parse_unified_diff(diff)
    with pytest.raises(WorkerError) as ei:
        reject_forbidden_patch_ops(parsed)
    assert ei.value.code == "BINARY_PATCH"


def test_submodule_rejected():
    diff = (
        "diff --git a/docs/sub b/docs/sub\n"
        "new file mode 160000\n"
        "--- /dev/null\n"
        "+++ b/docs/sub\n"
        "@@ -0,0 +1 @@\n"
        "+Subproject commit deadbeef\n"
    )
    parsed = parse_unified_diff(diff)
    with pytest.raises(WorkerError) as ei:
        reject_forbidden_patch_ops(parsed)
    assert ei.value.code == "SI2-PATH-SUBMODULE"


def test_symlink_rejected():
    diff = (
        "diff --git a/docs/link b/docs/link\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/docs/link\n"
        "@@ -0,0 +1 @@\n"
        "+target\n"
    )
    parsed = parse_unified_diff(diff)
    with pytest.raises(WorkerError) as ei:
        reject_forbidden_patch_ops(parsed)
    assert ei.value.code == "SI2-PATH-SYMLINK"


def test_quoted_path_parsed():
    diff = (
        'diff --git "a/docs/foo bar.md" "b/docs/foo bar.md"\n'
        "new file mode 100644\n"
        "--- /dev/null\n"
        '+++ "b/docs/foo bar.md"\n'
        "@@ -0,0 +1 @@\n"
        "+x\n"
    )
    parsed = parse_unified_diff(diff)
    assert parsed.new_path == "docs/foo bar.md"


def test_octal_path():
    token_path = "docs/caf\\303\\251.md"
    diff = (
        f'diff --git "a/{token_path}" "b/{token_path}"\n'
        "new file mode 100644\n"
        "--- /dev/null\n"
        f'+++ "b/{token_path}"\n'
        "@@ -0,0 +1 @@\n"
        "+x\n"
    )
    parsed = parse_unified_diff(diff)
    assert "docs/caf" in parsed.new_path
