# Requirements Document

## Introduction

E0 是货币资金函证 —— 七个函证循环（D0/E0/F0/G0/H0/K0/L0）里业务上最重要的一个
（银行函证是货币资金审计的核心程序，也是舞弊识别的第一道闸）。

**本 spec 已按用户要求重写**：第一版只做「4 项 override 接线」，属于按 `wp_code_overrides`
条目数反推缺口。逐 sheet 精读源模板
`backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx`
（20 个 tab，其中 13 张真实底稿，逐格读值+读公式+读合并区）后确认：
**真正的缺口在底稿内容与编制逻辑层，不在映射表层**，且第一版有两处判断是错的。

### 源模板的编制逻辑（一条询证函的全生命周期）

```
底稿目录（被审计单位/截止日/编制人 → 全部 12 张表的表头都 = 底稿目录!Ax）
   ↓
E0A 函证程序表（10 条程序 × 程序分类「常规★/备选」+ 底稿索引号）
   ↓
E1-3 银行存款及其他货币资金明细表  ← **外部工作簿引用**
   ↓ E0-3 的 D/G/K 列 = '[43]银行存款及其他货币资金明细表(仅人民币)E1-3'!$A/$C/$K
按品种分四张发函记录表（**四张不同构**，列集/是否有「是否函证」/汇总匹配键各不相同）：
   E0-3 货币资金（16 列 A:P，含 所属科目 / 是否函证 / 账户类型 / 是否属于资金归集 / 是否存在冻结担保或其他使用限制）
   E0-4 借款（16 列 A:P，含 所属科目 / 是否函证 / 借款类型 / 抵(质)押品·担保人 / 期末应付利息）
   E0-5 应付银行承兑汇票（10 列 A:J，含 票面金额 / 抵(质)押品；**无 是否函证、无 所属科目**）
   E0-6 理财产品（11 列 A:K，含 产品类型（封闭式/开放式） / 持有份额 / 产品净值 /
        是否被用于担保或存在其他使用限制；**无 是否函证、无 所属科目、无银行账号**，
        被询证单位列是 `C 开户行名称及收件人`、账号位由 `D 产品名称` 承担）
   ↓ E0-1 的 F 列 = 四层嵌套 IF，按 D 列「账户/交易」品种分派到不同表 + **不同匹配键**：
     银行存款/其他货币资金 → `SUMIF(E0-3!G:G, E0-1!E, E0-3!K:K)`      键=银行账号，取 账户余额（原币）
     短期借款/长期借款     → `SUMIFS(E0-4!I:I, E0-4!A:A,E0-1!D, E0-4!G:G,E0-1!E)` 键=所属科目+借款账号，取 余额
     应付票据             → `SUMIF(E0-5!A:A, E0-1!B, E0-5!G:G)`        键=索引号，取 票面金额
     理财产品             → `SUMIFS(E0-6!H:H, E0-6!A:A,E0-1!B, E0-6!D:D,E0-1!E)` 键=索引号+产品名称，取 产品净值
     （即 E0-1 的 E 列是**多态键**：银行账号 / 借款账号 / 产品名称，恰是表头「账号/理财产品名称」）
E0-2 核实被函证单位信息（三大区并列：
   B:O 被函证单位信息核对 14 列（含 银行官网公示的函证集中处理地址 / 是否一致 / 核实方式 / 支持性文件索引号 / 说明是否合理）
   P:AA 回函信息情况 11 列（含 是否原件 / 是否直接收到 / 回函发出地址含物流信息 / 三个「是否一致」）
   AB:AD 第一次发函结果（送抵/退回）/ 经核实的原因 / 该原因是否合理）
   ↓ E0-1 的 C/J/M/N/P/T/U 列 = VLOOKUP(索引号, E0-2!A:AL, {2,3,4,10,16,19,22})
E0-1 函证结果汇总表（上区 30 列 4 组 + 下区三块统计/说明/结论）
   ↓ 回函情况汇编 的 AC/AD = VLOOKUP(索引号, 银行函证其他信息核对表E0-5!B:E, {3,4})
银行函证其他信息核对表E0-5（20 列：13 个**询证函标准条款要项** 各选 回函相符/回函不符，
   「回函是否异常」「异常项目」为公式派生；C 列注明数据来自**函证中心导出表的「是否相符」列**）
回函情况汇编（33 列：按 4 品种横向展开 发函余额/回函金额/金额差异 + 货币资金受限金额
   + 「4、未收到回函的替代程序」3 列 + 其他信息核对是否异常/异常项；下区 4 品种×5 指标 + 11 条编制说明 + 参考结论 A/B/C）
E0-7 跟函函证过程控制（**备忘录式**，5 段带 [ ] 占位的银行专属话术 + 3 个「是否」项 + 手书签名）
邮件传真回函核对记录F1-12（21 列：按**回函渠道**分 邮寄 5 项 / 跟函 3 项 / 电子平台 6 项
   + 经办人复核人签名 + 与银行公示名单相符 + 回函可靠性结论）
E0-8 函证程序舞弊风险评价表（19 条舞弊迹象 × 是否存在/索引号或信息来源/应对措施，H26 明写汇总去向 `B50`）
```

### 第一版的两处判断被源模板推翻

| 第一版结论 | 源模板实证 |
|---|---|
| `reliabilityCode: null`「E0 无回函可靠性验证 sheet」 | **有** ——「邮件传真回函核对记录F1-12」就是可靠性表，只是索引号借用了 F1-12（F1 实为预付款项，属源模板索引贴错），且它比 D0-7 **宽**（4 渠道 + 银行公示名单核对） |
| `银行询证函其他信息核对表E0-5` | 真实 tab 名是 **`银行函证其他信息核对表E0-5`**（无「询证」二字），DB `workpaper_sheet_classification` 记的才是对的 |

### 🔴🔴 第二版又被 `sheet_state` 推翻：三张表是**隐藏 sheet**（2026-08-02，openpyxl 实证）

`openpyxl.load_workbook(...)[name].sheet_state` 全量扫 20 个 tab 的结论 —— **只有 10 个 visible**，
恰好 = `底稿目录` + 它 D9:F11 索引的 **9 张底稿**（E0A / E0-1 / E0-2 / E0-3 / E0-4 / E0-5 /
**E0-6** / E0-7 / E0-8）。其余 10 个全 `hidden`。

| sheet | state | 对第二版结论的影响 |
|---|---|---|
| `理财产品发函记录表E0-6` | **visible** | ✅ 是 9 张之一，专属组件打磨方向正确 |
| `银行函证其他信息核对表E0-5` | **hidden** | ⚠️ 第二版把「13 要项零实现」列为**最大缺口 / 核心表**（Requirement 1，最高优先级）**过重** —— 它不在 9 张索引底稿内 |
| `邮件传真回函核对记录F1-12` | **hidden** | ⚠️ Requirement 7「`reliabilityCode` 应声明它」需重新裁决 —— 隐藏 sheet 不参与 render 分发 |
| `回函情况汇编` | **hidden** | ⚠️ Requirement 8.6 的「独立底稿 vs E0-1 视图」二选一，前提变了 |
| `函证程序表-原版本备份` / `函证结果汇总表E0-1（原）` / `(备份)` / `-旧版`×2 / `F1-10-原` / `参考用-往来函证程序` | hidden | 与第二版判断一致（参考件） |

**并发会话已按此落地**：`wp_code_overrides.json` 把这三张 + 参考件全部置 `skip`，
并新增 `backend/tests/test_e0_hidden_sheets_skipped.py`（以 `sheet_state` 为裁决者）。
本 spec 的 Requirement 1 / 7 / 8.6 **需按「隐藏 sheet 是否仍要实现」重新裁决**
（隐藏 ≠ 无价值：可能是事务所备用表单；但不能再当"最高优先级核心缺口"）。

**教训（第三次同款）**：判 sheet 是否为真实底稿，`wb.sheetnames` 不够，
必须同时看 **`sheet_state`** 与 **`底稿目录` 的索引清单**（两者本次完全吻合，互为旁证）。

### ✅ 裁决门 A：**已裁决 = A-否（2026-08-02 用户明确答复「三张隐藏底稿不需要再实现了，已隐藏」）**

**结论落地**：Requirement 1（13 要项表）/ Requirement 7.1·7.5（F1-12 回函可靠性启用）/
Requirement 8.6·8.7（回函情况汇编形态二选一）**整体作废**；
tasks.md 的 Wave 6（Task 7/8/9，~39 KB 组件）**已删除**，任务数 19 → 16。
下方保留原裁决表与 AC 正文作为**存档**（口径已核实清楚，将来若另立 spec 可直接取用），
但**不再是本 spec 的交付范围**。

**A-否 之后仍然必做的三条**（不要连带砍掉）：

1. **`cycleConfirmationMeta.E0.reliabilityCode` 的注释必改** —— 取值 `null` 恰好正确，
   但注释「E0 无回函可靠性验证 sheet」**是错的**（源模板有 `邮件传真回函核对记录F1-12`，
   只是 hidden + `skip`）。**结论错、取值对**是最危险的形态，下个会话会照注释再判一次。
2. **Requirement 7.2/7.3/7.4（可靠性按渠道补 12 列）照做** —— 那是**七枢纽共享件增强**，
   D0-7 等**可见**的回函可靠性表同样受益，与 E0 那张 sheet 是否渲染无关。
3. **守卫：override 的 `skip` 集合 ∩ meta 的非 null code = ∅**（Property 12 补充）+
   **`银行函证其他信息核对表E0-5` 的全名 `skip` 条目不得删除**（见下方「A-否 的守卫要求」）。

### A-否 的守卫要求（2026-08-02 落地，实证代码路径）

**`E0-5` 一码两表已被 A-否 自然消歧，`e0-send-list-dedicated-components` 的 Task 14（override 消歧）不再需要** ——
实证 `wp_render_config.py` 的两条判定顺序**相反**，恰好使当前配置正确：

| 判定 | 行 | 顺序 | 对 `E0-5` 的作用 |
|---|---|---|---|
| **skip：按完整 sheet_name 精确匹配** | L709 | **先** | `银行函证其他信息核对表E0-5` → `skip` → `continue`，**永不进入下方 componentType 解析** |
| skip：按提取编码（尾码）匹配 | L722 | 后 | 尾码 `E0-5` 当前是 `d-form-table` ≠ skip → 不拦 |
| **componentType：尾码优先，全名与 `{wp_code}-{sheet}` 作 fallback** | L749~758 | —— | `应付银行承兑汇票发函记录表E0-5` → 尾码 `E0-5` → 取值 |

→ send-list spec 把短键 `E0-5` 改成 `confirmation-send-list-e05` 后仍然安全，
因为核对表在 L709 就被拦下了。**但这构成一条必须钉死的不变式**：

> `银行函证其他信息核对表E0-5` 的**全名 `skip` 条目 SHALL NOT 被删除或改值**。
> 一旦删除，该 hidden sheet 会在 L749 按尾码解析成 `confirmation-send-list-e05`
> 并作为一个多出来的页签渲染成"应付银行承兑汇票发函记录表"的形态（列集完全不符）。

该守卫归 `e0-send-list-dedicated-components` 的 Task 14（已降级为「只加守卫、不改查表顺序」）。

<details>
<summary>裁决门 A 的原始分析（存档，2026-08-02 复盘时写，已由用户裁决 A-否）</summary>

**受影响的需求**：Requirement 1（13 要项表）/ Requirement 7（F1-12 回函可靠性）/
Requirement 8.6（回函情况汇编形态二选一）—— 三者当时标为 **条件需求 [Conditional-A]**。

| 裁决 | 后果 |
|---|---|
| **A-否**（隐藏底稿不实现） | R1 / R7 / R8.6 **整体作废**；Wave 3（Task 7/8/9，~39 KB 组件）不开工；Task 2 的两项核实降级为「记录结论 + 说明为何不实现」；`cycleConfirmationMeta.E0.reliabilityCode` 保持 `null` 并把「F1-12 是隐藏 sheet」写进注释（**推翻第二版的"注释是错的"结论**：注释结论错，但 `null` 这个取值恰好正确）；send-list 的 R17.2/R17.3（资金归集勾稽）永久留遗留 |
| **A-是**（隐藏底稿仍要实现） | 必须**先**做 send-list 的 Task 14（override 消歧）—— 否则 `银行函证其他信息核对表E0-5` 被 `E0-5` 尾码键遮蔽，新组件永不渲染；且 Wave 3 **移到最后一个 wave**（它不是"最高优先级核心缺口"，第二版把它排在 Wave 3 是基于「13 要项零实现 = 最大缺口」这个已被 `sheet_state` 推翻的前提）；另需先解掉「隐藏 sheet 不进 render 分发」这一平台前提（现状 override 已置 `skip`） |

**未裁决前**：Wave 3 SHALL NOT 开工；Wave 1 的 Task 1 中「13 要项 / F1-12 / 回函情况汇编」
相关断言 SHALL 标为 `@pytest.mark.skipif(not E0_HIDDEN_SHEETS_IN_SCOPE)` 或直接不写，
**SHALL NOT 让守卫先绿再回头删**（守卫绿了会被当成"已实现"的证据）。

**倾向**：A-否。理由三条 ——
① `底稿目录` D9:F11 只索引 9 张，且与 10 个 visible sheet（含目录本身）完全吻合，两个独立证据一致；
② `wp_code_overrides` 已把三张置 `skip` 且该 `skip` 走全名精确匹配、**确实生效**（并发会话已加
`test_e0_hidden_sheets_skipped.py` 以 `sheet_state` 为裁决者）；
③ 隐藏 ≠ 无价值，但「事务所备用表单」不该占用一个 spec 的最高优先级 wave。
若用户认为 13 要项核对表业务上必须有（它确实是函证完整性的核心表），
更合适的做法是**另立 spec**并先解平台侧「隐藏 sheet 如何可控地纳入渲染」，
而不是在本 spec 里绕过 `skip`。

</details>

### 逐项实证的缺口（本 spec 的范围）

1. ~~**13 个询证函条款要项在平台零实现**~~ —— **已出范围（裁决门 A = A-否）**。
   业务上它是「函证完整性」的核心表（`confirmation-diff-*` 管金额差异、替代不了要项相符性），
   但 `银行函证其他信息核对表E0-5` 为 hidden + `skip` → 不实现。
   要项清单（`注销账户 / 委托贷款(委托人) / 委托贷款(借款人) / 对外担保 / 接受担保 /
   贴现商业汇票 / 托收商业汇票 / 信用证 / 外汇买卖合约 / 托管证券或其他产权文件 /
   银行理财产品 / 其他 / 附表(资金归集)`）留在 Requirement 1 存档，供将来另立 spec 取用。
2. **E0-1 列集与源模板不符** —— 缺 4 列（`抵押质押等事项回函说明` / `其他函证事项回函是否相符` /
   `函证不符事项说明` / 行级`审计结论`），多 8 列源模板没有的（`选取样本目的` / `联系人` /
   `联系电话` / 替代程序 4 列 / `备注`）。E0-1 源模板**没有替代程序区**（替代程序在「回函情况汇编」）。
3. **E0-1 下区「一、函证情况」6 品种 × 6 指标矩阵未实现** ——
   `其他货币资金 / 短期借款 / 长期借款 / 应付票据 / 理财产品` 在 `GtConfirmationSummary.vue` 全 0 命中。
4. **`GtConfirmationSummary.vue` 的 CrossRef 规则写死 `D0-5/D0-6/D0-7`** —— 而 `cycleConfirmationMeta`
   已备好 `buildCrossRefRules(wpCode)` 且会跳过 null sheet。E0 挂上去仍显示自己没有的表。
5. **`importE0ListsToSummary` 六个取数缺陷**（2026-08-02 逐格精读 E0-3~E0-6 后从 3 条修正为 6 条；
   **下列六条中的五条已由并发会话修复，见 Requirement 5 的状态更正 —— 保留原文作为诊断依据**）：
   - **🔴 P0 `是否函证` 门把 E0-5/E0-6 整表滤空** —— `buildSummaryRowsFromListRows` 第一道门是
     `if (!isConfirmFlagYes(raw)) continue`，而源模板**只有 E0-3(E5)/E0-4(E5) 有「是否函证」列**，
     **E0-5 与 E0-6 根本没有该列** → 这两张表恒 0 候选。**故只修 `AMOUNT_KEYS` 不解决问题**：
     应付票据与理财产品两品种永远进不了 E0-1。（`是否函证` 对这两张表的语义 = 入表即发函）
   - **🔴 P0 `account_no` 从未被带入** —— 产出行只写 `entity_name/confirm_index/account_type/amount`，
     而 E0-1 F 列（发函金额）的源公式**按 E 列「账号/理财产品名称」匹配**：
     E0-3 `SUMIF(E0-3!G:G, E0-1!E, E0-3!K:K)` / E0-4 `SUMIFS(…,E0-4!G:G, E0-1!E)` /
     E0-6 `SUMIFS(…,E0-6!D:D, E0-1!E)` → E 列空则汇总恒 0（与 `AMOUNT_KEYS` 并列的**第二条**归零路径）
   - **🔴 P0 去重键遗漏 `account_no` → 静默丢行** —— `dedupeSummaryRows` 的 keyOf =
     `entity_name || account_type`。同一家银行的多只理财产品（entity 相同、品种同为「理财产品」）
     **第 2..N 只被判重复丢弃**；E0-3 同一家行多个账号同理。源模板的匹配键是二元组
     （E0-6 = 索引号 + 产品名称 / E0-3 = 银行账号），去重键必须含 `account_no`
   - **`AMOUNT_KEYS` 无 `票面金额`(E0-5) 与 `产品净值`(E0-6)** → 这两品种发函金额恒 0
   - **E0-4 品种真源是 A 列「所属科目」不是 O 列「借款类型」** —— 源公式匹配
     `E0-4!$A:$A ↔ E0-1!$D`；两列并存，`所属科目` 才是 E0-1「账户/交易」的对应列，
     `借款类型` 只能作兜底。原第一版结论（"读 `借款类型` 分流"）需修正
   - `E0-5` 一码两表，`fetchWorkpaperHtmlRows(projectId,'E0-5')` 可能拿到「银行函证其他信息核对表」
6. **E0-7 备忘录模板是 D0-3 口径**（前往被询证单位跟函），而源模板是**银行专属 5 段**：
   对公柜台办理（银行工作人员姓名+**工号**、复核人姓名+工号）/ 对公柜台不办理转部门 /
   银行无法即时确认→留函待寄回致同办公室 / 银行已对全部项目作出回应且回函流程·用章·受理部门与**公示内容一致** /
   事后收回补记。现模板无「工号」「银行公示制度核对」概念。
7. **回函可靠性列集缺 9 项**（**共享件缺口，无条件成立** —— 与 F1-12 那张 sheet 是否渲染无关，
   D0-7 等可见的可靠性表同样缺这些渠道核对项）—— `ReliabilityRow` 覆盖传真/邮件真实性，但缺邮寄渠道 3 项
   （信封名称地址一致 / 邮戳发出城市一致 / 回函信息完整）、跟函渠道 3 项、电子平台 4 项
   （电子签名一致 / IP 地址一致 / 平台操作时间 / 意见反馈）、银行特有 2 项
   （经办人与复核人分别签名 / 签字人员与银行公示名单相符）。
8. **`E0-7` 无 componentType 映射**（仍成立）；
   **`E0-6` 已解决** —— 并发会话已交付专属组件 `confirmation-wealth-list` 全链
   （前端 registry + `_CONFIRMATION_COMPONENTS` + `_CONFIRMATION_FORMAT_MAP` +
   `wp_classification_service` + `wp_code_overrides` 编码尾码与 sheet_name **两处**），
   且 `test_confirmation_sheet_override_contract.py` 硬断言两个键都指向它。
   → `e0-send-list-dedicated-components` 原计划的 `confirmation-send-list-e06` **已撤回**，
   那边只做「符合度核查」，本 spec 的 R8 保留 wealth-list 为唯一 E0-6 形态。
9. ~~**「回函情况汇编」无 wp_code、无 override、`functional_type` 为 NULL**~~
   —— **已出范围（A-否）**，hidden + `skip`；结构结论按 R8.7b 留存进 Notes。
10. **E0-3 的受限标记未联动 E1** —— 源模板「回函情况汇编」O 列本想 `SUMIF(E0-3!B:B, 索引号, ...)`
    汇总「货币资金受限金额」，公式已坏成 `#REF!`（源模板自身缺陷）。而 E1 侧刚做完受限资金 ②表
    与受限资产附注段 → 这条联动是现成的高价值缺口。
11. **`handleJumpB50()` 是 TODO stub**（`console.log`）—— E0-8 源模板 H26 明写汇总去向 `B50`。
12. **E0 公式预设块双重贴错标签** —— `sheet='审定表E0-1'` 与 `wp_name='银行询证函'`
    在源 xlsx 都不存在（真实为 `函证结果汇总表E0-1`）。
13. **四张发函记录表 `functional_type` 为 NULL**（其余函证 sheet 都是 `confirmation`）。

**不做的**：不重建源模板没有的表；不改源模板 sheet 名；不把 `F1-12` 的索引号"修正"成 E0-x
（源模板索引贴错是它的事实，改索引会打断 `回函情况汇编` 与既有项目数据）。

## Requirements

### Requirement 1: ~~银行函证其他信息核对表（13 个条款要项）~~ —— **已作废（裁决门 A = A-否）**

> **本需求不在交付范围内**（2026-08-02 用户裁决）。
> `银行函证其他信息核对表E0-5` 经 `sheet_state` 实证为 **hidden**、不在 `底稿目录` 索引的
> 9 张底稿内、override 已置 `skip` 且生效 → 第二版把它列为「最高优先级核心缺口」的前提已失效。
> 对应的 Wave 6（Task 7/8/9）与 design 的 §1 `confirmation/otherItems/`、
> Property 1/2/3 **均已标作废**。
> 下方 AC **保留为存档**：13 要项的列名/列号/派生公式口径已逐格核实清楚，
> 若将来平台侧解决「隐藏 sheet 可控纳入渲染」后另立 spec，可直接取用不必重新精读。

**User Story:** 作为审计助理，我需要逐条核对询证函标准格式里 13 个条款要项的回函相符性，
并让异常项自动汇总，而不是自己在备注里写一段话。

#### Acceptance Criteria

1. WHEN 渲染 `银行函证其他信息核对表E0-5` THEN SHALL 呈现源模板的 20 列，
   13 个要项 SHALL 逐字取自源模板 F6:R6（`3.注销账户` … `15.附表(资金归集)`，含序号前缀）
2. WHEN 每个要项取值 THEN SHALL 为 `回函相符 / 回函不符` 二选一枚举（可留空 = 未核对）
3. WHEN `回函情况` ∈ {未回函, 退函, 待确认} THEN `回函是否异常` SHALL 派生为 `是`
   且 `异常项目` SHALL 派生为 `未回函/退函/待确认`
4. WHEN 任一要项 = `回函不符` THEN `回函是否异常` SHALL 派生为 `是`
   且 `异常项目` SHALL 为全部不符要项**按列序拼接**的字符串（与源模板 E7 公式同序）
5. WHEN 无不符要项且回函情况正常 THEN `异常项目` SHALL 派生为 `无异常`
6. WHEN `回函是否异常` / `异常项目` 被渲染 THEN SHALL 只读派生，SHALL NOT 可手工编辑
7. WHEN 该表数据来源被标注 THEN SHALL 写明「函证中心导出表的『是否相符』列」（源模板 C5 原文）
8. WHEN 某要项判为不符 THEN SHALL 可填 `回函不符原因` 与 `相关资料索引号`
9. WHEN 该表已录数据 THEN E0-1 的 `其他函证事项回函是否相符` SHALL 能按索引号取到该行的 `回函是否异常`

### Requirement 2: E0-1 列集与源模板对齐

**User Story:** 作为审计助理，E0-1 应该只显示源模板有的列，且源模板有的列一个都不能少。

#### Acceptance Criteria

1. WHEN 解析 E0 的汇总表列集 THEN SHALL 包含 `抵押质押等事项回函说明` /
   `其他函证事项回函是否相符` / `函证不符事项说明` / 行级 `审计结论` 四列
2. WHEN 解析 E0 的汇总表列集 THEN SHALL NOT 包含替代程序四列
   （`是否采取替代程序` / `替代程序确认金额` / `替代后不可确认金额` / `替代程序索引`）
   —— 源模板 E0-1 无替代程序区，替代程序在「回函情况汇编」
3. WHEN 某枢纽需要剔除 BASE 列 THEN SHALL 通过**配置**（如 `CYCLE_EXCLUDED_COLUMNS`）实现，
   SHALL NOT 在渲染层写 if-else
4. WHEN 剔除机制引入 THEN 其余六个枢纽的列集 SHALL 逐字节不变（零回归）
5. WHEN 新增列被渲染 THEN 其 `group` SHALL 与源模板的分组表头一致
   （四列均在 E0-1 主表尾部，属独立列不并入前四组）
6. WHEN 新增列声明 `source` THEN SHALL 逐字写明源模板列名与列号

### Requirement 3: E0-1 下区「函证情况」品种矩阵

**User Story:** 作为现场经理，我要一眼看到每个品种的函证覆盖率与回函确认率，
而不是自己拿计算器算。

#### Acceptance Criteria

1. WHEN 渲染 E0-1 下区 THEN SHALL 呈现 6 品种
   （`银行存款 / 其他货币资金 / 短期借款 / 长期借款 / 应付票据 / 理财产品`）
   × 6 指标（`本期（期末）账面金额` / `抽取样本的发函金额` / `发函金额占账面金额的比例` /
   `回函确认金额` / `回函可确认金额占发函金额的比例` / `回函可确认金额占账面金额的比例`）
2. WHEN 计算 `抽取样本的发函金额` THEN SHALL 按品种对主表 `发函金额（原币）` 求和
   （对齐源模板 `SUMIF(D:D, 品种, F:F)`）
3. WHEN 计算 `回函确认金额` THEN SHALL 按品种对主表 `可确认金额（原币）` 求和
4. WHEN 分母为 0 THEN 比例 SHALL 为 0 而非 `NaN` / `Infinity`（对齐源模板 `ISERROR` 兜底）
5. WHEN `本期（期末）账面金额` 可从四表取数 THEN SHALL 预填并标注取数口径；
   取不到 THEN SHALL 留空可手填，SHALL NOT 填 0 冒充
6. WHEN 品种矩阵为纯派生 THEN 除 `本期（期末）账面金额` 外 SHALL 全部只读
7. WHEN 渲染 E0-1 下区 THEN SHALL 呈现源模板的**全部四块**而非仅矩阵一块
   （逐格实证：`C27 一、函证情况` / `O27 二、样本选择` / `V27 三、审计说明` / `V34 四、审计结论`，
   另有 `A37 提示：对收到的回函重点检查：` + `A38`（合并 `A38:N38`）四条提示）
   —— 第二版只写了「一、函证情况」，是因为首轮 dump 只取了 A..L 列而漏掉 O/V 列
8. WHEN 渲染「二、样本选择」THEN SHALL 就地展示源模板四段固定说明文字
   （逐字：`O28 所有银行账户全部函证（包括零余额账户和在本期内注销的账户）。` /
   `O29 如果存在未函证的银行账户应记录不执行函证程序的理由。` /
   `O30+O31 审计准则规定的可以不执行银行函证程序的理由是：银行存款、借款及与金融机构往来的其他重要信息对财务报表不重要且与之相关的重大错报风险很低。`
   —— O30/O31 是**一句话被源模板拆成两行**，渲染时 SHALL 合并为一句），
   并提供「未函证账户的理由」录入位置；SHALL NOT 只把这四段塞进 guidance 折叠区
   （它是准则要求的记录义务，不是编制提示）
9. WHEN 「二、样本选择」渲染 THEN SHALL 与 `e0-send-list-dedicated-components` 的 R16
   （E0-3 函证范围完整性红线）**交叉引用同一准则要求**：`O28` 是该红线的第二处源模板依据
   （第一处是 `函证程序表E0A` 程序 1 的同款措辞）→ 本 spec 只负责**说明文字与理由录入位置**，
   零余额/注销账户的**逐账户校验**归 send-list spec 的 R16，两侧 SHALL NOT 各造一份判定逻辑
10. WHEN 渲染「三、审计说明」THEN SHALL 呈现源模板三条小标题作为分段引导
    （`V28 1.对询证函保持的控制的说明` / `V30 2.针对不符事项的程序` /
    `V32+V33 3.如果银行回函中存在未函证的其他信息（如XX账号未包含在本函证证中，具体信息另函回复等），应考虑未函证信息的影响，并考虑实施进一步审计程序`
    —— V32/V33 同样是一句话拆两行；`本函证证` 是源模板笔误，SHALL 原样保留不"修正"），
    每段独立可录入 + 各带 AI 辅助与复核触发
11. WHEN 渲染「四、审计结论」与「提示」THEN 结论 SHALL 可录入且带 AI 辅助；
    「提示」四条 SHALL 作为只读方法论上下文就地展示（琥珀色左边线，源模板 A38 逐字）

### Requirement 4: 跨表引用文案按循环解析

**User Story:** 作为审计助理，在 E0 的汇总表上不该看到 `D0-5/D0-6/D0-7` 这些 E0 根本没有的底稿。

#### Acceptance Criteria

1. WHEN `GtConfirmationSummary` 渲染 CrossRef 规则 THEN SHALL 调用
   `buildCrossRefRules(wpCode)`，SHALL NOT 使用写死的 `D0-*` 常量
2. WHEN 某循环该 sheet 为 `null` THEN 对应规则行 SHALL 不出现
3. WHEN 挂在 E0 上 THEN SHALL NOT 出现 `D0-` 字样
4. WHEN 守卫扫描 `confirmation/**` THEN 共享组件里 SHALL NOT 残留写死的 `D0-` sheet 编码
   （已按 wpCode 解析的除外，需逐条登记豁免并写明理由）

### Requirement 5: 发函清单带入 E0-1 的取数纠偏 —— **主体已由并发会话落地（2026-08-02）**

> **状态更正**：`importE0ListsToSummary.ts` 已由 124 行改写到 357 行，
> 引入声明式 `E0_LIST_SPEC` + `hasConfirmFlag` + `account_no` + per-list `amountKeys`
> （含 `票面金额` / `产品净值`）+ 三元去重键 + E0-4 `所属科目` 优先。
> 即 **AC 1/2/4/7/8/9/10 已实现**，Task 11 的 `[ ]` 是**假红**（见 tasks.md 更正）。
> **剩余未完成**：
> - AC 3 的「回退时标注 `fallback`」与 AC 6 的「报告命中/跳过统计并在 UI 展示」—— 需核实
> - AC 5（E0-5 命中核对表时返 0 候选）—— **A-否时天然成立**（核对表已 `skip`，
>   `fetchWorkpaperHtmlRows` 拿不到它），但守卫仍应保留反向断言防将来 override 变动
> - **🔴 硬前置仍未解**：`fetchWorkpaperHtmlRows` 的两处断点（wp_code 解析 + `_format` 匹配）
>   未解则上述改动全部是 dead code —— 详见 tasks.md Task 11 的硬前置节。
>   这是「口径改对了但一行数据都拿不到」，属**验收必须端到端实测**的典型

**User Story:** 作为审计助理，四张发函记录表填好后，E0-1 应该拿到正确的品种、账号/产品名称和金额，
且同一家银行下的多个账号/多只产品各占一行不被合并。

#### Acceptance Criteria

1. WHEN 从 `E0-5 应付银行承兑汇票发函记录表` 带入 THEN 发函金额 SHALL 取 `票面金额`
2. WHEN 从 `E0-6 理财产品发函记录表` 带入 THEN 发函金额 SHALL 取 `产品净值`；
   SHALL NOT 取 `持有份额 × 产品净值`（源模板 E0-1 F 列直接 `SUMIFS(E0-6!$H:$H,…)`，
   与其余三张表一样是**总额口径列**，`持有份额` 是询证函正文的补充信息）
3. WHEN 从 `E0-4 借款发函记录表` 带入 THEN 品种 SHALL 优先读 `所属科目`（源公式匹配列）
   区分 `短期借款` / `长期借款`；该列为空 THEN SHALL 回退读 `借款类型`；
   两列皆空 THEN SHALL 回退 `短期借款` 并在带入结果里标注回退
4. WHEN 从 `E0-3` 带入 THEN 品种 SHALL 优先读 `所属科目`，其次按 `账户类型` 启发式判别
   `银行存款` / `其他货币资金`
5. WHEN 带入 `E0-5` 而该 wp_code 命中的是「银行函证其他信息核对表」
   THEN SHALL 不产生候选行，SHALL NOT 把核对表的行当发函记录带入
6. WHEN 带入完成 THEN SHALL 报告每张清单的命中行数与跳过原因，SHALL NOT 静默返回空
7. WHEN 清单来源是 `E0-5` 或 `E0-6` THEN SHALL NOT 用「是否函证」列过滤
   （源模板这两张表**无该列**，过滤即整表归零）；有该列的 `E0-3`/`E0-4` SHALL 继续按其过滤
8. WHEN 任一清单带入 THEN SHALL 填充 `account_no`，取值按清单分别声明：
   E0-3 `银行账号` / E0-4 `借款账号` / E0-5 `银行承兑汇票号码` / E0-6 `产品名称`
   （E0-1 的 E 列「账号/理财产品名称」是源公式的匹配键，留空则发函金额汇总恒 0）
9. WHEN 从 `E0-6` 带入 THEN `entity_name` SHALL 取 `开户行名称及收件人`（被询证单位是银行），
   SHALL NOT 取 `产品名称`（产品名称归 `account_no`）
10. WHEN 去重 THEN 键 SHALL 含 `account_no`（与 `entity_name` + `account_type` 并列），
    使同一家银行的多个账号 / 多只理财产品各占一行；
    SHALL 有反向自检用例证明旧二元键会丢行

### Requirement 6: E0-7 跟函备忘录改为银行口径

**User Story:** 作为审计助理，E0-7 的备忘录话术应该是银行柜台/部门办理那一套，
含银行工作人员工号与银行公示制度核对，而不是通用的"前往被询证单位"。

#### Acceptance Criteria

1. WHEN 在 E0 上使用备忘录模板 THEN SHALL 提供源模板的五种场景话术
   （对公柜台办理 / 对公柜台不办理转部门 / 无法即时确认留函待寄回 / 已对全部项目作出回应 / 事后收回补记）
2. WHEN 话术含银行经办与复核人员 THEN SHALL 包含**姓名与工号**两个占位
3. WHEN 话术含回函流程核对 THEN SHALL 包含「回函工作流程、回函用章及函证受理部门名称、
   地址、联系电话与被询证银行管理制度及公示内容一致」这一断言项
4. WHEN 在 D0/F0/G0/H0/K0/L0 上使用 THEN 现有通用话术 SHALL 逐字不变（按循环选模板）
5. WHEN 渲染 E0-7 THEN SHALL 呈现源模板的三个「是否」项
   （是否了解处理函证的通常流程和处理人员 / 是否确认询证函处理人员的身份及权限 /
   处理人员是否按正常流程处理）与签名栏
6. WHEN `E0-7` 的 componentType 被解析 THEN SHALL 返回 `confirmation-followup`
7. WHEN `cycleConfirmationMeta.E0.followupCode` 与 override 表不一致 THEN 守卫 SHALL 失败

### Requirement 7: 回函可靠性按渠道补列（共享件增强）—— **7.1/7.5 已作废，7.2~7.4 照做**

> **裁决落地（A-否）**：`邮件传真回函核对记录F1-12` 是 **hidden** sheet（不在 9 张索引底稿内、
> override 已 `skip`）→ **7.1 与 7.5 作废**（不把它声明为 `E0.reliabilityCode`）。
>
> **7.2/7.3/7.4 照做**：按渠道补 12 列是**七枢纽共享件**的能力增强 ——
> 邮寄 3 项 / 跟函 3 项 / 电子平台 4 项 / 银行特有 2 项在**任何**函证循环都适用，
> **D0-7 那张可见的回函可靠性表直接受益**，与 E0 那张 sheet 是否渲染无关。
> 验收实测改在 **D0-7** 上做（E0 侧不可达）。
>
> **7.6（新增，无条件必做）**：`cycleConfirmationMeta.E0.reliabilityCode` 取值保持 `null`
> （恰好正确），但注释 SHALL 改为
> 「源模板有 `邮件传真回函核对记录F1-12`，但为 hidden sheet 且 override 置 skip，故不启用」。
> 现注释「E0 无回函可靠性验证 sheet」**是错的** —— **结论错、取值对**是最危险的形态，
> 守卫查不出，下个会话会照注释再判一次。

**User Story:** 作为审计助理，银行回函的可靠性核对要按邮寄/跟函/电子平台三种渠道分别记录，
并核对签字人员是否在银行公示名单里。

#### Acceptance Criteria

1. WHEN 核实 `邮件传真回函核对记录F1-12` 是 E0 的回函可靠性底稿
   THEN `cycleConfirmationMeta.E0.reliabilityCode` SHALL 声明它，
   注释 SHALL 写明「源模板索引号沿用 F1-12，非 E0-x」
2. WHEN 可靠性行模型被扩展 THEN SHALL 新增邮寄渠道 3 项 / 跟函渠道 3 项 /
   电子平台 4 项 / 银行特有 2 项，字段名与源模板列名对照 SHALL 写在类型注释里
3. WHEN 新字段引入 THEN 既有 `reliability-v1` 载荷 SHALL 仍可读（新字段缺省 `undefined`），
   D0/F0/G0/H0/K0/L0 的可靠性表现 SHALL 逐字不变
4. WHEN 回函渠道已知 THEN SHALL 只展开该渠道的核对项，其余渠道项 SHALL 折叠或置灰
5. ~~WHEN 该 sheet 的 wp_code 解析不到 THEN SHALL 如实记录为遗留并说明所需平台改动~~
   —— **已作废（A-否）**，该 sheet 为 hidden + `skip`，wp_code 归属问题不再需要解
6. WHEN `cycleConfirmationMeta.E0.reliabilityCode` 保持 `null` THEN 其注释 SHALL 写明
   「源模板有 `邮件传真回函核对记录F1-12`，但为 hidden sheet 且 override 置 skip，故不启用」，
   SHALL NOT 保留现有的「E0 无回函可靠性验证 sheet」（该结论已被源模板证伪）
7. WHEN 验收 7.2~7.4 THEN 实测 SHALL 在 **D0-7**（可见的回函可靠性表）上进行，
   SHALL NOT 因 E0 侧不可达而跳过实测

### Requirement 8: E0-6 / 回函情况汇编 / 一码两表

**User Story:** 作为审计助理，E0 的每张真实底稿都应有明确的渲染形态，不掉进默认分支。

#### Acceptance Criteria

1. WHEN 解析 `E0-6` 的 componentType THEN SHALL 返回**专属类型** `confirmation-wealth-list`，
   SHALL NOT 退回通用 `d-form-table`
   （用户裁决 2026-08-02：通用表格「太丑」，要按 D0 函证底稿家族的专属 HTML 形态精细打磨。
   原第一版结论「与 E0-3/E0-4 一致即可」作废 —— 那只是"不掉进默认分支"的底线，
   不是打磨目标。E0-6 有独立的审计判断维度：受限标记 / 到期日 / 汇总键完整性，
   通用表格无法承载看板与勾稽）
2. WHEN E0 的发函记录表集合被枚举 THEN SHALL 覆盖 E0-3 / E0-4 / E0-5 / E0-6 四张
3. WHEN 两张 sheet 共用 wp_code `E0-5` THEN 系统 SHALL 能按 **sheet 名**而非 wp_code
   区分它们的 componentType
4. WHEN 消歧方案落地 THEN SHALL NOT 修改源模板 sheet 名
5. WHEN 无法在不改平台机制的前提下消歧 THEN SHALL 如实记录为遗留并说明所需平台改动，
   SHALL NOT 用「随便挑一张」的方式糊过去
6. ~~WHEN 核实「回函情况汇编」是否需要独立组件 THEN 结论 SHALL 二选一~~
   —— **已作废（A-否）**：该 sheet 为 hidden 且 override 已 `skip`，
   **既不新建组件、也不在 E0-1 内做「按品种横向」视图切换**
   （视图切换会把一张用户看不到的表的形态引进可见底稿 = 凭空造需求）
7. ~~WHEN 结论为①THEN SHALL NOT 新建组件~~ —— 同上作废
7b. **（无条件必做）** WHEN 本 spec 收口 THEN Notes SHALL 留存两条源模板事实，
   即使「回函情况汇编」不实现也必须记录：
   - 结构结论：「回函情况汇编 = E0-1 的品种横向视图 + 替代程序区 + 11 条编制说明
     + 参考结论 A/B/C，33 列里 90% 来自 `VLOOKUP/SUMIFS 函证结果汇总表E0-1`」
     —— 将来若重新裁决，不必再精读一遍
   - `V9` 表头逐字「长期借款（含一年内到期的长期借款）函证情况」
     —— 它是 E0-4「所属科目」枚举只取两项（长/短期，一年内到期并入长期）的**唯一依据**，
     已被 `e0-send-list-dedicated-components` 的 manifest 枚举变更引用；
     **这条事实的载体表不实现，但事实本身必须留存**，否则那边的枚举失去依据
8. WHEN 渲染 E0-6 THEN 列集 SHALL 逐字为
   `索引号 / 报表截止日 / 开户行名称及收件人 / 产品名称 / 产品类型（封闭式/开放式） / 币种 /
   持有份额 / 产品净值 / 购买日 / 到期日 / 是否被用于担保或存在其他使用限制`
9. WHEN 渲染 E0-6 的 `是否被用于担保或存在其他使用限制` THEN SHALL 给**整个数据区**下拉「是/否」；
   源模板该列数据验证只覆盖 `K6:K10` 而数据区是 `R6:R20`（对比 E0-3 是 `O6:O26` 全覆盖）
   → 属源模板缺陷，SHALL 按意图全列启用并在 Notes 记录，SHALL NOT 照抄残缺范围
10. WHEN 渲染 E0-6 的 `产品类型（封闭式/开放式）` THEN SHALL 为点选（封闭式 / 开放式），
    依据源模板列名自带的枚举括注（交互点选优先铁律）
11. WHEN E0-6 专属组件落地 THEN SHALL 按 D0 函证家族分层：
    宿主 `GtConfirmationWealthList.vue` + 看板 + 网格 + 审计说明结论 + `*Types/*Enums` + 数据 composable；
    payload `_format` SHALL 为 `wealth-list-v1`；旧格式（无 `_format`）SHALL 降级只读
12. WHEN E0-6 看板渲染 THEN SHALL 呈现源模板可判定的审计指标：
    产品笔数 / 发函金额合计（Σ 产品净值） / 受限笔数与金额 / 已到期笔数 /
    封闭式·开放式分布 / **汇总键缺失笔数**（缺 索引号 或 产品名称）
13. WHEN 存在缺 `索引号` 或 `产品名称` 的行 THEN SHALL 红色告警说明
    「E0-1 发函金额无法自动汇总（源公式按 索引号 + 产品名称 匹配）」
14. WHEN 存在 `到期日` 不晚于 `报表截止日` 的行 THEN SHALL 告警提示核实期末是否仍应列示
15. WHEN E0-6 金额列渲染 THEN `产品净值` SHALL 用 `WpAmountInput`（千分符）；
    `持有份额` SHALL NOT 套用该组件（份额是数量不是金额，铁律禁套）
16. WHEN E0-6 网格渲染 THEN SHALL 有合计行（Σ 产品净值 / Σ 持有份额），
    SHALL NOT 把合计行混入可编辑数据行

### Requirement 9: E0-3 受限标记联动 E1

**User Story:** 作为审计助理，E0-3 里勾了「存在冻结、担保或其他使用限制」的账户，
应该能带到 E1 的受限货币资金明细，而不是两处各录一遍。

#### Acceptance Criteria

1. WHEN E0-3 存在 `是否存在冻结、担保或其他使用限制` 为「是」的行
   THEN SHALL 可一键带入 E1 ②表「受限制的货币资金明细」（金额取 `账户余额（原币）`，
   受限原因取该列填写的说明）
2. WHEN 带入 THEN SHALL **手工优先**（E1 侧已录同账号行不被覆盖），并给出确认预览
3. WHEN E1 侧已有该账号行且金额不同 THEN SHALL 弹确认（可选「仅补空值」）
4. WHEN E0-3 无受限行 THEN SHALL 静默无操作，SHALL NOT 产生空行
5. WHEN 联动落地 THEN SHALL NOT 反向写 E0-3（单向：E0-3 → E1）
6. WHEN 源模板「回函情况汇编」O 列公式为 `#REF!` THEN SHALL 在 Notes 记录该源模板缺陷，
   本 spec 的实现 SHALL 按其**意图**（按索引号汇总 E0-3 受限金额）而不是照抄坏公式
7. WHEN 枚举「受限」来源列 THEN SHALL 覆盖**两处**而非仅 E0-3：
   `E0-3 · 是否存在冻结、担保或其他使用限制（如是，请注明）` 与
   `E0-6 · 是否被用于担保或存在其他使用限制`（两列同性质，源模板 DV 均为「是/否」）
8. WHEN E0-6 存在受限行 THEN 其落点 SHALL 按该理财产品的核算科目二选一并写明判据：
   计入**其他货币资金** → E1 ②表受限货币资金；计入**交易性金融资产等** → 受限资产附注段
   （`restricted-assets-note-row-scope-rollout` 已建的行级合并通路）。
   四表数据推不出「哪只产品挂哪个科目」THEN SHALL 由用户点选归属，SHALL NOT 猜测

### Requirement 10: E0-8 舞弊迹象汇总去向 B50

**User Story:** 作为业务合伙人，函证程序识别出的舞弊迹象要能真的进 B50 风险评估，
而不是只在函证底稿里躺着。

#### Acceptance Criteria

1. WHEN 点击「跳转 B50 风险评估底稿」THEN SHALL 真的导航到该项目的 B50，
   SHALL NOT 只 `console.log`
2. WHEN B50 底稿不存在或无权限 THEN SHALL 给可见提示，SHALL NOT 静默失败
3. WHEN 存在已识别但无应对措施的迹象 THEN 跳转前 SHALL 提示补齐
4. WHEN 该能力落地 THEN SHALL 对全部 7 个函证循环一致生效（共享组件）

### Requirement 11: 公式预设与 functional_type 纠偏

**User Story:** 作为审计助理，E0 的公式预设应指向真实存在的 sheet，
发函记录表上应能看到「函证生成」动作按钮。

#### Acceptance Criteria

1. WHEN E0 预设块声明 `sheet` / `wp_name` THEN 该值 SHALL 逐字命中源 xlsx 的某个 tab 名
2. WHEN 预设条目引用科目 THEN SHALL 属于本循环报表行
   （`BS-002 = TB('1001')+TB('1002')+TB('1012')`）解析出的科目集合
3. WHEN 纠偏脚本以 `--check` 运行 THEN SHALL 输出 0 项欠账；重复运行 SHALL 幂等
4. WHEN 纠偏脚本改写 JSON THEN SHALL 做 round-trip 自检
   （`json.dumps` 不能逐字复现原文即退出非 0）
5. WHEN 核实 `ACTION_REGISTRY['confirmation']` 的动作对发函记录表适用
   THEN SHALL 把四张发函记录表的 `functional_type` 标为 `confirmation`
6. WHEN 核实结论是**不适用** THEN SHALL 保持 `NULL` 并在 Notes 写明理由
7. WHEN 修改 `workpaper_sheet_classification` THEN SHALL 通过幂等迁移或幂等脚本，
   SHALL NOT 手工改库；同循环其它 sheet 的 `functional_type` SHALL 逐字不变

### Requirement 12: 守卫与零回归

**User Story:** 作为平台维护者，我需要守卫把「源模板 ↔ meta ↔ override ↔ 列定义」四处锁死。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN SHALL 以 openpyxl 直读源 xlsx，交叉比对
   13 个要项列名 / E0-1 的 30 列 / 品种矩阵的 6 品种 6 指标 / E0-7 的五段场景关键词
2. WHEN 守卫比对 sheet 名 THEN SHALL 用真实 tab 名
   （`银行函证其他信息核对表E0-5` 无「询证」二字、`跟函函证过程控制E0-7` 有两个「函」）
3. WHEN 运行守卫 THEN SHALL 对 7 个函证循环交叉比对 meta 的非 null code 与 override 映射；
   meta 显式为 `null` 的 SHALL NOT 要求 override
4. WHEN 守卫读源码判定接线 THEN SHALL 先 `stripComments()` 并含反向自检
5. WHEN 本 spec 改动落地 THEN 函证相关既有测试 SHALL 全绿（预存在失败基线除外，须逐条列明）
6. WHEN 实测写库 THEN SHALL 先快照、后按 md5 逐字节复原
7. WHEN 本 spec 完成 THEN 会话产生的 `tmp_*` 诊断产物 SHALL 清理干净

## Glossary

- **override**：`backend/app/data/wp_code_overrides.json`，wp_code → componentType 精确映射
- **`skip`**：override 的一个合法取值（在 `VALID_COMPONENT_TYPES` 白名单内），
  表示该 sheet 不进 render-config 的 `sheets`。E0 的 10 张 hidden sheet 全部为 `skip`
- **裁决门 A**：「三张 hidden 底稿是否仍要实现」这一裁决项，
  **2026-08-02 用户裁决 = A-否**（不实现）。原标 `[Conditional-A]` / `[Cond-A]` 的条目
  已按此作废并标 `~~删除线~~ + 已作废`，正文保留为口径存档。
  与 `e0-send-list-dedicated-components` 的「待裁决 4」是同一裁决项（已同步关闭）
- **meta**：`cycleConfirmationMeta.ts`，各函证循环的 sheet 编码与跨表文案真源
- **一码两表**：同一 wp_code 对应源模板里两张不同 sheet（`E0-5` 即如此）
- **「三 + 一」命名**（2026-08-02 定论）：四张发函清单的 componentType **有意不统一** ——
  E0-3/E0-4/E0-5 走 `confirmation-send-list-e03/e04/e05`（归 `e0-send-list-dedicated-components`），
  E0-6 走 **`confirmation-wealth-list`**（本 spec Task 12.5 已落地，`_format = 'wealth-list-v1'`）。
  统一命名的三笔代价（改契约硬断言 / `_format` 二次迁移 / 删重写七件套）大于「命名整齐」的收益。
  **本条写进 Glossary 就是为了让下个会话不再提一次统一**
- **发函记录表**：E0-3~E0-6，按函证品种（货币资金 / 借款 / 应付银行承兑汇票 / 理财产品）
  记录发函对象与金额
- **13 个条款要项**：询证函标准格式里除余额外需银行确认的事项，源模板编号 3./4./5./6.(1)/6.(2)/
  8./9./10./11./12./13./14./15.，序号即询证函条款号
- **函证中心**：第三方电子函证平台；`银行函证其他信息核对表E0-5` 的相符性来自它的导出表
- **回函渠道**：邮寄 / 跟函 / 传真或电子邮件 / 电子询证函平台，各有不同的可靠性核对项
