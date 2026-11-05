# Mergen Hermes demonstration

## Reproducible evidence

From the repository root, with pytest installed in the current Python environment:

```sh
python eval/hermes_demo.py --out /tmp/mergen-hermes-demo-evidence
```

The script creates a temporary Git repository and invokes the adapter's registered tool through an explicit test host, which runs the real Mergen CLI. It is an adapter-to-CLI integration demonstration, not a live LLM conversation. It writes three synthetic verification reports and a summary outside the temporary fixture.

The expected sequence is:

1. `missing_file`: a task claims a greeting function is done, but its file is absent. Verdict `fail`, exit 1.
2. `failing_test`: the external executor adds an incorrect function. The file is tracked but the declared test fails. Verdict `fail`, exit 1.
3. `repaired`: the external executor corrects the greeting function and commits it. The declared test and file/Git checks pass. Verdict `pass`, exit 0.

This illustrates three planted cases, not performance on arbitrary engineering tasks. Mergen verifies the claims. The external executor changes the implementation between runs.

## Live Hermes recording outline, under 90 seconds

Record an actual Hermes session with the plugin installed and the terminal environment prepared. Do not label the synthetic harness as a live Hermes conversation.

- 0 to 10 seconds: show the task declaration and the claim that the greeting function is done.
- 10 to 30 seconds: ask Hermes to use `mergen_verify`. Show the missing-file evidence and `fail`.
- 30 to 50 seconds: add the incorrect implementation, then show the failing-test result.
- 50 to 75 seconds: fix it as the executor, then rerun verification and show the supported `pass`.
- 75 to 85 seconds: show the repo and state the boundary: evidence checks, not a guarantee of universal correctness or automatic agent enforcement.

Keep any API keys, personal paths, account tokens, and unrelated work out of the recording. Approvals must remain enabled. Do not hide a denied or unfinished operation behind an edited successful result.

## Submission prerequisites

- Public exact-SHA plugin code and a matching catalog entry PR.
- Passing Hermes catalog validation at that SHA.
- A genuine recorded demo within the competition's duration limit and the required public X post.
- The applicant's actual Discord username and any other required form fields.
- Final form submission confirmation.

The source PR, synthetic demo, or successful validator alone is not a completed application.
