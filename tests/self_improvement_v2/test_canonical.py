from tools.self_improvement_v2.canonical import canonical_dumps, content_sha256, unicode_form


def test_key_order_same_hash():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert content_sha256(a) == content_sha256(b)
    assert canonical_dumps(a) == canonical_dumps(b)


def test_value_change_different_hash():
    assert content_sha256({"a": 1}) != content_sha256({"a": 2})


def test_array_order_different_hash():
    assert content_sha256([1, 2]) != content_sha256([2, 1])


def test_null_differs_from_missing():
    assert content_sha256({"a": None}) != content_sha256({})


def test_bool_differs_from_int():
    assert content_sha256({"a": True}) != content_sha256({"a": 1})


def test_unicode_normalization_explicit():
    nfc = "é"
    nfd = "e\u0301"
    assert unicode_form(nfc) in {"NFC", "NFKC", "UNKNOWN"}
    assert content_sha256(nfc) != content_sha256(nfd) or nfc == nfd
