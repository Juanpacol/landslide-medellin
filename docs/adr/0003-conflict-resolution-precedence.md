# ADR-0003 — Conflict resolution precedence: Veto > rule floor > neural level

## Context

Once `domain/rules` can fire alongside the neural hazard score, something has to decide what
happens when they disagree — a low neural score on a steep, saturated slope, or a confident
neural score with zero underlying data coverage.

## Decision

Precedence, high to low:

1. **`Veto`** — the score cannot be trusted regardless of what any other rule or the neural
   layer says. Confidence is floored to 0 and the reason is surfaced. Currently only
   `R-QUAL-01` (zero trigger coverage) uses this.
2. **Rule floor (`SetFloor`)** — a fired rule can raise the level, never lower it below the
   neural level. If the neural level is already at or above the floor, the floor is a no-op.
3. **`Escalate`** — raises the level by N categories from wherever it currently stands (after
   any floor has been applied), in priority order.
4. **Neural level** — the default when nothing above overrides it.

Ties within the same precedence tier break by rule priority, then rule id (both deterministic,
see `domain/rules/engine.py::evaluate`'s sort).

Every override is recorded in `Verdict.conflicts` with both the neural and rule-driven values —
this record is the evidence, for the eventual paper, that the two layers genuinely interact
rather than running as two independent stages (the boundary `domain/risk_rules.py` explicitly
described before this ADR: "the model never learns from these rules; the rules never predict").

## Consequences

- The neural score can never silently suppress a geotechnical red flag — a rule floor always
  wins over a lower neural reading.
- The neural score CAN exceed a rule floor (a rule only guarantees a minimum, not a maximum),
  so a genuinely severe neural signal is never capped by a conservative rule.
- `Veto` sitting above everything means a confidently wrong neural score on missing data cannot
  present as trustworthy — the direct fix for the audit's "zero trigger reads as zero risk" gap.
- Trade-off: this precedence is declared, not learned or optimized — consistent with the rest of
  the project's "no real labels exist to fit anything against" position
  (`docs/research/audit-2026-07.md` §8).
