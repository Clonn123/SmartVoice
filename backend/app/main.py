from fastapi import FastAPI

from app.api.routers import api_router
from app.core.init_system import init_base, init_telephony
from app.observability import observability_runtime

app = FastAPI()
app.include_router(api_router)


@app.on_event("startup")
async def init_system():
    observability_runtime.start()

    await init_base()
    await init_telephony(app)


@app.on_event("shutdown")
async def shutdown_system():
    observability_runtime.stop()
