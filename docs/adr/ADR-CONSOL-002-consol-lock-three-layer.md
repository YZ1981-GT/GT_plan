# ADR-CONSOL-002: consol_lock 三层一致

## 状态
已接受 (2026-05-31)

## 背景

合并锁定功能存在致命缺口：
- 后端 `ConsolLockService` 用裸 SQL `UPDATE projects SET consol_lock=true` 操作
- `consol_lock` 列既不在 ORM `Project` 模型中，也不在 DB 迁移中
- `schema_drift_detector` 只保护 ORM 声明字段 → 锁定列对自动化安全网完全隐形
- `check_consol_lock`（deps.py）用 try/except SAVEPOINT 静默 pass → 列不存在时永远放行

结果：前端点锁定 → 后端 UPDATE 静默失败仍返 200 → 锁定形同虚设（"假成功"）。

## 决策

**consol_lock 必须三层齐全，drift detector 守护**：

1. **DB 迁移层**（V027）：`ALTER TABLE projects ADD COLUMN IF NOT EXISTS consol_lock BOOLEAN NOT NULL DEFAULT false` + `consol_lock_by UUID` + `consol_lock_at TIMESTAMPTZ`
2. **ORM 层**（Project 模型）：`consol_lock: Mapped[bool]` + `consol_lock_by: Mapped[UUID|None]` + `consol_lock_at: Mapped[datetime|None]`
3. **Service 层**（ConsolLockService）：改用 ORM `select(Project.consol_lock)` 查询/更新，**禁止裸 SQL**

**规约：service 层禁止裸 SQL 操作 ORM 未声明列**

- 用裸 SQL 操作未在 ORM 声明的列 = 自动化 schema 安全网盲区
- `schema_drift_detector` 只对比 ORM `Base.metadata` vs DB，裸 SQL 列两边都看不到
- 所有 consol 相关 service 必须通过 ORM `Mapped[]` 声明的字段操作
- 违反此规约的代码应被 code review 拒绝

**去静默 pass**：`check_consol_lock` 移除 try/except，列就位后 SELECT 失败应暴露而非永远放行。

## 后果

- 进 ORM 后 `schema_drift_detector` 自动守护 consol_lock 三列（0 漂移）
- 锁定功能从"装饰性失效"变为真实生效
- 前端锁定 → 后端真锁 → 子公司写端点返 423 → 前端显示锁定态（闭环）
- 新增 consol 字段必须同时走 DB 迁移 + ORM 声明 + service 使用，缺一不可
