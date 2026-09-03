from server.services.signing import sign_visitor_token, verify_visitor_token


def test_sign_and_verify_roundtrip():
    token = sign_visitor_token("site_1", "visitor-abc")
    assert verify_visitor_token("site_1", token) == "visitor-abc"


def test_token_is_bound_to_site():
    token = sign_visitor_token("site_1", "visitor-abc")
    assert verify_visitor_token("site_2", token) is None


def test_tampered_token_is_rejected():
    token = sign_visitor_token("site_1", "visitor-abc")
    payload, sig = token.rsplit(".", 1)
    # Flip the visitor id inside a validly-signed body is impossible without the
    # secret; a naive edit of the payload must fail signature verification.
    forged = payload + "." + ("f" * len(sig))
    assert verify_visitor_token("site_1", forged) is None


def test_malformed_token_is_rejected():
    assert verify_visitor_token("site_1", "") is None
    assert verify_visitor_token("site_1", "no-dot-separator") is None
    assert verify_visitor_token("site_1", "payload.garbage") is None


def test_expired_token_is_rejected():
    token = sign_visitor_token("site_1", "visitor-abc", ttl=-1)
    assert verify_visitor_token("site_1", token) is None