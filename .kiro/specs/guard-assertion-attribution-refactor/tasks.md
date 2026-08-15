# Implementation Plan: 守卫判据归因化改造（全局等值型 → 归因型）

## Overview

8 个任务分 4 波。Wave 1 止血（解除 3 个 blocking CI job），Wave 2 拆登记表语义与解耦
跨文件锚定，Wave 3 处理天花板余量与消息质量，Wave 4 变异检验与验收。

不改业务代码，只改判据形态。4 个被改的守卫文件里 **3 个属于别的 spec**
（disclosure-note-row-level-merge / disclosure-sync-path-buildout / l-cycle-…-completion）
—— 这是判据缺陷的固有属性，提交说明须点明跨 spec 改动与原因。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "止血：前端守卫转绿（解除 3 个 blocking CI job）",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "Task 1 是纯读的普查，Task 2 依赖它的分级结论决定改哪些；两者都只碰 disclosureSharedTableRowScope 一个文件，串行避免自撞"
    },
    {
      "wave": 2,
      "name": "登记表语义拆分与外部锚定解耦",
      "tasks": ["3", "4"],
      "parallel": false,
      "rationale": "Task 4 改 l2l4DisclosureWiring 依赖 Task 3 产出的新常量名；且两者跨 spec 边界，串行便于逐步验收"
    },
    {
      "wave": 3,
      "name": "余量与消息质量",
      "tasks": ["5", "6"],
      "parallel": true,
      "rationale": "Task 5 只碰 disclosureColumnsCoverage、Task 6 只碰 conventions.md，无文件重叠"
    },
    {
      "wave": 4,
      "name": "变异检验与验收",
      "tasks": ["7", "8"],
      "parallel": false,
      "rationale": "Task 8 的验收需要 Task 7 的变异记录作为「守卫仍有效」的证据"
    }
  ]
}
```

---

- [ ] 1. 全库同类判据普查与分级（只读，不改代码）

  - 新建 `backend/scripts/check/audit_guard_assertion_grades.py`，扫
    `audit-platform/frontend/src/**/__tests__/**/*.spec.ts` 与 `backend/tests/**/*.py`
  - 识别形态 D（`expect(<集合>.length).toBe(<数字>)` / `toEqual({...数字})`）与
    形态 E（同一 `it` 内既读别的守卫源码又做数字等值）
  - 🔴 **判定「必须改」的唯一标准**：该断言的真源被本 spec 之外的其它 active spec 拥有或触及。
    作用域限于单一循环的硬计数（`g7NoteSubtableContract` 的 27/2/11/3 等）判 `keep`
  - 输出 `backend/data/guard_assertion_grades.json`（六字段见 design Property 14）
  - 已知待覆盖清单（普查须逐条给判定，不得只报总数）：
    - 前端：`disclosureSharedTableRowScope`(7) · `disclosureAutoSyncCoverage`(1) ·
      `l2l4DisclosureWiring`(1，形态 E) · `ieOrphanBaseline`(1) ·
      `cycleImportExportRegistry`(4) · `blockColumnAmountRender`(2+) ·
      `nCycleNoteSubtableContract`(1) · `iCycleDisclosureWiring`(1) ·
      `g7NoteSubtableContract`(4) · `ieWiringIntegrity`(2) · `adjustmentIeContract`(2) ·
      `e1BankAccountPrefill`(1) · `g0SummaryLowerZone`(4)
    - 后端：`test_note_shared_table_segments`(4) · `test_x3_ie_manifest_registration`(4) ·
      `test_x3_ie_registrar`(3) · `test_note_i_cycle_structure`(1) ·
      `test_k0_source_template_facts`(3) · `test_x3_keyfamily_property`(1)
  - 脚本含反向自检：喂一个已知形态 D 的替身片段必须被识别；喂形态 A/B/C 必须不被识别
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 2. `disclosureSharedTableRowScope.spec.ts` 判据改造（解除 3 个 blocking job）

  - 按 design「形态 D → B+C 的替换配方」逐条改造 7 处
  - 🔴 核心替换：`counts).toEqual({23,6})` + `tables.length).toBe(29)`
    → **结构不变式** `counts.listed + counts.soe === tables.length` + 两键为正整数
    （替代两个硬编码且判据更强 —— 生成器出 bug 才红，别人改真源不红）
  - 地板常量命名声明 + 注释记「当前实测 N」：`tables.length ≥ 20`（实测 32）、
    `narrowed.length ≥ 10`（实测 18）、`SCANNABLE.length ≥ 10`（实测 26）
  - 天花板：`leaky.length ≤ 4`（脏名只许减少，实测已降到 2）
  - **删除** `leaky.some(含 <br/>)).toBe(true)`（真源已无此类名，锁死正在消失的脏数据无意义）
  - `GENERIC_TABLE_NAMES` 判据反转为形态 A：「登记条目若已不在真源清单则报请移出」并列出条目
    （当前 `''` 与 `'项  目'` 两条都已不在 → 改造后应报请移出 ⇒ **本 Task 需一并移出这两条**，
    同时确认移出后 `SCANNABLE` 仍不含它们（真源里已没有））
  - 拆 `it`：原 L155-171 的规模断言与 6 条归因断言分离（`八、93` 必在 / `外币货币性项目` 必不在 /
    `五、32`·`五、71`·`八、91`·`八、81` 必在），归因断言改为收集清单后单次 `toEqual([])`
  - 每条失败消息补真源路径 `backend/data/note_shared_table_segments.json` 与重生成命令
  - 修正注释里的过期推导链（「29 张表 → 17 去重名 → 剔 2 脏名 = 15」已全错）
  - 🔴 **不重复承担生成器职责**：前端不得自行重算 payload 与真源逐字比对
    —— 「生成器与真源漂移」已由后端 `test_note_shared_table_segments.py` 的
    `gen.main() == 0`（`--check`）覆盖且工作正常（它正是本次唯一没红的那一侧）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_

- [ ] 3. `MISSING_SYNC_PATH` 语义拆分

  - 拆为 `PERMANENT_EXEMPT`（4 条：H5 listed / L2 ×2 / N4 soe）与 `SYNC_PATH_GAP`（2 条：L4 ×2）
  - 🔴 拆分中**不得丢失**既有依据说明：H5 的三条实证（variant_matrix 两键 null / listed 模板
    204 章节含「油气」0 个 / `H5_NOTE_SECTION` 只有 soe 键）、L2 的 K3 撞表论证
    （含「源 xlsx 应付利息行清单逐字相同」）、N4 的「附注披露信息：无」+ variant_matrix null
  - 形态 A 关系断言保留并调整：`unexpected = actual − (exempt ∪ gap)` 必须为 `[]`；
    「已补齐必须移出」拆成两条（分别针对两个常量）
  - `expect(MISSING_SYNC_PATH.length).toBe(6)` → 两个天花板（`≤4` / `≤2`），注释写明「只许缩」
  - 新增可收敛断言：`SYNC_PATH_GAP.length` 的地板为 0（允许清零，L4 重建后自然归零）
  - 保留那段递减史注释（49→…→6）作为演进记录，但标注「数字不再作为断言」
  - _Requirements: 4.2, 4.3, 4.4_

- [ ] 4. 外部锚定解耦（跨 spec 边界，改 `l-cycle` 拥有的文件）

  - `l2l4DisclosureWiring.spec.ts` L842-849 的正则抠数字 + `toBe(6)` 改为语义存在性断言：
    `PERMANENT_EXEMPT` 段内含 `L2TabDisclosureListed.vue`、`SYNC_PATH_GAP` 段内含
    `L4TabDisclosureListed.vue`
  - 🔴 改造后的语义变化要在注释里写清：**L4 补齐时这条会红，且这是正确的红**
    （L 循环守卫应当感知自己关注的缺口被填），而不再因为「别人把 6 改成 4」而红
  - L1293-1310 的「豁免注释块字面存在」断言保留（它已是形态 A 的合理用法），
    但需随 Task 3 的常量改名同步锚点
  - 🔴 本 Task 改的是 `l-cycle-extraction-formula-and-disclosure-completion` 的产物
    ⇒ 提交说明须点明跨 spec 改动与原因，避免该 spec 推进方误判为回退
  - _Requirements: 4.1_

- [ ] 5. 天花板余量与失败消息质量

  - `ALLOWLIST_BUILDER_CEILING` / `ALLOWLIST_TABLE_CEILING`（现值 2 / 11，与实际条目数贴死）：
    确认「只许缩」是有意设计，注释补「缩小时必须同步下调天花板」，
    并验证「条目数 < 天花板」时不报红（design Property 13，用替身 fixture）
  - `INFERENCE_FALLBACK_ALLOWLIST` 的「实扫集合 === 声明集合」失败消息拆成两类明细：
    「新增 None 态表（违规，请补 flat/group）」与「已修好未删条目（请从 allowlist 删除）」
  - 复核 `BUILDER_FLOOR` / `TABLE_FLOOR`（12/60，实测 22/92）余量是否仍充足，
    注释更新实测值
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. 口径写入 steering

  - `.kiro/steering/conventions.md` 补守卫判据形态分级：A（违规清单为空）/ B（地板天花板）/
    C（包含式重点项）可用；D（全局等值）/ E（跨文件抠数字再等值）禁用
  - 给出本次实测的代价数据作为说服力：一次真源变更（K 循环补段首码）导致
    **3 个 blocking job 挂、7 条断言红、6 条有效归因断言被连坐、约 15 分钟归因成本**
  - 补一条操作口径：新建全量扫描守卫时，规模型断言一律用地板 + 注释记实测值，
    禁止 `toBe(<实测值>)`
  - _Requirements: 8.5_

- [ ] 7. 变异检验（每个被改判据必须 RED）

  - 新建 `backend/scripts/check/mutate_guard_attribution.py`，支持 `--list` / `--only X` / `--restore`
  - 锚点至少覆盖：
    - 结构不变式（人为让 `counts.listed + counts.soe ≠ tables.length`）
    - 地板（人为把真源清单截断到地板以下）
    - 天花板（人为给 `GENERIC_TABLE_NAMES` 加第 3 条）
    - 归因清单（人为从真源删掉 `八、93` 段的 `data_end` 使其不再窄）
    - 登记表拆分（人为把 L4 从 `SYNC_PATH_GAP` 移除但不补链路 → `unexpected` 非空）
    - 外部锚定（人为从 `PERMANENT_EXEMPT` 移除 L2 → `l2l4DisclosureWiring` 必红）
  - 四态判定：RED / GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）/ WRONG-TEST（污染）；
    只有 RED 且命中预期测试名才算通过
  - 🔴 变异真源 JSON 时必须走临时副本 + `monkeypatch`/环境变量重定向，**不得直接改**
    `backend/data/note_shared_table_segments.json`（并发会话可能正在读）
  - 每个归因清单型断言补「扫描面非空」地板（design Property 17）
  - 绑定 `e1FxNoteSectionMap.ts` 的反向自检处补风险注释（design Property 18）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. 验收与入库

  - 串行跑（`--no-file-parallelism`）：`disclosureSharedTableRowScope` ·
    `disclosureAutoSyncCoverage` · `disclosureColumnsCoverage` · `l2l4DisclosureWiring` ·
    `e1FxNoteSectionMap` · `e1DisclosureConsistency` · `restrictedAssetsNoteSectionMap` ·
    `restrictedAssetsSources` · `restrictedAssetsConsistency`，记录 files/tests 通过数
  - 后端侧确认未被波及：`backend/tests/test_note_shared_table_segments.py` 仍全绿
  - 🔴 三个 blocking job 的**干净 checkout 模拟**：`git stash` 无关改动或在临时 worktree 上
    跑 job 的命令行，证明不依赖工作树里的未提交文件
  - 🔴 `.github/workflows/governance-checks.yml` 若需改动（如给普查脚本加 job）：
    验收判据用**归因型**（变动落在本 spec 的字节区间内），不得用「其他 job 一个都没变」
    —— 该文件多 spec 并发编辑，全局等值必假红
  - `git status --porcelain -- <本 spec 产物清单>` 必须无 `??`
  - 清理 `_wip_*` 临时产物（只删本 spec 前缀，不动他人的）
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

## Notes

### 本 spec 的立项证据（2026-08-15 实测，i 循环收口时发现）

`disclosureSharedTableRowScope.spec.ts` 7 条断言全 RED：

| 断言 | 硬编码基线 | 实测真源 |
|---|---|---|
| `manifest.counts` | `{listed:23, soe:6}` | `{listed:24, soe:8}` |
| `manifest.tables.length` | 29 | 32 |
| 窄可写区段数 | 15 | 18 |
| `SCANNABLE.length` | 15 | 26 |
| `项  目*` 泄漏名数 | 4 | 2 |
| 泄漏名含 `<br/>` | true | 两个都不含 |
| 脏名登记表每条仍在清单 | `''` / `'项  目'` 必须在 | 两者都已不在 |

因果链：2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 补了共享表段首
`report_row_code` → 真源 23/6/29 变 24/8/32 → 改动方同步了生成器 `EXPECTED_COUNTS`
与后端 `test_note_shared_table_segments.py`（两处都写了 docstring 说明来源）→
**前端守卫属于另两个 spec，改动方 CI 视野里没有它**。

### 三条注意事项

1. **不要跑前端全量**：本仓 1999 个测试文件、4-worker 并发下会产出大量资源竞争型
   flaky（实测全量报 73 files failed，抽样单独复跑只剩 1 个真红，失败原因是 mock 的
   `HTTP 500`/`Network error`）。一律按引用关系反查辐射面 + `--no-file-parallelism`
2. **改真源 JSON 做变异时走临时副本**：`backend/data/note_shared_table_segments.json`
   可能被并发会话读取，直接改会污染他人判断
3. **`governance-checks.yml` 的验收判据必须归因型**：该文件多 spec 并发编辑，
   「其他 job 一个都没变」这类全局等值必假红（实测拍快照 144 job → append 后复核 147）

### 与其它 spec 的边界

- 本 spec **只改判据形态**，不补任何真实缺口。`SYNC_PATH_GAP` 里的 L4 ×2 由
  `l-cycle-extraction-formula-and-disclosure-completion` 负责重建，本 spec 只是让
  「缺口数」变成可独立收敛的断言
- `INFERENCE_FALLBACK_ALLOWLIST` 里 H1/I1 的 11 张表补 `flat` 不属本 spec，
  本 spec 只改天花板语义与失败消息分类
- 普查判为 `keep` 的单循环硬计数（如 `g7NoteSubtableContract` 的 27/2/11/3）
  一律不动，只补一行「作用域限于 X 循环，故硬计数安全」的注释
