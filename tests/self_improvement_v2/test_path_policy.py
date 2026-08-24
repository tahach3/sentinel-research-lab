import pytest

from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.path_policy import assert_path_allowed, load_policy

POLICY = load_policy()
PROP = {"allowed_paths": ["docs/**", "tests/**"], "forbidden_paths": []}


@pytest.mark.parametrize(
    "path,code",
    [
        ("docs/.env", "SI2-PATH-PROTECTED-BASENAME"),
        ("tests/fixtures/.git/HEAD", "SI2-PATH-PROTECTED-SEGMENT"),
        ("docs/secrets/key.txt", "SI2-PATH-PROTECTED-SEGMENT"),
        ("Docs/.ENV", "SI2-PATH-PROTECTED-BASENAME"),
        ("docs/../secrets/x", "SI2-PATH-TRAVERSAL"),
        ("/abs/path", "SI2-PATH-ABSOLUTE"),
        ("C:/windows/path", "SI2-PATH-ABSOLUTE"),
        ('docs/"evil".md', "SI2-PATH-QUOTED-UNSAFE"),
        ("database/migrations/001.sql", "SI2-PATH-FORBIDDEN-ROOT"),
    ],
)
def test_path_rejections(path, code):
    with pytest.raises(WorkerError) as ei:
        assert_path_allowed(path, POLICY, PROP)
    assert ei.value.code == code


def test_allowed_docs_ok():
    assert assert_path_allowed("docs/note.md", POLICY, PROP) == "docs/note.md"


@pytest.mark.parametrize(
    "path",
    [
        "docs/%2e%65%6e%76",
        "docs/%2Eenv",
        "docs/\u202e.env",
        "docs/\u200b.env",
    ],
)
def test_spoofed_protected_names_rejected(path):
    with pytest.raises(WorkerError) as ei:
        assert_path_allowed(path, POLICY, PROP)
    assert ei.value.code == "SI2-PATH-SPOOFED-PROTECTED-NAME"
