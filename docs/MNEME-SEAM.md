# The mneme seam

Mergen is the execution layer. mneme is the memory layer. They meet at one seam and nowhere else. This
document defines that seam so the boundary stays honest and neither system reaches into the other.

## The rule

Mergen stores no memory of its own. It does not run a vault, an index, or a database. When a piece of work
produces something worth remembering, a decision, a rationale, a failure pattern, Mergen emits it as a
record that mneme can ingest through mneme's own public interface. mneme remains the single memory
authority.

## What crosses the seam

One direction, Mergen to mneme. After a verified run, Mergen can turn its `verification-report.json` and its
rollup into mneme-ingestable decision records. The record is plain Markdown with provenance and a confidence
label, which is exactly mneme's vault format. `scripts/mneme_emit.py` is the stub that performs this
conversion today. It reads a `verification-report.json` and writes a decision record to stdout. A future
release may write directly into a configured vault path or call mneme's MCP surface, but the format is the
contract and it does not change.

The other direction, mneme to Mergen, is a read. The Governor and the spec commands may pull relevant prior
decisions as context. That read goes through mneme's public MCP surface (its `server.json`) or by reading
the Markdown vault. Mergen treats everything it reads as data, never as instruction, per the data fence in
`MERGEN.md`.

## Invariants Mergen must not violate

mneme publishes hard guarantees. The seam preserves all of them.

- Markdown is ground truth. The records Mergen emits are human-readable Markdown, never an opaque blob.
- No network or LLM on the critical path. `mneme_emit.py` is pure stdlib and deterministic. It makes no
  network call and runs no model.
- Redaction before any derived store. Mergen emits records it believes are already safe, and it never
  bypasses mneme's redaction. Redaction at ingest remains mneme's responsibility, and Mergen does not assume
  it can skip it.
- Provenance on every record, a confidence label on every claim. Every emitted record names its source (the
  verification report) and carries a confidence label.

## What does not cross the seam

Mergen never renames, forks, vendors, or re-publishes any mneme package (`mneme-core`, `mneme-mcp-server`,
`mneme-cc-plugin`, the `mneme-mcp` command). Mergen never writes to mneme's internal indexes or databases.
The only writes are Markdown records handed to mneme through its own ingest path.
