"""底稿模板扫描与索引建立

Phase 9 Task 9.1: 扫描致同模板文件夹，解析文件名，写入 wp_template 表
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpTemplate

logger = logging.getLogger(__name__)

# 审计循环映射：文件夹名首字母 → 循环代码
_CYCLE_MAP = {
    "B": "B",  # 初步业务活动
    "C": "C",  # 控制测试
    "D": "D",  # 收入循环
    "E": "E",  # 货币资金循环
    "F": "F",  # 存货循环
    "G": "G",  # 投资循环
    "H": "H",  # 固定资产循环
    "I": "I",  # 无形资产循环
    "J": "J",  # 职工薪酬循环
    "K": "K",  # 管理循环
    "L": "L",  # 债务循环
    "M": "M",  # 权益循环
    "N": "N",  # 税金循环
    "A": "A",  # 完成阶段
    "S": "S",  # 特定项目
    "Q": "Q",  # 关联方
}

# 从文件名提取编号的正则：匹配 E1-1、B60、C1、D1-1至D1-5 等
_CODE_PATTERN = re.compile(r'^([A-Z]\d+(?:-\d+)?(?:至[A-Z]?\d+-\d+)?)')


class TemplateScannerService:
    """底稿模板扫描服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def scan_folder(
        self,
        root_path: str,
        created_by: UUID | None = None,
    ) -> dict:
        """递归扫描模板文件夹，解析文件名，写入 wp_template 表

        Returns: {"scanned": N, "imported": M, "skipped": K, "errors": [...]}
        """
        root = Path(root_path)
        if not root.exists():
            return {"scanned": 0, "imported": 0, "skipped": 0, "errors": [f"路径不存在: {root_path}"]}

        # 获取已有模板编号（避免重复导入）
        existing_q = sa.select(WpTemplate.template_code).where(WpTemplate.is_deleted == False)  # noqa
        existing_codes = set((await self.db.execute(existing_q)).scalars().all())

        scanned = 0
        imported = 0
        skipped = 0
        errors: list[str] = []

        for file_path in root.rglob("*"):
            # 只处理 xlsx 和 docx
            if file_path.suffix.lower() not in (".xlsx", ".docx"):
                continue
            # 跳过临时文件
            if file_path.name.startswith("~$"):
                continue

            scanned += 1
            try:
                parsed = self._parse_filename(file_path)
                if not parsed:
                    skipped += 1
                    continue

                code, name, cycle = parsed
                if code in existing_codes:
                    skipped += 1
                    continue

                template = WpTemplate(
                    template_code=code,
                    template_name=name,
                    audit_cycle=cycle,
                    file_path=str(file_path),
                    status="published",
                    created_by=created_by,
                )
                self.db.add(template)
                existing_codes.add(code)
                imported += 1

            except Exception as e:
                errors.append(f"{file_path.name}: {e}")

        if imported > 0:
            await self.db.flush()

        logger.info(f"模板扫描完成: scanned={scanned}, imported={imported}, skipped={skipped}")
        return {"scanned": scanned, "imported": imported, "skipped": skipped, "errors": errors[:20]}

    def _parse_filename(self, file_path: Path) -> tuple[str, str, str] | None:
        """从文件名解析底稿编号、名称、审计循环

        示例：
          E1-1至E1-11 货币资金- 审定表明细表.xlsx → ("E1-1至E1-11", "货币资金-审定表明细表", "E")
          B60 审计方案.xlsx → ("B60", "审计方案", "B")
          C1 控制测试.docx → ("C1", "控制测试", "C")

        Returns: (code, name, cycle) or None if cannot parse
        """
        stem = file_path.stem.strip()

        # 提取编号
        m = _CODE_PATTERN.match(stem)
        if not m:
            return None

        code = m.group(1)

        # 提取名称（编号后面的部分，去掉多余空格和连字符）
        rest = stem[m.end():].strip()
        # 去掉开头的空格和连字符
        rest = re.sub(r'^[\s\-]+', '', rest)
        name = rest if rest else code

        # 推断审计循环（从编号首字母）
        cycle_letter = code[0].upper()
        cycle = _CYCLE_MAP.get(cycle_letter, cycle_letter)

        # 也可以从父文件夹名推断
        parent_name = file_path.parent.name
        if parent_name:
            folder_letter = parent_name[0].upper()
            if folder_letter in _CYCLE_MAP:
                cycle = _CYCLE_MAP[folder_letter]

        return code, name, cycle

    async def get_scan_summary(self) -> dict:
        """获取已扫描模板的统计摘要"""
        q = (
            sa.select(
                WpTemplate.audit_cycle,
                sa.func.count(WpTemplate.id).label("count"),
            )
            .where(WpTemplate.is_deleted == False)  # noqa
            .group_by(WpTemplate.audit_cycle)
            .order_by(WpTemplate.audit_cycle)
        )
        rows = (await self.db.execute(q)).all()
        total = sum(r.count for r in rows)
        by_cycle = {r.audit_cycle: r.count for r in rows}
        return {"total": total, "by_cycle": by_cycle}
