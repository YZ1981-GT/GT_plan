# Lane 1 代码改动证据

**日期**：2026-09-27

## T4~T7: 位置化行身份修复（8 个 site）

### useI3Disclosure.ts 改动（6 处）

1. **新增** `_stableRowId(prefix)` 内部函数：`${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
2. **Site #1 (族A')** L488: `cgu-${i}` → `_stableRowId('cgu')`
3. **Site #2 (族B)** L441: `bv-${r.rowId || i}` → `bv-${r.rowId || _stableRowId('bv').slice(3)}`
4. **Site #3 (族B)** L463: `imp-${r.rowId || i}` → `imp-${r.rowId || _stableRowId('imp').slice(4)}`
5. **Site #4 (族B)** L503: `perf-${r.rowId || i}` → `perf-${r.rowId || _stableRowId('perf').slice(5)}`
6. **Site #7 (族D)** L665: `perf-${Date.now()}-${added}` → `_stableRowId('perf')`
7. **Site #8 (族D)** L725: `ap-${Date.now()}-${added}` → `_stableRowId('ap')`

### I3TabRecoverableTest.vue 改动（1 处）

8. **Site #5 (族B)** L686: `cgu-${idx}` → `cgu-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

### i1DisclosureEnhance.ts 改动（1 处）

9. **Site #6 (族B)** L241: `tc-i18-${r.rowId || i}` → `tc-i18-${r.rowId || <稳定id>}`

### Grandfather 策略

- 族 B 的 5 处都保留了 `r.rowId ||` 前缀 → 已落库的旧值（如 `cgu-3`）在上游 rowId 存在时原值保留
- 族 A' 的 site #1 是全新生成，不走兜底逻辑
- 旧格式正则: `^(cgu|bv|imp|perf|ap|tc-i18)-\d+$` 读时仍认

## T13: I3-2 四格覆盖层

**方案已设计**（FC-5 第 5 个例外），覆盖层把 AA23:AD23 的 `=SUM(AA27:AA30)` 改为 `=SUM(AA14:AA22)`。
**产品代码改动待 provider 文件实施时一并写入**（覆盖层注册在 `StoreMergePlan` 的 `known_template_quirks` 处理逻辑中）。

## T14/T15: 两份契约

- `i1.intangible_assets_detail.json` ✅（含 regions[1] derived + dual_definition + soe_classification MISMATCH）
- `i3.goodwill_detail.json` ✅（含 footer_kind=row_formula_applied + positional_identity 7 sites + overlay_fixed quirk）
- 契约目录现算: **24 个**（并发会话又加了 f2×2 + g9）

## T16: 载体/门控/跨引用

- I1/I3 都是 host_inline（Task 5 已验 checklist_get=0 / bridge=0 等）
- TB 发布门: I1 = useI1Adjudication.ts + I1TabAdjudication.vue / I3 同型
- 跨 lane 冻结: `I2-2-rows` 被 useI1AdditionCheck.ts#L250-251 跨 entry 消费（Task 17 已确认）
- H1 pilot golden: 不动（Task 17 已确认）

## T17: 注册

注册走 `register_from_manifest()`，**禁手改 manifest**。provider python 文件待并发收尾后实施。

## T18*/T19*: 阻塞

- T18* roundtrip: `[ ]*` 阻塞于 BP-4（真库两键皆空 → 只能合成载荷）
- T19* 人工审核: `[ ]*` 阻塞于 BP-2/BP-3
