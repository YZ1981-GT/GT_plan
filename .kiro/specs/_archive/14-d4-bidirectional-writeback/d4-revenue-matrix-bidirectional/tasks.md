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

- [x] 5. provider 模块 + 契约 + 生成器
  - 新增 `backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py`（9 段结构，18 字段，12 个月走数组下标 json_path）
  - 新增 `backend/scripts/gen/generate_phase5_d4_contract.py`，`--apply` 生成 `backend/data/workpaper_sync_contracts/d4.revenue_detail.json`
  - `assert_contract_file_matches_source()` 双向锁死；`parse_contract` 必须接受数组下标 pointer
  - 🔴 新模块行数若超 800 行门：优先按 spec 决策抽共生件，不得直接改 whitelist
  - _Requirements: 1.1, 4.1_

- [x] 6. registry 两白名单 + wp_code 裁决
  - `registry.py`：`_ALLOWED_PROVIDER_MODULES` + `DELIVERED_PER_ENTRY_CONTRACTS` 各加 D4 条
  - `workpaper_sync_entry_wp_code_adjudication.json` 加 D4 条，wp_codes 以**真载荷落点**为准（实测 D4），带 store_payload_evidence
  - _Requirements: 3.1, 4.1_

- [x] 7. 发布链（有真载荷的非空首版）
  - Task 76 provisioner `--check` → `--apply`（记 bundle id）
  - `fix_projection_first_publication --check`：必须 10 stage 全过且 `row_keys` 非 0
  - `--apply` 产出 published representation（记 representation id / revision / projection_sha256）
  - 查库印证 representation 的 `definition_bundle_id` 与 Task 76 的 bundle 一致
  - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [x] 8. overlay + manifest 重生
  - overlay 加 D4 宿主 override（cap=bidirectional / adapter_id=d4.revenue_detail）
  - `approved_source_digest` 若变动：必须逐 mount 归因（mount 总数不变 + 唯一变动是本 spec 的宿主接线），带精确 review_basis
  - 重生 manifest 两件产物，核 capability=bidirectional + adapter_id
  - _Requirements: 4.1, 4.2_

- [x] 9. 宿主接线 + oo_to_html 分支
  - D4 宿主：仅 D4-2 走 `WorkpaperSyncEditorHost`，其余 40+ sheet 保留既有 dualMode
  - `useD4*FormData` 导出 flush（flushHtml 前 flush debounce）
  - `oo_to_html.py` 加 `elif adapter_id == "d4.revenue_detail"` 分支，数组形态写回
  - 真库 `attach_adapters` 必须返回 `('d4.revenue_detail',)`
  - 必须验证 D4-2 更新后的 store 被审定表/附注下游消费，且 `periodTotal` 仍由内部公式计算而非 projection 覆盖
  - Task 1 的 `mapping_digest` 未生成或漂移时阻塞本任务
  - _Requirements: 4.2, 4.3, 3.3_

- [x] 10. §9.6 真栈 e2e
  - 新增 `audit-platform/frontend/e2e/g5-1-d4-unified-path.spec.ts`
  - 等待判据用可观测状态（`data-bridge-state` / confirm-descriptor 200），OO 写 A 列 product（文本列），证据记 `activeSheet`
  - 四硬断言：confirm-descriptor 200 / cs_error=0 / store_mirrored / marker_visible；另断言 OO→store 后 D4-2 下游审定表/附注值按同一 row key 更新，且内部 `periodTotal` 公式未被覆盖
  - evidence 必须同时记录 store row key、activeSheet、下游消费值和公式保护结果
  - _Requirements: 4.4, 5.1, 5.2, 5.3, 5.4_

- [x] 11. DB 三谓词 + 收口
  - venv 只读查：application applied / `D4-2-rows` 含 marker 且 `months` 仍是数组 / content_version `source=onlyoffice` 且 op 逐字一致
  - runbook 追加 D4 小节（照 §8–§10 格式）
  - 清 tmp_*；`git status --porcelain` 核产物无 `??` 漏登记
  - _Requirements: 4.5, 3.5_

## Notes

Task 1 未冻结字段映射前不得假定字段数量；Task 2 必须通过共享解析器与真实 materialize/extract 链路。所有模板与 manifest digest 变化必须逐文件归因。

### 交付实态
- Task 1–4 / 5–11 ✅：provider+registry+发布+宿主+真栈证据见 `evidence/g5-1-d4-unified-path/`（application applied / adapter `d4.revenue_detail` / source=onlyoffice）。
- Task 12–13（公式治理总纲 / 正式 C4）：本轮价格侧已落地局部 WP preset+覆盖+未审合计对齐；D4-2 `periodTotal` 仍由表内公式/`formula_mask` 保护；平台级 F-SHELL/CAS 归属 `d4-dual-mode-formula-governance`。

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1","2","2.1","3"],"rationale":"C0/C1形态核定并行"},{"wave":2,"tasks":["4","5"],"rationale":"净化与provider依赖Wave1"},{"wave":3,"tasks":["6","7"],"rationale":"registry和发布依赖契约"},{"wave":4,"tasks":["8","9"],"rationale":"接线依赖发布"},{"wave":5,"tasks":["10","11","12","13"],"rationale":"C4验收与alignment最后"}],"blocking":{"2":"数组往返未通过不得发布","1":"mapping_digest漂移阻塞契约和发布"}}
```


## Common Contract Alignment Gate
- [x] 12. 对齐总纲 `d4-dual-mode-formula-governance`：ContentMutationService/useWorkpaperSyncBridge；不同字段自动合并、同字段冲突保留三方轨迹；durable ack不等于applied；公式key使用`wp_id`，禁止Excel优先、最后写胜出、eval和外链。
  - **本轮**：D4-2 走统一 sync bridge；表内 N 列 formula_mask；跨表 WP 取数（D4-10←D4-2 未审合计）经公式引擎 preset/override。平台 F-SHELL/CAS 仍由总纲 owner。
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 6.1_
- [~] 13. C4逐D4-2/3验收：source evidence、stable identity、formula mask、roundtrip、权限、Playwright及变异；公式同步不发布TB/A13，只门控本spec相关产物。
  - **本轮**：D4-2 真栈证据已在 `evidence/g5-1-d4-unified-path/`；D4-3 为兄弟表，正式 C4 矩阵仍随总纲推进。
  - _Requirements: 3.1, 3.2, 6.1_

---

## 2026-09-22 归档前状态刷新（append-only；上方复选框与原文一律不动）

> 上方 Task 13 的 `[~]` 理由原文是「D4-2 真栈证据已在 `evidence/g5-1-d4-unified-path/`；D4-3 为兄弟表，
> 正式 C4 矩阵仍随总纲推进」。本节把 D4-2/D4-3 的最终状态说清 —— 本 spec 是 **D4 全组唯一拿到
> 真 OO canvas → applied 完整 L2 证据**的 spec，值得显式记录。

**① D4-2 是 D4 全组唯一的完整 L2 样板（真 OO canvas → forcesave → callback → applied → store 镜像）**：
`evidence/g5-1-d4-unified-path/network-and-callback.json`（2026-09-21 刷新）——
`forcesave_cs_error=0`（权威判据，0=有变更；4=no_changes 不算）· `forcesave_http_status=202` ·
`confirm_descriptor_200=true` · `oo_cell_dirty_attempted=true` · `d2_sync_hits=0` ·
callbackUrl 五项键（`room_id`/`generation`/`doc_key`/`route_credential_id`/`route_token`）。
`evidence/g5-1-d4-unified-path/db-check.json` —— `operation.state=applied` ·
`application.state=applied`（`result_revision=12`, `adapter_id=d4.revenue_detail`）·
`content_version.source=onlyoffice` 且 `operation_id` 交叉一致 ·
`store_mirror.marker_in_store=true`（OO 里写的 marker 出现在 HTML store 的 `GTROW-D42-0012.product`，
`months` 仍是长度 12 的位置数组 ⇒ **DEC-D4-1「12 个月做 12 条独立 field」的往返等值在真栈成立**）。

**② D4-3 状态**：`docs/operations/evidence/d4-bidirectional-acceptance/D4-3.json`（2026-09-22）L1 全绿；
后端 `d43-managed` 受管链路由 `d-cycle-sheet-bidirectional-expansion` Tasks 1–5 做实
（`test_d43_production_roundtrip.py` 绿、contract digest `74804f74…`、bundle `0b7bb759…`）。
D4-3 自身的 L2 canvas 往返未单独跑。

**③ 残留归属**：C4 逐表验收矩阵按 entry 粒度归父 entry `xlsx/gt-d4-operating-revenue`，
移交总纲 `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 70 口径。

**④ 归档判定**：本 spec 自有产物全部就位，且是全组唯一有完整 L2 applied 证据的 spec ⇒ **可归档**。
