# Implementation Plan — D4-12 转置双向回写

## Overview

把绑死 D4-29 的转置引擎泛化为 `TransposedSheetSpec` + 注册表分派（GENERALIZE 不回归 D4-29），再为 D4-12 建 provider、instrument 模板（注入 definedName + 隐藏载体行）、登记契约、跑发布链、接前端桥、守卫收口。

**分两大阶段**：先泛化引擎让 D4-29 零回归全绿（灰度，无 D4-12），再接 D4-12。此顺序使「泛化」与「D4-29 不回归」可独立验证，回归风险最高的 Task 4（D4-29 零回归）是接 D4-12 的前置门。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "几何核定与判据先行", "tasks": ["1", "2"], "parallel": true },
    { "wave": 2, "name": "泛化转置引擎（薄壳化 D4-29）", "tasks": ["3"], "depends_on": [1] },
    { "wave": 3, "name": "注册表 + adapter 4 处旁路遍历分派", "tasks": ["4"], "depends_on": [3] },
    { "wave": 4, "name": "D4-29 零回归门（接 D4-12 前置）", "tasks": ["5"], "depends_on": [4] },
    { "wave": 5, "name": "D4-12 provider + instrumentation + 契约", "tasks": ["6", "7", "8"], "depends_on": [5] },
    { "wave": 6, "name": "发布链", "tasks": ["9"], "depends_on": [6, 7, 8] },
    { "wave": 7, "name": "前端接桥 + 宿主登记", "tasks": ["10", "11"], "depends_on": [8] },
    { "wave": 8, "name": "守卫、变异、消费侧、e2e", "tasks": ["12", "13", "14"], "depends_on": [9, 10, 11] },
    { "wave": 9, "name": "清册同步与收口", "tasks": ["15"], "depends_on": [12, 13, 14] }
  ],
  "blocking": {
    "3": "引擎未泛化不得改 adapter 分派",
    "5": "D4-29 零回归未全绿不得接 D4-12（回归风险最高）",
    "7": "载体行几何未 census 定死不得注入",
    "9": "rematerialize 抛 SoftTimeout/Roundtrip 即未落地"
  }
}
```

## Tasks

- [x] 1. 几何核定与 mapping_digest 冻结
  - openpyxl 直读源模板 `D/D4-12 营业收入-合同检查（Leap-常规程序）.xlsx`，冻结转置几何：header R10、合同列 B–K（10 列）、21 字段↔R11–R31 有序映射、footer R32/R36、static_prompt R38；**census 确定 identity_carrier_row**（R9 是否被审计过程文本占用；若占用则裁定 insert 隐藏行 + 几何下移方案）。产出 `evidence/d412-geometry.json` + 21 字段↔前端 `ContractInspectionItem` key 逐项对齐表。
  - 判据：几何与前端 21 字段逐项对齐；载体行位置有明确裁决（不覆盖已有内容）。
  - _Requirements: 1.1, 3.1, DEC-4, DEC-5_

- [x] 2. `TransposedSheetSpec` 契约结构守卫（先写测试）
  - 新增 `test_transposed_registry.py`：断言 spec 数据类字段齐全 + `resolve_transposed_specs` 分派语义（命中/未命中/多命中）。此时通用引擎未建，测试先红（TDD 锚）。
  - _Requirements: 1.1, 1.2_

- [x] 3. 泛化转置引擎 `phase5_transposed_sheet.py`（薄壳化 D4-29）
  - 新增 `TransposedSheetSpec` dataclass（全部几何/身份字段）+ 把 D4-29 的 `materialize_transposed_workbook`/`extract_transposed_workbook`/`build_store_projection`/`merge_projection_into_store`/`sheet_payload`/`resolve_managed_sheet`/`_copy_column` 搬进来，所有硬编码常量改读 `spec` 字段。
  - `phase5_d4_29_customer_detail.py` 改薄壳：`SPEC_D429 = TransposedSheetSpec(...)` + 保留既有导出名（`is_enabled`/`materialize_file`/`extract_file`/`materialize_transposed_workbook`/`extract_transposed_workbook`/`assert_mapping_digest` 等）委托通用引擎 + SPEC_D429。
  - 判据：`phase5_d4_29_customer_detail` 既有符号 import 零改动即可用；D4-29 `assert_mapping_digest()` 不漂移。
  - _Requirements: 1.1_

- [x] 4. 注册表 + adapter 4 处旁路遍历分派
  - 新增 `transposed_registry.py`：`REGISTRY=[SPEC_D429]`（此阶段仅 D4-29）+ `resolve_transposed_specs(contract)`；`is_enabled(contract)` 保留为 `bool(resolve_transposed_specs(contract))`。
  - `adapters/excel.py` 4 处旁路（materialize 单/多 binding、extract、verify_unmanaged_regions）从 `if is_enabled: 调 D4-29 专属` 改为 `for spec in resolve_transposed_specs(contract): 调通用引擎(spec, ...)`；verify before 副本重投影按 spec 逐张（多转置 sheet 时链式叠加）。
  - 判据：改动 diff 仅「单例 → 遍历」，不改算法本体。
  - _Requirements: 1.2, 1.3_

- [x] 5. 【前置门】D4-29 零回归全面复核（接 D4-12 前，回归风险最高）
  - D4-29 materialize 产物 sha256 逐字节 == 泛化前（Property 1）；extract 反读逐字段 == 泛化前；`EXPECTED_MAPPING_DIGEST`(D4-29) 逐字符不变；既有 D4-29 守卫/生产 roundtrip 全绿；变异反证（把注册表改回写死 D4-29 单例仍应绿，证明纯灰度）。
  - 判据：D4-29 辐射面测试全绿 + 逐字节等价实证。**未全绿不得进 Task 6。**
  - _Requirements: 1.4, 1.5_

- [x] 6. D4-12 provider `phase5_d4_12_contract.py`
  - `SPEC_D412 = TransposedSheetSpec(managed_sheet=合同检查表D4-12, sheet_key=d4-12-managed, table_key=contract_inspection_transposed, template_id=D412, store_item_id=D4-12-contracts-v2, header_row=10, first_entity_column=B, initial_entity_column=K, identity_carrier_row=<Task1 裁决>, identity_carrier_prefix=GT-CONTRACT-, field_rows=<21 条 R11–R31>, footer_rows=(32,36), static_prompt_first_row=38, defined_name=GT_MANAGED_REGION_D412, managed_ref=$B$10:$K$31, identity_key=id)` + 契约装配 helper + mapping_digest 冻结。
  - 判据：`build_store_projection(spec=SPEC_D412)` stable_key=`contract_inspection_transposed/{id}/{field}`；隔离 probe materialize→extract 21 字段往返绿。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.4a_

- [x] 7. instrumentation 注入 D4-12 definedName + 隐藏载体行
  - 按 Task 1 裁决的 carrier 行，注入 workbook-scope `GT_MANAGED_REGION_D412=$B$10:$K$31`（无 localSheetId、RANGE）+ 隐藏载体行逐合同列写 `GT-CONTRACT-{id}` + locked；复用泛化后 `resolve_managed_sheet(spec=SPEC_D412)` 自检注入产物。
  - 判据：注入后 openpyxl 认出唯一 workbook-scope definedName、载体行 hidden；触发 Tier-A 保鲜门则刷 gate digest 重跑。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 8. 契约集成 + 注册 D4-12
  - `transposed_registry.REGISTRY` 加 `SPEC_D412`；`phase5_d4_revenue_detail.py` 装配 D4-12（instrumentation_specs / sheet_payload / sibling store `D4-12-contracts-v2` / digest 断言，只加不动既有张）；`generate_phase5_d4_contract.py --apply` 落盘，`assert_contract_file_matches_source` OK，契约 sheet 32→33。
  - 判据：`parse_contract` 含 d4-12-managed（layout 转置 + 21 field transposed_row + protected_regions）；同 entry 既有张 digest 不回归。
  - _Requirements: 3.5, 3.6_

- [x] 9. 发布链（provision + rematerialize，live PG）
  - `generate --apply` → `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d4-operating-revenue` → `d43_rematerialize --apply`；判据查库：新 bundle 含 d4-12-managed、entry current bundle=desired、gen++、无 Roundtrip/FooterAnchorDrift、soft_limit 120 不提高不抛 SoftTimeout；真栈 store-projection 200 含 D4-12 字段。
  - ✅ 已落地（2026-09-20，live PG audit-postgres）：provision created bundle57/contract/instrumentation；rematerialize gen82→83，current bundle `2a8db8076`==desired（含 d4-12-managed），`--check`=already_on_desired_bundle，无 Roundtrip/FooterAnchor/SoftTimeout（`evidence/d412-publish-chain.json`）。途中修复 pre-existing bug `_read_store_map` dict-store 默认值。`~` store-projection 200 端点抓包需全栈，标 UNVERIFIABLE（往返正确性由 Task12 单测 + 本发布链真 PG 无 Roundtrip 保证）。
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 10. 前端 D4-12 接桥（参照 D4-29 `D4TabCustomerDetail.vue`）
  - `D4TabContract.vue` 在线编辑模式从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge`（entry=xlsx/gt-d4-operating-revenue, sheetKey=d4-12-managed, capabilityForEntry）+ `WorkpaperSyncEditorHost` + flushHtml（先 flushPendingSave 再 readStoreProjection）+ 同步态三态中文 tag；行身份 id 安全校验（不含 `/~{}`、CRUD 保证唯一，不改现有 id 生成规则）；OCR/AI/导入导出/卡片能力保留不回归。
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6_

- [x] 11. 宿主登记 D4-12
  - `GtD4OperatingRevenue.vue` `isD4DedicatedSyncSheet` 加 'D4-12'（子组件自管切换器，宿主不叠加 legacy）。
  - _Requirements: 5.3_

- [x] 12. 后端守卫 + 变异
  - `test_d4_12_contract.py`（契约 parse 含 d4-12-managed）+ `test_d4_12_transposed_roundtrip.py`（21 字段 × N 合同 materialize→extract 逐字段、空值/占位空列跳过/扩列、首列 B、载体行 hidden 强校验、公式格拒绝）；变异 `mutate_d4_12_transposed_guards.py`（≥4 锚点四态 RED：泛化改回 D4-29 单例 / first_column 改 C / 去 carrier hidden / 契约去 d4-12-managed），每条变异 D4-29 回归须绿。
  - _Requirements: 6.1, 6.3, 6.4, Property 1/2/3/4/7_

- [x] 13. OO→HTML 消费侧（第四维）
  - `test_d4_12_mirror_consume.py`：`oo_to_html` mirror 对 `D4-12-contracts-v2`（list base）正确消费、applied>0 不抹 HTML-only、不静默投空；对齐 `test_d4_mirror_shape_invariants.py` 判据面（转置 store item ∈ 消费集合）。
  - _Requirements: 6.2, Property 5_

- [x] 14. 前端守卫 + 真栈 e2e
  - `d4ContractSyncHostWiring.spec.ts`：D4-12 接桥字面量 entry_id/sheetKey、宿主 `isD4DedicatedSyncSheet` 含 'D4-12'、fail-visible、双模式切换器不与宿主叠加；变异（删宿主 'D4-12' → dedicated 断言 RED）。
  - e2e：env 可用则产 `evidence/d4-bidirectional-acceptance/D4-12.json`（L1 统一路径 + L2 转置往返）；env 不可用标 `[~] UNVERIFIABLE` 不假绿（转置往返正确性由 Task 12 单测 + Task 9 真 PG 无 Roundtrip 保证）。
  - ✅ 已落地（2026-09-20）：`d4ContractSyncHostWiring.spec.ts` 10 passed（接桥字面量/flushHtml 顺序/WorkpaperSyncEditorHost 无 GtOnlyOffice/三态 tag/OCR+AI+导入导出+CRUD 不回归/宿主 dedicated 含 D4-12）。`[~]` e2e：`evidence/d4-bidirectional-acceptance/D4-12.json` 标 status=UNVERIFIABLE（真 OO canvas 非 DOM，不伪造 REQUEST_PATH 抓包避免假绿），记 code_level_evidence。
  - _Requirements: 5.1, 6.5_

- [x] 15. 清册同步与三件套收口
  - `d4-bidirectional-writeback-inventory.md`：D4-12 从「⏸ 待专项 spec」转 ✅ 三维代码全绿（真 OO env 门），统计段 ✅ 32→33 / ⏸ 2→1、契约集合 32→33 张同步；泛化若解除 D4-14 转置轴阻塞则两边登记。spec 三件套结构校验（Property 整数、Validates X.Y、waves JSON 唯一）；行数门禁同步；全部正式产物无 `??`（provider + 泛化 + 契约 + 前端 + 守卫全 git add）。
  - _Requirements: 7.1, 7.2, 7.3_

## Notes

- **参照实现（唯一可照抄范式）**：`phase5_d4_29_customer_detail.py`（转置 provider）+ `D4TabCustomerDetail.vue`（D4-29 前端接桥，已走 sync host）+ `adapters/excel.py` 4 处 D4-29 旁路（泛化对象）。
- **GENERALIZE 铁律**（主控 §5.3 共享锁）：改 `adapters/excel.py` / `phase5_d4_29_customer_detail.py` 属双向内核共享文件，须泛化不回归 D4-29（逐字节 + mapping_digest + 变异守卫），Task 5 是硬前置门。
- **模板前置差异**：D4-29 definedName + 隐藏载体行是模板预置；D4-12 两者皆无须 instrument 注入（Task 7），源模板磁盘不手改。
- **诚实边界**：真 OO canvas 往返是 env 门（OO canvas 非 DOM，Playwright 无法可靠编辑单元格），同 D4 全组批次C 标准，标 `UNVERIFIABLE` 不假绿。
- **Windows 命令约定**：`python`（非 python3）；禁 `&&` 用 `;`；禁 `cd` 用 `cwd`；pytest 从仓库根跑；shell 命令加 `rtk` 前缀（计数以不带 rtk 的原始 pytest 为准）。
- **收尾纪律**：一次性探针脚本用完即删；spec 目录入库；push 前先 `git fetch`；协作走 PR 不直推 main。
