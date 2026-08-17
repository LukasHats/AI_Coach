# CLAUDE.md

Dev conventions for this repo. Merge with any directory-specific CLAUDE.md as needed.

## Environment

- Conda env is `ultra-coach` (see `environment.yml`). Activate it before running anything:
  `conda activate ultra-coach`.

## Data handling

- **Never commit health data or the database.** `data/` and `*.db` are gitignored — keep it that
  way. Garmin credentials live in `.env` (gitignored); `.env.example` documents the shape only.

## Config

- **FTP lives in `config.py` as a single constant** (`FTP`), along with `MAX_HR`, `THRESHOLD_HR`,
  and the hrTSS zone-factor table. Change it there, not in `metrics.py` or anywhere else — every
  TSS/IF calculation reads from it, so one edit recomputes everything.

## sync.py

- Must stay **incremental and idempotent**: upserts on `activity_id`, only fetches activities
  newer than what's already stored (`--backfill N` overrides for a full reload). Safe to run
  repeatedly — re-running over an already-synced range should not create duplicates or change
  existing rows beyond refreshing their values.

## activityType is unreliable

- Garmin's `activityType` field is manually entered and sometimes wrong (a gravel ride has been
  seen tagged `road_biking`). **Never infer power availability, or anything else, from the type
  label.** Use `has_power` (derived from whether `avg_power` is non-null) instead.


# Commong claude instructions

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 0. Acknowledge the context of the work: Bioinformatics
- We are working in the field of bioinofrmatics, more precisely single-cell spatial omics
- The data is inherently noisy, often coming from imaging data being processed with segmentation
- Think about appropriate statistical testing if necessary (multi-cohort designs, pseudoreplication, etc). If unsure, ask and discuss
- If unsure, try to get context from literature and platforms like bioconductor, scverse, biostars etc.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- If you do have improvements, please list them.
- No abstractions for single-use code.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Instead of automatically "improving" adjacent code, comments, or formatting, suggest the improvements and the reason.
- Don't refactor things that aren't broken. If you do find possible improvements, suggest them.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

After changes are performed, check the code again for appropriate structure and best practices in sodtware engineering. 

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
