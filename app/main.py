from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import spheroidization
from app.api import review
from app.api import standard
from app.core.exceptions import BusinessException


app = FastAPI(
    title="球化监测系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(spheroidization.router)
app.include_router(review.router)
app.include_router(standard.router)


@app.exception_handler(BusinessException)
async def business_exception_handler(
    request: Request,
    exc: BusinessException,
):
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
        },
    )


@app.get("/api/health")
def health_check():
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "running"
        }
    }