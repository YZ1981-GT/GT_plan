# tenant_id 渐进迁移计划

## Current State

- `get_active_filter` 已有 `current_user_id: UUID | None` 可选参数（Sprint 7.6）
- 40+ 调用点中 **3 个**已显式传入（2 个 `import_service.py` opt-out + 1 个穿透入口）
- 路由层 `require_project_access` 仍是主要权限屏障，tenant_id 是防御性冗余

## Strategy: 触碰即修

每次修改含 `get_active_filter` 调用的文件时，补上 `current_user_id` 参数。

规则：
- 路由层能拿到 `current_user.id` 的，直接传入
- Service 内部调用（无 user context），显式写 `current_user_id=None`（opt-out）
- 新增调用点**必须**传入（CI review 卡点）

## Deadline

**2026-08-11**（3 个月）

## Tracking

```bash
# 统计剩余未迁移数量（目标：降到 0）
grep -rn "get_active_filter" backend/app/ | grep -v "current_user_id" | wc -l
```

## Priority Order

1. `drilldown_service.py` — 穿透查询，安全敏感
2. `ledger_penetration.py` — 14 处调用，最大单文件
3. `formula_engine.py` — 公式计算引用账表数据
4. `import_intelligence.py` — 导入分析
5. 其余（aging_analysis / data_validation / note_data_extractor 等）

## Note

路由层 `require_project_access` 仍是主要权限屏障。
`current_user_id` 校验是**防御性冗余**——即使路由层被绕过（内部 RPC / 未来微服务拆分），
数据层仍能阻止越权访问。迁移完成后可考虑将校验从"可选"升级为"强制"。
