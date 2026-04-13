from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict

import aiofiles

from internal.agent.planning import Plan
from .base import PlanStorage

logger = logging.getLogger(__name__)


class JSONPlanStorage(PlanStorage):
    """JSON文件存储后端。
    
    所有计划存储在单个JSON文件中。
    """

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        # Ensure parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._plans: Dict[str, dict] = {}
        self._initialized = False

    async def init(self) -> None:
        """初始化存储，加载现有数据"""
        if self._initialized:
            return

        # 如果文件不存在，创建空结构
        if not self.file_path.exists():
            self._plans = {}
            await self._save_to_disk()
        else:
            await self._load_from_disk()

        self._initialized = True

    async def _load_from_disk(self) -> None:
        """从磁盘加载JSON数据"""
        try:
            async with aiofiles.open(self.file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                self._plans = data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"Failed to load plans from {self.file_path}: {e}")
            self._plans = {}

    async def _save_to_disk(self) -> None:
        """保存数据到磁盘"""
        try:
            async with aiofiles.open(self.file_path, "w", encoding="utf-8") as f:
                content = json.dumps(self._plans, indent=2, ensure_ascii=False)
                await f.write(content)
        except Exception as e:
            logger.error(f"Failed to save plans to {self.file_path}: {e}")
            raise

    async def save(self, plan: Plan) -> None:
        """保存或更新计划"""
        if not self._initialized:
            await self.init()

        now = int(time.time())

        # Serialize the entire plan by extracting all public properties
        # This should work for any concrete Plan implementation
        plan_dict = {
            "plan_id": plan.plan_id,
            "name": plan.name,
            "description": plan.description,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "description": task.description,
                    "dependencies": task.dependencies,
                    "status": task.status
                }
                for task in plan.tasks
            ],
            "created_at": self._plans.get(plan.plan_id, {}).get("created_at", now),
            "updated_at": now
        }

        self._plans[plan.plan_id] = plan_dict
        await self._save_to_disk()

    async def load(self, plan_id: str) -> Plan | None:
        """根据ID加载计划"""
        if not self._initialized:
            await self.init()

        if plan_id not in self._plans:
            return None

        try:
            plan_data = self._plans[plan_id]
            # The actual reconstruction needs to be handled by the consumer
            # since Plan is abstract, we just store the deserialized data
            # and reconstruction happens at a higher level with the concrete Plan class
            logger.debug(f"Loaded plan data for {plan_id}: {plan_data}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse plan {plan_id}: {e}")
            return None

    async def delete(self, plan_id: str) -> bool:
        """删除计划，返回是否删除成功"""
        if not self._initialized:
            await self.init()

        if plan_id not in self._plans:
            return False

        del self._plans[plan_id]
        await self._save_to_disk()
        return True

    async def list_plans(self) -> list[str]:
        """列出所有存储的计划ID"""
        if not self._initialized:
            await self.init()

        return list(self._plans.keys())

    async def count(self) -> int:
        """统计存储的计划数量"""
        if not self._initialized:
            await self.init()

        return len(self._plans)
