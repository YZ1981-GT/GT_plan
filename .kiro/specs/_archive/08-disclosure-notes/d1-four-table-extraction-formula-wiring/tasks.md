# Implementation Plan: D1 四表库取数 + 公式接线 + 披露/附注复核

## Task Dependency Graph

本 spec 分 4 波推进。Wave 1（后端取数 seed 服务 + 纯函数 + 单测）是基础；Wave 2 接入 render 并做 characterization 零回归；Wave 3 补公式管理预设 / cross-sheet 溯源；Wave 4 复核披露表 + 附注同步并浏览器实测。

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端取数 seed 服务（纯函数 + 单测）",
      "tasks": ["1.1", "1.2", "1.3", "1.4"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "接入 D1 render + characterization 零回归",
      "tasks": ["2.1", "2.2", "2.3"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "公式管理预设 + 各底稿间连接取数溯源",
      "tasks": ["3.1", "3.2", "3.3"],
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "披露表复核 + 附注同步 + 浏览器实测",
      "tasks": ["4.1", "4.2", "4.3", "4.4"],
      "depends_on": [2, 3]
    }
  ]
}
```

## Tasks

- [x] 1.1 新建 `backend/app/services/d_cycle_extraction/d1_detail_seed.py`，实现纯函数 `build_d1_category_rows_from_tb(leaves)`：把 1121 叶子映射为 D1-cat-rows（priorUnadjusted=opening / currentIncrease=debit / currentDecrease=credit；名称含「银行承兑」→ fixed-bank、「商业承兑」→ fixed-commercial、其余动态行）。
  - Requirements: 1.1, 1.2, 1.4
  - Properties: 5, 6

- [x] 1.2 在同模块实现纯函数 `build_d1_bad_debt_rows_from_tb(leaves, direction_map)`：把 1231「应收票据」叶子映射为 D1-bd portfolio 行（期初/本期净计提按方向归一），individual 留空（宁缺勿造）。
  - Requirements: 2.1, 2.2, 2.3
  - Properties: 1

- [x] 1.3 实现 `async seed_d1_detail_rows(ctx, responses_snapshot)`：经 `get_active_filter` + leaf-only 查 1121/1231 叶子，构建行；仅当 snapshot 无对应 anchor 非空 remark 时 transient seed（手工优先）；anchor 经 `is_known_anchor('D1',...)` 校验；全程 fail-open。
  - Requirements: 1.3, 1.5, 1.6, 2.4, 4.5
  - Properties: 1, 2, 4, 7

- [x] 1.4 新建 `backend/tests/d_cycle_extraction/test_d1_detail_seed.py`：覆盖叶子选取（Property 1）、勾稽一致 opening+debit−credit=closing（Property 5）、固定行映射（Property 6）、手工优先（Property 2）、fail-open（Property 4）。
  - Requirements: 7.2
  - Properties: 1, 2, 4, 5, 6

- [x] 2.1 修改 `_d1_notes_receivable.py::render`：灰度开关分支内、`seed_tier_a_reconciliation` 之后 `await seed_d1_detail_rows(ctx, responses_snapshot)`（fail-open 包裹）；更新原「宁缺勿造」注释为实证叶子取数说明。
  - Requirements: 1.1, 2.1, 3.1
  - Properties: 3, 4

- [x] 2.2 characterization/seed 集成：`test_d1_render_prefill_integration.py` 扩展（灰度关逐字节等价 + tb 叶子存在时 seed D1-cat-rows/D1-bd-portfolio-rows；修正原「宁缺勿造」误导性断言）：灰度关时 D1 render 输出与基线逐字节等价（characterization）；灰度开时 responses_snapshot 含 D1-cat-rows/D1-bd seed。
  - Requirements: 1.7, 2.5, 7.1
  - Properties: 3

- [x] 2.3 前端单测 `useD1DetailCategory` / `useD1BadDebt` 消费 seed（无持久化 seed 就位、有持久化不覆盖）；若既有测试已覆盖加载路径则仅补 seed-priority 断言。
  - Requirements: 7.3
  - Properties: 2
  - 产出 `composables/__tests__/d1DetailSeedConsumption.spec.ts`（18 例全绿）。既有
    `useD1DetailCategory.spec.ts` / `useD1BadDebt.spec.ts` 是**复刻逻辑的纯函数 PBT**
    （不实例化 composable），加载路径零覆盖 → 本文件真实例化两个 composable，分两层断言：
    ① **消费层**：以 Wave 4.4 真实项目实测值作 fixture（银承 12,460,611.29 / 商承
    7,748,586.89 / 信用证 0，合计 = tb 1121 期末 20,209,198.18；坏账 3,037,132.25 →
    1,162,288.03），断言逐行 roll-forward 守恒、小计 = tb 期末、净减记 `currentReversal`
    而非 `currentProvision`、按单项区保持默认空行（宁缺勿造）、seed 只含动态行时前端补齐
    固定行且不篡改 seed 金额、**已有持久化不被 seed 顶掉**（Property 2，同锚点单一真源），
    另 1 条 PBT（任意叶子集 → 小计 = Σ 各叶子期末）。
    ② **跨语言字段契约层**：直接读后端 `d1_detail_seed.py`，断言三个锚点常量、科目前缀
    （1121 / 1231 / 应收票据）与**两个行 dict 键集逐字等于**前端反序列化字段集，并断言
    `_has_persisted` 前置于 seed、模块内无落库写入。字段名跨 Python/TS 漂移时 mypy、
    vue-tsc、vitest **全查不出**，只表现为「seed 跑了但界面全 0」。
  - 🔴 该守卫已证非空转：首版 `pyDictKeysIn` 的函数体边界只认 `\ndef `，而 D1 坏账函数后面
    是 `async def _fetch_leaves` → body 溢出，把 `code/name/opening/closing/debit/credit`
    误算成坏账行字段，测试当即打红。已修边界为 `\n(?:async\s+)?def ` 并把该 bug 钉进反向自检。
  - 回归：`composables/__tests__` 全量 **720 passed / 4 failed**（l4×2 · F3 · F5 · H4，
    全在未触碰文件，与既有基线一致）。

- [x] 3.1 修改 `presets.py::_TIER_B_PROVENANCE['D1']`：D1-2/D1-4 溯源描述由「不从四表库填」更新为「← tb_balance 1121/1231.01 叶子」。
  - Requirements: 4.2
  - Properties: 8

- [x] 3.2 在 `_TIER_B_PROVENANCE['D1']` 增登记各底稿间连接取数溯源条目：D1-1 原值←D1-2 小计 / D1-1 坏账←D1-4 小计 / D1-4 期末坏账↔D1-15 ECL / D1-1 表外←D1-8 未终止确认合计 / D1-3 期后兑付←序时账 1121 贷方（editable=False）。
  - Requirements: 4.3, 4.4
  - Properties: 8

- [x] 3.3 契约测试（复用 `test_d1_render_prefill_integration.py::test_tier_b_provenance_d1_honest` 扩展）：`tier_b_provenance('D1')` 每条 editable=False/source=prefill/tier=B、覆盖 tb 直取 + 连接取数锚点 每条 anchor ∈ 登记表、editable=False、含源/目标/口径字段。
  - Requirements: 4.5, 7.2
  - Properties: 7, 8

- [x] 4.1 以源模板 xlsx 两个披露 sheet 为裁决者，逐 sheet 复核 D1 上市/国企披露表 + `d1NoteSectionMap` 列结构、两级表头、动态插行区域、账龄枚举，产出差异清单（无差异亦记录）。
  - Requirements: 5.1, 5.3, 5.4
  - Properties: 9

- [x] 4.2 对复核发现的差异，参照源模板修复披露表 / `d1NoteSectionMap` / 附注 note_template 五、4·八、4（幂等脚本 `fix_note_d1_notes_receivable_structure.py` 增量 + 契约 `d1NoteSubtableContract.spec.ts`）。
  - Requirements: 5.2, 6.2, 6.4
  - Properties: 9

- [x] 4.3 复核披露表推送附注链路：文本框键集一一对应、动态插行/账龄段同构；缺口按既有 `useDisclosureAutoSync` 补齐。
  - Requirements: 6.1, 6.3, 6.5
  - Properties: 10

- [x] 4.4 浏览器实测（chrome-devtools + postgres 只读）：四表入库后 D1-1/D1-2/D1-4 有数据 → 披露推送 → 附注 五、4/八、4 落库正确；测试数据用后复原。
  - Requirements: 7.5
  - Properties: 3, 10

## Notes

### 当前进度（本会话）

- **Wave 1 ✅**：`d1_detail_seed.py`（纯函数 + `seed_d1_detail_rows`）+ `test_d1_detail_seed.py` 14 例绿。
- **Wave 2 ✅**：接入 `_d1_notes_receivable.py::render`（灰度分支内，fail-open，手工优先）；`test_d1_render_prefill_integration.py` 扩展（灰度关逐字节等价 + tb 叶子存在时 seed D1-cat-rows/D1-bd-portfolio-rows）；修正原「宁缺勿造」误导性断言。
- **Wave 3 ✅**：`_TIER_B_PROVENANCE['D1']` 由「不从四表库填」改为 tb 叶子取数 + 各底稿间连接取数溯源（D1-1←D1-2/D1-4、D1-4↔D1-15 ECL、D1-1 表外←D1-8、D1-3←序时账 1121 贷方）；契约断言随之更新。
- **全量 `backend/tests/d_cycle_extraction/` 347 例绿。**
- **Wave 4.1 部分 ✅**：`fix_note_d1_notes_receivable_structure.py --check` = 0 项欠账（附注 五、4/八、4 note-template 结构已对齐，沿用 `d1-notes-receivable-disclosure-alignment` 既有成果）。

### 灰度开关（已按「本环境 opt-in」落地，代码默认未动）

D1 明细 seed 门控已收敛为 **主开关 ∧ 子开关**：
`D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（P0-1，D 循环公用）
∧ `D_CYCLE_DETAIL_SEED_ENABLED`（P0-2 明细 seed 子开关）。

- 🔴 **修掉门控不一致**：首版（Task 2.1）只挂主开关，而 D6-2 同类明细 seed 早已按「主 ∧ 子」
  门控、子开关注释语义本就是 D 循环**通用**的「明细表 render 自动 seed」→ 让文档承诺的
  「发 P0-1、压 P0-2」（开主开关拿 Tier A、同时压住明细自动 seed）对 D1 失效：运维为启用
  Tier A 开主开关时会**静默**连带打开 D1 明细 seed 且无法单独回退。已与 D6 对齐，
  新增 `test_main_on_sub_off_no_detail_seed`（含反向自检）锁死该矩阵态。
- **本环境 `.env` opt-in**（主开关此前已由前序会话开启，本次补子开关），**未改 `config.py`
  的代码默认值**（那会波及 D2~D7 全部署，属平台级变更，仍待确认）→ 删掉 `.env` 那行即回退。
- 连带修正：`test_d1_render_prefill_integration` 的开关辅助改为**两开关都显式 setattr**，
  `test_detail_seed_subswitch_default_false` 改断言 `Settings.model_fields[...].default`
  而非 `settings` 运行值 —— 原写法读 env 合并值，环境一 opt-in 就把「代码默认零回归」
  这一意图误报成回归（本次实际打红过）。

### 🔴 live 实测挖出的真缺陷（已修）：坏账 seed 被全零骨架永久堵死

`useD1BadDebt` 在底稿**首次打开**时就把 `DEFAULT_PORTFOLIO_ROW` / `DEFAULT_INDIVIDUAL_ROW`
经防抖保存落库，remark 是一段**非空** JSON 全零骨架。而 `_has_persisted` 原先只判「remark 非空」
→ **任何被打开过一次的底稿，坏账 seed 永久不再触发**。实证：真实项目 wp `68c7740e…` 的
`D1-bd-portfolio-rows` 自 **2026-07-09** 起即为该骨架，seed 一直静默跳过（后端单测、前端
vitest、`get_diagnostics` 全绿，只有 HTTP/浏览器实测才暴露）。

修法对齐 D6「明细**完全空**才 seed」语义：新增 `_is_blank_skeleton()` —— 所有行数值字段全为 0
→ 判为无用户数据（骨架 rowId/label 由前端按默认行逐字重建，无可丢内容）；**任一非零金额或
解析失败一律视为有手工数据，绝不覆盖**。守卫 3 例：全零骨架仍 seed / 任一非零即保留 /
remark 非 JSON 保守不覆盖。

### 浏览器实测记录（对应 4.4，已完成）

环境：重启 9980 载入修正后代码 + 两开关；chrome-devtools MCP 驱动 + postgres MCP 只读比对。
项目 `0ec33ac9…`（重药控股安徽_2025）/ wp `68c7740e…`。

1. **四表 seed 在 UI 可见**（D1 底稿 33 个 Tab 正常，无 Vite 错误）：
   - D1-2 原值明细：银行承兑汇票 期末 **12,460,611.29** / 商业承兑汇票 **7,748,586.89** /
     信用证 **0**（显示「-」）/ 小计 **20,209,198.18**
   - D1-4 坏账准备：按组合计提 期初 **3,037,132.25** → 本期转回 **1,874,844.22**
     （期末 1,162,288.03 = tb 1231.01）；按单项计提全 0（宁缺勿造）
   - 🔴 与裸 SQL 全量汇总（1121 期末 40,418,396.36 / 1231.01 期初 6,074,264.50）恰好 **2 倍**
     关系 —— 裸查跨了两个数据集版本，`get_active_filter` 只取 active，**印证数据集治理正常**，
     不是取数错误。核对时不要用裸 SQL 当基准。
2. **披露推送附注**：国企 Tab → `POST /disclosure-notes/sync-from-workpaper` **200**
   （`section_id=八、4`、`rows_synced=28`）→ 库中 `八、4` 的 `_last_sync_at`
   由 `2026-07-27T12:18:12` 前移至 **`2026-07-31T11:03:54`**，12 子表、
   `_last_sync_sheet=附注披露信息（国企）`、`_current_standard=soe_standalone`。
3. **跨主体守卫实证生效**：同一底稿的**上市** Tab 点同步 → **409 `STANDARD_MISMATCH`**
   （「项目适用准则为 soe_standalone，不能以 listed_standalone 同步披露数据」）→ `五、4`
   **纹丝未动**（守卫阻止了跨变体污染）。该项目 `template_type='listed'` 但
   `applicable_standard_v2.entity_type='soe'`，故底稿渲染出上市 Tab 而准则判定为国企。
4. **数据未被污染**：`D1-cat-rows` 始终不在 `checklist_responses`（seed 保持 transient）；
   坏账两行 `updated_at` 仍为 2026-07-09；仅 `八、4` 的 `_last_sync_at` 因幂等重同步前移
   （即本次实测证据本身），无需复原。

### 遗留（不阻塞本 spec）

- 🟡 **前端把 409 静默吞掉 → 点「同步到附注」毫无反馈**。静默是有意设计（宁可不写也不写错章节），
  但用户完全看不出发生了什么。建议 409 时给一条明确提示（「当前项目适用国企准则，请在国企披露页同步」）。
- 🟡 **D1 披露 Tab 无 `applicable_standards` 门控**（归档 spec `d1-notes-receivable-disclosure-alignment`
  已登记的最后一项）：上市 Tab 在国企项目上照样渲染可编辑可点，用户能一路填到底才撞 409。
  属平台级，随对应 spec 一起做。
- 是否把 `config.py` 的两个默认值翻为 True（波及 D2~D7 全部署）待用户裁决；当前仅本环境 `.env` opt-in。
- commit（按层分批，见 memory 铁律）。
