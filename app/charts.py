from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
from matplotlib.patches import Patch

from app.mailer import InlineImage
from app.stats import DailyStats
from app.streaks import DayStatus
from app.timeutils import minutes_after_18

BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
VERMILLION = "#D55E00"
SKY = "#56B4E9"
GRAY = "#6B665D"
LIGHT = "#E9E3D7"
DARK = "#25231F"

matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["font.size"] = 9
matplotlib.rcParams["axes.edgecolor"] = "#B9B0A1"
matplotlib.rcParams["axes.labelcolor"] = DARK
matplotlib.rcParams["xtick.color"] = DARK
matplotlib.rcParams["ytick.color"] = DARK


def _day_labels(days: tuple[DailyStats, ...]) -> list[str]:
    return [day.local_date.strftime("%a") for day in days]


def _style(ax: Any, *, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color="#DED7CA", linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)


def _save(fig: Figure, cid: str, filename: str, alt: str) -> InlineImage:
    buffer = BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=110,
        bbox_inches="tight",
        pad_inches=0.08,
        metadata={"Software": None},
    )
    fig.clear()
    return InlineImage(
        cid=cid,
        filename=filename,
        content=buffer.getvalue(),
        content_type="image/png",
        alt=alt,
    )


def completion_chart(days: tuple[DailyStats, ...]) -> InlineImage:
    fig = Figure(figsize=(6.4, 2.7))
    ax = fig.subplots()
    x = list(range(len(days)))
    heights: list[float] = []
    colors: list[str] = []
    hatches: list[str | None] = []
    notes: list[str] = []
    for day in days:
        if day.status is DayStatus.ACHIEVED:
            heights.append(day.completion_percent)
            colors.append(GREEN)
            hatches.append(None)
            notes.append(f"{day.completion_percent:.0f}%")
        elif day.status is DayStatus.PARTIAL:
            heights.append(day.completion_percent)
            colors.append(ORANGE)
            hatches.append(None)
            notes.append(f"{day.completion_percent:.0f}%")
        elif day.status is DayStatus.MISSED:
            heights.append(0)
            colors.append(VERMILLION)
            hatches.append(None)
            notes.append("0%")
        elif day.status is DayStatus.NO_GOALS:
            heights.append(6)
            colors.append(LIGHT)
            hatches.append("//")
            notes.append("NG")
        else:
            heights.append(6)
            colors.append(LIGHT)
            hatches.append("..")
            notes.append("-")
    bars = ax.bar(x, heights, color=colors, width=0.68)
    for bar, hatch in zip(bars, hatches, strict=True):
        if hatch:
            bar.set_hatch(hatch)
            bar.set_edgecolor(GRAY)
    for position, height, note in zip(x, heights, notes, strict=True):
        ax.text(
            position,
            height + 3,
            note,
            ha="center",
            va="bottom",
            fontsize=7,
            color=DARK,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(_day_labels(days))
    ax.set_ylim(0, 110)
    ax.set_ylabel("Completion %")
    _style(ax)
    handles = [
        Patch(color=GREEN, label="Achieved"),
        Patch(color=ORANGE, label="Partial"),
        Patch(color=VERMILLION, label="Missed"),
        Patch(facecolor=LIGHT, hatch="//", edgecolor=GRAY, label="No goals"),
        Patch(facecolor=LIGHT, hatch="..", edgecolor=GRAY, label="Not logged"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=7, ncol=5, loc="upper center")
    labels = ", ".join(
        f"{day.local_date.strftime('%a %d')}: {note}" for day, note in zip(days, notes, strict=True)
    )
    return _save(
        fig,
        "weekly-completion",
        "weekly-completion.png",
        f"Goal completion by day. {labels}.",
    )


def sleep_chart(days: tuple[DailyStats, ...]) -> InlineImage:
    fig = Figure(figsize=(6.4, 2.9))
    ax = fig.subplots()
    x = list(range(len(days)))
    bed = [
        minutes_after_18(day.bedtime_time) if day.bedtime_time is not None else None for day in days
    ]
    wake = [minutes_after_18(day.wake_time) if day.wake_time is not None else None for day in days]
    ax.plot(x, bed, marker="o", linewidth=1.6, color=BLUE, label="Bedtime")
    ax.plot(x, wake, marker="s", linewidth=1.6, color=ORANGE, label="Wake")
    ax.set_xticks(x)
    ax.set_xticklabels(_day_labels(days))
    ax.set_ylim(0, 1440)
    ax.set_yticks([0, 180, 360, 540, 720, 900, 1080, 1260, 1440])
    ax.set_yticklabels(
        ["18:00", "21:00", "00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00"]
    )
    ax.set_ylabel("Local time")
    _style(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    parts = []
    for day, bed_value, wake_value in zip(days, bed, wake, strict=True):
        if bed_value is None or wake_value is None:
            parts.append(f"{day.local_date.strftime('%a %d')}: not logged")
        else:
            parts.append(
                f"{day.local_date.strftime('%a %d')}: bed {day.bedtime_time.strftime('%H:%M')}, "
                f"wake {day.wake_time.strftime('%H:%M')}"
            )
    return _save(
        fig,
        "weekly-sleep",
        "weekly-sleep.png",
        "Bedtime and wake time on an anchored 18:00-to-18:00 axis. " + "; ".join(parts),
    )


def screen_chart(days: tuple[DailyStats, ...]) -> InlineImage:
    fig = Figure(figsize=(6.4, 2.5))
    ax = fig.subplots()
    x = list(range(len(days)))
    values = [day.screen_minutes if day.screen_minutes is not None else None for day in days]
    ax.plot(x, values, marker="o", linewidth=1.6, color=SKY)
    ax.set_xticks(x)
    ax.set_xticklabels(_day_labels(days))
    maximum = max((value for value in values if value is not None), default=300)
    ax.set_ylim(0, max(300, maximum * 1.15))
    ax.set_ylabel("Minutes")
    _style(ax)
    parts = [
        f"{day.local_date.strftime('%a %d')}: "
        f"{day.screen_minutes if day.screen_minutes is not None else 'not logged'}"
        for day in days
    ]
    return _save(
        fig,
        "weekly-screen",
        "weekly-screen.png",
        "Screen time in minutes by day. " + "; ".join(parts),
    )


def mood_chart(days: tuple[DailyStats, ...]) -> InlineImage:
    fig = Figure(figsize=(6.4, 2.5))
    ax = fig.subplots()
    x = list(range(len(days)))
    values = [day.mood if day.mood is not None else None for day in days]
    ax.plot(x, values, marker="o", linewidth=1.6, color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(_day_labels(days))
    ax.set_ylim(1, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_ylabel("Mood")
    _style(ax)
    parts = [
        f"{day.local_date.strftime('%a %d')}: {day.mood if day.mood is not None else 'not logged'}"
        for day in days
    ]
    return _save(
        fig,
        "weekly-mood",
        "weekly-mood.png",
        "Mood from 1 to 5 by day. " + "; ".join(parts),
    )


def weekly_charts(days: tuple[DailyStats, ...]) -> tuple[InlineImage, ...]:
    return (
        completion_chart(days),
        sleep_chart(days),
        screen_chart(days),
        mood_chart(days),
    )
