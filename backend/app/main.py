from fastapi import FastAPI

from app.core.init_system import init_base, init_telephony
from app.api.routers import api_router

app = FastAPI()
app.include_router(api_router)


@app.on_event("startup")
async def init_system():
    await init_base()
    await init_telephony(app)