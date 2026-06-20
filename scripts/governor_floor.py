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
import sys
from pathlib import Path
from typing import Any

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
) -> dict[str, Any]:
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


def _build_policy_catalog() -> list[tuple[str, str]]:
    """Return the ordered, deduped catalog of (policy_id, source) the floor checks.

    A policy id can be checked two ways (a segment match and a glob match share
    one id, for example "secrets-path"). The catalog records each id once, in a
    stable order, tagged with where it is evaluated: "path" for the path-based
    guards, "diff" for the diff-text guards.
    """
    catalog: list[tuple[str, str]] = []
    seen: set[str] = set()
    for policy_id in _SEGMENT_EXACT:
        if policy_id not in seen:
            catalog.append((policy_id, "path"))
            seen.add(policy_id)
    for policy_id in _PATH_GLOBS:
        if policy_id not in seen:
            catalog.append((policy_id, "path"))
            seen.add(policy_id)
    for policy_id in _DIFF_PATTERNS:
        if policy_id not in seen:
            catalog.append((policy_id, "diff"))
            seen.add(policy_id)
    return catalog


# The full set of floor guards, computed once. Stable and deterministic.
_POLICY_CATALOG: list[tuple[str, str]] = _build_policy_catalog()


def policy_results(
    changed_paths: list[str],
    diff_text: str = "",
    include_passing: bool = False,
) -> list[dict[str, Any]]:
    """Return a per-policy audit trail for the floor decision.

    Each entry uses the shared policy-result shape {policy_id, result, reason}
    that verification-report.json also uses, so the Governor and the verifier
    speak one policy vocabulary. A guard that matched the change is a tripped
    high-trust floor and reports result "fail" (a non-downgradable escalation,
    the policy-engine sense of a deny rule firing). A guard that did not match
    reports "pass".

    By default only the tripped guards are returned, which keeps the trace
    minimal. Pass include_passing=True for the full evaluated catalog, the
    record an auditor needs to confirm every guard was actually checked.

    Scope: the built-in path and diff floor catalog. The config-overlay and
    injection guards are applied in a later layer and surface their own ids in
    triggers_matched.
    """
    fired = set(_check_paths(changed_paths)) | set(_check_diff(diff_text))
    results: list[dict[str, Any]] = []
    for policy_id, source in _POLICY_CATALOG:
        if policy_id in fired:
            results.append({
                "policy_id": policy_id,
                "result": "fail",
                "reason": f"matched the high-trust floor via {source}",
            })
        elif include_passing:
            results.append({
                "policy_id": policy_id,
                "result": "pass",
                "reason": f"no {source} match",
            })
    return results


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
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Exit non-zero when the diff reaches the high-trust floor and is "
             "not acknowledged. For CI on a real pull-request diff.",
    )
    parser.add_argument(
        "--ack",
        metavar="TIER",
        default="",
        help="Acknowledgement tier supplied by a human reviewer (for example "
             "'high-trust'). Under --gate it authorises a matching floor.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Path to a project .specify/mergen.toml. Its domain and "
             "protected-path overlay can raise the floor, never lower it.",
    )
    parser.add_argument(
        "--scan-injection",
        action="store_true",
        help="Also scan the diff for prompt injection (A3). A detection forces "
             "high-trust. Opt-in, because the patterns fire on security prose.",
    )
    parser.add_argument(
        "--policy-trace",
        nargs="?",
        const="matched",
        choices=["matched", "all"],
        default=None,
        help="Add a per-policy audit trail (policy_results) to the decision "
             "JSON. Bare or 'matched' lists only the floor guards that tripped; "
             "'all' lists every guard evaluated, matched or not.",
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

    if args.config:
        # The project overlay lives beside this script. Load it lazily so the
        # core classifier has no dependency on the config reader.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import project_config
        cfg = project_config.load_config(Path(args.config))
        decision = project_config.apply_overlay(decision, cfg, args.paths)

    if args.scan_injection and diff_text:
        # A3 binds back here: a diff that carries injection text is forced to
        # high-trust. The injection module owns the detection; the floor owns
        # the consequence.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import injection_quarantine
        inj = injection_quarantine.classify(diff_text)
        if inj["injection_detected"]:
            triggers = list(decision.get("triggers_matched", []))
            if "injection-detected" not in triggers:
                triggers.append("injection-detected")
            decision = {**decision, "tier": "high-trust", "triggers_matched": triggers}

    if args.policy_trace is not None:
        # Auditable policy-as-code trace, in the shape shared with the verify
        # report. Reflects the built-in floor catalog (path + diff guards).
        decision = {
            **decision,
            "policy_results": policy_results(
                args.paths, diff_text, include_passing=(args.policy_trace == "all")
            ),
        }

    print(json.dumps(decision, indent=2))

    if args.gate and decision["tier"] == "high-trust":
        if (args.ack or "").strip().lower() == "high-trust":
            print(
                "governor floor: high-trust acknowledged by a human reviewer, gate passes.",
                file=sys.stderr,
            )
            return 0
        trigger_list = ", ".join(decision["triggers_matched"]) or "none"
        print(
            "governor floor: this diff reaches the high-trust tier "
            f"(triggers: {trigger_list}). A human must review it and record the "
            "acknowledgement line 'Governor-Ack: high-trust' in the pull-request "
            "body before it can merge. The floor is non-downgradable.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
