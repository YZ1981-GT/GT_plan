# Requirements Document

## Introduction

`report_config` 是平台**报表行 → 科目码**的唯一真源：`resolve_report_line_account_codes`
与 `semantic_account_resolver`（层③）都读它，D~N 全部循环的四表取数、审定表预填、
溯源面板、附注 `REPORT()` 公式均沿它取数。**它错一行，对应循环的钱就错。**

本 spec 的触发点：2026-08-03 对 `report_config` 做**全表**「TB 引用码 ↔ `account_chart`
科目名」双向对账（132 条 `TB('code')` 引用 / 102 个报表行），结果远超此前逐个手工发现的
6 处 —— **权益段 BS-081~BS-090 是一整块错位**，另有资产/负债/减值段共 8 处，以及
7 个引用了全库零命中的码。

此前两次修复是被动的、且有一次前提错误：

| 迁移 | 覆盖 | 状态 |
|---|---|---|
| `V136__fix_report_config_bs082_bs117_special_reserve.sql` | BS-082 / BS-117 | 🔴 **失效** —— 它假设「BS-082 = 专项储备且 formula 含 `4103`」，实测 BS-082 的 row_name 是**其他权益工具**、formula 是 `TB('4003')` → `WHERE` 从不命中、0 行影响。真正写 `4103` 的是 **BS-086 专项储备**，V136 没碰 |
| `V137__fix_report_config_g_cycle_account_codes.sql` | BS-022 / BS-025 / BS-026 / IS-016 / IS-017 | ✅ 已生效（本 spec 不重复） |

**根因不是「有人写错了几个码」，而是这张表没有任何自动化一致性校验** ——
`row_name` 与 formula 引用科目的实际名称从不比对，错码可以静默存在数年。
所以本 spec 的交付物是「修正 + 守卫」两件，缺守卫等于等下一轮手工发现。

**范围外**：不改 `report_config` 的行集/行名/行序；不改 `project:` 级覆盖行
（客户自定义，需逐项目人工确认）；不动 `formula` 的运算结构（只改科目码字面量）。

---

## Glossary

| 术语 | 含义 |
|---|---|
| `report_config` | 平台报表行 → 科目码真源表；`row_code` + `applicable_standard` 定位一行，`formula` 声明取数公式 |
| 报表行 / row_code | `BS-*`（资产负债表）/ `IS-*`（利润表）/ `EQ-*`（权益变动表）/ `IMP-*`（减值准备表）/ `CFSS-*`（现金流量表补充资料）|
| `account_chart` | 项目科目表；`source='client'`（客户科目表，8 项目）/ `source='standard'`（标准科目表，10 项目）|
| 双向对账 | ① 码 → 名（该码实际叫什么科目）② 名 → 码（该科目名实际挂哪个码）。缺任一方向都会漏判 |
| 一码两义 | 同一科目码在不同 source 或不同编码体系下指代完全不同的科目 |
| 两套编码体系 | 旧《企业会计制度》(2001)：3xxx 权益 / 4xxx **成本** / 5xxx 损益；CAS 2006：4xxx 权益 / 6xxx 损益 |
| 派生行 | 语义上由重分类或合并抵销得出、不对应任何单一会计科目的报表行（如少数股东权益、一年内到期的非流动资产）|
| 零命中码 | 在全库 `account_chart` 任何 source 任何项目都不存在的科目码 |
| 宁缺勿造 | 取不到就返空并如实显示「本项目无此科目」，而不是取 0 或挂一个近似科目 |

---

## Requirements

### Requirement 1: 权益段 BS-081~BS-090 错码修正

**User Story:** 作为审计师，我需要资产负债表所有者权益各行取到正确科目，
以免「其他权益工具」显示成其他综合收益、「少数股东权益」显示成库存股。

#### Acceptance Criteria

1. WHEN 解析 `BS-082 其他权益工具` THEN 系统 SHALL 返回 `4401`（实证：client 5 项目 = 其他权益工具；现写 `4003` = **其他综合收益**）
2. WHEN 解析 `BS-084 减：库存股` THEN 系统 SHALL 返回 `4201`（实证：client 5 / standard 3 项目 = 库存股；现写 `4005` = **全库零命中**）
3. WHEN 解析 `BS-085 其他综合收益` THEN 系统 SHALL 返回 `4003`（实证：client 8 项目；现写 `4102` = **全库零命中**）
4. WHEN 解析 `BS-086 专项储备` THEN 系统 SHALL 返回 `4301`（实证：client 4 项目 = 专项储备；现写 `4103` = **本年利润**）
5. WHEN 解析 `EQ-015 （五）专项储备` THEN 系统 SHALL 返回 `4301`（现写 `4201` = **库存股**）
6. WHEN 解析 `BS-090 少数股东权益` THEN 系统 SHALL **不返回任何科目码**（`formula` 置 NULL）—— 少数股东权益是**合并抵销派生项**，CAS 2006 无对应单一会计科目；现写 `4201` = 库存股，既取错又与修正后的 BS-084 双算
7. WHEN 修正后重新解析 BS-081 / BS-083 / BS-087 / BS-088 THEN 系统 SHALL 返回与修正前**完全相同**的码（`4001`/`4002`/`4101`/`4104`，实证正确，不得被批量替换波及）
8. WHERE 存在 `project:` 前缀的覆盖行 THE 修正 SHALL 跳过它们并在报告中列出待人工确认的清单

### Requirement 2: 资产段与负债段错码修正

**User Story:** 作为审计师，我需要开发支出、衍生金融负债、其他流动负债等行取到正确科目。

#### Acceptance Criteria

1. WHEN 解析 `BS-033 开发支出` THEN 系统 SHALL 返回 `1704`（实证：client 4 / standard 3 项目 = 开发支出；现写 `1703` = **无形资产减值准备**，即把备抵当原值）
2. WHEN 解析 `BS-014 其他流动资产` THEN 系统 SHALL **不返回 `1901`**（实证 `1901` = 待处理财产损溢/损益，且 `tb_balance` 全库该科目余额恒 0）；具体处置见 Requirement 5
3. WHEN 解析 `BS-043 衍生金融负债` THEN 系统 SHALL **不返回 `2102`**（实证 `2102` = 短期应付债券，client 4 / standard 3 项目）；CAS 2006 下衍生工具在 `3201`，但该码在旧制项目是「利润分配」→ 一码两义，须按名定位或置 NULL
4. WHEN 解析 `BS-053 其他流动负债` THEN 系统 SHALL **不返回 `2901`**（实证 `2901` = 递延所得税负债，且已由 `BS-067 递延所得税负债` 认领 → 现状是**跨行双算**）
5. WHEN 解析 `IMP-008 七、债权投资减值准备` THEN 系统 SHALL 返回 `1505`（实证 standard 6 项目 = 债权投资减值准备；现写 `1502` = **持有至到期投资减值准备**，旧准则科目）
6. WHEN 解析 `IMP-017 十六、商誉减值准备` THEN 系统 SHALL **不返回 `1711`**（`1711` = 商誉**原值**，把原值当备抵；`1712` 商誉减值准备全库零命中 → 宁缺勿造置 NULL）
7. WHEN 修正任一行 THEN 该行 SHALL 有对应的 `account_chart` 实证记录（码 → 名 与 名 → 码 双向），且实证写入迁移文件注释

### Requirement 3: 零命中码的分档处置

**User Story:** 作为平台维护者，我需要区分「码写错了」与「这批项目确实没有该科目」，
避免把业务事实当缺陷改坏。

#### Acceptance Criteria

1. WHEN 某码在全库 `account_chart` 零命中 AND 该科目名在库中挂在另一个码上 THEN 系统 SHALL 判为**错码**并修正（`BS-084 4005→4201` / `BS-085 4102→4003`）
2. WHEN 某码在全库 `account_chart` 零命中 AND 该科目名在库中亦零命中 THEN 系统 SHALL 判为**业务事实**、保留现状并在守卫白名单登记理由（候选：`BS-004 衍生金融资产 1102` / `BS-007 应收款项融资 1124` / `BS-037 其他非流动资产 1911` / `BS-066 递延收益 2811` / `BS-068 其他非流动负债 2911`）
3. WHEN 登记白名单条目 THEN 每条 SHALL 写明「该科目名在全库零命中」的实证查询与日期
4. WHEN 白名单某条目对应的科目名后来在库中出现 THEN 守卫 SHALL 打红（迫使复核）

### Requirement 4: 派生行不得挂单一科目码

**User Story:** 作为审计师，我需要「一年内到期的非流动资产」这类**重分类派生行**
不要伪装成能从单一科目取数，否则审定表会显示一个来源错误的数。

#### Acceptance Criteria

1. WHEN 报表行语义是重分类/合并派生 THEN 系统 SHALL 置 `formula = NULL` 而非挂一个近似科目
2. WHEN 解析 `BS-013 一年内到期的非流动资产` THEN 系统 SHALL 不返回 `1503`（实证 `1503` = **可供出售金融资产**，旧准则科目；该行实为各非流动资产的一年内到期部分重分类）
3. WHEN 解析 `CFSS-016 存货的减少` THEN 系统 SHALL 不返回单一 `1401`（实证 `1401` = **材料采购**，存货是区间 `1401~1499`；该行是**变动额**不是余额）
4. WHEN 某行被置 NULL THEN 依赖它的循环 SHALL 回退到自己 spec 的兜底码或显示「本项目无此科目」，而**不是**取 0

### Requirement 5: BS-014 其他流动资产的口径裁决

**User Story:** 作为审计师，我需要 K2 其他流动资产审定表的取数口径有明确依据。

#### Acceptance Criteria

1. WHEN 评估 `BS-014` THEN 系统 SHALL 记录三项实证：`1901` 的真实科目名（待处理财产损溢/损益）、`tb_balance` 中该科目余额（全库恒 0）、以及 `listed_standalone` 变体额外加的 `TB('1131')`（应收股利，已由 `BS-009 其他应收款` 认领 → 潜在双算）
2. IF 存在能覆盖「其他流动资产」语义的标准科目 THEN 系统 SHALL 改为该码
3. IF 不存在 THEN 系统 SHALL 置 NULL 并让 K2 走 `k2_account_scope` 的兜底 + 溯源面板显示「本项目无此科目」
4. WHEN 处置 BS-014 THEN 变更 SHALL 附带 K2 的回归证据（22 个文件引用该行号，含 `k2AccountScope.ts` / `k2NoteSectionMap.ts` / `wp_surfaced_k.py`）
5. 🔴 本项须**用户裁决**后再改 —— 它直接改变 K2 审定表未审数的取数结果

### Requirement 6: 平台级一致性守卫（本 spec 的核心交付）

**User Story:** 作为平台维护者，我需要 `report_config` 的错码在 CI 就被拦住，
而不是等某个循环的 spec 偶然发现。

#### Acceptance Criteria

1. WHEN CI 运行 THEN 守卫 SHALL 抽取 `report_config.formula` 中全部 `TB*('code')` 引用并与 `account_chart` 的科目名做双向对账
2. WHEN 某行的 `row_name` 与其引用科目的实际名称语义不符 AND 该行不在白名单 THEN 守卫 SHALL 打红并给出「现码实际是什么科目 / 该名实际挂哪个码」
3. WHEN 新增或修改 `report_config` 行引入不一致 THEN 守卫 SHALL 打红（防再次静默劣化）
4. WHERE 白名单条目 THE 守卫 SHALL 要求每条写明理由（空理由视为未登记，同 `disclosureColumnsCoverage` 的 `reason` 必填范式）
5. WHEN 守卫运行 THEN 它 SHALL 包含反向自检：注入一条已知错码（如 `BS-090 = TB('4201')`）必须被判红
6. WHERE 需要连库 THE 守卫 SHALL 在无 DB 时 `pytest.skip` **并打印 skip 原因**（静默 skip 是假绿源），且 CI 上挂在有 DB 的 job
7. WHEN 名称比对 THEN 它 SHALL 处理已知的合法差异（`未分配利润`↔`利润分配`、`预收款项`↔`预收账款`、`预付款项`↔`预付账款`、`公允价值变动收益`↔`公允价值变动损益`、`资产处置收益`↔`资产处置损益`），且这些别名对 SHALL 集中声明在单一真源

### Requirement 7: V136 失效迁移的处置

**User Story:** 作为平台维护者，我需要失效的修复迁移被显式记录，
否则下个会话会以为「BS-082 已经修过了」。

#### Acceptance Criteria

1. WHEN 处置 V136 THEN 系统 SHALL **不修改也不删除**该已应用迁移文件（改已应用迁移会触发 checksum 漂移）
2. WHEN 新建修复迁移 THEN 其注释 SHALL 说明「V136 的 WHERE 从不命中、前提错误（BS-082 不是专项储备）、真正写 `4103` 的是 BS-086」
3. WHEN 新建迁移 THEN 它 SHALL 对 BS-082 与 BS-086 都给出正确 UPDATE
4. WHEN 检查 `BS-117 专项储备` THEN 系统 SHALL 确认其 formula 为 NULL（无需修正）并记录该事实

### Requirement 8: 下游影响面与回归

**User Story:** 作为开发者，我需要知道改这张表会波及哪些循环，避免静默改变已验收的取数结果。

#### Acceptance Criteria

1. WHEN 修正任一行 THEN 系统 SHALL 列出引用该 `row_code` 的全部后端策略与前端 scope 文件
2. WHEN 修正完成 THEN 系统 SHALL 对受影响循环跑真实 DB 直跑（非替身）并比对修正前/后金额
3. WHERE 某循环的 spec 已声明兜底码 THE 修正 SHALL 确认兜底码与新解析结果**一致**（不一致说明两处真源打架，须一并收敛）
4. WHEN `BS-053` 的双算被解除 THEN K3 其他应付款与 N3 递延所得税负债的取数 SHALL 各自正确且不再重叠
5. WHEN 权益段修正 THEN M 循环 `m_cycle_specs.py` 的兜底码 SHALL 与新解析结果对齐（现已实证一致：M9 `4003` / M10 `4401` / M3 `4201` / M7 `4301`）
6. WHEN 全部修正完成 THEN 后端 `backend/tests/four_table/` SHALL 全绿，且新增/变更的失败数为 0
