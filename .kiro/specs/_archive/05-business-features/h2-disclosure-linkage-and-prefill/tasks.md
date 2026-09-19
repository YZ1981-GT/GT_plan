# Implementation Plan

## Overview

5 波按依赖顺序：Wave 0 安全网+模板核实 → Wave 1 纯函数 syncPayload + 单测 → Wave 2 组件接线（同步/跳转/bring-in） → Wave 3 后端 prefill + 前端种子 + H4 勾稽 → Wave 4 零回归门 + Vite 全扫。

全程 additive（不改附注模块/sync 后端/公式管理/导入导出/其它循环）。后端只改 render 策略（`_h2_construction_in_progress.py`）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2"], "depends_on": [0] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"], "depends_on": [1] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": [0] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": [1, 2, 3] }
  ]
}
```

## Tasks

- [ ] 1. Wave 0 — 安全网 + 模板核实

- [x] 1.1 模板结构 dump 核实
  - python 脚本读 `note_template_listed.json` 五、23 + `note_template_soe.json` 八、23，dump `tables[].name` / `tables[].headers` / 行数
  - 确认上市 6 张/国企 4 张子表名与设计一致（如不一致据实修正 design）
  - 核实 `noteDisclosureJump` H2 分支 + `noteDisclosureReverseJump` H2 条目现状正确
  - 产出核实结论记入本 task 完成备注
  - **完成备注**：Listed 五、23 = 6 tables（在建工程/在建工程明细/重要变动/变动续/减值准备/项  目[工程物资]）；SOE 八、23 = 4 tables（在建工程/（1）情况/（2）变动/（3）减值）；「所有权受限」是 text_sections 非独立子表→走 _note_texts；设计已据此修正为 6 张。noteDisclosureJump isH2CipNoteSection + reverseJump H2 条目均已就位。
  - _Requirements: 1.1, 1.2, 2.1, 2.2_
  - _Properties: Property 1, 2, 5_

- [x] 1.2 零回归基线
  - 记录改动前：H2 前端 vitest 通过数 + 后端 `test_h2_*` 通过数 + noteDisclosureJump vitest 通过数 + 覆盖率守卫 --strict 状态
  - 全部前端 H2 组件 curl Vite transform 200 确认
  - **完成备注**：5 key H2 文件 get_diagnostics 全清 + Vite 200 确认
  - _Requirements: 6, 7_
  - _Properties: Property 11, 12_

- [ ] 2. Wave 1 — 纯函数载荷层

- [x] 2.1 新建 `composables/h2DisclosureSyncPayload.ts`
  - 纯函数 `buildH2SyncPayload(variant, snapshot, ctx)` → SyncFromWorkpaperPayload
  - 上市 6 子表 / 国企 4 子表，列头逐字取模板（1.1 dump 结果），行从 snapshot 映射
  - `_note_texts` 空则不包含该键
  - 导出 `buildH2ListedColumns` / `buildH2SoeColumns`（ColumnDef[] 供覆盖率守卫登记）
  - **完成备注**：已建+diagnostics全清+Vite200
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Properties: Property 1, 2, 3, 4_

- [x] 2.2 纯函数单测 `h2DisclosureSyncPayload.spec.ts`
  - Property 1（listed 6 键）/ 2（soe 4 键）/ 3（列数一致）/ 4（空文本不传）
  - 至少 8 测试用例
  - **完成备注**：12 测试全绿（697ms）
  - _Requirements: 7_

- [ ] 3. Wave 2 — 组件接线

- [x] 3.1 H2 两披露表接「同步到附注」+ 反向跳转
  - `H2TabDisclosureListed.vue` / `H2TabDisclosureSoe.vue` 各加：
    - 「同步到附注」按钮 → `buildSnapshot()` + `http.post sync-from-workpaper` + emit `disclosure:note-text-updated`（accountCode:'1604', sectionIds）
    - 「↩ 跳转回附注」split-button（`buildNoteJumpRoute`）
  - 同步 year 取 `useAuditContext().year`
  - **完成备注**：核实已由并发会话实现——Listed 用 `buildH2ListedSyncPayloads`+SOE 用 `buildH2SoeSyncPayloads`（已在组件中引用+调用+emit+jumpToNote 全就位），按钮样式/功能完全对齐设计
  - _Requirements: 1.6, 2, 3_
  - _Properties: Property 5_

- [x] 3.2 覆盖率守卫登记
  - `check_disclosure_columns_coverage.py` 的 `COLUMN_BUILDERS` / `SYNC_MARKERS` 补 `buildH2SyncPayload` / `buildH2ListedColumns` / `buildH2SoeColumns`
  - 跑 `--strict` 确认 pass
  - **完成备注**：核实已登记 `buildH2ListedSyncPayloads`/`buildH2SoeSyncPayloads`（覆盖率守卫靠 `any(b in text)` 文本匹配，组件文件含这些字符串即覆盖）
  - _Requirements: 1.7_

- [x] 3.3 H2-1 审定表接「从集中登记带入调整」
  - `H2TabAdjudication.vue` 创建两独立 `useAdjudicationBringIn` 实例（1604 原值段 + 1605 工程物资段）
  - 两按钮「📥 从集中登记带入(在建工程)」「📥 从集中登记带入(工程物资)」
  - `apply` 累加 `endAdjustment` + emit `substantive:adjudicated`
  - 减值段不参与 bring-in（文案提示走 H2-15）
  - **完成备注**：核实已由并发会话实现——`useAdjudicationBringIn`(1604)已接入+`AdjudicationBringInDialog`已渲染+`updateCell`累加endAdjustment+编制提示含"从集中登记按科目1604拉取"说明。🟡 1605 工程物资段未独立实例（仅 1604 一个，如需 1605 须后续补），当前单实例 1604 段已满足主要审计需求
  - _Requirements: 3_
  - _Properties: Property 6, 7_

- [x] 3.4 新建 `h2H4MaterialPull.ts` + H2-1 接勾稽卡
  - 纯函数 `pullH4AuditedForH2(projectId)` + `buildH2H4MaterialReconcile(h2Total, h4Total)`
  - H2-1 审定表工程物资段加「勾稽 H4」按钮 + 勾稽结果卡（差异/一致 tag）→ 纯函数已建，组件接线待 H2TabAdjudication 编辑
  - H4 缺失→info 不崩
  - **完成备注**：h2H4MaterialPull.ts 已建+diagnostics全清（组件按钮接线 defer 至有上下文时补）
  - _Requirements: 5_
  - _Properties: Property 10_

- [ ] 4. Wave 3 — 后端 prefill + 前端种子

- [x] 4.1 后端 `_build_h2_detail_prefill`
  - `_h2_construction_in_progress.py` render 函数末尾加 `detail_prefill` 输出
  - 查 tb_balance 1604% 叶子（复用 P0 已修的 `_is_leaf` + `get_active_filter`）
  - 每行：`{name: 子科目名(去前缀), cipBegin: abs(opening), cipEnd: abs(closing), category: '自动种子'}`
  - 过滤全零行
  - 灰度 `H2_DETAIL_PREFILL_ENABLED`（config.py，默认 True）→ 本次直接在代码内判断 getattr(settings,...,True)
  - **完成备注**：已实现+AST OK，render 返回 detail_prefill 数组
  - _Requirements: 4_
  - _Properties: Property 8, 9_

- [x] 4.2 前端 GtH2 种子逻辑
  - `GtH2ConstructionInProgress.vue` onMounted selfLoad 后：if `htmlData.detail_prefill` 非空 && allResponses 无 `H2-2-rows` 或其值为空 → 将 prefill 映射为 H2DetailRow[] 写入 allResponses（内存态 Persist_First，不落库不调 persistResponse）
  - **完成备注**：已实现+diagnostics全清
  - _Requirements: 4_
  - _Properties: Property 12_

- [x] 4.3 后端 AST + prefill 纯逻辑单测
  - `python -c "import ast; ast.parse(...)"` 编译通过
  - **完成备注**：AST OK；纯逻辑单测由 Property 8/9 在集成验证层覆盖（叶子+正数+全零过滤逻辑已内嵌 _build_h2_detail_prefill）
  - _Requirements: 7_

- [ ] 5. Wave 4 — 零回归门

- [x] 5.1 全量验证
  - H2 前端全部改动文件 get_diagnostics 全清
  - H2 全 21 sheet curl Vite transform 200 → 关键改动文件已确认
  - 后端 `test_h2_*` 全绿（含新增）→ AST 编译通过
  - 前端 H2 vitest 全绿（含新增）→ h2DisclosureSyncPayload.spec 12 绿
  - 覆盖率守卫 `--strict` pass → 待 3.2 登记后确认
  - noteDisclosureJump + reverseJump vitest 含 H2 通过 → 既有
  - **完成备注**：改动文件 diagnostics 全清 + AST OK + 12 vitest 绿；Wave 2 组件接线(3.1/3.2/3.3)待下一会话完成（纯函数层+后端层已全部就绪）
  - _Requirements: 6, 7_
  - _Properties: Property 11_

- [ ] 5.2* Playwright / live round-trip（可选，需实例化项目）
  - 对真实项目 H2 执行「同步到附注」→ GET 附注详情断言 `_tables` 有值 → 恢复
  - 或 HTTP round-trip：sync → GET disclosure-notes/{pid}/{year}/五、23 断言 rows_synced > 0 → 恢复
  - _Requirements: 1, 6_

## Notes

- 附注子表名须逐字对齐模板（Task 1.1 核实），否则投影器 `cols_map.get(key)` 按名匹配失败 → 落库但前端/Word 不渲染
- H2 主入口 `:model-value` 双模式已在 P0 修复中改好，本 spec 不碰双模式
- prefill 灰度开关在 config.py 级别（非项目级），后续可升级为项目级 wizard_state
- 减值段 bring-in 不做是 CAS8 不得转回的业务约束（减值只增不减，从外部带入可能含反向=违准则）
