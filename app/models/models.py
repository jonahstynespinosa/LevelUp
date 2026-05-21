from datetime import date, datetime
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # User-configurable settings stored as JSON.
    # This avoids adding a new column every time we add a setting.
    # Example value:
    # {
    #   "gym_days_per_week": 5,
    #   "max_gym_duration_minutes": 60,
    #   "coding_hours_push": 3,
    #   "coding_hours_moderate": 2,
    #   "coding_hours_rest": 1,
    #   "require_proof": true
    # }
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships — SQLAlchemy uses these to let you do user.daily_logs
    # without writing a JOIN manually
    daily_logs: Mapped[list["DailyLog"]] = relationship(back_populates="user")
    scores: Mapped[list["DailyScore"]] = relationship(back_populates="user")


class DailyLog(Base):
    """
    One row per day per user. This is the master log entry.
    Workout and coding logs hang off this via foreign key.
    We separate them so the schema stays clean and each can
    be updated independently.
    """
    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Sleep
    sleep_hours: Mapped[float | None] = mapped_column(Float)

    # Physical feel — both rated 1 (very bad) to 5 (excellent)
    soreness: Mapped[int | None] = mapped_column(Integer)   # 1=very sore, 5=fresh
    energy: Mapped[int | None] = mapped_column(Integer)     # 1=drained, 5=great

    # Diet — simple 1-5 quality rating to start.
    # Could expand to meal logging later without breaking this schema.
    diet_quality: Mapped[int | None] = mapped_column(Integer)  # 1=poor, 5=excellent

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="daily_logs")
    workout_log: Mapped["WorkoutLog | None"] = relationship(
        back_populates="daily_log", uselist=False  # one-to-one
    )
    coding_log: Mapped["CodingLog | None"] = relationship(
        back_populates="daily_log", uselist=False  # one-to-one
    )
    score: Mapped["DailyScore | None"] = relationship(
        back_populates="daily_log", uselist=False
    )


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_log_id: Mapped[int] = mapped_column(
        ForeignKey("daily_logs.id"), unique=True, nullable=False
    )

    workout_type: Mapped[str] = mapped_column(String(100))  # e.g. "chest", "legs", "cardio"
    duration_minutes: Mapped[int] = mapped_column(Integer)
    intensity: Mapped[int] = mapped_column(Integer)  # 1-5, self-reported

    # Rest day flag — user explicitly marks this as a planned rest day.
    # Important: rest days shouldn't count against the 5-day gym target.
    is_rest_day: Mapped[bool] = mapped_column(Boolean, default=False)

    daily_log: Mapped["DailyLog"] = relationship(back_populates="workout_log")


class CodingLog(Base):
    __tablename__ = "coding_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_log_id: Mapped[int] = mapped_column(
        ForeignKey("daily_logs.id"), unique=True, nullable=False
    )

    hours: Mapped[float] = mapped_column(Float)
    focus_rating: Mapped[int] = mapped_column(Integer)   # 1-5
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    what_i_worked_on: Mapped[str | None] = mapped_column(Text)

    # Proof of work — either a GitHub URL or a screenshot URL (stored in S3/Cloudinary)
    proof_url: Mapped[str | None] = mapped_column(String(500))
    proof_type: Mapped[str | None] = mapped_column(String(20))  # "github" | "screenshot"
    proof_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    daily_log: Mapped["DailyLog"] = relationship(back_populates="coding_log")


class DailyScore(Base):
    """
    Computed once per day and stored. We store it rather than
    recomputing on every request because:
    1. The score depends on 7 days of history — expensive to recalculate
    2. The recommendation shouldn't change mid-day
    3. Gives us a clean history of how scores evolved over time
    """
    __tablename__ = "daily_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    daily_log_id: Mapped[int] = mapped_column(
        ForeignKey("daily_logs.id"), unique=True, nullable=False
    )
    score_date: Mapped[date] = mapped_column(Date, nullable=False)

    # The final score 0-100
    score: Mapped[float] = mapped_column(Float, nullable=False)

    # Component scores stored for transparency — user can see why they got their score
    sleep_score: Mapped[float | None] = mapped_column(Float)
    recovery_score: Mapped[float | None] = mapped_column(Float)
    workout_consistency_score: Mapped[float | None] = mapped_column(Float)
    diet_score: Mapped[float | None] = mapped_column(Float)
    coding_consistency_score: Mapped[float | None] = mapped_column(Float)

    # The two recommendations
    workout_rec: Mapped[str] = mapped_column(String(20))   # "push" | "moderate" | "rest"
    coding_rec_hours: Mapped[float] = mapped_column(Float)  # minimum hours today

    # Human-readable explanation shown in the app
    summary: Mapped[str] = mapped_column(Text)

    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="scores")
    daily_log: Mapped["DailyLog"] = relationship(back_populates="score")