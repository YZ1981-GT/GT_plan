# L7 其他非流动负债「真双向」改线 — 实现计划

> 任务：把 L7（其他非流动负债，科目 2801）从「仅 UI、后端全零」做到真双向闭环。
> 受管表已裁决 = **明细表 L7-2**（走方案 b），HTML 子组件 `l7/core/L7TabDetail.vue` 是其忠实渲染。
> 范式：L1~L4 已做过四遍；L7 比 L3/L2 多「HTML 行 key 换稳定 rowId」+「公式列 E/L/M/N/O 往返幸存」（后者同 L1/L4）。
> 严格对齐用户 7 步，禁臆造、禁扩范围、禁假绿、不 push、不建 worktree 外新长期分支。

## 0. 起始状态快照（git，调查时实测）

- **HEAD**（`git rev-parse HEAD`）：`1d8887d5ee982792a05026ebc0a08b6fe754ecca`
- **当前分支**：`work/2026-10-01-i-cycle-classification-convergence`
- **脏状态**（`git status --porcelain | Measure-Object -Line`）：**230 项**未提交改动 —— 全部是并发 K/J/N/I 会话产物，属正常。
- **铁律**：全程 **绝不** `git add -A` / `git add .`；只逐文件 add 本任务产物；绝不碰、绝不删并发会话改动与其临时文件（`_*.py` / `_*.txt`）。
- 本任务临时探针一律放 `backend/scripts/analyze/_l7p_*.py`（`_` 前缀=用完即删），交付前清理（已删调查用的 `_l7p_geom.py`）。

## L7-2 受管表几何（openpyxl 现算，调查时实测，provider 常量须据此冻结）

- 模板路径：`backend/wp_templates/L/L7 其他非流动负债.xlsx`
- **TEMPLATE_SHA256** = `9fe09748148a6f0692eef85e0c0cf3e24f22ea7e5d011c029dfa3e71bb04daea`（净化前原始值；若发布链触发净化须更新，见步骤 4）
- 受管 sheet = `明细表L7-2`；max_row=25、max_col=27(A..AA) ⇒ **UUID_COL = AB**（max_col+1）
- 两级表头：**R10（组标题）/ R11（叶子）**；数据区 **R12~R16（5 行）**；footer **R17**，标签在 **A17「合计」**（B17~O17 连续 `=SUM(..12:..16)`）
- footer 之下 R18「三、审计说明：」—— 不受管，`last_data_row=16`/`footer_row=17` 必须正确截断
- **公式列 5 个（逐行，mode=formula）**：`E==B+C-D`、`L==B+F+G`、`M==C+H+J`、`N==D+I+K`、`O==L+M-N`
- **受管表零裸 IF**；整册裸 IF 仅 `审定表L7-1` 6 格 ⇒ per-file 中性化照挂（同 L1/L4，`neutralize_oo_crash_if_formulas`）
- 18 个受管业务列 A..R 与 `L7DetailRow` 字段逐列对齐：
  A=itemName | B=beginUnadjusted | C=beginAje | D=beginRje | **E=beginAudited(公式)** | F=ajeIncrease | G=rjeIncrease | H=endAjeIncrease | I=endRjeDecrease | J=endAjeDecrease | K=endRjeIncrease | **L=endUnadjusted(公式)** | **M=endAje(公式)** | **N=endRje(公式)** | **O=endAudited(公式)** | P=nature | Q=reason | R=maturityInfo

## 关键设计决策（本模式无 design 文档，决策在此记录）

- **行身份字段名改 `key` → `rowId`**（对齐 L1/L3/L4 范式与契约 `/rows/*/rowId`）。理由：L7-2 HTML 现用 `L7DetailRow.key`（随机 ID），而 L1/L3/L4 provider 的 `ROW_IDENTITY_STORE_KEY` 全是 `rowId`、契约行身份 json_pointer 也要求 `rowId`；统一字段名避免 provider 用非标准键名。改动面小（`L7DetailRow.key`→`rowId`，addRow/removeRow/_restoreRowsFromResponses/_triggerSave 内 `r.key` 跟随），且 `useL7CrossSheet` 不读该字段（读 `L7-L7-2-*-end_balance` 键），风险低。
- **持久化通道不变**：仍是单 item JSON 数组 `L7-L7-2-full-data`（`_restoreRowsFromResponses` 优先读它）。`STORE_ITEM_ID = "L7-L7-2-full-data"`（对齐 HTML 实际写入键；L3 是 `L3-L3-9-voucher-rows`，L7 保持它既有的 full-data 键，不改 HTML 写入点）。
- **公式列 E/L/M/N/O 判 mode=formula**（同 L1 的 K/R/S/T/U、L4 的 R/S/AF..AM）；`FORMULA_TEMPLATES` 逐字记模板原式，往返须断言公式幸存（同 L4，不照抄 L3 的「零公式列」断言——那在非空 FORMULA_COLUMNS 上不成立）。
- **文件组织照 L3**：拆 `phase5_l7_sheets.py`（身份/几何/字段/SPEC）+ `phase5_l7_other_noncurrent_liabilities.py`（IDENTITY+SPECS+薄转发），避免单文件超 800 行门。
- **不重构工作流**：7 步严格顺序依赖、共享单一 worktree、带 digest 的 fail-closed 门需串行，拆分无收益。沿用既有 build-loop 按本计划实现；停止契约不变（build-loop 读 `review.json` 的 `verdict==APPROVED` 停）。

---

## 验证证据（2026-10-02 实跑，供评审读取）

- **第1步 vitest**：`npx vitest run useL7Detail.rowIdentity.spec.ts` → **5 passed**（新增行 rowId 唯一 / 删中间行其余 rowId 不变 / 缺 rowId hydrate 补铸 / updateRow 不动 rowId / newRowIdentity l72det 唯一性）。
- **第1/2步 vue-tsc**：单区域 `tsconfig._l7-dual-mode.json`（含 host + L7TabDetail + useL7Detail + rowIdentity + dualMode 依赖）本任务改动零新错；变异证明生效（`isProcedureSheet: number` 注入后报 TS2322，恢复后消失）；既有预存错误（host 第47/102 行 schema/sheetName、与 GtAProgramConsole/GtOnlyOfficeSheet 既有类型，非本任务引入）不变。
- **第3步 adapter 测试**：`pytest test_l7_adapter_registration.py` → **20 passed**（几何现算 UUID=AB/footer A17/5 公式列 E/L/M/N/O 逐行 / 契约 disk-source 锁 + formula_mask 5 段非空 + 5 formula 字段 / 五处登记 store+ledger+whitelist+裁决 + 配对不变式 L 白名单==ledger / HTML 对齐契约字段 ⊆ L7DetailRow + 稳定 minter / 真库 L7-L7-2-% 干净命名空间）。契约生成器 `--check` rc=0；裁决表预演新增 L7 一条（54→55）后 apply。
- **第4步五环发布**：task76 provision `--check` would_create_total=5、contract digest 06c004a7（净化前）；净化后重 provision would_create=4（authority 复用）、新 bundle 1c4b7950、template sha 9a50cfeb。first_publication `--apply` → representation_generation=1。**DB 三表闭环 SQL 实证**：entry_state has_current=t + representation_generation=1；representation fe8f97f8 绑 bundle 1c4b7950；bundle state=**approved** + template_slot_digest=9a50cfeb（与 provision 逐字一致）。
- **第4/6步模板净化**：真 OO 往返 materialize 对受管 sheet 横向共享公式组 `M12:N16`（si=0）抛 `excel_row_shift_shared_formula_orientation_unsupported`（横向共享组平移会每格算错，引擎 fail-closed）⇒ 新建 `sanitize_l7_template_external_links.py`（复用 L4 _unshare 内核），把受管 sheet 3 个共享组（M12:N16 横向 10 格 / O13:O16 纵向 4 格 / B17:O17 footer 横向 14 格 = 28 成员）展开为逐格显式公式。净化判据：受管 sheet openpyxl 逐格 **0 diff**（cells 84→84, merged_same=True）、shared 残留 **0**、step1 外链 stats 全 0（L7 无外链）、unshared=28 == 期望。sha 9fe09748→35e47cf9，PRE_SANITIZE_TEMPLATE_SHA256 保留；`.preclean.bak` 备份。净化在五环发布前执行（已回退旧 representation 重发）。
- **第5步 manifest 翻转**：干净 worktree `.worktrees/l7-flip`（基于 b117123b1 只叠加 L7 overlay override）重算 `approved_source_digest`=7ae8f4c7（旧 d648767136 为 L4 轮）；manifest digest 1cf5e739；mount-diff 零能力损失复核（完整 manifest build 对比 HEAD）：**唯一翻转 entry=L7**（capability single_onlyoffice→bidirectional、migration_state legacy_fake_bidirectional→adapter_registered、adapter_id None→l7.other_noncurrent_liabilities）、changed entry count=1、per-entry mount 1→2、stats.mount_count 246→247、host_count 154 不变、byComponent 仅 GtOnlyOfficeSheet 240→241、capability_counts bidirectional 16→17/single_onlyoffice 133→132，其它零变化；baseline 下游 diff 仅 L7+顶层 digest/stats。worktree manifest `--check` rc=0、task73 `test_task73_entry_profile_manifest.py` 在干净 worktree **46 passed 0 failed**。主树 `--check` FAIL（current 0fdfc3a0≠7ae8f4c7）归因并发会话未提交的其它 host mount churn（非本任务）；回拷产物与 worktree 逐字 sha256 一致。详见 `l7-flip-diff.md`。
- **第6步真 OO 往返**：`verify_l7_oo94_roundtrip.py` → **9 步全绿**：①attach=('l7.other_noncurrent_liabilities',) ②substrate 000000001-d70b3026（净化模板 representation）③projection 2 行==输入 ④materialize（净化后不再撞共享公式门）⑤OO ConvertService 真引擎 resave percent=100 ⑥G1 等值门 OK ⑦往返逐字段相等 2 行×14 键 rowId 稳定无幽灵行 ⑧OO 重存后受管行 [17,18] 的 E/L/M/N/O 五列公式 10 格全部仍是公式 ⑨L7 载荷 5 行不变（不写库）。err 日志仅 HTTP 文件服务正常访问，无被吞异常。
- **真浏览器 dev server（9980/3030）**：未起环境，**第2步 host procedureDualMode UI 代码已改但未在真浏览器实测**（如实标，待 start-dev.bat）；vue-tsc + vitest 已覆盖类型与行身份逻辑。

## 实现步骤（逐项可验证，按依赖排序）

- [x] 1. L7-2 HTML 行身份换稳定 rowId（字段 `key`→`rowId`，随机 ID→`newRowIdentity('l72det')`，缺时补铸）。
      改 `composables/useL7Detail.ts`：`L7DetailRow.key` 改名 `rowId`；`import { newRowIdentity } from './shared/rowIdentity'`；`addRow` 内 `key: l7-detail-${Date.now()}...` 改 `rowId: newRowIdentity('l72det')`；`_triggerSave`/`_triggerSaveAll` 的 rows 摘要里 `key: r.key` 改 `rowId: r.rowId`。
      改 `l7/core/L7TabDetail.vue`：`_restoreRowsFromResponses` fallback 分支 `key: r.key || 'l7-detail-...'` 改 `rowId: raw.rowId || newRowIdentity('l72det')`（照 L3 `useL3VoucherCheck.ts::normalizeRow` 的 `raw.rowId || newRowIdentity('l39vc')` 范式，已有 rowId 优先不重铸）；确认 full-data 恢复路径把 `rowId` 带回。
      Files: `audit-platform/frontend/src/components/workpaper/composables/useL7Detail.ts`、`audit-platform/frontend/src/components/workpaper/l7/core/L7TabDetail.vue`
      Verify: 新增 vitest `audit-platform/frontend/src/components/workpaper/composables/__tests__/useL7Detail.rowIdentity.spec.ts`（覆盖：新增两行 rowId 唯一；删中间行其余 rowId 不变=位置化反例；缺 rowId 的旧数据 hydrate 时补铸）→ 限定范围 `npx vitest run src/components/workpaper/composables/__tests__/useL7Detail.rowIdentity.spec.ts` 全绿；限定范围 vue-tsc（临时 `tsconfig` 只含改动的两个文件，配故意写错变异确认检查生效，参考 memory 铁律㉔的单区域 tsconfig 先例）通过。

- [x] 2. host `GtL7OtherNoncurrentLiabilities.vue` 补 procedureDualMode 模式切换器（照 L1/L3）。
      模板 `<template v-else>` 内 sheet 分发链**最前**加：`<div v-if="isProcedureSheet" class="l7-procedure-toolbar">` 内放 `<el-segmented :model-value="procedureDualMode.currentMode.value" :options="procedureDualMode.modeOptions.value" size="small" @change="procedureDualMode.onModeChange" />` + `<GtEntrySyncCapabilityNotice entry-id="xlsx/gt-l7-other-noncurrent-liabilities" />` + `<el-tag v-if="!procedureDualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>`；其后 OO 挂载块 `<GtOnlyOfficeSheet v-if="isProcedureSheet && procedureDualMode.currentMode.value === 'onlyoffice'" :wp-id :project-id :sheet-name="props.sheetName || 'L7A'" :readonly="isReadonly" style="height: calc(100vh - 180px)" />`。
      原 `L7TabIndex` 的 `v-if="currentSheet === 'L7'"` 改 `v-else-if`；程序表 `GtAProgramConsole v-else-if="currentSheet === 'L7A'"` 保留作 HTML 模式分支。
      script：`import { useCycleHtmlOoDualMode } from './composables/useCycleHtmlOoDualMode'`、`import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'`；加 `const isProcedureSheet = computed(() => currentSheet.value === 'L7A')` + `const procedureDualMode = useCycleHtmlOoDualMode({ wpId: toRef(props,'wpId') as any, storagePrefix: 'l7-proc:' })`。
      CSS：加 `.l7-procedure-toolbar`（照抄 L1：flex/gap 8px/align-items center/margin-bottom 8px/flex-wrap wrap）。host 补 toolbar 时同时挂 host 级 notice（与 L1 一致，两处都挂不冲突）。
      Files: `audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue`
      Verify: 限定范围 vue-tsc（临时 tsconfig 只含该 host）通过 + 变异证明（故意把 isProcedureSheet 写成 number 应报 TS2322）；`npx vitest run src/components/workpaper`（若有既有 L7 host 测试）不回归。

- [x] 3. 新建 provider + reviewed contract，并完成五处登记 + adapter 注册测试。
      新建 `backend/app/services/workpaper_sync/phase5_l7_sheets.py`（照 `phase5_l1_sheets.py`/`phase5_l3_sheets.py`）：常量 openpyxl 现算 —— `PHASE5_WAVE="l_cycle_other_noncurrent_liabilities"`、`ENTRY_ID="xlsx/gt-l7-other-noncurrent-liabilities"`、`ADAPTER_ID="l7.other_noncurrent_liabilities"`、`WP_CODES=frozenset({"L7O"})`（幻影码，须按步骤3实测 finder 零命中确认，否则改用真实现算值）、`MANAGED_SHEET="明细表L7-2"`、`TEMPLATE_RELATIVE_PATH="L/L7 其他非流动负债.xlsx"`、`TEMPLATE_SHA256="9fe0...daea"`（现算，若步骤4净化则更新）、`HEADER_GROUP_ROW=10`/`HEADER_LEAF_ROW=11`/`FIRST_DATA_ROW=12`/`LAST_DATA_ROW=16`/`FOOTER_ROW=17`、`MANAGED_LAST_COL="R"`、`UUID_COL="AB"`、`FOOTER_MARKER="合计"`、`footer_search_column="A"`、`STORE_ITEM_ID="L7-L7-2-full-data"`、`ROW_IDENTITY_STORE_KEY="rowId"`、`FORMULA_TEMPLATES={"E":"=B{row}+C{row}-D{row}","L":"=B{row}+F{row}+G{row}","M":"=C{row}+H{row}+J{row}","N":"=D{row}+I{row}+K{row}","O":"=L{row}+M{row}-N{row}"}`、18 字段 7 元组 `MANAGED_FIELD_SPECS_7`（A..R，E/L/M/N/O 判 formula，组标题单元格对齐 R10 合并组 B10/F10/H10/J10/L10）、`ghost_row_anchor_index`=itemName 列下标（A，真业务名称文本）、`SPEC_L72: RowTableSheetSpec(...)`。HTML-only 键若有（L7DetailRow 全列有对端 ⇒ `HTML_ONLY_ROW_KEYS=()`，接线时按前端接口复核）。
      新建 `backend/app/services/workpaper_sync/phase5_l7_other_noncurrent_liabilities.py`（照 `phase5_l3_long_term_loans.py`）：re-export `phase5_l7_sheets` 常量、构 `IDENTITY = _L.LEntryIdentity(...)`、`SPECS=(SPEC_L72,)`、全部七段薄转发 `phase5_l_cycle_common`、三别名 `publish_pilot_definitions`/`attach_pilot_adapters`/`PILOT_WP_CODES`。
      生成 contract：`backend/scripts/gen/generate_phase5_l_contracts.py` 的 `_PROVIDERS` 加 `_l7.ADAPTER_ID: _l7`（import `phase5_l7_other_noncurrent_liabilities as _l7`）；先 `--check` 预演再 `--apply` 落 `backend/data/workpaper_sync_contracts/l7.other_noncurrent_liabilities.json`。
      五处登记（照 L2/L3 格式，末尾追加不重排）：① registry `_ALLOWED_PROVIDER_MODULES` 加 `"app.services.workpaper_sync.phase5_l7_other_noncurrent_liabilities"`；② `store_item_registry.py` `STORE_MERGE_REGISTRY` 加 `"l7.other_noncurrent_liabilities": StoreMergePlan(adapter_id=..., provider_module="phase5_l7_other_noncurrent_liabilities", items=(StoreItemSpec(item_id="L7-L7-2-full-data", kind=StoreKind.rows),), oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas")`；③ `adapters/delivered_contracts_ledger.py` `DELIVERED_PER_ENTRY_CONTRACTS` 末尾追加 L7 条目；④ 生成器 `_PROVIDERS`（同上）；⑤ `backend/scripts/fix/fix_l_cycle_wp_code_adjudication.py` 的 `_ROWS` 追加 L7 条目（entry_id/contract_id/wp_codes=["L7"]/basis/store_payload_evidence），`--check` 预演再 `--apply`。配对不变式：`_ALLOWED_PROVIDER_MODULES` 的 L 条数 == ledger 的 L 条数。
      新建测试 `backend/tests/workpaper_sync/test_l7_adapter_registration.py`（照 `test_l3_adapter_registration.py`，含选型/几何现算、契约 disk-source 锁 + formula_mask 非空 + 5 个 formula 字段、注册 store/ledger/whitelist/adjudication、HTML 对齐=契约 json_pointer ⊆ 前端 L7DetailRow 字段、真库干净命名空间 `L7-L7-2-%` 现算）。
      Files: `backend/app/services/workpaper_sync/phase5_l7_sheets.py`、`backend/app/services/workpaper_sync/phase5_l7_other_noncurrent_liabilities.py`、`backend/data/workpaper_sync_contracts/l7.other_noncurrent_liabilities.json`、`backend/app/services/workpaper_sync/adapters/registry.py`、`backend/app/services/workpaper_sync/store_item_registry.py`、`backend/app/services/workpaper_sync/adapters/delivered_contracts_ledger.py`、`backend/scripts/gen/generate_phase5_l_contracts.py`、`backend/scripts/fix/fix_l_cycle_wp_code_adjudication.py`、`backend/tests/workpaper_sync/test_l7_adapter_registration.py`
      Verify: `rtk python -m pytest backend/tests/workpaper_sync/test_l7_adapter_registration.py -v --tb=short`（cwd 仓库根，venv `.venv\Scripts\python.exe`）→ 18 passed 量级全绿；`& .venv\Scripts\python.exe backend/scripts/gen/generate_phase5_l_contracts.py`（`--check`）rc=0；`fix_l_cycle_wp_code_adjudication.py --check` 报 OK 或将新增 L7 一条。

- [x] 4. 五环发布（判成败查 DB 不看退出码）。
      先确认 Docker：`rtk docker ps` 看 `audit-postgres`/`audit-onlyoffice`；未起则 `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"` 并等待 health。
      task76 provision：`& .venv\Scripts\python.exe backend/scripts/fix/fix_task76_provision_projection_definitions.py --check --entry xlsx/gt-l7-other-noncurrent-liabilities`（确认 would_create_total=5、contract digest 与 provider 现算逐字相同），再 `--apply`。
      first_publication：`& .venv\Scripts\python.exe backend/scripts/fix/fix_projection_first_publication.py --apply --entry xlsx/gt-l7-other-noncurrent-liabilities`。
      若 L7-2 模板被 OOXML 安全门（外链/OLE）或插行门（共享公式）拒（L4 踩过），照 `backend/scripts/fix/sanitize_l4_template_external_links.py` 的净化内核处理（受管 sheet 0 diff，先 --check 预演），净化后更新 provider 的 `TEMPLATE_SHA256` 并保留 `PRE_SANITIZE_TEMPLATE_SHA256`，重跑步骤3生成器 `--apply`。
      Files: （本步主要是运行脚本；若净化则新增 `backend/scripts/fix/sanitize_l7_template_external_links.py` 并改 `phase5_l7_sheets.py` 的 sha 常量）
      Verify: 只读 SQL（`docker exec audit-postgres psql -U postgres -d audit_platform` 或脚本内 async_session）确认 L7 entry 三表闭环：`working_paper_sync_entry_state` 有 L7 行且 `current_representation_id` 非空 + `working_paper_content_representation` 该 entry representation_generation=1 + approved `definition_bundle` 存在。禁以脚本退出码判成败。

- [x] 5. overlay 补 L7 override + 干净 worktree 重算 digest + 翻 manifest（铁律）。
      `backend/data/workpaper_sync_entry_overlay.json` 的 `overrides` 末尾加 L7 一条（照 L3 格式）：`file_glob="audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue"`、`component="GtOnlyOfficeSheet"`、`html_store="checklist_responses_l7_other_noncurrent_detail_rows"`、`canonical_resolver="workpaper_sync_published_representation"`、`adapter_id="l7.other_noncurrent_liabilities"`、`capability="bidirectional"`、`migration_state="adapter_registered"`、`evidence_patch.review_status="published_representation_verified"`、`legacy_reasons=[]`；并更新 `review_basis`（追加 L7 轮说明，`||` 分隔）与 `approved_source_digest`（下一句在干净 worktree 重算）。
      干净 worktree：`git worktree add .worktrees/l7-flip -b work/2026-10-01-l7-true-bidirectional <含步骤1~3提交后的最新主HEAD>`（分支名描述性、仅本 worktree 用，任务结束删除；不是「worktree 外的新长期分支」）。在干净 worktree 跑 manifest 重生成 `& .venv\Scripts\python.exe backend/scripts/gen/generate_workpaper_sync_manifest.py --apply` 重算 `approved_source_digest`（这是 overlay 下游的真源）。
      mount-diff 零能力损失复核（铁律）：用**完整 manifest build 对比 HEAD**（不是 entries[].mounts vs live 的错误口径，L4 踩过）。预期：`xlsx/gt-l7-other-noncurrent-liabilities` capability `single_onlyoffice→bidirectional`、migration_state `legacy_fake_bidirectional→adapter_registered`、adapter_id `None→l7.other_noncurrent_liabilities`、per-entry mount +1、`stats.mount_count` +1、`host_count` 不变、`byComponent` 仅 `GtOnlyOfficeSheet` +1；capability_counts 仅三项各 ±1（bidirectional +1 / single_onlyoffice −1 / legacy_fake −1）；**其它所有 entry 零变化**，预期外翻转停报（send_message warning）。无关 churn 归因并发会话。全部写进 `.agents/tasks/l7-true-bidirectional-2026-10-01/l7-flip-diff.md`。
      baseline 是 manifest 下游（L3 踩过）：翻转后在干净 worktree 跑 `& .venv\Scripts\python.exe backend/scripts/gen/generate_workpaper_sync_legacy_baseline.py --apply`，确认 baseline diff 只影响 L7 条目 + 顶层 digest/stats + 可接受的并发预存哈希顺手修正。前端投影 `workpaperSyncManifest.generated.ts` 若由 manifest 生成器连带更新一并回拷。
      回拷主树产物（manifest.json / overlay.json / legacy_baseline / generated.ts）；只 `git checkout`/`git add` 本任务产物。
      Files: `backend/data/workpaper_sync_entry_overlay.json`、`backend/data/workpaper_sync_entry_manifest.json`、`backend/data/workpaper_sync_legacy_baseline*.json`、`audit-platform/frontend/src/components/workpaper/sync/workpaperSyncManifest.generated.ts`、`.agents/tasks/l7-true-bidirectional-2026-10-01/l7-flip-diff.md`
      Verify: 干净 worktree `& .venv\Scripts\python.exe backend/scripts/gen/generate_workpaper_sync_manifest.py --check` rc=0（无漂移）；`rtk python -m pytest backend/tests/workpaper_sync/test_task73_entry_profile_manifest.py --tb=short` 在干净 worktree 0 failed；flip-diff.md 的 capability 范围校验表显示唯一翻转 entry = L7。

- [x] 6. 验证（禁「看代码觉得对」）。
      先 `git stash` 区分预存红 vs 本任务红（已知预存红：task73 drift 脏主树 digest 失配、TestImportDataAPI 400）。
      L7 adapter 测试：`rtk python -m pytest backend/tests/workpaper_sync/test_l7_adapter_registration.py -v --tb=short` 18 passed；clean worktree 跑 L7 drift（task73）应 0 failed。
      新建真 OO 往返 `backend/scripts/e2e/verify_l7_oo94_roundtrip.py`（照 `verify_l4_oo94_roundtrip.py`——L7-2 有公式列，用 L4 的「公式幸存」范式，不照抄 L3 的「零公式列」断言）：生产 attach（断言 ids==('l7.other_noncurrent_liabilities',)）→ 真 representation substrate → HTML 载荷 2 行稳定 rowId（_row 跳过 formula 列，置 itemName 等 editable 列）→ materialize → docker `audit-onlyoffice` ConvertService xlsx→xlsx 重存 → extract → G1 等值门 → merge 回 store 逐字段比（rowId 稳定、无幽灵行、行命中数==输入数）→ 受管行 E/L/M/N/O 五列公式往返后仍是公式（`startswith("=")`）→ 不写库（前后 `L7-%` 行数不变）。9 步。cwd 仓库根，venv `.venv\Scripts\python.exe`。
      L7-2 数据区 R12~R16 无预置标签行（骨架行只有序号），风险类似 L1 可过；仍按铁律接线前核 HTML 骨架行身份==instrumentation 模板行身份（若往返翻倍则排查）。
      真浏览器 dev server（9980/3030）大概率未起：如实标「代码已改但未实测（环境待 start-dev.bat）」，不假绿。
      Files: `backend/scripts/e2e/verify_l7_oo94_roundtrip.py`
      Verify: `& .venv\Scripts\python.exe backend/scripts/e2e/verify_l7_oo94_roundtrip.py`（cwd 仓库根）退出码 0、打印「✅ L7 真 OO 引擎往返全绿」9 步全过；`git stash pop` 恢复并记录预存红清单。

- [x] 7. 提交（逐文件 git add，禁 -A）。
      commit 前 `git rev-parse HEAD` 对比步骤0 的 HEAD：若被并发移动，确认本任务产物（上述 Files）没被抢先提交，再逐文件 `git add`。可分两 commit（前端 rowId+host / 后端 provider+发布+manifest）或单 commit。中文 message 说明「L7 其他非流动负债真双向（受管表明细表 L7-2，HTML 行身份换稳定 rowId + provider/contract 五处登记 + 五环发布 + manifest 翻 bidirectional + 真 OO 往返）」。
      清 worktree：`git worktree remove .worktrees/l7-flip` + 删临时分支 `work/2026-10-01-l7-true-bidirectional`。**不 push**（走用户 PR 流程）。
      Files: （git 操作，无新文件）
      Verify: `rtk git status` 确认本任务 Files 已提交、无 `-A` 误纳并发产物；`rtk git log --oneline -2` 显示 L7 commit；`git worktree list` 不含 l7-flip；并发会话的 220+ 项仍未提交（未被动过）。

## 异常处理

任一步出现预期外结果（finder 幻影码意外命中真码 / 发布链 DB 三表未闭环 / manifest 翻转波及非 L7 entry / 往返公式未幸存或行翻倍 / 净化后受管 sheet 非 0 diff），停下报告（send_message severity warning），不绕开、不假绿、不降级断言。
