# Package scope and curation

The v1 release is preserved. This v2 package uses an explicit file allowlist rather than copying the application's source directories.

| Area | Included | Purpose |
|---|---|---|
| analysis/scripts | Numeric refit; Figures 1–6; public input preparation; coding merge audit | Executable offline reproduction |
| analysis/src + config/cases.yaml | Import dependencies used by the original numerical functions | Retain scientific implementation |
| experiment | Unmodified historical archive | Inspect experimental rules and settings |
| optional-coding-reference | Three initial coding sources, two later adjudication sources, and coding prompts | Inspect paid coding implementation; requires adaptation |
| Root metadata | License, third-party notice, dependency locks, manifest, verification | Version and scope checks |

Excluded from the current analysis tree: web/UI/API services, RAG and web search, generic consensus reports, manuscript assembly and prose checking, manuscript/SI authoring, old manual-validation package builders, private databases, raw full-corpus data, caches and credentials. The frozen archive intentionally retains historical source, including code not invoked by the offline analysis. No platform source was deleted from the main repository.

Verification covers the 15 E1–E5 model/contrast estimates and intervals, the plotted numerical records for six figures, and the released three-domain coding merge. Figures are rendered from archived estimates; that step does not refit all plotted models. The remaining registered/exploratory analyses are not all independently refitted by this quick start. Offline coding checks verify merging and counts, not label correctness or human validation. The complete Python lock was previously installed in a fresh environment; the v2 checks use that environment and the existing R installation, not a newly provisioned operating system.
