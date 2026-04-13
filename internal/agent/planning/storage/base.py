from __future__ import annotations

from abc import ABC, abstractmethod

from internal.agent.planning import Plan


class PlanStorage(ABC):
    """计划存储抽象基类"""

    @abstractmethod
    async def init(self) -> None:
        """初始化存储（创建表、打开文件等）"""
        ...

    @abstractmethod
    async def save(self, plan: Plan) -> None:
        """保存或更新计划"""
        ...

    @abstractmethod
    async def load(self, plan_id: str) -> Plan | None:
        """根据ID加载计划"""
        ...

    @abstractmethod
    async def delete(self, plan_id: str) -> bool:
        """删除计划，返回是否删除成功"""
        ...

    @abstractmethod
    async def list_plans(self) -> list[str]:
        """列出所有存储的计划ID"""
        ...

    @abstractmethod
    async def count(self) -> int:
        """统计存储的计划数量"""
        ...
