# AI Coach 🧑‍🏫

A personal coaching pipeline: pulls your training data from Garmin Connect into a local database,
crunches it into real numbers, and lets Claude write you a weekly review — grounded in *your*
training plan and *your* coaching style, not a generic chatbot pep talk.

Built on [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) for the Garmin
side, and [Claude Code](https://claude.com/claude-code) as the coach. There's no fine-tuned model
involved — the "coach" is just a persona file and a plan file, both read fresh every time.

This particular setup happens to be configured for endurance cycling (power, TSS, the works), but
the pattern itself doesn't care what sport or goal you're chasing — swap in your own plan and
persona and it follows those instead. Bike, run, swim, something else entirely — up to you.

## How it fits together

```
Garmin Connect --sync.py--> data/garmin.db --metrics.py--> load, fitness/fatigue, trends...
                                                                      |
                                        coach/persona.md  +  your plan (e.g. plan/periodization.md)
                                                      \            /
                                                   /weekly-review (Claude Code)
                                                            |
                                                            v
                                                plan/reviews/YYYY-Www.md
```

- **`sync.py`** — incremental, idempotent pull from Garmin Connect into `data/garmin.db`. Safe to
  run again and again, it only grabs what's new since last time. `--backfill N` for the first big
  load.
- **`metrics.py`** — turns the raw sync into numbers worth looking at (in this instance: TSS, an
  hrTSS fallback for non-power rides, CTL/ATL/TSB, weekly aggregates, power curve, durability).
  No opinions, no coaching — just the math.
- **`.claude/commands/weekly-review.md`** — the actual coaching step. Running `/weekly-review` in
  Claude Code syncs, crunches the numbers, reads the context below, and writes you a review.

## Where your stuff goes

| File | What goes here |
|---|---|
| `.env` | Your Garmin login. Copy `.env.example`, fill it in. **Never commit this** — it's gitignored on purpose, keep it that way. 🔒 |
| `config.py` | Your numbers — FTP, HR thresholds, whatever your metrics depend on. One place, so one edit recomputes everything downstream. |
| `coach/persona.md` | Who your coach is and how it should think: your goals, what data to trust, what tone to take, what it should never pretend to know. This is the actual "brain" of the thing — change this before you touch any code. |
| `plan/periodization.md` | Your plan, whatever you're training for. Swap it out entirely if your goal changes — `/weekly-review` always reads whatever's currently there. |
| `CLAUDE.md` (repo root) | Conventions for anyone (human or Claude) touching the code itself. |
| `plan/reviews/` | Where the reviews land, `YYYY-Www.md` per week. Mostly hands-off — append athlete feedback when the command asks, don't rewrite it wholesale. |
| `data/garmin.db` | Your synced data, gitignored. Rebuild anytime with `sync.py --backfill 365`. |

## Setup

```
conda env create -f environment.yml
conda activate ultra-coach
cp .env.example .env   # fill in GARMIN_EMAIL / GARMIN_PASSWORD
python sync.py --backfill 365
python metrics.py
```

Then, from Claude Code in this repo: `/weekly-review` 🚀
