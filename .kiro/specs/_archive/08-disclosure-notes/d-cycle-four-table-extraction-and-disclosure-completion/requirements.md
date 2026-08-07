# Requirements Document

## Introduction

D 循环（D1 应收票据 / D2 应收账款 / D3 预收款项 / D4 营业收入 / D5 应收款项融资 / D6 合同资产 / D7 合同负债）的「四表入库 → 底稿取数 → 披露表 → 附注模块」全链收口。

本 spec 的立项依据是 2026-08-05 的只读全链勘查（真实库 + 源模板 openpyxl 直读 + 源码 grep），三块结论：

- **披露→附注侧已基本对齐**（前序 spec 成果）：7 个 `dXNoteSectionMap.ts` 齐全、7 个披露 Tab 全部已接手动同步与自动同步、附注 14 个主章节的 `columns`/`guidance`/`group|flat` 齐备并带 `_aligned_by` 标记。**本 spec 不重做这部分**。
- **断点全在上游取数**：`backend/app/services/four_table/d_cycle_specs.py` 已建好 7 个 `SemanticAccountSpec`（含备抵槽、否决词、逐项 DB 实证注释），但 7 个 render 策略对 `resolve_semantic_accounts` / `d_cycle_specs` 的引用**全为 0** —— 该文件是死代码。
- **另有 4 个披露/附注侧的结构缺口**（孤儿重复章、D4 分解信息表硬编码列、D3/D7 未接账龄枚举、三个组件金额控件未收敛）与 **1 组未兑现的高价值联动**（客户子科目天然对应披露分类）。

### 关键实证基线（改动前的事实，供守卫与验收比对）

> **🔴 基线表已按开工后的深入实证修正两处**（原判断被推翻，保留记录以免重犯）：
> 1. ~~「D7 取不到数」~~ **撤回** —— D7 查的是 `trial_balance`（**标准码**体系），`LIKE '2205%'` 在该表能命中；`trial_balance` 本身就是经 `account_mapping` 映射后的标准码，故查它无需反解。反解只在查 `tb_balance`（原始码体系）时才需要。
> 2. ~~「D3 查错科目」~~ **撤回** —— D3 的 `2205%` 查询是**有意的**（注入 D7 合同负债审定数供 D3↔D7 交叉核对，CAS14 预收拆分口径，落点 `responses_snapshot['D3-d7-tb-audited-amount']`）。D3 的真实缺口是**没查自己的 `2203`**。

### 7 个 render 的真实取数现状（2026-08-05 逐文件核实，去注释后统计）

| 循环 | `trial_balance` 前缀 | 科目解析器 | `tb_source_codes` | 叶子聚合 | `parent_check` | 真实缺口 |
|---|---|---|---|---|---|---|
| D1 | `1121%` + 备抵（净额口径） | ✅ 共享件 | ✅ | ❌ | ❌ | 缺三口径 |
| D2 | `1122%` − `1231-02%` | ❌ 源码自标 `hardcoded` | ✅ | ❌ | ❌ | 硬编码 + 缺三口径 |
| **D3** | 只有 D7 的 `2205%`（交叉核对） | ❌ | ❌ | ❌ | ❌ | 🔴 **自己的 `2203` 完全没查** |
| D4 | 不查该表 | ❌ | ✅ | ✅ | ❌ | 缺三口径 |
| D5 | `1124%` | ❌ | ❌ | ❌ | ❌ | 硬编码 + 无溯源 |
| D6 | `1141%` | ❌ | ❌ | ❌ | ❌ | 硬编码 + 无溯源 |
| D7 | `2205%`（能命中） | ❌ | ❌ | ❌ | ❌ | 硬编码 + 无溯源 |

**修正后的价值排序**：① D3 补 `2203` 取数（唯一「自己科目完全取不到」的循环，`trial_balance` 实测 9 项目 / **77,338,768.39**）② 5 个循环消除硬编码（`report_config` 改码即失效的隐患，D2 源码自己标了 `hardcoded`）③ 7 个循环补 `parent_check` 三口径（`trial_balance` 的父子双算只比对两口径发现不了）④ 补 4 个循环的取数溯源 ⑤ `tb_balance` 叶子级取数推广。

### 关键实证基线（改动前的事实，供守卫与验收比对）

| 事实 | 实证方式 | 数值 |
|---|---|---|
| 7 个 D render 对 `resolve_semantic_accounts` 引用数 | 源码 grep | 全部 0（但**不代表没接科目映射**，D1 走 `report_line_accounts`） |
| `trial_balance` 中 `2203`（预收款项，D3 应查未查） | 真实库 | 9 项目 / **77,338,768.39** |
| `trial_balance` 中 `2205`（合同负债，D7 实际能取到） | 真实库 | 5 项目 / **7,855.34** |
| `trial_balance` 中 `1231` 父行与 `1231-01..05` 子行 | 真实库 | **并存**（父 9 项目 / 1,756,301.88；子码合计 252,539,860.06）⇒ `LIKE '1231%'` 会双算 |
| `trial_balance` 中 `1141`/`1142` | 真实库 | 各 5 项目但金额**全 0** |
| `trial_balance` 中 `1231-04`/`1231-05` | 真实库 | 各 8 项目但金额**全 0** |
| `tb_balance` 中 `2205`/`1141`/`1142`/`1124` 行数 | 真实库 | 均 **0**（叶子级取数在这些循环无数据可用） |
| `account_mapping` 中 `2205 ← 2204` 反解 | 真实库 | 存在，`auto_exact`，1 项目 |
| `account_chart` 中「应收款项融资」按名命中数 | 真实库 | **0**（两个 source 均无） |
| `1231` 全库期末合计 / 其中 `1231.02` / `1231.03` / `1231.01` | 真实库 | 190,479,717.05 / 186,648,869.59 / 3,811,793.41 / **0.00** |
| `closing_balance` 为 NULL 的 D 类子科目 | 真实库 | 5 个（`1121.03`/`1122.02`/`1122.12`/`1231.05`/`2203.02`） |
| `1122.11 应收账款_收款通` 期末 | 真实库 | **−114,209,110.16** |
| ~~附注孤儿重复章数量~~（**2026-08-06 实证推翻**） | 模板 JSON | 立项记 listed 3 / soe 2，实为**母公司章正当子节**（listed `chapter-16` / soe `chapter-12`）；按严判据真孤儿 = listed **23** 章（全在「三、重要会计政策」与「十四、日后事项」下）/ soe **0** 章，与 D 类零交集 ⇒ 归 C spec |
| D4「按分解信息」表 group | 模板 JSON | `['其他','汽车','消费品','能源']`（9 列，源模板示例行业） |
| `D2DisclosureNoteBody` 的 `el-input-number` / `WpAmountInput` | 源码计数 | **43 / 0** |
| `D5TabDisclosure` / `D7TabDisclosure` 同上 | 源码计数 | 14 / 0 与 4 / 0 |
| D3/D7 披露 Tab 的账龄信号 | 源码计数 | 均 **0** |
| D 类公式预设块数 / 披露 sheet 有预设的循环 | 配置 JSON | 23 块 / 仅 D4 |

### 范围外（显式声明，避免下个会话重复提议）

- `report_config` 自身的三处缺陷归 **`report-config-account-code-integrity`** spec：`BS-006 listed_standalone` 用整个 `1231`、`IMP-002` 用点号 `TB('1231.02')` 导致恒空、`IMP-004 合同资产减值准备` formula 四准则全 NULL。本 spec 只做**冲突检出与如实告警**，不改该表数据。
- `account_mapping` 里 `1231.05 → 1231-02` 的 `auto_fuzzy` 错映射属数据问题，本 spec 只在取数侧叠名称过滤兜住，不改映射数据。
- D0 是函证循环（源模板无披露 sheet），只修其 3 处贴错标签的公式预设 sheet 名，不做取数改造。
- 附注 14 个主章节的行集与列结构**不重做**（已由前序 spec 三向对齐），本 spec 只动 R6/R7 明确列出的部分。

## Requirements

### Requirement 1: 科目定位接线（把 D1 范式推广到 D2~D7）

**User Story:** 作为审计助理，我希望四表入库后打开任一 D 循环底稿就能看到取数，而不是因为客户科目编码与标准码不一致就显示空白。

> **🔴 方案方向修正（2026-08-05，开工后实证推翻立项判断）**
>
> 立项时按 `grep resolve_semantic_accounts` 得 0 就判定「D 类完全没接科目映射」，**判据选错了**。实证结果：
>
> - **D1 已有完整取数链路**，走 `four_table/report_line_accounts.py` 共享件（`d1_account_resolver` 只是放 D1 参数的薄壳），且已实现名称过滤（`d1_detail_seed._fetch_leaves(..., name_contains=)`）、双态标注（`provision_resolved_from` / `provision_exact`）、fail-open 与零回归守卫。K1/K2/F1 是同一共享件的其它消费者。
> - **该能力只有 D1 有** —— `use_provision_name_filter` 全库 grep 只命中 `d1_*`，D2~D7 全无。
> - **D 类科目码在项目间基本一致**（`1121`/`1122`/`2203`/`6001` 各项目相同）⇒ 换成 `semantic_account_resolver` 买不到东西；而唯一码不一致的 D7（client `2204` vs standard `2205`）靠 `account_mapping` 反解已足够（该反解行已存在）。
> - 机械迁移有已实证风险：memory 记 F3/F4 曾因「下游读 `accounts.gross` 而新类型没有该字段」被弄坏，且 962 例测试全绿一个没抓到。
>
> **故本 spec 改为：把 D1 已建好的 `report_line_accounts` 范式推广到 D2~D7，不换解析器。**
> `four_table/d_cycle_specs.py` 的语义规格保留（Task 1 对它的备抵槽全名化仍是正确改动、`subject_keywords` 为将来留口），但**当前不接线**，须在文件头写明理由，避免下个会话又发起一轮迁移。

#### Acceptance Criteria

1. WHEN `_d2_accounts_receivable` / `_d3_prepaid_accounts` / `_d4_operating_revenue` / `_d5_receivables_financing` / `_d6_contract_assets` / `_d7_contract_liabilities` 的 render 执行取数 THEN 系统 SHALL 经新增的 `d_cycle_extraction.d_account_resolver.resolve_d_cycle_account_codes(ctx, wp_code)` 取得科目码，该函数 SHALL 委托既有共享件 `four_table.report_line_accounts.resolve_report_line_accounts`
2. WHEN 接线完成 THEN 系统 SHALL 用解析出的**原始码**集合查询 `tb_balance`、用**标准码**集合查询 `trial_balance`，禁止在 render 内保留硬编码科目码前缀作为查询条件
3. WHERE `_d1_notes_receivable` 已走该共享件 THE 系统 SHALL NOT 改动 D1 的科目定位路径（零回归红线），仅在其上补齐本 spec 新增的载荷字段
4. WHEN 聚合金额 THEN 系统 SHALL 经 `four_table.leaf_aggregation` 的叶子口径聚合（只汇总叶子科目），且 SHALL 记录该槽前缀在 `tb_balance` 的命中行数 `tb_rows_count`

   > **口径说明（2026-08-05 实证修正）**：原验收标准要求区分 `closing_balance` 的 NULL 与 0，但共享件 `leaf_aggregation.to_leaf_rows` 通过 `_f()` 已把 `None` 归一成 `0.0`，`LeafRow` 层面两者不可区分；要保留该区分须改共享 `LeafRow`（波及全部循环）。复核后确认该区分**不必要** —— 三态的真正判据是 `found`（科目表有无落点）+ `tb_rows_count`（四表有无数据行），后者能表达「科目表有此科目但四表无数据行」，这正是 D6 的真实形态且更有审计意义。故改用 `tb_rows_count`，不改共享件。
5. WHEN 某科目族内叶子的 `closing_direction` 不一致 THEN 系统 SHALL 按方向带符号求和，禁止对逐行取绝对值
6. WHEN 取数完成 THEN 系统 SHALL 输出 `parent_check` 三口径比对结果（叶子和 / 父行 / `trial_balance`）到 render 载荷
7. WHEN 解析或取数抛异常 THEN 系统 SHALL fail-open 返回空结果并记 WARNING，且 WARNING 文本 SHALL 包含 wp_code 与失败阶段
8. WHEN 调用共享件 THEN 系统 SHALL 以 `inspect.signature` 实证过的真实签名调用（`select_leaves` 是同步纯函数，`get_active_filter` 是 async 四参，`fetch_trial_balance_rows` 供 `build_parent_check` 用）

### Requirement 2: 备抵串科目防护（补第三种污染成因）

**User Story:** 作为业务合伙人，我不能接受应收票据的坏账准备里混进应收账款或长期应收款的坏账，那会让审定表金额直接错。

> **既有机制与本需求的分工（2026-08-05 实证）**
>
> 共享件 `report_line_accounts` 已提供 `use_provision_name_filter`（保守口径）与 `provision_exact`（精确判定），其 docstring 自述备抵污染有**两种**成因：① 报表公式没引用备抵科目 ② `account_mapping` 反解退化为宽前缀。**但过滤动作本身由调用方执行**，且全库只有 D1 执行了（`d1_detail_seed._fetch_leaves(..., name_contains=)`）。
>
> 本需求补的是**第三种成因**：**反解成功但映射数据本身错** —— 实证 `account_mapping` 有 `1231.05 坏账准备_长期应收款 → 1231-02`（`auto_fuzzy`，2 个项目）。此时 `provision_resolved_from='report_config'` ⇒ `use_provision_name_filter` 为 **False** ⇒ 既有机制**不叠过滤** ⇒ 长期应收款的坏账进入 D2 备抵。

#### Acceptance Criteria

1. WHEN D2~D7 的备抵侧反解出原始码 THEN 系统 SHALL 无条件叠加名称过滤（不依赖 `use_provision_name_filter`），过滤词取本循环主体关键词
2. WHEN 判定主体关键词 THEN 关键词粒度 SHALL 足以区分同族科目：D2 的关键词 SHALL 为「应收账款」而 SHALL NOT 为「应收」（后者无法拦住「坏账准备_长期应收款」）
3. WHEN 反解结果被名称过滤剔除 THEN 系统 SHALL 在载荷中记录被剔除的原始码、科目名与原因，供溯源面板展示；SHALL NOT 静默丢弃
4. WHEN 某原始码的科目名缺失 THEN 系统 SHALL 保留该码并单独记入 `warnings`（不计入 `dropped`），交人工确认
5. WHEN D1 与 D2 在同一项目同时取数 THEN 两者的备抵科目码集合 SHALL 无交集
6. WHERE `four_table/d_cycle_specs.py` 的语义规格当前不接线 THE 该文件 SHALL 在头部写明「不接线的实证理由」，防止后续会话重复发起迁移
7. WHEN 备抵槽的 `names` 被求值 THEN 该元组 SHALL NOT 包含裸「坏账准备」「减值准备」这类一级科目通名，且 SHALL 同时覆盖横杠与下划线两种写法
8. WHERE 存在守卫测试 THE 系统 SHALL 包含反向自检：关键词写宽成「应收」时过滤空转、不传关键词时为空操作

### Requirement 3: 恒空的四态呈现（宁缺勿造）

> **态数由三改四的实证依据（2026-08-05）**：`resolve_semantic_accounts` 内部对反解结果的处理是 `originals = await to_original_codes(ctx, codes) or list(codes)` —— **反解不到就保留标准码**。而标准码是横杠体系（`1231-04`）、`tb_balance` 是点号体系（`1231.04`）⇒ `LIKE '1231-04%'` 必然命中 0 行。实证 `1231-04`（预付账款坏账）与 `1231-05`（合同资产坏账）在 `account_mapping` 中**0 反解**，D6 备抵走的正是这条路：结果恰好正确（该备抵全库确实无数据）但机理是「碰巧对」，与 M8 那次「按不存在的码查、恒空碰巧正确」同族。故必须把「前缀体系不匹配」单独成态并告警，否则下次某项目真有数据时会静默取空。

**User Story:** 作为现场经理，我需要区分「本项目没有这个科目」「科目余额确实是 0」「还没取数」，这三种在审计结论上完全不同。

#### Acceptance Criteria

1. WHEN 某语义槽在本项目 `account_chart` 与 `account_mapping` 两侧均无落点（`found=False`）THEN 系统 SHALL 标记为「本项目无此科目」态，且金额字段返回 `null` 而非 `0`
2. WHEN 某语义槽 `found=True` 但该槽前缀在 `tb_balance` 命中行数为 0 THEN 系统 SHALL 标记为「四表无数据」态、金额返回 `null`，并进一步判定：IF 该槽 `query_codes` 中存在含横杠的码 THEN 追加 `prefix_mismatch` 标志（表示反解失败导致前缀体系不匹配，需告警）
3. WHEN 某语义槽 `found=True` 且命中行数大于 0 而聚合结果为 0 THEN 系统 SHALL 标记为「余额为 0」态并返回数值 `0`
4. WHEN render 未执行取数（灰度关闭或前置条件不满足）THEN 系统 SHALL 不输出该槽键，前端据「键不存在」判为未取数
5. WHEN 前端渲染溯源面板 THEN 「本项目无此科目」与「四表无数据」SHALL 用 `info` 级 tag 呈现，SHALL NOT 用 `danger`
6. WHEN 某槽带 `prefix_mismatch` 标志 THEN 溯源面板 SHALL 以 `warning` 级提示「标准码未能反解为本项目原始码，取数可能失效」，SHALL NOT 静默显示为「无数据」
7. WHEN 前端读取金额 THEN 系统 SHALL 先排除 `null` 与空串再转数值，禁止依赖 `Number(null) === 0`
8. WHEN `report_config` 解析出的科目码与按名定位结果不一致 THEN 系统 SHALL 把差异写入 `conflicts` 并在溯源面板以告警条呈现，同时以按名定位结果为准

### Requirement 4: 前端消费与溯源（消除 dead output）

**User Story:** 作为审计助理，我希望在审定表上一键把四表数据带进未审数列，并能看清这个数是从哪个科目怎么算出来的。

#### Acceptance Criteria

1. WHEN D1~D7 的审定表 Tab 渲染 THEN 每个 Tab SHALL 提供「从四表库带入未审数」操作，且 SHALL 复用平台共享件 `WpFourTableSourcePanel` 展示取数溯源
2. WHEN 宿主组件把 render 载荷传给审定表子组件 THEN 宿主 SHALL 显式传 `:html-data`，且 SHALL 存在守卫扫描 7 个宿主模板断言该属性已传
3. WHEN 组件读取 `tb_source_codes` THEN SHALL 优先读 `html_data.project_context.tb_source_codes`、其次兼容 `html_data` 顶层
4. WHEN 用户点击带入 THEN 系统 SHALL 只覆盖四表命中的行，对「四表无数据且无手工值」的行显式写 0，并在提示中说明清零了几行
5. WHEN 带入操作完成 THEN 已有手工录入值 SHALL NOT 被覆盖
6. WHEN 传给 `WpFourTableSourcePanel` 的属性被求值 THEN 属性名 SHALL 与该组件 `defineProps` 声明一致，且必填属性 SHALL 已传（守卫从 SFC 动态抽取合法属性名比对）

### Requirement 5: 公式预设纠偏与补全

**User Story:** 作为审计助理，我在公式管理页面看到的预设应当指向真实存在的 sheet 和正确的科目，否则我照着用就是错的。

#### Acceptance Criteria

1. WHEN 修订 D 类公式预设 THEN 系统 SHALL 提供幂等脚本，支持 `--dry-run` / `--check` / `--apply`，且 `--check` 在修订完成后返回 0 项欠账
2. WHEN 脚本写回 JSON THEN 脚本 SHALL 做 round-trip 自检（不能逐字复现原文即退出非零），防止全文件重排与并发冲突
3. WHEN 修订 sheet 名 THEN 以下 4 处 SHALL 改为源 xlsx 真实 tab 名：`审定表D0-1`→`函证结果汇总表D0-1`、`函证汇总表D0-2`→`核实被函证单位信息D0-2`、`分析程序D0-3`→`跟函函证过程控制D0-3`、`分析程序D4-3`→`其他业务收入明细表D4-3`
4. WHEN 修订 D4 审定表 THEN「期初余额」单元格 SHALL NOT 与「未审数」使用同一公式，损益类上年数 SHALL 走 `PREV()`
5. WHEN 修订 D5 预设 THEN 引用 `1124` 的公式 SHALL 改为 `PLACEHOLDER` 并在描述中写明「应收款项融资在本平台活体科目表零命中」
6. WHEN 补齐明细表块 THEN 系统 SHALL 为 D3-2 / D5-2 / D5-4 / D6-2 / D6-3 / D7-2 各新增预设块
7. WHEN 补齐披露 sheet 块 THEN 系统 SHALL 为 D1/D2/D3/D5/D6/D7 各自的上市与国企两张披露 sheet 新增预设块
8. WHEN 新增 `WP()` 联动 THEN 审定表 SHALL 可引用本循环明细表，而明细表块 SHALL NOT 反向引用审定表（防成环），且 SHALL 有守卫断言无环
9. WHEN 校验预设语法 THEN 系统 SHALL 按 prefill 引擎词汇表放行 `ADJ`/`TB_SUM`/`LEDGER`/`LEDGER_DETAIL`/`PLACEHOLDER`，并对 `PLACEHOLDER` 逐条登记理由

### Requirement 6: 母公司附注章禁删锁死（原「孤儿重复章处置」，立项判断已被实证推翻）

**User Story:** 作为质量控制复核合伙人，我需要确保「十六、应收票据」这类看似重复的章节不被当成重建残留删掉 —— 它们是母公司口径的正当披露章节，删掉等于删掉整章母公司附注。

**🔴 立项判断撤回依据（2026-08-06 实测 `note_template_listed.json` / `note_template_soe.json`）**：原清单 5 章（listed `十六、应收票据`/`十六、应收账款`/`十六、营业收入与营业成本` + soe `十二、应收账款`/`十二、营业收入与营业成本`）的 `parent_section_id` 全部指向母公司章（`chapter-16-mu-gong-si-...` / `chapter-12-mu-gong-si-...`），`scope='consolidated_only'`。母公司章下共 12 个子节，形态（`_aligned_by=None` + `columns` 全 0）**逐个相同**，原清单只挑了其中 5 个 ⇒ 该判据描述的是**母公司章共性**而非孤儿特征。按严判据（全部子表名都是表头首格泄漏）真孤儿 = listed 23 章 / soe 0 章，全在「三、重要会计政策」与「十四、日后事项」章下，与 D 类零交集。

#### Acceptance Criteria

1. WHEN 守卫运行 THEN 系统 SHALL 断言那 5 章仍存在且 `parent_section_id` 仍指向母公司章，若被删或被改挂 THEN SHALL 打红
2. WHEN 守卫运行 THEN 系统 SHALL 断言母公司章下**全部**子节共享同一形态（`_aligned_by` 为空且子表 `columns` 全 0），以证明原判据描述的是母公司章共性
3. THE 系统 SHALL NOT 提供任何删除这 5 章的脚本；守卫 SHALL 断言仓库内不存在 `cleanup_*orphan*note*` 形态的脚本文件
4. WHEN 守卫运行 THEN 系统 SHALL 断言全部 `*NoteSectionMap.ts` 的章节号常量与 `十六、`/`十二、` 前缀零交集（D 类 7 个 map 应指向 `五、4`/`八、4` 等合并章）
5. WHERE 真孤儿章（listed 23 章）的处置 THE 本 spec SHALL 只登记清单与归属（`note-template-columns-and-legacy-snapshot-closure`），SHALL NOT 在本 spec 内实现补列或删除
6. WHERE 母公司章的列结构与取数补齐 THE 归属 SHALL 为 `parent-company-note-chapter-and-sourcing` spec，本 spec 只做禁删锁死

### Requirement 7: D4「按分解信息」表动态列

**User Story:** 作为审计助理，收入分解披露的列应当是本项目真实的业务板块，而不是模板里举例的「汽车、消费品、能源」。

#### Acceptance Criteria

1. WHEN D4 披露表渲染分解信息 THEN 列 SHALL 由本项目实际业务板块动态生成，SHALL NOT 写死列数或行业名
2. WHEN 生成动态列的键 THEN 键 SHALL 形如 `{slot}_{seq}` 的稳定标识，SHALL NOT 使用中文 label 作键
3. WHEN 分配新列序号 THEN 序号 SHALL 取自持久化的单调计数器，SHALL NOT 复用已删除列的序号
4. WHEN 该表已有历史同步数据 THEN 迁移 SHALL 按列名匹配把旧值搬到新列，未匹配上的旧列 SHALL 保留并标注待人工归并
5. WHEN 底稿推送该表到附注 THEN 附注侧列头 SHALL 与底稿同构（收入与成本两级分组），SHALL NOT 压扁成单级

### Requirement 8: D3/D7 账龄枚举贯通

**User Story:** 作为审计助理，项目账龄配置改成 3 年段后，预收款项和合同负债的「账龄超过 1 年」披露也应当跟着走，不该还是写死的档位。

#### Acceptance Criteria

1. WHEN D3 与 D7 的披露 Tab 渲染账龄相关表 THEN 档位标签 SHALL 取自平台单一真源 `composables/disclosureAgingLabels.ts`
2. WHEN 项目账龄配置为 3 年段 / 5 年段 / 自定义 THEN 披露行集 SHALL 随之变化，且 SHALL 提供「按账龄段生成」操作
3. WHEN 国企变体渲染首档 THEN 字面 SHALL 取自 `DISCLOSURE_AGING_WITHIN1_SOE`，SHALL NOT 在组件内写死
4. WHEN 账龄行推送到附注 THEN 合计行字面 SHALL 按该章节实证取值，SHALL NOT 全局套用固定字面
5. WHERE 某循环源模板确实无账龄维度（D1 按票据种类、D5 票据、D6 按组合）THE 系统 SHALL NOT 引入账龄枚举，且守卫 SHALL 反向断言这三者不得引用账龄真源

### Requirement 9: 金额控件收敛

**User Story:** 作为审计助理，披露表里录入金额应当自动显示千分符，现在 D2/D5/D7 三个页面完全没有。

#### Acceptance Criteria

1. WHEN D2 / D5 / D7 披露组件渲染可编辑金额 THEN SHALL 使用 `components/workpaper/shared/WpAmountInput.vue`
2. WHEN 替换完成 THEN 这三个组件的 `el-input-number` 计数 SHALL 归零，且守卫 SHALL 断言该计数为 0
3. WHEN 渲染非金额数值列 THEN 比例 / 损失率 / 账龄天数 / 年度 / 笔数 SHALL NOT 使用 `WpAmountInput`，守卫 SHALL 含此反向边界断言
4. WHEN 只读金额渲染 THEN SHALL 经 `displayPrefs` store 的 `fmtAmount`，且 SHALL 以 setup 顶层 inject 方式取得该 store
5. WHEN D6 组件仍有 3 处 `el-input-number` THEN SHALL 一并收敛，避免同页控件风格分裂

### Requirement 10: 客户子科目联动 seed

**User Story:** 作为审计助理，四表入库后明细表应当按客户实际的子科目自动建行，而不是让我手工照抄一遍科目表。

#### Acceptance Criteria

1. WHEN D3 明细表（D3-2）为空且四表有 `2203` 子科目数据 THEN 系统 SHALL 按叶子子科目名自动建行并填期初/期末金额
2. WHEN D4 披露表渲染「按行业（或产品类型）划分」THEN 系统 SHALL 由 `6001` 与 `6401` 的同构客户子科目板块自动 seed 收入与成本双列
3. WHEN seed 执行 THEN 手工录入的行 SHALL NOT 被覆盖，且 seed SHALL 幂等（重复执行不产生重复行）
4. WHEN 四表某板块只有收入没有成本（或反之）THEN 系统 SHALL 建行并把缺失侧留空，SHALL NOT 填 0
5. WHEN 子科目名在项目间不一致 THEN 系统 SHALL 按本项目实际叶子名建行，SHALL NOT 跨项目套用固定分类名
6. WHEN seed 后再次入库且新增了子科目 THEN 系统 SHALL 支持增量补行，对已有行金额有变化时弹确认（可选「仅补空值」）

## Glossary

| 术语 | 本 spec 内的确切含义 |
|---|---|
| 语义槽（slot） | `SemanticAccountSlot`，一个命名的科目集合（如 D1 的 `gross`=应收票据原值、`provision`=应收票据坏账准备）。一个循环可有 N 个槽，不限于原值/备抵二元 |
| 按名定位 | 在**本项目自己的** `account_chart` 里按科目**名称**匹配（client 表优先于 standard 表），而非按硬编码码值 |
| 反解 | 经 `account_mapping` 从标准码（横杠体系，如 `1231-02`）取回客户原始码（点号体系，如 `1231.02`），用于前缀匹配 `tb_balance` |
| 叶子口径 | 只汇总没有子科目的末级科目，自检不变量为「叶子和 == 父科目行金额」 |
| 三态 | 「本项目无此科目」（`null`）/「余额为 0」（`0`）/「未取数」（键不存在）三者互不混淆 |
| 孤儿重复章 | 附注模板里 `_aligned_by` 为空、全部子表 `columns` 长度为 0、表名是表头首格泄漏或自动编号的章节，为 md 重建残留 |
| 表头泄漏 | 子表 `name` 实际是源表格第一个单元格的文字（如 `种  类`/`项  目`/`单位名称`），而非真实表名 |
| 动态插行区 | 附注模板中留给底稿按实际情况增删的行区（源模板常写 `……` 或「可无限量添加行」），与固定行集相对 |
| 账龄真源 | `composables/disclosureAgingLabels.ts`，披露侧账龄档位标签的唯一来源；项目账龄配置只服务底稿内部 |
| dead output | render 输出了某字段但前端零消费，或前端读了某字段但后端从不输出，两侧都不报错 |
