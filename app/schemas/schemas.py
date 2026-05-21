from pydantic import BaseModel, ConfigDict

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # This tells Pydantic to read from SQLAlchemy models
    id: int
    username: str
    email: str
    is_active: bool

class WorkoutLogCreate(BaseModel):
    workout_type: str
    duration_minutes: int
    intensity: int
    is_rest_day: bool

class WorkoutLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    log_date: str
    workout_type: str
    duration_minutes: float
    intensity: int
    is_rest_day: bool

class CodingLogCreate(BaseModel):
    log_date: str  # ISO date string
    hours: float | None = None
    focus_rating: float | None = None
    tasks_completed: int | None = None
    what_i_worked_on: str | None = None
    proof_type: str | None = None
    proof_url: str | None = None

class CodingLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    log_date: str
    hours: float | None
    focus_rating: float | None
    tasks_completed: int | None
    what_i_worked_on: str | None
    proof_type: str | None
    proof_url: str | None

class DailyLogCreate(BaseModel):
    log_date: str  # ISO date string
    sleep_hours: float | None = None
    soreness: int | None = None
    diet_quality: int | None = None
    energy: int | None = None

class DailyLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    log_date: str
    sleep_hours: float | None
    soreness: int | None
    energy: int | None
    diet_quality: int | None
    workout_log: WorkoutLogResponse | None
    coding_log: CodingLogResponse | None

class DailyScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    score: float
    sleep_score: float | None
    recovery_score: float | None
    workout_consistency_score: float | None
    coding_consistency_score: float | None
    diet_score: float | None
    workout_rec: str | None
    coding_rec_hours: float | None
    summary: str | None
    flag_messages: list[str]
    