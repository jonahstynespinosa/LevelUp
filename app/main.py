from fastapi import FastAPI
from app.api.routes.auth import router as auth_router

from app.db.session import engine
from app.models.models import Base

app = FastAPI(title="LevelUp")
app.include_router(auth_router, prefix="/auth", tags=["auth"])


Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "LevelUp API running!"}