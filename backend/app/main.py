from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config
from app.api.review import router as review_router
from app.api.upload import router as upload_router

app = FastAPI(title="Lab Budget Monitoring API")

app.include_router(config.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api")
app.include_router(review_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
