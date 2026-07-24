import io
import logging
import uuid

from decide import security


def test_sign_verify_roundtrip(dbenv):
    pid = str(uuid.uuid4())
    cookie = security.sign_participant(pid)
    assert security.verify_participant(cookie) == pid


def test_tampered_cookie_rejected(dbenv):
    pid = str(uuid.uuid4())
    other = str(uuid.uuid4())
    cookie = security.sign_participant(pid)
    version, _, sig = cookie.split(".")
    assert security.verify_participant(f"{version}.{other}.{sig}") is None


def test_garbage_and_missing_rejected(dbenv):
    assert security.verify_participant(None) is None
    assert security.verify_participant("") is None
    assert security.verify_participant("v1.onlytwoparts") is None
    assert security.verify_participant("v2.a.b") is None


def test_redaction_filter_masks_secrets(dbenv):
    secret = "plx-SECRET-abcdef123456"
    security.add_secret(secret)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(security.RedactionFilter())
    logger = logging.getLogger("redaction-test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("connecting with token %s to server", secret)
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert secret not in output
    assert "***redacted***" in output
