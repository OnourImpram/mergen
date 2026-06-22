#!/usr/bin/env python3
"""mergen sign: a pre-action authorization token bound to the exact artifact it approves.

The govern-diff gate accepts a plaintext acknowledgement, the line "Governor-Ack: high-trust"
in a pull-request body. That line proves a human typed it, but nothing binds it to the change
under review, so the same words copied onto a different, unreviewed diff would pass just as
well. This binds the acknowledgement to the change.

sign takes the artifact under review, a diff or a verification report, hashes its exact bytes,
and returns an HMAC of that hash under a locally held key. verify recomputes the HMAC and
compares it in constant time. Because the token is a function of the artifact's own hash, it
authorizes that one artifact and cannot be lifted onto another: change a single byte of the diff
and the token no longer verifies.

Honest scope. This is a shared-secret MAC, not a public-key signature. It proves that whoever
holds the key (MERGEN_SIGNING_KEY) authorized this exact artifact, offline and with the standard
library alone. It is NOT publicly verifiable and NOT non-repudiable to a third party: anyone with
the key can both produce and check a token, and a party without the key cannot verify it at all.
For a public-verifiable, keyless identity, keyless cosign or Sigstore is the external path. It
needs the network and an OIDC identity, so it is named here, not built. The key is read only from
the environment and is never printed, logged, or written, exactly like every other credential.

Tier 0: pure standard library (hmac, hashlib), no network, no model, deterministic.
Exit codes: 0 a valid token or a successful sign, 1 an invalid token, 2 a usage or key error.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
from pathlib import Path

_KEY_ENV = "MERGEN_SIGNING_KEY"

#: The shortest key the signer will accept. A pre-action authorization MAC is only as strong
#: as its key, and a short key is brute-forceable offline, so anything below this is refused.
_MIN_KEY_LEN = 32

#: Keys a careless or default setup might fall back to. Refused outright (case-folded), since a
#: guessable key lets anyone forge an authorization. This is a floor, not a substitute for a
#: random key: the length and variety checks below catch padded or low-entropy values too.
_WEAK_KEYS = frozenset({
    "x", "test", "secret", "password", "passw0rd", "changeme", "change-me", "changemenow",
    "mergen", "mergen-signing-key", "signing-key", "key", "default", "12345678", "00000000",
})

#: How to make a real key, surfaced in the error so the fix is one copy-paste away.
_KEY_HINT = 'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'


def artifact_hash(data: bytes) -> str:
    """The sha256 of the exact artifact bytes. The token binds to this, not to the file name."""
    return hashlib.sha256(data).hexdigest()


def _require_key(key: str) -> None:
    """Reject an empty, too-short, or guessable key at the library boundary, not only at the CLI.

    The fail-closed rule (never produce or accept a token under a weak key) must hold for a
    direct importer of sign/verify too, not only for a caller who goes through main(). A MAC is
    only as strong as its key, so the key must be present, not a known-guessable value, at least
    _MIN_KEY_LEN characters, and not trivially low-entropy. This is a floor, not a guarantee of
    randomness: the operator is responsible for using a random secret (see _KEY_HINT).
    """
    if not key:
        raise ValueError(f"key must be non-empty; set {_KEY_ENV} to a strong key. {_KEY_HINT}")
    if key.strip().lower() in _WEAK_KEYS:
        raise ValueError(f"key is a known guessable value; set {_KEY_ENV} to a random secret. {_KEY_HINT}")
    if len(key) < _MIN_KEY_LEN:
        raise ValueError(
            f"key must be at least {_MIN_KEY_LEN} characters (a short key is brute-forceable). {_KEY_HINT}")
    if len(set(key)) < 4:
        raise ValueError(f"key has too little variety to be a real secret; use a random value. {_KEY_HINT}")


def sign(payload_hash: str, key: str) -> str:
    """Return the HMAC-SHA256 of an artifact hash under the key, as hex.

    The token is a function of the artifact hash, so it authorizes that one artifact. The key
    never appears in the output: the HMAC reveals nothing about it. An empty key is rejected.
    """
    _require_key(key)
    return hmac.new(key.encode("utf-8"), payload_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(payload_hash: str, token: str, key: str) -> bool:
    """True when the token is the valid HMAC for this artifact hash. Constant-time compare.

    An empty key is rejected rather than used, so a token can never be accepted under it.
    Leading and trailing whitespace on the token is tolerated, since a shell command
    substitution that captures the token commonly appends a trailing newline; interior
    whitespace is not stripped, so a tampered token is still rejected.
    """
    _require_key(key)
    expected = sign(payload_hash, key)
    return hmac.compare_digest(expected, token.strip())


def _read_key() -> str | None:
    """Read the signing key from the environment. Absent or empty yields None, never a default.

    Failing closed on a missing key is deliberate: a token must never be produced or accepted
    under an empty or guessable key.
    """
    key = os.environ.get(_KEY_ENV, "")
    return key or None


def _load_artifact(path: str) -> bytes | None:
    p = Path(path)
    if not p.is_file():
        return None
    return p.read_bytes()


def _cmd_sign(args: argparse.Namespace) -> int:
    key = _read_key()
    if key is None:
        print(f"error: set {_KEY_ENV} in the environment to a strong key. {_KEY_HINT}", file=sys.stderr)
        return 2
    data = _load_artifact(args.artifact)
    if data is None:
        print(f"error: artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    digest = artifact_hash(data)
    try:
        token = sign(digest, key)
    except ValueError as exc:
        # A present but weak key reaches the library boundary; surface a clean usage error
        # (exit 2) instead of a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Print the token and the bound hash. Neither reveals the key. A reviewer records the token
    # alongside the change; the hash names exactly which bytes it authorizes.
    print(f"artifact-sha256: {digest}")
    print(f"mergen-ack-token: {token}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    key = _read_key()
    if key is None:
        print(f"error: set {_KEY_ENV} in the environment to a strong key. {_KEY_HINT}", file=sys.stderr)
        return 2
    data = _load_artifact(args.artifact)
    if data is None:
        print(f"error: artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    digest = artifact_hash(data)
    try:
        valid = verify(digest, args.token, key)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if valid:
        print("token valid: it authorizes this exact artifact", file=sys.stderr)
        return 0
    print("token INVALID: it does not authorize this artifact (or the key differs)", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mergen sign", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_sign = sub.add_parser("sign", help="bind an authorization token to an artifact's bytes")
    p_sign.add_argument("--artifact", required=True, metavar="FILE",
                        help="the diff or verification report to authorize")
    p_sign.set_defaults(func=_cmd_sign)

    p_ver = sub.add_parser("verify", help="check a token authorizes an artifact (exit 0 or 1)")
    p_ver.add_argument("--artifact", required=True, metavar="FILE",
                       help="the diff or verification report the token should authorize")
    p_ver.add_argument("--token", required=True, metavar="HEX", help="the token to check")
    p_ver.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
