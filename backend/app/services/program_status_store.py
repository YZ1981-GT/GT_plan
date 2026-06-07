"""程序状态存储接口 (Protocol).

定义项目级审计程序状态的持久化接口。
下游实现方（如 workpaper-account-package-d1-d2-pilot）需满足此协议，
通过 account_package_program_status 表落地。

本模块仅定义接口契约，不包含具体实现。
实际持久化由 `workpaper-account-package-d1-d2-pilot` spec 的
`account_package_program_status` 表承接。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.schemas.workpaper_semantic_contract import ProgramStatusContract


@runtime_checkable
class ProgramStatusStore(Protocol):
    """项目级程序状态存储接口。

    要求支持的核心字段：
    - applicable: 程序是否适用
    - status: 程序执行状态 (not_started/in_progress/completed/reviewed/rejected)
    - evidence_refs: 证据引用列表
    - conclusion: 程序结论
    - review_status: 复核状态 (pending/approved/rejected)
    - not_applicable_reason: 不适用理由（applicable=False 时必填）
    - reviewer / reviewed_at: 复核留痕

    实际持久化由 workpaper-account-package-d1-d2-pilot 的
    account_package_program_status 表落地。本接口仅定义读写契约，
    保证消费方可面向接口编程而不耦合具体存储实现。
    """

    async def get_status(
        self, project_id: str, program_code: str
    ) -> ProgramStatusContract | None:
        """获取单个程序的状态。

        Args:
            project_id: 项目 ID
            program_code: 程序编码（如 D1A-01）

        Returns:
            ProgramStatusContract 或 None（未找到时）
        """
        ...

    async def save_status(self, status: ProgramStatusContract) -> None:
        """保存（创建或更新）程序状态。

        调用方需保证 ProgramStatusContract 的验证规则已通过
        （如 applicable=False 时 not_applicable_reason 非空）。

        Args:
            status: 完整的程序状态契约对象
        """
        ...

    async def list_by_package(
        self, project_id: str, account_package_id: str
    ) -> list[ProgramStatusContract]:
        """列出指定科目工作包下所有程序状态。

        Args:
            project_id: 项目 ID
            account_package_id: 科目工作包 ID（如 D1, D2）

        Returns:
            该工作包下所有程序状态列表
        """
        ...
