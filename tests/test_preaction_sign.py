"""Tests for scripts/preaction_sign.py, the artifact-bound authorization token.

The load-bearing property is copy resistance: a token authorizes the exact bytes it was signed
over and cannot be lifted onto a different artifact. The key used here is a throwaway test
literal, never a real secret.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# A throwaway test literal, never a real secret, but long and varied enough to clear the
# signer's key floor (>= 32 chars, more than a handful of distinct characters).
_TEST_KEY = "throwaway-test-signing-key-not-a-secret"


def _load():
    spec = importlib.util.spec_from_file_location("preaction_sign", REPO / "scripts" / "preaction_sign.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load()


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #

def test_sign_then_verify_round_trips():
    h = ps.artifact_hash(b"a unified diff\n")
    token = ps.sign(h, _TEST_KEY)
    assert ps.verify(h, token, _TEST_KEY) is True


def test_a_token_does_not_authorize_a_different_artifact():
    # The copy-resistance property: a token signed over one artifact must not verify against
    # another, even a one-byte change.
    token = ps.sign(ps.artifact_hash(b"original diff\n"), _TEST_KEY)
    assert ps.verify(ps.artifact_hash(b"original diff!\n"), token, _TEST_KEY) is False


def test_a_token_does_not_verify_under_a_different_key():
    h = ps.artifact_hash(b"diff\n")
    token = ps.sign(h, _TEST_KEY)
    assert ps.verify(h, token, "another-throwaway-key-also-long-enough-x") is False


def test_the_token_never_contains_the_key():
    token = ps.sign(ps.artifact_hash(b"diff\n"), _TEST_KEY)
    assert _TEST_KEY not in token


def test_artifact_hash_is_deterministic():
    assert ps.artifact_hash(b"x") == ps.artifact_hash(b"x")
    assert ps.artifact_hash(b"x") != ps.artifact_hash(b"y")


def test_an_empty_key_is_rejected_at_the_library_boundary():
    # Fail-closed must hold for a direct importer, not only at the CLI: an empty key can neither
    # produce nor accept a token.
    import pytest
    h = ps.artifact_hash(b"diff\n")
    with pytest.raises(ValueError):
        ps.sign(h, "")
    with pytest.raises(ValueError):
        ps.verify(h, "any-token", "")


def test_a_short_key_is_rejected():
    # A short key is brute-forceable offline. The floor holds at the library boundary.
    import pytest
    h = ps.artifact_hash(b"diff\n")
    with pytest.raises(ValueError):
        ps.sign(h, "short")
    with pytest.raises(ValueError):
        ps.sign(h, "x" * (ps._MIN_KEY_LEN - 1))  # one character under the floor


def test_a_guessable_key_is_rejected():
    import pytest
    h = ps.artifact_hash(b"diff\n")
    for weak in ("password", "changeme", "mergen", "secret", "X", "Default"):
        with pytest.raises(ValueError):
            ps.sign(h, weak)


def test_a_low_variety_key_is_rejected():
    # Long enough but only one distinct character, which is not a real secret.
    import pytest
    h = ps.artifact_hash(b"diff\n")
    with pytest.raises(ValueError):
        ps.sign(h, "a" * 40)


def test_a_strong_random_key_is_accepted():
    import secrets
    h = ps.artifact_hash(b"diff\n")
    key = secrets.token_hex(32)  # 64 hex chars
    assert ps.verify(h, ps.sign(h, key), key) is True


def test_verify_tolerates_surrounding_whitespace_on_the_token():
    h = ps.artifact_hash(b"diff\n")
    token = ps.sign(h, _TEST_KEY)
    assert ps.verify(h, f"  {token}\n", _TEST_KEY) is True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _artifact(tmp_path, content=b"--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"):
    p = tmp_path / "change.diff"
    p.write_bytes(content)
    return p


def test_cli_sign_prints_token_and_hash(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", _TEST_KEY)
    art = _artifact(tmp_path)
    assert ps.main(["sign", "--artifact", str(art)]) == 0
    out = capsys.readouterr().out
    assert "artifact-sha256:" in out and "mergen-ack-token:" in out
    assert _TEST_KEY not in out  # the key never leaks to stdout


def test_cli_sign_then_verify_passes(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", _TEST_KEY)
    art = _artifact(tmp_path)
    ps.main(["sign", "--artifact", str(art)])
    token = [ln.split(": ", 1)[1] for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("mergen-ack-token:")][0]
    assert ps.main(["verify", "--artifact", str(art), "--token", token]) == 0


def test_cli_verify_fails_on_a_tampered_artifact(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", _TEST_KEY)
    art = _artifact(tmp_path)
    ps.main(["sign", "--artifact", str(art)])
    token = [ln.split(": ", 1)[1] for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("mergen-ack-token:")][0]
    art.write_bytes(b"a different diff\n")  # tamper after signing
    assert ps.main(["verify", "--artifact", str(art), "--token", token]) == 1


def test_cli_without_key_env_returns_2(tmp_path, monkeypatch):
    monkeypatch.delenv("MERGEN_SIGNING_KEY", raising=False)
    art = _artifact(tmp_path)
    assert ps.main(["sign", "--artifact", str(art)]) == 2
    # The verify path is guarded the same way, not only sign.
    assert ps.main(["verify", "--artifact", str(art), "--token", "deadbeef"]) == 2


def test_cli_weak_key_returns_2_not_a_traceback(tmp_path, capsys, monkeypatch):
    # A present but weak key is a usage error (exit 2), surfaced cleanly, never a token.
    monkeypatch.setenv("MERGEN_SIGNING_KEY", "password")
    art = _artifact(tmp_path)
    assert ps.main(["sign", "--artifact", str(art)]) == 2
    err = capsys.readouterr().err
    assert "guessable" in err
    assert "mergen-ack-token" not in err


def test_cli_missing_artifact_returns_2(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", _TEST_KEY)
    assert ps.main(["sign", "--artifact", str(tmp_path / "nope.diff")]) == 2
