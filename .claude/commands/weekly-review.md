---
description: Sync latest Garmin data, compute metrics, and write a weekly training review against the periodized plan.
---

Generate this week's training review. Follow these steps in order.

## 1. Get fresh data

Run, from the repo root:

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate ultra-coach && python sync.py
```

Then run:

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate ultra-coach && python metrics.py
```

Capture its full output: calibration report, the trailing-12-weeks table, current CTL/ATL/TSB,
and the durability series. This is the numeric basis for everything below — don't recompute any
of it by hand or from raw SQL, `metrics.py` is the source of truth.

## 2. Read context

Read, in full:

- `coach/persona.md` — how to reason, what to trust, what to flag, the required output shape.
- `plan/periodization.md` — the current plan.
- The two most recently dated files in `plan/reviews/` (by filename, `YYYY-Www.md`), if any exist.
  If fewer than two exist, read whatever is there. If none exist, note this is the first review.

## 3. Identify the completed week and its plan target

The completed week is the most recent full Monday–Sunday week that has already ended (if today is
mid-week, that's last week; the trailing-12-weeks table from `metrics.py` has its row).

Map that week onto the plan:

- Find the Monday date of the completed week.
- In `plan/periodization.md` section 3 ("Week-by-week schedule"), find the row across all block
  tables whose **Mon start** matches that date.
- That row's block heading, Hours, TSS, and Type (`load` / **deload**) are this week's target.
- If no row matches (the week falls outside the plan's 39-week span, or the plan has since
  changed), say so explicitly rather than guessing at a target.

Compare actual (from the `metrics.py` weekly row: total TSS, hours, ride counts, HR-derived share)
against that target. Note explicitly whether the completed week was supposed to be a load or
deload week, and whether the actual data is consistent with that.

**Also pull per-activity data for every ride in the completed week** (date, duration, avg_hr,
TSS/hrTSS, HR-zone coverage where relevant) — not just the week's aggregate row. A weekly total or
a min/max avg-HR range across days can flatten away real structure: e.g. two rides carrying most of
the week's Z4 time and 5-10x the hrTSS of the others read as "quality days embedded in an easy
week" once you look per-activity, but as an undifferentiated blob of "mostly Z1/Z2" if you only
look at the weekly row. Look for rides that stand out from the rest of the week before writing
"What was done" — don't summarize from the aggregate alone.

## 4. Write the review

Follow `coach/persona.md` throughout — its tone, its "Data you can/cannot trust" boundaries, its
"Known gaps between plan and data" section, and its required Output structure (what was done, how
it compares to the plan's *intent*, anything notable or off, what next week should contain, open
questions for him). Apply its honesty rules: don't manufacture signal from a handful of rides,
don't reassure him about recovery with no recovery data, say directly if load looks too high or
too low.

Where relevant, reference the durability series (NP final-third vs first-third on rides >2h) and
the current CTL/ATL/TSB — but only make claims the data actually supports, flagging HR-heavy weeks
per persona.md rather than comparing them directly to power-based weeks.

Write the result to `plan/reviews/YYYY-Www.md`, where `YYYY-Www` is the ISO week number of the
**completed week being reviewed** (e.g. a review of the week starting Mon 10 Aug 2026 is
`2026-W33`). If a review for that week already exists, overwrite it.

## 5. Print it

Print the full contents of the file you just wrote.

## 6. Flag that open questions need a written answer to persist

After printing, explicitly tell him: any answers he gives to the "Open questions" section in this
conversation **will not persist** unless they're written back into `plan/reviews/YYYY-Www.md` —
the next `/weekly-review` run only reads the two most recent files in `plan/reviews/`, not this
conversation. Offer to append his answers to that file, under a new **"Athlete feedback"** section
(append, don't overwrite the rest of the file), once he responds. Don't write that section
speculatively — only once he's actually answered.
