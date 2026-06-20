"""Focused unit tests for core/scripts/feature_ops.py.

These tests exercise the Python logic directly (no subprocess). They cover:
  - Path resolution (find_specify_root, get_repo_root, get/persist feature.json)
  - Feature-name generation (clean_branch_name, generate_branch_name,
    get_highest_from_specs)
  - JSON output contract for every subcommand (check-prerequisites, setup-plan,
    setup-tasks, create-new-feature)
  - m3 fold-in: setup-plan warns to stderr when spec.md is absent
  - Template resolution priority stack
  - Invoke-separator and format_speckit_command
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_FOPS_PATH = REPO / "core" / "scripts" / "feature_ops.py"


def _load_fops():
    spec = importlib.util.spec_from_file_location("feature_ops", _FOPS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fops = _load_fops()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _run(argv: list[str], tmp_path: Path, env: dict | None = None, monkeypatch=None) -> tuple[int, str, str]:
    """Call fops.main() in-process, capture stdout/stderr, return (rc, out, err)."""
    import io as _io

    out_buf = _io.StringIO()
    err_buf = _io.StringIO()

    if monkeypatch is not None and env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        rc = fops.main(argv)
    except SystemExit as e:
        rc = int(e.code) if e.code is not None else 0
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    return rc, out_buf.getvalue(), err_buf.getvalue()


def _make_specify(tmp_path: Path) -> Path:
    """Create a minimal .specify directory so get_repo_root resolves to tmp_path."""
    (tmp_path / ".specify").mkdir()
    return tmp_path


def _make_feature_json(tmp_path: Path, feature_dir: Path) -> None:
    """Write .specify/feature.json pointing at feature_dir."""
    rel = str(feature_dir.relative_to(tmp_path))
    fj = tmp_path / ".specify" / "feature.json"
    fj.write_text(json.dumps({"feature_directory": rel}), encoding="utf-8")


# --------------------------------------------------------------------------- #
# find_specify_root
# --------------------------------------------------------------------------- #

def test_find_specify_root_finds_marker(tmp_path):
    (tmp_path / ".specify").mkdir()
    result = fops.find_specify_root(tmp_path)
    assert result == tmp_path


def test_find_specify_root_walks_up(tmp_path):
    (tmp_path / ".specify").mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    result = fops.find_specify_root(deep)
    assert result == tmp_path


def test_find_specify_root_returns_none_when_absent(tmp_path):
    result = fops.find_specify_root(tmp_path)
    assert result is None


# --------------------------------------------------------------------------- #
# Feature JSON persistence
# --------------------------------------------------------------------------- #

def test_persist_feature_json_writes_relative_path(tmp_path):
    _make_specify(tmp_path)
    feature_dir = tmp_path / "specs" / "001-my-feature"
    feature_dir.mkdir(parents=True)
    fops.persist_feature_json(tmp_path, str(feature_dir))
    fj = tmp_path / ".specify" / "feature.json"
    data = json.loads(fj.read_text(encoding="utf-8"))
    # Should be stored as a relative path.
    assert not Path(data["feature_directory"]).is_absolute()


def test_persist_feature_json_skips_write_when_unchanged(tmp_path):
    _make_specify(tmp_path)
    feature_dir = tmp_path / "specs" / "001-x"
    feature_dir.mkdir(parents=True)
    fops.persist_feature_json(tmp_path, str(feature_dir))
    fj = tmp_path / ".specify" / "feature.json"
    mtime1 = fj.stat().st_mtime
    fops.persist_feature_json(tmp_path, str(feature_dir))
    mtime2 = fj.stat().st_mtime
    assert mtime1 == mtime2


def test_read_feature_json_returns_empty_when_missing(tmp_path):
    _make_specify(tmp_path)
    result = fops.read_feature_json_feature_directory(tmp_path)
    assert result == ""


def test_read_feature_json_returns_value(tmp_path):
    _make_specify(tmp_path)
    fj = tmp_path / ".specify" / "feature.json"
    fj.write_text('{"feature_directory": "specs/001-foo"}', encoding="utf-8")
    result = fops.read_feature_json_feature_directory(tmp_path)
    assert result == "specs/001-foo"


# --------------------------------------------------------------------------- #
# Feature-name generation
# --------------------------------------------------------------------------- #

def test_clean_branch_name_lowercases_and_hyphenates():
    assert fops.clean_branch_name("Hello World!") == "hello-world"


def test_clean_branch_name_collapses_multiple_hyphens():
    assert fops.clean_branch_name("foo---bar") == "foo-bar"


def test_clean_branch_name_strips_leading_trailing():
    assert fops.clean_branch_name("--foo--") == "foo"


def test_generate_branch_name_filters_stop_words():
    result = fops.generate_branch_name("Add user authentication system")
    # "add" is a stop word, "user" < 3 chars is not (len=4), "authentication" ok
    assert "add" not in result.split("-")
    assert len(result) > 0


def test_generate_branch_name_uses_up_to_three_words():
    result = fops.generate_branch_name("implement oauth2 integration for api")
    parts = result.split("-")
    assert 1 <= len(parts) <= 4


def test_generate_branch_name_uses_four_words_when_exactly_four_meaningful():
    # "oauth2" "integration" "system" "monitoring" = 4 meaningful words
    result = fops.generate_branch_name("oauth2 integration system monitoring")
    parts = result.split("-")
    assert len(parts) == 4


def test_get_highest_from_specs_returns_zero_when_empty(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    assert fops.get_highest_from_specs(specs) == 0


def test_get_highest_from_specs_finds_highest(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    for name in ("001-foo", "002-bar", "010-baz"):
        (specs / name).mkdir()
    assert fops.get_highest_from_specs(specs) == 10


def test_get_highest_from_specs_ignores_timestamp_dirs(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "20240101-120000-feature").mkdir()
    assert fops.get_highest_from_specs(specs) == 0


# --------------------------------------------------------------------------- #
# Template resolution
# --------------------------------------------------------------------------- #

def test_resolve_template_returns_none_when_not_found(tmp_path):
    _make_specify(tmp_path)
    result = fops.resolve_template("no-such-template", tmp_path)
    assert result is None


def test_resolve_template_finds_core_template(tmp_path):
    _make_specify(tmp_path)
    templates_dir = tmp_path / ".specify" / "templates"
    templates_dir.mkdir(parents=True)
    core = templates_dir / "plan-template.md"
    core.write_text("# Plan", encoding="utf-8")
    result = fops.resolve_template("plan-template", tmp_path)
    assert result == core


def test_resolve_template_override_wins_over_core(tmp_path):
    _make_specify(tmp_path)
    templates_dir = tmp_path / ".specify" / "templates"
    (templates_dir / "overrides").mkdir(parents=True)
    override = templates_dir / "overrides" / "plan-template.md"
    override.write_text("# Override", encoding="utf-8")
    core = templates_dir / "plan-template.md"
    core.write_text("# Core", encoding="utf-8")
    result = fops.resolve_template("plan-template", tmp_path)
    assert result == override


# --------------------------------------------------------------------------- #
# invoke separator and format_speckit_command
# --------------------------------------------------------------------------- #

def test_get_invoke_separator_defaults_to_dot(tmp_path):
    _make_specify(tmp_path)
    assert fops.get_invoke_separator(tmp_path) == "."


def test_get_invoke_separator_reads_integration_json(tmp_path):
    _make_specify(tmp_path)
    integration = tmp_path / ".specify" / "integration.json"
    integration.write_text(
        json.dumps({
            "default_integration": "cc",
            "integration_settings": {"cc": {"invoke_separator": "-"}},
        }),
        encoding="utf-8",
    )
    assert fops.get_invoke_separator(tmp_path) == "-"


def test_format_speckit_command_dot_separator(tmp_path):
    _make_specify(tmp_path)
    result = fops.format_speckit_command("plan", tmp_path)
    assert result == "/speckit.plan"


def test_format_speckit_command_dash_separator(tmp_path):
    _make_specify(tmp_path)
    integration = tmp_path / ".specify" / "integration.json"
    integration.write_text(
        json.dumps({
            "default_integration": "cc",
            "integration_settings": {"cc": {"invoke_separator": "-"}},
        }),
        encoding="utf-8",
    )
    result = fops.format_speckit_command("plan", tmp_path)
    assert result == "/speckit-plan"


# --------------------------------------------------------------------------- #
# Subcommand: check-prerequisites  --json output contract
# --------------------------------------------------------------------------- #

def _make_feature_env(tmp_path: Path) -> tuple[Path, Path]:
    """Return (repo_root, feature_dir) for a minimal repo with plan.md present."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_specify(repo)
    fd = repo / "specs" / "001-feat"
    fd.mkdir(parents=True)
    (fd / "plan.md").write_text("# Plan", encoding="utf-8")
    _make_feature_json(repo, fd)
    return repo, fd


def test_check_prerequisites_json_keys(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["check-prerequisites", "--json"], tmp_path)
    assert rc == 0
    data = json.loads(out.strip())
    assert "FEATURE_DIR" in data
    assert "AVAILABLE_DOCS" in data
    assert isinstance(data["AVAILABLE_DOCS"], list)


def test_check_prerequisites_paths_only_json(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["check-prerequisites", "--json", "--paths-only"], tmp_path)
    assert rc == 0
    data = json.loads(out.strip())
    for key in ("REPO_ROOT", "BRANCH", "FEATURE_DIR", "FEATURE_SPEC", "IMPL_PLAN", "TASKS"):
        assert key in data, f"missing key {key}"


def test_check_prerequisites_require_spec_fails_when_missing(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    # plan.md exists but spec.md does not.
    rc, out, err = _run(["check-prerequisites", "--json", "--require-spec"], tmp_path)
    assert rc != 0
    assert "spec.md" in err


def test_check_prerequisites_require_spec_passes_when_present(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    (fd / "spec.md").write_text("# Spec", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["check-prerequisites", "--json", "--require-spec"], tmp_path)
    assert rc == 0


def test_check_prerequisites_require_tasks_fails_when_missing(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["check-prerequisites", "--json", "--require-tasks"], tmp_path)
    assert rc != 0
    assert "tasks.md" in err


def test_check_prerequisites_include_tasks_in_docs(tmp_path, monkeypatch):
    repo, fd = _make_feature_env(tmp_path)
    (fd / "tasks.md").write_text("# Tasks", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["check-prerequisites", "--json", "--include-tasks", "--require-tasks"], tmp_path
    )
    assert rc == 0
    data = json.loads(out.strip())
    assert "tasks.md" in data["AVAILABLE_DOCS"]


# --------------------------------------------------------------------------- #
# Subcommand: setup-plan  --json output contract + m3 warning
# --------------------------------------------------------------------------- #

def _make_plan_env(tmp_path: Path) -> tuple[Path, Path]:
    """Return (repo_root, feature_dir) with a plan template and spec absent."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_specify(repo)
    templates = repo / ".specify" / "templates"
    templates.mkdir(parents=True)
    (templates / "plan-template.md").write_text("# Plan template", encoding="utf-8")
    fd = repo / "specs" / "001-feat"
    fd.mkdir(parents=True)
    _make_feature_json(repo, fd)
    return repo, fd


def test_setup_plan_json_keys(tmp_path, monkeypatch):
    repo, fd = _make_plan_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-plan", "--json"], tmp_path)
    assert rc == 0
    data = json.loads(out.strip())
    for key in ("FEATURE_SPEC", "IMPL_PLAN", "SPECS_DIR", "BRANCH"):
        assert key in data, f"missing key {key}"


def test_setup_plan_creates_plan_from_template(tmp_path, monkeypatch):
    repo, fd = _make_plan_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    assert not (fd / "plan.md").exists()
    rc, out, err = _run(["setup-plan", "--json"], tmp_path)
    assert rc == 0
    assert (fd / "plan.md").exists()
    assert (fd / "plan.md").read_text(encoding="utf-8") == "# Plan template"


def test_setup_plan_warns_to_stderr_when_spec_absent(tmp_path, monkeypatch):
    """m3: setup-plan must warn (non-fatal) when spec.md is absent."""
    repo, fd = _make_plan_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-plan", "--json"], tmp_path)
    assert rc == 0, "setup-plan must not fail when spec.md is absent"
    assert "spec.md" in err, "setup-plan must warn to stderr when spec.md is absent"
    assert "warn" in err.lower() or "warning" in err.lower()


def test_setup_plan_no_warning_when_spec_present(tmp_path, monkeypatch):
    """m3: no spec-absent warning when spec.md exists."""
    repo, fd = _make_plan_env(tmp_path)
    (fd / "spec.md").write_text("# Spec", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-plan", "--json"], tmp_path)
    assert rc == 0
    # The stderr warning about spec.md being absent must not appear.
    assert "spec.md not found" not in err


def test_setup_plan_skips_template_when_plan_exists(tmp_path, monkeypatch):
    repo, fd = _make_plan_env(tmp_path)
    existing_content = "# Existing plan"
    (fd / "plan.md").write_text(existing_content, encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-plan", "--json"], tmp_path)
    assert rc == 0
    assert (fd / "plan.md").read_text(encoding="utf-8") == existing_content


# --------------------------------------------------------------------------- #
# Subcommand: setup-tasks  --json output contract
# --------------------------------------------------------------------------- #

def _make_tasks_env(tmp_path: Path) -> tuple[Path, Path]:
    """Return (repo_root, feature_dir) with plan.md, spec.md, and tasks template."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_specify(repo)
    templates = repo / ".specify" / "templates"
    templates.mkdir(parents=True)
    (templates / "tasks-template.md").write_text("# Tasks template", encoding="utf-8")
    fd = repo / "specs" / "001-feat"
    fd.mkdir(parents=True)
    (fd / "plan.md").write_text("# Plan", encoding="utf-8")
    (fd / "spec.md").write_text("# Spec", encoding="utf-8")
    _make_feature_json(repo, fd)
    return repo, fd


def test_setup_tasks_json_keys(tmp_path, monkeypatch):
    repo, fd = _make_tasks_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-tasks", "--json"], tmp_path)
    assert rc == 0
    data = json.loads(out.strip())
    for key in ("FEATURE_DIR", "AVAILABLE_DOCS", "TASKS_TEMPLATE"):
        assert key in data, f"missing key {key}"
    assert isinstance(data["AVAILABLE_DOCS"], list)


def test_setup_tasks_fails_without_plan(tmp_path, monkeypatch):
    repo, fd = _make_tasks_env(tmp_path)
    (fd / "plan.md").unlink()
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-tasks", "--json"], tmp_path)
    assert rc != 0
    assert "plan.md" in err


def test_setup_tasks_fails_without_spec(tmp_path, monkeypatch):
    repo, fd = _make_tasks_env(tmp_path)
    (fd / "spec.md").unlink()
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-tasks", "--json"], tmp_path)
    assert rc != 0
    assert "spec.md" in err


def test_setup_tasks_fails_without_template(tmp_path, monkeypatch):
    repo, fd = _make_tasks_env(tmp_path)
    (repo / ".specify" / "templates" / "tasks-template.md").unlink()
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-tasks", "--json"], tmp_path)
    assert rc != 0
    assert "tasks-template" in err


def test_setup_tasks_available_docs_detects_research(tmp_path, monkeypatch):
    repo, fd = _make_tasks_env(tmp_path)
    (fd / "research.md").write_text("# Research", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["setup-tasks", "--json"], tmp_path)
    assert rc == 0
    data = json.loads(out.strip())
    assert "research.md" in data["AVAILABLE_DOCS"]


# --------------------------------------------------------------------------- #
# Subcommand: create-new-feature  --json output contract
# --------------------------------------------------------------------------- #

def _make_create_env(tmp_path: Path) -> Path:
    """Return repo_root with .specify and a spec template."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_specify(repo)
    templates = repo / ".specify" / "templates"
    templates.mkdir(parents=True)
    (templates / "spec-template.md").write_text("# Spec template", encoding="utf-8")
    return repo


def test_create_new_feature_json_keys(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--dry-run", "Add authentication system"],
        tmp_path,
    )
    assert rc == 0
    data = json.loads(out.strip())
    for key in ("BRANCH_NAME", "SPEC_FILE", "FEATURE_NUM"):
        assert key in data, f"missing key {key}"
    assert data.get("DRY_RUN") is True


def test_create_new_feature_uses_short_name(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--dry-run", "--short-name", "user-auth",
         "Add authentication system"],
        tmp_path,
    )
    assert rc == 0
    data = json.loads(out.strip())
    assert "user-auth" in data["BRANCH_NAME"]


def test_create_new_feature_uses_explicit_number(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--dry-run", "--number", "42",
         "some feature"],
        tmp_path,
    )
    assert rc == 0
    data = json.loads(out.strip())
    assert data["FEATURE_NUM"] == "042"
    assert data["BRANCH_NAME"].startswith("042-")


def test_create_new_feature_timestamp_prefix(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--dry-run", "--timestamp",
         "--short-name", "ts-feat", "some feature"],
        tmp_path,
    )
    assert rc == 0
    data = json.loads(out.strip())
    import re
    assert re.match(r"^\d{8}-\d{6}-", data["BRANCH_NAME"]), (
        f"Expected timestamp prefix, got: {data['BRANCH_NAME']}"
    )


def test_create_new_feature_creates_files(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--number", "5",
         "--short-name", "my-feat", "My feature"],
        tmp_path,
    )
    assert rc == 0
    data = json.loads(out.strip())
    spec_file = Path(data["SPEC_FILE"])
    assert spec_file.exists(), "spec.md should have been created"
    assert spec_file.read_text(encoding="utf-8") == "# Spec template"


def test_create_new_feature_fails_on_empty_description(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(["create-new-feature", "--json"], tmp_path)
    assert rc != 0


def test_create_new_feature_number_and_timestamp_warns(tmp_path, monkeypatch):
    repo = _make_create_env(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    rc, out, err = _run(
        ["create-new-feature", "--json", "--dry-run",
         "--timestamp", "--number", "5", "some feature"],
        tmp_path,
    )
    assert rc == 0
    assert "--number is ignored" in err or "ignored" in err.lower()


# --------------------------------------------------------------------------- #
# build_available_docs helper
# --------------------------------------------------------------------------- #

def test_build_available_docs_empty_when_nothing_present(tmp_path):
    fd = tmp_path / "feat"
    fd.mkdir()
    paths = {
        "RESEARCH": str(fd / "research.md"),
        "DATA_MODEL": str(fd / "data-model.md"),
        "CONTRACTS_DIR": str(fd / "contracts"),
        "QUICKSTART": str(fd / "quickstart.md"),
        "TASKS": str(fd / "tasks.md"),
    }
    assert fops.build_available_docs(paths) == []


def test_build_available_docs_detects_all_present(tmp_path):
    fd = tmp_path / "feat"
    fd.mkdir()
    contracts = fd / "contracts"
    contracts.mkdir()
    (contracts / "api.md").write_text("# API", encoding="utf-8")
    for name in ("research.md", "data-model.md", "quickstart.md", "tasks.md"):
        (fd / name).write_text("x", encoding="utf-8")
    paths = {
        "RESEARCH": str(fd / "research.md"),
        "DATA_MODEL": str(fd / "data-model.md"),
        "CONTRACTS_DIR": str(contracts),
        "QUICKSTART": str(fd / "quickstart.md"),
        "TASKS": str(fd / "tasks.md"),
    }
    docs = fops.build_available_docs(paths, include_tasks=True)
    assert "research.md" in docs
    assert "data-model.md" in docs
    assert "contracts/" in docs
    assert "quickstart.md" in docs
    assert "tasks.md" in docs


def test_build_available_docs_tasks_excluded_by_default(tmp_path):
    fd = tmp_path / "feat"
    fd.mkdir()
    (fd / "tasks.md").write_text("x", encoding="utf-8")
    paths = {
        "RESEARCH": str(fd / "research.md"),
        "DATA_MODEL": str(fd / "data-model.md"),
        "CONTRACTS_DIR": str(fd / "contracts"),
        "QUICKSTART": str(fd / "quickstart.md"),
        "TASKS": str(fd / "tasks.md"),
    }
    docs = fops.build_available_docs(paths, include_tasks=False)
    assert "tasks.md" not in docs
