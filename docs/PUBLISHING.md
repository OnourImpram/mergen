# Publishing policy

The default branch is the public product surface. Product identity changes must update the README, package metadata, release notes, and relevant repository documentation in the same release sequence.

Pull requests that change verification authority, approval semantics, risk classification, package metadata, or release behavior are high trust. They require the complete continuous integration and security suite and an exact-diff human checkpoint.

## Recommended GitHub administration

Repository administrators should configure the following controls in GitHub settings.

1. Protect `main` against force pushes and deletion.
2. Require pull requests for changes to `main`.
3. Require the complete CI and security check set before merge.
4. Require at least one approving review for high-trust changes.
5. Dismiss stale reviews after new commits.
6. Require conversation resolution.
7. Prefer squash merges for release changes.
8. Delete merged feature branches.

These controls are GitHub repository settings. They are not established merely by committing this document, and Mergen must not claim enforcement until an administrator has enabled them.
