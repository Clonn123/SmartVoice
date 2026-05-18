from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import get_settings
from app.modules.calls.schemas import ProcessCallsResponse

logger = logging.getLogger(__name__)


class JsonCallResultStorage:
    def __init__(self, storage_dir: str | None = None) -> None:
        settings = get_settings()
        self.storage_dir = Path(storage_dir or settings.result_storage_dir)

    async def save(self, result: ProcessCallsResponse) -> Path:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / f"{result.job_id}.json"
        payload = result.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Call result saved to JSON: path=%s", path)
        return path
