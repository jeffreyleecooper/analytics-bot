# Documentation

A central repository for technical and business-context documentation that supports work across our projects. The goal is to keep durable, hand-curated knowledge — schema conventions, metric definitions, business rules, system overviews — in one place that both humans and AI coding agents can rely on.

## What lives here

Reference material that isn't obvious from reading source code or schemas alone:

- Business definitions and metric formulas
- Field-level documentation for important tables
- Conventions and ordering rules (e.g. canonical category sequences)
- System overviews and integration notes
- Anything else an engineer or analyst would otherwise have to ask a teammate about

If a fact can be derived directly from code or a schema, it generally doesn't belong here. If it requires institutional knowledge, it does.

## Folder layout

Documentation is organized by project area. Each top-level folder groups docs that share a domain:

- [bigquery/](bigquery/) — BigQuery table references, field definitions, and analysis conventions

Add new folders as new domains come up (e.g. `salesforce/`, `infra/`, `pricing/`). Keep folder names short and lowercase.

## AGENTS.md and CLAUDE.md

Both files exist so AI coding assistants have a single, reliable entry point into this repo:

- **[AGENTS.md](AGENTS.md)** is the canonical index. It lists every documentation file in the repo with a short description and a "use when" hint so an agent (or a human) can quickly figure out which doc is relevant to a task. **This is the file to update whenever you add, rename, or remove a document.**
- **[CLAUDE.md](CLAUDE.md)** exists only because Claude Code looks for it by name. It just points at AGENTS.md so we don't have to maintain the index in two places.

The convention: maintain document references in `AGENTS.md`. Leave `CLAUDE.md` as a one-line pointer.

## Adding a new document

1. Drop the file into the appropriate project-area folder (create the folder if one doesn't exist yet).
2. Add an entry for it in [AGENTS.md](AGENTS.md) under the matching section, including a one-paragraph description and a "Use when" line describing the situations where the doc is relevant.
3. Commit and push.
