#!/usr/bin/env python3
"""Deterministic Governor floor pre-classifier (roadmap A2).

Implements the non-downgradable high-trust floor described in
core/commands/govern.md. Detects high-trust triggers from path segments,
file names, and diff text, then returns the floor tier so the Governor
can never silently lower a matched trigger below high-trust.

Tier order (lowest to highest): tiny < standard < spec < high-trust.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from pathlib import Path

# Ordered tier list, lowest to highest. Index position encodes rank.
_TIERS: list[str] = ["tiny", "standard", "spec", "high-trust"]


def _tier_rank(tier: str) -> int:
    """Return the numeric rank of a tier string. Raises ValueError for unknown tiers."""
    return _TIERS.index(tier)


# ---------------------------------------------------------------------------
# Path-based trigger definitions.
# Each entry is (trigger_id, matcher) where matcher is a callable(str) -> bool
# applied to every individual path segment (lowercased) OR the full path
# (lowercased, forward-slash normalised).
# ---------------------------------------------------------------------------

# Segment triggers fire when any single path segment equals the keyword exactly.
_SEGMENT_EXACT: dict[str, set[str]] = {
    "auth-path":            {"auth", "authentication", "authorize", "authorization"},
    "identity-path":        {"identity", "identities"},
    "session-path":         {"session", "sessions"},
    "payment-path":         {"payment", "payments", "pay", "checkout"},
    "billing-path":         {"billing"},
    "cryptography-path":    {"crypto", "cryptography", "cipher", "crypt"},
    "secrets-path":         {"secrets", "secret", "credentials", "credential",
                             "keystore", "keyring"},
    "security-policy-path": {"security", "security-policy", "secpolicy"},
    "privacy-path":         {"privacy", "pii", "gdpr", "dpa"},
    "data-retention-path":  {"retention", "redaction", "redact", "purge"},
    "clinical-path":        {"clinical", "mental-health", "mentalhealth",
                             "diagnosis", "medication", "crisis", "selfharm",
                             "self-harm", "regulated"},
    "safety-path":          {"safety"},
    "migration-path":       {"migrations", "migration"},
    "deploy-path":          {"deploy", "deployment", "deployments", "prod",
                             "production"},
    "egress-path":          {"egress", "proxy", "webhook", "webhooks"},
    "permissions-path":     {"permissions", "permission", "capabilities",
                             "capability", "grants", "grant", "roles", "role",
                             "acl", "iam", "rbac", "abac"},
}

# Glob patterns applied to the full lowercased forward-slash path.
_PATH_GLOBS: dict[str, list[str]] = {
    "secrets-path":         ["*secret*", "*credential*", "*.pem", "*.key",
                             "*.p12", "*.pfx", "*.jks", "*.keystore"],
    "cryptography-path":    ["*crypto*", "*cipher*", "*encrypt*", "*decrypt*",
                             "*hash*hmac*", "*hmac*"],
    "manifest-change":      ["*plugin.json", "*server.json", "*pyproject.toml",
                             "*package.json", "*/manifest.json",
                             "*/mcp-server*.json"],
    "release-artifact":     ["dist/*", "*/dist/*", "build/*", "*/build/*",
                             "releases/*", "*/releases/*", "*.whl",
                             "*release*.zip", "*release*.tar.gz"],
    "egress-path":          ["*network*", "*http_client*", "*httpclient*",
                             "*requests*", "*urllib*", "*aiohttp*"],
}

# ---------------------------------------------------------------------------
# Diff-text trigger definitions.
# Patterns are applied (re.search, IGNORECASE) to individual diff lines.
#
# Note: the govern.md "treats retrieved or untrusted input as a potential
# instruction" (injection) trigger is intentionally out of scope here. It is
# handled by the A3 injection-quarantine module, which binds its findings back
# to this floor.
# ---------------------------------------------------------------------------

_DIFF_PATTERNS: dict[str, list[str]] = {
    "secret-in-diff": [
        r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY",
        r"api[_\-]?key\s*=\s*['\"][A-Za-z0-9+/\-_]{8,}",
        r"api[_\-]?secret\s*=\s*['\"][A-Za-z0-9+/\-_]{8,}",
        r"secret[_\-]?key\s*=\s*['\"][A-Za-z0-9+/\-_]{8,}",
        r"private[_\-]?key\s*=\s*['\"][A-Za-z0-9+/\-_]{8,}",
        r"password\s*=\s*['\"][^'\"]{6,}",
        r"AKIA[0-9A-Z]{16}",                # AWS access key id
        r"[A-Za-z0-9+/]{40}",               # AWS secret-style 40-char base64
        r"ghp_[A-Za-z0-9]{30,}",            # GitHub personal access token
        r"sk-[A-Za-z0-9]{32,}",             # OpenAI-style key
    ],
    "high-trust-keyword-in-diff": [
        r"\bauth(?:\w+)?",                  # auth, authentication, authorization, etc.
        r"private[_\s]?key",
        r"session[_\s]?token",
        r"access[_\s]?token",
        r"(?<![A-Za-z])payment\w*",           # payment, payments, process_payment
        r"(?<![A-Za-z])billing(?!\w)",
        r"(?<![A-Za-z])pii(?!\w)",
        r"personal[_\s]?(?:data|information)",
        r"schema[_\s]?migration",
        r"bulk[_\s]?delete",
        r"force[_\-]?push",
        r"production[_\s]?deploy",
        r"(?<![A-Za-z])clinical\w*",        # clinical, clinical_assessment
        r"mental[_\s]?health",
        r"self[_\-]?harm",
        r"\bcrisis\b",
        r"\bdiagnos\w+",                    # diagnosis, diagnose, diagnostic
        r"\bmedication\b",
        r"cryptograph\w*",
        r"\bencrypt\w*",
        r"\bdecrypt\w*",
        r"\bhmac\b",
        r"(?<![A-Za-z])permission\w*",
        r"(?<![A-Za-z])capabilit(?:y|ies)",
    ],
}

# Compile diff patterns once at import time.
_COMPILED_DIFF: dict[str, list[re.Pattern[str]]] = {
    tid: [re.compile(p, re.IGNORECASE) for p in patterns]
    for tid, patterns in _DIFF_PATTERNS.items()
}


def _normalise_path(p: str) -> str:
    """Return the path lowercased with all separators converted to forward slashes."""
    return p.replace("\\", "/").lower()


def _segments(norm_path: str) -> list[str]:
    """Return the non-empty path segments from a normalised path string."""
    return [s for s in norm_path.split("/") if s]


def _check_paths(changed_paths: list[str]) -> list[str]:
    """Return the list of trigger ids that fire from the given path list."""
    fired: list[str] = []
    seen: set[str] = set()

    for raw in changed_paths:
        norm = _normalise_path(raw)
        segs = _segments(norm)

        # Segment-exact matching.
        for tid, keywords in _SEGMENT_EXACT.items():
            if tid in seen:
                continue
            if any(seg in keywords for seg in segs):
                fired.append(tid)
                seen.add(tid)

        # Glob matching against the full normalised path.
        for tid, globs in _PATH_GLOBS.items():
            if tid in seen:
                continue
            if any(fnmatch.fnmatch(norm, g) for g in globs):
                fired.append(tid)
                seen.add(tid)

    return fired


def _check_diff(diff_text: str) -> list[str]:
    """Return the list of trigger ids that fire from scanning the diff text."""
    if not diff_text:
        return []

    fired: list[str] = []
    seen: set[str] = set()

    for line in diff_text.splitlines():
        for tid, patterns in _COMPILED_DIFF.items():
            if tid in seen:
                continue
            if any(pat.search(line) for pat in patterns):
                fired.append(tid)
                seen.add(tid)
        if len(seen) == len(_COMPILED_DIFF):
            break  # All diff triggers already fired, no need to scan further.

    return fired


def classify_floor(
    changed_paths: list[str],
    diff_text: str = "",
) -> dict[str, object]:
    """Classify the floor tier from changed paths and optional diff text.

    Returns a dict with keys:
      tier             -- one of "tiny", "standard", "spec", "high-trust"
      triggers_matched -- list of stable trigger id strings that fired

    This function is deterministic and pure. It makes no network calls and
    has no side effects.

    The floor is a lower bound only. It is "tiny" when no triggers match.
    Any trigger match forces "high-trust".
    """
    path_triggers = _check_paths(changed_paths)
    diff_triggers = _check_diff(diff_text)

    all_triggers = list(dict.fromkeys(path_triggers + diff_triggers))  # stable, deduped

    # The floor only ever returns "tiny" or "high-trust" by design. It is a
    # lower bound. The two middle tiers (standard, spec) come from the model's
    # own classification and are applied by combine(), never lowered below this.
    tier = "high-trust" if all_triggers else "tiny"
    return {"tier": tier, "triggers_matched": all_triggers}


def combine(model_tier: str, floor_tier: str) -> str:
    """Return the higher of model_tier and floor_tier.

    The floor can raise the model tier but can never lower it. Tier order is
    tiny < standard < spec < high-trust. Raises ValueError for unknown tiers.
    """
    model_rank = _tier_rank(model_tier)
    floor_rank = _tier_rank(floor_tier)
    return _TIERS[max(model_rank, floor_rank)]


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic Governor floor classifier.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--paths",
        metavar="PATH",
        nargs="+",
        default=[],
        help="Changed file paths to classify.",
    )
    parser.add_argument(
        "--diff-file",
        metavar="FILE",
        default=None,
        help="Path to a file containing the unified diff to scan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints the decision JSON to stdout."""
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    diff_text = ""
    if args.diff_file:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8")

    decision = classify_floor(args.paths, diff_text)
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
