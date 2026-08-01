# Requirements Document

## Introduction

H 循环（H0~H10）披露→附注对齐工作已逐循环收口，但复盘（2026-07-31）暴露 8 项遗留。经只读探针实证后，其中 6 项确认为真实缺陷、1 项为误报（H3 AI 实为正常）、1 项需活体环境。

本 spec 收口这 8 项。其中两项是**平台级**（波及全部循环，不止 H）：

- `text_sections` 里的 markdown `**` 残迹：**38 段 / 22 章节**（listed 20 + soe 2）+ `guidance` 22 处。附注正文与 Word 导出会把 `**` 原样渲染给用户。**关键约束**：其中 2 段的 `**` 是**不成对**的脱敏占位（`诉讼金额为**元`），无脑剥离会破坏语义。
- `note_template` 的 `report_row_code` **系统性陈旧**：134 行全部指向旧编号体系（`固定资产→BS-014` 而现 `BS-014` 是其他流动资产；`短期借款→BS-031` 而现 `BS-031` 是使用权资产）。今日 inert（134 行全部同时带 `account_codes`，`REPORT()` 不触发），但属定时炸弹：`DISCLOSURE_NOTE_FORMULA_ENABLED` 一旦开启且未来新增无 `account_codes` 的行即取错值。

H 循环专属四项：

- H8/H9 四个披露 Tab 的「AI 辅助」「复核」按钮 `emit('open-ai')` / `emit('open-review')`，而宿主 `GtH8RightOfUseAssets.vue` / `GtH9LeaseLiabilities.vue` **零处理器**（只有 `change`/`navigate-sheet`/`refresh-complete`/`save`）→ 按钮可见可点、零网络请求。同族坑在 K5/K7 已实证（marker stub 空转）。H1/H2/H4/H5/H6 披露 Tab 则**压根没有 AI 按钮**，违反平台铁律「多 section 底稿每个文本区都要 AI 辅助」。
- H4 无 `h4NoteSectionMap.ts` → `gen_note_wp_sync_registry.py` 与 `disclosureSheetNameRegistry.spec.ts` 都扫不到它（两者都按 `{code}NoteSectionMap.ts` 命名 glob），「同步就绪度」视角里 H4 不存在。
- 勾稽面板范式只在 D1/F1/H1/J1/N1 五个循环落地，H2~H10 缺失；且五份引擎各写一套 `eqCheck`/`subsetCheck`，无共享件。
- 上市变体从未活体验证（唯一 `template_type=listed` 项目 `0ec33ac9` 的 `entity_type=soe` → 前端变体门关闭）；H1/H2 只测过空底稿。

## Requirements

### Requirement 1: 平台级 markdown `**` 残迹清理

**User Story:** 作为审计报告使用者，我希望附注正文与 Word 导出里不出现 `**` 这类 markdown 语法残迹，以便交付物可以直接对外。

#### Acceptance Criteria

1. WHEN 幂等脚本以 `--check` 运行 THEN 系统 SHALL 报告 `note_template_{listed,soe}.json` 中 `text_sections` / `guidance` / `headers` / `rows[].label` 里所有**成对** `**` 的出现位置与条数
2. WHEN 脚本以 `--apply` 运行 THEN 系统 SHALL 把 `**xxx**` 剥离为 `xxx`，且**不修改**任何不成对的 `**`
3. WHEN 某段落 `**` 出现次数为奇数 THEN 系统 SHALL 原样保留该段并在输出中单独列示（脱敏占位语义，如 `诉讼金额为**元`）
4. WHEN 脚本重复运行 THEN 第二次 SHALL 报告 0 处变更（幂等）
5. WHEN 后端守卫测试运行 THEN 系统 SHALL 断言全库无成对 `**`，并含反向自检（对内联 fixture 断言检测器确实能抓到成对 `**` 且放行不成对 `**`）
6. WHEN 剥离后 THEN 段落的非 `**` 字符 SHALL 逐字不变（仅删除标记本身）

### Requirement 2: H8/H9 披露 Tab 的 AI 与复核接线

**User Story:** 作为审计助理，我希望 H8/H9 披露页的「AI 辅助」与「复核」按钮真的能用，以便不必手工撰写披露说明。

#### Acceptance Criteria

1. WHEN 用户点击 H8/H9 披露 Tab 的 AI 按钮 THEN 系统 SHALL 向 `POST /api/workpapers/{wpId}/ai/generate-text` 发起请求，body 为 `{section, prompt, context, existingContent}` 且 `context` 的每个值 SHALL 为字符串
2. WHEN AI 返回文本 THEN 系统 SHALL 回填到对应说明文本域并触发持久化
3. WHEN 组件处于只读态 THEN AI 按钮 SHALL 被禁用
4. WHEN AI 请求进行中 THEN 按钮 SHALL 显示 loading
5. WHEN 用户点击「复核」 THEN 系统 SHALL 打开平台复核对话框（`GtReviewTrigger` 或等价 composable），而非 emit 一个无人处理的事件
6. WHEN 守卫测试运行 THEN 系统 SHALL 断言 H8/H9 披露 Tab 源码内不存在「emit 一个宿主未声明的事件」形态的 AI/复核按钮

### Requirement 3: H1/H2/H4/H5/H6 披露文本域补 AI 辅助

**User Story:** 作为审计助理，我希望所有 H 循环披露页的说明文本域都有 AI 辅助，以便体验一致。

#### Acceptance Criteria

1. WHEN H1/H2/H4/H5/H6 任一披露 Tab 存在说明文本域 THEN 该文本域旁 SHALL 有 AI 按钮，且点击后真调 `/ai/generate-text`
2. WHEN 新增 AI section THEN 后端 `review_dialog._SECTION_PROMPTS` SHALL 登记对应 prompt，每条 SHALL ≥20 字且含「不得虚构」约束与源模板口径说明
3. WHEN 守卫测试运行 THEN 系统 SHALL 从前端文本域键集派生期望的 prompt id 清单并断言后端全部登记，且无孤儿 prompt

### Requirement 4: H4 补映射薄壳以进入 registry

**User Story:** 作为平台维护者，我希望所有有披露同步链路的循环都能被 registry 生成器与命名守卫扫到，以便「同步就绪度」视角完整。

#### Acceptance Criteria

1. WHEN `gen_note_wp_sync_registry.py --write` 运行 THEN 输出 registry SHALL 含 H4 条目，`note_section` 与 `sheet_name` 两变体齐备且与源 xlsx tab 名逐字一致
2. WHEN H4 薄壳建立 THEN 它 SHALL re-export 既有 `h4DisclosureSyncPayload` / `h4SoeDisclosureSyncPayload` 的 builder，不复制逻辑
3. WHEN 薄壳内的章节号/sheet 名字面量与被 re-export 模块的真源不一致 THEN 契约测试 SHALL 失败（交叉锁死防漂移）
4. WHEN 平台命名守卫运行 THEN 系统 SHALL 断言「凡存在 `{code}DisclosureSyncPayload.ts` 或 `{code}NoteSectionMap.ts` 的循环都能被 registry 扫到」，例外须在 allowlist 写明理由

### Requirement 5: 勾稽引擎共享件与 H 循环推广

**User Story:** 作为审计助理，我希望每个披露页都能实时看到内部勾稽是否成立，以便在同步到附注前发现录入错误。

#### Acceptance Criteria

1. WHEN 建立共享勾稽件 THEN 它 SHALL 提供 `eqCheck`（相等类，容差 0.01 元）与 `subsetCheck`（子集类）两种规则构造器，返回 `{label, rule, left, right, diff, level, detail, refs}` 形态
2. WHEN 既有 D1/F1/H1/J1/N1 五份引擎改为委托共享件 THEN 它们的既有测试 SHALL 零回归
3. WHEN 为 H2/H3/H5/H7/H8/H9/H10 建立勾稽规则 THEN 每条规则 SHALL 可由源 xlsx 判定（层间派生、子集约束、模板「—」列示约定），不得自造勾稽
4. WHEN 勾稽项无可比数据 THEN 面板 SHALL 显示「暂无可比对数据」而非报不一致
5. WHEN 勾稽有 error 级差异 THEN 面板 SHALL 提供追溯（`GtIndexChip`）与规则 tooltip

### Requirement 6: `report_row_code` 陈旧编号一次性重映射

**User Story:** 作为平台维护者，我希望 `note_template` 的 `report_row_code` 与当前 `report_config` 编号体系一致，以便附注公式灰度开启时不取错值。

#### Acceptance Criteria

1. WHEN 重映射脚本以 `--check` 运行 THEN 系统 SHALL 报告每条陈旧 `report_row_code`（当前编号下 `row_name` 与该附注行标签不符者）及其建议新编号
2. WHEN 某行标签在 `report_config` 中**无法唯一解析**到一个 `row_code` THEN 系统 SHALL 原样保留并单独列示为「待人工核对」，不得猜测
3. WHEN 脚本以 `--apply` 运行 THEN 系统 SHALL 仅改写能唯一解析的行，且不触碰 `account_codes` 与其它字段
4. WHEN 守卫测试运行 THEN 系统 SHALL 断言：凡带 `report_row_code` 的行，其标签在 `report_config` 里对应的 `row_code` 与所写值一致（无法解析者进 allowlist 并写明理由）
5. WHEN 脚本重复运行 THEN 第二次 SHALL 报告 0 处变更

### Requirement 7: 上市变体活体验证

**User Story:** 作为项目负责人，我希望上市变体披露链路至少被真实走通一次，以便相信它不是只在测试里绿。

#### Acceptance Criteria

1. WHEN 存在 `template_type=listed` 的项目 THEN 系统 SHALL 能在其上渲染 H 循环上市披露 Tab 并成功同步到对应上市章节
2. WHEN 用户在国企项目上打开上市披露 Tab THEN 系统 SHALL 显示「当前不适用」并零写入
3. WHEN 活体验证使用临时改库 THEN 验证后 SHALL 逐字复原（含 `text_content`、`last_sync_at`、`entity_type`）

### Requirement 8: H1/H2 真实数据端到端验证

**User Story:** 作为审计助理，我希望固定资产/在建工程披露在有真实四表数据的项目上跑通，以便金额与勾稽都被验证过。

#### Acceptance Criteria

1. WHEN 项目含真实 `1601`/`1604` 科目余额 THEN H1/H2 审定表未审数 SHALL 由四表叶子聚合预填，且叶子和等于父科目期末余额
2. WHEN H1/H2 披露录入完成并同步 THEN 附注子表金额 SHALL 与底稿一致，且层间派生（账面原值−累计折旧−减值准备=账面价值）成立
3. WHEN 验证结束 THEN 测试数据 SHALL 完整复原

## Glossary

| 术语 | 含义 |
|------|------|
| `**` 残迹 | md 重建脚本把 markdown 粗体标记原样落进 `note_template` 的 `text_sections`/`guidance`，附注正文与 docx 会字面渲染 |
| 不成对 `**` | 段落内 `**` 出现次数为奇数，语义是脱敏占位（`诉讼金额为**元`），必须保留 |
| marker stub 空转 | 按钮只 `emit` 一个宿主未处理的事件或只写 checklist marker，零网络请求；`get_diagnostics` 与 vitest 全绿 |
| 薄壳 map | `{code}NoteSectionMap.ts`，只 re-export 真源 builder + 内联章节号/sheet 名字面量，供 registry 生成器与命名守卫 text-scan |
| 勾稽 | 披露表内部数学一致性（层间派生、子集约束、小计=明细和），规则须可由源 xlsx 判定 |
| `report_row_code` | 附注行指向报表行的编号，真源是 `report_config` DB 表 |
| 变体门 | 前端按 `applicable_standards` 判定当前项目是否适用某准则变体，不适用则披露 Tab 显示「当前不适用」 |
