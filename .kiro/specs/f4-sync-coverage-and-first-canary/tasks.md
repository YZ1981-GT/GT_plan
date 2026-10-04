# Implementation Plan

## Overview

**spec**：`f4-sync-coverage-and-first-canary`　**创建**：2026-09-26　**状态**：**10/20 已实施**（2026-10-03 复盘修正，原 8/20 偏低）
**上游**：umbrella Task 48 · FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）· D1 引擎 ·
F1 spec（借贷镜像同构 + 三家审定表统一口径裁决）· F3 spec（FC-11 工具链根因）

## 实施进度（2026-09-26）

已完成 Task 0~4 + 6 + 7 + 18（canary 链路 + F4A 撞码隔离 + FC-11 数据侧）。判据
`backend/tests/workpaper_sync/test_f4_canary_and_contract.py` **30 passed / 1 xfailed**。

🔴 **实施中实测修正 spec 的三处**（详见 `evidence/task2-morphology-and-geometry.md`）：

1. 🔴 **三张多区 sheet 的 `uuid_col` 同列声明不可用**：同 sheet 多区靠 `uuid_col` 配对
   spec↔contract table（框架层源码注释：缺它 → 匹配 0 张 → `ProviderCapabilityError`）。
   design 受管区清单把 F4-7 五区全写 **L**、F4-8 双区全写 **S**、F4-1 两区全写 **M** ⇒ 全部不可用。
   实测全空列充足，改为：F4-7 = **L/M/N/O/P**（N/O/P 超 max_col 需扩列）· F4-8 = **S/T** ·
   F4-1 = **M/N**。provider 的 `build_contract_payload()` 已加兄弟区重复检测并抛。
2. **撞码形态精确化**：`wp_code_overrides.json` 确有 `F4A -> f4-accounts-payable`，但
   **`F4` 本身没有 override 条目** ⇒ 撞码只有「幻影码与路由码字面相同」这一种，不是两条并存。
   这让三条隔离判据的前提更强（finder 域 `_index.json` 与业务域 `wp_index` **都没有** `F4A`，
   只有路由表有 ⇒ 误用时得到空集而不是命中程序表）。判据已扩到四条子断言。
3. 🔴 **新发现 F4-6 模板缺陷**：`B8:B11` 的数据验证 `formula1=$N$7:$N$14` 而 **N 列全空**
   （悬空引用）⇒ R8-R11 四行的关联关系下拉是空列表；仅 `B7` 的 DV 指向真实枚举源 `$B$18:$B$25`。
   不改模板字节，登记在 `TEMPLATE_DEFECT_F406`，判据逐格证明其属实。
4. **F4-1 账龄区 R21 是空槽行**（标签只有 4 个而 SUM 覆盖 R17-21 五行）⇒ 与 F3-1 的 R9/R10
   同型，正是裁决 **F3-H4「mask 是行级不是矩形」**的场景。Task 19 须先实测 R17-20 与 R21 的
   公式集合差异，不同则拆两个 spec（此时 uuid_col 需从 M/N 扩到三个）。

✅ **FC-10 不命中已取证**（需求 7.6）：`关联方及交易检查表F4-6` 全表 `number_format` 含 `%`
的格数 = **0**（判据 `test_canary_sheet_has_zero_percent_format_cells`）—— 不是「以为不命中」。

`[ ]*` = 依赖外部供给（BP-61-1 / OO 真栈 / 三家统一口径裁决 / 业务确认）。

## Tasks

### 阶段 0：前置门 + 形态判定 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）：框架层 `RowTableSheetSpec` / **兄弟 Table ref 位移**（F4-7 五区 + F4-8 双区 +
  F4-1 两区共 8 个同 sheet 区，全依赖它）/ `merge._protection` 格级判定；F3 spec 的 FC-11 工具链修复状态
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 4.5, 6.1, 7.2_

- [x] 1. slice 核对 + wp_code 裁决条目（含 `F4A` 撞码隔离证据）
  - 核 slice 中 `xlsx/gt-f4-accounts-payable` 的 `migration_state` / 五个 null 供给位 / `template_ref` / `mount_count=2`
  - 新增 F4 裁决条目：`wp_codes=["F4"]` + `store_payload_evidence`（`F4-2-rows` 3,485 B / 4 行 / wp_code=F4）+
    `matcher_domain_conflict=null`；🔴 另记 `phantom_code_collision` 证据（`F4A` 与 `wp_code_overrides.json:549` 同名、
    `_index.json` 无 `F4A`），重算 digest
  - _Requirements: 1.3_

- [x] 2. 形态判定 + 几何逐格实测 + 下游消费方 grep + FC-10 不命中取证
  - 13 个受管候选区逐格复核（F4-7 五区表头层级/列集、F4-8 两区列集、F4-1 两区公式列差异与空槽行、F4-9 三组边界）
  - 三元组实证表；F4-4 两区「无 -rows 键、无 addRow」取证（红基线 B4）；F4-5 I 列是否 HTML 派生（FC-7）
  - 🔴 逐列核模板百分比格式列均为公式列（FC-10 不命中，需求 7.6）
  - `F4-2-rows` 9 处引用清单；F4-7 六个 legacy 别名 + F4-9 七个 legacy 键清单；F4-8 两个零写入读键登记
  - 证据 `evidence/task2-morphology-and-geometry.md`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.5, 4.1, 4.3, 5.4, 7.6_

- [x] 3. F4-P1 / P2 / P3 / P4 红判据（现状必红，记录红形态）
  - P2 三条子判据（`_index.json` 无 `F4A` / fallback 通过 / provisioner 用真码）+ 变异
  - P3 两条别名变异 + 受管区总数断言；P4 F4-4 误作行表变异
  - _Requirements: 1.3, 1.5, 2.1, 2.2, 2.3_

- [x] 4. F4-P15 / P16 / P18 红判据：FC-11 数据侧 + FC-10 不命中 + 零写入键
  - _Requirements: 2.4, 7.2, 7.6_

- [ ] 5. F4-P17 零回归基线（10 contract golden digest 现算记录）
  - _Requirements: 7.4_

### 阶段 1：canary 链路（F4-6）

- [x] 6. `phase5_f4_accounts_payable.py` 从零建
  - `ENTRY_ID="xlsx/gt-f4-accounts-payable"` / `ADAPTER_ID="f4.accounts_payable_detail"` / `WP_CODES={"F4A"}`（幻影码）/
    `TEMPLATE_RELATIVE_PATH="F/F4 应付账款.xlsx"` /
    `TEMPLATE_SHA256="e20e62725c209b716eab4977231f21c627ab92346a72b58c20acdc7a6f1711fd"`（本 spec 实测，108,329 B）
  - `assert_entry_selectable(*, resolution, manifest=None)`（D3 同签名、无关闭开关）+ `build_matcher()`（带 `document_type`）+
    `build_registration` 照 D3:830 + **真构造判据**；13 个灰度开关（除 F4-6 外默认 False）+ `all_store_item_ids` +
    单数 `STORE_ITEM_ID="F4-6-rows"` + `instrumentation_specs()` 复数 + `build_contract_payload` + `attach_pilot_adapters`
  - _Requirements: 1.2, 1.3_

- [x] 7. `phase5_f4_06_related_party.py` canary 薄声明（无 def/class）
  - `F4-6-rows` / `rowId` / 表头 R6 / 数据 R7-11 / footer R12「合计」/ UUID **M** / `formula_columns=("F",)` /
    `{"F":"=C{r}+E{r}-D{r}"}`（🔴 负债类：期初 + 贷方 − 借方，与 F1-6 的 `=C+D-E` 镜像，逐格实测不照抄）
  - 字段键逐字取 `useF4RelatedParty` 行接口（12 列 A-L）
  - _Requirements: 1.1, 2.2_

- [ ]* 8. 契约发布链五环 + 登记点
  - 生成器 `generate_phase5_f4_contract.py --apply` → `f4.accounts_payable_detail.json` →
    `assert_contract_file_matches_source` → approved bundle → published representation → entry_state → `register_from_manifest()`
  - 登记点：`DELIVERED_PER_ENTRY_CONTRACTS` + `_ALLOWED_PROVIDER_MODULES` + `store_item_registry` plan +
    `check_sync_provider_golden_digest.PROVIDERS` + overlay + 重生 manifest
  - 🔴 第③环卡 BP-61-1 时如实 `upstream_gap`
  - _Requirements: 1.4, 1.5, 7.4_

- [x] 9. 宿主接桥（保留 legacy）
  - `GtF4AccountsPayable.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；`F4_SHEET_KEY_BY_CODE` +
    `isF4SyncManagedSheet` 从 provider 派生
  - _Requirements: 1.6, 7.5_
  - **已完成**：受管分支 `v-if="dualMode.currentMode.value === 'onlyoffice' && isF4SyncManagedSheet"`
    走 `WorkpaperSyncEditorHost`，非受管降级 `v-else-if` 保 legacy；工具栏加「同步中…」tag；
    `.oo-container` 给足高度。`F4_SHEET_KEY_BY_CODE = { 'F4-6': 'f46-managed' }` 与 provider 受管清单一致。
  - 🔴 **`useF4FormData` 补导出 `flushPendingSave`**：`_flushPending()` 实现早已存在（`onScopeDispose` 在用），
    只是没对外导出 ⇒ 改动一行。`flushHtml` 先 flush 再 `readStoreProjection`（顺序不可换）。
  - 🔴 **拒绝照抄 F1 宿主**（F1 调用未定义的 `flushPendingSave()` + 漏必填 `descriptor` 却传三个不存在的
    prop，两处已移交 F1 spec），照 E1 正确范式。
  - 类型核查：`npx vue-tsc --noEmit -p tsconfig._f345-canary.json` 三宿主 + 三 composable **零错误**。
  - 未做（如实）：Playwright 真栈实测卡 BP-61-1。

- [ ]* 10. canary 验收：三谓词 + DB 证据
  - _Requirements: 1.7_

- [x] 11. 批量 e2e 骨架：`e2e/fixtures/f4-l2-cases.json` + `e2e/f4-l2-oo-to-html-all.spec.ts` +
  `backend/scripts/e2e/seed_f4_publish_e2e.py`；🔴 兄弟 Table ref 用例覆盖「最靠前区插行」与「最靠后区插行」两向
  - _Requirements: 4.5_
  - **已完成**：`e2e/fixtures/f4-l2-cases.json` + `e2e/f4-l2-oo-to-html-all.spec.ts`（3 tests：
    2 条前置 + 1 条 canary）。`--list` 实测 3 tests 正常加载（用 `readFileSync` 而非 `import`，
    后者会让 Playwright ESM 加载器抛 `needs an import attribute of "type: json"`、整文件 0 tests，
    F1 lane 正栽于此）。
  - 🔴 **seed 脚本三 spec 合一**：`backend/scripts/e2e/seed_f345_canary_rows.py --entry f4`
    （不建 `seed_f4_publish_e2e.py`——三 spec 要造的东西逐字同构，分三份会造三处重复实现）。
  - 🔴 **canary 选的 F4-6 真库零载荷**（实测：全库只有 `F4-2-rows` 3485 B 与
    `F4-7-estimated-inbound-rows` 1211 B 有数据，都不是 F4-6）⇒ **必须 seed**，否则空表往返会让
    三谓词全部成立而什么都没验证。已 seed 2 行（381 B，带 `_seed` 标记），目标
    wp `e4f00fc1-…`（项目 `0ec33ac9-…`，与 F3/G2 lane 同项目便于串跑）。
  - seed 安全性实测：幂等（二次跑 `was_seed=true`）· 拒绝覆盖非 seed 载荷 ·
    `--purge` 只删带标记的行（F3 的真实载荷被 `kept_not_seed` 保住）· `--dry-run` 离线可验。
  - 兄弟 Table ref 双向插行用例：**未覆盖**（F4-6 是单区；该用例需 F4-8 双区 / F4-7 五区声明后才有
    意义，随 Task 13/14 一起补，如实登记而不是塞一个跑不到的用例进 fixture）。
  - 未做（如实）：真栈三谓词卡 BP-61-1（canary `pending_adapter` skip）；前置断言待后端可用。

### 阶段 2：F4-5 + F4-8 双区 + F4-7 五区

- [ ] 12. `phase5_f4_05_long_outstanding.py`：`F4-5-rows` / 表头 R8 / R9-14 / footer R15 / UUID **L** /
  `formula_columns=()`；I 列按 Task 2 的 FC-7 结论处置（`auto_source` 或 editable）
  - _Requirements: 4.1_

- [ ] 13. `phase5_f4_08_voucher_check.py` 两区声明 + 兄弟 Table ref 首验（F4-P5 部分）
  - 两区列集按 Task 2 实测各自声明；UUID **S**；两个零写入读键不进 field_specs
  - _Requirements: 2.4, 4.2, 4.5_

- [ ] 14. `phase5_f4_07_unrecorded.py` **五区**声明 + 除零判据
  - 五份独立 `field_specs`（裁决 F4-H3）；`formula_columns` 区①`("F","G","I")` / 区②`("F",)` / 区③④⑤`()`；
    UUID **L**；F4-P5 + F4-P6（除零三条子判据）
  - _Requirements: 4.3, 4.4, 4.5_

### 阶段 3：F4-2 明细 + F4-9 / F4-4 / F4-3 核

- [ ] 15. `phase5_f4_02_detail.py`：两级表头 R9/R10 / R11-31 / footer R32 / UUID **AB** /
  `formula_columns=("H","K","M","T")` / nested 账龄两组（N-Q 未审 / U-X 审定）；仅 THREE_YEAR 启用（F4-P8）；
  F4-P7（前端已对齐，预期直接绿，作 F1-2 参照）；下游 9 处消费方回写后重算
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 16. F4-9 容量裁决（F4-H4）+ 限额内声明
  - 裁决证据：模板 3 组 × 4 行 + 合计三小计相加 vs 前端任意组/行；限额内受管、超限降级（F4-P9）；
    `rowId` + `groupId` 双身份；组小计行不受管
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 17. F4-4 两区可行性核 + F4-3 可行性核（**均不改生产代码**）
  - F4-4：区① `static_region` 候选 / 区② 派生只读 + 局部覆盖，默认 HTML-only（F4-P10）；
    F4-3：FC-6 默认 `single_html`；证据 `evidence/task17-f44-f43-feasibility.json`
  - _Requirements: 5.4, 6.5_

- [x] 18. FC-11 数据侧修复（F4 三块）
  - `[224]` / `[225]` / `[307]` 的 `items` 迁 `cells`；删全角重复块 `[225]`、保留半角 `[307]`；
    `test_sheet_exists_in_source_xlsx[F4]` 转绿（F4-P15）
  - 🔴 依赖 F3 spec 已修工具链（`_ensure_cells` 只写 `cells`），否则再次运行脚本会把 `items` 造回来
  - _Requirements: 7.2_

### 阶段 4：F4-1 审定表（最后）

- [ ]* 19. F4-1 两区声明 + 行身份修复 + 统一口径落地 + 收口
  - 行身份：修 `useF4Adjudication.ts:230` 的 `custom-${index}`（F4-P11）
  - 两区各自 `formula_columns`（F4-P12）；空槽行公式集合差异按 F3-H4 处置（必要时拆 spec）
  - 🔴 取数口径按 **F1 spec 需求 7.3 的三家统一裁决结论**落地（F4-P13），不在本 spec 独立裁决
  - TB 红线 F4-P14；变异收口 + 整册 materialize/verify + 公式管理双模式可达（F4-P17）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.3, 7.4_
  - **进度：几何实测已落盘**（`evidence/task19-adjudication-f4-1-geometry.md`），声明未做。
  - 🔴 **任务名"两区"应为"三区"**（实测修正）：
    · **性质区 R8~R12 五行完全同构**（7 公式列 E,F,G,H,I,J,K），A8~A12 五个标签齐全
      ⇒ **不存在空槽行、不用拆**（此前记「性质区含空槽」有误）。
    · **账龄区必须拆**：R17~R20 是 6 公式列（E,F,G,I,J,K）、R21 只 4 列（E,I,J,K），且 **F/G/I 三列
      语义根本不同** —— R17~R20 的 `F17='明细表F4-2'!N32`、`I17='明细表F4-2'!U32` 是**按账龄段直引
      明细表合计行**、`G17=I17-F17-H17` 是倒算；R21 的 `I21=F21+G21+H21` 是本行横向加总且 F/G 无公式。
    ⇒ 共三区，各区独立 `uuid_col`：性质 **M** / 账龄种子 **N** / 账龄空槽 **O**。
  - 🔴 **共享单一 `sheet_key="f41-managed"`**（D3-4 先例），区级唯一性靠 `table_key`
    （`adjudication_nature_rows` / `adjudication_aging_seed_rows` / `adjudication_aging_slot_rows`）
    + `template_id` + `table_name` + uuid_col。表头各区独立：区① `header_group_row=6/leaf=7`（anchor `A6`）、
    区②③ `15/16`（anchor `A15`）。
  - ⚠️ **M/N/O 超出 `max_col=L`（12 列）** ⇒ materialize 需扩列（同 F4-7 五区处置；全空列实测仅 M~P 四个）。
  - 🔴 **A 列不可受管**（性质区）：`A8`~`A12` 是 `SUMIF` 的匹配键，改标签会让取数静默归零。
  - FC-10 不命中：列 `K` 是 `0.00%` 但 12 格**全是公式**（`IF(AND(E=0,J=0),...)`）⇒ mode=formula。
  - 🔴 **顺带查出的模板债（登记不改字节）**：
    ① 性质区 `SUMIF('明细表F4-2'!$D$11:$D$32, ...)` 匹配区多含合计行 R32（实测数据区是 R11~R31、
       R32 是合计行）—— 因 `D32` 为空不匹配任何标签，**无计算错误**，属不严谨。
    ② 账龄区引用 `N32`/`U32` **是正确的**（R32 确为 `SUM(N11:N31)` 合计行）⇒ 与 `F5-7!G31` 越界不同型，
       **不是缺陷**（此前的缺陷嫌疑已排除）。
    ③ 🔴 **`明细表F4-2` 数据验证语义错位（新发现）**：`DV C19:D31` 挂的是「货款,工程款,设备款,服务费,其他」
       （款项性质），但 **C 列语义是「关联方类型」**（同列上半段 `C11:C18` 挂的才是正确的
       「合并范围内关联方,...」）⇒ 会引导用户在 C19:C31 填错值。与 F4-6 的 `B8:B11` DV 悬空引用
       （`formula1=$N$7:$N$14` 而 N 列全空）同类但更严重。处置走模板覆盖层。
  - 阻塞（未做）：取数口径依赖 **F1 spec 需求 7.3 三家统一裁决**（未出结论）；行身份 F4-P11 的
    `custom-${index}` 修复属前端 BP-7 同型，可独立先做。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：兄弟 Table ref 位移是 8 个同 sheet 区的共同依赖；FC-11 工具链状态决定 Task 18 时机" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice + 撞码证据 与 13 区几何/三元组实测，互不依赖" },
    { "wave": 2, "tasks": ["3", "4", "5"], "rationale": "三组红判据并行；F4A 撞码与 FC-10 不命中都必须先取证" },
    { "wave": 3, "tasks": ["6"], "rationale": "provider 从零建" },
    { "wave": 4, "tasks": ["7"], "rationale": "canary 薄声明（F4-6，与 F1-6/F3-6 同型但公式镜像）" },
    { "wave": 5, "tasks": ["8"], "rationale": "发布链五环；第③环卡 BP-61-1 时如实 upstream_gap" },
    { "wave": 6, "tasks": ["9", "11", "18"], "rationale": "宿主接桥 / e2e 骨架 / FC-11 数据侧互不依赖" },
    { "wave": 7, "tasks": ["10"], "rationale": "canary 真栈验收，是后续真栈的硬前置" },
    { "wave": 8, "tasks": ["12", "17"], "rationale": "F4-5 第二张验证复用；F4-4/F4-3 核独立" },
    { "wave": 9, "tasks": ["13"], "rationale": "F4-8 双区先验兄弟 Table ref（区数少、风险低）" },
    { "wave": 10, "tasks": ["14"], "rationale": "F4-7 五区在双区验通后做（同 sheet 最多区数 + 除零列）" },
    { "wave": 11, "tasks": ["15", "16"], "rationale": "F4-2 明细与 F4-9 容量裁决互不依赖" },
    { "wave": 12, "tasks": ["19"], "rationale": "F4-1 最后：依赖 F4-2 受管（SUMIF/直引源）+ 兄弟 Table ref + 三家统一口径裁决" }
  ],
  "blocking": {
    "0": "兄弟 Table ref 位移未入 HEAD ⇒ Task 13/14/19 阻塞",
    "8": "published representation 供给（BP-61-1）⇒ adapter 注册与全部真栈验收阻塞",
    "18": "F3 spec 的 FC-11 工具链修复未完成 ⇒ 迁移后会被脚本改回 items",
    "19": "F1 spec 三家统一口径裁决未出结论 ⇒ F4-1 不得改取数、不得受管"
  }
}
```

## Notes

- 🔴 F4-7 是**五区**不是四区（探针摘要的四个 footer 是 `--max-rows` 截断所致，逐行实测为五区且前端五键一一对应）。
- 🔴 F4-6 公式与 F1-6 **镜像**（`=C+E-D` vs `=C+D-E`）—— 同型不等于同式，逐格实测（FC-4）。
- 🔴 F4 是四个 F spec 里唯一**无 FC-10 阻塞**的（百分比格列全是公式列），但该结论须有 Task 2 的逐列证据。
- 🔴 F4-1 取数口径**不在本 spec 独立裁决** —— 与 F1-1 / F3-1 三家同型，统一裁决在 F1 spec 需求 7.3。
