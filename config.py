"""Single source of truth for athlete thresholds. Change here; metrics.py recomputes everywhere."""

FTP = 280  # W — trained value, confirmed over months of structured Zwift work calibrated against it.
# NOT derived from the 365-day best-20-min mean-maximal power (278 W, 2026-07-19): that ride was
# submaximal, on an unrecovered day. The standard 95%-of-20-min estimator applied to it gives
# 0.95 * 278 = 264 W (not 280) -- a floor implied by a submaximal effort, not the trained FTP.

MAX_HR = 197  # bpm
THRESHOLD_HR = 179  # bpm (LTHR)

# hrTSS zone-factor table: Friel/Coggan-style 5 zones as %LTHR, representative IF = zone midpoint.
# Boundaries in bpm at THRESHOLD_HR=179: Z1 <122, Z2 123-149, Z3 150-168, Z4 170-188, Z5 >190.
# Applied ORDINALLY to Garmin's own hr_time_in_zone_1..5 buckets, i.e. assuming Garmin zone N
# behaves like Friel zone N (recovery -> VO2max), NOT that the bpm cutoffs match exactly: Garmin's
# own zone configuration is known to be miscalibrated (confirmed -- zone 2 should top out around
# 148 bpm, which is exactly the 83%*LTHR boundary above, so the %LTHR model is the better reference
# point, but the seconds already binned by Garmin's real boundaries can't be rebinned after the
# fact without the raw HR stream). hrTSS is therefore an approximation -- see HR_SHARE_FLAG_THRESHOLD.
HR_ZONE_IF = {
    1: 0.60,
    2: 0.76,
    3: 0.89,
    4: 1.00,
    5: 1.12,
}

# Weekly HR-derived load share above this fraction gets flagged as not directly comparable
# to power-based weeks.
HR_SHARE_FLAG_THRESHOLD = 0.30
