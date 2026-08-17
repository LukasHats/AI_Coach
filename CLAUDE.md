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
