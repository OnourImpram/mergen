"""Tests for scripts/governor_floor.py.

Verifies deterministic floor classification for every trigger class defined
in core/commands/govern.md, and verifies the combine() invariant that the
floor can raise but never lower the model tier.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loading helper so the test does not depend on the package being
# installed. The scripts/ directory is not a package, so we load by file path.
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "governor_floor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("governor_floor", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_m = _load_module()
classify_floor = _m.classify_floor
combine = _m.combine
main = _m.main


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_high_trust(result: dict) -> bool:
    return result["tier"] == "high-trust"


def _is_tiny(result: dict) -> bool:
    return result["tier"] == "tiny"


def _triggers(result: dict) -> list[str]:
    return result["triggers_matched"]


# ===========================================================================
# Path-based trigger classes
# ===========================================================================


class TestAuthPathTrigger:
    def test_auth_segment_forces_high_trust(self):
        result = classify_floor(["src/auth/login.py"])
        assert _is_high_trust(result)
        assert "auth-path" in _triggers(result)

    def test_authentication_segment(self):
        result = classify_floor(["app/authentication/handler.py"])
        assert _is_high_trust(result)

    def test_identity_segment(self):
        result = classify_floor(["services/identity/user.py"])
        assert _is_high_trust(result)
        assert "identity-path" in _triggers(result)

    def test_session_segment(self):
        result = classify_floor(["middleware/session/store.py"])
        assert _is_high_trust(result)
        assert "session-path" in _triggers(result)


class TestPaymentBillingTrigger:
    def test_payment_segment(self):
        result = classify_floor(["api/payment/webhook.py"])
        assert _is_high_trust(result)
        assert "payment-path" in _triggers(result)

    def test_billing_segment(self):
        result = classify_floor(["backend/billing/invoices.py"])
        assert _is_high_trust(result)
        assert "billing-path" in _triggers(result)

    def test_checkout_segment(self):
        result = classify_floor(["store/checkout/flow.py"])
        assert _is_high_trust(result)


class TestCryptographySecretsTrigger:
    def test_crypto_segment(self):
        result = classify_floor(["lib/crypto/aes.py"])
        assert _is_high_trust(result)
        assert "cryptography-path" in _triggers(result)

    def test_secret_segment(self):
        result = classify_floor(["config/secret/vault.py"])
        assert _is_high_trust(result)
        assert "secrets-path" in _triggers(result)

    def test_credentials_segment(self):
        result = classify_floor(["ops/credentials/rotate.sh"])
        assert _is_high_trust(result)

    def test_pem_glob(self):
        result = classify_floor(["certs/server.pem"])
        assert _is_high_trust(result)

    def test_key_glob(self):
        result = classify_floor(["keys/id_rsa.key"])
        assert _is_high_trust(result)


class TestSecurityPolicyTrigger:
    def test_security_segment(self):
        result = classify_floor(["app/security/policy.py"])
        assert _is_high_trust(result)
        assert "security-policy-path" in _triggers(result)


class TestPrivacyPiiTrigger:
    def test_privacy_segment(self):
        result = classify_floor(["services/privacy/consent.py"])
        assert _is_high_trust(result)
        assert "privacy-path" in _triggers(result)

    def test_pii_segment(self):
        result = classify_floor(["handlers/pii/mask.py"])
        assert _is_high_trust(result)

    def test_redaction_segment(self):
        result = classify_floor(["pipeline/redaction/runner.py"])
        assert _is_high_trust(result)
        assert "data-retention-path" in _triggers(result)

    def test_retention_segment(self):
        result = classify_floor(["jobs/retention/cleanup.py"])
        assert _is_high_trust(result)


class TestClinicalSafetyTrigger:
    def test_clinical_segment(self):
        result = classify_floor(["modules/clinical/assessment.py"])
        assert _is_high_trust(result)
        assert "clinical-path" in _triggers(result)

    def test_mental_health_segment(self):
        result = classify_floor(["content/mental-health/crisis.md"])
        assert _is_high_trust(result)

    def test_crisis_segment(self):
        result = classify_floor(["flows/crisis/intervention.py"])
        assert _is_high_trust(result)

    def test_safety_segment(self):
        result = classify_floor(["core/safety/guardrails.py"])
        assert _is_high_trust(result)
        assert "safety-path" in _triggers(result)


class TestMigrationIrreversibleTrigger:
    def test_migrations_directory(self):
        result = classify_floor(["db/migrations/0042_add_index.sql"])
        assert _is_high_trust(result)
        assert "migration-path" in _triggers(result)

    def test_migration_singular(self):
        result = classify_floor(["src/migration/runner.py"])
        assert _is_high_trust(result)

    def test_deploy_segment(self):
        result = classify_floor(["scripts/deploy/prod.sh"])
        assert _is_high_trust(result)
        assert "deploy-path" in _triggers(result)

    def test_production_segment(self):
        result = classify_floor(["infra/production/terraform.tf"])
        assert _is_high_trust(result)


class TestManifestVersionTrigger:
    def test_plugin_json(self):
        result = classify_floor(["plugin.json"])
        assert _is_high_trust(result)
        assert "manifest-change" in _triggers(result)

    def test_server_json(self):
        result = classify_floor(["config/server.json"])
        assert _is_high_trust(result)

    def test_pyproject_toml(self):
        result = classify_floor(["pyproject.toml"])
        assert _is_high_trust(result)

    def test_package_json(self):
        result = classify_floor(["frontend/package.json"])
        assert _is_high_trust(result)

    def test_manifest_json_in_subdir(self):
        result = classify_floor(["extensions/mcp/manifest.json"])
        assert _is_high_trust(result)


class TestReleaseArtifactTrigger:
    def test_bare_dist_wheel_forces_high_trust(self):
        # Regression: a wheel directly inside dist/ (the standard Python build
        # output) was silently let through when the glob required a leading
        # path component.
        result = classify_floor(["dist/myapp-1.0.whl"])
        assert _is_high_trust(result)
        assert "release-artifact" in _triggers(result)

    def test_nested_dist_artifact(self):
        result = classify_floor(["project/dist/app-2.0.tar.gz"])
        assert _is_high_trust(result)
        assert "release-artifact" in _triggers(result)

    def test_build_dir_artifact(self):
        result = classify_floor(["build/lib/module.py"])
        assert _is_high_trust(result)

    def test_releases_dir(self):
        result = classify_floor(["releases/v1.2.3/notes.md"])
        assert _is_high_trust(result)

    def test_top_level_wheel(self):
        result = classify_floor(["mergen-1.0.0-py3-none-any.whl"])
        assert _is_high_trust(result)


class TestNetworkEgressPermissionsTrigger:
    def test_egress_segment(self):
        result = classify_floor(["infra/egress/rules.yaml"])
        assert _is_high_trust(result)
        assert "egress-path" in _triggers(result)

    def test_permissions_segment(self):
        result = classify_floor(["iam/permissions/policy.json"])
        assert _is_high_trust(result)
        assert "permissions-path" in _triggers(result)

    def test_capabilities_segment(self):
        result = classify_floor(["system/capabilities/registry.py"])
        assert _is_high_trust(result)

    def test_roles_segment(self):
        result = classify_floor(["access/roles/admin.py"])
        assert _is_high_trust(result)


# ===========================================================================
# Diff-text trigger classes
# ===========================================================================


class TestSecretInDiff:
    def test_private_key_header(self):
        diff = "+-----BEGIN RSA PRIVATE KEY-----\n+MIIEowIBAAKCAQEA..."
        result = classify_floor([], diff)
        assert _is_high_trust(result)
        assert "secret-in-diff" in _triggers(result)

    def test_api_key_assignment(self):
        diff = "+api_key = 'sk-abc123XYZsecretvalue'"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_aws_access_key_id(self):
        diff = "+AWS_ACCESS_KEY_ID = 'AKIAIOSFODNN7EXAMPLE'"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_github_token(self):
        diff = "+token = 'ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456'"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_openai_style_key(self):
        diff = "+OPENAI_KEY = 'sk-verylongkeyvaluethatexceedsminlength'"
        result = classify_floor([], diff)
        assert _is_high_trust(result)


class TestHighTrustKeywordInDiff:
    def test_auth_keyword(self):
        diff = "+  if not user.authentication_valid():"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_schema_migration_keyword(self):
        diff = "+# schema migration: drop users table"
        result = classify_floor([], diff)
        assert _is_high_trust(result)
        assert "high-trust-keyword-in-diff" in _triggers(result)

    def test_bulk_delete_keyword(self):
        diff = "+  bulk_delete(records)"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_clinical_keyword(self):
        diff = "+def run_clinical_assessment(patient):"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_payment_keyword(self):
        diff = "+charge = process_payment(amount)"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_encrypt_keyword(self):
        diff = "+data = encrypt(payload, key)"
        result = classify_floor([], diff)
        assert _is_high_trust(result)

    def test_permission_keyword_snake_case(self):
        # Regression: "\\bpermission" missed snake_case names because the
        # underscore is a word char, so no word boundary exists before it.
        diff = "+def check_permission(user, resource):"
        result = classify_floor([], diff)
        assert _is_high_trust(result)
        assert "high-trust-keyword-in-diff" in _triggers(result)

    def test_capability_keyword_snake_case(self):
        diff = "+grant_capability(agent, scope)"
        result = classify_floor([], diff)
        assert _is_high_trust(result)


# ===========================================================================
# Benign paths stay tiny
# ===========================================================================


class TestBenignStaysTiny:
    def test_plain_docs(self):
        result = classify_floor(["docs/README.md"])
        assert _is_tiny(result)
        assert _triggers(result) == []

    def test_readme_only(self):
        result = classify_floor(["README.md"])
        assert _is_tiny(result)

    def test_test_file(self):
        result = classify_floor(["tests/test_utils.py"])
        assert _is_tiny(result)

    def test_changelog_prose(self):
        # changelog without a path segment that matches a trigger segment.
        result = classify_floor(["docs/changelog.txt"])
        assert _is_tiny(result)

    def test_empty_paths_and_no_diff(self):
        result = classify_floor([])
        assert _is_tiny(result)
        assert _triggers(result) == []

    def test_plain_diff_no_keywords(self):
        diff = (
            "-old_value = 42\n"
            "+new_value = 43\n"
            " # update constant\n"
        )
        result = classify_floor(["src/config.py"], diff)
        # src/config.py has no trigger segments, diff has no trigger patterns.
        assert _is_tiny(result)

    def test_nested_docs_path(self):
        result = classify_floor(["docs/architecture/overview.md"])
        assert _is_tiny(result)


# ===========================================================================
# combine() invariant tests
# ===========================================================================


class TestCombineInvariant:
    def test_floor_raises_model(self):
        """model tiny + floor high-trust must yield high-trust."""
        assert combine("tiny", "high-trust") == "high-trust"

    def test_model_raises_above_tiny_floor(self):
        """model spec + floor tiny must yield spec (model is higher)."""
        assert combine("spec", "tiny") == "spec"

    def test_equal_tiers(self):
        """Same tier on both sides returns that tier."""
        for t in ["tiny", "standard", "spec", "high-trust"]:
            assert combine(t, t) == t

    def test_floor_can_raise_standard_to_high_trust(self):
        assert combine("standard", "high-trust") == "high-trust"

    def test_model_high_trust_floor_tiny_stays_high_trust(self):
        assert combine("high-trust", "tiny") == "high-trust"

    def test_model_standard_floor_spec(self):
        assert combine("standard", "spec") == "spec"

    def test_model_spec_floor_standard(self):
        assert combine("spec", "standard") == "spec"

    def test_full_order_tiny_lt_standard_lt_spec_lt_high_trust(self):
        tiers = ["tiny", "standard", "spec", "high-trust"]
        for i, lower in enumerate(tiers):
            for upper in tiers[i + 1:]:
                assert combine(lower, upper) == upper
                assert combine(upper, lower) == upper


# ===========================================================================
# Multiple paths, multiple triggers
# ===========================================================================


class TestMultiplePaths:
    def test_one_benign_one_trigger_still_high_trust(self):
        result = classify_floor(["docs/README.md", "src/auth/token.py"])
        assert _is_high_trust(result)
        assert "auth-path" in _triggers(result)

    def test_two_different_triggers_both_recorded(self):
        result = classify_floor([
            "db/migrations/001_init.sql",
            "services/payment/charge.py",
        ])
        assert _is_high_trust(result)
        tids = _triggers(result)
        assert "migration-path" in tids
        assert "payment-path" in tids

    def test_triggers_deduped_across_paths(self):
        result = classify_floor([
            "src/auth/login.py",
            "src/auth/logout.py",
        ])
        tids = _triggers(result)
        assert tids.count("auth-path") == 1


# ===========================================================================
# Result shape
# ===========================================================================


class TestResultShape:
    def test_keys_present_high_trust(self):
        result = classify_floor(["src/auth/login.py"])
        assert set(result.keys()) == {"tier", "triggers_matched"}

    def test_keys_present_tiny(self):
        result = classify_floor(["docs/README.md"])
        assert set(result.keys()) == {"tier", "triggers_matched"}

    def test_tier_is_valid_enum_value_high_trust(self):
        result = classify_floor(["src/auth/login.py"])
        assert result["tier"] in {"tiny", "standard", "spec", "high-trust"}

    def test_tier_is_valid_enum_value_tiny(self):
        result = classify_floor(["docs/README.md"])
        assert result["tier"] in {"tiny", "standard", "spec", "high-trust"}

    def test_triggers_matched_is_list(self):
        result = classify_floor(["src/auth/login.py"])
        assert isinstance(result["triggers_matched"], list)

    def test_triggers_matched_empty_for_tiny(self):
        result = classify_floor(["docs/README.md"])
        assert result["triggers_matched"] == []


# ---------------------------------------------------------------------------
# The Governor command doc: the human-readable half of the same floor. Kept
# with the floor logic so every Governor concern lives in one file (C4).
# ---------------------------------------------------------------------------

def test_govern_command_documents_the_floor():
    text = (_REPO / "core" / "commands" / "govern.md").read_text(encoding="utf-8")
    assert "high-trust" in text
    assert "governor-decision.json" in text
    # The deterministic no-downgrade floor is the safety property that matters.
    assert "never lower" in text or "never silently" in text


# ---------------------------------------------------------------------------
# CLI gate: the CI-facing enforcement of the floor on a real PR diff (B3).
# ---------------------------------------------------------------------------

def test_cli_gate_blocks_high_trust_without_ack(capsys):
    rc = main(["--paths", "src/auth/login.py", "--gate"])
    assert rc == 1


def test_cli_gate_passes_high_trust_with_ack(capsys):
    rc = main(["--paths", "src/auth/login.py", "--gate", "--ack", "high-trust"])
    assert rc == 0


def test_cli_gate_ack_is_case_insensitive(capsys):
    rc = main(["--paths", "src/auth/login.py", "--gate", "--ack", "High-Trust"])
    assert rc == 0


def test_cli_gate_passes_tiny_diff(capsys):
    rc = main(["--paths", "docs/README.md", "--gate"])
    assert rc == 0


def test_cli_gate_fires_on_diff_text_keyword(capsys, tmp_path):
    diff = tmp_path / "pr.diff"
    diff.write_bytes(b"+ def process_payment(amount):\n+     charge(amount)\n")
    rc = main(["--paths", "docs/README.md", "--diff-file", str(diff), "--gate"])
    assert rc == 1


def test_cli_without_gate_never_fails(capsys):
    rc = main(["--paths", "src/auth/login.py"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Project config overlay through the CLI (C3): a domain can raise the floor.
# ---------------------------------------------------------------------------

def test_cli_config_clinical_floors_tiny_change_to_high_trust(tmp_path, capsys):
    cfg = tmp_path / "mergen.toml"
    cfg.write_text('domain = "clinical"\n', encoding="utf-8")
    # A tiny docs change matches no built-in trigger, but the clinical domain
    # overlay floors any change to high-trust, so the gate refuses it.
    rc = main(["--paths", "docs/readme.md", "--config", str(cfg), "--gate"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "high-trust" in out
    assert "domain:clinical" in out


def test_cli_config_clinical_passes_with_ack(tmp_path, capsys):
    cfg = tmp_path / "mergen.toml"
    cfg.write_text('domain = "clinical"\n', encoding="utf-8")
    rc = main(["--paths", "docs/readme.md", "--config", str(cfg),
               "--gate", "--ack", "high-trust"])
    assert rc == 0
