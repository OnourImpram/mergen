<!-- Mergen pull request. Keep the description evidence-bearing and honest. Delete sections that do not apply. -->

## Problem and boundary

<!-- What verification or developer experience problem does this solve. State what remains owned by the external executor. -->

## Change

<!-- Describe the smallest implemented change. Do not describe roadmap work as shipped. -->

## Evidence

<!-- List the commands, fixtures, reports, and outputs that support the change. -->

- [ ] `python -m pytest tests/ -v`
- [ ] `ruff check .`
- [ ] `mypy`
- [ ] `python scripts/check_sync.py`
- [ ] `python scripts/check_no_reference_text.py`
- [ ] `python scripts/spec_verify.py --gate`
- [ ] `python scripts/validate_version.py`
- [ ] `python eval/benchmark.py --gate`
- [ ] Documentation and schemas updated where behavior changed
- [ ] A valid control passes and planted invalid cases fail

## Security and trust boundary

<!-- Identify untrusted inputs, path or command boundaries, human review requirements, and false pass or false failure risk. -->

## Governor acknowledgement

<!-- The PR diff gate raises protected changes to high-trust. Add the next line only after a human has reviewed the exact diff. -->

<!-- Governor-Ack: high-trust -->

## Compatibility and migration

<!-- State whether schemas, commands, outputs, adapters, or existing users are affected. Name any deprecation period. -->

## Honest limitations

<!-- State what this change does not prove, verify, or enforce. -->
