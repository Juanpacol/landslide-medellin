# Spec-Driven Development at TEYVA

Every non-trivial change to the neuro-symbolic system starts as a spec under `specs/NNN-name/`,
three files:

- **`spec.md`** — WHAT and WHY. Problem statement, acceptance criteria. No implementation detail.
- **`plan.md`** — HOW. Architecture, files touched, sequencing, interfaces.
- **`tasks.md`** — Ordered, independently-verifiable checklist. Each task is small enough to review
  in one sitting and ends with a test.

Rules:

1. `spec.md` must be written and reviewed before `plan.md`. `plan.md` before any code.
2. Hard cap: 150 lines per file. If it doesn't fit, split the spec.
3. A spec that locks in a non-obvious, hard-to-reverse decision gets an ADR in `docs/adr/`
   (one page: context, decision, consequences). The spec links to it; the ADR is not duplicated.
4. Status lives in `specs/README.md`, not in the spec files themselves.
5. Language: English. See `CLAUDE.md` for the code/docs-English vs user-facing-Spanish rule.

Use `docs/SPEC_TEMPLATE.md` to start a new spec.
