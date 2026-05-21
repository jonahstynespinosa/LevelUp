"""
Score Engine — the brain of LevelUp.

Takes a user's recent log history and produces:
- A score from 0–100
- A workout recommendation (push / moderate / rest)
- A coding minimum (hours)
- A plain-English summary explaining the call

Design principle: start rule-based, keep it explainable.
Each component score is computed independently and weighted.
This makes it easy to tune weights and explain to the user
exactly why they got their score.
"""
from dataclasses import dataclass, field
from datetime import date

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# These are plain Python dataclasses — not database models.
# The engine doesn't touch the database directly; the service layer
# fetches the data, passes it in here, and stores the result.
# ---------------------------------------------------------------------------

@dataclass
class DaySnapshot:
    """
    A single day's worth of logged data, normalized for the engine.
    All fields are Optional because users may not log everything every day.
    """
    log_date: date
    sleep_hours: float | None = None
    soreness: int | None = None       # 1 (very sore) to 5 (fresh)
    energy: int | None = None         # 1 (drained) to 5 (great)
    diet_quality: int | None = None   # 1 (poor) to 5 (excellent)
    workout_done: bool = False
    workout_duration_minutes: int | None = None
    is_rest_day: bool = False
    coding_hours: float | None = None
    focus_rating: int | None = None   # 1–5
    tasks_completed: int | None = None
    proof_submitted: bool = False


@dataclass
class ScoreBreakdown:
    """The full output of the engine for one day."""
    score: float                          # 0–100
    sleep_score: float                    # 0–100 component
    recovery_score: float                 # 0–100 component
    workout_consistency_score: float      # 0–100 component
    diet_score: float                     # 0–100 component
    coding_consistency_score: float       # 0–100 component
    workout_rec: str                      # "push" | "moderate" | "rest"
    coding_rec_hours: float               # minimum hours recommended
    summary: str                          # plain-English explanation
    flag_messages: list[str] = field(default_factory=list)  # warnings e.g. "Only 4h sleep"


# ---------------------------------------------------------------------------
# User settings with defaults
# ---------------------------------------------------------------------------

@dataclass
class UserSettings:
    gym_days_per_week: int = 5
    max_gym_duration_minutes: int = 60
    coding_hours_push: float = 3.0
    coding_hours_moderate: float = 2.0
    coding_hours_rest: float = 1.0
    require_proof: bool = True


# ---------------------------------------------------------------------------
# Component scorers
# Each function takes recent history and returns a 0–100 float.
# ---------------------------------------------------------------------------

def _score_sleep(snapshots: list[DaySnapshot]) -> tuple[float, list[str]]:
    """
    Optimal sleep: 7–9 hours. We score last night (most recent day)
    heavily, then factor in the 7-day average for trend.
    """
    flags = []
    sleep_values = [s.sleep_hours for s in snapshots if s.sleep_hours is not None]

    if not sleep_values:
        return 50.0, ["No sleep data logged — defaulting to neutral"]

    avg_sleep = np.mean(sleep_values)
    last_night = sleep_values[-1]

    def sleep_to_score(hours: float) -> float:
        if hours < 5:
            return 10.0
        elif hours < 6:
            return 40.0
        elif hours < 7:
            return 70.0
        elif hours <= 9:
            return 100.0
        else:  # oversleeping can signal illness/fatigue
            return 80.0

    # Weight last night at 60%, rolling average at 40%
    score = sleep_to_score(last_night) * 0.6 + sleep_to_score(avg_sleep) * 0.4

    if last_night < 6:
        flags.append(f"Only {last_night:.1f}h sleep last night — recovery is limited")
    elif last_night < 7:
        flags.append(f"{last_night:.1f}h sleep — slightly under optimal")

    return round(score, 1), flags


def _score_recovery(snapshots: list[DaySnapshot]) -> tuple[float, list[str]]:
    """
    Recovery = soreness + energy combined.
    High soreness + low energy = body needs rest.
    Low soreness + high energy = ready to push.
    """
    flags = []
    recent = [s for s in snapshots if s.soreness is not None and s.energy is not None]

    if not recent:
        return 50.0, ["No soreness/energy data — defaulting to neutral"]

    # Use the most recent entry as primary signal
    latest = recent[-1]

    # Soreness: higher soreness = lower score (inverted)
    soreness_score = (6 - latest.soreness) / 5 * 100  # soreness 5 → score 20, soreness 1 → score 100

    # Energy: higher energy = higher score (direct)
    energy_score = (latest.energy / 5) * 100

    # Weight them equally
    score = (soreness_score + energy_score) / 2

    if latest.soreness >= 4:
        flags.append("High soreness reported — consider lighter training")
    if latest.energy <= 2:
        flags.append("Low energy reported — this affects your recommendation")

    return round(score, 1), flags


def _score_workout_consistency(
    snapshots: list[DaySnapshot],
    settings: UserSettings
) -> tuple[float, list[str]]:
    """
    Did you hit your gym target over the last 7 days?
    We ignore rest days when counting — a planned rest day isn't a miss.
    """
    flags = []
    target = settings.gym_days_per_week

    # Count days where a workout was logged (excluding planned rest days)
    workout_days = sum(
        1 for s in snapshots
        if s.workout_done and not s.is_rest_day
    )

    # Scale: hitting target = 100, zero workouts = 0
    ratio = min(workout_days / target, 1.0) if target > 0 else 1.0
    score = ratio * 100

    # Check for sessions that went over the duration limit
    over_limit = [
        s for s in snapshots
        if s.workout_duration_minutes and s.workout_duration_minutes > settings.max_gym_duration_minutes
    ]
    if over_limit:
        flags.append(
            f"{len(over_limit)} session(s) exceeded your {settings.max_gym_duration_minutes}min limit"
        )

    if workout_days < target:
        flags.append(f"{workout_days}/{target} gym days this week")

    return round(score, 1), flags


def _score_diet(snapshots: list[DaySnapshot]) -> tuple[float, list[str]]:
    """
    Simple average of diet quality ratings over the window.
    Diet 5 every day = 100. Diet 1 every day = 20.
    """
    flags = []
    diet_values = [s.diet_quality for s in snapshots if s.diet_quality is not None]

    if not diet_values:
        return 50.0, ["No diet data logged — defaulting to neutral"]

    avg = np.mean(diet_values)
    score = (avg / 5) * 100

    if avg < 2.5:
        flags.append("Diet quality has been low this week — this affects recovery")

    return round(score, 1), flags


def _score_coding_consistency(snapshots: list[DaySnapshot]) -> tuple[float, list[str]]:
    """
    Did you actually show up and code? We reward:
    - Hours logged
    - Proof submitted (if required)
    - Focus rating
    - Consistency (logging most days) over cramming
    """
    flags = []
    coding_days = [s for s in snapshots if s.coding_hours is not None and s.coding_hours > 0]

    if not coding_days:
        return 0.0, ["No coding logged this week"]

    # Consistency: how many of the last 7 days had coding
    consistency_ratio = len(coding_days) / len(snapshots)

    # Average hours on days you coded (capped at 6h — diminishing returns)
    avg_hours = np.mean([min(s.coding_hours, 6.0) for s in coding_days])
    hours_score = (avg_hours / 6.0) * 100

    # Average focus on coding days
    focus_values = [s.focus_rating for s in coding_days if s.focus_rating is not None]
    focus_score = (np.mean(focus_values) / 5 * 100) if focus_values else 50.0

    # Proof bonus: if proof was submitted more than half the time, small boost
    proof_ratio = sum(1 for s in coding_days if s.proof_submitted) / len(coding_days)
    proof_bonus = 10.0 if proof_ratio >= 0.5 else 0.0

    score = (
        consistency_ratio * 40   # showing up matters most
        + hours_score * 0.35     # then volume
        + focus_score * 0.25     # then quality
        + proof_bonus            # proof of work bonus
    )
    score = min(score, 100.0)

    if consistency_ratio < 0.5:
        flags.append("Coding less than 4 days this week — consistency is the key habit")

    return round(score, 1), flags


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

# Component weights — must sum to 1.0
WEIGHTS = {
    "sleep": 0.25,
    "recovery": 0.25,
    "workout_consistency": 0.20,
    "diet": 0.15,
    "coding_consistency": 0.15,
}


def compute_score(
    snapshots: list[DaySnapshot],
    settings: UserSettings | None = None,
) -> ScoreBreakdown:
    """
    Main entry point. Call this with the last 7 days of snapshots
    (most recent last) and get back a full ScoreBreakdown.

    Args:
        snapshots: Up to 7 DaySnapshot objects, ordered oldest → newest.
                   Fewer than 7 is fine — the engine handles partial history.
        settings:  User's configurable settings. Defaults used if None.

    Returns:
        ScoreBreakdown with score, components, recommendations, and summary.
    """
    if settings is None:
        settings = UserSettings()

    all_flags: list[str] = []

    sleep_score, sleep_flags = _score_sleep(snapshots)
    recovery_score, recovery_flags = _score_recovery(snapshots)
    workout_score, workout_flags = _score_workout_consistency(snapshots, settings)
    diet_score, diet_flags = _score_diet(snapshots)
    coding_score, coding_flags = _score_coding_consistency(snapshots)

    all_flags.extend(sleep_flags + recovery_flags + workout_flags + diet_flags + coding_flags)

    # Weighted final score
    final_score = (
        sleep_score * WEIGHTS["sleep"]
        + recovery_score * WEIGHTS["recovery"]
        + workout_score * WEIGHTS["workout_consistency"]
        + diet_score * WEIGHTS["diet"]
        + coding_score * WEIGHTS["coding_consistency"]
    )
    final_score = round(min(max(final_score, 0.0), 100.0), 1)

    # Recommendations based on score band
    if final_score >= 75:
        workout_rec = "push"
        coding_rec_hours = settings.coding_hours_push
        rec_label = "Push day"
    elif final_score >= 50:
        workout_rec = "moderate"
        coding_rec_hours = settings.coding_hours_moderate
        rec_label = "Moderate day"
    else:
        workout_rec = "rest"
        coding_rec_hours = settings.coding_hours_rest
        rec_label = "Rest day"

    # Build the summary
    summary = _build_summary(
        rec_label=rec_label,
        final_score=final_score,
        workout_rec=workout_rec,
        coding_rec_hours=coding_rec_hours,
        flags=all_flags,
        component_scores={
            "sleep": sleep_score,
            "recovery": recovery_score,
            "workout": workout_score,
            "diet": diet_score,
            "coding": coding_score,
        }
    )

    return ScoreBreakdown(
        score=final_score,
        sleep_score=sleep_score,
        recovery_score=recovery_score,
        workout_consistency_score=workout_score,
        diet_score=diet_score,
        coding_consistency_score=coding_score,
        workout_rec=workout_rec,
        coding_rec_hours=coding_rec_hours,
        summary=summary,
        flag_messages=all_flags,
    )


def _build_summary(
    rec_label: str,
    final_score: float,
    workout_rec: str,
    coding_rec_hours: float,
    flags: list[str],
    component_scores: dict[str, float],
) -> str:
    """Build a plain-English summary the user actually wants to read."""

    workout_detail = {
        "push": "Train hard today — your body is recovered and ready.",
        "moderate": "Keep it moderate — solid effort but don't max out.",
        "rest": "Take it easy today. Active recovery or full rest.",
    }[workout_rec]

    coding_detail = f"Aim for at least {coding_rec_hours:.0f} hour{'s' if coding_rec_hours != 1 else ''} of focused coding today."

    # Find the weakest component to call out
    weakest = min(component_scores, key=component_scores.get)
    weak_score = component_scores[weakest]
    weak_note = ""
    if weak_score < 50:
        weak_note = f" Your {weakest.replace('_', ' ')} score ({weak_score:.0f}/100) is your main limiter right now."

    flag_text = ""
    if flags:
        flag_text = " Note: " + " | ".join(flags[:2])  # show top 2 flags max

    return (
        f"{rec_label} — Score: {final_score}/100. "
        f"{workout_detail} "
        f"{coding_detail}"
        f"{weak_note}"
        f"{flag_text}"
    )