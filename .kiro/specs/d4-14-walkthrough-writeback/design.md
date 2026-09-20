# Design — D4-14 营业收入发生检查表 双向回写

## 概述

D4-14 是**单宽动态行表**（每行一笔交易，横向 37 物理列覆盖 7 个证据维度）。引擎范式（动态行 + 嵌套 json_pointer）已由 D4-7 验证可支持，footer 单行 `合计` 非障碍。**真障碍是语义映射权威源未确认**：源模板 15+ 物理列在前端 7 维模型无对应字段。

因此本 spec 的形态与 D4-12（纯工程）不同：**第一阶段是业务裁决门，不是工程**。裁决未签署确认前，后续全部工程 BLOCKED。这是 design 的核心结构决策——把"人工决策"显式建成阻塞门，而非让工程基于臆想映射先跑。

## 现状锚点（实测冻结）

### 源模板物理列（`营业收入发生检查表D4-14`，A1:AK52，37 列）
| 组 (R13) | 物理列 (R14) | 前端 7 维是否有对应字段 |
|---|---|---|
| — | A 序号 | 模板自增，不入契约 |
| 记账凭证 | B 客户名称 | ❌ 前端 voucher 无 |
| 记账凭证 | C 日期 / D 编号 / E 品名 / F 数量 / G 金额(SUM) | ✅ voucher.date/number/productName/quantity/amount |
| 销售合同 | H 日期 | ❌ 前端 contract 无 date |
| 销售合同 | I 合同号/订单号 | ✅ contract.number |
| — | N 仓库保管员 | ✅ delivery.warehouseKeeper |
| — | O 发货审批人 | ⚠️ 前端 contract.approver/confirmor 归属存疑（裁决定） |
| 出库单 | J 日期 / L 品名 | ✅ delivery.date/productName |
| 出库单 | K 编号 / M 数量 | ❌ 前端 delivery 无 number/quantity |
| 运输单 | P 日期 | ✅ shipping.date |
| 运输单 | Q 编号 / R 运输数量 / S 运输公司 / T 运输地址 | ❌ 前端 shipping 全无（只有 date/productName/amount，且模板运输组无金额列） |
| 签收单 | U 日期 / V 品名 / X 金额(SUM) | ✅ receipt.date/productName/amount |
| 签收单 | W 数量 / Y 签收人 / Z 盖章类型 / AA 盖章单位 | ❌ 前端 receipt 无 |
| 发票 | AB 日期 / AC 编号 / AF 金额(SUM) | ✅ invoice.date/number/amount |
| 发票 | AD 品名 / AE 数量 | ❌ 前端 invoice 无 |
| — | AI 其他文件说明 / AJ 索引号 | ✅ other.description/indexNo |
| — | AG/AH …… 占位 / AK 是否异常 | 占位/派生 |

> 数据区 R15-R36；footer marker 单行 `合计` R37（G37/X37/AF37 SUM → formula_mask）；R38 本期发生额 / R39 检查比例(G39=G37/G38) / R40+ 审计说明结论 = HTML-only。UUID 列 = AL（物理列止于 AK）。

### 关键差异（vs 语义投影头）
后端 `_SHEET_HEADERS["D4-14"]`（32 列）是**按前端 7 维平铺的语义投影头**，非物理列。上表右列 ❌ 的物理列在语义投影头里根本没有——直接拿语义投影头当 sync 映射会静默丢弃它们。

## 架构

### 阶段结构（关键：Phase 0 是业务门）
```
Phase 0（业务裁决门，非工程）
  └─ 逐列裁决表：37 物理列 × {受管/前端补字段/HTML-only/派生}
      └─ 审计业务复核签署 → 权威源确认
          └─（未签署 = 后续全 BLOCKED）
─────────── 裁决门通过后才进 ───────────
Phase 1  前端模型对齐（按裁决补字段 / import-export 同步）
Phase 2  provider（动态行 + 嵌套 json_pointer，只受管裁决的「受管」列）
Phase 3  发布链
Phase 4  前端接桥 + 宿主登记
Phase 5  守卫 + 消费侧 + e2e + 收口
```

### 关键设计决策

**决策 0：业务裁决门显式建成 BLOCKED 前置**
不把裁决藏在 Task 正文的一句话里，而是让 Phase 0 产出一份**签署制**裁决表（`evidence/d414-column-mapping-adjudication.md`），后续所有 Task 的 blocking 条件指向它。裁决三种可能结论，design 都预置了路径：
- **A. 全受管（前端全补字段）**：扩前端 7 维加 15+ 字段。ROI 需评估（是否值得为穿行测试补这么多字段）。
- **B. 部分受管 + 部分 HTML-only**：核心可比对字段（日期/金额/品名/编号）受管，辅助字段（客户名称/盖章单位/运输地址等）HTML-only。**最可能的现实结论**。
- **C. 不值得双向（single_html）**：若受管收益 < 补字段成本，裁决为 D4-14 保持 single_html/仅导入导出，本 spec 收口为"裁决完成，工程不执行"，清册标终态。

> 无论 A/B/C，**都不静默丢物理列**——HTML-only 列显式标记为"不受管、保留模板内容"，extract/materialize 不触碰。

**决策 1：动态行表轴（非转置/非 static-region）**
D4-14 走既有动态行 provider 范式（同 D4-7/D4-20），行身份 = 交易 id、UUID 列 AL、两级表头 R13-14（header_rows=2）、footer marker `合计`。嵌套 json_pointer（`/voucher/amount` 等）同 D4-7 已验证。

**决策 2：只受管「受管」列，HTML-only 列 fail-closed 保护**
provider 的 field specs 只覆盖裁决表标「受管」的物理列。HTML-only 物理列（如 B 客户名称、Z 盖章类型）不进契约 field，materialize 不写、extract 不读；verify_unmanaged_regions 把它们纳入 unmanaged 区（改动即判 drift，保护模板内容不被覆盖）。

**决策 3：前端补字段最小化**
若裁决为 B（部分受管），前端只补「受管且前端缺」的字段（如 shipping 补 number/quantity/company），不补 HTML-only 字段。补字段同步 import/export 32 列头，避免语义投影头再次与物理映射分叉。

## 数据流

### HTML → OO（materialize）
前端 store `D4-14-transactions` = `[{id, voucher{...}, contract{...}, ...7维}]` → build_store_projection（嵌套 json_pointer，只投影受管字段）→ materialize 逐交易行写受管物理列（按裁决映射），HTML-only 列不动。

### OO → HTML（extract + mirror）
extract 读交易行受管物理列 → 7 维嵌套 projection → merge。`oo_to_html` mirror 消费 `D4-14-transactions`（list base，第四维判据：base 非空、applied>0 不抹 HTML-only 维度字段）。

## 组件与接口

### 新增文件
- `backend/app/services/workpaper_sync/phase5_d4_14_occurrence.py`：provider（动态行 + 嵌套，字段按裁决表）。
- `backend/tests/workpaper_sync/test_d4_14_occurrence_contract.py` / `test_d4_14_walkthrough_roundtrip.py` / `test_d4_14_mirror_consume.py`。
- 前端守卫 `d4OccurrenceSyncHostWiring.spec.ts`。
- 变异 `backend/scripts/diagnose/mutate_d4_14_guards.py`。
- `evidence/d414-column-mapping-adjudication.md`（Phase 0 裁决表，签署制）。
- `evidence/d414-geometry.json`（物理列几何冻结）。

### 改动文件（依赖裁决）
- `useD4WalkthroughTest.ts`（若裁决补字段）+ `D4TabOccurrence.vue`（接桥）+ `GtD4OperatingRevenue.vue`（宿主登记）。
- `_d4_import_export.py`（若补字段同步 32 列头）。
- `phase5_d4_revenue_detail.py`（契约装配，只加不动既有）。
- 契约 `d4.revenue_detail.json`（generate --apply）。
- `docs/operations/d4-bidirectional-writeback-inventory.md`（收口）。

## 错误处理
- 裁决未签署 → 后续 Task BLOCKED（不 fail-open 造 provider）。
- HTML-only 物理列被 materialize 触碰 → verify 判 unmanaged drift fail-closed。
- footer marker `合计` 多行歧义 → 单行匹配（实测 R37 唯一）。
- 公式格（G/X/AF/G39）含公式被当录入 → formula_mask 保护，extract 拒绝把公式当值。
- rematerialize soft_limit → 不提高过关。

## 测试策略

### Properties
- **Property 1（裁决门 fail-closed）**：裁决表未签署确认时，provider Task 视为 BLOCKED（本 property 由流程守卫 + tasks blocking 表达，非运行时代码）。**Validates: 1.5, DEC-0**
- **Property 2（不丢物理列）**：materialize→extract 后，HTML-only 物理列内容逐字节 == 改前（不被覆盖）；受管列逐字段往返一致。**Validates: 3.3, 6.1**
- **Property 3（7 维嵌套往返）**：受管字段 build_projection→merge 逐字段等（嵌套 json_pointer）。**Validates: 3.2, 6.1**
- **Property 4（契约形态）**：契约 parse 含 d4-14-managed（header_rows=2、嵌套 field、formula_mask 含 G/X/AF/G39）；item_id 字面量 `D4-14-transactions`。**Validates: 3.4**
- **Property 5（消费侧第四维）**：mirror 对 `D4-14-transactions`（list base）正确消费不静默投空。**Validates: 6.2**
- **Property 6（不打挂 entry）**：契约加 D4-14 后同 entry 既有张 200。**Validates: 3.5**
- **Property 7（materialize ≤120s）**：加 D4-14 后 rematerialize 不抛 SoftTimeout。**Validates: 4.3**

### 变异反证（≥4 锚点四态 RED）
1. 把某 HTML-only 物理列（如 B 客户名称）改成受管 field → 守卫应挡（不丢/不越权受管断言 RED）。
2. 去嵌套 json_pointer（改平铺）→ 往返 RED。
3. formula_mask 去掉 G37 → 合计列被当录入回写 RED。
4. 契约去 d4-14-managed → parse RED。

## 部署与回滚
- Phase 0 裁决表独立 commit（审计业务复核签署留痕）。
- provider/契约改动经 generate --apply + assert_contract_file_matches_source OK 后才发布。
- 产物全 git add，收口后无 `??`（HEAD 断裂教训）。
- 若裁决为 C（single_html），Phase 1+ 不执行，spec 收口为裁决记录，不假装受管。
