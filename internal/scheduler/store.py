"""Task persistence layer."""

import asyncio
import json
import logging
import time
from pathlib import Path

from internal.scheduler.types import Task, task_from_dict

logger = logging.getLogger(__name__)


class TaskStore:
    """Persist scheduled tasks to disk."""

    def __init__(self, data_dir: str = "./data/scheduler"):
        self.data_dir = Path(data_dir)
        self._filepath = self.data_dir / "tasks.json"
        self._tasks: dict[str, dict] = {}

    async def init(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self._filepath.exists():
            await self._load_from_disk()
        else:
            self._tasks = {}
            await self._save_to_disk()

    async def save(self, task: Task) -> None:
        self._tasks[task.task_id] = task.to_dict()
        await self._save_to_disk()
        logger.debug("Saved task '%s'", task.task_id)

    async def load(self, task_id: str) -> Task | None:
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return task_from_dict(data)

    async def list_all(self) -> list[Task]:
        return [task_from_dict(d) for d in self._tasks.values()]

    async def delete(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            await self._save_to_disk()
            logger.debug("Deleted task '%s'", task_id)
            return True
        return False

    async def _save_to_disk(self) -> None:
        content = json.dumps(
            {"tasks": list(self._tasks.values()), "updated_at": time.time()},
            ensure_ascii=False, indent=2,
        )
        await asyncio.to_thread(self._write_file, content)

    def _write_file(self, content: str) -> None:
        self._filepath.write_text(content, encoding="utf-8")

    async def _load_from_disk(self) -> None:
        content = await asyncio.to_thread(self._filepath.read_text, encoding="utf-8")
        try:
            data = json.loads(content)
            task_list = data.get("tasks", [])
            self._tasks = {t["task_id"]: t for t in task_list}
            logger.info("Loaded %d tasks from disk", len(self._tasks))
        except json.JSONDecodeError:
            logger.warning("Corrupt tasks.json, starting fresh")
            self._tasks = {}
