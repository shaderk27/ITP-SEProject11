from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config
from app.api.upload import router as upload_router
from app.api.auth import router as auth_router

app = FastAPI(title="Lab Budget Monitoring API")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",'null'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(config.router)
app.include_router(upload_router, prefix="/api")
app.include_router(auth_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
