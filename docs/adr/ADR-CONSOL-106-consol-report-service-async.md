# ADR-CONSOL-106: consol_report_service 统一 async（搭车 A1/A2 重构）

## 状态
已接受 (2026-05-31)

## 背景

`ConsolReportService.__init__(db: AsyncSession)` 声明 async session，但方法体内全部用同步 `self.db.query(...).filter(...).all()` —— `AsyncSession` 根本没有 `.query()`，SQLAlchemy 2.0 下属破碎代码（A3，因 0 PG consolidated 项目从未真正运行而未暴露）。且 `get_goodwill_list` / `get_mi_list` 是 async 却被同步调用（未 await）。

## 决策

随 A1/A2 重构（已触碰 consol_report_service）一并完成 async 统一，避免二次触碰：

- 全部方法改 `async def`：`generate_consol_reports` / `verify_balance` / `_verify_balance_from_consol_trial` / `generate_consol_workpaper` + 4 个 sheet 构建器 / `generate_consol_notes` + 5 个 section 生成器。
- 同步 `self.db.query(...).filter(...).all()` → `await self.db.execute(sa.select(...))` + `.scalars().all()`。
- `get_goodwill_list` / `get_mi_list` 改 `await`。
- `_create_company_trial_sheet` 的 N×M 逐格查询改批量预加载 dict（消除 N+1）。
- `*_sync` 便捷函数改 `async def` + 内部 `await`；保留 `*_sync` 名称兼容既有 import；路由层（consol_report.py）4 处调用加 `await`。
- 删除死代码：`import re` + `_TB_PATTERN`/`_SUM_TB_PATTERN`/`_ROW_PATTERN` + `from sqlalchemy.orm import Session, joinedload`。

## 后果

- 消除 `MissingGreenlet` 风险路径，与 A1/A2 一次改完（R8）。
- 全程 Decimal 取数（Q6）。
- 改造面与 A1/A2 重叠，统一回归测试覆盖（report_engine 56 + consol Phase0/1 测试全绿）。
