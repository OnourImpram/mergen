#!/usr/bin/env python3
"""mergen adapter: per-host capability manifests, so a renderer never overclaims.

mergen renders one source in core/ into several host shells: native Claude Code skills,
a Spec Kit preset and extension, and a passive rule file for generic agents. The hosts do
not have the same powers. Claude Code runs lifecycle hooks and the Workflow orchestration.
Spec Kit carries the command suite and the verify gate but no Claude Code hooks. A generic
agent carries only the portable minimalism discipline. The honest scope used to live in
prose in each renderer. This makes it data.

Each host declares a manifest in core/adapters/<host>.json: a yes or no for every capability
in a fixed vocabulary, so none is left ambiguous. The Adapter SDK reads those manifests and
offers three things. validate checks a manifest is complete and well formed and that its name
matches its file. require_capability is the enforcement primitive a renderer calls to refuse a
capability the host's manifest denies. The built-in renderers do not wire it yet, so today it
guards any new or external renderer and backs the generated matrix, and adopting it in the
shipped renderers is a forward step, not a current claim. matrix generates the capability table
from the manifests, so the table is derived from the declared truth and can never drift from it
by hand.

Tier 0: pure standard library, deterministic, no network, no model. Exit codes: 0 success,
1 a validation or drift failure, 2 a usage or not-found error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_ADAPTERS_DIR = _REPO / "core" / "adapters"
_CAPABILITIES_DOC = _REPO / "docs" / "CAPABILITIES.md"

# The fixed capability vocabulary. Every manifest declares a boolean for each, so a host
# states a yes or a no for all of them. The order is the column and row order of the matrix
# and must match the schema's capabilities.required (a test asserts they agree, so neither
# can drift from the other).
CAPABILITY_KEYS: tuple[str, ...] = (
    "slash_commands",
    "command_suite",
    "lifecycle_hooks",
    "settings_registration",
    "project_bootstrap",
    "workflow_orchestration",
    "verify_gate",
    "passive_rules",
)


class CapabilityError(RuntimeError):
    """Raised when a host is asked for a capability its manifest denies."""


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_manifest(host: str, adapters_dir: Path | None = None) -> dict[str, Any]:
    """Load core/adapters/<host>.json. Raises FileNotFoundError when absent."""
    base = Path(adapters_dir) if adapters_dir is not None else _ADAPTERS_DIR
    path = base / f"{host}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def load_all_manifests(adapters_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load every manifest under the adapters directory, sorted by host name."""
    base = Path(adapters_dir) if adapters_dir is not None else _ADAPTERS_DIR
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*.json"))]
    manifests.sort(key=lambda m: str(m.get("host", "")))
    return manifests


# --------------------------------------------------------------------------- #
# Capability queries and the refusal guard
# --------------------------------------------------------------------------- #

def has_capability(manifest: dict[str, Any], capability: str) -> bool:
    """True when the manifest declares this capability and sets it true."""
    if capability not in CAPABILITY_KEYS:
        raise ValueError(f"unknown capability {capability!r}; known: {list(CAPABILITY_KEYS)}")
    caps = manifest.get("capabilities")
    return bool(caps.get(capability)) if isinstance(caps, dict) else False


def require_capability(host: str, capability: str, adapters_dir: Path | None = None) -> None:
    """Raise CapabilityError unless the host's manifest grants the capability.

    This is the guard a renderer calls before emitting a host-specific artifact, so the
    renderer refuses to claim a power the host's own manifest denies. The denial is data,
    declared in core/adapters/<host>.json, not a judgement made here.
    """
    manifest = load_manifest(host, adapters_dir)
    if not has_capability(manifest, capability):
        raise CapabilityError(
            f"host {host!r} does not provide capability {capability!r}; "
            "its manifest denies it, so a renderer must not claim it"
        )


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_manifest(manifest: dict[str, Any], expected_host: str) -> list[str]:
    """Return a list of human-readable errors. An empty list means the manifest conforms.

    Mirrors core/schemas/adapter-manifest.schema.json as a runtime check: the host matches
    the file name, the title is a non-empty string, every capability in the vocabulary is
    present and boolean, and no unknown capability or top-level key appears.
    """
    errors: list[str] = []
    host = manifest.get("host")
    if host != expected_host:
        errors.append(f"host {host!r} does not match the file name {expected_host!r}")
    if not isinstance(manifest.get("title"), str) or not manifest.get("title"):
        errors.append("title must be a non-empty string")
    if "note" in manifest and not isinstance(manifest["note"], str):
        errors.append("note must be a string")

    known_top = {"host", "title", "note", "capabilities"}
    for key in manifest:
        if key not in known_top:
            errors.append(f"unknown top-level field {key!r}")

    caps = manifest.get("capabilities")
    if not isinstance(caps, dict):
        errors.append("capabilities must be an object")
        return errors
    for key in caps:
        if key not in CAPABILITY_KEYS:
            errors.append(f"unknown capability {key!r}")
    for key in CAPABILITY_KEYS:
        if key not in caps:
            errors.append(f"missing capability {key!r}")
        elif not isinstance(caps[key], bool):
            errors.append(f"capability {key!r} must be a boolean")
    return errors


def validate_all(adapters_dir: Path | None = None) -> list[str]:
    """Validate every manifest. Returns all errors prefixed with the host file name."""
    base = Path(adapters_dir) if adapters_dir is not None else _ADAPTERS_DIR
    errors: list[str] = []
    for path in sorted(base.glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for err in validate_manifest(manifest, path.stem):
            errors.append(f"{path.name}: {err}")
    return errors


# --------------------------------------------------------------------------- #
# The generated capability matrix
# --------------------------------------------------------------------------- #

def render_capability_matrix(manifests: list[dict[str, Any]]) -> str:
    """Render the host capability matrix as deterministic Markdown.

    Columns are the hosts, ordered most-capable first then by name so the table reads from
    the full engine down to the portable discipline. Rows are the capability vocabulary in
    its canonical order. No timestamp appears, so the output is stable and a drift check can
    compare it byte for byte against the committed docs/CAPABILITIES.md.
    """
    hosts = sorted(
        manifests,
        key=lambda m: (-sum(1 for k in CAPABILITY_KEYS if has_capability(m, k)), str(m.get("host", ""))),
    )
    header = "| Capability | " + " | ".join(str(m.get("title", m.get("host", ""))) for m in hosts) + " |"
    divider = "| --- | " + " | ".join("---" for _ in hosts) + " |"
    rows = [
        "| `" + cap + "` | " + " | ".join("yes" if has_capability(m, cap) else "no" for m in hosts) + " |"
        for cap in CAPABILITY_KEYS
    ]
    notes = [f"- **{m.get('host')}**: {m.get('note')}" for m in hosts if m.get("note")]
    lines = [
        "# Mergen host capability matrix",
        "",
        "Generated from `core/adapters/*.json` by `scripts/adapter_sdk.py`. Do not edit by hand.",
        "Run `mergen adapter render --write` to regenerate it after a manifest changes.",
        "",
        header,
        divider,
        *rows,
        "",
        "## Honest scope per host",
        "",
        *notes,
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_matrix(args: argparse.Namespace) -> int:
    print(render_capability_matrix(load_all_manifests()))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    errors = validate_all()
    if errors:
        print("adapter manifests invalid:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("adapter manifests valid", file=sys.stderr)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        require_capability(args.host, args.capability)
    except CapabilityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"no manifest for host {args.host!r}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"host {args.host!r} provides {args.capability!r}", file=sys.stderr)
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    generated = render_capability_matrix(load_all_manifests())
    if args.write:
        # write_bytes keeps the file LF on every platform. write_text would translate the
        # newlines to CRLF on Windows, and the committed doc must be byte-identical to the
        # render so the drift check passes on Windows and on CI alike.
        _CAPABILITIES_DOC.write_bytes(generated.encode("utf-8"))
        print(f"wrote {_CAPABILITIES_DOC}", file=sys.stderr)
        return 0
    if args.check:
        # Compare raw bytes decoded as utf-8, not read_text, which would normalize CRLF to LF
        # on Windows and so mask a real drift that fails on a non-Windows CI runner.
        committed = _CAPABILITIES_DOC.read_bytes().decode("utf-8") if _CAPABILITIES_DOC.is_file() else ""
        if committed != generated:
            print("docs/CAPABILITIES.md is out of sync with the manifests. "
                  "Run mergen adapter render --write.", file=sys.stderr)
            return 1
        print("docs/CAPABILITIES.md is in sync with the manifests", file=sys.stderr)
        return 0
    print(generated)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mergen adapter", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_matrix = sub.add_parser("matrix", help="print the generated host capability matrix")
    p_matrix.set_defaults(func=_cmd_matrix)

    p_val = sub.add_parser("validate", help="validate every adapter manifest")
    p_val.set_defaults(func=_cmd_validate)

    p_check = sub.add_parser("check", help="exit 0 if a host provides a capability, 1 if not")
    p_check.add_argument("--host", required=True, help="the host name (native, speckit, agents)")
    p_check.add_argument("--capability", required=True, help="the capability to check")
    p_check.set_defaults(func=_cmd_check)

    p_render = sub.add_parser("render", help="render docs/CAPABILITIES.md, or --check it for drift")
    # --write and --check are contradictory (write then verify), so reject the pair rather than
    # silently honoring one and dropping the other.
    grp = p_render.add_mutually_exclusive_group()
    grp.add_argument("--check", action="store_true", help="exit 1 if the doc is out of sync")
    grp.add_argument("--write", action="store_true", help="write the doc to disk")
    p_render.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
