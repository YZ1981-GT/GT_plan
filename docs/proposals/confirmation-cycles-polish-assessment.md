# 函证枢纽底稿逐 sheet 打磨评估（D0 为标准，评估 E0/F0/G0/H0/K0/L0）

> 2026-07-26 只读调研，未改任何代码。源模板经 openpyxl 逐 sheet 实测，组件经逐文件读码核对。
> 铁律：源模板有而组件没有 → 才算 gap；**源模板本来没有的一律不建议加**（宁缺勿造）。

## 一、架构前提（决定工作量分布）

**共享组件占绝大多数，per-cycle 只有替代程序**：

| 类别 | 组件 | 循环覆盖 |
|---|---|---|
| 共享单份（改一次全循环生效） | `GtConfirmationSummary`(X0-1)、`entityVerify/`(X0-2)、`followup/`(跟函)、`diffReconcile/`(差异调节)、`diffChecklist/`、`reliability/`(可靠性)、`fraudRisk/`(舞弊) | D0/E0/F0/G0/H0/K0/L0 |
| per-cycle | `alternativeD05`(887,拆子组件+composables=**标准**)、`D06`(831)、`F05`(858)、`F06`(858)、`H05`(1207)、`K05`(474)、`K06`(994)、`L05`(597)、`G06`(1078)、`diffSecurities`(344,G0 特有) | 各自 1 循环 |

**推论**：绝大部分「打磨」是**共享组件的字段/区块补全**（一次修惠及 7 循环），真正 per-cycle 的只有替代程序结构与 G0 特有表。

## 二、D0 标准（对照尺子，源模板实测）

| sheet | 源模板结构 |
|---|---|
| D0-1 | **4 段 24 列**：发函信息 / 收到回函 / 回函金额确认（差异·可确认金额·调节索引）/ **未收到回函的替代程序**（是否采取替代·替代后可确认·替代后不可确认）；首列「选取样本目的」 |
| D0-2 | **25 列**：企查查核查块 + 回函地址/寄件人/电话核实块 + 两次发函 |
| D0-5 / D0-6 | 抽样方法学区（测试范围/特定样本/抽样总体/样本量/抽样方法/抽样过程）+ 函证项目账面数据区（年初/借方/贷方/期末）+ 检查比例 |
| D0-7 | 14 列：注1 身份确认 / 注2 邮箱验证 / 注3 信息可靠性考虑 |
| D0-8 | 舞弊迹象 / 是否存在 / 索引号或信息来源 / 应对措施 |

**注**：D0 源模板自身即含编码污染（D0-6 内部索引写 F0-6、D0-7 写 F0-7、D0-8 写 F0-8）→ 致同源模板是从 F0 复制的，这解释了 G0/L0 的同类污染。

## 三、🔴 P0 阻断级问题（功能实际不可用）

### 1. G0 两张差异核对表路由完全失效 —— `diffSecurities` 组件全平台零渲染

`wp_render_config._SHEET_CODE_RE = ([A-Z]\d+(?:-\d+)*[A-Z]?)(?:-新增)?\s*$` **要求编码在 sheet 名结尾**，而 G0 两张表名以「（证券投资）」「(非证券投资)」收尾 → 尾码提取失败 → sheet 级 override 全落空 → 落 `pkg_sheets and ovr` 分支得 `confirmation-hub`（无渲染组件）。

- `G0-3S → confirmation-diff-securities`、`G0-4 → confirmation-diff-reconcile` **两条 override 都从未生效**
- 344 行的 `diffSecurities/` 组件**全平台零渲染**
- 且两张表尾码（G0-3/G0-4）比表内真实索引号（G0-4/G0-5）**整体错位一位**，G0-3 还与「跟函函证过程控制G0-3」撞码
- override 里没有 G0-5 键；现有 `G0-4` 键实际指向「非证券」表 → 键与源索引号语义相反

### 2. L0 程序表被 F0A 劫持 —— L0A 模板永不生效

L0 的 sheet 名是「函证程序表**F0A**」（源模板污染）→ 尾码提取得 `F0A` → 命中 F0A override（组件类型仍对）→ 但 `get_template("F0A")` 无 JSON 模板 → **已存在的 `L0A` 模板（含 `risk_for_cycle` / `control_test_result_for_cycle` 联动）永不生效**，只走源 xlsx 兜底提取。

### 3. E0 映射与 schema 双缺

- `wp_code_overrides.json` 仅映射 E0/E0-1~E0-5/E0-8；**E0-6/E0-7 与全部无编码 sheet 落 `d-form-confirmation`**（E0-7 跟函表字段完全够，纯映射缺失）
- E0-1~E0-6 走 `d-form-table` 时用的是 `wp_render_schema/generated/E0.yaml`——**该文件自述「此文件为草稿，关键字段需人工审核」**，字段名是 `col_a/col_d`，label 抓成「编制日期：」「3」→ 这几张 sheet 目前就是**占位表**
- 两张 sheet 同为 E0-5（应付银行承兑汇票发函记录表 / 银行函证其他信息核对表）编码冲突
- 7 张遗留 sheet（`-原版本备份`/`（原）`/`(备份)`/`-旧版`×2/`F1-10-原`/`参考用-`）全部 `is_real_workpaper=true` 无 skip → 照常渲染成页签

### 4. K0-5 两处接线缺陷

- 「从 K0-1 带入未回函」：`useAlternativeK05Data` **已导出** `importFromSummary`，组件无按钮调用（K06/L05 都有）
- AI 调用 `context: JSON.stringify(context)` → 后端 `dict[str,str]` **恒 422**

## 四、共享组件字段 gap（一次修惠及 7 循环）

| 共享类型 | 现状 | 源模板要求（各循环共性） | gap |
|---|---|---|---|
| `ConfirmationRow`(28 字段) | 有 confirm_index/account_type/entity_name/amount/currency/method/send·reply_date/is_replied/reply_amount/match_status/difference/confirmed_amount/alt_confirmed/diff·alt_ref_index | D0-1 4 段 24 列；F0-1 4 段 27 列；G0-1/H0-1 4 段 27 列；**K0-1/L0-1 5 段 28 列**（多「发函询证纪要」段+「审计结论」列）；E0-1 3 段 24 列 | **缺 ~10 列**：选取样本目的、发函单号、地址核查是否一致、回函快递单号、回函发出地址、发函/回函地址是否一致、是否采取替代程序(布尔)、替代后不可确认金额、行级审计结论、账户/交易（`account_type` 是科目大类语义不等）<br>**E0 额外**：账号/理财产品名称、汇率、发函金额原币/本位币双列、可确认金额原币/本位币双列<br>**H0 额外**：源为「金额**或合同条款**」双口径，`amount` 是 number → 条款类差异**无载体** |
| `EntityVerifyRow` | 有企查查块(qcc_*)+一致性判定+两次发函 | D0-2 25 列 / F0-2·G0-2·H0-2·K0-2·L0-2 38~43 列 | **回函核实块几乎全缺（~11 列）**：是否原件、是否直接收到、回函发出地址、回函寄件人、回函电话、三项一致性判定、不一致说明、核实证据索引、跟函控制过程索引；企查查块另缺 邮编/邮箱传真/不一致说明是否合理/支持性文件索引/备注 |
| `ReliabilityRow`(6 验证字段) | identity/email/phone 三类 + conclusion_status | F0-7·G0-7·H0-6·K0-7·L0-6 均 14 列同构 | **缺 ~8 列**：函证索引号、被询证单位名称、回函方式、是否项目组直接接收、是否寄回原件、传真信息及验证、发函/回函邮箱双列（现仅 `email_domain`）、可靠性考虑文本 |
| `DiffReconcileRow` | 8 列全对应 | X0-4 均 9 列 | **缺 1 列**：相关支持性证据 |
| `fraudRisk` | 19 条迹象预置 | 各循环 X0-8 同构 | **齐，不动** |
| `followup` | memo 模板+3 控制项+签名 | 各循环跟函表同构 | **齐**（K0-3/L0-3 的 3 判断项与签名字段待逐字核对） |
| `diffChecklist` | — | D0/F0/L0 有该 sheet | **齐** |

## 五、per-cycle 替代程序对照（D05 为标准）

| 组件 | 行数 | 源模板结构 | 覆盖状况 |
|---|---|---|---|
| D05 / D06 | 887/831 | 抽样区+账面区+检查比例+区块 | **标准**（拆 Dashboard/Master/CheckBlock + composables） |
| F05 / F06 | 858/858 | 同 D0-5 结构 | **字段齐**（抽样 6 字段 + 账面 4 列 + 2 比例全渲染）；差别是单文件未拆子组件 = 结构债非功能缺 |
| H05 | 1207 | 抽样 6 项 + **「二、检查过程记录」是空白区** | 抽样区齐；4 区块（验收权属/采购证据/新增资产/抵押租赁）是**自造**（源空白）→ 按宁缺勿造**不再新增区块**；源无账面区/无检查比例 |
| G06 | 1078 | 测试范围 1 行 + ①初始投资协议表 ②本期借方/贷方双表 ③期后出售赎回表 | **区块与源完全错配**：组件自造「持仓证明/股利/处置/公允价值」4 区块，且多出源没有的抽样总体/样本量/抽样方法/抽样过程/账面区/检查比例 |
| K05 / K06 | 474/994 | 抽样 6 项 + 账面 4 列 + 4 区块（**③本期发生额是借方/贷方两张表**） | **③未拆借贷**（三套共性）；K05 474 行是复用 CheckBlock/Dashboard/Master 的结果，**区块不缺**；block4（往来对账/协议）是超源增强 |
| L05 | 597 | 同上 + **第 3 项「检查期初余额是否与上期期末余额一致」** | ③未拆借贷；**缺期初一致性核对项**；block4（抵质押/担保）超源 |
| diffSecurities | 344 | G0 证券差异 17 列（数量·市价·公允 三维） | **缺 5 列**：询证函索引号、资金账号、开户名称、账面余额、相关支持性证据；「是否需要调账」被做成文本（源是判断列）；自造了源没有的 security_code/security_type |
| （G0-4 非证券） | — | 15 列：**持股比例/投资金额/投资条款 × 账面·回函·差异 三维** | `diffReconcile` 只有单维金额 → **比例列与条款列无处落**，结构不匹配 |

## 六、编码污染与治理清单

| 循环 | 问题 | 影响 |
|---|---|---|
| G0 | 两张差异表尾码（G0-3/G0-4）比表内索引号（G0-4/G0-5）错位一位；G0-3 与跟函表撞码；舞弊表 sheet 名尾码是 `F0-8`；registry 登记「…G0-8」与 DB 真实 sheet_name 不一致 | 路由失效（见 P0-1）+ 索引号显示错 |
| L0 | 程序表 sheet 名 `F0A`；L0-1 调节索引写 F0-4、L0-2 跟函索引写 F0-3 | L0A 模板失效（P0-2）+ chip 目标错 |
| K0 | K0-1 调节索引写 K1-12、K0-2 跟函写 K1-11（应 K0-4/K0-3）；`GT_Custom` 占位（已被 render 排除）；目录序号 6 跳号 | chip 目标错 |
| E0 | 两张 E0-5；`F1-12`/`F1-10-原` 带 F1 编码 | 编码冲突 + 索引混淆 |
| D0 | 源模板 D0-6/D0-7/D0-8 内部索引写 F0-* | 污染源头（源模板从 F0 复制） |
| H0 | **无污染**，8 张编码 sheet override 全部正确命中（含 H0-6 可靠性/H0-7 舞弊偏移已正确登记） | — |

## 七、明确不做（宁缺勿造）

- H0 / G0 / K0 **不新增**「函证差异检查表（示例）」（源模板确无，仅 D0/F0/L0 有）
- H0-5 **不再新增源外区块**（源「二、检查过程记录」是空白区）
- G0-6 已有的抽样总体/样本量/抽样方法/检查比例属源外能力，**保留但不扩**
- K0/L0 **不加** 币种/汇率/原币双列（源 X0-1 主表无）
- L0 **不加** 借款起止日/利率/抵质押品/期末应付利息列（源 L0-1/L0-5 主表均无）
- 替代程序 **不加**检查比例表（K0/L0 源模板无；D0-5/F0-5 才有）

## 八、建议 spec 划分（5 个）

> **落地状态（2026-07-26 更新）**：spec-1 **已并入** `confirmation-hub-workbench-tabs`（新增 Requirement 10 + 决策 8 + 属性 P21~P24 + 任务 1.4 / 2.4 / 2.5）；spec-2 ~ spec-5 已按 requirements-first 起草 requirements.md（design/tasks 待批准后再进）。目录名：`confirmation-shared-model-extension` / `confirmation-alternative-structure-alignment` / `g0-investment-diff-model` / `e0-send-list-components`。

| spec | 范围 | 优先级 | 独立可发 |
|---|---|---|---|
| **spec-1 函证路由与编码治理**（已并入 `confirmation-hub-workbench-tabs` Req10） | G0 两张差异表 sheet_name 精确 override（修 P0-1，让 `diffSecurities` 首次渲染）+ 删 `G0-3S` 死键 + 补 G0-5 语义键；L0 程序表 sheet_name override 到 L0A（修 P0-2，让 L0A 模板生效）；E0 补 E0A/E0-6/E0-7 映射 + 两张 E0-5 消歧 + 7 张遗留 sheet skip；G0/L0 舞弊·程序表 F0 污染纠正；沿 sheet_name↔真实索引号对照表 + 契约守卫防再漂移 | **P0** | ✅ 纯 JSON override + 守卫，逐条可回退 |
| **spec-2 confirmation-v1 共享模型扩展** | `ConfirmationRow` 补 ~10 列（+K0/L0 的 5 段/审计结论、E0 原币本位币汇率族、H0 条款口径）；`EntityVerifyRow` 补回函核实块 ~11 列 + 企查查块 5 列；`ReliabilityRow` 补 ~8 列；`DiffReconcileRow` 补支持性证据 | **P0** | ⚠️ 跨 7 循环 + 存量 htmlData `_format` 兼容为红线，additive 扩展 |
| **spec-3 替代程序结构对齐** | K05/K06/L05「本期发生额」拆借方/贷方两表 + L05 补期初一致性核对项；G0-6 区块改对齐源 3 区；F05/F06 拆子组件对齐 D05（characterization 先行） | P1 | ✅ 可按 per-cycle 逐套发布 |
| **spec-4 G0 非证券差异三维模型** | G0-4（非证券）「持股比例/投资金额/投资条款 × 账面·回函·差异」三维模型（`diffReconcile` 无法承载）；`diffSecurities` 补 5 列 + 是否调账改判断列 | P1 | ✅ G0 专属 |
| **spec-5 E0 发函清单组件** | E0-3/E0-4/E0-5/E0-6 四张发函前清单（10~16 列，含「是否函证」驱动 E0-1）配置驱动组件 + 人工审 `E0.yaml` 草稿 | P1 | ✅ E0 专属 |

**快赢（无需 spec，各 1~5 行）**：K05 接 `importFromSummary` 按钮；K05 AI context 值转字符串；K0 目录序号 6 跳号；程序表 JSON 模板补齐（G0A 8→12 条、H0A 8→11 条、K0A 缺模板）。

**与既有 spec 的关系**：`confirmation-hub-workbench-tabs`（已有三件套）已覆盖 E0 结构重建（E0-1→summary 等）、7 张遗留 skip、G0-3 冲突、F0A/F0-8 污染、Unreplied_Pull 四处、Sync/Backflow 联动。**spec-1 与它高度重叠 → 建议并入该 spec 而非另起**；spec-2~5 为其后续增量。

## 九、待核实（未 live 验证，实现前需确认）

1. G0 两张差异表落 `confirmation-hub` 是代码路径 + DB class_code + registry 三处推导，**未在浏览器实测呈现形态**（`confirmation-hub` 无渲染组件，可能空白或 grid 兜底）
2. E0-1~E0-6 走 `d-form-table` 时前端最终渲染列（依据 `_unpack_sheet_schema` 消费 E0.yaml 草稿判定，未 live）
3. E0「回函情况汇编」是在用的第二版汇总表还是遗留（源模板未标旧版，与 E0-1 语义重叠且含 `#REF!`）
4. K0/L0「底稿目录」sheet 的实际 componentType（override 无条目，未追 class_code 派生链）
5. K0-3/L0-3 跟函控制的 3 判断项与签名字段是否被 `followup/` 承载
6. `GtConfirmationSummary` 的「函证情况统计」是否覆盖源模板底部 8 项口径

## 十、路由根因补充实证（2026-07-26 读码修正）

对 P0-1 / P0-2 的修法做了源码级核实，结论比 §三 更精确：

1. **sheet_name 精确 override 通道已存在**：`wp_render_config.py:734-743` 的解析顺序是 `Sheet_Code_Tail override` → **`_WP_CODE_OVERRIDE.get(cls.sheet_name)`** → `{wp_code}-{sheet_name}`。故编码不在尾部的 sheet（G0 两张差异核对表）**无需改 `_SHEET_CODE_RE`**，加 sheet_name 精确 key 即可命中（改正则会影响全平台多 sheet 底稿，风险不成比例）。
2. **G0 未命中 sheet_ovr 的实际落点是 `onlyoffice-sheet` 而非 `confirmation-hub`**：`wp_render_config.py:791-802` 对 `_is_multi_sheet and class_code.startswith("G-") and not _sheet_ovr` **强制改写为 `onlyoffice-sheet`**。无论哪种落点，`diffSecurities` 均零渲染，结论不变；具体形态列为 Wave 0 实测项。
3. **L0A 模板失效的根因在 `_a_program.py:212-216`**：`_sheet_code` 由 sheet_name 正则提取（「函证程序表F0A」→ `F0A`），**不校验循环前缀是否等于父 wp_code**，随后 `get_template(_sheet_code)`。修法 = 抽纯函数「父码优先 + `get_template` 命中才采用 + 否则回退原提取值」，同时对所有「sheet 名编码与父码不同循环」的底稿普遍生效，且保留 xlsx 提取兜底（零回归）。
4. **G0-4（非证券）本 spec 只保可达**：`confirmation-hub-workbench-tabs` 让它渲染成 `confirmation-diff-reconcile`（不落兜底）；其「持股比例 / 投资金额 / 投资条款 × 账面·回函·差异」三维结构由 `g0-investment-diff-model` 承接（不臆造三维模型塞进共享单维组件）。
