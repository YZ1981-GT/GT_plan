# Implementation Plan

## Overview

本任务集按 D4-2 位置数组验证、模板净化、发布链、宿主接线和真栈回写五条链路收口；Task 2 与 mapping_digest 均为硬阻塞门。

## Tasks

- [x] 1. 逐格核定 D4-2 受管区并冻结列↔字段映射
  - openpyxl 直读净化前模板，落 `主营业务收入明细表D4-2` 的表头行 / 数据区首末行 / footer marker 精确文本（含空格）/ A~V 每列语义
  - 与 `useD4RevenueDetail.ts` 的 `RevenueDetailRow` 逐字段对齐，确定契约字段的最终数量与列位（含 `prior_unadjusted` / `prior_adjustment` / `remark` 真实列），不得在核定前假定为 18 条
  - 输出带 `mapping_digest` 的映射清单到 spec evidence，作为后续所有任务的唯一真源；Task 5/6/7 必须校验该 digest
  - **完成**：`evidence/T01-column-field-mapping.json`；`mapping_digest=6d2f340d45ba0a24c95424c1e698be3df105252c160d174a2e4c748ec1554cc8`；几何 header=11 / data=12–23 / footer=24 marker=`合计`；契约 18 条（P/S/T/U 公式列进 mask 不进契约）
  - _Requirements: 3.3, 4.1_

- [x] 2. 位置数组往返等值先验证（阻塞门）
  - 新增 `backend/tests/workpaper_sync/test_d4_positional_array_roundtrip.py`
  - 测试必须调用真实 `parse_contract → build_excel_adapter → materialize → extract → merge_projection_into_store_rows` 链路；provider 私有 helper 只能作为辅助断言，不能单独解除阻塞
  - 实现或扩展共享数组路径解析：段为纯数字且游标是 list → 按 index；遵守统一 JSON Pointer token 规则
  - 最小 fixture（1 行 × 12 月）跑真实链路，断言 12 值逐个等值 + `months` 仍是 list
  - 覆盖越界（`/months/12`）、长度 ≠ 12、缺失/类型错误三类 fail-closed，并断言稳定错误码
  - 🔴 本任务不通过则 Task 4 起全部阻塞（Requirement 1.5）
  - **完成**：共享 `json_path.py`；阻塞门 6 passed（含生产链 roundtrip）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2.1 PBT：数组下标写入的最小改写面
  - hypothesis/fast-check 对任意 12 元数组 + 任意下标，断言仅目标位被改、长度不变、类型仍 list
  - **完成**：`TestPropertyMinimalWriteSurface` hypothesis 通过
  - _Requirements: 1.2_

- [x] 3. 270 个公式格分类清册（净化前置）
  - 逐 sheet 扫 `<f>`，按含/不含 `[n]` 分两类并计数，输出可复核清单（sheet → 公式格坐标 → 分类）
  - 单独确认 D4-2 的 N 列属「内部公式」类且必须保留
  - **完成**：`evidence/T03-formula-classification-census.json`；openpyxl 展开 external=270 / internal=951；N12:N23 全为 `=SUM(B:M)` 内部公式；重生脚本 `backend/scripts/diagnose/d4_wave1_census.py`
  - _Requirements: 2.1_

- [x] 4. 净化脚本 + 变异检验
  - 新增 `backend/scripts/fix/sanitize_d4_template_external_links.py`：删 17 外链部件/rels/Override/Relationship/`<externalReferences>`/含 `[n]` 的 defined name；公式只中和含 `[n]` 的 `<f>`
  - 判据：受管 sheet 逐格 0 diff + merge 不变 + **N 列公式文本不变** + 门 PASS
  - `--check` 预演通过后 `--apply`，留 `.preclean.bak`
  - 新增 `backend/scripts/diagnose/mutate_d4_sanitize_guards.py`，四态判定，GREEN 即守卫缺陷；变异必须覆盖坐标错位、内部公式误删、仅删 XML 不删 rels、受管格改动
  - 真 OOXML 门实测：净化后 PASS + `.bak` REJECT
  - **完成**：clean sha256=`b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f`；bak=`ecac5d56…`；变异 4/4 RED（`evidence/T04-sanitize-mutation-verdict.json`）；zip 元数据保留保证 sha 可复现
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 5. provider 模块 + 契约 + 生成器
  - 新增 `backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py`（9 段结构，18 字段，12 个月走数组下标 json_path）
  - 新增 `backend/scripts/gen/generate_phase5_d4_contract.py`，`--apply` 生成 `backend/data/workpaper_sync_contracts/d4.revenue_detail.json`
  - `assert_contract_file_matches_source()` 双向锁死；`parse_contract` 必须接受数组下标 pointer
  - 🔴 新模块行数若超 800 行门：优先按 spec 决策抽共生件，不得直接改 whitelist
  - _Requirements: 1.1, 4.1_

- [ ] 6. registry 两白名单 + wp_code 裁决
  - `registry.py`：`_ALLOWED_PROVIDER_MODULES` + `DELIVERED_PER_ENTRY_CONTRACTS` 各加 D4 条
  - `workpaper_sync_entry_wp_code_adjudication.json` 加 D4 条，wp_codes 以**真载荷落点**为准（实测 D4），带 store_payload_evidence
  - _Requirements: 3.1, 4.1_

- [ ] 7. 发布链（有真载荷的非空首版）
  - Task 76 provisioner `--check` → `--apply`（记 bundle id）
  - `fix_projection_first_publication --check`：必须 10 stage 全过且 `row_keys` 非 0
  - `--apply` 产出 published representation（记 representation id / revision / projection_sha256）
  - 查库印证 representation 的 `definition_bundle_id` 与 Task 76 的 bundle 一致
  - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [ ] 8. overlay + manifest 重生
  - overlay 加 D4 宿主 override（cap=bidirectional / adapter_id=d4.revenue_detail）
  - `approved_source_digest` 若变动：必须逐 mount 归因（mount 总数不变 + 唯一变动是本 spec 的宿主接线），带精确 review_basis
  - 重生 manifest 两件产物，核 capability=bidirectional + adapter_id
  - _Requirements: 4.1, 4.2_

- [ ] 9. 宿主接线 + oo_to_html 分支
  - D4 宿主：仅 D4-2 走 `WorkpaperSyncEditorHost`，其余 40+ sheet 保留既有 dualMode
  - `useD4*FormData` 导出 flush（flushHtml 前 flush debounce）
  - `oo_to_html.py` 加 `elif adapter_id == "d4.revenue_detail"` 分支，数组形态写回
  - 真库 `attach_adapters` 必须返回 `('d4.revenue_detail',)`
  - 必须验证 D4-2 更新后的 store 被审定表/附注下游消费，且 `periodTotal` 仍由内部公式计算而非 projection 覆盖
  - Task 1 的 `mapping_digest` 未生成或漂移时阻塞本任务
  - _Requirements: 4.2, 4.3, 3.3_

- [ ] 10. §9.6 真栈 e2e
  - 新增 `audit-platform/frontend/e2e/g5-1-d4-unified-path.spec.ts`
  - 等待判据用可观测状态（`data-bridge-state` / confirm-descriptor 200），OO 写 A 列 product（文本列），证据记 `activeSheet`
  - 四硬断言：confirm-descriptor 200 / cs_error=0 / store_mirrored / marker_visible；另断言 OO→store 后 D4-2 下游审定表/附注值按同一 row key 更新，且内部 `periodTotal` 公式未被覆盖
  - evidence 必须同时记录 store row key、activeSheet、下游消费值和公式保护结果
  - _Requirements: 4.4, 5.1, 5.2, 5.3, 5.4_

- [ ] 11. DB 三谓词 + 收口
  - venv 只读查：application applied / `D4-2-rows` 含 marker 且 `months` 仍是数组 / content_version `source=onlyoffice` 且 op 逐字一致
  - runbook 追加 D4 小节（照 §8–§10 格式）
  - 清 tmp_*；`git status --porcelain` 核产物无 `??` 漏登记
  - _Requirements: 4.5, 3.5_

## Notes

Task 1 未冻结字段映射前不得假定字段数量；Task 2 必须通过共享解析器与真实 materialize/extract 链路。所有模板与 manifest digest 变化必须逐文件归因。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "2.1", "3"], "rationale": "只读核定 + 形态先验证 + 公式分类，互不依赖，可并行；Task 2 是后续总闸" },
    { "wave": 2, "tasks": ["4", "5"], "rationale": "净化与 provider 模块都依赖 Wave 1 的映射清单与形态结论；模板 sha256 由 Task 4 产出后喂给 Task 5 的哨兵" },
    { "wave": 3, "tasks": ["6", "7"], "rationale": "登记与发布链依赖契约落盘（Task 5）与净化后模板（Task 4）" },
    { "wave": 4, "tasks": ["8", "9"], "rationale": "overlay/manifest 与宿主接线依赖已有 published representation（Task 7）" },
    { "wave": 5, "tasks": ["10", "11"], "rationale": "e2e 与 DB 三谓词是最终验证，依赖全链接通" }
  ],
  "blocking": {
    "2": "位置数组真实生产链往返未通过 ⇒ Wave 2 起全部阻塞（Requirement 1.5/1.6）",
    "1": "mapping_digest 未生成或与权威模板/DetailRow 漂移 ⇒ Task 5/6/7 阻塞",
    "external": "F-SHELL/既有 Phase 5 shared infra 契约或 approved bundle 发生漂移 ⇒ 先校验 producer digest，再允许 D4 发布"
  }
}
```
