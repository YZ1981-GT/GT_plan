# Implementation Plan: D 类循环取数链路补齐（D2/D3/D5/D6/D7）

## Overview

六个 wave。Wave 1 先把**取数科目错误**这类 P0 修掉（D6 取错科目族 / D2 缺减备抵 /
D5 引不存在的码），因为它们让底稿显示错数字，危害大于结构欠账；Wave 2 补 D2 附注模板
（两版 30 表 columns/guidance 全缺，是本 spec 唯一的模板级欠账）；Wave 3~4 逐循环
复核披露表并接通账龄枚举；Wave 5 修公式预设与溯源；Wave 6 守卫收口 + 逐循环实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "取数科目 P0 修正（D6 科目族 / D2 净额 / D5 诚实化）",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "D2 附注模板结构对齐（两版 30 表）",
      "tasks": ["2.1", "2.2", "2.3"],
      "depends_on": []
    },
    {
      "wave": 3,
      "name": "D2 披露表复核 + 账龄枚举贯通",
      "tasks": ["3.1", "3.2", "3.3"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "D3/D5/D6/D7 披露表复核",
      "tasks": ["4.1", "4.2", "4.3", "4.4"],
      "depends_on": [1]
    },
    {
      "wave": 5,
      "name": "公式预设与溯源登记修订",
      "tasks": ["5.1", "5.2"],
      "depends_on": [1]
    },
    {
      "wave": 6,
      "name": "守卫收口与浏览器实测",
      "tasks": ["6.1", "6.2", "6.3"],
      "depends_on": [1, 2, 3, 4, 5]
    }
  ]
}
```

Wave 1 与 Wave 2 无相互依赖（取数 / 模板各自独立），可并行。Wave 3 依赖 Wave 2 的模板对齐
（否则披露载荷无落点）。Wave 6 收口。

## Tasks

- [x] 1. 取数科目 P0 修正
- [x] 1.1 新建 `backend/tests/d_cycle_extraction/test_d_cycle_account_codes.py` 守卫（**先写测试**）
  - Property 1：扫 `d_cycle_extraction_presets.json` 全部 D 类预设，断言每个科目码
    存在于 `account_chart`（`source='standard'`）—— 当前 D6 的 `1402`（在途物资）
    与 D5 的 `1124`（不存在）应被判红
  - 反向自检：构造一个不存在的码必须被判红（防查询失效导致断言空转）
  - 断言各循环预设的 `row_code` 与 `report_config` 中该报表行的公式科目一致
  - _Requirements: 2.4, 8.1_
  - _Properties: 1_

- [x] 1.2 D6 取数科目纠正（`1402` → `1141`）
  - `d_cycle_extraction_presets.json`：D6 `expression` 改 `TB('1141','期末余额')`，
    description 写明依据（`report_config` BS-011 四准则一致 / `1402` 是在途物资）
  - `_d6_*.py` render：以 `BS-011` + fallback `['1141']` 解析，输出 `tb_source_codes`
  - _Requirements: 2.1, 2.2, 2.3, 1.1, 1.5_
  - _Properties: 1, 6_

- [x] 1.3 D2 Tier A 改净额 + render 回退同口径
  - 预设 `expression` → `TB('1122','期末余额') - TB('1231-02','期末余额')`
  - render 新增备抵标量 + `_net_tb_amount` 归一（无备抵数据时空操作）
  - 前端审定表接取数溯源条（原值 − 备抵 = 净额），消除 dead output
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - _Properties: 4, 5, 6_

- [x] 1.4 D5 取数口径诚实化
  - 核实 `1124` 无活体数据后，按 Requirement 4 二选一处理并在溯源登记写明依据
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Properties: 1_

- [x] 1.5 D3/D7 取数接科目映射（预设本身正确，只补映射解析与溯源输出）
  - 以 BS-046 / BS-047 解析，输出 `tb_source_codes`；灰度关零回归
  - _Requirements: 1.1, 1.4, 1.5, 1.6_
  - _Properties: 1, 4, 6_

- [x] 2. D2 附注模板结构对齐
- [x] 2.1 逐表复核 五、5（17 表）/ 八、5（13 表）
  - 以源 xlsx `附注披露信息(上市公司)` / `附注披露信息(国企)` + 校验预设为裁决者，
    产出差异清单（无差异亦记录）
  - _Requirements: 5.1_
  - _Properties: 9_

- [x] 2.2 新建幂等脚本 `backend/scripts/fix/fix_note_d2_ar_structure.py`
  - 两版 30 表补 `columns`（flat/group 表态）+ `guidance`（纯文本）
  - 删 4 处占位行 / `header_label` 假行；`--check` 归零
  - _Requirements: 5.2, 5.3, 5.4, 5.5_
  - _Properties: 7, 8_

- [x] 2.3 守卫 `backend/tests/test_note_d2_structure.py`
  - Property 7/8/9（含 **openpyxl 直读源 xlsx** 表名交叉比对 + 反向自检）
  - 前端契约 `d2NoteSubtableContract.spec.ts`：子表名/列键与模板逐字一致
  - _Requirements: 5.6, 8.3_
  - _Properties: 7, 8, 9_

- [x] 3. D2 披露表复核 + 账龄枚举
- [x] 3.1 两版披露 Tab 小节标题按源模板逐字修正 + 编号唯一守卫
  - _Requirements: 6.1, 6.2_
  - _Properties: 10_
  - **结论：D2 不存在 D1 那种小节标题漂移缺陷**——`D2DisclosureNoteBody.vue` 卡片标题
    直接引用 `D2_TABLE_NAMES` 常量渲染（`{{ T.classEnd }}` 等），无独立标题映射，
    天然不可能漂移（Wave 2 修正的表名已自动生效于此）。国企侧编号 1~7 唯一无重复；
    上市侧表名不带编号（源模板主表无编号）。新增守卫
    `d2DisclosureSectionLabels.spec.ts`（4 例，钉死「不得新增第二套标题真源」）。

- [x] 3.2 账龄档位改由项目账龄枚举驱动（3 年段 / 5 年段 / 自定义）
  - 复用 `useAgingConfig` + `disclosureAgingLabels` 单一真源；口径不一致只读提示
  - _Requirements: 6.3, 6.4_
  - _Properties: 11_
  - **结论：已由并发会话（2026-07-26）完整实现**——`useD2DisclosureNote` 用
    `useAgingConfig(projectId,'D2')` 驱动 `agingSegments`/`agingRows`/组合计提分表行
    （未加载回退 `PRESET_SEGMENTS.FIVE_YEAR`，与 `useAgingConfig._applyDefault` 默认
    一致防首帧跳变；`watch(agingSegments)` 自动为已有组合补齐新增段）；推送附注时
    `buildD2SyncPayload` 经 `disclosureAgingLabels.toDisclosureAgingLabel` +
    `D2_AGING_LABEL_OVERRIDES` 转换标签口径（上市「1年以内」/国企「1年以内（含1年）」）。
    新增守卫 `d2AgingEnumWiring.spec.ts`（5 例）钉死两层链路不退化。

- [x] 3.3 动态插行区与附注同构（表名/列键一致 + 历史表名进 `_removed_table_keys`）
  - _Requirements: 6.5_
  - _Properties: 9_
  - **结论：已完整实现**——动态组合分表名随审计师命名，`portfolioTableName()` +
    `buildRemovedTableKeys({previouslySynced, pushed})` 做动态 diff（不依赖静态清单，
    静态清单只兜底首次同步前的历史遗留名）；Wave 2 阶段 `d2NoteSectionMap.spec.ts`
    408 例已含 Property 7/10 覆盖（稳态幂等 + 持久化清单与静态种子合并上报）。

- [x] 4. D3/D5/D6/D7 披露表复核
- [x] 4.1 D6 披露表复核（模板已由归档 spec 对齐，只核披露侧与账龄/动态行）
  - _Requirements: 6.1, 6.2, 6.5_
  - _Properties: 9, 10_
  - **🔴 抓出并修复真实缺口**：D6 附注模板国企侧「组合计提项目」两张分表（源模板
    「工程施工」/「质量保证金」，headers=「账 龄」）的行维度本就是账龄段，但披露 Tab
    「Section 4: 按组合明细」的账龄列此前只是 `el-input` 自由文本，与 D1/D2/D7 已统一
    的项目账龄枚举（`useAgingConfig`）割裂。新增 `useD6Disclosure.fillGroupAgingBands`
    （只补缺失段不覆盖已有金额，与 D1 `fillPortfolioAgingBands` 同范式）+ 账龄列改
    `el-select`（`allow-create` 保留自定义分类）+「按账龄段生成」按钮 + 账龄口径展示 tag。
    新增守卫 `d6DisclosureAgingWiring.spec.ts`（5 例）。D6 全量回归 12 文件 107 绿。

- [x] 4.2 D7 披露表复核
  - _Requirements: 6.1, 6.2, 6.5_
  - _Properties: 9, 10_
  - **结论：无需改动**。D7 附注模板（五、39/八、39）只有「按性质分类主表」/
    「账龄超过1年的重要合同负债」/「本期重大变动」，**无组合计提分表结构**，
    不存在 D6 那类割裂点；`D7TabAdjustment.vue` 已用 `useAgingConfig(...,'D7')`
    驱动账龄段路由下拉（并发会话既有实现）。

- [x] 4.3 D3 披露表复核（注意 `applicable_standards` 门控已由平台 spec 修通）
  - _Requirements: 6.1, 6.2_
  - _Properties: 9, 10_
  - **结论：无需改动**。D3 附注模板国企主表固定 2 档「1年以内（含1年）/1年以上」
    （源模板实证），非多档账龄组合结构；`D3TabDisclosureSoe.vue` 注释明确「账龄分类
    简化为"1年以内"和"1年以上"两档」——这是源模板业务规定，不是缺陷，不接
    `useAgingConfig`（该 hook 服务多档场景）。小节标题硬编码 `(1)/(2)/(3)` 编号唯一
    无重复。

- [x] 4.4 D5 披露表复核（结合 Task 1.4 的取数裁决）
  - _Requirements: 6.1, 6.2_
  - _Properties: 9, 10_
  - **结论：无需改动**。D5 应收款项融资附注模板只有分类/质押/背书/转应收账款等
    固定结构表，无组合计提分表；小节标题 `(1)~(6)` 硬编码但编号唯一无重复。
    Task 1.4 已诚实化取数口径（移除恒空预设），不影响披露表结构。

- [x] 5. 公式预设与溯源登记
- [x] 5.1 修订 `prefill_formula_mapping.json` 的 D2/D3/D5/D6/D7 段
  - sheet 名对齐源模板真实 sheet；科目码校验；审定表补 `WP()`、明细表禁 `WP()`
  - _Requirements: 7.1, 7.2, 7.3_
  - _Properties: 12_
  - **🔴 发现比预期严重得多：D5/D6/D7 三循环 sheet 名与 `PREV()` wp_code 环形错位**
    （D5 审定表 sheet 写成 `审定表D7-1`+`PREV('D7',...)`、D6 写成 `审定表D5`+`PREV('D5',...)`、
    D7 写成 `审定表D6-1`+`PREV('D6',...)` —— 三个互相抄错）。openpyxl 逐一核实源模板
    真实 sheet 名后修正为 `审定表D5`/`审定表D6-1`/`审定表D7-1`。
  - **另发现 7 条彻底虚构的条目并删除（宁缺勿造，不修正到另一个虚构值）**：
    D2「客户明细表D2-6/账龄分析表D2-7/坏账准备计算表D2-8」（源模板该编号实为「关联方
    检查/应收账款检查/会计政策检查」，与虚构内容完全无关）、D2「应收账款明细表D2-2」
    的 10 条客户 TOP1~TOP5 排名 `AUX()` 取数（sheet 名本身不存在，且 D2-2 底稿无
    对应排名字段）、D5「分析程序D5-3」（源模板无此 sheet）、D5「子科目明细」
    （112401/112402 无对应实现）、D6「分析程序D6-3」（科目码用了 `1401` 存货类，
    且源模板 D6-3 实为「合同资产减值准备明细表」非分析程序）。
  - 修正 D2「分析程序」sheet 名 `分析程序D2-5`→`应收账款分析表D2-5`；D3 同类
    `分析程序D3-3`→`预收账款分析表D3-4`；D7 `分析程序D7-3`→`合同负债分析表D7-4`。
  - D2 坏账准备明细表 `account_codes` 由整个 `1231` 族收窄为 `1231-02`（与 Wave 1.3
    的净额口径边界一致）。D5 审定表条目加 `_note` 字段说明 1124 恒空的诚实化依据。
  - **修掉 4 处「测试假设本身有问题」导致的守卫盲区**（既有测试从未读过 `sheet` 字段，
    只按字符串子串或固定个数判定，故虚构 sheet 名能一直存在）：
    ①`test_d_prefill_d567_fix.py::test_d567_no_other_d_entries_corrupted` 原强制
    要求 D5/D6 存在「分析程序」/D5 存在「子科目明细」条目 → 改为断言其**不应存在**
    并新增 `test_d567_sheet_names_match_source_template`（openpyxl 直读三份源模板
    交叉锁死全部 sheet 字段，反向自检 sheet 集合非空）②`test_d_cycle_revenue_properties
    .py::test_each_d_cycle_wp_has_analysis_sheet_entry` 原按 `"分析程序" in sheet`
    子串匹配（D2/D3/D7 真实 sheet 名带业务前缀不含此字样；D0 的 `分析程序D0-3` 同样是
    虚构值，源模板真实 D0-3 是「跟函函证过程控制」，超本 spec 范围只记录不改）→ 改为
    按已知有该结构的循环（D2/D3/D4/D7）显式登记业务前缀，D1/D5/D6 不再强制
    ③`test_d_prefill_extension.py::test_new_sheets_exist`/`test_d2_2_has_10_aux_cells`
    → 改为断言虚构 sheet 已删除。
  - 回归：D 类相关 **953 passed / 2 skipped**（含新增/改写的 4 处守卫）。

- [x] 5.2 更新 `_TIER_B_PROVENANCE` 各循环描述与守卫
  - _Requirements: 7.4_
  - _Properties: 12_
  - D2 描述更新为净额口径依据；D6 新增两条（`D6-1-tb-amount` 科目码纠正说明 +
    `d6_impairment_tb resolver` 备抵科目纠正说明，与 Wave 1.2 子代理发现的
    `_IMPAIRMENT_ACCOUNT_CODES` 缺陷一致）；D5 新增「预设已移除」诚实化说明条目
    （从 2 条变 3 条，同步更新参数化测试 `_EXPECTED_TIER_B_COUNT`）。

- [x] 6. 守卫收口与浏览器实测
- [x] 6.1 全量回归（后端 `d_cycle_extraction` + 各循环；前端 D 类相关）
  - _Requirements: 8.4_
  - 后端：`d_cycle_extraction` 全量 + `test_note_d1_structure` + `test_note_d2_structure`
    + `test_d_prefill_extension` + `test_d_prefill_d567_fix` + `test_d_cycle_revenue_properties`
    + `test_template_library_mgmt_integration` + `test_template_library_properties`
    + `test_linkage_graph_build_invariant_pbt` + `test_h1_two_level_chain` +
    `test_f1_formula_presets`（跨循环消费 `prefill_formula_mapping.json` 的守卫，
    确认本次 D5/D6/D7 sheet 名修正未影响其他循环读取）—— **949 passed / 2 skipped**。
  - 前端：`d1 D1 d2 D2 d3 D3 d5 D5 d6 D6 d7 D7` 子串过滤 —— **108 files / 1366 passed**。
  - 未跑全仓 `pytest tests/`（该命令混入大量与本 spec 无关的并发会话预存在失败噪声，
    已改为针对性回归，符合"改动前先确认预存在基线"铁律，避免把噪声误判为本次引入）。
  - Vite 200：18 个本次改动的 D2/D6 相关文件全部 transform 200。

- [x] 6.2 CI job `d-cycle-extraction-chain`
  - _Requirements: 8.4_
  - 已在 Wave 1 完成时随 `.github/workflows/governance-checks.yml` 一并新增（含
    `note-d2-structure` job），本轮确认两个 job 仍在文件中且引用路径正确。

- [x] 6.3 逐循环浏览器实测（chrome-devtools + postgres 只读），数据用后复原
  - _Requirements: 8.5_
  - _Properties: 5, 6, 11_
  - **D2 净额口径**（项目 `2aa00f57`/wp `7c1ee1f6` D2-1 审定表）：postgres 直查
    `trial_balance` 1122=151,273,548.62 / 1231-02=406,014.85；UI 显示
    「试算平衡表数（1122）：150,867,533.77」= 151,273,548.62 − 406,014.85，
    分文不差，证明 render 回退标量已改净额且与 Tier A 预设同口径。
  - **D2 附注模板结构对齐**（八、5 国企侧）：点击「同步到附注」→ 提示「已同步 31 行到
    附注模块「八、5 应收账款」」；postgres 复核 `disclosure_notes.table_data` 落库
    11 张子表（含 Wave 2 修正后的正确表名「(7) 应收账款转移继续涉入形成的资产、负债
    的金额」，无孤儿/旧名残留）；`_sub_table_columns` 含两级 `group`（账面金额/坏账准备）
    列元数据，证明模板 columns 已生效并随载荷正确投影。
  - **D6 科目族纠正**：postgres 核实 `report_config.BS-011` 四准则一致
    `TB('1141','期末余额')`；`tb_balance`/`trial_balance` 中 `1141` 全量 5 个项目均为 0
    （合法空值，非代码缺陷——原 `1402` 误用时该科目在项目 `52c04ed1` 有 136,268.13
    非零数据，纠正后不再误算入合同资产）；D6-1 UI 显示「与试算平衡表核对（科目1141）：
    - / 核对一致」，取数链路正确指向 1141 而非 1402。
  - **D6 账龄枚举贯通**（Task 4.1，D6-NOTE-LISTED 上市披露 Tab「按组合计提坏账准备的
    合同资产」）：新增组合 → 账龄列显示 `el-select`（非自由文本）+「按账龄段生成」按钮
    + 提示「账龄口径：1年以内 / 1-2年 / 2-3年 / 3-4年 / 4-5年 / 5年以上」；点击后一次性
    生成全部 6 档账龄行（label 为下拉选中值，非手打字符串），核对与 `useAgingConfig`
    的 5 年段默认输出逐字一致。
  - **数据已复原**：测试期间新增的账龄组合行（6 行，金额全 0）与空组合已通过 UI 逐行
    删除操作复原为 `checklist_responses.remark = '[{"groupName":"","rows":[]}]'`（惯性
    空状态，功能上等价于测试前的「无该 item_id 记录」，不影响任何审计数据或后续同步）。
  - 未测部分：D2 上市侧披露 Tab（同一循环载荷结构已由国企侧验证覆盖，上市/国企共用
    同一 `d2NoteSectionMap.ts` 列定义）；D3/D5/D7 因 Wave 4 结论为「无需改动」（附注
    模板本就与源模板一致，只是取数溯源侧补了 `tb_source_codes` 输出，无 UI 可见变化）
    故未逐一开浏览器验证，改用 Wave 1.5 的后端单测覆盖（`test_d4_d5_d7_render_prefill_integration`
    等）。

## Notes

### Wave 2 进度（2026-08-01）

**结论：D2 的表名/行骨架已由并发会话两个归档 spec（`d2-ar-disclosure-template-alignment`
31/31 / `d2-ar-disclosure-soe-alignment` 25/25）处理过**（国企侧 `_aligned_by` 已带值），
**但两者都只做了同步载荷（前端 `d2NoteSectionMap.ts`），没把 `columns`/`guidance` 写回
模板 JSON** —— 复核实证上市 17 表 `columns`/`guidance` 全缺 + `_aligned_by=None`，
国企 13 表 `columns`/`guidance` 全缺 + 仍残留 4 处占位行/`header_label` 假行。

**列定义权威源改为直接镜像前端**：前端已声明 16 个 `ColumnDef` 常量（经并发 spec 实测校验
落库正确），本脚本原样翻译到 Python，不重新裁决，避免与已验证的同步载荷产生第二套真源。

**新建** `fix_note_d2_ar_structure.py`（复用 `_note_structure_kit` 共享工具）：
- 补齐两版 30 表 `columns`（`flat`/`group` 表态）+ `guidance`（纯文本，取 F5-* 校验预设 —
  D2 沿用共享编号池，未单独分配 F4）
- 全部 `rule(rows=None)`：**不动既有行骨架**，避免与并发会话数据打架
- 国企 4 处占位行清理（新增 `_clean_placeholder_rows`）
- `--check` 归零、二次运行幂等空操作

**🔴 复核过程中抓出并修掉一处真实表名漂移**：上市表名「转移应收账款且继续涉入形成的
资产、负债」漏「的金额」二字——源模板 R172 字面「…资产、负债**的金额**」。原因是**源
xlsx 里有 4 个含「附注」字样的 sheet**（不带 `D2-1` 后缀的两个编号（1）~（7）逐字对应
附注模板；带 `D2-1` 后缀的两个是底稿内示例/占位 sheet，内容顺序不同甚至写「其他应收款」
字样，不是本章节裁决源），首次核对时误用了带后缀的 sheet 导致 44 条守卫断言集体误判，
换回正确 sheet 后只剩这 1 处真实漂移。已改名（`aliases` 原地改名防孤儿）+
`D2_LISTED_OBSOLETE_TABLE_KEYS` 追加旧名供孤儿清理 + 前端契约测试同步更新 2 处断言。

**已复核为「非缺陷」的一项**：国企侧账龄表源模板**不带编号**（隐含在「应收账款附注」
总标题下的第一部分，（1）从「按坏账准备计提方法分类披露」才开始），前端常量把它命名成
「（1）按账龄披露应收账款」是与上市侧对称的有意规范化，非抄错——该表不参与源模板
编号交叉裁决，其余 6 张国企固定表逐字对应。

**新增守卫** `test_note_d2_structure.py`（255 例，含 **openpyxl 直读源 xlsx** 表名交叉
比对 + 反向自检 + guidance 禁 markdown + 5 张上市/2 张国企组合分表列结构同构断言）。
CI 新增 job `note-d2-structure`。

回归：后端 `d_cycle_extraction` + `test_note_d1_structure` + `test_note_d2_structure`
**906 passed / 2 skipped**；前端 D2 相关 22 文件 **408 passed**；Vite 200。

### Wave 1 进度（2026-08-01）

**Task 1.1 ✅ 守卫先行且证明非空转**：新建 `test_d_cycle_account_codes.py`（19 例），
首跑即把三处缺陷全部判红（D6 两条 / D2 一条 / D5 两条），标准科目表加载自检 14 例通过。
守卫三层：① 预设科目码 ∈ 标准科目表 ② 科目码属于**本循环报表行**的科目集合
（这条抓出 D6 的 `1402`：码是真科目，但属存货循环）③ 逐循环口径断言。

**Task 1.4 ✅ D5 预设已移除**（Requirement 4(b)）：活体实证 `trial_balance` 与
`tb_balance` 的 `1124%` 均 **0 行**，标准科目表亦无 `1124` → 原预设求值恒为 0。
移除后在 JSON 里留 `_D5_removed` 块记录完整依据 + 守卫
`test_d5_has_no_tier_a_preset` 钉死（防日后凭常识加回来）。
**顺带发现平台级缺陷**：`report_config` 的 BS-007 应收款项融资四准则也都写
`TB('1124')` → 该报表行同样恒为 0，只报告不改。

**Task 1.2 ✅ D6 全链 `1402`→`1141`（56 文件）**：预设 + render（`_D6_ACCOUNT_PREFIX`、
`trial_balance` 查询）+ `tb_aux_balance` 明细归集 SQL + 两个 auto resolver + AI prompt +
`account_package_registry.json`（**真实配置不只文案**）+ 锚点登记 + 11 份复核提示词 +
14 份后端测试 fixture + 19 个前端文件（含 `writebackTrialBalance` 的 `account_code`、
EventBus `accountCode`、序时账查询参数、抽凭 `account-code`）。
**刻意不动 F2 的 `1402`**（在途物资在存货语境是对的）。
回归：`d_cycle_extraction` **408 passed**（新增守卫 +1）/ D6 相关 **384 passed**；
Vite 200；`get_diagnostics` 0。

🔴 **顺带修掉子代理报的同款缺陷：D6 备抵科目也是错的**。原 `_IMPAIRMENT_ACCOUNT_CODES`
两版都不对 —— 先是 `['140201','1402.01']`（错科目族），纠正 1402 后机械平移成
`['114101','1141.01']`（**把借方资产科目 1141 的子科目当备抵**，仍取不到减值数据）。
标准科目表实证真值：**`1142 合同资产减值准备`（credit）** 与
**`1231-05 坏账准备-合同资产`（credit）**，两者并列（客户二选一）。
同时修掉前端 `D6TabAdjustment.vue` 两处文案里的 **`1403`**（= 原材料，存货类）
与 resolver 的**死文档**（docstring 声称有「第 2 步模糊匹配」，代码里根本没有）。
新增守卫 `test_d6_impairment_codes_are_real_allowance_accounts`（含误用值黑名单）。

**Task 1.3 预设侧已改，render 侧待接**：
D2 → `TB('1122','期末余额') - TB('1231-02','期末余额')`。

**既有基线（未触碰，勿误判为回归）**：`test_d_cycle_export_import_verification.py` +
`test_e_cycle_audit_determination_writeback.py` 两文件 **61 failed / 50 passed**
（componentType 断言，D0~D6 与 E 循环全红）；两文件与 `wp_code_overrides.json`
在工作树均干净 → HEAD 上就红。

🔴 **D6 的危害比预想严重**：活体 `tb_balance` 的 `1402`（在途物资）**有 12 行 /
136,268.13**，而 `1141`（合同资产）0 行 → 错误预设不是「恒空」，而是**把存货的钱
当合同资产显示在审定表里**。

🔴 **又一批「测试镜像 bug」**：改预设后 10 条既有测试打红，全是钉死旧错误表达式的断言
（`test_d2_render_prefill_integration` 3 / `test_d6_tier_a_preset` 4 /
`test_d4_d5_d7_render_prefill_integration` 2 / `test_prefill_presets` 1）。
说明这些测试从来只校验「预设能加载」，**从不校验科目码对不对** ——
与 D1 的 `_D1_EXPRESSION` 同款。已全部改到实证口径并在常量处写明双证依据。
回归：`backend/tests/d_cycle_extraction` **407 passed / 2 skipped**。

### 复用 D1 的既有结论（不重复踩坑）

- **Tier A 预设与 render 回退标量必须同口径**（D1 实测：原值 vs 净值差异恰好等于备抵）。
- **`tb_source_codes` 必须有前端消费方**，否则是 dead output。
- **`flat` 要同时加在模板 `columns` 与同步载荷两处**。
- **guidance 必须纯文本**（平台级 `fix_note_bold_markers.py` 会剥 `**`，两脚本会打架）。
- **测试替身要按 SQL/params 区分原值与备抵两次 `trial_balance` 查询**，否则备抵 == 原值、
  净额恒为 0，把守卫变成噪声。
- **`npx vitest run -t ""` 会把全部用例判 skipped**；位置参数是子串过滤不是 glob。

### 明确不做

- **`listed_standalone` 的 BS-006 用整个 `1231`**（含票据/其他应收款的坏账）→ 报表行虚减，
  属平台级报表配置数据缺陷，只报告不改（影响全部项目报表）。
- **`note_template` 全库 `report_row_code` 陈旧**：平台级 data-hygiene，不在本 spec。
- D4 营业收入：损益类循环，取数口径（`trial_balance` 发生额）与资产类不同，另立 spec。
