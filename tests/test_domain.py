from server.services.domain import origin_allowed


def test_exact_origin_match():
    assert origin_allowed("https://example.test", ["https://example.test"])
    assert not origin_allowed("https://example.test", ["https://other.test"])


def test_wildcard_subdomain():
    allowed = ["https://*.example.test"]
    assert origin_allowed("https://www.example.test", allowed)
    assert origin_allowed("https://blog.example.test", allowed)
    assert origin_allowed("https://example.test", allowed)
    assert not origin_allowed("https://example.evil.test", allowed)


def test_mixed_scheme_rejected():
    allowed = ["https://example.test"]
    assert not origin_allowed("http://example.test", allowed)


def test_localhost_dev():
    allowed = ["http://localhost:5000", "http://*.localhost"]
    assert origin_allowed("http://localhost:5000", allowed)
    assert origin_allowed("http://localhost:3000", ["http://*.localhost"])


def test_file_origin_always_allowed():
    assert origin_allowed("null", ["file://"])


def test_empty_allowed_rejected():
    assert not origin_allowed("https://example.test", [])
