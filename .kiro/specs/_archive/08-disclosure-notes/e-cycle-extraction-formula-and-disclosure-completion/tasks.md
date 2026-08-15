# Implementation Plan: E 类取数、公式预设与披露附注收口

## Overview

E 循环（E0 函证 / E1 货币资金）四条互不重叠的改动轴：账户级取数（A）、公式预设（B）、附注结构（C）、披露逻辑与动态行（D）。

**不重建任何已通的链路** —— 归档 spec `e1-four-table-extraction-and-disclosure-alignment`（20/20）建的科目定位链路实测正确（真实库 8/8 `parent_check` 勾稽成立、既有 132 守卫全绿、三个幂等脚本 `--check` 0 欠账），本 spec 只补缺口与纠错。

11 需求 / 81 AC / 41 Property / 24 任务 / 6 波。**无 DB 迁移。**

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（必须先打红）", "tasks": ["1", "2", "3"], "parallel": true },
    { "wave": 2, "name": "账户级取数后端", "tasks": ["4", "5", "6"], "depends_on": [1] },
    { "wave": 3, "name": "账户级取数前端与宿主", "tasks": ["7", "8", "9"], "depends_on": [2] },
    { "wave": 4, "name": "公式预设与附注结构", "tasks": ["10", "11", "12", "13"], "depends_on": [1] },
    { "wave": 5, "name": "披露逻辑与动态行", "tasks": ["14", "15", "16", "17", "23", "24"], "depends_on": [4] },
    { "wave": 6, "name": "守卫、CI、变异与验收", "tasks": ["18", "19", "20", "21", "22"], "depends_on": [2, 3, 4, 5] }
  ],
  "notes": [
    "Task 1/2/3 三个守卫互不依赖可并行，但都必须在对应 Wave 之前完成并对当前状态打红。",
    "Task 4（e1_bank_accounts.py）是 Task 5/7 的共同前置。",
    "Wave 4（预设 + 附注）与 Wave 2/3（取数）无文件重叠，可与之并行。",
    "🔴 Task 14（受限 L2 链路）**不依赖** Task 7 —— tb_aux_balance 没有受限金额字段，L2 读的是审计师在 E1-3 手填的 restrictedAmount/restrictedReason（AJ/AK 列，已在 USER_FIELDS 里）。R1 只是让 E1-3 有账户行可填（UX 前提）。Wave 5 因此只依赖 Task 4 的槽定义，不被 Wave 2/3 阻塞。",
    "Task 23（受限桶展示序分离）与 Task 13（新增桶）碰同一文件，须串行：先 13 后 23，或合并落地。",
    "Task 24（披露主表槽预填）依赖 Task 5（render 扩槽）。",
    "Task 20 变异检验必须在 Task 18/19 全绿之后；Task 22 浏览器实测是最后一步。",
    "改 note_template_*.json 后必须重跑 gen_note_shared_table_segments.py --write（Task 13）。"
  ]
}
```

## Tasks

- [x] 1. 账户级取数判据守卫（先打红）
  - 新建 `backend/tests/four_table/test_e1_bank_accounts_live.py`（连库）：断言至少 1 个项目能从 `tb_aux_balance` 的 `aux_type='银行账户'` 取到账户级明细，且各槽账户合计与 `tb_balance` 叶子合计之差 ≤ 0.005
  - **必须先红**：当前 `e1_bank_accounts.py` 不存在 → import 失败即红（这就是「先打红」）
  - 连库范式（Property 31）：一次 `asyncio.run` + `create_async_engine(url, poolclass=NullPool)` 专用引擎 + 同 loop 内 `dispose()`，**禁借 `app.core.database.async_session` 共享池**；验收用「victim 单独 / 本文件在前 / victim 在前」三序跑，victim 结果必须逐条相同
  - 反向自检：同一查询去掉 `get_active_filter`（改裸 `is_deleted == False`）时勾稽**必须不成立**，据此证明 dataset 过滤是必要的而非装饰
  - 冻结实证基线常量 `ACCOUNT_COUNT_BASELINE`：`a7fc75e5`=38 / `0ec33ac9`=22 / `52c04ed1`=21 / `f064f5e4`=23 / `2aa00f57`=17 / `b39809ed`=6 / `4f6dbc36`=2 / `c8621493`=1（1002 科目，只许因数据变更而变，配「数值来自实测复算而非预期」注释）
  - 无 aux 数据的项目如实 skip 并打印原因，**禁用 fixture 冒充**
  - _Requirements: 1.1, 1.5, 10.1, 10.2_

- [x] 2. 公式预设覆盖面守卫（先打红）
  - 新建 `backend/tests/four_table/test_e1_preset_coverage.py`
  - Property 11：E 类每个预设块的 `sheet` 值必须存在于对应源 xlsx 的 `wb.sheetnames`（openpyxl 直读 `backend/wp_templates/E/*.xlsx`）→ **当前必红**（`审定表E0-1` 不存在，真实为 `函证结果汇总表E0-1`）
  - Property 12 + Property 40：E 类 visible sheet 分三段（有预设 / 登记无预设 / 非数据表白名单）互不相交且并集完备 → **当前必红**
  - 🔴 **实测基线（openpyxl 直读 5 个 E 类 workbook，数值来自复算不是预期）**：visible **45 次出现 / 去重名 41** 张（`底稿目录` 在 5 个 workbook 各一张 ⇒ 去重后 1 个名）· 现有预设块 **17** 个，其中 `审定表E0-1` 是错名不对应任何真实 sheet ⇒ 真实命中 **16** · 非数据表白名单**去重名 4**（`底稿目录` + `货币资金实质性程序表E1A` + `货币资金实质性程序表E26A` + `函证程序表E0A`，出现次数 8）· 缺口 = `41 − 4 − 16 = 21` 张
  - 🔴 **21 张缺口的处置分四路**（守卫要按这四路分别断言，别只断总数）：`函证结果汇总表E0-1` 由 Task 10 改名后自动覆盖（1 张）· Task 10 补 5 张（E1-6/E1-10/E1-21/E1-22/E1-23）· Task 10 补 1 张（`(仅人民币)E1-3`）· 登记 14 张（E1-5/7/8/9/11/18/19 + E0-2~E0-8）
  - 🔴 **计数一律用「去重名」口径** —— `底稿目录` 出现 5 次但只是 1 个名，按「出现次数」算会让白名单命中数与集合大小对不上（自检必假红）。白名单配「去重名命中数 == 4 且出现次数 == 8」双断言（防它退化成逃逸阀）
  - 🔴 判据只覆盖 **visible**；sheet 名比对一律用**全名**（hidden 的 `银行函证其他信息核对表E0-5` 与 visible 的 `应付银行承兑汇票发函记录表E0-5` 同尾码，按尾码匹配会撞）
  - Property 13：明细表块不得出现引用同 wp_code 审定表的 `WP()`（防成环）
  - Property 14：扫 `backend/scripts/fix/fix_e1_*.py` 与 `fix_note_e1_*.py` 源码，**能到达控制台**的字符串字面量必须 `s.encode('gbk')` 不抛 → **当前必红**（`fix_e1_orphan_sheet_presets.py` 有 `✅`/`❌` 共 7 处）
    - 🔴 **判据是 GBK 可编码性，不是「U+2000 以上非 CJK」** —— 本轮实测 GBK **可**编码 `→`(U+2192) / `≥`(U+2265) / `—`(U+2014) / `─`(U+2500) / `【`(U+3010) / `·`(U+00B7)，**不可**编码 `✅` / `❌` / `⚠` / `✔` / `✓` / `🔴` / `░`。按过宽口径写会误伤 `fix_e1_prefill_presets.py` 与 `fix_note_e1_monetary_fund_structure.py` 里大量含 `→` 的**安全**说明串，制造无谓 churn
    - 扫描面含**间接到达控制台**的收集器（`changes.append(f"…")` 被后续 `print` 输出 —— `fix_e1_prefill_presets.py` 正走这条路径）；docstring 与注释**不进**扫描面（不输出到控制台）
    - 配「中文汉字 + GBK 可编码符号不打红」正向断言（防判据收紧后退化成噪声）
  - 登记表条目数上限断言（只许减不许增）+ 每条理由 ≥15 字
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 3.8, 3.9, 3.10, 4.1, 4.3, 4.4, 4.5_

- [x] 3. 附注结构与段 row_code 守卫（先打红）
  - 扩展 `backend/tests/four_table/test_note_e1_structure.py`
  - Property 16：python-docx 直读 `docs/模版/` 两份 docx，soe 货币资金表行标签序列 == 模板 JSON == 同步载荷（去空白归一）→ **当前必红**（首行 `现金` vs docx `库存现金`；JSON 5 行 vs docx 6 行）
  - Property 20：受限表行序 == `docx 六类（按 docx 序）+ 平台补充桶 + 合计` → **当前必红**（缺「金融企业法定存款准备金或备付金」）。🔴 **不得写成「== docx r1~r6」** —— 平台兜底桶 `other` 在 docx/模板都无行但推送时会出现，那样写会把正确实现打红
  - Property 37：listed docx「货币资金」标题下表格数 **== 1**（受限内容是文字段落）⇒ listed 受限表是平台补充表，**不得**对 listed 侧写「与 listed docx 三向一致」的断言
  - Property 41：soe docx 主表 6 行**不含**「存放财务公司款项」「存款应计利息」（listed 有）⇒ 断言该差异存在且不得对齐两版
  - Property 23：两版外币表每个段首行 `report_row_code` 在 `report_config` 的 `row_name` 与段 `label` 归一后相等 → **当前必红**（`BS-031` 是使用权资产、段 label 是短期借款）
  - Property 24 反向锁死：`report_config` 的 `BS-031` 四准则 `row_name` 均为 `使用权资产`，且 `h8_account_scope.py` / `dual_family_codes.py` 仍引用 `BS-031`（防日后把 H8 改成 BS-041）
  - Property 19：listed 五、1 主表 8 行、两版外币表段数（3/5）与行数（16/25）冻结快照
  - Property 30：`row_type` 取值集合仍为 5 值（不引入 `expandable`）
  - Property 23 附加断言：段首行 `account_codes`（短期借款 = `['2001']`）逐字不变
  - 🔴 docx 定位必须按 `paragraph.style.name == 'Heading N'`（Word 自动编号，段落文本不含「五、」）；**listed 是 Heading 2、soe 是 Heading 3**（两版层级不同）。抽表格要沿 `document.element.body` 的**段落/表格顺序流**走（`Paragraph`/`Table` 混排），只遍历 `doc.tables` 拿不到「哪张表属哪个章节」
  - 本守卫同时兑现「附注结构改动必须由幂等脚本落地 + 守卫直读源 docx 三向比对」这条判据（不接受手改 JSON）
  - _Requirements: 5.1, 5.2, 5.6, 5.7, 6.1, 6.6, 6.8, 7.1, 7.2, 7.5, 7.6, 9.5, 10.3, 11.4_

- [x] 4. 账户级取数共享件 `e1_bank_accounts.py`
  - 新建 `backend/app/services/four_table/e1_bank_accounts.py`
  - `AuxDimensions` dataclass + `parse_aux_dimensions(raw, aux_name) -> AuxDimensions`：解析 `金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296`，三级降级（1=账号+银行名 / 2=仅账号 / 3=靠 `aux_name` 兜底），**任何一级都不臆造银行名**
  - `BankAccountRow` dataclass（`account_code`/`account_no`/`bank_name`/`currency`/`opening`/`debit`/`credit`/`closing`/`slot`/`source`/`parsed_level`）
  - `fetch_e1_bank_accounts(db, project_id, year, *, account_prefixes)` **async**：
    - 🔴 **`await get_active_filter(db, TbAuxBalance.__table__, project_id, year)`** —— 它是 `async def`（模块 `app.services.dataset_query`，签名 `(db, table, project_id, year, *, force_dataset_id=None, current_user_id=None)`）。**漏 `await` → `sa.and_(coroutine, ...)` 抛异常 → 被本函数的 fail-open 吞成 warning → 清单恒空且与「本项目无 aux 数据」不可区分**（N5 与 D 循环各因此出过一次 P0）。禁裸写 `is_deleted == False`
    - `aux_type == '银行账户'` + `account_code` 前缀过滤
    - 按解析出的 `(account_code, account_no)` 聚合求和，金额 `COALESCE(...,0)`
    - fail-open：异常返 `[]` + warning + `rollback()`
  - `assign_accounts_to_slots(rows, accounts)`：按槽原始码前缀归属，都不中的进 `unassigned`（**禁兜底**）
  - `check_accounts_vs_leaves(slot_accounts, slot_leaves)`：三口径 `{account_sum, leaf_sum, diff}`，**不修正数据**
  - `build_e1_account_prefill(slot_accounts, slot_leaves)`：产出 `{accounts:{bank,other,finance_co,unassigned}, reconcile, meta:{source,account_count,parsed_level_dist}}`
  - 新建 `backend/tests/four_table/test_e1_bank_accounts.py`：Property 1（active 过滤）/ Property 2（同账号聚合）/ Property 3（三级降级不臆造）/ Property 4（归属三态不兜底）/ Property 5（勾稽如实不修正）+ Property 39（源码级断言每处 `get_active_filter(` 前紧邻 `await`，配「去掉 await 必红」反向自检）+ PBT「各槽合计之和 == 全部账户合计」；含「同账号两行必聚合」用 `a7fc75e5` 的 ±25,954,468.80 造样本
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 10.8, 10.9_

- [x] 5. render 接账户级取数 + 扩明细槽
  - `_e1_monetary_fund.py` 三处加法式改动：
    - `_DETAIL_SLOT_KEYS` 扩至 5 槽（`+ E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL`）
    - `_build_four_table_extraction()` 末尾调 Task 4 的共享件，产出 `account_prefill`
    - `render()` 返回 dict 新增 `"account_prefill"` 键
  - **零回归支点**：`build_e1_detail_rows` 的字段与顺序不变；扩槽只让返回 dict 多两个键
  - Property 9 characterization：同一输入下 `cash`/`bank`/`other` 三键值与字段顺序逐字节相同
  - Property 10：`found=False` 的槽明细返 `[]` 而非零值占位行
  - aux 查询失败或无数据时 `account_prefill.accounts` 各键为 `[]`（前端据此退回叶子口径）
  - _Requirements: 1.6, 1.7, 2.1, 2.2, 2.5, 11.6_

- [x] 6. 账户级取数真实库验收脚本
  - 新建 `backend/scripts/diagnose/verify_e1_account_extraction_live.py`（只读，默认 dry-run，`--all-projects`）
  - 逐项目输出：账户数 / `parsed_level` 分布 / 各槽勾稽 diff / `unassigned` 明细 / 与 `ACCOUNT_COUNT_BASELINE` 对照
  - 判据：有 aux 数据的项目 `|diff| ≤ 0.005`；`unassigned` 非空时打印全部明细
  - 态名全集从枚举派生 + 启动即断言「实际态名 ⊆ 派生集合」，不匹配 `[FATAL]` 退出（防脚本级假阴性）
  - 无法验证时输出 `UNVERIFIABLE` 并写明原因，**禁 fixture 冒充**
  - 控制台输出仅 ASCII 符号（中文汉字可）；诊断产物写盘用 `Path(__file__).resolve().parent` 绝对路径
  - _Requirements: 10.1, 10.7_

- [x] 7. 前端账户级归一层 `e1BankAccountPrefill.ts`
  - 新建 `audit-platform/frontend/src/components/workpaper/composables/e1BankAccountPrefill.ts`
  - `E1AccountRow` / `E1AccountPrefill` 接口 + `normalizeAccountPrefill(raw)`（缺字段按空处理，不抛）
  - `buildBankSeedRowsFromAccounts(p)`：产出 E1-3 种子行，字段对齐 `useE1BankDetail` 的 USER_FIELDS 序列化契约；`bankName` → `bankName` 列、`accountNo` → `accountNo` 列、`currency` → `fxCurrency`
    - 🔴 行 id 前缀必须是 `bank-principal-{group}-acct-{账号}`，与既有叶子口径的 `-ft-{科目码}` **不撞键**（Property 7）
    - `finance_co` 槽的账户归入 `group: 'finance'`（R2.3，不要求审计师手工重分类）
    - 账户为空时返 `null`（由宿主退回叶子口径）
  - `buildAccountListSeedRowsFromAccounts(p)`：产出 E1-10 种子行，**保留零余额账户**（Property 6）
  - `buildDigitalSeedRows(prefill)`：从 `four_table_prefill.digital` 产出 E1-4 种子行
  - 🔴 **按 E1-3 variant 分流**（平台已有机制：宿主按 `sheetName` 含「仅人民币」→ `rmb`、含「人民币及外币」→ `multi`；`useE1BankDetail` 的 `USER_FIELDS` 已含 `fxCurrency`/`fxRate`/`openingFc`/`increaseFc`/`decreaseFc`/`adjustmentFc`，两版共用同一持久化键）：`buildBankSeedRowsFromAccounts(p, variant)` 在 `rmb` 版不下发 `fxCurrency`、`multi` 版下发；**两版账户条数必须相同**
  - 🔴 **原币金额与汇率一律留空** —— `tb_aux_balance` 只有 `opening_fc` 一列且 `aux_type='银行账户'` 下**全库为 NULL**，**无 `closing_fc`、无汇率列**，308 行 `currency_code` 全 `CNY` ⇒ `fxRate`/`openingFc`/`increaseFc`/`decreaseFc`/`adjustmentFc` **不得由本位币金额反推**（Property 34）
  - 「存在非本位币账户 → `rmb` 版提示」分支当前全库 0 命中 = 潜伏态（同 `digital`/`finance_co` 恒空同性质）⇒ 用替身构造 `currency_code='USD'` 验证分支可达，并断言恒空时形态合法
  - 新建 `composables/__tests__/e1BankAccountPrefill.spec.ts`：归一 / 三种 seed / 行 id 不撞键 / E1-10 保留零余额 / 空输入返 null / `finance_co` 归 finance 组 / **两 variant 账户条数相同、字段集不同、原币列都不带值**
  - _Requirements: 1.7, 1.9, 1.10, 2.3, 2.4, 11.3_

- [x] 8. 宿主种子化接账户级优先
  - `GtE1MonetaryFund.vue`：
    - 新增 `const accountPrefill = computed(() => normalizeAccountPrefill(props.htmlData?.account_prefill))`
    - `seedFromFourTable()`：`bankSeed = buildBankSeedRowsFromAccounts(accountPrefill.value) ?? buildBankSeedRows(p)`；`acctSeed` 同款；新增 `seedRowsKey('E1-digital-detail-rows', buildDigitalSeedRows(p))`
    - 🔴 `ftRowsKey` / **`reExtractFromFourTable()`**（**真实函数名** —— 宿主里 `refetchFromFourTable` 命中数为 0，按后者写守卫会静默空转）的 sheet 分支加 `E1-4`，`E1-3`/`E1-10` 改走账户级优先。`ftRowsKey` 现只映射 `E1-2`/`E1-3`/`E1-10` 三张
  - Property 8 零回归：`account_prefill.accounts` 全空时种子化产出与改造前**逐字节相同**
  - 新建 `composables/__tests__/e1HostSeedWiring.spec.ts`：读宿主源码断言三段链（render 键 → 宿主消费 → 写入的 `allResponses` 键），并断言子 Tab 侧读该键
    - 🔴 判据必须是「函数体内」而非「文件内出现」—— 用花括号配对截 `seedFromFourTable` 与 `reExtractFromFourTable` 函数体
    - 🔴 断言函数名存在性本身（`reExtractFromFourTable` 命中数 == 1 且 `refetchFromFourTable` == 0），防下次又按错名写
    - 替身反向自检：把账户级优先链删掉时必红
  - _Requirements: 1.6, 2.4, 11.3_

- [x] 9. 取数溯源面板扩展
  - `e1/E1FourTableSourcePanel.vue` 新增两块：
    - 账户级取数溯源：账户数 / `parsed_level` 分布 / 各槽勾稽 diff（diff ≠ 0 时 `danger` tag）
    - `unassigned` 告警：列出未归属账户的账号与金额，提示「aux 里有账户但科目定位未覆盖」
  - `parsed_level` 分布作为数据质量指标：level 3 占比高时提示「该客户 `aux_dimensions_raw` 格式与预期不同，请核对账号列」
  - 传 prop 前先核对 `defineProps` 键集（memory 铁律：传不存在的 prop 静默失效，四层验证全查不出）
  - _Requirements: 1.8, 10.7_

- [x] 10. 公式预设幂等脚本（E0 纠正 + 5 块新增 + 登记表）
  - 扩展 `backend/scripts/fix/fix_e1_prefill_presets.py`：
    - E0 块 `sheet` `审定表E0-1` → `函证结果汇总表E0-1`、`wp_name` `银行询证函` → `函证结果汇总表`
    - 新增 E1-6 预设块（银行存款余额调节表：账面余额取账户级/`TB('1002','期末余额')`）
    - 新增 E1-10 预设块（已开立银行账户清单：账户数与合计取账户级，`PLACEHOLDER` 说明账户明细来自 `tb_aux_balance:银行账户`）
    - 新增 E1-21 / E1-22 预设块（截止测试：银行存款 / 其他货币资金期末余额作截止金额参照基数）
    - 新增 E1-23 预设块（收支检查：`TB('1002','本期借方')` / `TB('1002','本期贷方')` 作大额收支占比基数）
    - 🔴 新增 **`银行存款及其他货币资金明细表(仅人民币)E1-3`** 预设块 —— 现只有 `(人民币及外币)E1-3` 有（4 cells），两张是同 wp_code 的两个 variant 且都是真实数据录入表，缺它时用户选「仅人民币」版公式管理页全空（R3.7）
    - 新增 `E1_SHEETS_WITHOUT_PRESET` 登记表（**E1 7 张 + E0 7 张 = 14 条**，每条理由 ≥15 字）
    - 新增非数据表白名单（`底稿目录` ×5 + `E1A` + `E26A` + `E0A` = **8 条**）+ 「命中数 == 8」存在性自检
  - `--check` 归零 + 二次 `--apply` md5 不变（Property 15）
  - round-trip 自检：`json.dumps` 不能逐字复现原文即 exit 2（防全文件重排与并发冲突）
  - 校验器只扫**语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`），不对整块 `json.dumps` 做「不得出现 xxx」断言（description 会如实写出被纠正的反例）
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8_

- [x] 11. 幂等脚本输出改 GBK 可编码
  - `fix_e1_orphan_sheet_presets.py` 实测 **7 处**不可编码字符：`❌`×2（validate 报错头 / `--check` 欠账头）+ `✅`×5（`--check` 0 欠账 / `--dry-run` 无需变更 / `--apply` 无需变更 / `--apply` 已写入 / 另一处）→ 一律改 `[OK]` / `[ERR]`
  - 🔴 **另两个脚本不要动** —— 实测 `fix_e1_prefill_presets.py` 与 `fix_note_e1_monetary_fund_structure.py` 的非 ASCII 全是 `→`(U+2192)，GBK **可**编码、不会崩；它们已 `--check` rc=0。按「非 ASCII 一律换掉」会白改一堆说明串
  - 验证：GBK 控制台下三个脚本 `--check` 全部 rc == 0（0 欠账时）
  - 🔴 本任务的判据**就是**退出码（与「判成败查数据不看退出码」的一般铁律相反）—— 需 `subprocess` 在**默认（GBK）编码**下捕获 rc；用 `PYTHONIOENCODING=utf-8` 跑会掩盖问题
  - _Requirements: 4.1, 4.2_

- [x] 12. 附注结构幂等脚本（四处 additive 修正）
  - 扩展 `backend/scripts/fix/fix_note_e1_monetary_fund_structure.py`：
    - soe 八、1 主表首行 label `现金` → `库存现金`（走 rule aliases 改名，**不进 drops**）
    - soe 八、1 主表合计行后补 `其中：存放在境外的款项总额`（`row_type: data`，无 `is_total`）
    - 两版受限表合计行前补 `金融企业法定存款准备金或备付金`
    - soe 八、92 短期借款段首行 `report_row_code` `BS-031` → `BS-041`
  - 🔴 改 row_code 时该段首行的 `account_codes: ['2001']` **逐字不变**（本来就是对的，只有 row_code 错）
  - 🔴 **受限表只需在合计行前插一行，不需重排** —— docx r1~r5 的顺序（银行承兑→信用证→履约→担保定期→境外）与模板现状**逐字一致**
  - 受限表 guidance 补两句：① 合计行为平台按校验预设 F1-4 要求保留（源 docx 无该行）② **listed 侧整张受限表是平台补充表**（listed docx 该处只有 1 张主表 + 两段文字），补第 6 类的依据是镜像 soe 而非 listed docx（R6.6）
  - 复用共享 `backend/scripts/fix/_note_structure_kit.py` 的 `rule` / `apply_plan` / `run_section` / `build_cli`
  - 🔴 `rule(name, cols, rows, guidance, aliases=None, *, insert=False, ...)` 的 **`guidance` 是必填位置参数** ⇒ 只改行集时必须把既有 guidance **原样传回**，别顺手改写（改写会让 Property 16 的三向比对与既有 guidance 断言同时漂移）
  - `--check` 归零 + 幂等（Property 15）；本任务是「附注结构只经幂等脚本落地」判据的落点
  - _Requirements: 3.6, 5.1, 5.2, 6.1, 6.4, 6.6, 7.1, 7.2, 10.3_

- [x] 13. 受限桶新增 + 派生段清单重生成
  - `backend/app/services/four_table/e1_restricted_buckets.py` 新增第 6 桶 `statutory_reserve`（label `金融企业法定存款准备金或备付金`，keywords `法定存款准备金`/`备付金`/`存款准备金`，`source_ref` 指 docx）
  - 🔴 声明位置：`pledged_deposit` 之后、`other` 之前（`other` 兜底桶必须始终最后）
  - 扩展 `backend/tests/four_table/test_e1_restricted_buckets.py`：Property 21「用 6 个真实项目的全部货币资金叶子科目名跑 `classify_e1_restricted_leaf`，新增桶前后分类结果逐条相同」+ 打乱顺序反向自检 + Property 22（前端源码不得出现桶中文标签字面量，标签只从 `bucketDefs` 取）
  - 重跑 `backend/scripts/gen/gen_note_shared_table_segments.py --write`，核对外币表段 `row_code` 序列与模板一致、`find_segment(rows,'BS-041')` 在 soe 侧返非 None（Property 25）
  - `e1FxNoteSectionMap.ts` 的段归属注释表 `BS-031` → `BS-041`；扩展 `e1FxNoteSectionMap.spec.ts` 与模板交叉锁死
  - Property 33 回归断言：`aggregateE1FxByCurrency` 保持「不写死币种表」—— 输出币种集合 == 底稿实际出现的非本位币集合（保持首次出现顺序），源码无写死币种清单常量；用「加一个模板里没有的币种（英镑）必须出现在载荷里」做正向证明
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 7.3, 7.4, 9.3, 11.5_

- [x] 14. 受限资金第二链路（E1-3 逐户归集，源模板口径）
  - `e1RestrictedScope.ts` 新增 `resolveRestrictedFromAccounts(opts)`：按 E1-3 逐户的「受限金额（AJ 列 `restrictedAmount`）+ 受限原因（AK 列 `restrictedReason`）+ 账户性质/主要用途（D 列 `accountType`）」归集成 ②表行
  - 🔴 **数据源是审计师在 E1-3 手填的持久化行（`E1-bank-detail-rows`），不是账户级取数** —— `tb_aux_balance` 没有受限金额字段，故本任务**不依赖 Task 7**（R8.8）
  - 源模板依据：soe 受限表原始公式是 `SUMIF(E1-3!$D$23:$D$28, A17, E1-3!$AB$23:$AB$28) + SUMIF(E1-3!$D$38:$D$40, ...)` —— 按 D 列受限类别匹配、取 AB 列期末审定人民币
  - **两条链路并存不互相覆盖**（Property 26）：L1 = 四表叶子按科目名分类（现状）/ L2 = 本任务的逐户归集；代码中不得出现「取其一覆盖另一」的分支
  - 🔴 **归集出的「受限原因」不得进 ②表列**（Property 38）—— 既有契约钉死②表只 3 列 `['label','end_amount','prior_amount']`（源模板即 3 列），原因文本去重后并入 `_note_texts` 文字说明段；加第 4 列会打红既有断言
  - `e1DisclosureConsistency.ts` 新增勾稽项「L1 合计 vs L2 合计」，不等时 `warning` 级（审计判断，非 error）
  - 扩展 `composables/__tests__/e1DisclosureConsistency.spec.ts`
  - _Requirements: 8.1, 8.2, 8.3, 8.7, 8.8_

- [x] 15. 披露表主表 soe 补境外款项行 + 双口径投影
  - `e1DisclosureScope.ts`：
    - `E1MainRowDef` 新增可选 `noteLabel?: string`（附注字面，缺省用 `label`）
    - `E1_MAIN_ROWS_SOE` 首行加 `noteLabel: '库存现金'`（底稿 UI 仍显源 xlsx 字面 `现金`）
    - `E1_MAIN_ROWS_SOE` 末尾补 `overseas` 行（`label`/`noteLabel` 同为 `其中：存放在境外的款项总额`、`isMemo: true`、`crossKey: ''`、`sourceRef` 写明「源 docx soe 货币资金表 r6；源 xlsx 无该行」）
  - `e1NoteSectionMap.ts` 的 `mainRow()` 改用 `r.noteLabel ?? r.label`（Property 17）
  - `E1TabDisclosure.vue` soe 主表渲染该行（金额可录入，不参与合计 —— Property 18；`overseas` 的 `isMemo` 实现直接复用 listed 侧既有那行）
  - 🔴 **必须诚实改写 `e1CurrencyScope.spec.ts` 三条锁定旧行为的断言**（Property 41）：`E1_MAIN_ROWS_SOE` `toHaveLength(5)` → 6 / `sourceRef` 序列 `['A8'..'A12']` 补新行 / `E1_MAIN_ROWS_SOE.some(r => r.key === 'overseas') === false` → `true`（该用例注释现写「国企版源 xlsx R13 是括注文字，不是数据行」）。改写理由写进用例注释：**附注行集真源是 docx 不是底稿 xlsx**，源 xlsx R13 的括注对应 docx 的正式数据行 r6
  - 🔴 **不得顺手给 soe 补「存放财务公司款项」「存款应计利息」两行** —— soe docx 主表只有 6 行，两版不对称是准则口径差异（R5.7）
  - 扩展 `composables/__tests__/e1NoteTextsAndPayload.spec.ts`：投影断言 + soe 主表 6 行 + `e1SummableRows()` 不含 memo 行
  - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_
  - **实录（2026-08-09 交付）**：后端 `test_note_e1_structure.py` **79 passed / 0 failed**（改前 78 passed / 1 failed，唯一那条 `TestProperty16SoeMainRowsMatchDocx::test_payload_projects_soe_first_row_to_docx_label` 已转绿）；E 类后端全量 `-k "e1 or e_cycle"` **358 passed / 1 skipped / 0 failed**；前端 `vitest run e1 E1` **21 files / 421 passed / 0 failed**（基线 412 → 净增 9，新增失败 0）；三改动文件 `get_diagnostics` 零诊断 + Vite transform 全 200；**变异检验 3/3 全 RED**（M1 投影退回只用 `label` / M2 移除 soe 首行 `noteLabel` / M3 移除 soe `overseas` 行）
  - **投影落法偏离了任务原文一处（更强）**：`mainRow()` 不只读 `r.noteLabel ?? r.label`，而是 `r.noteLabel ?? noteLabelByKey.get(r.key) ?? r.label` —— 按 `key` 从 `e1MainRows(variant)` 真源反查。原写法要求**每个调用方**在快照里传 `noteLabel`，漏传即产生一条静默孤儿行（附注按行标签匹配）；反查版把正确性收在真源侧，`E1MainRowLike.noteLabel?` 仅作可选覆盖保留。守卫含「不传 noteLabel 也必须投影成 `库存现金`」用例，M1 变异对它打红
  - **`E1TabDisclosure.vue` 无需功能改动（实证）**：主表完全数据驱动（`disclosureItems = e1MainRows(variant)`、合计走 `e1SummableRows` 按 `isTotal`/`isMemo` 判定、载荷 `mainRows` 全量映射）⇒ 真源加行即渲染，`isMemo` 与 listed 同一条路径。只补了说明注释（禁把 `label` 改成附注字面）
  - 🔴 **「金额可录入」与实现现状不完全一致（超本任务范围，归 Task 24）**：主表**期末列全表只读**（`computed-cell` span，值取审定表跨 sheet 键），只有期初列是 `el-input` 可录入。`overseas` 的 `crossKey` 为空 ⇒ 期末恒 0 且无录入入口 —— listed 侧同名行同款，正是 memory 已记的「`crossKey: ''` 三行注释承诺『由 render 语义槽预填』而零实现」。本任务按「沿用 listed 侧既有实现、不另造一套」处置，未改期末列可编辑性（改它要动 listed 行为 + 新增持久化键）
  - 🔴 **顺带修掉一个预存在 P0（与本任务零因果，归 spec `e1-orphan-components-wiring` Task 10）**：`E1TabDisclosure.vue` 的 `variantApplicable` JSDoc 里写了 `listed*` + `/` + `soe*`，其中 `*` `/` 组合**提前闭合块注释** ⇒ 整个 SFC 编译失败、Vite transform **500**、披露 Tab 在浏览器打不开，而 `get_diagnostics` 与 vitest 全绿（守卫只把该文件当文本读、不挂载组件）。用 `vue/compiler-sfc` 对 **HEAD 版**与工作树版分别编译取证：HEAD `FAIL (124:28)` / 工作树 `OK`，行号相同证明与本任务新增的 7 行无关。改法 = 注释里一个字符，零行为改动。**建议另立守卫**：扫全部 SFC 的 `<script>` 区块注释内是否出现 `*/`（该类缺陷四层验证全绿，只有 Vite transform 能发现）

- [x] 16. 受限表动态类别 UI + 稳定序号
  - `E1TabDisclosure.vue` 新增「+ 新增受限类别」按钮：`ElMessageBox.prompt` 输入类别名 → `customBucketKey(name)` → 建行
  - `e1RestrictedScope.ts` 新增持久化单调计数器：`e1RestrictedSeqKey(variant)` = `E1-disclosure-{variant}-restricted-seq`；`nextRestrictedSeq(existingRows, storedSeq)` = `max(现有最大, 已存计数器) + 1`
  - Property 28：删除某自定义类别后再新增，新 key 序号 > 历史最大；**朴素 `max+1` 实现必红**（守卫用替身证明）
  - 受限表行序按源 docx 6 类顺序 + 自定义类别追加在后
  - 待归类面板分区：「无子科目明细的父科目行」与「真明细行」视觉区分（R8.4）
  - 金额列一律 `WpAmountInput`（禁 `el-input-number :formatter`，EP 2.13.6 无该 prop）
  - 🔴 Property 29 是**防回退**性质不是新实现 —— 条件表语义（`restrictedRows === undefined` → 不推且不进 `_removed_table_keys`；`=== []` → 不推且**进**）**已实现且已有守卫**（`e1NoteSubtableContract.spec.ts` / `e1NoteTextsAndPayload.spec.ts` 各有用例）。新增自定义类别时要断言该语义不被打破（删空全部自定义类别后仍走 `[]` 分支）
  - _Requirements: 8.4, 9.1, 9.2, 9.4_
  - **归属说明（2026-08-09）**：纯函数、组件接线与守卫**由前一轮交付**（`e1RestrictedScope.ts` 30877 B / `E1TabDisclosure.vue` 91005 B / `__tests__/e1RestrictedSeq.spec.ts` 34001 B，7 describe / 46 it，未跟踪新文件）。**本轮只做变异检验 + 三项验证 + 回归验收，未重写或覆盖任何已存在文件**（收尾三文件 md5 与开工基线逐字相同 = 零净改动）
  - **变异检验 5/5 全 RED**（脚本 `backend/scripts/diagnose/_wip_t16v_mut.py`，按「失败测试名集合差集」判定 + 每条锚点断言 `hits == 1` + 备份落 `.t16vbak` 并提供 `--restore`）：
    - **M1** `nextRestrictedSeq` 退化朴素 `max+1`（去掉 `parseRestrictedSeq(storedSeq)` 参与）→ **4 条新增失败**，含预期的「🔴 核心：删掉最高序号行后，新 key 序号 > 历史最大（计数器兜住）」与「🔴 反向自检：朴素 max+1 会复用已删序号」，另带出「按行数派生同样会复用」与「四表命中行 id 不带自定义前缀」
    - **M2** `parseRestrictedSeq` 的 `if (!Number.isFinite(n) || n <= 0) return 0` 改 `return n`（脏值直穿）→ **3 条**（非数值/空/负/零归一 · Infinity 不得当合法序号 · 计数器脏值不得让序号回落）
    - **M3** `bucketDisplayOrderMap` 回退数组下标（忽略 `displayOrder`）→ **5 条**，且**分类语义 16 条用例全部保持绿**（双向锁死成立，逐例状态见下）
    - **M4** 删 `E1TabDisclosure.vue` 落库处的 `items.push({ item_id: seqKey, ... })` → **1 条**「🔴 计数器随行落库：buildItems 体内往 items 推 seqKey」（判据落在函数体内，不是全文 `toContain`）
    - **M5** `isParentLikeLeaf` 的 `!/[.\-]/.test(code)` 改恒 `true` → **2 条**（待归类两区分区正确 · 🔴 判据只看科目码形态不看金额）
    - 还原核验一律按「与变异前 md5 逐字相同」判（**不**按变异字样是否出现 —— `new_prov[key] = value` 一类合法同形会误判）；5 条均 `restore_check=OK`，收尾 `BAK_COUNT=0`
  - **M3 双向锁死实测明细**：变异下 17 条相关用例里 16 条绿（人工归类优先 / 人工改判「不受限」 / 归类 map 往返无损 / L2 性质文本匹配不上不落兜底桶 / E0-6 未指定 accountingTarget 不进分类 / soe 主表 6 行 / `e1SummableRows` 不含 memo 行 / 待归类分区被真实消费 …），唯一打红的 `e1CurrencyScope.spec.ts::自动分类结果按桶聚合` **标题与判据不符** —— 其断言体是 `expect(rows.map(...)).toEqual([['bank_acceptance',100],['letter_of_credit',200]])`，**有序 `toEqual` 数组本质是行序断言**而非分类断言。如实登记不擅改（改标题或改成无序比较都会削弱既有保护），建议后续轮次拆成「分类归属（无序）」+「行序（有序）」两条
  - **三项验证**：① **Vite transform 全 200**（`E1TabDisclosure.vue` 288513 B / `e1RestrictedScope.ts` 63116 B / `e1RestrictedSeq.spec.ts` 94923 B，dev server 在 3030 运行）② **回归对照与基线逐项相同**：`npx vitest run e1 E1 --reporter=json` 前后均 `numTotalTestSuites=136 / numFailedTestSuites=0 / numTotalTests=563 / numPassedTests=563 / numFailedTests=0`，**失败测试名集合前后皆为空集** ③ **`getDiagnostics` 未执行** —— 该工具不在本轮执行环境的工具集内（如实标注，不冒充已查）。替代证据两条：Vite transform 200 是比 Volar 更强的编译期权威（memory 已记「崩溃类 bug 以 Vite transform 为权威，Volar 查不出 SFC 结构损坏/import 解析失败/未声明 binding」）；且 46 例守卫真实 import 这两个模块并执行，符号缺失会以 collection 失败暴露。**遗留**：三文件的 `getDiagnostics` 零诊断待有该工具的会话补一次
  - **两处 tasks.md 预设被实证否掉，本轮未按原文施工**：
    - **`isParentLikeLeaf` 不是 dead output** —— 它经 `partitionUnclassified` 被消费（`e1RestrictedScope.ts` L697 定义 → L1417/1425 分区，`.vue` 内 `partitionUnclassified` 4 处），模板 L1597~L1723 两区已分别渲染并带独立 `data-testid`，另有守卫「待归类分区在 script 里被真实消费（computed 实参区内调 `partitionUnclassified`）」正向锁死。**R8.4 已闭合，不需要补 UI**；M5 变异也证明该判据非空转
    - **金额控件已达标，禁改代码、禁调预算** —— ②表可编辑金额列已是 `WpAmountInput`（2 处），段内 `el-input-number` / `:formatter` 计数为 **0**；文件里剩余 2 处 `el-input-number` 是**折算率**（`endRate`/`openRate`，`:precision="4"`），按平台铁律「汇率/比例/利率绝不套用金额控件」**不得替换**。`E1_LEGACY_FORMATTER_BUDGET`（在 `e1AmountControlIronLaw.spec.ts`）**不含** `E1TabDisclosure.vue`（该文件在其 `SCOPED` 名单里已被逐个正向断言）⇒ 原文「清零后同步下调预算」不成立
  - **五条判据齐备方标绿**：实现在位（逐项探针核实）+ 守卫全绿（46 例，含在 563 内）+ 变异逐条 RED（5/5）+ 三项验证（Vite 200 / 回归对照 / `getDiagnostics` 如实标注未执行）+ 零新增失败（前后失败集合皆空集）
  - **噪声说明**：跑测试时终端可能出现 `useE1DepositDailyMatch.ts` 的一条 `vite:esbuild` 报错文本，而 `numFailedTestSuites=0` ⇒ 属噪声不是失败，前后两次运行一致出现

- [x] 17. 负余额与异常提示
  - 审定表与披露主表对负值**不经 `abs()`** 如实显示（Property 27）
  - 银行存款期末为负时在审定表与溯源面板给 `warning` 提示（实测 `a7fc75e5` = −297,771,168.89，可能是资金池/内部结算）
  - 扩展守卫：源码级断言相关取值路径无 `Math.abs` / `abs()`
  - _Requirements: 8.5_

- [x] 18. 主表存款应计利息口径与 guidance
  - 🔴 **源模板实证推翻本任务原描述**：审定表 E1-1 的应计利息是 **R13 = `SUM(G14:G17)` 四子项**（`R14` 财务公司存款 / `R15` 银行机构存款 / `R16` 其他货币资金 / **`R17` 数字货币**），而披露 sheet `B12 = G14+G15+G16` **只取三项、漏掉 G17** ⇒ 那是**源模板自身缺陷**不是正确口径。前端 `useE1Adjudication.accruedTotalValues()` 汇总四子项（`accrued_finance/bank/other/digital`）**与审定表 R13 一致 = 前端是对的**，故不得「把前端核对到与预设一致」（那会让披露少计数字货币应计利息）
  - 处置按平台铁律「源模板缺陷按意图实现 + 登记留证」：预设 description 与主表 guidance 均如实写明两个口径并标注漏项，前端口径不动
  - 附注 五、1 主表 guidance 补写「存款应计利息指按实际利率法计提、尚未到付息期的部分，不含逾期未收利息（列示于『应收利息』），且不属于现金及现金等价物」
  - 该 guidance 走 Task 12 的幂等脚本落地
  - _Requirements: 8.6_

- [x] 19. 回归与 CI
  - 后端：`backend/tests/four_table` 全量 + E1 相关；前端：`npx vitest run e1 E1 --reporter=json --outputFile=<abs>.json`
  - **动手前先实测记录基线**（memory 铁律：不信记载），改动后失败集合逐条相同
  - 零回归双证：① 既有 132 个 E1 守卫全绿（**扣除按 R5.8 / R6.9 诚实改写的 4 条**：`e1CurrencyScope` 三条 + `e1RestrictedScope` 行序一条 —— 这四条是「测试镜像旧行为」不是回归，报告里必须与真实回归分开列）② 未触碰模块失败集合相同（Property 32：`e_cycle_specs` 5 槽 / `E1-adj-total-*` 键 / 三个既有种子键名逐字节相同）
  - 🔴 用「**前后对照**」而非 HEAD-swap —— 本 spec 要改的 `note_template_*.json` 混着并发会话未提交成果，HEAD-swap 会抹掉它们（memory 已记该事故）
  - `governance-checks.yml` 新增两个 job：`e-cycle-extraction`（后端，引用 Task 1/2/3/4 的守卫文件 + 三个幂等脚本 `--check`）与 `e-cycle-frontend`（前端，引用 Task 7/8/23/24 的守卫）
  - CI 引用的文件必须全部存在；yml 改完 `yaml.safe_load` 验证可解析且 job 名无重复
  - _Requirements: 9.4, 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 11.6_

- [x] 20. 变异检验（逐条打红）
  - 新建 `backend/scripts/diagnose/mutate_e_cycle_guards.py`，**≥20 个变异**（清单见 design.md Testing Strategy）
  - 其中四条是本轮新增缺陷的专用变异，必须逐条验：**去 `await`**（源码 + 连库两处同时红）· **`displayOrder` 改回数组索引**（展示序红、分类绿）· **打乱声明序**（分类红、展示序绿）· **删主表预填链**（Property 35 红）
  - **三态判定**：`new_fails` 非空 = RED 有效 / 空 = 守卫缺陷 / 锚点命中数 ≠ 1 = ANCHOR-MISS 脚本缺陷
  - 按**失败测试名集合差集**判定，不看退出码（Wave 1 守卫基线本就是红的）
  - 备份必须落 `.bak` + 提供 `--restore`（只靠 `finally` 在本仓库并发度下不可靠，memory 已记事故）
  - 锚点必须**行级唯一**且不跨行（`.py`/`.ts` 工作树多为 CRLF，含 `\n` 的锚点必 MISS）
  - 还原核验用「与变异前 md5 逐字相同」，不按「变异字样是否出现」判（可能有合法同形）
  - 变异脚本 targets 必须覆盖**本 spec 全部守卫文件**，报告里打印 baseline passed 数
  - _Requirements: 10.4_

- [x] 21. 真实库验收
  - 跑 Task 6 的脚本覆盖全部 8 项目：账户级取数勾稽全部成立、`parsed_level` 分布、`unassigned` 明细
  - 用**独立 SQL** 交叉核对至少一个项目的账户合计（不拿被测函数证明自己）
  - 附注侧：跑 Task 12 幂等脚本 `--check` 归零 + 用 python-docx 复核四处修正与源 docx 一致
  - 记录实测结论进 tasks.md Notes（含被推翻的立项判断）
  - _Requirements: 10.1, 10.7_

- [x] 22. 浏览器实测与数据复原
  - 项目选 `0ec33ac9`（listed，22 个账户）+ `2aa00f57`（soe，17 个账户）
  - **实测前抓基线三件**：`parsed_data` 全文 + md5 + `jsonb_typeof`（memory 铁律：只记 length 不够，保存会新增副产键）
  - 验证项：E1-3 显示逐户账户行（含开户银行与账号，且原币/汇率列**留空**）· E1-3 两个 variant 账户条数相同 · E1-10 账户清单含零余额账户 · E1-4 显示「本项目无此科目」· 溯源面板显示账户数 / `parsed_level` 分布 / 勾稽 diff · **listed 披露主表「存放财务公司款项」「存款应计利息」「数字货币」三行按槽预填或如实空白（不显 0）** · soe 披露主表 6 行含境外款项 · **受限表行序 = 银行承兑→信用证→履约→担保定期→境外→法定准备金→(其他受限)→合计**（验展示序修好）· 新增自定义类别 + 删后再增序号不复用 · 推送后附注 八、1 落 6 行 · 外币段推送落 五、73/八、92 的 BS-002 段且他段行保留
  - 🔴 实测一律用 chrome-devtools 的 `take_snapshot`/`click`/`fill`（真实交互），**禁用 `evaluate_script` 遍历 DOM 探测**（会误触组件丢数据，memory 已记两次事故）
  - 复原：按基线三件逐字节复原，用**独立查询**验证复原成功（不看脚本自己的输出）
  - 清掉本 spec 产生的 `_wip_*` / `tmp_*` 诊断产物
  - _Requirements: 10.7_

- [x] 23. 受限桶展示序与优先级序分离
  - 🔴 **本任务修的是一个既存缺陷**：`E1_RESTRICTED_BUCKETS` 的声明序同时承担「匹配优先级」与「附注行序」两个语义，而两者实际不同 —— 声明序 `信用证→银行承兑→履约→境外→质押→other`，docx/模板行序 `银行承兑→信用证→履约→质押→境外→(新)法定准备金`（**1↔2、4↔5 互换**）。前端 `e1RestrictedScope` 推送排序用的正是 `bucketDefs` 数组索引 ⇒ **附注行序与 docx 不符**
  - 优先级序**不能改**（有硬理由：「信用证保证金」含「保证金」必须先于兜底桶；「境外冻结存款」同含「冻结」与「境外」，境外须优先）
  - 落法（零新增字段）：`bucket_defs_payload()` 增发 `displayOrder` —— 源类桶按 `source_ref` 的**单元格行号升序**（现值 `A17`/`A18`/`A19`/`A20`/`A21`，新桶 `A22`，恰好就是 docx 行序），平台补充桶（`source_ref is None`）排最后；前端 `e1RestrictedScope` 的排序键改用它
  - 前端类型 `E1RestrictedBucketDef` 加 `displayOrder`，`normalizeRestrictedPrefill` 缺字段时退化为数组索引（向后兼容）
  - 🔴 **诚实改写既有用例** `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` —— 其标题声称的等价关系本就不成立，改为按 `displayOrder` 并在注释写明两序分离的理由（Property 36）
  - 守卫**双向锁死**：① 打乱声明序 → 分类结果必红、`displayOrder` 序列不变；② 改 `source_ref` 行号 → `displayOrder` 必红、分类结果不变
  - 与 Task 13 碰同一文件 ⇒ **先 13 后 23** 或合并落地
  - _Requirements: 6.7, 6.8, 6.9_

- [x] 24. 披露主表三个无科目码行接语义槽预填
  - 🔴 **本任务兑现一处「注释承诺了但零实现」** —— `E1_MAIN_ROWS_LISTED` 的 `finance_co`「存放财务公司款项」/ `accrued`「存款应计利息」/ `digital`「数字货币」三行 `crossKey: ''`，注释明文写「由审计师手工填或**由 render 的语义槽预填**」，而当前无任何预填实现（同 E1-4 预设 description 那处的未兑现承诺）。它比明细表更直接影响交付件（附注主表行）
  - `finance_co` / `digital` 取对应语义槽的审定合计（Task 5 扩槽后 `adjudication_prefill` 已含这两槽）；`accrued` 取 E1-1 审定表应计利息三行之和（口径同 R8.6，源 xlsx B12 = G14+G15+G16）
  - persist-first：仅当该行**无手工值**时写入；槽 `found=False` 时保持**空白而不写 0**（Property 35）
  - 🔴 **soe 主表没有这三行**（docx 只 6 行）⇒ 预填只作用于 listed 变体，soe 侧无落点（R5.7），守卫要断言这一点而非「两版都预填」
  - 新增 `composables/__tests__/e1MainRowPrefill.spec.ts`：三行预填 / `found=False` 不写 0 / 手工值不覆盖 / soe 变体无该三行 / **反向自检：删掉预填链后三行恒空必红**
  - 依赖 Task 5（render 扩槽）
  - _Requirements: 2.6, 2.7_
  - **实录（2026-08-09 交付）**：新建纯函数 `composables/e1MainRowPrefill.ts` + 守卫 `__tests__/e1MainRowPrefill.spec.ts`（**42 例全绿**）+ 审定表侧 `useE1Adjudication.syncAuditedTotals()` additive 写槽键 + 披露表侧 `E1TabDisclosure.vue` 三处取值改走纯函数。E1 前端回归 **23 files / 483 passed / 0 failed**（Task 23 时 21/412 ⇒ 净增 2 suites / 71 例，零新增失败）；三个改动文件 Vite transform 全 **200**；**变异检验 4/4 全 RED**（字节级备份 + md5 还原核验，残留 0）
  - 🔴 **落地时查出 spec 未预见的双算风险，这是本任务最关键的设计判断**：审定表 `aggregateAuditedByCode()` 的科目归集口径是 `1002` = **`bank_principal` 全额**（`ROW_MATRIX` 里 `finance_co` 是它的「其中：」子项）、`1012` = `other_mf` + **`digital`**；而附注 docx 主表把「存放财务公司款项」「数字货币」写成**与银行存款/其他货币资金平行的列示行**（8 行里只有 `overseas` 带「其中：」前缀）⇒ 若照 spec 字面「三行取对应语义槽的审定合计」直接填，**合计会双算**（1002 已含 fc、1012 已含 dg）。处置 = **扣减映射** `E1_MAIN_ROW_DEDUCTIONS`（`bank -= slot(finance_co)` / `other_mf -= slot(digital)`），依据是准则解释 15 号要求这两项单独列示 ⇒ 银行存款行语义即「银行机构存款」。合计恒等式 `1001 + (1002−fc) + fc + (1012−dg) + dg + accrued = 1001+1002+1012+accrued` 由 PBT 守卫钉死
  - 🔴 **有意不给这两行标 `isMemo`** —— memo 语义是「其中：」子项而 docx 该两行不带该前缀；标了会让底稿 UI 与交付件的列示层级分叉，且要动 `e1DisclosureScope` 刚被 Task 15 诚实改写的断言
  - 🔴 **`accrued` 行是净增修正不是扣减** —— 存款应计利息**不属任何科目码**（`1001`/`1002`/`1012` 三个 `E1-adj-total-*` 都不含它，审定表 `aggregateAuditedByCode` 只取 `cash`/`bank_principal`/`other_mf`+`digital`）⇒ 改造前披露主表合计**系统性漏掉全部应计利息**。加它后合计变大是**修正**，守卫用「有 accrued 时合计 == 三科目 + accrued」正向锁死
  - **零回归支点（实测）**：全库 8 项目 `finance_co` / `digital` 两槽 `found=False`（`account_chart` 对「数字货币 / 数字人民币 / 财务公司」0 命中）⇒ 审定表那两行三值全 0 ⇒ **不写槽键** ⇒ 扣减额为 0 ⇒ `bank`/`other_mf` 取值与改造前逐字节相同、两行显示空白。守卫有专门用例断言这条
  - **「不写 0」的落点在写入侧不在读取侧**（Property 35）：`buildE1MainRowSlotWrites` 对「未审/调整/审定三值全 0」的行**不产出该键**，披露侧读不到即 `null` ⇒ UI 显示 `—` + tooltip「本项目无此科目或审定表未录入」，与「余额确实为 0」（显示 `0.00`）可区分。若无条件写 0，两态就不可区分
  - **UI 三个新标记**：`endingResolved=false` → `—` + tooltip · `endingPrefilled=true` → `预填` tag（槽预填而来）· `endingDeducted=true` → `已扣除` tag + tooltip 说明扣了哪一项。合计行不显示这些标记
  - **有意不复现审定表取数逻辑**：应计利息四子项汇总口径（`accruedTotalValues`：E1-20 明细行非空则按 category 汇总、否则读手工未审数）留在 `useE1Adjudication`，本模块只定义键名与读写契约 —— 复现一份即双真源（与 R8.6 的口径登记一致，那里已明确源模板 B12 漏 G17 是源模板缺陷、前端四子项口径是对的）
  - **soe 侧行为**：soe docx 主表 6 行**没有** `finance_co` 与 `accrued`（准则口径差异）⇒ 预填对它们无落点；`digital` 在 soe 行集里但 `crossKey` 亦为空 ⇒ 同样走槽键（恒空）；`other_mf` 走同一条扣减映射（`digital` 槽空 ⇒ 扣减 0 ⇒ 行为不变）。守卫按此断言而非「两版都预填」
  - **变异清单**（全部 RED）：M1 移除扣减映射（双算恒等式必红）· M2 `buildE1MainRowSlotWrites` 无条件写 0（「不写 0」与空白态断言必红）· M3 `resolveE1MainRowAmount` 取不到值返 0 而非 null（两态可区分性必红）· M4 槽键前缀改成与 `E1-adj-total-` 撞名（键空间隔离断言必红）

## Notes

### Wave 1 实录之一：账户级取数判据守卫（Task 1，2026-08-08）

产出 `backend/tests/four_table/test_e1_bank_accounts_live.py`（10 例）。**结果 3 failed / 7 passed = 符合「先打红」设计**。

**设计取舍：把断言分两类，让红落在「功能未实现」而不是「守卫写坏了」**

- **类 A（7 例，独立 SQL 口径，现已全绿）** —— 数据存在性 / 基线计数 / 与 `tb_balance` 叶子勾稽 / `aux_dimensions_raw` 含两维度 / 裸查对照 / 同账号多行聚合。全部用本文件自己的 SQL 算，**不碰被测实现** ⇒ 绿了才证明判据基础设施有效（不是空转），同时兑现「不拿被测函数证明自己」。
- **类 B（3 例，现全红）** —— 被测实现的 API 齐备性 / 解析器对真实 `aux_dimensions_raw` 的产出 / `fetch_e1_bank_accounts` 与独立 SQL 口径一致。

🔴 **不在模块顶层 import 生产模块**，改为测试内 try-import 后 `pytest.fail`。顶层 import 失败会让整个文件 collection error、零断言执行 ⇒ 无法区分「功能未实现」与「守卫写坏了」（memory 已记同族教训）。

**三条反向自检实测生效（PASSED 而非 skip），dataset 过滤的必要性已实证**：

| 断言 | 结果 | 含义 |
|---|---|---|
| `test_naive_query_differs_from_active` | PASSED | 当前库确有多 dataset 项目，裸查 ≠ active |
| `test_active_sum_is_the_one_tying_to_tb_balance` | PASSED | **只有 active 口径**与 `tb_balance` 勾稽、裸查不勾稽 |
| `test_multi_row_accounts_are_aggregated_by_name` | PASSED | 确有同账号多行样本，`GROUP BY` 口径正确 |

三条都写了「无样本时 `pytest.skip` 并说明暂不可验证 + ⚠️ 不等于可省掉该逻辑」，避免将来数据变化后变成静默假绿。

**基线口径的取舍**：`ACCOUNT_COUNT_BASELINE` 按 `count(DISTINCT aux_name)` 冻结而非「解析出的账号数」—— 后者依赖被测解析器，解析器一改基线就跟着漂。断言方向是「基线中且库中存在的项目计数必须相符」（新项目不打红，只是不校验），并要求变更时重新实测留证。

**顺带修掉探针的编码缺陷**：新建通用跑批器 `backend/scripts/diagnose/_wip_run.py`，强制 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`。此前 subprocess 用 utf-8 解码而 pytest 在 GBK 控制台输出中文 ⇒ 断言消息全成乱码（`��δʵ��`），无法判读失败原因。

### Wave 1 实录之二：Task 2 / Task 11 经实测已交付（复选框滞后，2026-08-08）

接手时 tasks.md 记 1/24，逐个探针后 **Task 2 与 Task 11 的产物已在磁盘且完整**：

**Task 2** = `backend/tests/four_table/test_e1_preset_coverage.py`（25995 B，17 例，Property 11/12/13/14 全在）。实跑 **2 failed / 14 passed / 1 skipped**，与「先打红」设计逐条吻合：

| 类别 | 例数 | 状态 | 含义 |
|---|---|---|---|
| 判据基础设施（`TestJudgementInfrastructure`）| 12 | 11 PASSED + 1 SKIP | 源模板可读+计数冻结 / 预设块计数冻结 / sheet 值唯一 / **GBK 判据双向自检**（中文与全角标点不打红 + 真 offender 必打红）/ 扫描器忽略注释与 docstring / 扫描面非空 / 引用图无环 + 真环必红 / `WP()` 抽取器同 wp_code 作用域 / 登记表上限只许缩 |
| Property 11（sheet 必须真实）| 2 | 1 FAILED + 1 PASSED | 红在 `审定表E0-1`，且断言消息直接写明「真实 tab 名是 `函证结果汇总表E0-1`，Wave 4 Task 10 待修」；另一例证明该错名**不可能由归一化救回**（不是空格差异）|
| Property 12+40（覆盖面完备）| 2 | 1 FAILED + 1 PASSED | 红在 **6 张待补预设 + 18 张待登记**，按四路分别列出 |
| Property 14（GBK 可编码）| 1 | PASSED | 三个脚本能到达控制台的字面量已全部 GBK 可编码 |

🔴 **实测修正 spec 里的两处数字**：待登记是 **18 张**不是 14 张 —— spec 的 R3.3 清单（E1 侧 7 + E0 侧 7）漏了 `银行存款及其他货币资金明细表(仅人民币)E1-3`（它由 R3.7 单独处置，Task 10 要补预设而非登记）与 3 张非数据表（`函证程序表E0A` / `货币资金实质性程序表E1A` / `货币资金实质性程序表E26A`）。守卫当前把非数据表也算进「待登记」= **白名单尚未生效**（Task 10 落地时要同时建白名单，否则登记表会被塞 3 条噪声，正是 R3.8 要防的）。

**Task 11** 经实测**已无欠账**（`fix_e1_orphan_sheet_presets.py` 的 emoji 已归零，输出为 `[OK] E1 orphan sheet presets: 0 欠账`）。**GBK 控制台下三脚本 `--check` 全部 rc=0**（本任务判据就是退出码，故用默认编码 subprocess 捕获，不设 `PYTHONIOENCODING`）。

🔴 **顺带纠正一处 memory 记载**：GBK **不可**编码的是 `−`(U+2212，减号) 而 memory 记的是 `—`(U+2014，破折号) —— 后者 GBK 可编码。实测 `fix_e1_prefill_presets.py` 有 3 处、`fix_note_e1_monetary_fund_structure.py` 有 1 处含 `−`，但**全部落在 `description`/`guidance` 字段**（进 JSON 不进控制台）⇒ 守卫 PASSED 是正确的，不是漏判。这也验证了 R4.4「扫描面按是否到达控制台划分」这条判据的必要性：按「文件里出现不可编码字符」写会误伤这 4 处。

### Wave 1 实录之三：附注结构与段 row_code 守卫（Task 3，2026-08-08）

`test_note_e1_structure.py` 由 60 例扩到 **75 例 = 6 failed / 69 passed**（18327 → 约 38 KB），红全部落在预期缺陷上、**0 error**。

新增 6 个类：`TestDocxFixtureSanity`（3）· `TestProperty37ListedHasNoRestrictedTableInDocx`（4）· `TestProperty16SoeMainRowsMatchDocx`（4）· `TestProperty41VariantAsymmetryIsIntentional`（2）· `TestProperty20RestrictedRowOrderMatchesDocx`（4）· `TestProperty23FxSegmentRowCodeMatchesReportConfig`（2，连库）+ `TestProperty19And30Snapshots`（快照冻结）。

**六个红的落点**（与 Wave 4/5 任务一一对应）：

| 红的用例 | 缺陷 | 修它的任务 |
|---|---|---|
| `test_template_soe_main_matches_docx` | soe 主表 5 行 vs docx 6 行、首行 `现金` vs `库存现金` | Task 12 |
| `test_payload_projects_soe_first_row_to_docx_label` | `e1DisclosureScope` 无 `noteLabel` 双口径投影 | Task 15 |
| `test_template_restricted_covers_six_plus_total` ×2 | 两版受限表缺「金融企业法定存款准备金或备付金」 | Task 12 + 13 |
| `test_platform_supplement_is_declared_not_claimed_as_docx_aligned` | listed ②表 guidance 未登记「平台补充表」 | Task 12 |
| `test_row_code_row_name_matches_segment_label[soe]` | 八、92 短期借款段 `BS-031`（使用权资产）应为 `BS-041` | Task 12 |

**docx 抽取的三处实现要点**（都是踩过才对）：① `_docx_section_blocks()` 沿 `document.element.body` 走并按 `w:tbl`/`w:p` 分流 —— 只遍历 `doc.tables` 拿不到「哪张表属哪个章节」；② listed 走 **Heading 2**、soe 走 **Heading 3**（两版层级不同，写死一个会 0 命中）；③ 节的结束边界是「遇到**同级或更高级** Heading」，只判同级会把子节内容吞进来。

**docx 实证复核（与 spec 判据全部吻合）**：listed 主表 9×3（表头 + 8 数据行，含 `存放财务公司款项`/`存款应计利息`）· soe 主表 7×3（表头 + 6 行，**无**那两行）· soe 受限表 7×3（表头 + 6 类，**无合计行**）· **listed「货币资金」节只有 1 张表**，受限内容是两段文字。

**🔴 新查出：后端还有 4 条锁定旧行为的断言要在 Wave 4 一并改写（spec R5.8 原只登记了前端 3 条）**：`test_soe_main_rows_verbatim`（按源 xlsx R8~R12 断言 5 行）· `test_soe_first_row_is_cash_not_cash_not_hand`（断言模板首行必须是 `现金`）· `test_soe_has_no_overseas_data_row`（断言 soe **不得**有境外款项行，注释写「源 R13 是括注文字」）· `test_restricted_excludes_reserve_row_and_ellipsis`（断言两版**不得**有第 6 类）。这四条与新增的 docx 三向断言**结论完全相反** —— 旧的以底稿 xlsx 为真源、新的以 docx 为真源，而 R5.8 已裁决「附注行集真源是 docx」⇒ Task 12/13 落地时必须删掉这四条旧断言（不是放宽），并在提交报告里与真实回归分开列。为此在新守卫里各留了一条对照断言（`test_soe_docx_lacks_finance_co_and_accrued` 等）证明差异是有意的。

### Wave 2 实录之一：账户级取数共享件（Task 4，2026-08-08）

产出 `backend/app/services/four_table/e1_bank_accounts.py`（15.4 KB）+ `backend/tests/four_table/test_e1_bank_accounts.py`（**53 passed**）+ 变异脚本，**变异 12/13 RED**（M11 经复算确认是无效变异，非守卫缺陷）。

**🔴 变异检验抓出一个真实现缺陷（M6 首轮 GREEN）** —— `assign_accounts_to_slots` 原用裸 `row.account_code.startswith(c)`，而平台既有口径是 `code == p or code.startswith(p + ".")`（`leaf_aggregation.filter_by_prefixes` / `resolve_leaf_totals` 都是点号边界）⇒ **`10021`（另一个一级科目）会被 `1002` 槽吞掉**。已抽 `_code_matches_prefix` helper + 两条守卫（逐样本拿平台 helper 当裁决者比对行为等价 + 源码级禁裸 `startswith`）。这是「守卫全绿不等于实现对，变异检验才是判据」的又一实例。

**两处守卫自身缺陷（GREEN → RED）**：

| 变异 | 首轮 GREEN 的原因 | 修法 |
|---|---|---|
| M9 空前缀仍查库 | 替身抛 `AssertionError`（`Exception` 子类）**被 fail-open 的 `except Exception` 吞掉** ⇒ 返 `[]`、断言照样过 | 替身改抛 `BaseException` 子类穿透，并加一条「该替身确实能穿透 fail-open」的自检 |
| M13 fail-open 不 rollback | 压根没写这条守卫（守卫缺口） | 新增 `TestFailOpenRollsBack`（替身记调用序列 + 源码级断言 rollback 在 except 分支内） |

**🔴 `get_active_filter` 自己内部也 `db.execute` + 自带 fail-open rollback** ⇒ 替身记到的调用序列是「它的一对 + 我们的一对」（`['execute','rollback','execute','rollback']`），按 `== ['execute','rollback']` 写死会假红。判据改为「`execute` 之后必须出现 `rollback`」的鲁棒形式。

**实现要点**（与 spec 一致，另补两处 spec 未写的）：`fetch_e1_bank_accounts` 用 `await get_active_filter(db, TbAuxBalance.__table__, project_id, year)`（Property 39 源码守卫钉死）· 空前缀**在 try 之前**早退不查库 · 归属取**最长前缀**且带点号边界 · `unassigned` 显式保留 · 勾稽只对两侧都有数据的槽产出条目 · 载荷 `accounts` 各键恒存在（无数据是 `[]` 不是缺键）。

**探针实证纠正一处基线口径**：`0ec33ac9` 裸查 **23** 个账户 / active **22** 个（`ACCOUNT_COUNT_BASELINE` 记的 22 是对的）—— 这正是 Task 1 反向自检「裸查 ≠ active」的活样本，8/8 项目 `active == baseline`。

**顺带记两处踩坑**：`TbAuxBalance` 在 `app.models.audit_platform_models`（不是 `app.models.trial_balance`）· `RenderContext` 不在 `wp_render_config_helpers`（Task 4 不需要它）。

### Wave 2 实录之二：render 接账户级取数 + 扩槽（Task 5，2026-08-08）

新增 `_build_account_prefill` / `_empty_account_prefill` / `_ACCOUNT_SLOT_KEYS`；`_DETAIL_SLOT_KEYS` 由 3 槽扩至 **5 槽**；render 返回 dict 新增 `account_prefill` 键。守卫 `test_e1_render_account_prefill.py` **30 passed / 1 skipped**，**变异 5/5 全 RED**。

**🔴 `_ACCOUNT_SLOT_KEYS` 是 3 槽不是 5 槽**（`bank`/`other`/`finance_co`）—— `cash` 是库存现金（无银行账户维度）、`digital` 是数字货币（不走银行账户），把它们纳入会让 aux 查询带上无意义前缀。这与 `_DETAIL_SLOT_KEYS`（5 槽）是**两个不同的集合**，守卫已双向锁死。

**守卫抓出一处零回归风险（已修）**：`_build_account_prefill` 起初没有自己的 fail-open —— 它抛异常会让 `_build_four_table_extraction` 整体失败，把**已经通了的三槽明细预填、审定预填、受限分类一起打掉**（比「账户级取空」坏得多）。现改为内部 `try/except` + `_empty_account_prefill()` 兜底，且 `except` 里**先 rollback**（aux 查询失败后事务 aborted 会让同一 render 里后续查询全部失败并伪装成「本项目无数据」）。

**四个变异首轮 GREEN 全是真守卫缺口（非无效变异），逐条补齐后转 RED**：

| 变异 | 首轮 GREEN 的原因 | 补的判据 |
|---|---|---|
| M1 扩槽退回 | 断言只读 import 进来的常量，**没有源码级断言** ⇒ 改声明块时测试进程用的仍是被 import 的值 | 加「声明块源码里五个槽名逐个在场」+ 顺序断言 |
| M2 dead output | `_fn_body("render")` 截取范围没覆盖到 return dict | 改为**整函数体键集冻结**断言（8 个键精确相等）|
| M5 空态返 `{}` | 守卫只测 `_empty_account_prefill()` 本身，**没真调** `_build_account_prefill` | 加替身 ctx 真调该函数（无槽码路径），断言返回形态合法而非裸 `{}` |
| M8 勾稽口径漂移 | `slot_leaf_closing` 零覆盖 | 加「勾稽基准必须是叶子**期末**合计」断言（造期初≠期末的样本区分两种口径）|

M1 那条最值得记：**「读 import 常量」与「读源码声明」是两种判据，只有后者能抓住声明块被改**（前者在模块已加载时拿的是旧值）。

**Task 5 的零回归支点**：`build_e1_detail_rows` 的字段名/顺序/映射/全零过滤全部逐字不变，扩槽只是让返回 dict 多两个键（characterization 守卫按字段序列冻结）。`_num`/`_is_all_zero`/`build_e1_account_list`/`build_e1_tb_values` 均未触碰。

### Wave 2 实录之三：账户级取数真实库验收（Task 6，2026-08-08）

产出 `backend/scripts/diagnose/verify_e1_account_extraction_live.py`（只读 / 默认 dry-run / `--all-projects` / `--project`）。**最终实测 10 个「项目×年度」全部 OK、diff 全 0.00、结论 PASS**。

| 项目:年度 | 账户数 | 独立SQL | 取数合计 | tb_balance | diff |
|---|---|---|---|---|---|
| 0ec33ac9:2025 | 22 | 22 | 4,703,056.26 | 4,703,056.26 | 0.00 |
| 12c15a96:2025 | 22 | 22 | 4,703,056.26 | 4,703,056.26 | 0.00 |
| 2aa00f57:2024 | 23 | 23 | 848,871.86 | 848,871.86 | 0.00 |
| 2aa00f57:2025 | 17 | 17 | 327,095.20 | 327,095.20 | 0.00 |
| 4f6dbc36:2025 | 2 | 2 | 4,048.93 | 4,048.93 | 0.00 |
| 52c04ed1:2025 | 21 | 21 | 1,272,030.63 | 1,272,030.63 | 0.00 |
| a7fc75e5:2025 | 38 | 38 | **−297,771,168.89** | −297,771,168.89 | 0.00 |
| b39809ed:2025 | 6 | 6 | 0.00 | 0.00 | 0.00 |
| c8621493:2025 | 1 | 1 | 110.30 | 110.30 | 0.00 |
| f064f5e4:2024 | 23 | 23 | 848,871.86 | 848,871.86 | 0.00 |

`a7fc75e5` 的负余额**如实保留未 abs**（负数是「贷方性质」的真实语义，套 `abs()` 会让勾稽从 0 变成两倍）；`parsed_level` 分布 **10/10 项目全为 `{'1': N}`** ⇒ 全部账户走的是「账号 + 银行名」完整解析路径，降级路径当前零命中（属潜伏态，替身守卫已覆盖）。

**🔴 脚本自身两处缺陷（都靠真实库暴露，替身测不到）**

| # | 缺陷 | 症状 | 修法 |
|---|---|---|---|
| 1 | aux 侧走 `get_active_filter`、**`tb_balance` 侧却是裸 `is_deleted = false`** | 同一 `account_code='1002'` 在多 dataset 各有一行（实测 `0ec33ac9` 3 行 / `2aa00f57` 2 行 / `c8621493` 3 行，金额相同）⇒ 裸查翻 2~3 倍 ⇒ 产出 **4 个假 DIFF**（diff 恰好 = −取数合计） | 改 ORM + `get_active_filter(db, TbBalance.__table__, pid, year)`，两侧口径一致 |
| 2 | 基线 `ACCOUNT_COUNT_BASELINE` 键是**短码单键**，而同一 `project_id` 可有多个审计年度 | `2aa00f57` 有 2024=23 / 2025=17 两行 ⇒ `by_short` 字典**互相覆盖** ⇒ 基线 17 被拿去比 2024 的 23，报「基线不符」**假 WARN** | 键改 **`短码:年度`** 复合键（10 条，补录 `2aa00f57:2024`=23 与 `12c15a96:2025`=22）+ 连库守卫加「复合键不得因覆盖而丢项目」反向自检 |

**🔴 第 3 处缺陷由变异检验挖出（M3 首轮 GREEN）**：只把「取键方式」退化成短码时，因基线键已是复合键 ⇒ 全部 miss ⇒ **既无 WARN 也无报错 = 静默假绿**。连库守卫有 `assert checked > 0`，而验收脚本**缺等价自检** ⇒ 新增「基线命中数为 0 即 `[FATAL]` + rc=1」+ 报告里固定打印 `基线命中：N/M`。

**变异检验 4/4 全 RED**（字节级备份 + `finally` 还原 + md5 核验）：

| 变异 | 判据 | 结果 |
|---|---|---|
| M1 态名派生改写死小写清单 | rc≠0 且输出含 `FATAL` | RED（`unknown` 检查生效）|
| M2 `tb_balance` 侧漏 active filter | rc≠0 且 `DIFF > 0` | RED，**`DIFF=4`** 与首轮实测的 4 个假 DIFF 数量逐一吻合 = 结构性证据 |
| M3 验收脚本基线取键退化为短码 | rc≠0 且输出含「基线命中 0」 | RED（新增自检生效）|
| M4 连库守卫基线索引退化为短码 | pytest rc≠0 | RED（`by_key` 覆盖自检 + 基线比对同时打红）|

M2 的锚点第一版写成**三行跨行字符串**导致 `ANCHOR-MISS hits=0`（memory 已记「跨行锚点在 CRLF/缩进不匹配时必 MISS」，本轮再证）→ 改**单行锚点**（`tb_active,` 那一行）后立刻 RED。

**连库守卫复合键改动后仍 10 passed**（改前也是 10 passed，即该改动是纯判据加强、零回归）。

**新增通用跑批器 `_wip_e_t6v.py`**（跑任意 python 脚本 + 强制 UTF-8 写盘）—— 既有 `_wip_run.py` 只能跑 pytest，直接传脚本路径会以 `rc=4` 收集失败（表现像脚本坏了，实为跑批器用错）。

### Wave 3 实录之一：前端账户级归一层（Task 7，2026-08-08）

产出 `composables/e1BankAccountPrefill.ts`（`normalizeAccountPrefill` / `assignedAccounts` / `hasAccountData` / `isBaseCurrency` / `currencyLabelOf` / `buildBankSeedRowsFromAccounts` / `buildAccountListSeedRowsFromAccounts` / `buildDigitalSeedRows`）+ 守卫 `__tests__/e1BankAccountPrefill.spec.ts`（**32 例全绿**）+ **变异检验 8/8 全 RED**。E1 前端回归 **96 files / 363 passed / 0 failed**。

**🔴 落地时实测到 spec 未写的冲突：`multi` 版若按「原币列留空」实现，金额会被静默抹成 0**

`useE1BankDetail.recalcRow` 在 `variant === 'multi'` 下把 `opening/increase/decrease/ending/adjustment/audited` **全部由「原币 × fxRate」派生**。而 spec 的 Property 34 要求「原币金额与汇率不得由本位币反推」⇒ 若原币列留 0 而只给本位币列，recalc 会把从 aux 取到的本位币金额覆盖成 0 —— 界面显示「有账户、金额全 0」，**比取不到更坏**（用户会以为客户余额确实为零）。

处置 = 把「恒等」与「反推」分开（这条区分是本任务的核心判断）：

| 币种 | multi 版下发 | 依据 |
|---|---|---|
| CNY / RMB / 空 | `fxRate=1`、`openingFc=opening`、`increaseFc=debit`、`decreaseFc=credit` | 「原币 == 本位币、汇率 = 1」对本位币账户是**恒等事实不是推断**；实测 aux 侧 `currency_code` 全库 308 行全为 `CNY` |
| 非本位币 | `fxRate=0` + 原币列全 0 + `note` 追加 `原币金额与汇率需手工录入（四表无原币数据）` | 原币与汇率四表确实没有（无 `closing_fc`、无汇率列）⇒ 留 0 但**不静默**，靠 note 告知 |

`rmb` 版不下发 `fxCurrency` 与任何原币列（该版 recalc 不走 fx 分支，本位币列即权威；composable 缺 `fxCurrency` 时回落 `'人民币'`）。**两版账户条数与 id 序列完全相同**（外币账户在 rmb 版不丢弃）。守卫用「复现 recalcMulti 纯函数 + 反向自检（原币留 0 时必被抹成 0）」把这条钉死。

**🔴 两处 spec 记载被实证修正**

| spec 原文 | 实测 | 后果 |
|---|---|---|
| Task 8 写 `seedRowsKey('E1-digital-detail-rows', ...)` | 真实键是 **`E1-digital-rows`**（`E1TabDigitalCurrency.vue` 的 `STORAGE_KEY`），且 E1-4 的行模型**内联在 `.vue` 里**没有独立 composable | 照 spec 写会产生零消费方的孤儿键（dead output）；守卫直接从 `.vue` 抽 `STORAGE_KEY` 与 `USER_FIELDS` 交叉锁死，并反向断言错名 |
| Task 7 写「`finance_co` 槽的账户归入 `group: 'finance'`」 | `group` 取值域由 `useE1BankDetail.GROUPS` 定义 = `institution / finance / other`，**槽名与 group 名不同构**（槽是 `bank`/`other`/`finance_co`） | 直接把槽名当 group 会落到取值域外；已建 `ACCOUNT_SLOT_TO_GROUP` 映射并断言「每个 group 值都在 GROUPS 取值域内」 |

**`normalizePrefill` additive 扩两键**（`finance_co` / `digital`，缺省 `[]`）—— 后端 Task 5 已扩 `_DETAIL_SLOT_KEYS` 到 5 槽，前端归一层原本只认 5 键 ⇒ 那两槽是 dead output。既有 5 键与 3 个既有 build 函数逐字不变（Property 9 零回归支点）。**叶子口径的 `buildBankSeedRows` 有意不动**（保持 bank+other 两槽），`finance_co` 叶子的落点归 Task 24。

**变异检验 8/8 全 RED**（字节级备份 + `finally` 还原 + md5 核验，判据 = vitest JSON reporter 的失败用例名差集）：

| 变异 | 打红的断言 |
|---|---|
| M1 `finance_co` 归错组 | 槽→group 映射（R2.3）|
| M2 行 id 前缀改回 `-ft-` | Property 7 不撞键 ×2 |
| M3 multi 版不下发原币列 | 「recalc 抹零」反向自检 |
| M4 非本位币臆造 `fxRate=1` | Property 34 |
| M5 E1-10 过滤零余额账户 | Property 6 |
| M6 digital 多给 `endingFc` 字段 | `USER_FIELDS` 子集断言 |
| M7 `normalizePrefill` 的 `finance_co` 退化成 `[]` | **新增断言**（见下）|
| M8 币种判定漏「人民币」中文写法 | 本位币判定 |

🔴 **M7 首轮 GREEN = 真守卫缺口**：只断言「新键缺省为空数组」与「既有五键不变」时，把 `finance_co: arr(p.finance_co)` 改成 `finance_co: []` **不会打红** —— 而那正是「后端发了数据前端读不到」的 dead output 形态。补了「新键必须真的透传数据 + 透传后能直接喂给 `buildDigitalSeedRows`（端到端链路可达）」两条断言后转 RED。⇒ **凡 additive 扩键，「缺省为空」与「非空时真透传」是两条独立断言，缺后者等于没测**。

M4/M5/M6 首轮 `ANCHOR-MISS hits=0`：锚点写成含 `\n` 的多行字符串，而文件是 **CRLF** ⇒ 改单行锚点后立刻 RED（memory 已记该坑，本轮又踩）。

**其它设计要点**：行 id 一律 `-acct-{账号}` / `acct-a-{账号}`（叶子口径是 `-ft-{科目码}`，Property 7）；账号为空时用科目码兜底且同账号重复出现补序号去重；`note` 如实标注「同账号 N 笔已合并」与「账号取自辅助项名称（未解析出银行名）」= `parsed_level` 降级可追溯；E1-10 **`unassigned` 账户也进清单**（aux 里有账户但科目定位未覆盖，正是完整性核对要暴露的信号），而 E1-3 不产出 unassigned 行（未归属账户定不了 group）。

### Wave 3 实录之二：宿主种子化接账户级优先（Task 8，2026-08-08）

`GtE1MonetaryFund.vue` 接线：新增 `accountPrefill` computed → `seedFromFourTable()` 与 `reExtractFromFourTable()` 双侧改「账户级优先、叶子口径兜底」→ 新增 E1-4 分支。守卫 `__tests__/e1HostSeedWiring.spec.ts`（**25 例全绿**）+ **变异检验 8/8 全 RED**。E1 前端回归 **102 files / 388 passed / 0 failed**（Task 7 时 96/363 ⇒ 净增 6 suites / 25 例，零新增失败）。5 个改动文件 Vite transform 全 **200**。

**🔴 spec 漏了两处必要接线（否则 E1-4 分支不可达 = 死代码）**

tasks.md 只说「`ftRowsKey` 的 sheet 分支加 `E1-4`」，但 E1-4 的「重新取数」按钮由 `showFtPanel` 控制显示、来源行由 `ftSources` 提供 ⇒ 只加 `ftRowsKey` 会得到「键有映射但按钮永不出现」的形态。三处必须同时加：

| computed | 改动 | 不改的后果 |
|---|---|---|
| `ftRowsKey` | `E1-4` → `E1-digital-rows` | 重新取数拿不到落库键，直接 return |
| `showFtPanel` | 数组加 `'E1-4'` | 四表取数面板不渲染 ⇒ 按钮不可达 |
| `ftSources` | `E1-4` → `fourTablePrefill.digital` | 面板里「来源科目」列为空 |

**零回归支点（Property 8）= `??` 而不是覆盖**：`buildBankSeedRowsFromAccounts(ap, variant) ?? buildBankSeedRows(p)` —— 账户级在 aux 无数据时返 `null` ⇒ 表达式回退叶子口径 ⇒ **产出与改造前逐字节相同**。变异 M1 把它换成叶子独占、另一条变异把 `??` 换成直接覆盖，两侧判据都会打红（后者会让「aux 空态清掉叶子种子」）。

**种子化与重新取数必须同口径**：两处若一处走账户级、一处走叶子，同一 sheet 会产出两套行 id（`-acct-` vs `-ft-`）⇒ 用户点「重新取数」后行数翻倍或数据错位。守卫对两个函数体施加**同一条**正则判据（变异 M8 只改 `reExtractFromFourTable` 一侧即打红）。

**守卫判据的三条形态约束**（每条都配了 fixture 自检，防判据空转）：

| 约束 | 为什么 |
|---|---|
| 用**圆括号配对**跳参数列表再取「第一个含语句特征的花括号块」 | `function f(): Promise<{ ok: boolean }> {` 的第一个 `{` 是**返回类型注解**，直接找 `{` 会把类型当函数体（memory 已记该坑，本轮 fixture 复现） |
| `computedArg()` 同时支持块体与**表达式体** | `showFtPanel`/`accountPrefill` 是 `computed(() => expr)` 无花括号，只写 `fnBody` 会返空串 ⇒ 断言在空文本上求值 = 又一种假绿 |
| 断言**函数名存在性本身**（`reExtractFromFourTable` ≥1 且 `refetchFromFourTable` == 0） | spec 写的是后者，按错名写守卫会静默空转（变异 M5 直接验证这条） |

**三段链判据**（缺任何一段都是 dead output）：后端 `_build_account_prefill` 下发 `"account_prefill"` → 宿主 `normalizeAccountPrefill(props.htmlData?.account_prefill)` → 写入 `allResponses` 的四个键 → **逐键断言它是某个消费方的 `STORAGE_KEY`**，并断言 `<E1TabDigitalCurrency>` 在模板里真收到 `:all-responses`（否则种子进不去）、`<E1TabBankDetail>` 真收到 `:variant`（两版共用持久化键，靠 variant 区分行模型）。

### Wave 3 实录之三：取数溯源面板扩展（Task 9，2026-08-08）—— Wave 3 收口

`e1/E1FourTableSourcePanel.vue` 新增 `accounts?: E1AccountPrefill` prop 与两块 UI（账户级取数溯源 + `unassigned` 告警），宿主按 sheet 门控传入。守卫 `__tests__/e1SourcePanelWiring.spec.ts`（**17 例全绿**）+ **变异检验 9/9 全 RED**。E1 前端回归 **107 files / 405 passed / 0 failed**（Task 8 时 102/388）。5 个文件 Vite transform 全 **200**。

**头号判据 = prop 键集交叉锁死**（从面板 SFC 的 `defineProps<{...}>()` **动态抽**合法 prop 名转 kebab、与宿主调用点属性求差集 + 断言必填 prop 真的传了）。理由：Vue 对「传了不存在的 prop」不报错（未知属性落到根元素当 HTML 属性）⇒ Volar 零诊断 / vitest 全绿 / Vite 200，**四层验证全查不出**而组件内部读到 `undefined` ⇒ 整块静默不渲染。平台已踩两次（G5 溯源面板从未渲染过 / G6 传 `report-row` 而真实 prop 是 `fallback-row-code`）。变异 M1（面板删 prop 声明）与 M2（宿主不传）各打红 2 条。

**面板内容三块**：①各槽勾稽表（账户级合计 vs 叶子合计 vs 差异，`ok` 决定 success/danger 分色，另有整块 `勾稽不平` danger tag）②账户明细表（语义槽 / 开户银行 / 账号 / 科目 / 币种 / 期末 / **解析级别 L1-L3** / **合并笔数**）③`unassigned` 告警（列出账号与金额 + 明确成因「辅助余额表里有这些账户，但科目语义定位未覆盖其科目码」+ 告知已计入 E1-10 供完整性核对）。

**`parsed_level` 作数据质量指标**：level 3（降级取辅助项名作账号）占比 ≥ 50% 时提示「请核对该客户导出的『辅助项组合』格式」。实测 10 个项目全为 `{'1': N}` ⇒ 该分支当前零命中（潜伏态），守卫用阈值源码断言 + 变异 M5 证明它可达。

**🔴 「未传 accounts」与「传了但账户为空」必须是两种状态**（变异 M6 专门验这条）：E1-2 现金 / E1-4 数字货币没有账户维度 ⇒ 宿主传 `undefined`，面板**完全不渲染**账户级块；E1-3 / E1-10 传了但 aux 无数据 ⇒ 显示「本项目无账户级明细，已退回叶子科目口径取数」。若把 `accountsEmpty` 写成只判 `accountCount === 0`，现金页会莫名多出一条「无账户级明细」的无意义提示。

**顺带修掉 Task 8 遗留的一处不可达**：面板 `v-if` 原含 `ftSources.length` ⇒ 叶子来源为空时面板不显示。新增 `ftHasAccountSource` 让「叶子空但账户级有数据」也显示（否则账户级溯源在那种情形下不可达）。**E1-4 面板当前仍不显示是正确的** —— `digital` 全库恒空是数据事实（该科目 `account_chart` 零命中），无来源就不显示取数面板属宁缺勿造；Task 8 加的 E1-4 分支是「机制就位」的潜伏态，客户一旦有数字货币科目即自动可见。

### Wave 4 实录 + Task 23（2026-08-09）

接手时复选框记 9/24（Task 10 记 `[ ]` 而 11 记 `[x]`），逐个探针后 **Task 10 经实测已完整交付**（复选框滞后）：`fix_e1_prefill_presets.py --check` **rc=0 / 0 项欠账**、E0 块已改名 `函证结果汇总表E0-1`+`wp_name=函证结果汇总表`、6 个新块（`(仅人民币)E1-3` / E1-6 / E1-10 / E1-21 / E1-22 / E1-23）全在库（E 类块 17→**23**）、`E1_SHEETS_WITHOUT_PRESET` 登记表与 8 条非数据表白名单齐备 ⇒ **Task 2 守卫的 2 条红已全部转绿**（`test_e1_preset_coverage.py` 17 例全过）。

**Task 12（四处 additive 修正）** —— 扩 `fix_note_e1_monetary_fund_structure.py`，`--dry-run` 逐条命中 6 处变更、`--apply` 后 `--check` **0 欠账**、**二次 apply 两份模板 md5 逐字节不变**（Property 15 幂等双证）：

| # | 修正 | 落点 |
|---|---|---|
| 1 | soe 主表首行 `现金` → `库存现金` | `MAIN_ROWS_SOE[0]` |
| 2 | soe 主表合计行后补 `其中：存放在境外的款项总额`（`row_type: data`，不标 `is_total`）| `MAIN_ROWS_SOE` |
| 3 | 两版②表合计行前补 `金融企业法定存款准备金或备付金`（前 5 类顺序不动）| `RESTRICTED_ROWS` |
| 4 | soe 八、92 短期借款段 `report_row_code` `BS-031` → `BS-041` | 新增 `_run_fx_row_code_pass` |

🔴 第 4 处需**新开一趟** —— 外币表在 `PLANS` 里传 `rows=None`（跨循环共享表，动行集会打断 D2/K/L），`run_section` 碰不到段首行 ⇒ 仿 `_run_xref_pass` 建独立 pass，且**只写 `report_row_code` 一个字段**（`account_codes:['2001']` 本来就是对的，脚本内 `assert` 钉死它没被误改）。

🔴 `GUIDANCE_RESTRICTED` **必须拆两份** —— 「listed 侧整张②表是平台补充表、依据镜像 soe docx」这条登记只对上市成立，共用一份会把它写进国企侧（那里 docx 确有该表）。现为 `GUIDANCE_RESTRICTED_LISTED`（500 字，含平台补充表登记）/ `GUIDANCE_RESTRICTED_SOE`（334 字，只含合计行偏离登记）。

**同时改写了脚本 docstring 的「改造前欠账」清单** —— 原文把「首行是库存现金」「境外款项行是假行」「②表多一行第 6 类」当作**要修的缺陷**记载（那是上一轮以底稿 xlsx 为真源得出的结论，已被 R5.8 推翻）。不改 docstring 的话下个会话会照它把这三处再改回去。

**Task 13（受限桶第 6 桶）** —— `e1_restricted_buckets.py` 新增 `statutory_reserve`（label `金融企业法定存款准备金或备付金`，声明在 `pledged_deposit` 之后、兜底桶 `other` 之前）。**零回归由真实库实证**：只读探针 `_wip_e_t13probe.py` 跑真实库 **212 个去重货币资金叶子科目名**，含新桶关键词的 **0 个**、分类结果差异 **0 条**（Property 21）。

🔴 **关键词必须含 `法定准备金`（不带「存款」二字的简写）** —— 首版按 spec 只写 `法定存款准备金`/`存款准备金`/`备付金`，守卫立刻打红：`存放中央银行法定准备金专户` 落到了兜底桶 `other`（被它的「专户」关键词吃掉）。客户实际命名有这种简写形态，故补该关键词并用同一形态做反向自检。

**派生段清单已重生成**（`gen_note_shared_table_segments.py --write`，29 张共享表）。Property 25 实测：两版 manifest 段序列 == 模板段序列；**soe 侧 `find_segment(rows,'BS-041')` 返非 None**（`start=10 end=15`）、`resolve_segment_window` 同值；两版 `find_segment(rows,'BS-031')` 均返 `None`（错配面已消除）。

**Task 23（展示序与优先级序分离）** —— 这是本 spec 修的一个**既存缺陷**：一份声明序同时承担「匹配优先级」与「附注行序」，而两者实际 **1↔2、4↔5 互换**（声明序 `信用证→银行承兑→履约→境外→质押`，docx 行序 `银行承兑→信用证→履约→质押→境外→法定准备金`），而前端推送排序用的正是桶数组下标 ⇒ **附注②表行序与 docx 不符**。

🔴 **落法与 design 初稿偏离一处（已核实必要）**：初稿写「`displayOrder` 按 `source_ref` 的单元格行号升序派生（现值 A17~A21，新桶 A22）」，但**第 6 桶的真源是 docx 不是 xlsx**（xlsx R17~R21 只 5 类、R22 是 `…` 动态插行标记），docx 行号（r6）与 xlsx 行号（A17~A21）不在同一坐标系，混排会把它排到最前。故展示序真源改为显式元组 `E1_RESTRICTED_DOCX_ROW_ORDER`（零新增 dataclass 字段），并**保留初稿的洞察作交叉锁**：五个 xlsx 源桶的元组顺序必须与其 `source_ref` 行号升序一致（两个独立口径互证）。→ **design.md Property 36 的第②条已同步改写**。

前端：`E1RestrictedBucketDef` additive 加可选 `displayOrder`（缺字段退化为数组下标 = 向后兼容旧 render 载荷）+ 新增 `bucketDisplayOrderMap()` 作排序键唯一入口。

**诚实改写的既有断言（本轮共 7 条，与真实回归分开列）**

| 文件 | 用例 | 改写理由 |
|---|---|---|
| `test_note_e1_structure.py` | `test_soe_main_rows_verbatim` → `test_soe_main_xlsx_has_five_rows_but_docx_has_six` | 原按 xlsx R8~R12 锁 5 行 |
| 同上 | `test_soe_first_row_is_cash_not_cash_on_hand` → `..._dual_wording_is_bridged_by_note_label` | 原断言模板首行必须是 `现金` |
| 同上 | `test_soe_has_no_overseas_data_row` → `..._is_real_in_docx_though_parenthetical_in_xlsx` | 原据 xlsx R13 括注把 docx 正式数据行判成假行 |
| 同上 | `test_restricted_rows_verbatim[listed/soe]` → `..._are_xlsx_five_plus_docx_sixth_plus_total`（2 条）| 原按 xlsx 锁 5 类 |
| 同上 | `test_restricted_excludes_reserve_row_and_ellipsis` → `..._sixth_category_comes_from_docx_not_xlsx` | 原断言两版**不得**有第 6 类 |
| `e1CurrencyScope.spec.ts` | `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` → `行序按 displayOrder（= 源 docx 行序）` | 标题声称的等价关系**本就不成立** |

🔴 **xlsx 事实一条没删，全部保留为「对照断言」** —— 它们现在证明「两侧差异真实存在且是有意的」（同 `TestProperty41VariantAsymmetryIsIntentional` 的范式），而不再用来约束附注模板行集。

🔴 **`e1CurrencyScope.spec.ts` 的 `DEFS` 样本此前按 docx 序排列，恰好让「按数组下标排序」的旧实现也能通过 ⇒ 掩盖了该缺陷**。现把样本改成复现后端**真实声明序**（`letter_of_credit` 在前）+ `displayOrder` 复现 docx 序，并加一条反向自检（去掉 `displayOrder` 时行序退化成数组下标 = 复现旧缺陷形态）。→ **凡「按某数组顺序」的断言，其 fixture 顺序必须复现真实真源顺序，否则断言恒真**。

**顺带记：并发会话已修掉 Property 30 的一处过期断言（2026-08-09 12:54，非本会话）**。原判据「全库 `row_type` 取值域恰为 5 值」在 C spec（`note-template-columns-and-legacy-snapshot-closure` R11，已 23/23）正当落地第 6 个取值 `expandable` 后变成假红（全库 121 行，其中外币表 9 行正是源模板 `可无限量添加行`/`……` 的位置）。现改为「⊆ 六值，且第 6 个取值**从 C spec 的 service 层 import**」（跨 spec 交叉锁死）+ 保住自律部分「E1 自己负责的主表与②表内不得出现 `expandable`」。

**验证**：后端 `test_note_e1_structure` + `test_e1_restricted_buckets` + `test_e1_preset_coverage` = **175 passed / 1 failed / 1 skipped**，唯一失败是 `test_payload_projects_soe_first_row_to_docx_label`（Task 15 的 `noteLabel` 尚未实现，属预期红）；受限桶守卫 36 → **78 例**。前端 `vitest run e1 E1` = **21 files / 412 passed / 0 failed**。

### 实证基线（2026-08-08，只读零改动）

- 真实库 8 项目 `parent_check`「叶子和 == 父额」**8/8 全部成立**
- 既有 E1 守卫 **132 passed**；`fix_note_e1_monetary_fund_structure` / `fix_e1_prefill_presets` **`--check` 0 欠账**；`fix_e1_orphan_sheet_presets` 欠账为 0 但 **rc=1**（emoji 崩）
- `account_chart` 对「数字货币 / 数字人民币 / 财务公司」**全库 0 命中** ⇒ `digital` / `finance_co` 两槽 8 项目全 `found=False` 是数据事实
- `tb_aux_balance` `aux_type='银行账户'`：全库 **114 个账户名**；带 `get_active_filter` 后与 `tb_balance` **逐分勾稽成立**（8 项目 × 全部科目 `1002`/`1012.02`/`1012.03`/`1012.04`/`1012.11.03`）
- E1-3 源模板列：A 开户银行 / B 总账银行名称 / C 银行账号 / D 账户性质·主要用途 / E 原币币种 / F 期末汇率 / G~T 未审数（两级）/ U~X 审计调整 / Y~AB 审定数 / AC~AF 对账单与回函 / AG~AI 索引号 / **AJ 受限金额 / AK 受限原因** / AL 利率 / AM 备注
- E1-3 分段：（一）存款本金［银行 r12·r13-17 / 其他金融机构（存放财务公司款项）r18·r19-21 / 其他货币资金 r22·r23-28 / 小计 r29］+（二）应计利息［r31-41］+ 银行存款小计 r42 / 财务公司存款小计 r43 / 其他货币资金小计 r44 / 合计 r45 / 其中：存放在境外的款项总额 r46

### 立项时被实证推翻的判断（勿再照错的走）

1. **「24 个子 Tab 无 `htmlData` prop ⇒ 四表预填是 dead output」是错的** —— E1 架构是宿主种子化进 `allResponses`，子 Tab 经既有通道读，链路是通的
2. **「外币段 `owner_row_code` 全为 None ⇒ E1 外币推送从未成功」是错的** —— 段字段名是 `row_code`，探针读错了字段；`find_segment(rows, code)` 第一参是模板 rows 不是 segments 列表
3. **「soe 受限表『金融企业法定存款准备金或备付金』是自造行」是错的**（前一轮据源 xlsx 删掉了它）—— 附注源 docx **确有**该行，附注结构真源是 docx

### 三件套审查轮被实证推翻的 spec 自身判断（2026-08-08，只改文档零改代码）

| # | spec 初稿写的 | 实证事实 | 后果 |
|---|---|---|---|
| 1 | `get_active_filter(db, table, pid, year)` | 它是 **`async def`**（`app.services.dataset_query`）| 漏 `await` → `sa.and_(coroutine,…)` 抛异常 → fail-open 吞成 warning → 清单恒空且与「无数据」不可区分。N5/D 循环各因此出过 P0 ⇒ 新增 Property 39 源码守卫 |
| 2 | 宿主 `refetchFromFourTable()` | 真名 **`reExtractFromFourTable`**（前者命中数 0）| 按 spec 名写守卫会静默空转 ⇒ Task 8 加「函数名存在性」断言 |
| 3 | 「`multi` 版下发原币/汇率字段」 | `tb_aux_balance` 只有 `opening_fc` 且 `银行账户` 维度下**全 NULL**，**无 `closing_fc`、无汇率列**，308 行 `currency_code` 全 `CNY` | 原币金额与汇率**无数据源** ⇒ 只能下发 `fxCurrency`，其余留空；外币提示分支当前 0 命中 = 潜伏态（R1.9/R1.10 重写）|
| 4 | Property 20「受限表行序 == docx r1~r6」 | 平台兜底桶 `other 其他受限资金`（`source_ref=None`）在 docx 与模板行集里**都无对应行**但推送时会出现 | 照原判据会把正确实现打红 ⇒ 改为「docx 六类 + 平台桶 + 合计」（R6.8）|
| 5 | 「两版受限表补第 6 类（源 docx soe r6）」 | **listed docx 该处只有 1 张主表 + 两段文字，没有受限表** | listed 侧无 docx 依据 ⇒ 登记为有意偏离（平台补充表镜像 soe），且禁写「与 listed docx 三向一致」的断言（R6.6 / Property 37）|
| 6 | —（未察觉）| **受限桶声明序 ≠ docx 行序**（1↔2、4↔5 互换），而前端推送排序用的正是 `bucketDefs` 数组索引 | **附注行序与 docx 不符**（既存缺陷）；既有用例标题 `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` 声称的等价关系本就不成立 ⇒ 新增 Task 23 分离两序 + 诚实改写该用例 |
| 7 | R2 只讲明细表与 E1-4 种子 | `E1_MAIN_ROWS_LISTED` 三个 `crossKey: ''` 行注释明写「由 render 的语义槽预填」而**零实现** | 又一处「未兑现的承诺」，且比明细表更直接影响交付件 ⇒ 新增 Task 24 / Property 35（R2.6/2.7）|
| 8 | Task 2「11 个 sheet 既无预设也无登记」；R3.3 列 7 张 E1 + E0；Task 10 写「8 张 E1」 | 实测 visible **44** / 有预设 **17** / 真实缺口 **19**（含 spec 两份清单都漏掉的 **`(仅人民币)E1-3`**，它是真数据表）；且判据若按「每个 visible sheet」会把 5 个 `底稿目录` + 3 张 `*A` 程序表算进去 | 数字互相矛盾且判据会产生 8 条噪声 ⇒ R3.7~R3.10 + Property 40（白名单 + 基线冻结 + 命中数自检）|
| 9 | Task 15 只说「补 overseas 行」 | 会打红 **3 条**既有断言（`toHaveLength(5)` / `sourceRef` 序列 / `overseas` 不存在于 soe，后者注释写「源 xlsx R13 是括注文字」）| 需显式登记诚实改写 + 写明「附注行集真源是 docx 不是底稿 xlsx」（R5.8 / Property 41）|
| 10 | design 依赖表「D 依赖 A（账户级受限金额）」 | `tb_aux_balance` **没有受限金额字段**，L2 读的是 E1-3 手填的 `restrictedAmount`/`restrictedReason`（AJ/AK 列，早在 `USER_FIELDS` 里）| 依赖关系写错 ⇒ Wave 5 只依赖 Task 4，不被 Wave 2/3 阻塞（R8.8）|
| 11 | Task 14「归集成 ②表行」 | 既有契约钉死②表只 3 列、`reason` 走 `_note_texts` | 加第 4 列会打红既有断言 ⇒ R8.7 / Property 38 明确原因文本落 `_note_texts` |
| 12 | Task 12「走 rule aliases 改名」 | `rule(name, cols, rows, guidance, aliases=None, *, insert=False,…)` 的 **`guidance` 是必填位置参数** | 只改行集时必须原样传回既有 guidance，否则 guidance 与三向比对同时漂移 |

**结构性校验（改后）**：AC **81** 条 / Property **41** 条（1~41 无缺号无重号、`Validates` 行数 == Property 数、编号升序）/ 悬挂引用 **0** / 未被引用 AC **0** / 任务 **24** / waves ≡ 复选框。

### soe 与 listed 主表行集不对称（docx 事实，勿对齐）

| listed docx（8 行）| soe docx（6 行）|
|---|---|
| 库存现金 | 库存现金 |
| 银行存款 | 银行存款 |
| **存放财务公司款项** | —（无）|
| 其他货币资金 | 其他货币资金 |
| **存款应计利息** | —（无）|
| 数字货币 | 数字货币 |
| 合  计 | 合  计 |
| 其中：存放在境外的款项总额 | 其中：存放在境外的款项总额 |

⇒ `finance_co` 槽（Task 5 扩槽 + Task 24 预填）在 **soe 附注无落点**，这是准则口径差异不是缺陷。

### 已核实无需改动（防「顺手纠正」）

| 项 | 结论 |
|---|---|
| listed 外币章节号 `五、73` | 正确（第五章 74 子节、外币第 73 个）；docx 正文「五、81」是 docx 自身陈旧交叉引用 |
| 外币表两版段数不对称（listed 3 / soe 5）| 源 docx 事实，不得对齐 |
| 附注 `合计` / `项目` 字面 | 符合平台惯例（listed 248/192、soe 160/130 主流）|
| 全零账户被金额明细过滤 | 设计如此（账户清单保留是完整性核对红线）|
| listed 五、1 主表 8 行 | 与 docx 一致 |

### 范围外（登记不做）

- 附注 `row_type` 新增 `expandable` → 归 `note-template-columns-and-legacy-snapshot-closure` R11（该 spec 21/23）
- 外币表扩列（4 → 7 列）→ 跨循环共享表，波及 D2/K/L，需平台级 spec
- 银行账户完整性三方比对（四表 ∪ 央行清单 OCR ∪ E0-3 回函）→ 涉 OCR 数据源，够独立 spec
- `trial_balance` 父子双算 → 平台级缺陷，E1 已用叶子口径规避
- E1 孤儿组件接线 → 归 `e1-orphan-components-wiring`
- E0 发函清单专属组件 → 归 `e0-send-list-dedicated-components`
- 存量项目附注回填 → 模板改动只对新建/重新生成生效

### Wave 6 实录之一：变异检验 20/20 全 RED（Task 20，2026-08-10）

产出 `backend/scripts/diagnose/mutate_e_cycle_guards.py`（`--list` / `--check-anchors` / `--run all|be|fe|M01,M02` / `--restore` / `--out`）。**锚点自检 20/20 OK，变异结果 20 RED / 0 GREEN / 0 WRONG-TEST / 0 ANCHOR-MISS**。

**冻结基线（本轮亲测，与记载有差异）**

| 范围 | 本轮实测 | tasks.md 原记载 |
|---|---|---|
| 后端 `backend/tests/four_table -k "e1 or e_cycle"` | **368 passed / 1 skipped / 1704 deselected / 0 failed** | Task 15 实录写 **358 passed** |
| 前端 `vitest run e1 E1` | **136 suites / 563 passed / 0 failed**（`numFailedTestSuites=0`） | Task 24 实录写 23 files / 483 passed |

⇒ 基线以本轮实测为准（差 10 例，系 Wave 5/6 期间守卫增量）。两侧失败测试名集合均为**空集**，故差集判定可信。

**变异结果（逐条）**

| 变异 | 侧 | 目标文件 | 判定 | 命中的守卫 | 新增红 |
|---|---|---|---|---|---|
| M01 裸 `is_deleted == False` 替代 `get_active_filter` | be | `e1_bank_accounts.py` | RED | `test_no_naive_is_deleted_filter` | 4 |
| M02 去掉按账号聚合（`key=(code, object())`）| be | 同上 | RED | `test_same_account_two_rows_are_summed` | 3 |
| M03 `_f` 的 NULL 归零改返 NaN | be | 同上 | RED | `test_null_amounts_are_coalesced_to_zero` | 1 |
| M04 解析失败时把账号臆造成银行名 | be | 同上 | RED | `test_bank_name_is_never_the_account_no` | 3 |
| M05 `unassigned` 改塞进 `bank` 槽 | be | 同上 | RED | `test_unrelated_code_goes_to_unassigned_not_dropped` | 5 |
| M06 勾稽 `diff` 恒 0（自动修正而非暴露）| be | 同上 | RED | `test_mismatch_is_exposed_not_corrected` | 2 |
| M07 新受限桶挪到兜底桶 `other` 之后 | be | `e1_restricted_buckets.py` | RED | `test_declared_before_fallback_bucket` | 3 |
| M08 新受限桶关键词加「保证金」 | be | 同上 | RED | `test_classification_unchanged_by_new_bucket[投标保证金]` | 2 |
| M09 soe 主表首行改回底稿字面「现金」 | be | `note_template_soe.json` | RED | `test_template_soe_main_matches_docx` | 3 |
| M10 外币表短期借款段 row_code 改回 `BS-031` | be | 同上 | RED | `test_row_code_row_name_matches_segment_label[soe]` | 1 |
| M11 幂等脚本 print 加回 GBK 不可编码字符 | be | `fix_e1_orphan_sheet_presets.py` | RED | `test_print_literals_are_gbk_encodable` | 1 |
| M13 去掉 `await get_active_filter` | be | `e1_bank_accounts.py` | RED | `test_get_active_filter_is_awaited` | 3 |
| M14 `displayOrder` 回退成声明序数组索引 | be | `e1_restricted_buckets.py` | RED | `test_payload_carries_display_order` | 1 |
| M15 打乱声明序（`overseas` ↔ `pledged_deposit`）| be | 同上 | RED | `test_classification[境外冻结存款-overseas]` | 1 |
| M20 非数据表白名单混入不存在的 sheet 名 | be | `fix_e1_prefill_presets.py` | RED | `test_non_data_whitelist_is_effective` | 1 |
| M12 E1-3 种子行 id 前缀改成与叶子口径相同 | fe | `e1BankAccountPrefill.ts` | RED | Property 7「账户级 id 与叶子口径无交集」 | 2 |
| M16 删掉 `E1_MAIN_ROW_SLOTS` 的 `finance_co` 键 | fe | `e1MainRowPrefill.ts` | RED | 「键集完全一致且字典序冻结」 | 15 |
| M17 删掉 `isBlankPeriod` 短路（三值全 0 也写键）| fe | 同上 | RED | 「三值全 0 的行不产生写入」 | 6 |
| M18 ②表加第 4 列 `reason` | fe | `e1NoteSectionMap.ts` | RED | Property 38「②表不推受限原因列」 | 3 |
| M19 非本位币汇率由本位币反推填 1 | fe | `e1BankAccountPrefill.ts` | RED | Property 34「原币与汇率一律留 0」 | 1 |

四条任务原文点名的专用变异**全部验到**：M13（去 `await`）· M14（`displayOrder` 回数组索引，展示序红 / 分类绿）· M15（打乱声明序，分类红 / 展示序绿）· M16（删主表预填链，Property 35 红）。M14 与 M15 的**互补性**成立 —— 前者只红载荷展示序、后者只红分类，证明两序确已分离（Task 23 的核心断言）。

**🔴 首轮跑出 3 条非 RED，逐条查实全是变异脚本自身缺陷，不是守卫缺陷**

| # | 首轮判定 | 根因 | 处置 |
|---|---|---|---|
| M03 | GREEN | `_f()` 里 `if v is None: return 0.0` **下方还有** `except (TypeError, ValueError): return 0.0`。删掉前者，`float(None)` 抛的 TypeError 被后者兜住 ⇒ 返回值逐字节相同 = **双层防御让变异自我抵消** | 改成返 `float("nan")`，真正破坏 COALESCE 语义 ⇒ RED |
| M15 | GREEN | 原选 `letter_of_credit` ↔ `bank_acceptance`，但两桶关键词（`信用证` / `银行承兑`）**无交集**，换序不改变任何分类结果 = **无效变异** | 改换 `overseas` ↔ `pledged_deposit`（守卫自带的 `test_reverse_selfcheck_overseas_after_pledged_breaks` 已指明这才是敏感桶对）⇒ RED |
| M14 | WRONG-TEST | 变异只改 `bucket_defs_payload`，而 `test_display_order_matches_docx_six_categories` **直接调 `display_order_of()` 绕过载荷**故不红；实红的是同属 Property 36 的 `test_payload_carries_display_order` | `want` 改锚到载荷断言 ⇒ RED |

**这三条正是「无效变异」判别的实例**：变异必须真的改变被测属性。判据是「改完行为变了吗」，不是「改完源码不一样了吗」。

**顺带修掉变异脚本两处工具坑**

1. **失败名撞名** —— 原按 `nodeid.split("::")[-1]` 取末段，而 `test_strip_comments_is_not_a_noop` 在 `test_e1_bank_accounts.py` 与 `test_e1_render_account_prefill.py` **两文件同名** ⇒ 差集判定会把另一文件的同名测试误认成已知失败。改为收**全 nodeid**（`文件名::类::方法`），`want` 命中判定同时支持末段前缀匹配与全名子串匹配（吃掉 parametrize 后缀）。
2. **vitest `--outputFile` 静默失效** —— `subprocess.run([...], shell=True)` 在 Windows 下把 list 参数交给 `cmd`，`--outputFile=` 被 npm 自己吞掉，**JSON 从未产出**且 rc=0（表现为「基线非空 → ABORT」，极易误判成守卫坏了）。改用 `cmd /c "npm exec vitest run ... --outputFile=\"...\""` 单串形式 ⇒ 正常产出 201 KB JSON。

**四态判定实现**：`RED`（新增失败非空且含 `want`）/ `WRONG-TEST`（非空但不含 `want` = 污染残留或锚点错行）/ `GREEN`（空 = 守卫缺陷或无效变异）/ `ANCHOR-MISS`（锚点命中数 ≠ 1，或变异后 md5 未变）。另有 `ERROR` 态记录异常。备份落 `.mutbak` + 还原进 `finally` + 还原核验用「与变异前 md5 逐字相同」+ 开跑前扫残留备份即 ABORT。**收尾 `--restore` 报告 0 个备份文件 ⇒ 零残留**。

**锚点落法要点**（CRLF 工作树下的实战约束）：全部单行锚点，`hits != 1` 即 ANCHOR-MISS。三处必须**行号消歧**：M03（`return 0.0` 在 `_f` 内出现 2 次，锚 L157）· M09（`"label": "库存现金"` 在 listed/soe 两份模板各 1 次，只改 soe）· M19（`base.fxRate = 1` 在 foreign/else 两分支各 1 次，锚 foreign 侧 L291）。M07 用 `move`、M15 用 `swap`，两者按 `E1RestrictedBucket(` 括号配对截块，不用固定行数窗口。

**🔴 M09/M10 的变异目标是数据文件不是脚本常量** —— 守卫 `test_note_e1_structure.py` 读的是 `backend/data/note_template_{listed,soe}.json`，改 `fix_note_e1_monetary_fund_structure.py` 里的 `MAIN_ROWS_SOE` / `FX_ROW_CODE_FIXES` 常量**不会**打红任何测试（脚本不跑就不影响数据）。这也印证了「变异目标必须是生产代码/数据」这条判据的必要性。

### Wave 6 实录之二：真实库验收（Task 21，2026-08-10）

**账户级取数：`verify_e1_account_extraction_live.py --all-projects` = 10/10 全 OK、diff 全 0.00、结论 PASS**，与 Task 6 实录基线逐条相同（`0ec33ac9:2025`=22/4,703,056.26 · `12c15a96:2025`=22/同 · `2aa00f57:2024`=23/848,871.86 · `2aa00f57:2025`=17/327,095.20 · `4f6dbc36:2025`=2/4,048.93 · `52c04ed1:2025`=21/1,272,030.63 · `a7fc75e5:2025`=38/−297,771,168.89 · `b39809ed:2025`=6/0.00 · `c8621493:2025`=1/110.30 · `f064f5e4:2024`=23/848,871.86）。`parsed_level` 分布 10/10 全为 `{'1': N}`。

**🔴 独立 SQL 交叉核对（经 postgres MCP 直连，完全不经被测代码）** —— 任务原文要求「不拿被测函数证明自己」。验收脚本虽绕开了 `fetch_e1_bank_accounts`，但它的「独立 SQL」列仍共用 `get_active_filter`，故另跑一组**裸 SQL 显式锁 `dataset_id`**：

| 项目:年度 | 裸 SQL 账户数 | 裸 SQL aux 合计 | `tb_balance` 1002 叶子 | diff |
|---|---|---|---|---|
| `0ec33ac9:2025` | 22 | 4,703,056.26 | 4,703,056.26 | 0.00 |
| `12c15a96:2025` | 22 | 4,703,056.26 | 同 | 0.00 |
| `2aa00f57:2025` | 17（raw 19）| 327,095.20 | 同 | 0.00 |
| `4f6dbc36:2025` | 2 | 4,048.93 | 同 | 0.00 |
| `52c04ed1:2025` | 21 | 1,272,030.63 | 同 | 0.00 |
| `a7fc75e5:2025` | 38（raw 39）| −297,771,168.89 | 同 | 0.00 |
| `b39809ed:2025` | 6 | 0.00 | 同 | 0.00 |
| `c8621493:2025` | 1 | 110.30 | 同 | 0.00 |
| `f064f5e4:2024` | 23 | 848,871.86 | 同 | 0.00 |
| `2aa00f57:2024` | 23 | 848,871.86 | 同 | 0.00 |

**M01 变异对应的缺陷在真实数据上被证实**（不是理论假设）—— `0ec33ac9:2025` 的 `1002` 维度：

```
裸查（不锁 dataset）   : 23 账户 / 9,406,222.82 / 45 行
锁 active dataset      : 22 账户 / 4,703,056.26 / 22 行
```

金额**几乎正好翻倍**（差 110.30，因 superseded 里多一个账户）。该项目有 1 个 active + 4 个 superseded + 1 个 failed dataset，裸查会把 superseded 的行一起算进来。⇒ `get_active_filter` 不是形式主义，是防止合计翻倍的必要条件。

**🔴 查出验收脚本一处覆盖面缺口（非缺陷但需登记）** —— 脚本传 `account_prefixes=["1002"]`，而生产 render（`_e1_monetary_fund._build_account_prefill` L393）传的是 `_ACCOUNT_SLOT_KEYS`（`bank` + `other` + `finance_co`）三槽 `slot_codes` 的**全展开**，实际覆盖 `1002` **和** `1012.x`。补验 `other` 槽 14 个「项目×科目」：

| 科目码 | 覆盖项目数 | 账户数合计 | diff |
|---|---|---|---|
| `1012.02` | 5 | 28 | 全 0.00 |
| `1012.03` | 2 | 2 | 全 0.00 |
| `1012.04` | 4 | 6 | 全 0.00 |
| `1012.11.03` | 3 | 8 | 全 0.00 |

全部 diff = 0.00 ⇒ 生产口径同样成立。**登记**：脚本只是验收覆盖面比生产窄（`1002` 是最大科目、勾稽逻辑同一条），不影响结论有效性；若日后扩展该脚本，`account_prefixes` 应改从 `E1_MONETARY_FUND_SPEC` 反解而非写死。

**M02（按账号聚合）的真实数据前提被证实** —— active dataset 内确有同账号多行：`2aa00f57:2025` 两个账号各 2 行（`3100021509024876090` / `346030100100631215`）· `a7fc75e5:2025` 一个账号 2 行（`1207014210004455`）· `52c04ed1:2025` 的 `1012.02` raw 7 行 / 6 户。⇒ 不聚合会虚增账户数并破坏勾稽。

**🔴 `2aa00f57:2024` 走 legacy 口径（dataset_id IS NULL）** —— 该「项目×年度」在 `ledger_datasets` **无任何行**，aux 数据的 `dataset_id` 为 NULL。我最初的裸 SQL 用 `JOIN ledger_datasets ... status='active'` 只出 9 行、漏了它；`get_active_filter` 能覆盖是因为它有 legacy 回退路径。按 NULL 口径补验：23 户 / 848,871.86，与 `tb_balance` 叶子逐分一致 ⇒ 10/10 全覆盖成立。**这条是 `get_active_filter` 相对裸查的第二个必要性理由**（除防翻倍外还要兼容无 dataset 的历史数据）。

**`unassigned` 明细**：10/10 项目全为空（`acct_cnt == 独立SQL` 逐项相等即证）。`parsed_level` 全库 244 行**全是 level1**（两维度齐全），降级路径零命中 ⇒ level 2/3 分支是**潜伏态**（守卫 `test_level3_falls_back_to_aux_name` 等用构造数据覆盖，M04 变异对它打红证明判据非空转）。

**附注侧幂等脚本 `--check` 三个全 0 欠账、rc 全 0**：

```
fix_note_e1_monetary_fund_structure.py --check
  上市 五、1 货币资金 / 国企 八、1 货币资金 / 上市 五、73 外币 / 国企 八、92 外币
  → 四节逐条「= 已对齐（幂等空操作）」；--check：0 项欠账
fix_e1_orphan_sheet_presets.py --check   → [OK] 0 欠账（9 blocks 已全部就位）
fix_e1_prefill_presets.py --check        → --check: 0 项欠账
```

四个章节**逐条报「已对齐」而非静默跳过** —— 这是「0 欠账」与「没查」的区分点。

**python-docx 独立复核四处修正 = PASS（29 项判据全 OK）**，直读源 docx 与模板 JSON 双向比对：

| 修正 | docx 侧实证 | 模板侧实证 |
|---|---|---|
| 1+2 soe 主表首行 + 境外备忘行 | 6 行 `['库存现金','银行存款','其他货币资金','数字货币','合  计','其中：存放在境外的款项总额']` | 6 行、首行 `库存现金`、行序与 docx 一致（空白归一后） |
| 3 受限表 6 类 | 6 类无合计行，行序 = `银行承兑→信用证→履约→担保定期→境外→法定准备金` | 7 行（6 类 + 平台补充 `合计`），前 6 行与 docx 逐字一致 |
| 4 外币段 row_code | — | soe 八、92 短期借款段 `BS-041`、`account_codes=['2001']` 逐字不变；两版均已无 `BS-031` |

同时验到 Property 37（listed docx 货币资金节**只有 1 张表** ⇒ listed 受限表确属平台补充）与两版行集不对称（listed docx 主表 8 行含 `存放财务公司款项`/`存款应计利息`，soe 6 行无 ⇒ `finance_co` 在 soe 无落点是准则差异）。

**🔴 复核探针首轮 2 条 FAIL 均为探针判据缺陷，用既有守卫反证后修掉**（不是真缺陷）：

| 首轮 FAIL | 根因 | 反证依据 |
|---|---|---|
| 「模板 soe 主表行序 ↔ docx 逐字一致」 | docx 合计行字面是 `合  计`（**双空格**），模板是 `合计`。我的比较缺空白归一 | 既有守卫 `test_total_label_matches_template` 明写「模板是 `合计` 无空格，不套平台的 `合 计`」⇒ 差异是有意的 |
| 「listed 外币表应有短期借款段」 | listed 侧**本就没有**短期借款段（段序 = 货币资金/应收账款/长期借款） | 既有守卫 `test_fx_segment_counts` 实证「listed 3 段 / soe 5 段，两版不对称是源 docx 事实」⇒ 修正 4 只针对 soe 八、92 |

**这两条是「守卫把错值当基线锁死」的反面案例** —— 新写探针时若不先查既有守卫的口径裁决，很容易把「有意的不对称」当成缺陷去"修"，反而打破正确状态。

**被推翻的立项判断（本轮新增 1 条）**

| spec/任务原文写的 | 实证事实 | 处置 |
|---|---|---|
| Task 21「跑 Task 6 的脚本覆盖全部 **8 项目**」 | 实为 **10 个「项目×年度」**（`2aa00f57` 与 `f064f5e4` 各有 2024/2025 两个年度）；且其中 `2aa00f57:2024` 无 `ledger_datasets` 行、走 legacy `dataset_id IS NULL` 口径 | 覆盖面按「项目×年度」计 10/10；legacy 口径必须一并验（裸 SQL 若只 JOIN active dataset 会静默漏掉它）|

### Wave 6 实录之三：浏览器实测抓到一处真实缺陷并修复（Task 22，2026-08-10）

**实测环境**：后端 `:9980`（146 迁移 / schema_drift 0）· 前端 `:3030` · admin/admin123 ·
底稿路由 `/projects/{projectId}/workpapers/{wpId}/edit`（🔴 `/workpapers/{wpId}` 会 404）。

#### 🔴 抓到的真实缺陷：Property 28 端到端失效（本轮已修）

**现象**（soe 项目 `2aa00f57`，真实浏览器点击 + 库侧独立查询取证）：

| 步骤 | `-restricted-seq` remark | 落库行 id | 判定 |
|---|---|---|---|
| 新增「测试类别甲」 | `2` | `restricted_custom_测试类别甲_2` | — |
| 删除该行 | `2`（保留，正确） | 行数 0 | — |
| 新增「测试类别乙」 | `3`（正确递增） | `restricted_custom_测试类别乙_`**`2`** | 🔴 **复用已删序号** |

计数器本身完全正常，坏的是 **id 生成没用它**。

**根因**：`e1RestrictedScope.resolveRestrictedRows` 末尾
`.map(([bucketKey, amt], i) => ({ id: e1RestrictedRowId(bucketKey, i) … }))`
用**数组下标 `i`** 重算全部行 id，把 `addRestrictedRow` 里 `nextRestrictedSeq` 算好的稳定
序号**覆盖**掉；而 `saveAll` 序列化的正是这个 computed ⇒ 落库是被覆盖后的值。
第一次新增「看起来对」是巧合 —— 当时下标恰好也等于 2。

**为什么原有 46 例守卫全绿而缺陷仍在**：`e1RestrictedSeq.spec.ts` 既测了
`nextRestrictedSeq` 纯函数（返回 4，正确），也测了 `resolveRestrictedRows` 的行序，
但**没有一条断言把两者串起来** —— 即「经过 `resolveRestrictedRows` 之后，新增行的 id
是否仍等于 `nextRestrictedSeq` 给的那个」。属 memory 假绿第一源
「additive 注入即死代码」的变体：**注入点在、消费方在、结果被下游覆盖**。

**为什么 Task 23 的守卫也没拦住**：Task 23 拆分了「展示序 vs 匹配优先级」两个语义，
但漏了第三个 —— 同一个 `i` 在那行 `.map()` 里**同时**承担「排序位次」与「id 序号」。
拆分不彻底 ⇒ 同一处设计债留了个尾巴。

**修法**（生产代码 1 处 + 守卫 1 处）：
- `e1RestrictedScope.resolveRestrictedRows`：先由 `existingRows` 建
  `idByBucket: Map<bucketKey, id>`，输出时 `idByBucket.get(bucketKey) ?? e1RestrictedRowId(bucketKey, i)`
  —— **已持久化行的 id 原样保留**，下标只作**新桶**（四表新归集出来、还没有 id 的行）兜底。
- `e1RestrictedSeq.spec.ts` 新增 describe「E1 受限表序号端到端（Property 28 落库口径）」共 5 例：
  ①核心（删除后再新增 id 不复用）②不得改写 existingRows 已有 id（传 seq=9、下标=0 的行）
  ③与四表行混排时自定义行仍保序号 ④反向自检（复现缺陷实现证明判据非空转）
  ⑤源码级（id 表达式必须先查 `idByBucket`）。

**修复后真实链路复测**（同一项目，页面 reload 加载新代码）：

| 步骤 | 计数器 | 落库 id | 判定 |
|---|---|---|---|
| 删「测试类别乙」 | `3` | 行 0 | — |
| 新增「测试类别丙」 | **`4`** | `restricted_custom_测试类别丙_`**`4`** | ✅ 不复用 |

**变异检验**：交付物脚本新增 **M21**（`--run M21`），锚点
`      id: idByBucket.get(bucketKey) ?? e1RestrictedRowId(bucketKey, i),` → 复现缺陷形态。
判定 **RED**（6.3s，还原 True），新增失败 **5 条恰为新写的 5 例**、`gone` 空集
（无 WRONG-TEST 混入），精确命中 want。冻结基线 `BASELINE_FE_PASSED` 563 → **568**。

🔴 **写守卫时自己踩的坑（ANCHOR/判据类）**：源码级断言首版写成
「禁止 `e1RestrictedRowId(bucketKey, i)` 出现」→ 把**正确实现**判红了
（新桶 fallback 合法需要它）。行为级 4 条全绿、只有这条自造判据红 ⇒ 是
「守卫把对值当错值」。改判据为「id 表达式必须先查 `idByBucket`，下标仅作兜底」后 51/51 绿。
**教训**：源码级判据要锚「必须有什么」，不要锚「不许出现什么」—— 后者容易把合法兜底路径误伤。

#### 已验通过的判据（逐条实测）

- **E1-3 两 variant**：溯源块 29 户 · 勾稽 diff 全 `-` · 零余额账户保留 ·
  multi 版原币/汇率列存在且本位币显「人民币 / 1」
- **E1-10**：共 29 行、含零余额、同账号跨科目未去重、完整性面板 29/0/0/无账外
- **E1-4**：无取数面板、1 空行、合计全 `-`（「本项目无此科目」口径）
- **soe 披露主表**：6 行含 `其中：存放在境外的款项总额`，首行「现金」
- **②受限表展示序**：`银行承兑汇票保证金 → 信用证保证金 → 测试类别丙 → 合 计`
  —— 自定义类别追加在声明类别之后，展示序与 docx 一致（Task 23 修复在真实链路成立）
- **待归类面板分两区**：「未分户的父科目行」1 项（`1002 银行存款`），与真明细行分开渲染
- **新增受限类别必须先输名称**：`ElMessageBox.prompt`「新增受限项目」实测弹出（动态行命名铁律）
- **推送后附注 `八、1` 落 6 行**：`库存现金/银行存款/其他货币资金/数字货币/合计/其中：存放在境外的款项总额`
  ✅（tasks.md 原判据）
- **外币段他段行保留**：`八、92` 两个项目推送前后 md5 均 **SAME**（`85f3ddcb` / `9952b9d5`），
  5 段 25 行完整（BS-002 货币资金 / BS-006 应收账款 / BS-041 短期借款 / BS-061 长期借款 / BS-062 应付债券）

#### 立项判断被实测推翻（勿再照错的走）

1. **🔴「`0ec33ac9`（listed，22 账户）」判断错误** —— 该项目 `template_type='listed'`，
   但 `projects.applicable_standard_v2.entity_type='soe'`，**运行态准则读后者** ⇒ listed 披露 Tab
   显示「当前项目不适用上市公司附注披露」。**全库 8 个真实项目 entity_type 全为 soe，
   无 listed 准则项目** ⇒ Task 24 的 listed 三行预填**无法在真实项目上浏览器实测**，
   只能靠 vitest 守卫（全绿）+ 源码级证据。Task 22 因此**转用 soe 侧**验证。
2. **附注 `八、1` 基线是 5 行不是 6 行** —— 库里 `0ec33ac9` 的推送记录是 **2026/7/27**
   （Task 15 补 `overseas` 行**之前**），`is_stale=True`。6 行判据靠本轮 soe 侧**重新推送**验证成立。
3. **保存披露表会连带触发附注同步** —— 状态条时间戳与「新增类别」时刻一致，
   不必单独点「同步到附注」。⇒ 交互测试会改动 `disclosure_notes`，**必须纳入复原范围**。
4. **`2aa00f57 / 八、1` 是 legacy `{headers, rows}` 形态**（`_legacy_row: True`），
   而 `0ec33ac9 / 八、1` 是 `sub_table_data` 形态。两种形态在库里并存，复原须按 md5 全文而非结构。

#### 数据复原（逐字节 + 第三方独立核对）

复原脚本 `_wip_e_t22_restore.py`（会话末删）盘点出 **4 项**：
`UPD_RESP -restricted` · `DEL_RESP -note-restricted` · `DEL_RESP -restricted-seq` · `UPD_NOTE 八、1`。

**第三方核对**（经 postgres MCP 重新 SELECT，不看复原脚本自己的输出）：

| 项 | 实测 md5 | 基线 md5 |
|---|---|---|
| note `八、1`（2aa00f57） | `cb370a99193acfbb12cb367b397276c4` | 同 ✅ |
| note `八、1`（0ec33ac9） | `037f65ce0aaa7e34d5be5bde8daee5b7` | 同 ✅ |
| resp `-restricted` | `d751713988987e9331980363e24189ce`（len 2 = `[]`） | 同 ✅ |
| resp `-restricted-map` | `99914b932bd37a50b983c5e7c90ae93b` | 同 ✅ |
| wp `2a482c69` parsed_data | `1977844a752921e790853543d84fb3a1` len 75 | 同 ✅ |
| wp `a5701bec` parsed_data | `<null>` | **NULL**（非 `{}`）✅ |

测试期新建的 `-restricted-seq` / `-note-restricted` 已删除。`a5701bec` 保持 NULL 而非 `{}`，
`jsonb_typeof` 形态未漂移。

🔴 **复原脚本两处踩坑（工具类，非生产代码）**：
1. **基线 `pid` 存的是 8 位前缀**，用 `project_id::text = ANY(:ps)` 匹配完整 UUID 恒 0 行
   ⇒ 首版盘点**静默漏掉附注**（只列 3 项 response）。改用基线里的完整 `nid`
   （`disclosure_notes.id`）定位。**教训**：盘点脚本必须与「已知已改动项」交叉核对，
   「盘点结果比预期少」是漏项信号不是「没改过」。
2. **`text()` 里禁写 `:参数::类型`** —— SQLAlchemy 对「绑定参数紧跟 `::`」解析失败，
   该参数不进参数表，asyncpg 只收到其余占位符，报 `syntax error at or near ":"`
   （事务整体回滚、未写入）。一律用 `CAST(:p AS type)`。

#### 回归复跑（逐条相同）

- 后端 `-k "e1 or e_cycle"`：**368 passed / 1 skipped / 1704 deselected / 0 failed**
- 前端 `vitest run e1 E1`：**25 suites / 568 passed / 0 failed**（原 563 + 新增 5）

#### 本轮新登记的范围外缺陷（只登记不修）

1. **E1-10 交叉核对把科目码当账号比对** —— 告警「E1-3 银行明细有、账户清单无（疑未报告开户 3 户）：
   `1002`、`1012.02`、`1012.04`」。根因 = E1-3 存改造前**叶子口径** 3 行、E1-10 存**账户级** 29 行，
   两侧口径不同。本 spec 不含存量数据迁移 ⇒ 需另开 spec 做一次性回填。
2. **`useE1DepositDailyMatch.ts` 对象字面量重复键**（L252-256 `accounts` / L258-262 `depositType`）
   —— 既有欠账，与本 spec 无关。
3. **外币表分组行折算率显 `#N/A` 是既有设计不是缺陷** —— `E1TabDisclosure.vue` L1493/L1512
   `row.endRate ? .toFixed(4) : '#N/A'`，分组行是小计本无折算率。**勿「顺手纠正」**。

### Wave 6 实录之四：变异检验复核（Task 20，2026-08-10）—— 21 → 29 条，补齐守卫文件覆盖面缺口

**本轮定位**：脚本与「20/20 全 RED」结论已由上一轮写下（见「Wave 6 实录之一」），但复选框仍 `[-]`。本轮**逐条重跑核实**，并按任务原文「变异脚本 targets 必须覆盖**本 spec 全部守卫文件**」做了一次**逐文件**核对。结论：清单口径的 20 条 + M21 全部复现 RED，**但文件口径查出 7 个守卫文件从未被任何变异反证**。补 M22~M29 后 **29/29 全 RED、17/17 守卫文件全部被打红**。

#### 基线（本轮亲测，与冻结常量逐一相符）

| 范围 | 本轮实测 | 冻结常量 | 判定 |
|---|---|---|---|
| 后端 `backend/tests/four_table -k "e1 or e_cycle"` | **368 passed / 1 skipped / 1704 deselected / 0 failed** | `BASELINE_BE_PASSED = 368` | 相符 |
| 前端 `vitest run e1 E1` | **137 suites / 568 tests / 568 passed / 0 failed** | `BASELINE_FE_PASSED = 568` | 相符 |

两侧**失败名集合皆为空集** ⇒ 差集判定可信（脚本的「基线非空即 ABORT」未触发）。

🔴 **脚本注释里 `BASELINE_FE_PASSED` 的来源说明经交叉核实成立，不需要改常量** —— 注释称 Task 22 修 Property 28 时 `e1RestrictedSeq.spec.ts` 46 → 51 例、全量 563 → 568。上一轮 Task 20 记 `136 suites / 563 passed`，本轮实测 `137 suites / 568 passed`：**suites +1 / tests +5**，恰是「新增 1 个 describe、5 条断言」的形态，与 Task 22 实录的「新增 describe『E1 受限表序号端到端（Property 28 落库口径）』共 5 例」逐一对应。⇒ 差异有账可查，不是并发会话改动，也不是「常量凑数」。

🔴 **那唯一的 1 skipped 必须查明来源**（否则「连库侧同时红」的判定就悬空）：实测是 `test_e1_preset_coverage.py:575: 已无贴错标签的 sheet（Task 10 已收口）` —— **不是**连库不可用导致的 skip ⇒ `test_e1_bank_accounts_live.py` 的连库断言本轮真实执行过。这是 M01 / M13 能主张「源码 + 连库两处同时红」的前提。

#### 🔴 本轮最主要发现：「变异全 RED」≠「守卫都被反证过」

上一轮按 design.md Testing Strategy 的 20 条清单逐条验，20/20 RED，结论没错。但**清单是按「要验哪些属性」组织的，不是按「哪些守卫文件」组织的** —— 把 21 条变异的失败名逐一映射回文件后，**7 个本 spec 创建/扩展的前端守卫文件一次都没红过**：

| 未被反证的守卫文件 | 出处 | 例数量级 | 补的变异 |
|---|---|---|---|
| `e1HostSeedWiring.spec.ts` | Task 8 新建 | 25 例 | **M22** 宿主种子化退回叶子口径独占 |
| `e1SourcePanelWiring.spec.ts` | Task 9 新建 | 17 例 | **M23** 面板删 `accounts?` prop 声明 |
| `e1CurrencyScope.spec.ts` | Task 15 / 23 诚实改写 | — | **M24** 前端 `bucketDisplayOrderMap` 退回数组下标 |
| `e1FxNoteSectionMap.spec.ts` | Task 13 扩展 | — | **M25** 段归属表 `BS-041` → `BS-031` · **M29** 模板同一处（前端侧跑） |
| `e1RestrictedL2.spec.ts` | Task 14 新建 | — | **M26** 删 `pushL2Check('期末', …)` 调用点 |
| `e1NegativeBalance.spec.ts` | Task 17 扩展 | — | **M27** 负余额取值路径套 `Math.abs` |
| `e1NoteTextsAndPayload.spec.ts` | Task 15 扩展 | — | **M28** 删 soe 首行 `noteLabel` 双口径桥 |

这七个文件此前的「全绿」是**未经反证的绿** —— 正是 memory 假绿三源要防的形态（守卫在、跑了、绿了，但没人证明它会红）。M18 曾**顺带**打红 `e1RestrictedL2.spec.ts` 的列数断言，但那只覆盖②表列契约，Task 14 的 L2 归集与 L1/L2 勾稽项本身仍无变异。

**已把这条判据做进工具**（不靠下一轮再人工核对一遍）：脚本新增 `SPEC_GUARD_FILES`（17 个文件 + 各自出处），`run_one` 记 `added_files`（后端从 nodeid 首段取、前端从 vitest `testResults[].name` 反查，**是实测映射不是声明**），全量运行末尾打印「守卫文件覆盖面 N/17」并对欠账文件打 `[GAP]`。子集运行（`--run be` / `--run M01,M02`）明确不出覆盖面结论，避免半份数据当结论用。

#### 逐条结果（29 条，四态 tally = **RED 29 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0 / ERROR 0**）

锚点自检 **29/29 OK / 0 MISS**（全单行锚点；M03 / M09 / M19 三处靠行号消歧）。全 29 条 `restored=True`、`gone` 均为**空集**（无基线失败项消失 ⇒ 无污染残留，WRONG-TEST 风险为 0）。

| 变异 | 侧 | 目标文件（生产代码/数据）| 预期打红（`want`）| 实测打红的守卫文件 | 新增红 | 判定 |
|---|---|---|---|---|---|---|
| M01 | be | `e1_bank_accounts.py` | `test_no_naive_is_deleted_filter` | `test_e1_bank_accounts.py` + **`…_live.py`** | 4 | RED |
| M02 | be | 同上 | `test_same_account_two_rows_are_summed` | `test_e1_bank_accounts.py` | 3 | RED |
| M03 | be | 同上 | `test_null_amounts_are_coalesced_to_zero` | 同上 | 1 | RED |
| M04 | be | 同上 | `test_bank_name_is_never_the_account_no` | 同上 | 3 | RED |
| M05 | be | 同上 | `test_unrelated_code_goes_to_unassigned_not_dropped` | 同上 | 5 | RED |
| M06 | be | 同上 | `test_mismatch_is_exposed_not_corrected` | 同上 + `test_e1_render_account_prefill.py` | 2 | RED |
| M07 | be | `e1_restricted_buckets.py` | `test_declared_before_fallback_bucket` | `test_e1_restricted_buckets.py` | 3 | RED |
| M08 | be | 同上 | `test_classification_unchanged_by_new_bucket` | 同上 | 2 | RED |
| M09 | be | `note_template_soe.json` | `test_template_soe_main_matches_docx` | `test_note_e1_structure.py` | 3 | RED |
| M10 | be | 同上 | `test_row_code_row_name_matches_segment_label` | 同上 | 1 | RED |
| M11 | be | `fix_e1_orphan_sheet_presets.py` | `test_print_literals_are_gbk_encodable` | `test_e1_preset_coverage.py` | 1 | RED |
| M13 | be | `e1_bank_accounts.py` | `test_get_active_filter_is_awaited` | `test_e1_bank_accounts.py` + **`…_live.py`** | 3 | RED |
| M14 | be | `e1_restricted_buckets.py` | `test_payload_carries_display_order` | `test_e1_restricted_buckets.py` | 1 | RED |
| M15 | be | 同上 | `test_classification[境外冻结存款-overseas]` | 同上 | 1 | RED |
| M20 | be | `fix_e1_prefill_presets.py` | `test_non_data_whitelist_is_effective` | `test_e1_preset_coverage.py` | 1 | RED |
| M12 | fe | `e1BankAccountPrefill.ts` | 账户级 id 与叶子口径无交集（Property 7）| `e1BankAccountPrefill.spec.ts` | 2 | RED |
| M16 | fe | `e1MainRowPrefill.ts` | 槽键集完全一致且字典序冻结 | `e1MainRowPrefill.spec.ts` | 15 | RED |
| M17 | fe | 同上 | 三值全 0 的行不产生写入（Property 35）| 同上 | 6 | RED |
| M18 | fe | `e1NoteSectionMap.ts` | ②表不推「受限原因」列（Property 38）| `e1NoteSubtableContract.spec.ts` + `e1RestrictedL2.spec.ts` | 3 | RED |
| M19 | fe | `e1BankAccountPrefill.ts` | 原币与汇率一律留 0（Property 34）| `e1BankAccountPrefill.spec.ts` | 1 | RED |
| M21 | fe | `e1RestrictedScope.ts` | 删除后再新增 id 不复用（Property 28 端到端）| `e1RestrictedSeq.spec.ts` | 5 | RED |
| **M22** | fe | `GtE1MonetaryFund.vue` | `seedFromFourTable` 内账户级优先 + 叶子兜底 | `e1HostSeedWiring.spec.ts` | 3 | RED |
| **M23** | fe | `E1FourTableSourcePanel.vue` | `accounts` prop 已声明且宿主已传 | `e1SourcePanelWiring.spec.ts` | 2 | RED |
| **M24** | fe | `e1RestrictedScope.ts` | `displayOrder` 排序键与后端桶数量对齐 | `e1CurrencyScope.spec.ts` + `e1RestrictedL2` + `e1RestrictedSeq` | 5 | RED |
| **M25** | fe | `e1FxNoteSectionMap.ts` | 段归属表 row_code 与模板段序列一致 | `e1FxNoteSectionMap.spec.ts` | 2 | RED |
| **M26** | fe | `e1DisclosureConsistency.ts` | L1/L2 勾稽条目确实产出 | `e1RestrictedL2.spec.ts` | 5 | RED |
| **M27** | fe | `e1NegativeBalance.ts` | 负余额原样返回不取绝对值（Property 27）| `e1NegativeBalance.spec.ts` | 3 | RED |
| **M28** | fe | `e1DisclosureScope.ts` | soe 载荷首行标签 == docx 字面「库存现金」| `e1CurrencyScope` + `e1NoteTextsAndPayload.spec.ts` | 4 | RED |
| **M29** | fe | `note_template_soe.json` | soe 短期借款段 row_code 是 `BS-041` | `e1FxNoteSectionMap.spec.ts` | 2 | RED |

**GREEN → RED 的守卫修补记录：本轮 0 条**（首轮即全 RED）。上一轮的 3 条非 RED（M03 GREEN / M15 GREEN / M14 WRONG-TEST）经查全是**变异脚本自身缺陷**而非守卫缺陷，改法已固化在脚本注释里；本轮按修后的形态复跑，三条均复现 RED，修法有效。

#### 任务原文点名的四条专用变异：逐条核对「另一侧」

1. **M13 去 `await`** —— 要求「源码守卫与连库守卫两处同时红」。实测新增红 3 条：`TestProperty39ActiveFilterIsAwaited::test_get_active_filter_is_awaited`（源码）+ **`test_e1_bank_accounts_live.py::TestImplementationMatchesSqlBaseline::test_fetch_result_ties_to_sql_baseline`（连库）** + `TestEmptyPrefixesShortCircuits::test_boom_stub_actually_penetrates_fail_open`。⇒ **两处同时红成立，不存在守卫缺口**。连库那条红的机理正是 P0 签名：不 await 拿到 coroutine → `sa.and_(coroutine, …)` 抛异常 → fail-open 吞成 warning → 清单恒空 → 与独立 SQL 基线不符（该轮 pytest 另报 `3 warnings` = coroutine never awaited，与机理吻合）。第三条红是替身穿透自检：不 await 则 `get_active_filter` 函数体从不执行 ⇒ `db.execute` 从未被调 ⇒ 替身没机会抛。
2. **M14 `displayOrder` 回数组索引** —— 新增红**只有 1 条** `test_payload_carries_display_order`；**分类语义全绿**（367 passed + 1 failed = 368，与基线同总数 ⇒ 分类用例全部执行且通过）。✅ 展示序红 / 分类绿。
3. **M15 打乱声明序（`overseas` ↔ `pledged_deposit`）** —— 新增红**只有 1 条** `test_classification[境外冻结存款-overseas]`；**`displayOrder` 断言全绿**。✅ 分类红 / 展示序绿。M14 与 M15 方向相反、各自只红一侧 ⇒ **两序确已分离**（Task 23 的核心主张成立）。
4. **M16 删主表预填链** —— 新增红 **15 条**，覆盖键名契约 / 读取侧 / 写入侧 / 反向自检四组，含 Property 35 家族。✅

**M24 是 M14 的前端对侧、M29 是 M10 的前端对侧** —— 本轮特意补的两条「同一缺陷跨侧」变异，把 M13 那条「两处同时红」的判据推广开：后端红不代表前端也锁死。M29 尤其值得记：它与 M10 **锚点完全相同**（`note_template_soe.json` 的 `"report_row_code": "BS-041"`），只是跑的测试侧不同 ⇒ 证明前端没有把模板当可信输入。

#### M24 顺带复现一条已登记的守卫命名缺陷（第二次实证）

M24 打红的 `e1CurrencyScope.spec.ts` 三条里，有一条标题是 `自动分类结果按桶聚合` —— 听着是分类断言，但**实际读源码确认其断言体是 `expect(rows.map(r => [r.bucketKey, r.endingAmount])).toEqual([['bank_acceptance',100],['letter_of_credit',200]])`**，有序 `toEqual` 数组本质是**行序断言**。故它随展示序变异而红，与「分类语义保持绿」并不矛盾：真正的分类用例（`人工把叶子改归到别的类别 → 两侧余额都精确重算` 等）全绿。

这与 Task 16 实录里 M3 登记的同一条完全吻合（那轮记「标题与判据不符，如实登记不擅改」）。**本轮独立复现 ⇒ 该登记属实，不是当时的偶发观察**。建议仍按 Task 16 的意见后续拆成「分类归属（无序比较）」+「行序（有序）」两条，本轮不擅改（改标题或改成无序比较都会削弱既有保护）。

#### M01 的 co-red 说明（不是 WRONG-TEST）

M01 新增红 4 条，除 want 与连库那条外，还有 `TestJudgementInfrastructure::test_strip_comments_is_not_a_noop` 与 `test_get_active_filter_is_awaited`。都是合理连带：前者的断言体是 `assert "is_deleted" not in stripped`（即在干净源码里 `is_deleted` **只**出现在注释/docstring 里），M01 注入了真代码 `TbAuxBalance.is_deleted == False` 故必红；后者因 M01 把 `await get_active_filter(` 整行换掉、调用点消失。**登记一处判据耦合**：`test_strip_comments_is_not_a_noop` 名义上是「剥注释器可用性自检」，实际与 `test_no_naive_is_deleted_filter` 共用同一条不变式 ⇒ 剥注释器真坏掉时它也会红，但红的原因无法从名字区分。不影响本轮结论（want 已精确命中），登记备查。

#### 顺带纠正脚本一处 `why` 注释（实证与记载不符）

M01 的 `why` 原写「连库勾稽 `test_active_sum_is_the_one_tying_to_tb_balance` 在本机 8 项目 active/裸查一致时会 skip，故 want 锚在源码级判据上」。**实测该测试既没 skip 也没红，而是 PASSED** —— 它是 Task 1 实录里的「类 A 独立 SQL」自检，自带 active 与裸查两套查询、**完全不调被测实现**，故任何变异下都恒绿；它证明的是「dataset 过滤有必要」这个**数据事实**，不是「实现用了它」。真正覆盖 M01 的连库判据是 `test_fetch_result_ties_to_sql_baseline`。已按实测改写该注释（否则下轮会照它误判「连库侧没覆盖」）。

#### 残留清零证据

- `*.mutbak` 残留数 **0**（脚本开跑前扫残留即 ABORT、结尾再扫返 5；本轮两次全量运行 + 一次子集运行结束后独立复扫均为 `BAK_COUNT=0`）。工作树另有 `wp_template.py.bak` 与 `procedure_table_templates.json.bak` 两个属他 spec/并发会话，**未触碰**。
- 逐字节还原：开工时对 **36 个文件**（变异脚本 `MUTATIONS` 的全部目标 + 本 spec 全部守卫 + 5 个相邻宿主/模板文件）落 md5 快照，收尾比对 **`FILES=36 DIFF=0`** ⇒ 与开工基线逐字相同。判据是「md5 逐字相同」而非「变异字样是否出现」（后者会被 `new_prov[key] = value` 一类合法同形骗过）。
- **第三方复核**（清理完诊断产物后，换 PowerShell `Get-FileHash -Algorithm MD5` 重算，不看 python 快照脚本自己的输出）—— 11 个变异目标文件 md5 与开工值逐一相同：

  | md5 | 文件 |
  |---|---|
  | `54aa9de04ca93c8f3991cf00c8e77d76` | `backend/app/services/four_table/e1_bank_accounts.py` |
  | `b8f03277257c993ac091449f67c3e2f8` | `backend/app/services/four_table/e1_restricted_buckets.py` |
  | `3e9b26e43cd858dcf4a8bc1d7e5977ca` | `backend/data/note_template_soe.json` |
  | `57d43fe6cc3b618a552108123f1e76f5` | `backend/scripts/fix/fix_e1_orphan_sheet_presets.py` |
  | `bd94c78f082fc2960f78def4bbd0e601` | `backend/scripts/fix/fix_e1_prefill_presets.py` |
  | `2b2bd883c4cb19ea564032ff1255458c` | `composables/e1BankAccountPrefill.ts` |
  | `b8a64eaeb9ccccc2848a90825739045d` | `composables/e1MainRowPrefill.ts` |
  | `d1653cda613219d305295e44d0f15f6f` | `composables/e1NoteSectionMap.ts` |
  | `1f297486fb005532b36415d68f17fe76` | `composables/e1RestrictedScope.ts` |
  | `e15a6611216d1380a6c90002c3884b2d` | `GtE1MonetaryFund.vue` |
  | `7a5d242af2f21ae946079b2826cfbf1c` | `e1/E1FourTableSourcePanel.vue` |

  另 4 个 M25~M28 新增目标（`e1FxNoteSectionMap.ts` / `e1DisclosureConsistency.ts` / `e1NegativeBalance.ts` / `e1DisclosureScope.ts`）已含在上面的 36 文件 `DIFF=0` 里。
- 收尾回归与基线逐项相同：后端 **368 passed / 1 skipped / 0 failed**；前端 **137 suites / 568 passed / 0 failed**。

#### 被推翻 / 被修正的 spec 预设

| 出处 | 原文写的 | 实证 | 处置 |
|---|---|---|---|
| tasks.md Task 20 | 「**三态**判定：`new_fails` 非空 = RED / 空 = 守卫缺陷 / 锚点 ≠ 1 = ANCHOR-MISS」 | 三态会把 **WRONG-TEST**（红了但不是预期项 = 污染残留或锚点错行）误判成 RED；上一轮 M14 首轮就是这一态 | 脚本已实现**四态**（+ `ERROR`）。tasks.md / design.md 的「三态」表述已被实践推翻，按四态执行 |
| tasks.md Task 20 | 「变异脚本 targets 必须覆盖本 spec 全部守卫文件」（只写了要求，没有可执行判据）| 21 条变异下 **7/17 守卫文件从未被打红**，而报告只打印「20/20 RED」，看不出缺口 | 补 M22~M29 + 把覆盖面做成工具里的实测 tally（`SPEC_GUARD_FILES` + `added_files`），欠账会以 `[GAP]` 打印 |
| design.md Testing Strategy | 「≥10 个变异」 | 与 tasks.md 的「≥20 个」不一致 | 实交付 **29 条**，两者都满足；不改 design（数字下限之争无实质） |
| 脚本注释（M01 `why`）| 连库那条会 skip | 它 PASSED 且恒绿（独立 SQL 自检不调被测实现）| 已改写注释，并指明真正的连库判据是 `test_fetch_result_ties_to_sql_baseline` |

**未被推翻的**：`BASELINE_BE_PASSED = 368` / `BASELINE_FE_PASSED = 568` 两个冻结常量本轮实测相符，来源说明可交叉核实（见上）；design 的 20 条清单逐条有对应变异且全 RED；四条点名专用变异的「另一侧行为」全部如 spec 预期。

#### 本轮产物与清理

交付物 = `backend/scripts/diagnose/mutate_e_cycle_guards.py`（29 条变异 / `--list` / `--check-anchors` / `--run all|be|fe|M01,M02` / `--restore` / `--out` / 覆盖面 tally）+ 结果 JSON。诊断脚本 `_wip_t20_md5.py`、`_wip_t20_probe.py` 与全部 `_wip_t20_*.json|log|txt` 中间产物本轮结束时删除；上一轮遗留的 `_wip_mut_fe.json` 是脚本 `run_frontend()` 的**固定输出路径**（每次运行覆写），属工具运行态文件而非本轮新建，一并清理后下次运行会自动重建。

### Wave 6 实录之五：真实库验收复核（Task 21，2026-08-12）

**本轮定位**：上一轮已写下「实录之二」，但复选框仍 `[-]`。本轮**全部重跑取新证**（不拿旧输出充当本轮实测），并补齐上一轮自己登记的两处缺口：① 验收脚本只验 `1002` 单槽，本轮按**生产口径三槽全展开**重验；② 上一轮的「独立 SQL」仍共用 `get_active_filter`，本轮改用**完全不经任何被测代码**的裸 SQL（经 postgres MCP 只读直连）。结论：**10/10 全 OK、24 条科目级独立核对 diff 全 0.00、三脚本 rc 全 0、docx 49/49 判据 OK、无 UNVERIFIABLE 项**；并**修正了上一轮的一条结论**（见下）。

#### 新证与旧证的关系（先说清「是不是重跑」）

| 项 | 旧证 | 本轮新证 |
|---|---|---|
| `_verify_e1_account_extraction_live.txt` mtime | 2026-08-10 12:43:48 | **2026-08-12 10:00:31** |
| 同文件 md5 | `d05b2d19549a26ebdd790beb1d829ca9` | **逐字相同** |

md5 相同不是「没跑」，而是**真实数据两天内未变**（mtime 已刷新证明重跑过）。这也顺带说明该脚本的输出是可复现的：同一库状态下逐字节稳定。

#### 基线（本轮亲测，与冻结常量逐一相符）

| 范围 | 本轮实测 | 冻结常量 / 上一轮 | 判定 |
|---|---|---|---|
| 后端 `backend/tests/four_table -k "e1 or e_cycle"` | **368 passed / 1 skipped / 1704 deselected / 0 failed**（6.97s）| `BASELINE_BE_PASSED = 368` | 相符 |
| 前端 `vitest run e1 E1 --reporter=json` | **137 suites / 568 tests / 568 passed / 0 failed**，`success=true`、失败名集合空集 | `BASELINE_FE_PASSED = 568` | 相符 |

那 1 skipped 仍是 `test_e1_preset_coverage.py:575`「已无贴错标签的 sheet（Task 10 已收口）」，**不是**连库不可用 ⇒ 连库断言本轮真实执行过。

#### 一、Task 6 验收脚本（`--all-projects`）：10/10 OK

`结论：PASS（DIFF+ERROR = 0）`、`基线命中：10/10（键 = 短码:年度）`、无 `[WARN]`、`parsed_level` 10/10 全 `{'1': N}`。与 `ACCOUNT_COUNT_BASELINE` 逐条相符：`0ec33ac9:2025`=22 · `12c15a96:2025`=22 · `2aa00f57:2024`=23 · `2aa00f57:2025`=17 · `4f6dbc36:2025`=2 · `52c04ed1:2025`=21 · `a7fc75e5:2025`=38 · `b39809ed:2025`=6 · `c8621493:2025`=1 · `f064f5e4:2024`=23。`a7fc75e5` 的 −297,771,168.89 **原样负数**（`tb_balance.closing_direction='credit'`，独立 SQL 复证）⇒ Property 27「禁 abs」在真实数据上成立。

#### 二、补齐覆盖面缺口：**生产口径**槽级勾稽 10/10 OK

上一轮登记「脚本传 `account_prefixes=["1002"]`，比生产窄」。本轮按 `_build_account_prefill` 的真实口径重跑（`_ACCOUNT_SLOT_KEYS` = `bank`/`other`/`finance_co`，槽码由 `resolve_semantic_accounts` 逐项目定位后全展开）：

| 项目:年度 | 账户数 | parsed_level | bank 槽 n / account_sum / diff | other 槽 n / account_sum / diff | unassigned |
|---|---|---|---|---|---|
| `0ec33ac9:2025` | 29 | `{'1': 29}` | 22 / 4,703,056.26 / **0.00** | 7 / 4,479,140.00 / **0.00** | 0 |
| `12c15a96:2025` | 29 | `{'1': 29}` | 22 / 4,703,056.26 / **0.00** | 7 / 4,479,140.00 / **0.00** | 0 |
| `2aa00f57:2024` | 23 | `{'1': 23}` | 23 / 848,871.86 / **0.00** | 无账户（不产出条目，见下）| 0 |
| `2aa00f57:2025` | 22 | `{'1': 22}` | 17 / 327,095.20 / **0.00** | 5 / 4,140,440.92 / **0.00** | 0 |
| `4f6dbc36:2025` | 2 | `{'1': 2}` | 2 / 4,048.93 / **0.00** | 无账户 | 0 |
| `52c04ed1:2025` | 29 | `{'1': 29}` | 21 / 1,272,030.63 / **0.00** | 8 / 11,223,060.22 / **0.00** | 0 |
| `a7fc75e5:2025` | 55 | `{'1': 55}` | 38 / −297,771,168.89 / **0.00** | 17 / 409,938,004.92 / **0.00** | 0 |
| `b39809ed:2025` | 6 | `{'1': 6}` | 6 / 0.00 / **0.00** | 无账户 | 0 |
| `c8621493:2025` | 1 | `{'1': 1}` | 1 / 110.30 / **0.00** | 无账户 | 0 |
| `f064f5e4:2024` | 23 | `{'1': 23}` | 23 / 848,871.86 / **0.00** | 无账户 | 0 |

判定分布 = `{'OK': 10}`。`slot_codes` 10/10 均为 `{'bank': ['1002'], 'other': ['1012']}` —— **`finance_co` 槽全库无码**（`found=False`，`e_cycle_specs` 故意无兜底码），故它连 `slot_codes` 都不进，不是「验了但空」。这与 Task 24 实录记的「全库 8 项目 `finance_co`/`digital` 两槽 `found=False`」互相印证。

#### 三、独立 SQL 交叉核对（裸 SQL，**不经任何被测代码**）

口径自己写（含 active dataset 语义：`ledger_datasets.status='active'` 取到就锁 `dataset_id`，取不到则退 legacy `dataset_id IS NULL` —— 与 `get_active_filter` 的两条路径等价），覆盖 aux 侧**全部**科目而非只 `1002`，共 **24 行「项目×年度×科目」，diff 全 0.00**：

| 项目:年度 | ds 口径 | 科目 | aux 户数 | raw 行数 | aux 期末 | `tb_balance` 同码 | diff |
|---|---|---|---|---|---|---|---|
| `0ec33ac9:2025` | ACTIVE | 1002 / 1012.02 / 1012.04 / 1012.11.03 | 22 / 4 / 1 / 2 | 22 / 4 / 1 / 2 | 4,703,056.26 / 3,223,000.00 / 1,256,140.00 / 0.00 | 同 | 0.00 ×4 |
| `12c15a96:2025` | ACTIVE | 同上 4 码 | 22 / 4 / 1 / 2 | 同 | 同上 | 同 | 0.00 ×4 |
| `2aa00f57:2024` | **LEGACY(NULL ds)** | 1002 | 23 | 23 | 848,871.86 | 同 | 0.00 |
| `2aa00f57:2025` | ACTIVE | 1002 / 1012.02 / 1012.03 | 17 / 4 / 1 | **19** / 4 / 1 | 327,095.20 / 4,140,440.92 / 0.00 | 同 | 0.00 ×3 |
| `4f6dbc36:2025` | ACTIVE | 1002 | 2 | 2 | 4,048.93 | 同 | 0.00 |
| `52c04ed1:2025` | ACTIVE | 1002 / 1012.02 / 1012.04 | 21 / **6** / 2 | 21 / **7** / 2 | 1,272,030.63 / 9,196,685.98 / 2,026,374.24 | 同 | 0.00 ×3 |
| `a7fc75e5:2025` | ACTIVE | 1002 / 1012.02 / 1012.03 / 1012.04 / 1012.11.03 | **38** / 10 / 1 / 2 / 4 | **39** / 10 / 1 / 2 / 4 | −297,771,168.89 / 99,504,201.24 / 5,400,000.00 / 4,139,558.80 / 300,894,244.88 | 同 | 0.00 ×5 |
| `b39809ed:2025` | ACTIVE | 1002 | 6 | 6 | 0.00 | 同 | 0.00 |
| `c8621493:2025` | ACTIVE | 1002 | 1 | 1 | 110.30 | 同 | 0.00 |
| `f064f5e4:2024` | ACTIVE | 1002 | 23 | 23 | 848,871.86 | 同 | 0.00 |

**槽合计可由科目级独立数字逐笔加总复现**（这是「独立 SQL 证到槽级」的落点，不是只证了 `1002`）：`0ec33ac9` other = 3,223,000.00 + 1,256,140.00 + 0.00 = **4,479,140.00** ✅ · `52c04ed1` other = 9,196,685.98 + 2,026,374.24 = **11,223,060.22** ✅ · `a7fc75e5` other = 99,504,201.24 + 5,400,000.00 + 4,139,558.80 + 300,894,244.88 = **409,938,004.92** ✅ · `2aa00f57:2025` other = 4,140,440.92 + 0.00 = **4,140,440.92** ✅ —— 与上表被测路径的槽合计逐分相同。

**M02（按账号聚合）的数据前提本轮复证**：三处 `raw 行数 > 户数`（`2aa00f57:2025` 19/17 · `52c04ed1:2025 1012.02` 7/6 · `a7fc75e5:2025 1002` 39/38）⇒ 不聚合会虚增账户数并破坏勾稽。

**`2aa00f57:2024` 走 legacy 口径本轮复证**：`ledger_datasets` 里该「项目×年度」**无任何行**（只有 2025 有 `active:d6f5f77b`），aux 的 `dataset_id` 为 NULL。裸 SQL 若只写 `JOIN ledger_datasets ... status='active'` 会静默漏掉它 —— 这是 `get_active_filter` 相对裸查的第二个必要性理由。

#### 🔴 四、**修正上一轮的一条结论**：勾稽 diff 抓不到「缺失 dataset 过滤」

上一轮记「裸查金额几乎正好翻倍 ⇒ `get_active_filter` 是防止合计翻倍的必要条件」——**前半句对，但由此推不出「勾稽会暴露它」**。本轮把 `tb_balance` 侧也按裸查跑了一遍（上一轮只裸查了 aux 侧），`0ec33ac9:2025` 的 `1002`：

| 口径 | aux 户数 | aux 行数 | aux 期末 | 涉及 dataset 数 | `tb_balance` 1002 行数 | `tb_balance` 1002 期末 |
|---|---|---|---|---|---|---|
| 裸 `is_deleted=false` | **23** | **45** | **9,406,222.82** | 3 | **3** | **9,406,222.82** |
| 锁 active dataset | 22 | 22 | 4,703,056.26 | 1 | 1 | 4,703,056.26 |

逐 dataset 明细（aux 与 tb 两侧结构完全对称）：

| dataset | status | aux 户数 / 行数 / 期末 | `tb_balance` 1002 期末 |
|---|---|---|---|
| `c050bfbe` | active | 22 / 22 / 4,703,056.26 | 4,703,056.26 |
| `b949639e` | superseded | 22 / 22 / 4,703,056.26 | 4,703,056.26 |
| `ab168cfb` | superseded | 1 / 1 / 110.30 | 110.30 |

⇒ **两侧同时裸查时 diff 仍恰好 0.00**（9,406,222.82 − 9,406,222.82），缺陷完全隐形。上一轮之所以看到「假 DIFF」，是因为当时 aux 走 active 而 tb 走裸查（**口径不对称**才暴露）。真正能抓住这个缺陷的判据是三条**别的**东西：① 账户数 22 → **23**（多出那户只存在于 superseded 集）② 行数 22 → **45**（每户重复列示，E1-3/E1-10 会看到重复行）③ 源码级守卫 `test_no_naive_is_deleted_filter`。M01 变异能 RED 也正是靠源码级判据 + `test_fetch_result_ties_to_sql_baseline`（账户数/合计对独立基线），**不是**靠勾稽 diff。

**教训**：「两侧共用同一个错误口径」会让差额判据自我抵消 —— 与 Task 20 里 M03 那条「`_f` 双层防御让变异自我抵消」同型。差额类判据必须配**绝对量判据**（户数、行数、对独立基线）才有反证力。

#### 五、`unassigned` 明细：10/10 全空，且是**数据事实**不是槽定义缺口

独立 SQL 扫全库 `aux_type='银行账户' AND is_deleted=false` 共 **308 行**，`account_code` 只有 5 个取值：

| 科目 | 行数 | 覆盖项目数 | 落在槽前缀（`1002`+`1012`）外 |
|---|---|---|---|
| `1002` | 244 | 9 | 0 |
| `1012.02` | 41 | 5 | 0 |
| `1012.03` | 3 | 2 | 0 |
| `1012.04` | 8 | 4 | 0 |
| `1012.11.03` | 12 | 3 | 0 |

`outside_1002_1012` 合计 **0** ⇒ 槽前缀对 aux 侧**100% 覆盖**，`unassigned` 恒空是覆盖完备而非判据空转。M05 变异（`unassigned` 塞进 `bank`）打红的是构造数据用例，与此不矛盾。

#### 六、`parsed_level` 独立复核（**不经解析器**）

按 `aux_dimensions_raw` 的字符串形态直接统计 308 行：同时含 `银行账户:` 与 `金融机构:` = **308**、只含账号（level 2 前提）= **0**、两者皆无（level 3 前提）= **0** ⇒ 与被测路径报的 `{'1': N}` 逐项一致，**level 2/3 分支全库零命中（潜伏态）**。顺带复证 Property 34 的数据前提：308 行 `currency_code` **全 `CNY`**、`opening_fc` **全 NULL（308/308）** ⇒ 原币/汇率列必须留空（无从反推）。

#### 🔴 七、本轮新发现一处**单侧盲区**（既有有意行为，但真实数据上分支活跃）—— 登记不改

`2aa00f57:2024` 与 `f064f5e4:2024` 的 `other` 槽：**叶子期末 52,475,713.77，aux 账户 0 户**。`check_accounts_vs_leaves` 按设计**不产出该槽条目**（docstring「只对两侧都有数据的槽产出条目（缺一侧时「不平」没有意义）」，守卫 `test_slot_without_accounts_is_skipped` / `test_slot_without_leaf_amount_is_skipped` 双向锁死），而溯源面板 `reconcileRows` 也只渲染后端产出的条目（注释明写「只列后端产出条目」）⇒ 审计师在这两个「项目×年度」**看不到「其他货币资金 5247 万无账户级明细」这个信号**。

独立 SQL 复证：`1012.02` = 21,225,713.77 + `1012.03` = 31,250,000.00 = **52,475,713.77**（与叶子合计逐分相同），且 aux 侧 `1012%` 行数 = **0**。另注：`tb_balance` 该项目 `1012` 子树裸加是 104,951,427.54 = 2 × 52,475,713.77，因为父行 `1012` 自身也存着同额 ⇒ **必须走 `select_leaves`**，这条也在本轮被真实数据证到。

**为什么本任务不改**：加 `reconcile` 条目会破坏 payload 契约并打红上述两条既有守卫；`unassigned` 也不该塞（它的语义是「有账户但科目未覆盖」，这里是反向）。**建议**（另立任务）：溯源面板加一个**独立**的 `no_accounts_but_leaves` 单侧信号（新键，不进 `reconcile`），文案「该槽叶子有余额但辅助余额表无账户明细，E1-3/E1-10 将退回叶子口径」。这与 Task 22 登记的「E1-10 交叉核对把科目码当账号比对」属同一类存量口径问题，可合并到那个 spec。

#### 八、三个幂等脚本 `--check`：**默认 GBK 编码下 rc 全 0**

判据就是退出码（Task 11 的口径）。runner 显式**剥掉** `PYTHONIOENCODING` / `PYTHONUTF8` / `PYTHONLEGACYWINDOWSSTDIO`（实测三者均为 `None`），`locale.getpreferredencoding(False)` = **cp936**：

| 脚本 | rc | `UnicodeEncodeError` | 输出 |
|---|---|---|---|
| `fix_note_e1_monetary_fund_structure.py --check` | **0** | False | 四节**逐条**「= 已对齐（幂等空操作）」（上市 五、1 / 国企 八、1 / 上市 五、73 / 国企 八、92）+「--check：0 项欠账」|
| `fix_e1_orphan_sheet_presets.py --check` | **0** | False | `[OK] E1 orphan sheet presets: 0 欠账（9 blocks 已全部就位）` |
| `fix_e1_prefill_presets.py --check` | **0** | False | `--check: 0 项欠账` |

四节逐条报「已对齐」而非静默跳过 —— 这是「0 欠账」与「没查」的区分点。第 2 个脚本的 `[OK]` 前缀正是 Task 11 把 `✅` 换掉的结果，在 cp936 下不再崩。

#### 九、python-docx 独立复核四处修正：**49/49 判据 OK**

探针不 import 既有守卫的任何 helper，自己写 `document.element.body` 顺序流遍历 + 归一化 + 「节号命中数 == 1」自检 + 「归一器不是空操作」自检。

| 修正 | docx 侧（源）| 模板侧（`note_template_*.json`）|
|---|---|---|
| ① soe 八、1 主表首行 | `库存现金`（H3「货币资金」节第 1 张表）| `label = 库存现金` |
| ② soe 八、1 补境外备忘行 | 6 行 `['库存现金','银行存款','其他货币资金','数字货币','合  计','其中：存放在境外的款项总额']` | 6 行、行序与 docx **归一后逐行相等**；境外行 `row_type='data'` 且**无** `is_total` |
| ③ 两版受限表补新桶 | soe 6 类、**无合计行**、序 = 银行承兑→信用证→履约→担保定期→境外→**法定准备金** | listed 与 soe **各 7 行**（6 类 + 平台补充 `合计`）；前 6 行与 docx 逐字一致；新桶 index 5 < 合计 index 6 |
| ④ soe 八、92 短期借款段 | —（模板侧修正）| 5 段 `BS-002/BS-006/`**`BS-041`**`/BS-061/BS-062`；短期借款段 `report_row_code='BS-041'`、`account_codes` 逐字 `['2001']`；**两版均已无 `BS-031`** |

同批验到的既有事实（防「顺手纠正」）：Property 37 —— listed docx 货币资金节**只有 1 张表**（受限内容是文字段落）⇒ listed 受限表确属平台补充 · listed 外币表**只 3 段**（货币资金/应收账款/长期借款）、**本就无短期借款段** ⇒ 修正 4 只针对 soe · docx 合计行字面 `合  计`（双空格）与模板 `合计` 的差异是**有意的**（既有守卫 `test_total_label_matches_template` 已裁决），故比较必须归一。上一轮探针在这两处首轮误 FAIL，本轮已把归一与「listed 无该段」直接写进判据，未重犯。

**修正 4 的方向另经 postgres MCP 独立查 `report_config` 复证**（不看模板、不看守卫）：`BS-041` 在 `listed_consolidated`/`listed_standalone`/`soe_consolidated`/`soe_standalone` 四准则下 `row_name` **全为 `短期借款`**；`BS-031` 四准则下**全为 `使用权资产`** ⇒ 改成 `BS-041` 正确，且 Property 24「`BS-031` 留给 H8」的反向锁死仍成立。

#### 被推翻 / 被修正的判断

| 出处 | 原文/上一轮写的 | 本轮实证 | 处置 |
|---|---|---|---|
| tasks.md Task 21 | 「跑 Task 6 的脚本覆盖全部 **8 项目**」 | 实为 **10 个「项目×年度」**（`2aa00f57`/`f064f5e4` 各有 2024/2025），其中 `2aa00f57:2024` 无 `ledger_datasets` 行、走 legacy `dataset_id IS NULL` | 覆盖面按「项目×年度」计 10/10（上一轮已记，本轮复证）|
| 「实录之二」 | 「裸查金额几乎正好翻倍 ⇒ `get_active_filter` 是防止合计翻倍的必要条件」（暗示勾稽会暴露）| **两侧同时裸查时 diff 恒 0.00**，缺陷隐形；能抓住它的是户数 22→23、行数 22→45、源码级守卫 | 结论改写（见第四节）。差额判据须配绝对量判据才有反证力 |
| 「实录之二」登记的覆盖面缺口 | 「脚本只验 `1002`，比生产窄」（登记不改）| 本轮按生产三槽口径重验：`other` 槽在 5 个「项目×年度」有账户，diff 全 0.00 | 缺口**已闭合**（用一次性探针，不改脚本）；若日后改脚本，`account_prefixes` 应从 `E1_MONETARY_FUND_SPEC` 反解而非写死 |
| `check_accounts_vs_leaves` 的「缺一侧不产出条目」 | 设计上视为「不平没有意义」 | 真实数据上该分支**活跃**（2 个「项目×年度」、52,475,713.77 无账户明细），导致溯源面板无信号 | 登记为单侧盲区 + 给出不破契约的改法建议（第七节），本任务不改 |

#### UNVERIFIABLE 项

**无。** 六类判据（脚本 10/10 · 生产口径槽级 10/10 · 独立 SQL 24 行 · 三脚本 rc · docx 49 项 · `report_config` 四准则）全部取到真实证据，未用任何 fixture 冒充。另说明两点**不属** UNVERIFIABLE 而属数据事实：① `finance_co`/`digital` 两槽全库 `found=False`（连 `slot_codes` 都不进）② `parsed_level` 2/3 与外币账户全库零命中（守卫用构造数据覆盖，M04/M19 变异已证判据非空转）。

#### 本轮产物与清理

全程**只读零写库**（postgres MCP 只读模式；验收脚本与探针均无 INSERT/UPDATE/DELETE），生产代码与数据文件零改动，仅本文件追加本节。一次性探针 `tmp_t21_slot_probe.py`（生产口径槽级勾稽）· `tmp_t21_check_rc.py`（GBK rc 捕获）· `tmp_t21_docx_probe.py`（docx 四处复核）与全部 `tmp_t21_*.json|txt` 中间产物本轮结束时删除；根目录并发会话的 `tmp_t26_*` / `_wip_*` **未触碰**。
### Wave 6 实录之六：Task 22 收口复核（2026-08-12）—— 浏览器复测补齐 4 项 + 抓到第二处真实缺陷

**本轮定位**：上一轮（「实录之三」）已在真实浏览器做完主体并修掉 Property 28 端到端失效，本轮**只做收口**：① 复核那处修复仍在工作树；② 补齐上一轮未闭合的 4 个验证项；③ 查清任务原文「原币/汇率列**留空**」与上一轮实录「本位币显『人民币 / 1』」的字面冲突；④ 复原复核 + 清理。**不重跑已闭合的判据**。

结论：修复在位（md5 相符）· 4 项全部补齐 · 字面冲突查清（任务原文那句**对本位币账户是错的**，已被 Task 8 实录裁决取代）· **本轮浏览器实测抓到第二处真实缺陷（E1-3 multi 版金额被静默抹零）**· 库侧**零写入**故无需复原 · 清掉本 spec 276 个 `_wip_e_*` 产物。

#### 一、上一轮修复在位性复核（md5 + 结构双证）

| 项 | 本轮实测 | Task 20 报告的参考值 | 判定 |
|---|---|---|---|
| `composables/e1RestrictedScope.ts` md5 | `1f297486fb005532b36415d68f17fe76`（31761 B） | `1f297486fb005532b36415d68f17fe76` | **逐字相同** |
| 该文件 L300 | `id: idByBucket.get(bucketKey) ?? e1RestrictedRowId(bucketKey, i),` | — | 在位 |
| `idByBucket` 出现处 | L292 建 Map / L295 填充 / L300 消费 | — | 三段链完整 |
| `__tests__/e1RestrictedSeq.spec.ts` | `it(` **51** 条 / 8 describe，含 `E1 受限表序号端到端（Property 28 落库口径）`（L399） | 46 → 51 | 在位 |

⇒ 修复未被并发会话回退，守卫例数与 `BASELINE_FE_PASSED = 568` 的来源说明一致。

#### 🔴 二、Property 34「原币/汇率」字面冲突：查清结果 —— 任务原文那句话**对本位币账户不成立**

任务原文写「E1-3 显示逐户账户行（含开户银行与账号，且原币/汇率列**留空**）」，上一轮实录写「multi 版原币/汇率列存在且本位币显『人民币 / 1』」。两者**确实冲突**，本轮按「判据落在种子行是否带值」逐层查证：

**① 后端载荷侧：根本没有原币字段可反推**（live API `GET /api/workpapers/{wp}/render-config` 实取）

`account_prefill.accounts[*]` 的键集精确为
`['account_code','account_no','bank_name','closing','credit','currency','debit','opening','parsed_level','row_count','slot','source']`
—— **无 `opening_fc` / 无 `fx_rate` / 无任何原币列**。两个项目的 `currency` 集合均为 `{'CNY'}`。与 Task 21 第六节的裸 SQL 复证（308 行 `currency_code` 全 CNY、`opening_fc` 全 NULL）一致。

**② 前端种子侧：本位币下发的是「恒等」，非本位币才「留空」**（`e1BankAccountPrefill.buildBankSeedRowsFromAccounts` L287~L303）

| 币种 | `fxRate` | `openingFc/increaseFc/decreaseFc` | `adjustmentFc` | 依据 |
|---|---|---|---|---|
| CNY/RMB/空 | **1** | **= opening / debit / credit** | 0 | 「原币 == 本位币、汇率 = 1」是**恒等事实**；不下发则 multi 版 recalc 把金额抹成 0 |
| 非本位币 | **0** | **全 0** | 0 | 四表确实没有原币与汇率 ⇒ 留 0 + `note` 追加 `原币金额与汇率需手工录入（四表无原币数据）` |

**③ 裁决**：Property 34 在 design.md 的正式表述是「账户级种子按 E1-3 variant 分流且不丢外币账户」，「不得由本位币反推」这条只约束**非本位币**账户（守卫 `🔴 非本位币账户原币与汇率一律留 0（Property 34）` + 源码级 `不得由本位币金额反推非本位币的原币/汇率` 两条，变异 **M19** 已 RED）。任务原文那句「原币/汇率列留空」是**压缩转述时丢了币种前提**，且早在 Task 8 实录（2026-08-08）就被实测推翻并留了处置表 —— 本轮只是把「tasks.md 验证项那一行仍写着旧说法」这件事登记清楚，**不改代码、不改守卫**。

**④「组件展示占位」vs「持久化了值」的区分（本轮实测结论）**：`2aa00f57` 库里 **`E1-bank-detail-rows` 这条 `checklist_responses` 根本不存在** ⇒ 该项目**没有任何 fx 值被持久化**。界面上的「人民币 / 1」来自 `seedFromFourTable()` 的**内存种子**（宿主 `seedRowsKey` 注释明写「仅内存，不落库」）+ `useE1BankDetail` 缺字段时的默认（`fxCurrency:'人民币', fxRate:1`）。⇒ **不存在 Property 34 违规**（既没反推，也没持久化）。

#### 🔴 三、本轮浏览器实测抓到的第二处真实缺陷：E1-3 multi 版金额被静默抹零（只登记，不在本任务修）

**这正是 Task 8 实录明文警告「比取不到更坏」的那种形态，且有确定性复现路径。**

| 复现路径（`2aa00f57` / a5701bec，每次都从**新加载页面**开始） | multi 版结果 |
|---|---|
| 加载 → 直接点 `(人民币及外币)E1-3` | ✅ 正常：招商 023900017110777 = **2,046.75**；银行机构小计「期初 848,871.86 期末 327,095.20 审定 327,095.20」；段头「期末 4,467,536.12」；横幅「E1-1 审定合计与试算平衡表核对一致」 |
| 加载 → 先点 `(仅人民币)E1-3` → 再点 `(人民币及外币)E1-3` | 🔴 **全表金额变 `-`**：22 行期末/审定/对账单差异全 `-`；三个小计全「期初 - 期末 - 审定 -」；段头全 `-`；横幅变「**E1-1 审定合计 0.00 ≠ TB数 4467536.12，差异 -4467536.12**」 |
| 加载 → 点 multi → 点 rmb → 再点 multi | ✅ 仍正常（说明**不是** variant 往返本身的问题） |

**根因**（源码级已定位，两处共同作用）：
1. `GtE1MonetaryFund.seedFromFourTable()` 只在 `onMounted` 跑一次，且 `seedRowsKey` 有 `if (allResponses.has(key)) return` 的 persist-first 短路 ⇒ **`E1-bank-detail-rows` 的种子形态在会话内只定型一次**，用的是当时的 `e13Variant.value`（`props.sheetName` 含「仅人民币」→ `rmb`）。
2. `useE1BankDetail.recalcRow(row,'multi')` 把 `opening/increase/decrease/ending/adjustment/audited` **全部由「原币 × fxRate」派生**；rmb 形态的种子行没有 `openingFc/increaseFc/decreaseFc`（`parseNum(undefined) = 0`）⇒ 期末恒 0 ⇒ `fmtAmount(0)` 显示 `-`。

**为什么 29 条变异 + 568 例守卫都没拦住**：M3（Task 7 轮）/ M19（Task 20 轮）验的是**纯函数** `buildBankSeedRowsFromAccounts(p,'multi')` 的输出，`e1HostSeedWiring.spec.ts` 验的是「账户级优先 + 叶子兜底」的接线，**没有一条把「种子的 variant」与「消费它的 Tab 的 variant」串起来断言**。同 Property 28 那次一样属「注入点在、消费方在、两者口径不一致」，是假绿第一源的第三种变体。

**归属与严重度**：
- **不是本 spec 新引入的** —— 叶子口径的 `e1FourTablePrefill.buildBankSeedRows()` **无条件**下发 `fxRate:1, openingFc:0, increaseFc:0, decreaseFc:0`（L126~L131）⇒ 改造前 multi 版**在任何路径下都被抹零**。本 spec 的账户级路径把它改善为「先开 multi 即正确」，属**部分修复**而非引入。
- 影响面：审计师若按目录顺序先点「仅人民币」再点「人民币及外币」（很自然的操作序），会看到「有 22 个账户但金额全空」+ 一条错的审定差异横幅。
- **不在本任务修**：改法要动宿主种子化的时机/键分离（例如按 variant 分键，或 variant 变化时重算 fc 列），属实现改动 + 需新守卫（「宿主种子 variant 必须与消费 Tab 的 variant 一致」+ 变异反证），超出 Task 22「实测与复原」的范围。**建议单独立任务**，与「E1-10 交叉核对把科目码当账号比对」合并到那个存量口径 spec。

#### 四、本轮补齐的验证项（逐条结论）

| 验证项 | 本轮证据 | 结论 |
|---|---|---|
| **E1-3 两 variant 账户条数相同** | 同一项目：rmb 版页脚「共 **22** 行」（银行机构 17 + 其他货币资金 5）· multi 版页脚「共 **22** 行」（同分组同账号同序） | ✅ 相等（上一轮只记了溯源块户数，未分 variant 计行数） |
| **溯源面板 `parsed_level` 分布可见** | 面板头 el-tag：`22 个账户` + **`账号 + 银行名 22`**（`LEVEL_LABELS['1']`）· 另一项目 render 载荷 `meta.parsed_level_dist = {"1": 29}` | ✅ 可见；真实数据全 level 1，故只渲染 1 个 tag（level 2/3 tag 为潜伏分支） |
| **溯源面板账户数 / 勾稽 diff** | `银行存款 327,095.20 vs 327,095.20 → -` · `其他货币资金 4,140,440.92 vs 4,140,440.92 → -`（`fmtAmount(0)` = `-`）；无「勾稽不平」danger tag | ✅ |
| **E1-3 逐户行含开户银行与账号** | 22 行逐户：重庆三峡银行/01141560014000168 · 招商银行/023900017110777 · 工商银行/3100021509024876090（合并笔数 2）… | ✅ |
| **E1-10 含零余额账户** | 「共 **22** 行」+ 完整性面板「账户 22 个 / 本期新开 0 / 本期注销 0 / 无疑似账外账户 / 清单与账面核对一致」；期末为 `-` 的账户（中国银行 111645582188 等）全部在列；同账号跨科目未去重（231181250710001 出现 3 次） | ✅ |
| **E1-4「本项目无此科目」口径** | 无四表取数面板（宿主 `ftAccountsForPanel` 对 E1-4 传 `undefined`）· 共 1 行空行 · 合计「期初 - / 期末原币 - / 本位币 - / 审定人民币 -」 | ✅ 口径成立。**但页面上没有「本项目无此科目」这句字面** —— 该文案实际是 Task 24 给披露主表 `endingResolved=false` 行做的 tooltip「本项目无此科目或审定表未录入」。任务原文把两处说法混了，登记备查 |
| **受限表展示序（后端 `displayOrder` 运行态证据）** | live render 载荷 `restricted_prefill.bucketDefs` 7 桶：`bank_acceptance=0` · `letter_of_credit=1` · `performance=2` · `pledged_deposit=3` · `overseas=4` · `statutory_reserve=5` · `other=12`；而**数组声明序**是 `信用证→银行承兑→履约→境外→担保定期→法定准备金→其他`（= 匹配优先级） | ✅ 排序后即任务原文的完整序「银行承兑→信用证→履约→担保定期→境外→法定准备金→(其他受限)」，**两序确已分离**（Task 23 主张在运行态成立） |
| **受限表真实数据可观察范围** | 真实数据下有金额的源类桶最多 2 个（`0ec33ac9` 命中 `bank_acceptance` + `other`；`2aa00f57` 命中 `bank_acceptance` + `letter_of_credit`）⇒ 完整 7 桶序**无法只靠真实数据观察** | 由三类证据合证：① 上表 live `displayOrder` ② vitest（`e1CurrencyScope.spec.ts` 行序用例 + `e1RestrictedSeq.spec.ts` displayOrder describe）③ 变异 **M14/M24 双侧 RED**（后端载荷 + 前端排序键各锁一侧） |
| **推送后附注 `八、1` 落 6 行** | 库侧独立 SELECT：`0ec33ac9 / 八、1`（`89b8b3fb`）的 `sub_table_data.货币资金` = **6 行** `库存现金 \| 银行存款 \| 其他货币资金 \| 数字货币 \| 合计 \| 其中：存放在境外的款项总额` | ✅ 上一轮在 soe 项目验过，本轮在**另一个项目**上复证（该项目已由并发会话于 2026-08-12 02:08:30 重新推送，`last_sync_sheet=附注披露信息(国企)`），⇒ 上一轮登记的「基线是 5 行」已被这次推送刷新为 6 行 |

#### 五、UNVERIFIABLE 项（如实登记 + 替代证据）

| 项 | 原因 | 替代证据 |
|---|---|---|
| **listed 披露主表三行（存放财务公司款项 / 存款应计利息 / 数字货币）按槽预填或如实空白** | 全库 8 个真实项目 `projects.applicable_standard_v2.entity_type` **全为 soe**（本轮再次核对 `0ec33ac9`：`template_type='listed'` 而 `entity_type='soe'`）⇒ listed 披露 Tab 恒显「当前项目不适用上市公司附注披露」。**按约束未改任何项目的 `applicable_standard_v2`**（那是写真实项目数据 + 会污染准则口径） | ① `e1MainRowPrefill.spec.ts` **42 例全绿**（三行预填 / `found=False` 不写 0 / 手工值不覆盖 / soe 无该三行 / 合计恒等式 PBT）② 源码级：`E1_MAIN_ROW_SLOTS` + `E1_MAIN_ROW_DEDUCTIONS` + `buildE1MainRowSlotWrites` 三段链在位 ③ 变异 **M16（删预填链，15 条红）/ M17（三值全 0 也写键，6 条红）** 均 RED ④ 数据事实：全库 `finance_co`/`digital` 两槽 `found=False` ⇒ 即便有 listed 项目，这两行也应显示空白而非 0（正是 Property 35 要区分的两态） |
| **listed 侧「外币段推送落 五、73」** | 同上（listed Tab 不可达）。soe 侧 `八、92` 已由上一轮验过（两项目推送前后 md5 均 SAME、5 段 25 行完整） | `e1FxNoteSectionMap.spec.ts` + 变异 **M25/M29** 双侧 RED；Task 21 第九节 python-docx 49/49 已证 listed 外币表**本就只 3 段无短期借款段** |
| **受限表完整 7 桶行序在真实页面上逐行观察** | 真实数据最多命中 2 个源类桶（见上表） | live `displayOrder` 载荷 + vitest + M14/M24 双侧变异（同上表末行） |
| **新增自定义类别 + 删后再增序号不复用（端到端）** | 该判据**已由上一轮在真实浏览器完成**（甲=2 → 删 → 乙 复用 `_2` = 缺陷；修后 丙=**4** 不复用），本轮**有意不重跑** —— 重跑必然写 `checklist_responses` 与 `disclosure_notes`，与本轮「零写库、无需复原」的收口目标冲突 | 上一轮实录的库侧取证 + `e1RestrictedSeq.spec.ts` 5 例端到端 describe + 变异 **M21 RED**（新增红 5 条恰为那 5 例、`gone` 空集） |

#### 六、库侧零写入复核（独立查询，非脚本自证）

**本轮浏览器操作全程只读**，故无复原动作。三重证据：

1. **开工基线 vs 收尾复查**（两次 postgres MCP 独立 SELECT，覆盖 2 个 wp 的 `parsed_data` + 26 条 `checklist_responses` + 7 条 `disclosure_notes`）：**md5 与 `updated_at` 逐条相同**，无新增/删除行。
2. **`updated_at` 全部早于本会话**（会话起始 `now()` = 2026-08-12 02:26:23 UTC）：最新一条是 02:08:30（并发会话的附注推送），其余为 08-10 及更早 ⇒ 我没写过任何一行。
3. **网络层**：chrome-devtools `list_network_requests` 全量 181 条中，对 `/api/**` 的写请求**只有** `POST /api/editing-locks/workpaper/{id}`（进入底稿页的编辑锁）与 `PATCH .../heartbeat`；**无任何** `checklist-responses` / `disclosure-notes` / `sync` 的 POST/PUT/PATCH。

上一轮登记的 6 项复原值本轮复核：`2aa00f57/八、1` = `cb370a99193acfbb12cb367b397276c4` ✅ · `a5701bec/-restricted` = `d751713988987e9331980363e24189ce`（`[]`）✅ · `a5701bec/-restricted-map` = `99914b932bd37a50b983c5e7c90ae93b`（`{}`）✅ · `2a482c69` parsed_data = `1977844a752921e790853543d84fb3a1` ✅ · `a5701bec` parsed_data = **NULL**（非 `{}`）✅ · 测试期键 `-restricted-seq` / `-note-restricted` **仍不存在** ✅。

🔴 **唯一一项与上一轮不同，且不属于我、也不得回退**：`0ec33ac9 / 八、1`（`89b8b3fb`）现为 `826110978f8984f4e8f261eb9aef702c`，上一轮基线是 `037f65ce0aaa7e34d5be5bde8daee5b7`。`updated_at = 2026-08-12 02:08:30`（我的会话开始前 18 分钟）、`last_sync_source='workpaper'`、`last_sync_wp_id=2a482c69`、`_last_sync_sheet='附注披露信息(国企)'` ⇒ **并发会话的一次正常推送**。按「并发会话的成果不得回退」处置：**保留现状**，并把它作为「八、1 落 6 行」的新证据（见第四节）。**教训**：跨会话复原必须先判「差异是谁造成的」，把别人的新成果当成自己的污染去"复原"就是回退事故。

顺带记一条本轮观察到的**存量数据形态**（登记不改）：该项目 `八、1` 的 `受限制的货币资金明细` 现为 8 行且 `银行承兑汇票保证金` 出现两次 —— 因其 `E1-disclosure-soe-restricted` 是 **2026-07-27（Task 23 之前）** 存的 5 条 legacy 行（只有 `item` 无 `bucketKey`），`E1TabDisclosure.loadRestricted()` 按设计把它们转成 `customBucketKey(item)`（注释「不丢审计师已录入的数据」）⇒ 自定义桶无 `displayOrder`、排序键取 `?? 999` 落到末尾，与四表新归集出的同名声明桶并存。属**存量数据 × 向后兼容**的产物，非当前代码缺陷，与已登记的「E1-10 口径不一致」同族，可并入那个回填 spec。

#### 七、清理清单

**删除（276 个，全部是本 spec 自己的 `_wip_e_*` 诊断产物）**：`backend/scripts/diagnose/_wip_e_*` **274** 个（含任务原文点名的 `_wip_e_t22_readmut.py`，以及 `_wip_e_t22_{anchor,baseline,basenote,env,fe_final,m21,m21b,note,restore,seq,snap,snap_before}*` 与 t2~t24 各轮探针）+ 仓库根 `_wip_e_fx.txt` / `_wip_e_t10chk.txt` **2** 个。归属判据 = 名字前缀 `_wip_e_` + 内容关键词（抽样 5 个逐个读首行：E1 探针 / E 循环守卫名抽取 / Task 21 docx 复核 / 读 `mutate_e_cycle_guards` 变异范式 / Task 24 披露主表探针）+ mtime 落在本 spec 各 Wave（08-08 ~ 08-10）。删后独立复扫 `_wip_e_*` = **0**、`*.mutbak` = **0**。

**保留（逐条给理由）**：

| 未删项 | 理由 |
|---|---|
| `backend/scripts/diagnose/mutate_e_cycle_guards.py` | Task 20 **交付物**（29 条变异 + 覆盖面 tally），非诊断中间产物 |
| `backend/scripts/diagnose/verify_e1_account_extraction_live.py` + `_verify_e1_account_extraction_live.txt` | Task 6 **交付物**及其运行输出，Task 21 两轮均引它作证据 |
| `audit-platform/frontend/tmp_t22_base.json` | 🔴 **名字带 t22 但不是本 spec 的** —— 读内容确认 16 个 suite 全是 `procedureTrimDecision` / `ProcedureTrimming.twoLayer` / `delegation*` / `trimAdequacyReview`，属 `procedure-trimming-and-delegation-intelligence` spec 的 Task 22（mtime 2026-08-11 07:56，本 spec 那两天无活动）。正是「按文件名里的任务号误删」的陷阱 |
| 根目录 `tmp_t26_*` / `tmp_3way_*` / `tmp_g7_*` / `tmp_t18_*` / `tmp_mem_*` 等 | 他 spec / 并发会话在用（`tmp_g7_*` 属 g7 spec、`tmp_3way_*` 与 `tmp_t18_*` 按 mtime 属 08-10 并发会话） |
| `backend/scripts/diagnose/_wip_mut_step1*` / `_wip_mutate_*` / 根 `_wip_mut_matrix.log` | 名字像变异脚本但**内容零 `e1`/`E1` 命中**，`_wip_mut_matrix.log` mtime 2026-08-06（早于本 spec 开工）⇒ 非本 spec |
| `backend/scripts/diagnose/_wip_t4_*` / `_wip_t5_*` / `_wip_t9v_*` / `_wip_task2_*` 等无 `e_` 段的 | 前缀不含 `_wip_e_`，按归属判据不属本 spec |
| `backend/app/routers/wp_template.py.bak` · `backend/data/procedure_table_templates.json.bak` | Task 20 已登记属他 spec/并发会话，**继续未触碰** |

**本轮自己的临时产物**：dev server（vite，3030 已被并发会话占用 ⇒ 本轮用 **3031**）会话末已停；三个回归输出 `tmp_e_t22_be.txt` / `tmp_e_t22_fe.json` / `tmp_e_t22_fe.log` 已删。工作树无本轮新建的 `tmp_*` / `_wip_*`。

#### 八、收尾回归（与冻结基线逐条相同）

| 范围 | 本轮实测 | 冻结基线 | 判定 |
|---|---|---|---|
| 后端 `backend/tests/four_table -k "e1 or e_cycle"` | **368 passed / 1 skipped / 1704 deselected / 0 failed**（6.93s） | `BASELINE_BE_PASSED = 368` | 相符 |
| 前端 `npx vitest run e1 E1 --reporter=json` | **137 suites / 137 passed suites / 568 tests / 568 passed / 0 failed**，`success=true`、失败名集合空集 | `BASELINE_FE_PASSED = 568` | 相符 |

本轮**生产代码与数据文件零改动**（仅本文件追加本节 + 删除 276 个本 spec 诊断产物）。

#### 九、被推翻 / 被修正的判断（本轮新增）

| 出处 | 原文写的 | 本轮实证 | 处置 |
|---|---|---|---|
| tasks.md Task 22 验证项 | 「E1-3 …且原币/汇率列**留空**」 | 对**非本位币**成立（fx 列全 0 + note 提示，M19 锁死）；对**本位币**不成立且**必须不成立**（不下发 `openingFc` 会被 multi recalc 抹零）。载荷侧根本无原币字段可反推 | 判据按 design.md Property 34 + Task 8 实录的「恒等 vs 反推」二分执行；本行文字已被实践推翻 |
| tasks.md Task 22 验证项 | 「E1-4 显示**「本项目无此科目」**」 | E1-4 页面无该字面 —— 该文案是 Task 24 给披露主表 `endingResolved=false` 行的 tooltip。E1-4 的实际口径 = 无取数面板 + 1 空行 + 合计全 `-` | 口径判据成立，字面表述登记纠正 |
| 「实录之三」 | 「附注 `八、1` 基线是 5 行不是 6 行（`0ec33ac9` 推送记录早于 Task 15）」 | 该项目已于 2026-08-12 02:08:30 被并发会话重新推送，现为 **6 行**且行序/字面与 docx 一致 | 基线已刷新；「6 行」判据现在在**两个**项目上都成立 |
| 「实录之三」的复原基线 | `0ec33ac9/八、1` md5 = `037f65ce…` | 现为 `826110978f…`（并发会话 02:08:30 推送所致，非本会话） | **不回退**。跨会话复原前必须先判差异归属 |
| Task 8 实录的处置表（`multi` 版恒等下发） | 隐含「照此实现后 multi 版就正确了」 | 只在「**先打开 multi 版**」时正确；先打开 rmb 版会让 multi 版金额全被抹零（宿主种子形态一会话内只定型一次） | 登记为**新缺陷**（第三节），另立任务修；本轮不改 |

