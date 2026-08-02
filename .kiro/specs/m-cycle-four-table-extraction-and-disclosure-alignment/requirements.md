# Requirements Document

## Introduction

M 循环（权益类 M1~M10）存在系统性缺陷：后端 render 硬编码科目码取数（10 个策略无一走 `four_table/` 共享件）、预设科目整体错位、前端 13 个披露 Tab 无同步链路、附注模板列结构与源 xlsx 不一致。本 spec 目标是让 M 循环实现「四表入库 → 底稿刷新取数 → 披露推送 → 附注有数据」全链贯通。

## Glossary

| 术语 | 含义 |
|---|---|
| 浅合并 | 多个底稿各推不同子表到同一附注章节，按 key 合并（不覆盖对方的键） |
| 动态插行 | 源模板「可无限加行」区域，由 tb_balance 叶子或用户手动新增行 |
| 两级表头 | `ColumnDef.group` 父级 + 叶子列名（如「本期增减」下 5 子列） |
| OCI | Other Comprehensive Income，其他综合收益 |
| 权益备抵 | 库存股（4201），借方方向，减少所有者权益 |

## Requirements

### 1. 四表库动态取数（后端 render 改造）

#### 1.1 科目映射真源对齐
各策略必须从 `report_config` 动态解析科目（复用 `four_table/report_line_accounts`），不得硬编码科目码常量。科目映射真源表（DB 实证）：

| 底稿 | 报表行(listed / soe) | 公式 | 标准科目 |
|---|---|---|---|
| M1 应付股利 | BS-055 / BS-076(soe=其中应付股利) | None→兜底 | `2232` |
| M2 实收资本(股本) | BS-075 / BS-102 | `TB('4001')` | `4001` |
| M3 库存股 | BS-080 / BS-114 | None→兜底 | `4201` |
| M4 资本公积 | BS-079 / BS-113 | `TB('4002')` | `4002` |
| M5 盈余公积 | BS-083 / BS-118 | `TB('4101')` | `4101` |
| M6 未分配利润 | BS-084 / BS-125 | `TB('4104')` | `4104` |
| M7 专项储备 | BS-082 / BS-117 | `TB('4103')` | `4103`（注意 5 项目中 2 项无此科目） |
| M8 一般风险准备 | 无 / BS-124 | None→兜底 | `4302`（仅金融企业） |
| M9 其他综合收益 | BS-081 / BS-115 | `TB('3102')` listed / `TB('3102')` soe | `4003`（活体;3102 为旧准则编码） |
| M10 其他权益工具 | BS-076(listed) / BS-110 | None→兜底 | `4401` |

#### 1.2 叶子聚合取数
- `tb_balance` 查询必须按**前缀匹配**（`LIKE code || '%'`），不能精确匹配父码。
- 聚合必须取叶子（`select_leaves`）。
- 权益类贷方口径：`closing_balance` 按 `abs()` 归一（因存储约定借正贷负）。

#### 1.3 render 输出 `tb_source_codes` + `tb_values`
各策略 render 返回新增：
- `tb_source_codes: ReportLineAccounts.as_dict()`（取数溯源，前端展示）
- `tb_values: {begin, end, debit, credit}` 叶子聚合结果
- `adjudication_prefill: [{label, begin, end}, ...]`（按叶子科目名分类预填）

#### 1.4 公式预设纠偏
修正全部 10 个审定表块的科目码 + 块名对齐 + 删除 9 条硬编码客户编码 AUX 条目 + 删除不存在的 sheet（`分析程序M1-3`）+ `M8` 改 `4302` + `M9` 改 `4003` + `M10` 改 `4401`。新增明细表/披露表公式预设（`WP()` 底稿间联动）。

### 2. 披露表 → 附注同步链路

#### 2.1 M4/M5/M7 已完成（验证通过不动）
确认共享映射 `mEquityChangeNoteSectionMap.ts` + 自动同步 + 附注 `_aligned_by` 三项齐全。

#### 2.2 M1 浅合并推 K3 章节
M1 按 H4→H2 / L6→L5 范式推 K3 §五、42 / §八、42 的「应付股利」+「重要的超过1年未支付的应付股利」子表。M1 持有完整两表录入数据，K3 侧这两张表从不推送。需 `m1NoteSectionMap.ts`（引用 K3 章节号 + 子表名，不自建章节）；M1 同步载荷只含自己那两张表，按 key 浅合并。

#### 2.3 M2 实收资本/股本（两级表头）
- 上市（五、53）：`股本（单位：万股）` 两级 8 列（期初余额 | 本期增减{发行新股,送股,公积金转股,其他,小计} | 期末余额）+ 动态可扩行（`股份总数` 是唯一固定行）。
- 国企（八、58）：`实收资本` 两级 7 列（投资者名称 | 年初余额{投资金额,所占比例%} | 本期增加 | 本期减少 | 期末余额{投资金额,所占比例%}）+ 动态插行区（按 `tb_balance` 叶子 4001.xx 自动展开投资者行）。
- 需新建 `m2NoteSectionMap.ts`。

#### 2.4 M3 库存股（仅上市，标准变动表）
- 上市（五、56）：5 列 flat + 动态可扩行 + 6 段 `text_sections`。国企无该章节。
- 需新建 `m3NoteSectionMap.ts`。

#### 2.5 M6 未分配利润（固定行变动链）
- 上市（五、61）：4 列（项目 / 本期发生额 / 上期发生额 / 提取或分配比例）14 行固定 + 12 段 `text_sections`。
- 国企（八、63）：3 列（项目 / 本期金额 / 上期金额）13 行固定 + 1 段说明。
- 需新建 `m6NoteSectionMap.ts`。

#### 2.6 M8 一般风险准备
- 上市（五、60）：5 列变动表 + 动态插行区 + 1 段说明。**模板当前 `tables=0`** → 需补建表结构。
- 国企：源模板有披露 sheet（5 列同结构），但模板无章节 → **新建 `八、N` 章节**（`八、62` 与 `八、63` 之间插入，需编号重排或使用 sort_index 插位）。
- 需新建 `m8NoteSectionMap.ts` + 幂等脚本。

#### 2.7 M9 其他综合收益（多级复杂表）
- 上市（五、57）：两级 8 列 × 2 张表（资产负债表中 + 利润表中）+ 动态可扩行。
- 国企（八、79）：两级 7 列 × 2 张表（表(1) OCI 各项目 11 类/43 行 + 表(2) OCI 调节情况 9 列 × 8 行列转置）。
- 需新建 `m9NoteSectionMap.ts`。

#### 2.8 M10 其他权益工具（两级表头）
- 上市（五、54）：3 张表（基本情况 10 列 + 变动表两级 9 列 + 权益持有者相关信息 3 列）+ 5 段 `text_sections`。
- 国企（八、59）：1 张两级 9 列变动表 + 1 段说明。
- 需新建 `m10NoteSectionMap.ts`。

### 3. 附注模板结构对齐

#### 3.1 幂等脚本修订
新建 `backend/scripts/fix/fix_note_m_equity_structure.py`（用共享 `_note_structure_kit`），修复所有 M 类章节的 columns/guidance/行集/表名/text_sections：
- 五、53：两级表头重建 + 删 `header_label` 假行
- 八、58：两级 7 列 + `年初余额` 列头
- 五、54：3 表改名 + 两级 9 列 + text 修复
- 八、59：两级 9 列
- 五、56：补 columns flat 5 列 + guidance
- 五、57：两级 8 列 + 删 `可无限量添加行` 假数据行
- 八、79：两级 7 列 + 补表(2) + 补 11→合计行 + 修列名
- **五、60**：新建 5 列表 + 3 行骨架 + guidance
- **八、新增**：一般风险准备章节 + 5 列表 + 行骨架
- 八、63：修列名 + 删 `……` 占位行
- 五、61：修列名 + 补 columns + guidance

#### 3.2 后端守卫 + CI job
`test_note_m_equity_structure.py` + `note-m-equity-structure` CI job。

### 4. 前端全量替换 `el-input-number` → `WpAmountInput`

19 个披露 Tab 共 49 处 `el-input-number` 千分符从未生效。按 K 系 / D 系已验证范式替换。金额列用 `WpAmountInput`；比例/数量保留原控件。

### 5. 前端科目单一真源 + 溯源面板

为 7 个未覆盖循环（M1/M2/M3/M6/M8/M9/M10）各建 `mXAccountScope.ts`（运行态取 render 下发 `tb_source_codes`，常量只作兜底+展示），并在审定表 Tab 接入 `WpFourTableSourcePanel` 共用件。

### 6. AI 辅助修正

M9 国企 context 改从 render 取真实科目码（删硬编码 `4103`）；各 Tab 的 `handleAI` 确认真调 `/ai/generate-text`（非 marker stub 空转）。

### 7. 账龄枚举（仅 M1）

M1 上市「重要的超过1年未支付的应付股利」的行展示与 aging 判定复用 `useAgingConfig` 的首档边界（`within1.dayTo=365`），超 1 年判定按项目配置自动适配。

