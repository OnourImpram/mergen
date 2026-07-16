# Publishing policy

The default branch is the public product surface. Product identity changes must update the README, package metadata, release notes, and repository settings in the same release sequence.

Pull requests that change verification authority, approval semantics, risk classification, package metadata, or release behavior are high trust. They require the complete continuous integration and security suite and an exact-diff human checkpoint.

The repository uses squash merges for release changes and deletes merged branches. The `main` branch is protected against force pushes and deletion.
