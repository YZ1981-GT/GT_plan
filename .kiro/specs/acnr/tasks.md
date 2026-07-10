# Implementation Plan: ACNR 地址坐标名称注册中心

## Overview

本实施计划按里程碑（M0 → M1 → M2 → M3）组织，与 design.md 的「Milestone mapping」一一对应。每个任务都是可由编码代理执行的具体编码活动（写/改代码、测试、schema、fixtures、CI 脚本），并按依赖顺序排列——后序任务只依赖前序任务，最终收口于消费者接线。

技术栈遵循项目 steering：后端 Python 3.12 + FastAPI（迁移用 `migration_runner` 而非 alembic；事件走 `EventBus`，`publish` 只传 `EventPayload`；路由经 `router_registry` 注册；四表查询走 `get_active_filter`），前端 Vue3 + TypeScript + Element Plus。PBT 用 hypothesis（`max_examples=5~15`），每个属性一个测试并打标 `# Feature: acnr, Property {n}: {text}`。标 `*` 的子任务为可选（测试类），但按项目约定也会执行完成。

约定路径前缀：后端服务 `backend/app/services/acnr/`、生成器 `backend/scripts/acnr/`、数据 `backend/data/acnr/`、路由 `backend/app/routers/acnr.py`、文档 `docs/acnr/`、前端 SDK `audit-platform/frontend/src/services/acnr/`。

---

## Tasks

### 里程碑 M0 — Catalog + 只读 API + CI + 语法/规则冻结

- [x] 1. 冻结 L0 语法与六条核心规则
  - [x] 1.1 编写 `backend/data/acnr/grammar_v1.json`
    - 收录五域 URI profile：standard（`wp://{parent}/{sheet_name}#{cell}`，WP 三参）与 custom_flat（`wp://{wp_code}/{cell}`，WP 二参），并保持 tb/report/note/aux 既有语法不变
    - 写入 `WP()`/`PREV()` 的 2 参与 3 参 arity 元数与互转规则（`arities:[2,3]`、`third_arg`、`roundtrip:true`）
    - 写入恰好 11 个索引命名空间（`wp/sheet/cell/Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm`）+ Layer 1-4 到 addr_id/五域 URI 的双向映射表，外部模块标 `exists=true`、内部命名空间不标
    - 定义单一常量 `STANDARD_WP_CODE_RE = "^[A-S]\\d"`
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.4, 11.1, 12.1, 20.1_
  - [x]* 1.2 编写 grammar 索引命名空间映射完备性属性测试
    - **Property 11: 索引命名空间映射完备且限定**
    - **Validates: Requirements 11.1, 11.4, 11.5, 13.4**
  - [x] 1.3 编写六条规则冻结文档 `docs/acnr/rules-freeze.md`
    - 归档 R-URI / R-ADDR / R-WP / R-NAME / R-ROUTE / R-ENTRY 六条规则与 bulk §8.6、A-Q、N-Q 决议
    - _Requirements: 20.1, 20.2, 20.3_

- [x] 2. Catalog JSON Schema
  - [x] 2.1 编写 `docs/acnr/schemas/global_catalog.schema.json`
    - 定义 SheetCatalogEntry / CellCatalogEntry 结构与 addr_id pattern；顶层与两类条目均加 `not.required: [project_id, wp_id]`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 20.1_
  - [x]* 2.2 编写 L1 层次身份纯净性属性测试
    - **Property 10: L1 层次身份纯净性（domain 均 wp、无 runtime_only、无 project_id/wp_id、L4 边端点均为合法 addr_id）**
    - **Validates: Requirements 6.4, 7.1, 17.2, 22.2, 24.2**

- [x] 3. 生成器管线与数据源
  - [x] 3.1 手写 `backend/data/acnr/sources/d_cycle_ie_manifest.yaml`
    - 从现有 `d*_import_export.py` 逐 sheet 手工整理 import_export 段（api_prefix / item_id / storage_field / import_order / depends_on_sheets），**不做 AST 自动扫描**
    - _Requirements: 1.2, 18.6_
  - [x] 3.2 实现 loaders（`backend/app/services/acnr/loaders/`）
    - `from_classification.py`（→ SheetCatalogEntry 骨架）、`from_ie_manifest.py`（读 yaml → import_export）、`from_address_seeds.py`（13 种子 → CellCatalogEntry）、`from_frontend_labels.py`（14 份 `*SheetLabels.ts` → sheet_name_aliases）、`from_render_registry.py`（component_type + upstream/downstream 第 6 L4 边源）
    - _Requirements: 1.1, 1.3, 3.2, 4.1, 4.3, 22.4_
  - [x] 3.3 实现 `backend/scripts/acnr/generate_catalog.py` 主管线与合并规则
    - 合并 6 类输入为 SheetCatalogEntry/CellCatalogEntry；确定性输出（同输入字节一致）
    - `skip_reason` 非空时写入条目并**完全阻止本次 bulk manifest 生成**；别名一对多冲突在合并前标缺口并阻断该别名进入 catalog（阻断优先于缺口标记）
    - 产出 `catalog_report.json`（冲突/缺口/未登记别名）
    - _Requirements: 1.3, 1.4, 3.3, 3.4, 3.5, 18.1_
  - [x] 3.4 生成 `backend/data/acnr/global_catalog.json`（+ 可选 `shards/catalog_D.json`）
    - 全循环 SheetCatalogEntry 骨架（100% 覆盖 classification）+ D 循环 import_export 与坐标种子详情；写入 `registry_version`
    - _Requirements: 1.1, 1.2, 1.5, 4.1, 22.1_
  - [x]* 3.5 编写别名反查唯一性与冲突阻断属性测试
    - **Property 6: 别名反查唯一性与冲突阻断**
    - **Validates: Requirements 3.1, 3.3, 3.5**
  - [x]* 3.6 编写 addr_id 全局唯一属性测试
    - **Property 1: addr_id 全局唯一且每物理格唯一**
    - **Validates: Requirements 8.5, 18.4, 24.4**
  - [x]* 3.7 编写 canonical addr_id 构造一致属性测试
    - **Property 2: canonical addr_id 与 formula_ref 构造一致**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.6, 16.2**
  - [x]* 3.8 编写生成器确定性属性测试
    - **Property 7: 生成器确定性（drift=0）与骨架覆盖**
    - **Validates: Requirements 18.3, 1.1**
  - [x]* 3.9 编写 skip_reason 阻断整册 manifest 属性测试
    - **Property 12: skip_reason 阻断整册 manifest**
    - **Validates: Requirements 1.4**

- [x] 4. 只读 lookup / resolve API
  - [x] 4.1 编写 `docs/acnr/fixtures/resolve_cases.json`（RC-01..RC-12）
    - 表驱动金样例：lookup 正向/别名反查、resolve 多语法同 addr_id、resolve_instance、custom_flat、tb 域委托、miss+candidates、索引 `cell:`/`TB:` 殊途同归
    - _Requirements: 2.1, 2.3, 2.4, 5.3_
  - [x] 4.2 实现 `backend/app/routers/acnr.py` 只读 `lookup`/`resolve`（读 `global_catalog.json`）并经 `router_registry` 注册
    - `catalog.py` 提供 `list_sheets`/`list_cells`/`lookup`/别名反查；resolve 首期只读 L1，命中返回统一响应契约，miss 返回 `found:false`+≤5 candidates，多命中返回 `error:"ambiguous"`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.3, 5.6_
  - [ ]* 4.3 编写 lookup/resolve 响应契约单元测试（表驱动 RC-01..RC-12 只读子集）
    - 覆盖正向命中、别名反查、miss candidates ≤5、ambiguous 候选完整
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 5. CI 守卫与治理文档
  - [x] 5.1 实现 `check-acnr-catalog-drift`（`generate_catalog.py && git diff --exit-code`）并接入 CI workflow
    - _Requirements: 18.3_
  - [x] 5.2 实现 `check-addr-id-unique`（全局 addr_id 无重复，含历史遗留）
    - _Requirements: 18.4, 24.4_
  - [x] 5.3 实现 `check-ie-catalog-sync`（`d_cycle_ie_manifest.yaml` 与 catalog `import_export` 一致，首期 D）
    - _Requirements: 18.5_
  - [x] 5.4 实现 `check-standard-wp-code-re-single`（grep-ban 阻断新增 `[A-I]\d`/`[A-S]\d` 副本）
    - _Requirements: 12.3_
  - [x] 5.5 编写 `docs/acnr/CONTRIBUTING.md` 双入口流程（生成器 / overrides）
    - _Requirements: 18.1, 18.2_

- [x] 6. Checkpoint（M0）
  - Ensure all tests pass, ask the user if questions arise.

---

### 里程碑 M1 — 运行时接线 + 语法实现 + resolve_instance + 失效收口 + 端点统一

- [x] 7. `formula_grammar.py` WP/PREV 2+3 参与无损往返
  - [x] 7.1 在 `formula_grammar.py` 实现 `WP()`/`PREV()` 的 2 参与 3 参解析（具备实际解析能力方可标完成）
    - _Requirements: 10.2, 10.5_
  - [x] 7.2 修复 `formula_ref_to_uri()` 保留第三参（语义名不丢弃），并接入 `grammar.py` 互转
    - _Requirements: 10.3_
  - [x]* 7.3 编写 formula_ref ↔ uri 无损往返属性测试
    - **Property 5: formula_ref ↔ uri 无损往返（含 2/3 参 WP/PREV 及五域）**
    - **Validates: Requirements 10.2, 10.3**
  - [x]* 7.4 编写 URI profile 往返属性测试
    - **Property 3: URI profile 往返保持（standard/custom_flat）**
    - **Validates: Requirements 9.1, 9.2, 9.4, 9.5**

- [x] 8. STANDARD_WP_CODE_RE 单一常量共享
  - [x] 8.1 让 `wp_render_config.py` 与 `wp_index_resolve.py` 从 grammar_v1 import `STANDARD_WP_CODE_RE`，删除各自 `[A-I]\d`/`[A-S]\d` 副本
    - _Requirements: 12.2_
  - [x]* 8.2 编写标准码判定收敛属性测试
    - **Property 9: 标准码判定收敛（J1/S3 判为标准，[A-I]\d 误判消除）**
    - **Validates: Requirements 12.4, 12.5**

- [x] 9. 运行时接线（种子进选址器 + 自定义登记）
  - [x] 9.1 改造 `build_workpaper_entries()` 合并来自 catalog 的 Cell 条目
    - 使 D 循环 473 种子坐标在公式选址器可被搜索到；坐标登记即可被 `resolve()` 搜索，不依赖 `build_workpaper_entries()` 执行状态
    - _Requirements: 4.2, 4.5_
  - [x] 9.2 实现 `runtime.py` 的 `register_custom()` 登记 RuntimeCellEntry（保存后 parsed_data 提交调用）
    - 校验 `project_id` + wp 归属；自定义 addr_id 仅存 L2/L3 不落全局 L1
    - _Requirements: 23.3, 24.1, 24.2_
  - [x]* 9.3 编写自定义写入项目归属校验属性测试
    - **Property 13: 自定义写入项目归属校验（防 IDOR）**
    - **Validates: Requirements 24.1**

- [x] 10. resolve_instance + ProjectOverlay + Resolver 决策树
  - [x] 10.1 实现 `resolve_instance(project_id, parent_wp_code, sheet_code)` + ProjectBinding（运行时查 `WpIndex`）
    - 唯一 wp_id 出口；返回 jump_route 模板 + 已填充 wp_id；多实例返回 disambiguation，除非显式传 wp_id
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 10.2 实现 `overlay.py` L2 补丁应用 + 归属校验
    - 带 project_id 时在 L1 命中前先应用 overlay；即使最终 ambiguous 仍先应用 overlay
    - _Requirements: 5.2, 5.8, 24.1_
  - [x] 10.3 实现 `resolver.py` 完整决策树（L2 overlay → L1 Cell 精确 → L1 Sheet+aliases → semantic_label 包含 → L3 Runtime → 非 wp 域委托 V1 → miss 推荐）
    - 命中带 project context 附 wp_id；非 wp 域经同一出口委托 V1 返回统一契约；miss 记指标
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [x]* 10.4 编写多语法一致性解析属性测试
    - **Property 4: 多语法一致性解析（同格殊途同归，含索引/公式/uri/tb 域委托）**
    - **Validates: Requirements 5.1, 5.3, 5.7, 11.2, 11.3, 14.4, 16.4, 22.3, 22.5**
  - [x]* 10.5 编写未命中/ambiguous 响应契约属性测试
    - **Property 8: 未命中响应契约与 ambiguous（含 resolve_instance 多实例）**
    - **Validates: Requirements 2.3, 2.4, 5.5, 5.6**
  - [x]* 10.6 编写非法引用编译期失败属性测试
    - **Property 15: 非法引用编译期失败（resolve 校验总返回失败且不入库）**
    - **Validates: Requirements 14.2**

- [x] 11. 端点统一与转发 + addr_id 不可变
  - [x] 11.1 实现 v1/v2 转发 + 三个 legacy index-resolve 端点转发至统一 resolve 出口
    - `/api/wp-index-resolve`、`/api/workpapers/render-registry/{wp_code}`、`/api/workpapers/index-resolve/{wpCode}` 转发；一次查询返回 exists/trimmed/reason；转发失败返回错误**不回退**旧逻辑
    - _Requirements: 13.1, 13.2, 13.4, 13.5_
  - [x] 11.2 实现 addr_id 不可变政策 + `registry_version` 处理
    - 禁改已有 addr_id（改名走 aliases）；弃用标 `deprecated:true` 保留 ≥1 版；归档项目记录 registry_version
    - _Requirements: 19.1, 19.2, 19.3, 19.4_
  - [x]* 11.3 编写 addr_id 不可变与版本确定性属性测试
    - **Property 14: addr_id 不可变与版本确定性（重命名不断边、版本锁定确定）**
    - **Validates: Requirements 14.3, 19.1, 19.2, 19.5**

- [x] 12. 缓存失效收口 + catalog 降级
  - [x] 12.1 在 `WorkpaperSaveOrchestrator.after_save` 统一调用 ACNR `invalidate`（按 trigger/extra.sheets 增量），并删除各 router 级重复 `touch_wp_registry`
    - `invalidate` 由 `WORKPAPER_SAVED` 触发，`publish` 只传 `EventPayload`
    - _Requirements: 23.1, 23.2_
  - [x] 12.2 实现 catalog 加载失败降级（两分支）
    - 有旧缓存：只读上一版 + 管理端告警，禁止静默退回分散 JSON；无旧缓存：操作整体失败要求人工介入
    - _Requirements: 23.4, 23.5_

- [x] 13. CCR 自检（报告模式）
  - [x] 13.1 实现 `check-ccr-resolve`（M1 报告模式）
    - 校验每条 CCR source 可 resolve 或已标 `semantic_only`，产出缺口清单不阻断 PR；L4 边端点 normalize 为 addr_id
    - _Requirements: 17.1, 17.2_

- [x] 14. Checkpoint（M1）
  - Ensure all tests pass, ask the user if questions arise.

---

### 里程碑 M2 — bulk 试点 + 消费者切换 + 披露工厂

- [x] 15. bulk manifest
  - [x] 15.1 实现 `manifest.py` 的 `list_import_export(project_id, cycle?)` + D 循环 bulk manifest 生成
    - I/E 路由只认 catalog 的 api_prefix + item_id
    - _Requirements: 18.6_

- [x] 16. 高级查询库回写 addr_id
  - [x] 16.1 改造 `snapshot_writer` 回写 `addr_id`，快照列元数据挂载 addr_id
    - 回写解析携带 project context
    - _Requirements: 15.1, 15.2, 15.4_

- [ ] 17. 消费者切换（公式库 / 索引库）
  - [ ] 17.1 实现前端 SDK `useAcnr.ts` + 公式选址器（`list_sheets`/`list_cells` 构建下拉树）+ 保存前 `resolve()` 校验
    - 非法引用编译期返回失败
    - _Requirements: 14.1, 14.2, 15.3_
  - [ ] 17.2 改造 `GtIndexChip` 调 `resolve(ns:target)` 获取 addr_id + jump_route（不自行 parse）
    - _Requirements: 11.2, 11.3, 13.3_
  - [x] 17.3 改造 `FormulaReverseIndex` 边端点使用 addr_id（重命名 sheet 边不断裂）
    - _Requirements: 14.3_

- [ ] 18. 附注披露工厂
  - [ ] 18.1 实现 `useDisclosureSection(cycle, options)` 工厂替换 ≥3 份 `useXDisclosureSoe`
    - 登记 note 子域坐标 `note/{note_code}/{row_key}`；`disclosure:note-text-updated` payload 携带 addr_id；审定表/明细表取数经 `resolve()`
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 19. labels 生成与守卫
  - [x] 19.1 生成 `audit-platform/frontend/src/generated/dSheetLabels.ts` + 实现 `check-sheet-labels-generated` CI（禁手改）
    - _Requirements: 3.2, 18.1_

- [ ] 20. Checkpoint（M2）
  - Ensure all tests pass, ask the user if questions arise.

---

### 里程碑 M3 — 扩展 + 治理

- [ ] 21. CCR blocking 迁移
  - [ ] 21.1 CCR 边端点 addr_id normalize + `check-ccr-resolve` 转 blocking 模式
    - blocking 级 CCR 100% resolve，存在未 resolve 则阻断 PR
    - _Requirements: 17.2, 17.3_

- [ ] 22. 治理与扩循环
  - [ ] 22.1 实现 `registry_version` 项目锁定解析（归档项目按锁定版本解析）
    - _Requirements: 19.4, 19.5_
  - [ ] 22.2 实现 `/api/acnr/coverage` 覆盖度报表端点
    - 标记 `semantic_only=true` 需补 A1 的条目
    - _Requirements: 4.4, 4.6_
  - [ ] 22.3 扩展 bulk manifest 到 K/F/G/H 循环（波 2）
    - _Requirements: 1.1, 18.6, 22.1_

- [ ] 23. Final Checkpoint（M3）
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- 标 `*` 的子任务为可选（测试类：PBT / 单元 / 集成），按项目约定仍会执行完成。
- 每个任务引用具体子需求（`_Requirements: X.Y_`），验证正确性属性的测试任务额外标注 `Property n`，确保可追溯。
- Checkpoint 在里程碑边界做增量验证。
- 15 条正确性属性 P1–P15 均由一个 property-based 测试覆盖：P1(3.6)、P2(3.7)、P3(7.4)、P4(10.4)、P5(7.3)、P6(3.5)、P7(3.8)、P8(10.5)、P9(8.2)、P10(2.2)、P11(1.2)、P12(3.9)、P13(9.3)、P14(11.3)、P15(10.6)。
- 非 PBT 验收（orchestrator 失效收口、披露工厂 ≥3 循环、snapshot addr_id、规则冻结 / CONTRIBUTING / 三件套、五层引用铁律 grep 守卫）以单元 / 集成 / 静态守卫覆盖。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "2.1", "3.1", "5.5"] },
    { "id": 1, "tasks": ["3.2"] },
    { "id": 2, "tasks": ["3.3"] },
    { "id": 3, "tasks": ["3.4"] },
    { "id": 4, "tasks": ["4.1", "4.2", "5.1", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["1.2", "2.2", "3.5", "3.6", "3.7", "3.8", "3.9", "4.3"] },
    { "id": 6, "tasks": ["7.1", "8.1"] },
    { "id": 7, "tasks": ["7.2", "9.1", "9.2"] },
    { "id": 8, "tasks": ["7.3", "7.4", "8.2", "10.1", "10.2"] },
    { "id": 9, "tasks": ["10.3"] },
    { "id": 10, "tasks": ["11.1", "11.2", "12.1", "12.2", "13.1"] },
    { "id": 11, "tasks": ["9.3", "10.4", "10.5", "10.6", "11.3"] },
    { "id": 12, "tasks": ["15.1", "16.1", "17.3", "19.1"] },
    { "id": 13, "tasks": ["17.1", "17.2", "18.1"] },
    { "id": 14, "tasks": ["21.1", "22.1", "22.2", "22.3"] }
  ]
}
```
