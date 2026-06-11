import asyncio

from app.modules.telephony.factory import create_worker_caller

_worker_caller = None
_worker_lock = asyncio.Lock()


async def get_worker_caller():
    global _worker_caller

    if _worker_caller:
        return _worker_caller

    async with _worker_lock:

        if _worker_caller:
            return _worker_caller

        _worker_caller = await create_worker_caller()

        return _worker_caller
