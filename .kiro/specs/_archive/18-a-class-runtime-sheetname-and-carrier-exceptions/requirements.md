# A 类运行时册名与载体例外车道 — 需求

## 引言

**上游**：`a-cycle-sync-foundation-and-first-canary`（以下简称 **foundation**）已一次性裁定共同判据 **AC-1 ~ AC-48**，本 spec **只引用编号、不复述判据正文**。术语与口径一律沿用 foundation 的「术语与口径」节。

**本 spec 的 entry 范围**（**3** 条，全部为非 docx 特例，各带一个独有 BP）：

| entry_id | wp_code | group | 权威册 | 独有 BP | 载体 / switch |
|---|---|---|---|---|---|
| `xlsx/gt-a177-independence-declaration` | **`A177I`**（单 pattern） | GRP-01 | **无册**（`runtime_sheet_name_expression`） | **BP-8** | segmented / redeemable |
| `xlsx/gt-a3-consolidation-console` | A3-3 / **`A3C`** | GRP-03 | **xlsx**（`A3-3 结构化主体纳入合并范围的判断.xlsx`） | **BP-10** | **`no_carrier` / `no_switch_at_all`** |
| `xlsx/gt-a38-goodwill-impairment` | A3-8 / A38G | GRP-03 | **无册**（`'A3-8'` 纯码也解析为 None） | **BP-6** | segmented / redeemable |

**切分依据**：这 3 条是「非 docx 的 4 条」里除 canary（a51）外的全部，且 **BP-6 / BP-8 / BP-10 三个区分项完整内聚本 spec**，横跨 **0**。三条的共同特征 = **都无法用「一本 xlsx 权威册 + 字面 sheet 名」的标准模型处理**。

**Property 前缀**：本 spec 用 **AH-P**（foundation 用 AF-P，lane2 用 AG-P）。

## 需求

### Requirement 1 — entry 范围与归属算术

**用户故事**：作为维护者，我要确认这 3 条虽规模小但各自背负一个独有 BP，与 foundation 算术表严格对齐。

#### 验收标准

1. WHEN 现算本 spec entry THEN SHALL 恰 **3** 条，全名逐一吻合上表。
2. WHEN 现算 BP 归属 THEN SHALL 为 **BP-6 = {a38}** · **BP-8 = {a177}** · **BP-10 = {a3-consolidation-console}**，三者**完整内聚本 spec**；公共 BP **6** 项对 3 条全成立 ⇒ BP 数 = 3×7 = **21**。
3. WHEN 现算 group 归属 THEN SHALL 为 GRP-01 **1**（a177）+ GRP-03 **2**（a3-console / a38）= **3**。
4. WHEN 现算权威册 THEN SHALL 为 **xlsx 1**（a3-console）+ **无册 2**（a177 / a38）⇒ docx **0** ⇒ 🔴 AC-38 / AC-39（docx 相关）对本 spec **空分母**。
5. WHEN 现算 OO 挂点与门控 THEN SHALL 为挂点 **3** · segmented **2** · mode 门控 **2** ⇒ 🔴 **a3-console 是全 A 域唯一无 segmented 且无 mode 门控的 entry**。
6. WHEN 现算真库归属 THEN SHALL 为 **0** 行（三条的 wp_code 前缀 `A177I` / `A3-3` / `A3-8` 在真库 28 行里均不存在）⇒ 闭环验证须自建夹具（依 AC-18）。
7. WHEN 现算 xlsx 侧量 THEN SHALL 为 sheets **4** · 公式格 **63** · `definedName` **261 / broken 190**（全部来自 a3-console 的 `A3-3` 册）。

### Requirement 2 — BP-8：运行时 sheet 名表达式（a177）

**用户故事**：作为实施者，我要处理「权威册在渲染时才确定」的 entry，且不能为凑字段硬指一本册。

#### 验收标准

1. 🔴 WHEN 现读 a177 的 `template_ref` THEN `resolution_kind` SHALL 为 **`runtime_sheet_name_expression`**、`workbook` 与 `workbook_format` SHALL 为 **null**、`sheet_name_exprs` SHALL 为 **`["variant === 'team' ? 'A17-7' : 'A17-7A'"]`**。
2. 🔴 WHEN 处理该 entry THEN SHALL NOT 为它硬指一本权威册 —— slice 的 `why_null` 明文：「本 slice 不为它硬指一本册（那是**伪造 source_ref**）」。判据 SHALL 按「运行时解析 + 双变体」建模。
3. 🔴 WHEN 登记变体轴 THEN SHALL 写明 **A17-7（team 变体）与 A17-7A（非 team 变体）双变体**，但 `wp_code_patterns` 只登记了 **`A177I`** 一个 ⇒ **变体轴信息在 pattern 里丢失**（依 AC-15）。归档 spec 名是 `a17-7` 而非 `a177`，也印证这一点。
4. WHEN 现算全 slice 的 BP-8 成员 THEN SHALL 为 **27** 条（`literal` 19 : `runtime_expression` 27 = 46），A 域只 **1** 条（a177）⇒ 其余 26 条在 B/C/S 与跨循环共享域，由后续轮次承接。
5. 🔴 WHEN 设计双射判据 THEN SHALL 按 AC-44 降级为**单射** —— 只 18 本册能归属 entry，a177 属于「无册可归属」一侧，须写 `excluded_reason` 而非报缺失。
6. WHEN 现算 a177 宿主 THEN SHALL 确认其有 `<el-segmented>` + mode 门控（依 AC-13 的三层嵌套形态之一），🔴 门控在**祖先的 v-else 链头**上，只看挂点自身会假阴。
7. WHEN 登记归档欠账 THEN `a17-7-independence-declaration` SHALL 为 **20/21**（1 条未完成）⇒ 这是 foundation 6 份欠账里归本 spec 的**唯一 1 份**（其余 5 份归 lane2，依 AC-25）。

### Requirement 3 — BP-10：无模式开关（a3-consolidation-console）

**用户故事**：作为架构维护者，我要给唯一一条「没有双模式开关」的 entry 补上开关，或论证它不需要。

#### 验收标准

1. 🔴 WHEN 现读 a3-console 宿主 THEN `<el-segmented>` 现算 SHALL 为 **0**、mode 门控 SHALL 为 **0**，与 slice 的 `dual_mode_carrier.kind = no_carrier` / `switch_verdict = no_switch_at_all` **完全吻合**。
2. 🔴 WHEN 现读其 OO 挂点 THEN SHALL 为 **1** 个，但该挂点的显示条件**不是 mode 门控而是 sheet 路由兜底**（BP-10 原文：「其 OO 挂载点是 sheet 路由兜底」）⇒ 判据 SHALL 区分「mode 门控」与「路由兜底」两种挂点成因。
3. 🔴 WHEN 判定是否补开关 THEN SHALL 先论证「该 entry 是否真需要双模式」：现算它有 **HTML 对端**（`html_counterpart_verdict = exists`）+ **xlsx 权威册可解析**（`find_template_file_any('A3-3')` 返回真实路径）+ **4 sheets / 63 公式格** ⇒ 结论 SHALL 为**需要补开关**，SHALL NOT 以「没有开关」为由裁 `single_onlyoffice`（AC 12.8 禁止）。
4. WHEN 补开关 THEN SHALL 直接采用形态 2（label/value 分离，抄 a38 或 a112 样板），SHALL NOT 新引入形态 1（中文标签作 mode 值，依 AC-41）。
5. WHEN 收口完成 THEN BP-10 成员集 SHALL 变为空集，且全 A 域 segmented 计数 SHALL 从 **19** 升至 **20**、mode 门控从 **19** 升至 **20** ⇒ foundation 与本 spec 的事实基线表须同步更新。
6. 🔴 WHEN 现算全 slice BP-10 成员 THEN SHALL 为 **4** 条（`xlsx/cash-flow-verification` · `xlsx/gt-a3-consolidation-console` · `xlsx/gt-c22-itgc-bundle` · `xlsx/gt-wp-renderer`），A 域只 **1** 条 ⇒ 其余 3 条归后续轮次。
7. WHEN 现算 a3-console 的 wp_code 第二形态 THEN SHALL 为 **`A3C`** ⇒ 🔴 **打破「去连字符 + 首字母」规则**（按规则应为 `A33C`），判据禁按规则推导第二形态（依 AC-15）。

### Requirement 4 — BP-6：无权威册（a38），且 slice 归因须更正

**用户故事**：作为 slice 维护者，我要更正 BP-6 的归因 —— 问题不是「sheet 名不是 wp_code」，而是根本没有这本册。

#### 验收标准

1. 🔴 WHEN 现读 BP-6 原文 THEN SHALL 为「字面 `sheet-name` 不是 wp_code ⇒ `find_template_file_any` 现算返回 None（A3-8 的 `A3-8商誉减值测试`）」。
2. 🔴 WHEN 实证该归因 THEN SHALL 登记 `find_template_file_any('A3-8商誉减值测试')` → **None**，**但 `find_template_file_any('A3-8')` → 也是 None**；对照 `'A3-3'` / `'A5-1'` / `'A10-1'` 全能解析到真实册 ⇒ **BP-6 的归因只说对一半**，真因是 **`backend/wp_templates/A` 下根本没有 `A3-8` 开头的权威册** ⇒ 即使把 sheet 名改成纯码也解析不到（依 AC-46）。
3. 🔴 WHEN 修 BP-6 THEN SHALL 分两步且顺序不可颠倒：① **先确认权威册是否存在**（不存在则是模板供给缺口，须业务补册或显式声明该 entry 无权威册）② 再改 `sheet_name_literal` 从 `A3-8商誉减值测试` 到纯码。SHALL NOT 只做第 ② 步 —— 那样解析仍返回 None。
4. WHEN 登记 `sheet_name_literal` 形态 THEN SHALL 写明 **`A3-8商誉减值测试`**（码 + 中文连写、无分隔符）是 19 条 `literal_sheet_name` 里的**唯一异形**（其余全为纯码），依 AC-15。
5. WHEN 收口 BP-6 THEN SHALL 在 `design.md` 记录「补册」与「声明无册」两条路径的裁定与理由；收口后 BP-6 成员集 SHALL 变为空集。
6. 🔴 WHEN 现算全 slice BP-6 成员 THEN SHALL 为 **1** 条（仅 a38）⇒ A 域独占，无跨域协调成本。

### Requirement 5 — Property 22 缺陷收口（a38 的写死列数 + 裸下标 key）

**用户故事**：作为质控，我要修掉本轮 Property 22 在 A 域的唯一缺陷站点。

#### 验收标准

1. 🔴 WHEN 现读 a38 宿主 THEN SHALL 确认站点 `GtA38GoodwillImpairment.vue#L154`：`v-for="(_, i) in 5"` ⇒ **写死 5 列**（`column_count_hardcoded`）· `key_binding: "i"` ⇒ **裸下标作 key**（`key_is_bare_index`）· `label_binding: \`第${i + 1}年\`` ⇒ **两类缺陷同时命中**（依 AC-48）。
2. 🔴 WHEN 修复 THEN SHALL 同时修两类：① 列数改为由数据驱动（预测期年数应可配置，SHALL NOT 写死 5）② key 改为稳定 `{slot}_{seq}` 形态（AC 6.4 原文要求），SHALL NOT 用裸下标、SHALL NOT 用可改 label。
3. WHEN 现算全 slice Property 22 THEN SHALL 为站点 **7** / label-as-key **3** / verdict **PARTIAL**，A 域占 **1** 条站点（a38）⇒ 本 spec 修完后 A 域份额归零，但全 slice verdict 仍为 PARTIAL（其余归 B 域）。
4. WHEN 现算 BP-14 成员 THEN SHALL 为 **4** 条（a38 / b14-due-diligence-report / b23-process-control / b50-risk-assessment），本 spec 占 **1** 条。
5. 🔴 WHEN 陈述关系 THEN SHALL 指出 a38 同时是 **形态 2 的 mode 载体正面样板**（`{label, value}` 分离）**却在列层用裸下标作 key** ⇒ 同一文件在模式层做对、在列层做错，证明「label/key 解耦」意识未贯穿全层（依 AC-41 · AC-48 的同源裁定）。
6. WHEN 收口 THEN BP-14 的 a38 份额 SHALL 变为已修，且 `dynamic_column_identity` 的 A 域站点数 SHALL 从 1 降至 0。

### Requirement 6 — xlsx 侧模板缺陷（a3-console 的 A3-3 册）

**用户故事**：作为审计业务负责人，我要知道这本册有一处公式恒错和一处最严重的 definedName 污染。

#### 验收标准

1. 🔴 WHEN 现算 `A3-3` 册的 AE 列 THEN `AE6 ~ AE15` **全 10 行**有公式 `=(AB#+AC#+AD#)/(L#*J#)`，但 `AB/AC/AD` **只 r6 一行有公式**、`L/J` **也只 r6 有值**（L6=100 / J6=0.09 示例数据）⇒ **AE7 ~ AE15 分母 `(L#*J#)` 恒 0 ⇒ 恒 `#DIV/0!`**，反向分母 **10 : 1**（依 AC-40）。
2. 🔴 WHEN 判定缺陷族 THEN SHALL 写明这是 **A 域独有新族「公式行数超出数据行数致除零」**，与 N 轮的超列引用族（NC-32）**不同型** —— 那里是引用超出 `max_column` 的列，这里是引用同表内的空行；两者扫描器完全不同。
3. 🔴 WHEN 现算 `definedName` THEN SHALL 为 **261 / broken 190（73%）**，是 N 轮全域（72/45）的 **4 倍**；broken 名 SHALL 含 `_.dbf` · `_00510` · `_13` · `_1w6_` · **`_1固定资产数据库_筛选打印`** · **`_2其他资产_开办费除外_明细表`** · **`_3余额表_一级_.dbf`** · `_YE1` ⇒ **中文名 + `.dbf` 后缀 = dBase/Foxpro 时代旧底稿残留**（依 AC-9）。
4. 🔴 WHEN 现算 sheet 名 THEN 首张 sheet SHALL 为 **`结构化主体纳入合并范围判断F6-10`** —— 码是 **`F6-10`** 而 wp_code 是 `A3-3` ⇒ **跨循环码混入**，比 N 轮的 `O1A`/`O2A`（同字母体系）更严重（不同字母 + 不同编号体系）；🔴 SHALL 按原始字面量比对，禁归一化（依 AC-10 · AC-21）。
5. WHEN 现算 4 个 sheet 名 THEN SHALL 为 `结构化主体纳入合并范围判断F6-10` · `合并范围判断流程图（举例）` · `单一控制模型判断流程（参考）` · `权益与负债的区分的判断框架（参考）`；🔴 后三张是**参考资料型 sheet**（0 公式格），双向回写 SHALL 排除它们。
6. WHEN 现算 footer THEN SHALL 用 raw XML（依 AC-36）：sheet1 有 **`第 &P 页，共 &N 页`**（中文），其余 3 张**无 `<headerFooter>` 元素** ⇒ 三态中的两态。
7. 🔴 WHEN 本 spec 任何任务执行 THEN SHALL NOT 修改 `A3-3` 册 —— 交付后 sha256 须仍 match（本 spec 1 本 xlsx + foundation 1 本 + lane2 16 本 = 18/18）。
8. WHEN 现算 ghost 行 THEN `合并范围判断流程图（举例）` SHALL 为 **12** 行幽灵（`max_row` 45 vs `last_value_row` 33），其余 3 张为 0。
