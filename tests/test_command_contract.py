"""The command/script contract gate: every flag a command's frontmatter invokes
must be a flag the named helper actually accepts. This is the gate that would
have caught the /clarify --require-spec defect, which the byte-for-byte drift
gate could not. After C1 the per-command scripts are thin shims, so the check
follows the shim into feature_ops.py.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _command_script_invocations():
    out = []
    for cmd in sorted((REPO / "core" / "commands").glob("*.md")):
        text = cmd.read_text(encoding="utf-8")
        for lang, pat in (("sh", r"^\s*sh:\s*(.+)$"), ("ps", r"^\s*ps:\s*(.+)$")):
            m = re.search(pat, text, re.MULTILINE)
            if not m:
                continue
            tokens = m.group(1).strip().split()
            flags = [t for t in tokens[1:] if t.startswith("-")]
            out.append((cmd.name, lang, tokens[0], flags))
    return out


def _shim_resolves_to_feature_ops(script_path: Path) -> Path | None:
    """If script_path is a thin shim that delegates to feature_ops.py, return the
    feature_ops.py path. Return None when the script is not a shim.

    A shim is identified by the presence of 'feature_ops.py' in its text together
    with a delegation call (exec python... or & $pyCmd ...).
    """
    text = script_path.read_text(encoding="utf-8")
    if "feature_ops.py" not in text:
        return None
    candidate = script_path.parent.parent / "feature_ops.py"
    if candidate.is_file():
        return candidate
    return None


def test_every_command_flag_is_implemented_by_its_script():
    invocations = _command_script_invocations()
    # At least clarify and implement declare script flags; guard against a parser regression.
    assert invocations, "no command declared a sh/ps script invocation"
    failures = []
    for cmd_name, lang, script_rel, flags in invocations:
        script_path = REPO / "core" / script_rel
        if not script_path.is_file():
            failures.append(f"{cmd_name} [{lang}] names a missing script: {script_rel}")
            continue

        # Follow the shim: if the script delegates to feature_ops.py, check flags
        # there instead. This preserves the real assertion while allowing the shim
        # pattern introduced by C1.
        target = _shim_resolves_to_feature_ops(script_path)
        if target is not None:
            search_text = target.read_text(encoding="utf-8")
        else:
            search_text = script_path.read_text(encoding="utf-8")

        for flag in flags:
            if lang == "sh":
                # bash flags appear as --flag in argparse add_argument calls.
                accepted = flag in search_text
            else:
                # PowerShell flags like -RequireSpec map to argparse dest or
                # the '-RequireSpec' / '--require-spec' string in feature_ops.py.
                bare = flag.lstrip("-")
                # Accept either the PowerShell-style dash-name or the
                # argparse long-flag equivalent (CamelCase -> hyphen-case not
                # needed: feature_ops uses both aliases in add_argument).
                accepted = (
                    ("-" + bare) in search_text
                    or ("$" + bare) in search_text
                )
            if not accepted:
                failures.append(
                    f"{cmd_name} [{lang}] invokes {flag} but"
                    f" {script_rel} (-> {target or script_path}) does not accept it"
                )
    assert not failures, "command/script contract violations:\n" + "\n".join(failures)
