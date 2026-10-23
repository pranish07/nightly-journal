# Streaks and statuses

Purpose: Define how a day is classified and how current and longest goal/logging streaks are computed.

Last verified: 2026-10-23

## Day statuses

`DayStatus` is defined in `app/streaks.py`.

| Status | Meaning | Conditions |
| --- | --- | --- |
| `achieved` | The day met the completion threshold | Logged, not `no_goals`, at least one goal done, `goals_done / goals_total >= threshold` |
| `partial` | Some goals were done, but below the threshold | Logged, not `no_goals`, at least one goal done, ratio below threshold |
| `missed` | A goal day with zero completed goals | Logged, not `no_goals`, `goals_done == 0` |
| `no_goals` | A logged day that intentionally has no goals | Logged and `no_goals == true` |
| `not_logged` | No entry for the local date | No `entries` row |

Important details:

- `missed` takes precedence over a threshold of `0.0`. A day with zero done is missed even when the threshold is zero.
- A logged day must have goals or the no-goals toggle. `DayRecord` rejects a logged day with zero goals and `no_goals == false`.
- `no_goals` is neutral for goal streaks: it neither increments nor resets the streak.
- `no_goals` counts as a logged day for logging streaks.
- A missing date is `not_logged` and breaks both current streaks.
- `threshold` is `STREAK_MIN_COMPLETION`, default `1.0`, constrained to `0.0..1.0`.

## One-day grace

`compute_streaks(records, as_of=...)` uses a one-day grace so the current streak does not appear to break just because today's entry is not written yet.

- If `as_of` has a logged record, the current anchor is `as_of`.
- Otherwise, the current anchor is `as_of - 1 day`.
- If the anchor day is missed or not logged, the current streak is zero.
- The grace applies to both current goal and current logging streaks.

The grace does not create a record. It only changes where the backward scan starts.

## Current goal streak

Starting at the current anchor and walking backward to the earliest known record:

1. `no_goals` -> skip the day and continue.
2. `achieved` -> increment and continue.
3. Any other status -> stop.

The result is the number of achieved days, with `no_goals` days transparent.

## Current logging streak

Starting at the current anchor and walking backward:

1. A logged record (`achieved`, `partial`, `missed`, or `no_goals`) -> increment and continue.
2. A missing or unlogged record -> stop.

## Longest goal streak

Scan from the earliest known record through `as_of`:

- `achieved` -> increment the running count and update the maximum.
- `no_goals` -> leave the running count unchanged.
- Any other status -> reset the running count to zero.

## Longest logging streak

Scan from the earliest known record through `as_of`:

- A logged record -> increment the running count and update the maximum.
- A missing or unlogged record -> reset the running count to zero.

## Worked 14-day example

Dates are `2026-10-10` through `2026-10-23`. `as_of` is `2026-10-23`. Threshold is `1.0`. Today has no entry, so the one-day grace anchors the current streaks at `2026-10-22`.

| Date | Logged | No goals | Goals done/total | Status |
| --- | --- | --- | --- | --- |
| 2026-10-10 | yes | no | 3/3 | `achieved` |
| 2026-10-11 | yes | no | 2/2 | `achieved` |
| 2026-10-12 | yes | yes | 0/0 | `no_goals` |
| 2026-10-13 | yes | no | 1/1 | `achieved` |
| 2026-10-14 | yes | no | 1/2 | `partial` |
| 2026-10-15 | yes | no | 0/2 | `missed` |
| 2026-10-16 | no | no | 0/0 | `not_logged` |
| 2026-10-17 | yes | no | 2/2 | `achieved` |
| 2026-10-18 | yes | no | 1/1 | `achieved` |
| 2026-10-19 | yes | yes | 0/0 | `no_goals` |
| 2026-10-20 | yes | no | 3/3 | `achieved` |
| 2026-10-21 | yes | no | 2/2 | `achieved` |
| 2026-10-22 | yes | no | 1/1 | `achieved` |
| 2026-10-23 | no | no | 0/0 | `not_logged` |

Computed result:

```text
current_goal=5
longest_goal=5
current_logging=6
longest_logging=6
```

Why:

- Current goal: `10-22, 10-21, 10-20`, skip `10-19`, then `10-18, 10-17` = 5. `10-16` breaks the scan.
- Current logging: `10-22` through `10-17` inclusive = 6. `10-16` breaks the scan.
- Longest goal: the best run is `10-17, 10-18`, skip `10-19`, then `10-20, 10-21, 10-22` = 5.
- Longest logging: both `10-10..10-15` and `10-17..10-22` are six logged days.

This example was checked against `compute_streaks()` with the same records.

## Range statuses

`statuses_for_range(records, start, end, threshold)` returns one `(date, DayStatus)` pair per date in the inclusive range, filling gaps with `not_logged`. It is available for future calendar and dashboard work; the current app uses `daily_stats()` and `range_stats()` for the weekly report.

## Validation rules

`DayRecord` raises `ValueError` for:

- Negative `goals_total` or `goals_done`.
- `goals_done > goals_total`.
- An unlogged day carrying goals or `no_goals`.
- A `no_goals` day carrying goals.
- A logged day with zero goals and `no_goals == false`.
- Duplicate records for the same date in `compute_streaks()` or `statuses_for_range()`.
- A threshold outside `0.0..1.0`.
- A reversed range in `statuses_for_range()`.

## Related docs

- [Data model](./data-model.md)
- [Scheduling and idempotency](./scheduling.md)
- [Testing](./testing.md)
- [AI insights](./ai-insights.md)
