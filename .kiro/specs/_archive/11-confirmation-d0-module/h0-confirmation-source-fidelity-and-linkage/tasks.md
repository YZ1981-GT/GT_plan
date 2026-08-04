# Implementation Plan: H0 函证源模板保真度与联动补齐

> 源模板唯一裁决者：`backend/wp_templates/H/H0 固定资产循环函证.xlsx`（9 sheet 全 visible）
> 参照范式：`e0-confirmation-completion`(18/18) · `f0-confirmation-linkage-and-structural-enhancement`

## Overview

四条互不耦合的改造线，共 24 个任务 / 7 wave：

| 线 | Requirements | 任务 |
|---|---|---|
| 枚举线 | R1 / R7 | 1~4 |
| 下区线 | R2 / R3 | 5~11 |
| 列集线 | R5 / R6 | 12~15 |
| 补列/话术/stub/预设线 | R4 / R8 / R9 / R10 / R11 | 16~21 |
| 收口 | R12 | 22~24 |

## Tasks

- [x] 1. 后端枚举 additive 扩展
  - `system_dicts.py`：`confirmation_account_type` 追加 9 项 H 类科目（标签逐字取 `wp_system_map.json` H 循环科目名）；`confirmation_subject` 同样追加 9 项
  - 新增 `confirmation_send_channel`（邮寄/跟函/电子函证/其他，逐字 `X0-2!C7`）
  - 新增 `confirmation_sample_purpose`（`A. 大额`/`B.异常`/`C.余额为0`/`D.账龄长`/`E.随机`，**空格与标点原样保留**）
  - 新增 `confirmation_addr_verify`（6 项，逐字 `X0-2!L7`）
  - `confirmation_reply_method` 追加 `纸质原件`/`电子函证`/`其他介质`
  - **既有取值一字不动**（新列表以旧列表为前缀）
  - _Requirements: 1.2, 1.6, 7.1, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 2. 后端枚举守卫 `tests/test_confirmation_dicts_h0.py`
  - openpyxl `coord in dv.sqref` 逐格取 H0-2 `C7`/`L7`/`P7` + H0-1 `C8` + H0-6 `D7` 的 `formula1`，拆分后与字典标签逐字比对
  - 断言 9 项 H 类标签与 `wp_system_map.json` 逐字一致
  - additive 断言：既有取值为新列表前缀
  - 反向自检：改任一既有取值必红 / 采信镜像列 sqref 必红
  - 更新 `tests/test_confirmation_dicts.py` 的 `EXPECTED_COUNTS`
  - _Requirements: 12.1, 12.2 / Property 1, 19, 21_

- [x] 3. 前端字典单一真源收敛
  - `coordination/confirmationDicts.ts`：`CONFIRMATION_DICTS` 增 3 个新 key；新增 `CONFIRMATION_DICT_FALLBACK`（组件内置回退的唯一真源）与 `H0_DICT_KEYS`
  - `GtConfirmationSummary.vue`：`dictData` 改为引用 `CONFIRMATION_DICT_FALLBACK`，删除 7 项字面量数组与该处 TODO
  - `GtConfirmationDiffReconcile.vue`：`subjectOptions` 改为引用同一真源，删除 13 项字面量与该处 TODO
  - _Requirements: 1.1, 1.3, 1.4_

- [x] 4. 前端字典守卫 `h0DictConsumption.spec.ts`（第一部分）
  - 断言两个组件源码中无品种字面量数组（`stripComments()` 后判定 + 断言原始源码曾含被禁字样）
  - 三方交叉：后端字典标签 ↔ `CONFIRMATION_DICT_FALLBACK` ↔ `H0_MATRIX_DEFAULT_CATEGORIES`
  - 反向自检：回退常量改回 7 项必红
  - _Requirements: 12.4 / Property 1, 2, 30_

- [x] 5. 后端账面金额取数 `services/four_table/h0_book_amounts.py`
  - `H0CategorySpec` + `H0_MATRIX_CATEGORY_SPECS`（品种 → `H{n}_ACCOUNT_SPEC`，复用 `h{n}_account_scope.py`）
  - `resolve_h0_book_amounts(ctx, categories)` → `H0BookAmountResult`（`amounts` / `source_codes` / `conflicts`）
  - 走 `semantic_account_resolver` + `leaf_aggregation.select_leaves`/`aggregate_leaves`
  - **源码不得出现 H 类标准码作查询前缀**（只允许在 `source_ref` 与注释）
  - 槽 `found=False` → `amount=None`；单品种异常隔离不影响其他品种
  - **先用 `inspect.signature` 核实共享件实参形态**（`select_leaves` 是同步纯函数，`await` 它会被 `except` 吞成 warning）
  - _Requirements: 3.2, 3.3, 3.8_

- [x] 6. 后端取数守卫 `tests/four_table/test_h0_book_amounts.py`
  - 品种映射齐备（矩阵默认 3 品种 + 枚举 9 品种全部有 spec 或显式登记「无对应循环」）
  - 源码级断言：无标准码字面量作前缀；不读 `project_context.tb_amount`
  - `found=False` → `None`；异常隔离
  - 反向自检：注入读 `tb_amount` 的实现必红
  - _Requirements: 3.4 / Property 8, 9_

- [x] 7. 后端加法式注入 `_inject_h0_book_amounts`
  - `wp_render_config_helpers.py` 新增注入器：**wp_code 前缀非 H0 直接 return**
  - 写 `project_context.h0_book_amounts` + `h0_book_source_codes`，不改 `rows`/`_format`
  - `wp_render_config.py` 的 `confirmation-summary` 注入点追加调用（**不注册 `RENDERER_DISPATCH`**）
  - fail-open：整体失败 → 不注入任何键（与「解析成功但无科目 → 键存在值为 null」可区分）
  - _Requirements: 3.5, 3.6_

- [x] 8. 后端注入守卫 `tests/test_h0_book_amount_injection.py`
  - 六枢纽 `html_data` 注入前后深比较逐字节不变
  - H0-1 新增两键且 `rows`/`_format` 不变
  - 「注入失败」与「无科目」两态可区分
  - _Requirements: 12.5 / Property 10_

- [x] 9. 前端矩阵纯函数 `confirmation/h0SummaryMatrix.ts`
  - `H0_MATRIX_METRIC_LABELS`（8 条，逐字 `C30:C37`）+ `H0_MATRIX_DEFAULT_CATEGORIES`（3 条，逐字 `E29/F29/G29`）
  - `H0MatrixCategory`（key 形态 `cat_{seq}`，**不用 label**）+ `H0MatrixCell`（含 `origin: auto|manual|derived|absent`）
  - `buildH0SummaryMatrix`：R31/R33/R36 = `sumByCategory(rows, cat, 'amount'|'confirmed_amount'|'alt_confirmed')`；5 个比例走 `safeRatio`（复用 `f0SummaryAggregation`）
  - `h0MatrixOverrideItemId` + `H0_MATRIX_CATEGORIES_KEY`
  - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [x] 10. 前端下区文字真源 `confirmation/h0SummaryLowerZone.ts`
  - `H0_LOWER_ZONE_TEXTS`（逐字 + 跨格合并，`W30+W31` 合并为整句）
  - `H0_LOWER_ZONE_BLOCKS`（`audit_note.title='三、审计说明'` + `sourceText='二、审计说明'` 登记源模板笔误）
  - `H0_SAMPLE_SELECTION_FIELDS`（6 条，标签逐字 `J29/J30/J31/J32/J34/J35`）
  - `H0_AUDIT_NOTE_SECTIONS`（5 条，标题逐字 `S29/W29/S33/S34/S37`）
  - `H0_REFERENCE_CONCLUSIONS`（A/B/C 逐字 `A66:B68`）+ 三个持久化 key 前缀
  - _Requirements: 2.6, 2.7, 2.8, 2.9, 2.10_

- [x] 11. 前端下区组件 `H0SummaryLowerZone.vue` + 接入
  - 四块渲染：矩阵（动态品种列 + 增删改名 + `el-collapse`）/ 样本选择 6 字段 / 审计说明 5 小节（每节带 AI 辅助 + `GtReviewTrigger`）/ 审计结论（参考结论 A/B/C 琥珀色只读上下文）
  - 账面金额行可编辑（`WpAmountInput`），空值 = 撤销覆盖；`absent` 显示「本项目无此科目」info tag
  - 取数溯源面板（品种 → 报表行 → 科目码 → `resolved_from`），复用 `WpFourTableSourcePanel` 或 `WpSemanticAccountSourcePanel`
  - `GtConfirmationSummary.vue` 加 `isH0` 门控接入；金额显示走 `displayPrefs.fmtAmount`（**setup 顶层 inject，不是模块导出**）
  - `checklist_responses` 批量保存按 `itemId` 去重
  - _Requirements: 2.1, 3.1, 3.7, 3.9_

- [x] 12. 前端矩阵与下区守卫
  - `h0SummaryMatrix.spec.ts`：三聚合行逐值 / 比例 null 语义 / PBT `Number.isFinite(v) || v === null` / key 形态与重名不撞键（反向自检 key 取 label 必红）
  - `h0SummaryLowerZone.spec.ts`：常量内部一致性 + 跨格合并条目不含拆句 + 笔误登记存在
  - `h0DictConsumption.spec.ts`（第二部分）：`h0_book_amounts` 有真实消费点且在 `buildH0SummaryMatrix` 入参链上（反向自检：入参改 `undefined` 必红）
  - _Requirements: 12.4 / Property 4, 5, 6, 7, 11_

- [x] 13. 前端列集扩展 `confirmationColumnSpec.ts`
  - 新增 `CYCLE_COLUMN_LABEL_OVERRIDES`（只有 `H0` 一个 key，12 处）
  - `CYCLE_EXCLUDED_COLUMNS.H0` 填 `contact_person`/`contact_phone`/`currency`
  - `CYCLE_VARIANT_COLUMNS.H0` 加 `row_conclusion`
  - `resolveConfirmationColumns` 对命中 override 的列做**浅拷贝**（不 mutate BASE 常量对象）
  - _Requirements: 6.1, 6.2, 6.4, 6.5_

- [x] 14. 前端列集守卫 `confirmationColumnSpecH0.spec.ts`
  - H0 含 `row_conclusion`、不含 3 项剔除列、12 处 label 逐字（比对基准由后端守卫导出的表头 fixture 提供）
  - key 仍 ⊆ `CONFIRMATION_SOURCE_MANIFEST.H0`
  - **六枢纽输出快照零回归** + 先调 H0 再调 D0 断言 BASE 未被污染
  - 剔除列不销毁持久化值
  - _Requirements: 6.3, 6.6, 6.7, 12.5 / Property 16, 17, 18_

- [x] 15. 前端带入联动 `h0SummaryFromEntityVerify.ts` + 入口
  - `H0_PULL_FROM_ENTITY_VERIFY`（7 条，带 `sourceColumnIndex` = VLOOKUP `col_index_num`）
  - `pullH0SummaryFromEntityVerify`（手工优先 / 幂等 / 空索引跳过 / 回报三类统计）
  - `GtConfirmationSummary.vue` 加「从 H0-2 带入」按钮（`isH0` 门控）+ 「仅补空值 / 覆盖全部」二选一 + 命中统计 toast + 未匹配索引号可见
  - 守卫 `h0SummaryFromEntityVerify.spec.ts`（Property 15）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 16. 带入映射与源模板交叉锁死守卫
  - 后端守卫解析 H0-1 `D8/G8/J8/K8/M8/Q8/R8` 七条公式的 `col_index_num`（2/3/4/10/16/19/22），导出为 fixture
  - 前端守卫比对 `H0_PULL_FROM_ENTITY_VERIFY[].sourceColumnIndex` 与 fixture 逐条一致，且 `sourceField` 对应的 H0-2 列字母与 index 一致
  - _Requirements: 5.6 / Property 14_

- [x] 17. H0-2 补列（R8）
  - `entityVerifyTypes.ts` additive 补 8 字段（`provided_zipcode` / `provided_email_fax` / `second_entity_*` 6 项）
  - `EntityVerifyDashboard.vue` 渲染第二次发函 6 列组（按 `is_second_send` 条件展开）+ 提供侧邮编/邮箱传真
  - 「地址不一致的核实方式」列绑定 `confirmation_addr_verify` 枚举
  - 两条审计说明（`C25`/`C26`）就地展示为只读方法论上下文（琥珀色）
  - 守卫 `entityVerifyH0Columns.spec.ts`（Property 23）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 18. H0-3 跟函话术补源模板要素（R9）
  - `memoTemplates.ts` 通用三段话术补陪同情况占位（`A10`）与工号占位（`A13`/`A17`）
  - 新增第三方致电回访段（`A18`/`A19`）为独立可选段
  - `FollowupDashboard.vue` 3 个核对点标签改为逐字 `A23:A25`；签名行语义保留
  - **E0 五段银行话术逐字不变**
  - 守卫 `memoTemplatesH0.spec.ts`（Property 24）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 19. H0-5 源模板结构回归（R4）
  - 补「一、样本选取标准与规模」6 字段（标签与占位逐字 H0-5，**去掉抄自 F0-5 的「贷方发生额」措辞**）
  - 补「二、检查过程记录」自由记录区（持久化 `H0-5-check-record-free`）
  - 补「三、审计说明」/「四、审计结论」（若缺）+ 编制说明 3 条逐字
  - 四区块渲染处加「平台增强（源模板此处为空白记录区）」标注 + 依据说明
  - `BLOCK_COLUMN_CONFIGS_H05` 四个 title 对齐 `ALTERNATIVE_BLOCK_MANIFEST.H05`
  - **不删既有四区块与 `companies[]` 存量数据**
  - 守卫 `alternativeH05SourceFidelity.spec.ts`（Property 12, 13）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 20. 四个 stub 实装（R10）
  - `GtConfirmationReliability.handleJumpD01` / `GtConfirmationDiffReconcile.handleJumpD01` → 按 `getCycleConfirmationMeta(wpCode).summaryCode` 跳转，**删除 `'D0-1'` 字面量**
  - `GtConfirmationFraudRisk.handleJumpRef` → 按索引号跳转
  - `GtConfirmationDiffReconcile.handleDelete` → 实装删除选中行
  - 复用 `navigateToCycleSheet` / `useConfirmationNavigation`，不新造导航
  - `handleJumpB50` 不动（已实装）
  - 守卫 `confirmationStubWiring.spec.ts`（Property 25, 26）
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 21. H0 公式预设纠偏（R11）
  - `scripts/fix/fix_h0_prefill_presets.py`（`--dry-run`/`--check`/`--apply` + round-trip 自检 exit 2）
  - `sheet` 改 `函证结果汇总表H0-1`；取数条目按 Task 5 结果决定「覆盖全品种科目」或改 `PLACEHOLDER` + description 说明
  - 只触碰 H0 块，其余 257 块逐字节不变
  - 守卫 `tests/test_h0_prefill_presets.py`（Property 27, 28）
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 22. 源模板事实守卫 `tests/test_h0_source_template_facts.py`
  - 9 sheet 名 + `sheet_state=visible` 全断言
  - H0-1 28 列表头逐字 + 5 段合并区
  - 下区四块锚点文字逐字（含跨格合并与 `S28` 笔误原文）
  - 8 指标标签逐字
  - 7 条 VLOOKUP `col_index_num` 导出 fixture
  - 五处真实 DV（`coord in dv.sqref` 逐格）
  - `审定表H0-1` tab 不存在
  - H0A 11 条程序 + 编号 1,2,3,5…12（**漏 4 属源模板事实**）+ 常规★/备选
  - H0-7 19 条与 `fraudRiskPresets.PRESET_FRAUD_ITEMS` 逐字一致（含 H0-7 的 J19/J20 举例**无行偏移**，与 D0-8/F0-8 的 J18/J19 不同 —— 登记该事实）
  - 反向自检：采信镜像列 sqref 必红 / 改任一断言值必红
  - _Requirements: 12.1, 12.2, 12.3 / Property 3, 7, 14, 19, 27, 29_

- [x] 23. CI job 挂载
  - `governance-checks.yml` 新增 `h0-confirmation-fidelity`（后端 5 个守卫文件 + `fix_h0_prefill_presets.py --check`）
  - 新增 `h0-confirmation-frontend`（前端 8 个守卫文件）
  - _Requirements: 12.6_

- [x] 24. 实测与回归
  - **真实 DB 直跑**：≥3 项目跑 `resolve_h0_book_amounts`，含客户用 `1651/1652`(H8) 与 `2651`(H9) 的项目，逐品种打印 `amount`/`resolved_from`/`found`，断言非标准码项目两品种取到数
  - **浏览器实测**：H0-1 录 ≥2 行不同品种明细 → 矩阵三聚合行 + 比例出数 → 增列改名 → 手工覆盖账面金额 → 「从 H0-2 带入」命中统计 → `postgres` 查 7 类新键落库 → **数据完整复原**
  - H0-5 / H0-2 / H0-3 / H0-4 / H0-6 / H0-7 逐 Tab 打开核对改造点
  - **回归**：六枢纽 `resolveConfirmationColumns` 快照 / `four_table` 后端全量 / `confirmation` 前端全量（失败清单与改造前基线逐条比对，新增失败 = 0）
  - 清理本会话 `tmp_*` 诊断产物
  - _Requirements: 12.7, 12.8_

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "枚举线（其余三线的前置：品种枚举是矩阵与下拉的共同基础）",
      "tasks": [1, 2, 3, 4],
      "parallel": [[1], [2, 3], [4]]
    },
    {
      "wave": 2,
      "name": "后端账面金额取数与注入",
      "tasks": [5, 6, 7, 8],
      "parallel": [[5], [6, 7], [8]]
    },
    {
      "wave": 3,
      "name": "前端下区四块（矩阵 + 固定文字 + 组件）",
      "tasks": [9, 10, 11, 12],
      "parallel": [[9, 10], [11], [12]]
    },
    {
      "wave": 4,
      "name": "列集与带入联动",
      "tasks": [13, 14, 15, 16],
      "parallel": [[13], [14, 15], [16]]
    },
    {
      "wave": 5,
      "name": "补列 / 话术 / H0-5 结构回归（三者互不耦合，可并行）",
      "tasks": [17, 18, 19],
      "parallel": [[17, 18, 19]]
    },
    {
      "wave": 6,
      "name": "stub 实装与公式预设纠偏",
      "tasks": [20, 21],
      "parallel": [[20, 21]]
    },
    {
      "wave": 7,
      "name": "守卫收口 / CI / 实测",
      "tasks": [22, 23, 24],
      "parallel": [[22], [23], [24]]
    }
  ],
  "dependencies": {
    "2": [1],
    "3": [1],
    "4": [3],
    "5": [1],
    "6": [5],
    "7": [5],
    "8": [7],
    "9": [1, 3],
    "10": [],
    "11": [7, 9, 10],
    "12": [9, 10, 11],
    "13": [],
    "14": [13, 22],
    "15": [3],
    "16": [15, 22],
    "17": [1],
    "18": [],
    "19": [],
    "20": [],
    "21": [5],
    "22": [],
    "23": [2, 6, 8, 12, 14, 16, 17, 18, 19, 20, 21, 22],
    "24": [23]
  }
}
```

## Notes

### 明确不做（防下个会话重启）

1. **其余六枢纽的枚举绑定改造**（R7.8）：D0/F0/G0/K0/L0/H0 的 `X0-2!C7`/`P7`/`L7` 与 `X0-1!C8` 四组 DV 实测**完全同构**，故新枚举声明为七枢纽共享；但把它们绑定到其余六枢纽的列会波及各自既有断言与已录数据，另立 spec。本 spec 只把 H0 接为首个消费者。
2. **删除 H0-5 既有四区块**：源模板「二、检查过程记录」确为空白区（R10:R19 无表头），四区块 30+ 列是源外增强 —— 但 `alternativeBlockManifest` 已诚实登记依据，且存量项目可能已录数据。本 spec 只做「标注 + 补源模板缺段」，不销毁。
3. **把 `confirmation-summary` 注册进 `RENDERER_DISPATCH`**：会劫持全部七枢纽载荷。账面金额走既有加法式注入通道。
4. **补 H0A 程序编号 4**：源模板 `函证程序表H0A` 的 A7~A17 就是 `1,2,3,5,6,7,8,9,10,11,12`，漏 4 属源模板事实，守卫按原文断言。
5. **改 `BASE_CONFIRMATION_COLUMNS` 的 label**：会波及其余六枢纽，一律走 `CYCLE_COLUMN_LABEL_OVERRIDES`。
6. **重复实现 `handleJumpB50`**：已由 `e0-confirmation-completion` Task 15 实装，七枢纽共享。
7. **改 `fraudRiskPresets.PRESET_FRAUD_ITEMS`**：19 条与 H0-7 `A6:A24` 已逐字一致，无需动（仅在守卫中补登记「H0-7 的 J19/J20 举例无行偏移」这一事实）。

### 已核实无需改的现状

| 项 | 结论 |
|---|---|
| `cycleConfirmationMeta.H0` | 7 个索引号（H0-1~H0-7）与源模板逐字一致 ✓ |
| `confirmationColumnSourceManifest.H0` | 28 列标签清单与源模板逐字一致 ✓（只是实现侧未渲染 `row_conclusion`） |
| `fraudRiskPresets` 19 条 | 与 H0-7 `A6:A24` 逐字一致 ✓ |
| `handleJumpB50` | 已实装 ✓ |
| `reliabilityTypes` | H0-6 全部 14 列均有等价字段 ✓ |
| `wp_code_overrides` H0 8 条 | componentType 映射齐备 ✓ |
| `wp_template_metadata_dn_seed` H0 | 9 sheet 齐备（含 H0-4）✓ |
| `alternativeBlockManifest.H05` | 四区块已登记 `sourceExtra` + 依据 ✓（仅 title 漂移待修） |
| `confirmationLinkageMatrix.H0` | 四条联动链 `implemented` ✓（但**不含** X0-1←X0-2 带入，那是本 spec R5 新增的第五条） |

### 实施顺序上的两个硬约束

- **Wave 1 必须先做**：品种枚举是矩阵（Task 9）与两处下拉（Task 3）的共同前置；先做矩阵会得到「品种选不出 → SUMIF 恒空」的假完成。
- **Task 14/16 依赖 Task 22**：列 label 与 VLOOKUP 列序的比对基准由后端源模板守卫导出 fixture（前端无法直读 xlsx），故守卫任务 22 要早于两个前端交叉守卫。

### 风险登记

| 风险 | 缓解 |
|---|---|
| 共享组件改动波及其余六枢纽 | 每条改造线都有「六枢纽输出/载荷逐字节不变」的零回归断言（Property 10, 17, 22） |
| 加法式注入沦为死代码 | Property 11 断言消费点在 `buildH0SummaryMatrix` 入参链上，反向自检入参改 `undefined` 必红 |
| 品种列写死列数 | Property 6 断言动态列 + key 形态 + 重名不撞键 |
| 账面金额照抄 F0 口径 | Property 9 断言不读 `project_context.tb_amount`（实测 H1~H10 零命中） |
| 守卫断言空转 | 每个源码型守卫先 `stripComments()` 并断言原始源码含被禁字样；每个保真度守卫含反向自检 |
| 并发会话改同一批文件 | 幂等脚本 round-trip 自检；改共享文件用 `str_replace` 不用整文件覆盖；改后查全部消费方诊断 |

## 实施记录（Wave 1~3 + Task 13，2026-08-04）

### 完成情况：13/24（Task 1~13）

| Wave | 任务 | 产出 | 测试 |
|---|---|---|---|
| 1 | 1~4 | `system_dicts.py` +4 枚举/+21 取值；`confirmationDicts.ts` 单一真源 + 两组件字面量归零 | 后端 73 / 前端 33 |
| 2 | 5~8 | `four_table/h0_book_amounts.py`；`_inject_h0_book_amounts` | 后端 28 + 28 |
| 3 | 9~12 | `h0SummaryMatrix.ts` / `h0SummaryLowerZone.ts` / **`H0SummaryLowerZone.vue`**（专属四块组件）+ 汇总表 `isH0` 接入 + H0 AI 6 section 登记 | 前端 27 + 44 + 增补 |
| — | 13 | `CYCLE_COLUMN_LABEL_OVERRIDES` + `CYCLE_EXCLUDED_COLUMNS.H0` + `send_channel` / `h0_row_conclusion` | 前端 24 |

**回归**：`confirmation` 全量 **1337 例 / 1335 passed / 2 failed**（改造前 1240 passed / 5 failed）
—— 新增 95 例通过、修复 3 条失败、**新增失败 0**。剩余 2 条为预存在基线
（`GtG0Confirmation.integration.spec.ts` 的 G0-4 componentType 断言）。

**Vite transform**：6 个改动文件全部 200。

### 实施中修正设计的 3 处（均为实证驱动）

1. **R7.2 改设计：渠道另立字段 `send_channel`，不改 `confirmation_method` 绑定。**
   原 R7.2 写「把 H0-1『函证方式』列改绑渠道枚举」。实证 `ConfirmationDetail.vue` 的可确认金额派生
   依赖 `row.confirmation_method === '消极式'`（消极式未回函 → 视同相符），改绑会让该派生分支永久失效。
   → 新增行级字段 `send_channel`（label「函证方式」，绑 `confirmation_send_channel`），
   `confirmation_method` 保持积极式/消极式语义并在 H0 上改 label 为「函证类型（积极式/消极式）」。
   requirements.md / design.md Property 20 已同步更正。

2. **矩阵品种 key 需持久化单调计数器（`H0_MATRIX_SEQ_KEY`）。**
   首版 `nextH0CategoryKey` 取「现有最大 seq + 1」→ 删掉 `cat_3` 再增列又得 `cat_3`，
   历史手工覆盖值 `H0-1-matrix-cat_3-0` 会串到新品种列。守卫先打红，改为持久化计数器
   + 保留一条反向自检用例（不传计数器必复用旧 key）。

3. **AI 走 H0 专属端点而非通用 `/ai/generate-text`。**
   H0 已有 `_h0_confirmation_ai.py`（`POST /workpapers/{id}/h0/ai-generate`，
   载荷 `{section, existingContent, relatedContext}`）。通用端点未登记这些 section 会 400 被 catch 吞掉
   → 6 个 section 以 kebab-case 登记进 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS`
   （每条 ≥40 字 + `_NO_FABRICATION` 约束），前端守卫交叉锁死「前端 aiSection ⊆ 后端已登记」。

### 顺带修掉的预存在缺陷（非本 spec 范围，1 行修复）

**`e0-send-list/__tests__/sendListSpec.spec.ts` 的 12 条断言从未执行过。**
`REPO_ROOT` 写死回退 7 级，而该目录到仓库根实为 **8 级** → 解析到 `audit-platform`，
`audit-platform/backend/data/...` 不存在 → 整文件 ENOENT（在全量报告里表现为「文件级失败」而非断言失败，
极易被当成噪声跳过）。改为按哨兵文件向上查找后 **15 例全部通过**（无隐藏回归）。
本会话新写的守卫已统一采用哨兵查找法 —— 且踩到同族陷阱：
哨兵**必须是具体文件**，`audit-platform/backend/app/routers` 目录也存在（历史遗留空目录），
只判目录会在 `audit-platform` 层提前停下。

### 关键实证结论（供后续 wave 与其它循环复用）

1. **H1~H10 十个 render 策略 `tb_amount` 零命中** → H0 矩阵账面金额不能照抄 F0 的
   `project_context.tb_amount` 口径（照抄必得 `undefined`）。H 循环下发的是
   `tb_values`（按槽前缀键）+ `tb_source_codes`。
2. **9 个品种的槽键映射已逐个实证命中**（`gross` + 各自备抵槽），
   H2 的 `eng_mat` 与 H4 的 `cip` 是跨品种核对槽，**不得并入本品种**（否则双算）。
3. **六枢纽 X0-2 的三处 DV 完全同构**（`C7` 渠道 / `P7` 回函介质 / `L7` 核实方式），
   `X0-1!C8` 选样目的五项亦同构 → 新增枚举声明为七枢纽共享，H0 是首个消费者。
4. **判 DV 必须 `coord in dv.sqref` 逐格测试**：openpyxl 打印的 `JF/JK/TG` 等镜像列 sqref
   不落在真实列上；照打印顺序取值会得出「H0-1!G 列 DV = 跟函/邮寄/电邮/其他」的错误结论
   （真实 H0-1 只有 C/L/N/X 四列有 DV）。已在守卫里加反向自检钉死。

### 下一步（Task 14~24）

Task 14/16 依赖 Task 22（前端读不了 xlsx，比对基准由后端源模板守卫导出 fixture）→
建议顺序 **22 → 14 → 15 → 16 → 17/18/19 → 20/21 → 23 → 24**。

## 实施记录（Wave 4~7，2026-08-04）

### 完成情况：23/24（Task 1~23；Task 24 的浏览器实测部分待做）

| Wave | 任务 | 产出 | 测试 |
|---|---|---|---|
| 4 | 14~16 | `confirmationColumnSpecH0.spec.ts` / `h0SummaryFromEntityVerify.ts` + 入口 + 守卫 / 后端导出 VLOOKUP fixture 并交叉锁死 | 前端 48 + 21 |
| 5 | 17~19 | H0-2 补 8 字段 + 第二次发函 6 列组 + 地址核实 `el-select` / H0-3 通用三段话术补陪同·工号·第三方回访 / **H0-5 源模板结构回归** | 前端 23 + 59 + 21 |
| 6 | 20~21 | 四个 stub 实装（跳转按循环派生）/ `fix_h0_prefill_presets.py`（3 项变更，`--check` 归零） | 前端 17 / 后端 12 |
| 7 | 22~23 | `test_h0_source_template_facts.py`（80 例，xfail 已移除）/ CI 两 job | 后端 80 |

**后端回归**：`four_table` 全量 **1305 passed / 0 failed**；
`four_table` + 5 个 H0 守卫文件合计 **1500 passed / 0 failed**。

### H0-5 源模板结构回归（任务 19）

源模板逐格实证（`替代程序H0-5`，`max_col=29`）：

| 锚点 | 内容 | 改造前平台 |
|---|---|---|
| `A6` 一、样本选取标准与规模 | 6 字段：`A7` 测试范围 / `I7` 特定样本 / `A8` 抽样总体 / **`I8` 确定的抽样样本量** / `A9` 抽样方法 / `I9` 抽样过程 | label 写「样本量」；`test_scope` 占位抄了 F0-5 的「、贷方发生额…」 |
| `A10` 二、检查过程记录 | R11:R19 **空白自由记录区** | 标题被占用为「二、余额汇总与检查比例」 |
| `A20` 三、审计说明 | — | 「三、检查过程记录」 |
| `A23` 四、审计结论 | — | 「四、审计说明与结论」（说明与结论合并） |
| `A28` 编制说明 | `1、函证替代程序` ①②③ + `2、概述`（1）（2） | 只有顶部 alert 显示第 ③ 条 |

产出：新建字面真源 `alternativeH05/h05SourceFidelity.ts`（6 字段 + 四段标题 + 编制说明
两组 + 源外增强标注 + 自由记录区常量，全部带 `labelRef`/`anchor` 指向源模板单元格）；
组件四段重排 + 6 字段由常量驱动 + 自由记录区（落 `AlternativeCompany.check_record_free`，
随 `buildPayload()` 持久化）+ 底部 `details` 编制说明；`BLOCK_COLUMN_CONFIGS_H05` 四个
title 对齐 `ALTERNATIVE_BLOCK_MANIFEST.H05`（`①验收权属检查`/`②采购证据检查`/
`③新增资产检查`/`④抵押/租赁证据`）；守卫 `alternativeH05SourceFidelity.spec.ts`（21 例，
读后端 `test_h0_source_template_facts.py` 抽 (anchor,label) 对与 3 条 tips 做**跨文件交叉锁死**）。

**不删既有四区块**（30+ 列源外增强），只加「平台增强（源模板此处为空白记录区）」标注 + 依据。

### 四个 stub 实装（任务 20，顺带修掉共享导航件的 http 客户端错配）

- `GtConfirmationReliability.handleJumpD01` / `GtConfirmationDiffReconcile.handleJumpD01`
  → `getCycleConfirmationMeta(props.wpCode).summaryCode` + `navigateToCycleSheet`，删 `'D0-1'` 字面量
- `GtConfirmationFraudRisk.handleJumpRef` → 取条目自身 `source_ref` 首段编码跳转
- `GtConfirmationDiffReconcile.handleDelete` → 实装删除；**选中态在 `DiffReconcileMaster` 内**，
  故把 `delete` 事件改为携带 `rowIds: string[]`（不带载荷父层拿不到选中行）
- 🔴🔴 **`coordination/navigateToCycleSheet.ts` 此前从未成功解析过 wp_id**：
  它 `import api from '@/utils/http'` 却按 apiProxy 语义读 `res.wp_id`。
  `@/utils/http` 的默认导出返回 **AxiosResponse**（拦截器只把 `{code,message,data}`
  信封剥进 `response.data`、**仍返回 response**）→ `res.wp_id` 恒 `undefined`
  → 永远走「未找到 X 底稿」分支。唯一存量消费方（E0-6「跳转汇总表」）同样静默失效。
  已改 `import { api } from '@/services/apiProxy'`（平台 20+ 处 `wp-id-by-code` 的写法）。
- `handleJumpB50` 未动，守卫含它的零回归断言。

### H0 公式预设纠偏（任务 21）

`fix_h0_prefill_presets.py`（`--dry-run`/`--check`/`--apply` + round-trip 自检 exit 2 +
写后复检 + 「非 H0 块逐字节不变」断言），3 项变更已 `--apply`：

1. `sheet`「审定表H0-1」→「**函证结果汇总表H0-1**」（函证枢纽没有审定表，9 sheet 全实证）
2. `account_codes` `['1601']` → 九品种参考码（仅展示；`primary_code` 已无 TB 类 cell 消费）
3. 两条 `TB('1601',…)` → `PLACEHOLDER`（沿用 E1 数字货币范式），description 写明真源
   `four_table/h0_book_amounts` + `semantic_account_resolver` + 「本项目无此科目」语义

同时**移除** `test_h0_source_template_facts.py::test_prefill_preset_h0_sheet_points_to_real_tab`
的 `xfail(strict=True)` 标记（留着会 XPASS 报错，那正是当初设 strict 的意图）。

### 实测（任务 24，真实库直跑部分已完成，浏览器实测待做）

新增只读诊断 `backend/scripts/diagnose/verify_h0_book_amounts_live.py`
（11 个「项目 × 年度」组合，逐品种打印 `amount` / `resolved_from` / `gross − net_of`）。

**正向证据（语义定位有效）**：

| 项目 | 品种 | 解析到的码 | 金额 |
|---|---|---|---|
| `2aa00f57`/2025 | 使用权资产 | `1651 − 1652`（**非标准码**） | 66,389,073.02 |
| `2aa00f57`/2025 | 租赁负债 | `2651`（**非标准码**） | 70,311,201.45 |
| `2aa00f57`/2024 | 使用权资产 | `1651 − 1652` | 107,683,697.46 |
| `52c04ed1`/2025 | 使用权资产 / 租赁负债 | `1651 − 1652` / `2651` | 1,755,435.53 / 1,987,236.67 |
| `a7fc75e5`/2025 | 使用权资产 / 租赁负债 | `1651 − 1652` / `2651 − 2702` | 5,696,084.83 / 4,108,683.78 |

→ 按标准码 `1641/1642`、`2601` 硬查这两个品种在**五个**项目会取空。
「本项目无此科目（None）」与「余额为 0（0.00）」两态实测可区分
（`52c04ed1` 投资性房地产 = None；`b39809ed` 固定资产 = 0.00）。

### 🔴 实测挖出的两个真缺陷（均已修 + 守卫，含反向自检）

**缺陷 1（跨循环串味，H3 是活的错数 / H8·H9 是潜伏态）——「裸通名兜底」把别的循环的备抵抓走。**

`match_slot_in_chart` 按 `names` 声明顺序取**第一个精确命中**的名字。DB 实证：

| 裸名 | 全库唯一对应 | 谁是正主 |
|---|---|---|
| `累计折旧` | `1602`（standard 10 项目 / client 7 项目都是裸名） | **H1 固定资产** |
| `累计摊销` | `1702`（standard 10 / client 8） | 无形资产（非 H 循环） |
| `累计折耗` | `1632`（standard 6 / client 1） | **H5 油气资产**（正主，保留裸名） |
| `未确认融资费用` | **`2602`（租赁负债）与 `2702`（长期应付款）两个都叫这个** | 各自 |

而 `1525 投资性房地产累计折旧` / `1526 投资性房地产累计摊销` 只在 4~5 个项目的科目表里存在
→ H3 原来把裸名列作第二兜底名，科目表缺 1525/1526 时精确命中 1602/1702，
**把固定资产的累计折旧 + 无形资产的累计摊销从投资性房地产原值里扣掉**：

| 项目 | 修复前 | 修复后 |
|---|---|---|
| `4f6dbc36`/2025 | **−21,601,944.08** | 0.00 |
| `df5b8403`/2025 | **−11,322,704.22** | 0.00 |
| `f064f5e4`/2024 | **−21,864,702.78** | +7,266,202.27 |

`exclude_names` 拦不住（裸名里没有「固定资产」这类关键词）。
修法 = 删掉裸名兜底，只留带主体前缀的专名 + `fallback_standard_codes`
（缺该科目 → `found=False` → **不扣减**，宁缺勿造）。已同款处理
`h8_account_scope.accum_dep`（潜伏态，专名先命中故行为逐字不变）与
`h9_account_scope.unearned_finance`（潜伏态，`2702` 全库余额为空）；
**H1 与 H5 保留裸名是对的** —— 1602/1632 本就是它们自己的科目。
守卫在 `tests/four_table/test_h3_account_scope.py`（新增 12 例，含 3 条反向自检：
把裸名加回去必然命中 1602 / 2702）。

**缺陷 2（本 spec 自己的代码）—— H0 聚合用了裸 `aggregate_leaves`，忽略两种符号约定。**

`c8621493`/2025 的 `2651 租赁负债` 家族：
`2651.01 租赁付款额 98,176.48(credit)` + `2651.02 未确认融资费用 3,956.64(**debit**)`，
父额 94,219.84。裸 `aggregate_leaves` 原样求和得 **102,133.12**（把借方性质的 contra
子科目**加**了进去）。修法：

- 改走 `resolve_leaf_totals`（两种约定都算、取与**父额**勾稽成立的那一种），
  且**不得**先 `select_leaves()` —— 父科目行是符号约定的判定依据，剔除即退化；
- 新增「备抵槽若是原值科目族的**子科目**则跳过扣减」规则
  （父族聚合已按方向净掉，再减一次是双算），跳过项如实记进 `net_of_skipped`；
- `parent_check`（各科目族的叶子和 − 父额差额）随溯源下发。

实测 `c8621493` 租赁负债 102,133.12 → **94,219.84（= 父额，diff 0）**；
`a7fc75e5` 4,360,873.46 → 4,108,683.78。守卫新增 5 例（含反向自检：
裸 `aggregate_leaves` 对同一份数据必得 102,133.12）。

### 剩余（任务 24 的浏览器实测）

- H0-1 录 ≥2 行不同品种 → 矩阵三聚合行 + 5 个比例出数 → 增列改名（`cat_{seq}` 不撞键）
  → 手工覆盖账面金额 → 「从 H0-2 带入」命中统计 → `postgres` 查 7 类新键落库 → **数据复原**
- H0-5 / H0-2 / H0-3 / H0-4 / H0-6 / H0-7 逐 Tab 打开核对改造点
- 前端 `confirmation` 全量与改造前基线逐条比对

### 浏览器实测（任务 24 收口，2026-08-04）

环境：项目 `c8621493` / **H0 工作簿** wp `9478ca80`（9 sheet）。
🔴 实测入口必须是 **wp_code=`H0` 的工作簿**，不是 `wp_code=H0-1` 的单 sheet 遗留记录
（后者 `_is_multi_sheet=False` → 既有分支都不赋值 → `html_data` 为 `null`，
`_inject_confirmation_population` 与 `_inject_h0_book_amounts` 都被 `isinstance(dict)` 挡掉，
组件自加载。属既有平台行为，已登记不在本 spec 修）。

**H0-1 下区（Wave 3 + Task 15）**

| 验证点 | 结果 |
|---|---|
| 四块渲染 | 一、函证情况 / 二、样本选择（6 字段）/ 三、审计说明（5 段，各带 AI + 复核）/ 四、审计结论（参考结论 A/B/C）✓ |
| 「源模板编号笔误已修正」标注 | ✓（S28 写「二、审计说明」，实为第三块） |
| 账面金额自动取数 | 固定资产 **13,063.72** / 租赁负债 **94,219.84** / 工程物资 0.00（与真实库直跑逐分一致） |
| 动态品种列 | 3 列默认 + 增列「油气资产」→ 4 列，各带 ✎ 改名 / ✕ 删除；`cat_1..cat_4` 稳定 key |
| 矩阵聚合 | 录 2 行（固定资产 10,000 / 租赁负债 50,000）→ 发函 10,000·50,000、比例 **76.55%**（=1e4/13,063.72）与 **53.07%**（=5e4/94,219.84）、回函确认 10,000、回函/发函 100.00% —— 8 个指标逐格正确 |
| 手工覆盖账面金额 | 输 99999.99 → 显示 `99,999.99`，落 `H0-1-matrix-cat_1-0`；**刷新后仍在**，其余品种仍走自动取数 |
| 落库键 | `H0-1-matrix-categories` / `H0-1-matrix-seq` / `H0-1-matrix-cat_1-0` / `H0-1-lower-sample-population` |
| 覆盖率红线 | 「覆盖率偏低，请评价函证程序的充分性并考虑扩大替代程序范围」✓ |
| 取数溯源面板 | 品种/来源底稿/报表行/口径/解析出的科目码/定位来源 六列；租赁负债显示 **2651**（非标准码）+「客户科目表(按名)」✓ |
| 「从 H0-2 带入」 | 入口打通（改造前恒报「未找到底稿 H0-2」，见下方缺陷 4）；H0-2 无数据时诚实回报「H0-2 尚无核实记录，或该底稿未编制」。**有数据的端到端带入未测**，映射由 `h0SummaryFromEntityVerify.spec.ts`(21) + 后端 VLOOKUP 交叉锁死覆盖 |

**H0-2（Task 17）**：详情表单实测含提供侧「邮编 / 邮箱、传真」+ 第二次发函 6 列组
（发函日期/发函方式/发函结果/地址/邮编/联系人/联系电话/传真/信息核查一致）✓

**H0-5（Task 19）**：8 个 `data-testid` 全在；四段编号为
一、样本选取标准与规模 / 二、检查过程记录 / 三、审计说明 / 四、审计结论 ✓；
无任何改造前的错位段名；「确定的抽样样本量」+ L8 样本计算器提示 ✓；
源外增强标注 ✓；自由记录区 ✓；四区块标题与 manifest 一致 ✓；
**「贷方发生额」措辞已归零** ✓；顶部提示条与底部编制说明取自源模板 ✓

**数据复原**：`working_paper.parsed_data` 回 `{}`、`checklist_responses` 回 **0 行**
（逐条核对：删除的 4 个键均为本轮测试写入）。唯一残留 = `updated_at` 时间戳（列语义如此，非数据）。

### 🔴 浏览器实测挖出的另 4 个缺陷（均已修 + 守卫）

**缺陷 3（本 spec 引入的 P0）—— 下区录入 `emit('save', {itemId, value})` 会整体覆盖 sheet 载荷。**

`confirmation-summary` 的宿主 save 处理器把载荷写成 `parsed_data.html_data[sheetName]`。
实测点一次「增加品种」后 `html_data['函证结果汇总表H0-1']` 变成
`{"itemId":"H0-1-matrix-seq","value":"4"}` —— 函证行被清掉，该 sheet 下次打开
**退化成「此底稿使用旧格式，仅支持只读查看」**（`_format` 丢了）。
下区录入是 itemId 维度的，改为直接 `http.put('/api/workpapers/{id}/checklist-responses', {items:[...]})`
（与 `useF2FormData.saveImmediate` 等 40+ 处同形）。修后实测 4 个键正确落 `checklist_responses`
且 `parsed_data` 保持 `{}`。

**缺陷 4 —— 两处跨底稿取数的 http 客户端 / 端点错用（同 F0 已记的同族坑）。**

- `loadH0Responses` 漏 `/api` 前缀（`utils/http` baseURL 是 `/`、vite 只代理 `/api`
  → 拿回 index.html，`Array.isArray` 判否后静默空 map）。并发会话在自己的 G0 函数注释里
  已登记「既有 `loadH0Responses` 就漏了 `/api`」，本轮修掉。
- `fetchH0EntityVerifyRows` 两错叠加：端点写 `/projects/{id}/workpapers/wp-id-by-code`
  （平台唯一入口是 `/api/custom-query/wp-id-by-code`），且用 `@/utils/http` 却按 apiProxy
  语义读 `res.wp_id`（前者返 AxiosResponse → 恒 `undefined`）→ 按钮**恒报「未找到底稿 H0-2」**。
  改走 `import { api } from '@/services/apiProxy'`。

**缺陷 5 —— 共享导航件 `navigateToCycleSheet` 从未成功解析过 wp_id。**
同款 http 形态错配（`import api from '@/utils/http'` + 读 `res.wp_id'`）→ 永远走
「未找到 X 底稿」分支。唯一存量消费方（E0-6「跳转汇总表」）一并静默失效。已修。

**缺陷 6 —— 冲突告警渲染成裸元组。**
后端 `conflicts` 是三元组 `[槽键, 报表公式给的码, 按名定位到的实际码]`，前端 `v.map(String)`
渲染出 `impairment,1601,1602,1606,1603`（读不出含义，违反「审计 UI 必须有逻辑追溯能力」）。
新增 `H0_SLOT_LABELS`（镜像后端 `h_cycle_specs` 槽 label，守卫读 py 源码交叉锁死）+
翻成「「减值准备」槽：报表行公式引用 1601,1602,1606，而本项目科目表按名定位到 1603
—— 已以科目表为准，请复核报表行公式。」实测四条冲突全部可读。

### 回归

- 后端：`four_table` **1305 passed / 0 failed**；`four_table` + 5 个 H0 守卫 **1500 passed / 0 failed**
- 前端 `confirmation` 全量 **1290 例 / 1289 passed / 1 failed**
  —— 唯一失败 `alternativeBlockManifestContract.spec.ts` 的 **G06** 用例，属并发 G0 会话
  正在改的 `blockColumnConfigsG06.ts`（`git status` 该文件为 ` M`），非本轮回归

### 遗留（已登记，不在本 spec 修）

1. **单 sheet 遗留 wp_code（`H0-1`/`H0-2`…）render 出 `html_data=null`** ——
   `_is_multi_sheet=False` 时 confirmation 组件既拿不到初始载荷也拿不到两处注入。
   真实用户路径是 `wp_code=H0` 工作簿，故不阻塞；属 `wp_index` 双命名族的平台级议题。
2. **`AlternativeD05Master` 的「从 D0-1 带入」按钮标签在七个循环上都写 D0-1** ——
   H0-5 上应显示「从 H0-1 带入」（handler 本身已是 `handleImportH01`，只是标签硬编码）。
   共享组件级文案，需按 `getCycleConfirmationMeta(wpCode).summaryCode` 派生。
3. **函证「完整表格视图」编辑永不落库**（七枢纽共享，memory 已记的既有 P0）。
4. **H0-2 有数据时的端到端带入**未在浏览器验证（映射已由跨文件守卫锁死）。
5. **并发会话的 HMR 中间态会让共享组件在浏览器里报
   `Property "isG0" was accessed during render but is not defined`** ——
   磁盘源码是好的，硬刷新（`ignoreCache`）即恢复。判「组件是否真坏」必须先硬刷新。
