# CHANGELOG and DECISIONS.md Format Templates

## CHANGELOG.md format

```markdown
## [date] — [brief description]

### Added
### Fixed
### Changed
### Removed
```

Rules:
- Never leave CHANGELOG.md empty after a working session.
- Reference file name and function name — not just "fixed a bug."
- If you fix a bug, write one sentence on the root cause.

## DECISIONS.md format

```markdown
## [date] — [decision title]

**Context**: Why was this decision needed?
**Decision**: What was chosen?
**Alternatives**: What else was evaluated?
**Consequences**: What does this constrain or enable?
```
