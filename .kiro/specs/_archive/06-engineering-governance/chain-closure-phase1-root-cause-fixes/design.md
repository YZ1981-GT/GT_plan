# 设计：阶段一四个根因修复

## 设计原则

四处都是**一行级漏传/写死/标错表**，不是设计缺失。修复一律**照抄同仓已有的正确用法**，
不引入新抽象、不新建 service、不加配置项（ponytail 原则：已有依赖能做就不写新的）。

## 关键对照事实（现读实证，2026-09-28）

`ReportConfigService.resolve_applicable_standard(db, project_id) -> str`
（`report_config_service.py:83`）已存在：读 `Project.template_type` + `report_scope`
组合为 `listed_standalone` 等，非白名单降级 `"enterprise"`。
`VALID_STANDARDS = {soe_consolidated, soe_standalone, listed_consolidated, listed_standalone, enterprise}`。

🔴 **决定性对照**：同一个 `ReportEngine` 类内的 `_build_unadjusted_bundle`（`report_engine.py:1604`）
**已经正确调用**该解析器：

```python
applicable_standard = await ReportConfigService.resolve_applicable_standard(self.db, project_id)
all_configs = await self._load_report_configs(applicable_standard)
```

而 `on_trial_balance_updated` → `regenerate_affected` 这条路径**漏传**第四参。
⇒ 修复 R3 = 把已有正确用法补到漏的那条路径上，**不是新设计**。

🔴 **隐患登记**：`enterprise` 在 `VALID_STANDARDS` 白名单里，但 `report_config` 表实测 **0 行**。
即解析器的降级值本身是死值。本 spec 不改白名单（影响面未知），改为在 configs 为空时**记 warning 暴露**
（需求 3.5），使「静默零重算」变成「可见的零重算」。

## 组件与改动清单

| 根因 | 文件 | 改法 | 行级规模 |
|---|---|---|---|
| R3 | `services/report_engine.py` `on_trial_balance_updated` | 补解析准则 + 传参 + configs 空时 warning | +~12 行 |
| R4 | `services/event_handlers/_impl.py` `_mark_reports_stale_on_adjustment` | 增 `FinancialReport` 的 update（保留 AuditReport） | +~20 行 |
| R2 | `services/formula_management/draft_refresh_orchestrator.py` `_dispatch_via_coordinator` | `"report:*"` → 从预设库 `report:` 前缀键派生 | ±~10 行 |
| R1 | `routers/draft_refresh.py` `PARTNER_ROLES` | 加 `"admin"` | ±1 行 |

## R3 设计：报表增量重算传项目真实准则

改 `ReportEngine.on_trial_balance_updated`：

```python
from app.services.report_config_service import ReportConfigService

applicable_standard = await ReportConfigService.resolve_applicable_standard(
    self.db, payload.project_id,
)
n = await self.regenerate_affected(
    payload.project_id, year, payload.account_codes,
    applicable_standard=applicable_standard,
)
if n == 0:
    logger.warning(...)   # 需求 3.5：零重算必须可见，不再静默成功
```

**为什么不在 `regenerate_affected` 内部解析**：该方法是纯计算入口，被 3 处调用
（orchestrator / 本 handler / 测试），内部解析会让调用方失去覆写能力，且与
`_build_unadjusted_bundle` 的既有分层（调用方解析、计算方收参）不一致。

**为什么不改默认值 `"enterprise"` → 其他**：默认值是 3 个调用点共享的签名契约，
动它会影响 orchestrator 路径；且 `"enterprise"` 作为「未知准则」的哨兵值有语义，
问题在于**没人把真值传进来**，不在默认值本身。

## R4 设计：stale 标到 financial_report

在 `_mark_reports_stale_on_adjustment` 内、现有 `AuditReport` 与 `DisclosureNote` 两段之间
插入 `FinancialReport` 段，三段各自 try/except + `log_stale_degraded`，互不阻断：

```python
from app.models.report_models import FinancialReport
await session.execute(
    _sa.update(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == year,
        FinancialReport.is_deleted == False,
    ).values(is_stale=True)
)
```

**为什么不替换 AuditReport 那段**：审计报告的财务数据摘要确实也会过期，
`AuditReportService.on_reports_updated` 依赖它，删掉是回归。两者都标才对。

## R2 设计：report scope 的 page_keys 逐张派生

现状（`draft_refresh_orchestrator._dispatch_via_coordinator`）：

```python
if scope == "report":
    page_keys.append("report:*")      # 预设库无此键 ⇒ 恒不命中
```

改为从预设库实际键派生（需求 2.4：不写死报表类型清单）：

```python
if scope == "report":
    from app.services.formula_management.preset_library import build_preset_index
    try:
        page_keys.extend(sorted(k for k in build_preset_index() if k.startswith("report:")))
    except Exception:
        logger.warning(...)           # 预设库不可用不阻断刷新（与治理层 fail-open 一致）
```

**为什么不写死 7 个报表类型**：预设库是权威源，写死会在预设库增删报表类型时静默漂移
（与 M 轮 `M{n}_SHEET_MAP` declared≠hit 同型缺陷）。派生法让两侧永远同集合。

**为什么不复用 `FinancialReportType` 枚举**：预设库的 `report:` 键除 5 张主表外还含
`report:cross_check` 与 `report:impairment_provision`，与枚举不是同一集合；
按枚举派生会漏掉 `cross_check`（勾稽校验公式 86 条）。

## R1 设计：门禁可达性

```python
PARTNER_ROLES = ["partner", "signing_partner", "admin"]
```

**为什么用 admin 而不是给现有用户改角色**：改真实用户的 role 是数据变更、影响其他权限判定；
把 admin 加进白名单是配置级、可逆、语义正确（admin 是超管）。

**为什么不放开 auditor**：全局一键刷新会批量改写全项目底稿/报表/附注初稿，
审计助理不应有此权限（需求 1.2 显式断言 auditor 仍 403，防止修过头）。

## 变异证明设计（需求 5）

| 根因 | 变异测试 | 修复前预期 | 修复后预期 |
|---|---|---|---|
| R3 | 同一项目分别用 `enterprise` / 项目真实准则调 `_load_report_configs` | enterprise → 0 行 | 真准则 → 非 0 行；且 handler 路径重算行数 > 0 |
| R4 | 触发 stale 级联后查 `financial_report.is_stale` | 0 行被标 | 该项目该年度全部被标；`AuditReport` 仍被标 |
| R2 | 断言派生出的 page_keys 全部命中 `build_preset_index()` | `"report:*"` 不命中 | 每个键都命中且数量 == 预设库 `report:` 键数 |
| R1 | 端点级 TestClient 真发请求（不是只查 `router.routes`） | admin 403 | admin 非 403；auditor 仍 403 |

🔴 **反向断言必配**（方法论铁律㉒㉓）：
- R3 测试 SHALL 同时断言 `enterprise` 仍得 0 行（证明扫描器不是恒真）
- R2 测试 SHALL 同时断言字面量 `"report:*"` 不在预设库（证明旧实现确实坏）
- R1 测试 SHALL 同时断言 auditor 被拒（证明没放开过头）

🔴 **端点级测试的依赖工厂坑**（方法论铁律㉕）：`require_role(...)` 每次返回**新函数对象**，
不能直接 `dependency_overrides[require_role(...)]`（key 匹配不上，override 静默失效）。
正解 = override 内层 `get_current_user` / `get_db`，让真实角色判定跑。

## 测试数据策略（需求 5.4）

端到端验证用**专用测试项目**（`seed` 造，测后删），不碰 10 个真实项目：
1. 建 project（`template_type='listed'`, `report_scope='standalone'`）
2. 造 `ledger_datasets`(active) + `tb_balance` 两个科目 + `trial_balance` 两行
3. 造 `financial_report` 两行（引用这两个科目的公式）
4. 建调整分录 → `draft` → `pending_review` → `approved`
5. 断言：TB 调整列变化 + 报表值变化 + `financial_report.is_stale=True`

## 风险与回归面

| 风险 | 缓解 |
|---|---|
| R4 给 `financial_report` 批量置 stale 可能让大量报表显示过期 | 这是**正确行为**（数据确实过期）；限项目+年度，不跨项目 |
| R3 每次事件多一次 Project 查询 | 单行主键查询，与既有 `_build_unadjusted_bundle` 同成本 |
| R2 派生键变多 ⇒ 刷新单元数上升 | 治理层 `refresh_with_presets` 已有幂等/覆盖排除/快照，不绕过 |
| R1 admin 获得全局刷新权 | 端点原有 precheck + advisory lock + 审计留痕不变 |

零回归判据：`test_report_engine.py` / `test_trial_balance.py` / `test_event_bus.py` /
`test_adjustment_sync.py` 修复前后同样通过；见红先 `git stash` 区分预存红与本轮引入红。
