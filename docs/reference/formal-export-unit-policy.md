# Formal Export Unit Policy Guide

> **spec**: platform-global-display-settings-closure task 12C (Stage C export unit documentation).
> Screen display preferences: [display-preferences.md](../frontend/display-preferences.md) (task 12A).
> Ledger import normalization: [ledger-import-unit-normalization.md](ledger-import-unit-normalization.md) (task 12B).

---

## 1. Export Surface Classification

Every file output is classified into exactly one of four types:

| Type | Description | Unit Source |
|------|-------------|-------------|
| formal | Official Excel/Word/PDF for audit delivery | ExportUnitPolicy (project unit) |
| data_exchange | Local data export (merge consolidation) | Raw yuan + _GT_EXPORT_META |
| template | Template-only (headers, no business rows) | N/A |
| non_amount | Non-financial output (logs, config, metadata) | N/A |

The EXPORT_SURFACE_REGISTRY enforces bidirectional equality between actual file sinks and registered classifications.

## 2. Standard Authority (Template-Based)

Standard templates declare default regions and units per version. Each ExportUnitRegion has:
- stable_id: template-defined stable identifier
- measure_kind: amount/quantity/count/ratio/exchange_rate/unit_price/text
- ratio_scale: fraction or percent_points (only for ratio kind)
- unit: yuan/qian/wan (from project amount_unit)
- divisor: 1/1000/10000

Only amount-kind regions execute the policy divisor. All other kinds output raw values.

## 3. Custom Authority (Two-Stage Reachable Chain)

Custom workbook units follow a five-step process:
1. Ingest: upload file, receive artifact + hash
2. Preflight: validate artifact structure, identify amount regions
3. Unit Authority PUT: confirm units per region with hash + preflight CAS
4. Finalize: lock artifact with confirmed authorities
5. Instantiate: bind to project working paper

Structure drift clears confirmations and requires re-preflight.

## 4. Audit Report Placeholders

Five financial placeholders in audit reports have registered stable region/kind:
- total_assets, total_liabilities, total_equity, total_revenue, net_income
- All are amount kind, use project amount_unit divisor
- ReportBodyService.fill_placeholders receives explicit policy

## 5. Working Paper / Word Version Evidence

- Every disclosure version with file content must have valid snapshot + digest pair
- OnlyOffice: base version verified before open, callback inherits by base_version_no
- Refresh: inherits current policy
- Full rebuild: creates new policy
- DB CHECK constraint enforces pair presence

## 6. PDF Export

- PDF strict DTO with object-level auth gate
- Memory password only (no disk credential)
- PDF-only validation errors: structured deletion of input/context in error_handler
- No report language selector (removed per review NIT)

## 7. Limitations and Degradation

- LibreOffice missing: PDF export returns 503 with clear message
- Custom workbook without authority: formal export blocked, data_exchange allowed
- Historical files without policy evidence: formal export blocked

## 8. Subsequent Batches

| Item | Status |
|------|--------|
| Full custom workbook wizard UI | Framework created, wizard not implemented |
| PDF password per-project configuration | Not in scope |
| Batch export with mixed policies | Not in scope |

---

## 9. 现行实现状态（2026-11-15 现算，禁按命名习惯推断）

> 本节由 `backend/tests/test_display_preferences_doc_guard.py` 守卫，
> 声明的每个符号都必须在代码里真实存在。

### 9.1 已接线的生产链

| 环节 | 代码位置 | 状态 |
|------|---------|------|
| 项目单位唯一读取入口 | `app/services/export_unit_policy_resolver.py` | ✅ 存在；读不到安全回落 `yuan`，不缩放金额 |
| 第一条正式导出链 | `bad_debt_rows.export_data` → `BadDebtExportService.export_bytes(export_policy=…)` | ✅ 金额按 `policy.divisor` 折算（Decimal `ROUND_HALF_UP` 到 0.01），R7 同步写「金额单位：元/千元/万元」 |
| 单位标注同源 | 同上 | ✅ 数值与标注同源（`test_export_unit_policy_wiring.py` 四例：元/千/万/Decimal 精度） |
| 出口注册表校验 | `app/services/export_surface_registry.py` | ✅ `validate_registry(app)` 可运行，四分类闭合检查在 |
| CLI 必含键 | `frontend_amount_guard.cli` 的 `export_surface_results` | ✅ `schema_version=3` 起为必含键（spec 任务 11C） |
| 前端正式导出边界 | `utils/exportUnit.ts` | ✅ 只接受服务端策略；`exportUnitPolicyGuard.spec.ts` 断言不 import/不读 `displayPrefs` |
| PDF 面板 | `PDFExportPanel.vue` | ✅ 「报表语言」选择器与 `exportLanguage` 已删除（`displaySettingsWiring.spec.ts` 反向断言） |

### 9.2 尚未接线（如实列出，不得标完成）

| 环节 | 现状 | 影响 |
|------|------|------|
| `unit_policy_snapshot` | 只在模型/迁移层（`V265`），无生产写入方 | 导出任务的策略快照尚未落库 |
| 审计报告五个 placeholder | `ReportBodyService.fill_placeholders` 未接收 policy | AC-19 未达成 |
| 组合包 / 归档消费者 | `ExportPackageService` / `archive_inventory` 未接 policy | AC-21 未达成 |
| `_GT_EXPORT_META` marker | 未实现 | data_exchange 文件缺说明与元数据 |
| PDF 422 redactor | `middleware/error_handler.py` 未做结构化删除 `input`/`context` | AC-22 未达成 |
| 出口注册表闭集 | 真实 `app.routes` 与注册表存在 **308 条未登记 + 15 条登记未挂载**的既有漂移 | 按 memory ㉗「恒红门禁等于没有门禁」，CLI 侧记 `known_drift` 不硬失败，待后续批次逐条治理 |

### 9.3 `ExportUnitRegion` 契约

```python
@dataclass(frozen=True)
class ExportUnitRegion:
    stable_id: str          # 模板定义的稳定标识（不因 sheet 改名而变）
    measure_kind: str       # amount/quantity/count/ratio/exchange_rate/unit_price/text
    ratio_scale: str | None # fraction | percent_points（仅 ratio kind 可传）
    unit: str               # yuan/qian/wan（来自项目 amount_unit）
    divisor: Decimal        # 1 / 1000 / 10000
```

**只有 `amount` 类 region 执行 policy divisor**；其余 kind 一律输出原值。
`ratio` 的两种刻度 divisor 都是 1（`0.2 fraction` 与 `20 percent_points` 都显示 `20.00%`）。

### 9.4 模板单位的判定纪律

🔴 **不得靠自由文本猜模板单位**。判据只有三条：

1. **standard 模板**：由 `export_unit_policy` sidecar 逐四版声明 `default` 与 `table` units；
2. **custom workbook**：由两阶段可达链的 **unit-authority PUT**（hash + preflight CAS）显式确认；
3. **历史文件**：无 policy 证据的一律阻断正式导出（`data_exchange` 可放行）。

模板表头里写「万元」「千元」之类的自由文本**不参与推断**——它既可能是单位声明，
也可能是业务描述（如「万元以上的固定资产」），靠文本猜会把单位猜错且无法审计。

### 9.5 与屏幕显示的关系

| 维度 | 屏幕（12A） | 正式导出（12C） |
|------|------------|----------------|
| 单位来源 | 账号偏好 `displayPrefs.amountUnit`（可覆盖） | **服务端项目策略**（`projects.amount_unit`） |
| 小数位 | 账号偏好 `displayPrefs.decimals` | 策略固定（金额 2 位） |
| 是否可被用户改 | 是（个人偏好） | **否**（formal 出口不得读 `displayPrefs`） |
| 证据 | 无（个人视图） | `unit_policy_snapshot` + digest pair |

🔴 这条边界是 AC-20 的核心：**个人单位偏好不得影响正式交付件**。
`utils/exportUnit.ts` 的 `applyFormalExportUnit` / `formalExportUnitHeaderNote` 是唯一入口，
divisor 与 unitSuffix 必须来自同一份服务端策略（否则会出现「数值按万元、标注写元」的错配）。

## 10. 故障注入清单（AC-24 的 C 部分）

逐 sink / 逐 placeholder / 逐 custom 阶段 / 逐归档证据 / 密码 redactor 都要有变异：

| 变异 | 必须红在 |
|------|---------|
| 删 `export_unit_policy_resolver` 的回落分支 | 「读不到项目单位时金额被缩放」断言 |
| 把 `divisor` 从 `policy.divisor` 改成常量 1 | 「万元项目导出金额未折算」断言 |
| 删 `formalExportUnitHeaderNote` | 「单位标注缺失」断言 |
| 让 `utils/exportUnit.ts` 读 `displayPrefs` | `exportUnitPolicyGuard.spec.ts` 的 import/读取断言 |
| 删 `EXPORT_SURFACE_REGISTRY` 某一分类 | `export_surface_results.errors` 的「没有任何登记出口」 |
| 注册表重复登记同一 path | `duplicate_classification` |
| PDF create 路由的 validation error 不删 `input` | 唯一 marker 的零泄漏断言 |
