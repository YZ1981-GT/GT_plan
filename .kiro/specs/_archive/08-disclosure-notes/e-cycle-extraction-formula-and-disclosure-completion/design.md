# Design Document

## Overview

本 spec 只做**加法与纠错**，不重建任何已通的链路。改动分四条互不重叠的轴：

| 轴 | 落点 | 依赖 |
|---|---|---|
| A. 账户级取数 | 新建后端共享件 + render 加法式注入 + 宿主种子化扩展 | 无 |
| B. 公式预设 | 幂等脚本 + 无预设登记表 | 无 |
| C. 附注结构 | 幂等脚本改两份 note_template JSON | 无 |
| D. 披露逻辑与动态行 | 前端受限链路双源 + 自定义类别 UI | **无数据依赖**（见下） |

🔴 **D 对 A 的依赖是 UX 而非数据** —— `tb_aux_balance` **没有受限金额字段**，L2 逐户归集读的是审计师在 E1-3 手填的 `restrictedAmount`/`restrictedReason`（源模板 AJ/AK 列，两字段早在 `USER_FIELDS` 里）。A 只是让 E1-3 有账户行可填。故 Wave 5 不因 Wave 2/3 未完成而阻塞（R8.8）。

### 关键设计判断（五条，均有实证支撑）

**判断 1：账户级取数是「新增第二数据源」而不是「替换 tb_balance 叶子」**

`tb_balance` 叶子给的是**科目级**金额（客户 1002 不分户 ⇒ 1 行），`tb_aux_balance` 的 `银行账户` 维度给的是**账户级**明细。两者勾稽成立（8/8 项目逐分相等）但粒度不同，都要保留：

- 科目级 → 审定表 TB 核对基准（`tb_amount`）、披露主表行、`parent_check` 自检
- 账户级 → E1-3 逐户列示、E1-10 完整性核对、受限金额逐户归集

⇒ render 输出**新增** `account_prefill` 键，既有 `four_table_prefill` **逐字不变**（零回归的结构性保证）。aux 侧无数据时 `account_prefill.accounts = []`，前端退回既有口径。

**判断 2：`aux_dimensions_raw` 解析必须容错到「只要账号」**

实测格式 `金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296`，但这是**客户导出习惯**不是平台契约（`aux_code` 全库为 NULL 已说明各账套导出差异大）。故解析器三级降级：

1. 能解析出 `银行账户:` 与 `金融机构:` → 账号 + 银行名俱全
2. 只解析出 `银行账户:` → 账号有、银行名留空
3. 完全解析不出 → 账号取 `aux_name`、银行名留空

**任何一级都不臆造银行名**。银行名缺失由审计师补或由 E0-3 发函记录带入。

**判断 3：账户级聚合必须在 active dataset 内按账号 GROUP BY**

两个实测坑叠加：非 active dataset 有**完全重复行**（同 `aux_dimensions_raw` 两行、`closing_balance` 相同）；active 内**同账号可有多行**（`a7fc75e5` 的 `1207014210004455` 有 ±25,954,468.80 两笔）。

⇒ 查询走 `get_active_filter`（禁裸写），聚合按解析出的账号键 GROUP BY + `SUM(COALESCE(...,0))`。守卫用「不带 dataset 过滤必翻倍」做反向自检。

**判断 4：附注行集以 docx 为准、底稿字面以 xlsx 为准，两者靠 `noteLabel` 投影桥接**

soe 首行底稿 xlsx 是 `现金`、附注 docx 是 `库存现金`。平台既有范式（合计行 `合  计` → `合计`）就是双口径：底稿 UI 用源模板字面、推送时投影成附注字面。故 `E1MainRowDef` 新增可选 `noteLabel`，`buildE1SyncPayload` 用 `r.noteLabel ?? r.label`。

**判断 5：受限桶新增项的声明位置由「不得抢夺既有分类」反推**

新桶关键词 `法定存款准备金` / `备付金` 与既有 6 桶无交集（既有兜底桶 `other` 的关键词是 `保证金/受限/限制/专户/专项存款/监管`，都不含「准备金」「备付金」）。但**顺序即优先级**，声明在 `other` 之前才能生效。守卫必须断言「新增桶后既有 6 项目的自动分类结果逐条不变」。

## Architecture

### 数据流（改造后，新增部分标 ★）

```
四表入库
  ├─ tb_balance ──→ semantic_account_resolver(5 槽) ──→ select_leaves
  │                          │                            │
  │                          │                            ├─→ build_e1_detail_rows(5 槽) ★扩槽
  │                          │                            ├─→ build_e1_tb_values
  │                          │                            ├─→ build_e1_adjudication_prefill
  │                          │                            ├─→ build_e1_restricted_prefill
  │                          │                            └─→ build_e1_parent_check
  │                          │
  └─ tb_aux_balance ★ ──→ fetch_e1_bank_accounts(get_active_filter) ★
                                     │
                                     ├─→ parse_aux_dimensions() ★  账号 + 银行名
                                     ├─→ 按账号 GROUP BY 聚合 ★
                                     ├─→ 按槽前缀归属（bank/other/unassigned）★
                                     └─→ build_e1_account_prefill() ★
                                              │
                                     与 tb_balance 叶子勾稽自检 ★
                                              ↓
                            render html_data.account_prefill ★
                                              ↓
              宿主 GtE1MonetaryFund.seedFromFourTable()
                    ├─ E1-cash-detail-rows            （既有）
                    ├─ E1-bank-detail-rows            （★改为账户级优先、叶子兜底）
                    ├─ E1-account-list-rows           （★改为账户级优先）
                    ├─ E1-digital-detail-rows  ★新增
                    └─ 跨 sheet 聚合键                 （既有）
                                              ↓
                                    各子 Tab（:all-responses）
                                              ↓
              E1TabDisclosure ──→ buildE1SyncPayload  ──→ 附注 五、1 / 八、1
                             └──→ buildE1FxSyncPayload ──→ 附注 五、73 / 八、92（BS-002 段）
```

### 账户级取数的归属规则（三态，禁兜底）

| 情形 | 归属 | 前端呈现 |
|---|---|---|
| 账户的 `account_code` 命中 `bank` 槽前缀 | `accounts.bank[]` | E1-3「银行：」段 |
| 命中 `other` 槽前缀 | `accounts.other[]` | E1-3「其他货币资金：」段 |
| 命中 `finance_co` 槽前缀 | `accounts.finance_co[]` | E1-3「其他金融机构（存放财务公司款项）：」段 |
| 都不命中 | `accounts.unassigned[]` | 面板提示「未归属账户」交审计师处置 |

`unassigned` **不静默丢弃也不塞进任一段** —— 它是「aux 里有账户但科目定位没覆盖」的诚实信号（可能是客户把货币资金挂在别的科目上）。

### 两个受限取数链路的关系（R8）

源模板 soe 受限表的原始公式是按 **E1-3 的 D 列「账户性质/主要用途」** SUMIF 归集：

```
=SUMIF(E1-3!$D$23:$D$28, A17, E1-3!$AB$23:$AB$28) + SUMIF(E1-3!$D$38:$D$40, A17, ...)
```

而平台现状是按 **`tb_balance` 叶子科目名**自动分类。两者是**互补**不是替代：

| 链路 | 粒度 | 优点 | 局限 |
|---|---|---|---|
| L1 四表叶子按科目名（现状） | 科目级 | 全自动、四表入库即有 | 客户科目名不含受限词时全落待归类 |
| L2 E1-3 逐户受限金额/原因（源模板口径）★ | 账户级 | 忠实源模板、可追溯到账户 | 需审计师先在 E1-3 填 |

⇒ 两条并存，勾稽面板如实暴露差异，**不自动取其一**（审计判断）。L2 依赖 R1 的账户级取数落地。

### 附注结构改动的三处落点（必须同时改，缺一即分叉）

| 落点 | 内容 | 脚本 |
|---|---|---|
| `note_template_soe.json` 八、1 | 首行 `现金`→`库存现金`、补境外行、受限表补第 6 类 | `fix_note_e1_monetary_fund_structure.py`（扩展既有） |
| `note_template_listed.json` 五、1 | 受限表补第 6 类 | 同上 |
| `note_template_soe.json` 八、92 | 短期借款段 `BS-031`→`BS-041` | 同上 |

派生清单 `note_shared_table_segments.json` 由 `gen_note_shared_table_segments.py --write` 重生成。

## Components and Interfaces

### 组件 1：`backend/app/services/four_table/e1_bank_accounts.py`（新建，后端共享件）

账户级取数的唯一真源。纯函数 + 一条查询。

```python
@dataclass(frozen=True)
class AuxDimensions:
    """`aux_dimensions_raw` 的解析结果（三级降级，任何一级都不臆造银行名）。"""
    account_no: str          # 银行账号；解析不出时取 aux_name
    bank_name: str           # 开户银行；解析不出时为 ""
    bank_code: str           # 金融机构编码（如 YG0014）；无则 ""
    parsed_level: int        # 1=账号+银行名 / 2=仅账号 / 3=完全靠 aux_name 兜底

def parse_aux_dimensions(raw: str | None, aux_name: str | None) -> AuxDimensions:
    """解析 `金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296`。纯函数。"""

@dataclass(frozen=True)
class BankAccountRow:
    account_code: str        # 会计科目码（1002 / 1012.02 ...）
    account_no: str
    bank_name: str
    currency: str
    opening: float
    debit: float
    credit: float
    closing: float
    slot: str                # bank / other / finance_co / ""（未归属）
    source: str              # "tb_aux_balance:银行账户:{账号}"
    parsed_level: int

async def fetch_e1_bank_accounts(
    db, project_id, year: int, *, account_prefixes: Sequence[str]
) -> list[BankAccountRow]:
    """查 `aux_type='银行账户'` 的账户级明细。

    🔴 四条硬约束：
    - **`await get_active_filter(...)`** —— 它是 `async def`（`app.services.dataset_query`，
      签名 `(db, table, project_id, year, *, force_dataset_id=None, current_user_id=None)`）。
      漏 `await` → `sa.and_(coroutine, ...)` 抛异常 → 被下面的 fail-open 吞成 warning →
      **账户级清单恒空且与「本项目无 aux 数据」不可区分**。N5 与 D 循环各因此出过一次 P0。
    - 禁裸写 `is_deleted == False` —— 非 active dataset 有完全重复行，裸查必翻倍
    - 按解析出的 `(account_code, account_no)` GROUP BY 求和（active 内同账号可多行）
    - 金额一律 `COALESCE(...,0)`（`closing_balance` 可为 NULL 而非 0）

    fail-open：查询失败返 [] 并 warning + rollback（不阻断底稿打开）。
    """

def assign_accounts_to_slots(
    rows: Sequence[BankAccountRow], accounts
) -> dict[str, list[BankAccountRow]]:
    """按语义槽的原始码前缀归属；都不命中的进 `unassigned`。纯函数。

    禁兜底：`unassigned` 既不丢弃也不塞进任一段。
    """

def check_accounts_vs_leaves(
    slot_accounts: Mapping[str, Sequence[BankAccountRow]],
    slot_leaves: Mapping[str, Sequence[LeafRow]],
) -> dict[str, dict[str, float]]:
    """账户级合计 vs tb_balance 叶子合计勾稽。纯函数。

    不平时如实暴露 `{slot: {account_sum, leaf_sum, diff}}`，**不修正数据**
    （aux 与 tb_balance 是两个导入口，差异本身是数据质量信号）。
    """

def build_e1_account_prefill(
    slot_accounts, slot_leaves
) -> dict:
    """render 下发载荷。

    Returns:
        ``{accounts: {bank: [...], other: [...], finance_co: [...], unassigned: [...]},
        reconcile: {...}, meta: {source, account_count, parsed_level_dist}}``
    """
```

### 组件 2：`_e1_monetary_fund.py` render（加法式改造）

三处改动，既有输出**逐字不变**：

1. `_DETAIL_SLOT_KEYS` 扩至 5 槽（`+ E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL`）—— R2.1
2. `_build_four_table_extraction()` 末尾新增 `account_prefill`（调组件 1）—— R1
3. 返回 dict 新增 `"account_prefill"` 键 —— R1.8

**零回归支点**：`build_e1_detail_rows` 的字段与顺序不变；扩槽只让 dict 多两个键（`digital`/`finance_co`），既有前端按 `cash`/`bank`/`other` 取值不受影响。

### 组件 3：`e1BankAccountPrefill.ts`（新建，前端归一层）

```ts
export interface E1AccountRow {
  accountCode: string; accountNo: string; bankName: string; currency: string
  opening: number; debit: number; credit: number; closing: number
  slot: string; source: string; parsedLevel: number
}
export interface E1AccountPrefill {
  accounts: { bank: E1AccountRow[]; other: E1AccountRow[]
              finance_co: E1AccountRow[]; unassigned: E1AccountRow[] }
  reconcile: Record<string, { account_sum: number; leaf_sum: number; diff: number }>
  meta: Record<string, unknown>
}
export function normalizeAccountPrefill(raw: unknown): E1AccountPrefill

/** E1-3 种子行：账户级优先，无账户时返 null 由调用方退回叶子口径。 */
export function buildBankSeedRowsFromAccounts(p: E1AccountPrefill): Record<string, unknown>[] | null

/** E1-10 种子行：**保留零余额账户**（完整性核对红线）。 */
export function buildAccountListSeedRowsFromAccounts(p: E1AccountPrefill): Record<string, unknown>[] | null

/** E1-4 数字货币明细种子（来自 digital 槽的 four_table_prefill）。 */
export function buildDigitalSeedRows(prefill: FourTablePrefill): Record<string, unknown>[] | null
```

**行 id 前缀必须与既有叶子口径区分**（`bank-principal-{group}-acct-{账号}` vs 既有 `...-ft-{科目码}`），否则两种口径的种子行会撞 key。

### 组件 4：`GtE1MonetaryFund.vue` 宿主（改造）

```
seedFromFourTable():
  bankSeed = buildBankSeedRowsFromAccounts(accountPrefill)     ★账户级优先
           ?? buildBankSeedRows(fourTablePrefill)              （既有叶子兜底）
  acctSeed = buildAccountListSeedRowsFromAccounts(accountPrefill)
           ?? buildAccountListSeedRows(fourTablePrefill)
  seedRowsKey('E1-digital-detail-rows', buildDigitalSeedRows(fourTablePrefill))  ★新增
```

`ftRowsKey` / **`reExtractFromFourTable()`**（🔴 真实函数名，宿主里没有 `refetchFromFourTable` —— 按后者写守卫会 0 命中空转）的 sheet 分支同步加 `E1-4`，并让 `E1-3`/`E1-10` 走账户级优先。

宿主既有函数全集（实测）：`openHandbook` / `openFormulaManager` / `seedRowsKey` / `seedFromFourTable` / `reconcileCashAggregateFromRows` / `reExtractFromFourTable` / `saveImmediate` / `debouncedSave`。`ftRowsKey` 现只映射 `E1-2`/`E1-3`/`E1-10` 三张。

### 组件 5：`E1FourTableSourcePanel.vue`（扩展）

新增两块：账户级取数溯源（账户数 / `parsed_level` 分布 / 勾稽差异）+ `unassigned` 告警。

`parsed_level` 分布是**数据质量指标**：level 3 占比高说明该客户的 `aux_dimensions_raw` 格式与预期不同，提示审计师核对账号列。

### 组件 6：`fix_e1_prefill_presets.py`（扩展既有幂等脚本）

三类修正 + 一张登记表：

1. E0 块 `sheet`/`wp_name` 纠正 —— R3.1
2. 新增 E1-6 / E1-10 / E1-21 / E1-22 / E1-23 预设块 —— R3.2
3. `E1_SHEETS_WITHOUT_PRESET`：无预设 sheet 的显式登记（每条带理由）—— R3.3

```python
E1_SHEETS_WITHOUT_PRESET: dict[str, str] = {
    "调整分录汇总E1-5": "调整分录由 AJE/RJE 模块产生，四表无对应取数",
    "库存现金（人民币）盘点表E1-7": "监盘实施记录，账面数在 E1-2，盘点数只能现场录入",
    "库存现金（外币）盘点表E1-8": "同 E1-7，另需原币与折算率",
    "银行存单盘点表E1-9": "存单实物监盘记录，四表无存单维度",
    "银行账户情况承诺E1-11": "管理层书面承诺，非取数表",
    "企业信用报告信息查询记录E1-18": "外部征信查询记录，四表无此数据",
    "企业信用报告信息与账面核对记录E1-19": "征信 vs 账面核对，征信侧靠 OCR/手工",
    # E0-2~E0-8 七张函证 sheet：函证过程记录，数据源是回函而非四表
}
```

守卫断言「E 类每个 visible sheet 要么有预设块、要么在登记表里」——**这样新增 sheet 时会自动打红**，不会静默漏掉。

### 组件 7：`fix_note_e1_monetary_fund_structure.py`（扩展既有幂等脚本）

四处 additive 修正：

| # | 章节 | 修正 |
|---|---|---|
| 1 | soe 八、1 主表 | 首行 label `现金` → `库存现金` |
| 2 | soe 八、1 主表 | 合计行后补 `其中：存放在境外的款项总额`（`row_type: data`，不带 `is_total`）|
| 3 | 两版受限表 | 合计行前补 `金融企业法定存款准备金或备付金` |
| 4 | soe 八、92 | 短期借款段首行 `report_row_code` `BS-031` → `BS-041` |

改完必须重跑 `gen_note_shared_table_segments.py --write`。

### 组件 8：`e1DisclosureScope.ts` / `e1NoteSectionMap.ts`（改造）

- `E1MainRowDef` 新增 `noteLabel?: string` —— R5.4
- `E1_MAIN_ROWS_SOE` 首行加 `noteLabel: '库存现金'`，末尾补 `overseas` 行（`isMemo: true`，`sourceRef: '（源 docx soe 货币资金表 r6；源 xlsx 无该行）'`）
- `buildE1SyncPayload` 的 `mainRow()` 改用 `r.noteLabel ?? r.label`
- `E1_RESTRICTED_TABLE` 行序按源 docx 6 类顺序输出

### 组件 9：`e1_restricted_buckets.py`（新增第 6 源类桶 + 展示序分离）

```python
E1RestrictedBucket(
    key="statutory_reserve",
    label="金融企业法定存款准备金或备付金",
    keywords=("法定存款准备金", "备付金", "存款准备金"),
    source_ref="附注披露信息(国企)!A22",   # 与既有 5 桶同域；docx 侧为 soe 受限表 r6
),
```

声明位置：`pledged_deposit` 之后、`other` 之前（`other` 兜底桶必须始终最后）。改造后共 **7 桶** = 6 个源类 + 1 个平台兜底。

**🔴 展示序必须与优先级序分离（R6.7 / R6.8）**

现状是**一份顺序被两个语义共用**，且两者实际不同：

| # | `E1_RESTRICTED_BUCKETS` 声明序（= 匹配优先级） | docx / 模板行序（= 展示序） |
|---|---|---|
| 1 | `letter_of_credit` 信用证保证金 | 银行承兑汇票保证金 |
| 2 | `bank_acceptance` 银行承兑汇票保证金 | 信用证保证金 |
| 3 | `performance` 履约保证金 | 履约保证金 |
| 4 | `overseas` 放在境外且资金汇回受到限制的款项 | 用于担保的定期存款或通知存款 |
| 5 | `pledged_deposit` 用于担保的定期存款或通知存款 | 放在境外且资金汇回受到限制的款项 |
| 6 | `other` 其他受限资金（**docx 与模板均无此行**） | 金融企业法定存款准备金或备付金（新增） |

优先级序有硬理由不能改（「信用证保证金」含「保证金」必须先于兜底桶；「境外冻结存款」同含「冻结」与「境外」，境外须优先），而前端 `e1RestrictedScope` 的推送排序用的正是 `bucketDefs` 数组索引 ⇒ **附注行序与 docx 不符**。

**落法（零新增字段）**：`source_ref` 的单元格行号本身就是 docx 行序（现值 `A17`/`A18`/`A19`/`A20`/`A21` ↔ 银行承兑/信用证/履约/担保定期/境外，新桶 `A22`）⇒ `bucket_defs_payload()` 增发 `displayOrder`（源类桶按 `source_ref` 行号升序、平台补充桶排最后），前端排序改用它。

守卫**双向锁死**：① 打乱 `E1_RESTRICTED_BUCKETS` 声明顺序 → 分类结果必红、展示序不变；② 改 `source_ref` 行号 → 展示序必红、分类结果不变。并**诚实改写**既有用例 `行序按后端 bucketDefs 声明顺序（与源模板行序一致）`（其标题声称的等价关系本就不成立）。

**行序契约的正确表述**（R6.8）：`docx 六类（按 docx 序）+ 平台补充桶 + 合计行`，不是「== docx r1~r6」。

### 组件 10：受限双链路与自定义类别 UI（`E1TabDisclosure.vue` + `e1RestrictedScope.ts`）

- 新增 `resolveRestrictedFromAccounts(accountPrefill, e13Rows)`：按 E1-3 逐户「受限金额 + 受限原因 + 账户性质」归集（L2 链路）—— R8.1
- 勾稽面板新增「L1 四表分类合计 vs L2 逐户归集合计」对比行 —— R8.2
- 「+ 新增受限类别」按钮：`ElMessageBox.prompt` 输入类别名 → `customBucketKey()` —— R9.1
- 自定义类别序号走持久化单调计数器 `E1-disclosure-{variant}-restricted-seq` —— R9.2
- 待归类面板把「无子科目的父科目行」与「真明细行」分区展示 —— R8.4

## Data Models

### 无 DB 迁移

本 spec **不新增任何表或列**。账户级数据全部来自既有 `tb_aux_balance`（列已齐备：`aux_type` / `aux_name` / `aux_dimensions_raw` / `currency_code` / `opening_balance` / `debit_amount` / `credit_amount` / `closing_balance` / `dataset_id` / `is_deleted`）。

### `tb_aux_balance` 相关列的实测语义

| 列 | 实测事实 | 取数含义 |
|---|---|---|
| `aux_type` | 全库 33 种；E 类用 `银行账户`（308 行/114 名）与 `金融机构`（1442 行/45 名） | 按维度**冗余存储**，同一笔余额在多维度各存一份 ⇒ **禁跨 aux_type 求和** |
| `aux_code` | **全库为 NULL** | 不能作标识，只能用 `aux_name` |
| `aux_name` | `银行账户` 维度下是**银行账号**（18~23 位数字）；`金融机构` 维度下是**银行名称** | 两个维度的同名字段语义不同 |
| `aux_dimensions_raw` | `金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296` | **一行含全部维度** ⇒ 只查 `银行账户` 维度即可拿到银行名 |
| `closing_balance` | 可为 **NULL**（不是 0） | 聚合必须 `COALESCE` |
| `dataset_id` | 非 active 版本有**完全重复行** | 必须 `await get_active_filter(...)` |
| `currency_code` | `String(3)` NOT NULL 默认 `'CNY'`；`银行账户` 维度下 **308 行全为 CNY** | 外币账户提示分支当前 0 命中 = 潜伏态 |
| `opening_fc` | 存在但 `银行账户` 维度下**全库为 NULL** | 原币期初无数据源 |
| 期末原币 / 汇率 | **列根本不存在**（只有 `opening_fc`，无 `closing_fc`、无 rate 列） | `fxRate`/`openingFc` 等**只能留空**，禁由本位币金额反推 |

### render 输出契约（新增键，additive）

```jsonc
{
  "account_prefill": {
    "accounts": {
      "bank":        [{ "accountCode": "1002", "accountNo": "58080155200000296",
                        "bankName": "上海浦东发展银行", "currency": "CNY",
                        "opening": 95.0, "debit": 5694002.1, "credit": 5693101.99,
                        "closing": 995.11, "slot": "bank",
                        "source": "tb_aux_balance:银行账户:58080155200000296",
                        "parsedLevel": 1 }],
      "other":       [/* 同构 */],
      "finance_co":  [/* 同构 */],
      "unassigned":  [/* 同构，slot="" */]
    },
    "reconcile": {
      "bank":  { "account_sum": 4703056.26, "leaf_sum": 4703056.26, "diff": 0.0 },
      "other": { "account_sum": 4479140.0,  "leaf_sum": 4479140.0,  "diff": 0.0 }
    },
    "meta": { "source": "tb_aux_balance:银行账户", "account_count": 27,
              "parsed_level_dist": { "1": 27, "2": 0, "3": 0 } }
  }
}
```

### `note_template_*.json` 改动（additive，四处）

```jsonc
// soe 八、1 tables[0].rows —— 首行改字面 + 末尾补行
[ { "label": "库存现金", "row_type": "data", "account_codes": ["1001"] },   // 原 "现金"
  { "label": "银行存款", ... }, { "label": "其他货币资金", ... },
  { "label": "数字货币", ... },
  { "label": "合计", "is_total": true, "row_type": "total" },
  { "label": "其中：存放在境外的款项总额", "row_type": "data", "account_codes": [] } ]  // 新增

// 两版受限表 tables[1].rows —— 合计行前插第 6 类
  { "label": "金融企业法定存款准备金或备付金", "row_type": "data" },   // 新增

// soe 八、92 tables[0].rows[10] —— 段首行 row_code 纠正
  { "label": "短期借款", "account_codes": ["2001"],
    "report_row_code": "BS-041",  // 原 "BS-031"（使用权资产）
    "row_type": "data" }
```

## Error Handling

| 情形 | 处置 | 理由 |
|---|---|---|
| `tb_aux_balance` 查询失败 | fail-open：返 `[]` + warning + rollback | 取数失败不阻断底稿打开（既有 render 范式） |
| `aux_dimensions_raw` 解析失败 | 降级到 `parsed_level=3`（账号取 `aux_name`）| 宁缺勿造，不臆造银行名 |
| 账户级合计与叶子不平 | 如实写入 `reconcile.diff` + UI 告警 | aux 与 tb_balance 是两个导入口，差异是数据质量信号，**不修正** |
| 账户归属不了任何槽 | 进 `unassigned` + UI 提示 | 既不丢弃也不塞进任一段 |
| `digital`/`finance_co` 槽 `found=False` | 明细返 `[]`，UI 显示「本项目无此科目」 | 与「余额为 0」必须可区分 |
| 银行存款期末为负 | 如实显示 + 异常提示 | 实测 `a7fc75e5` = −297,771,168.89，取绝对值会掩盖真实情况 |
| 附注章节改动对存量项目 | 只影响新建/重新生成 | 不做破坏性回填（平台既有语义） |
| 幂等脚本 `--check` 有欠账 | rc≠0 + ASCII 报告 | 禁 emoji（GBK 崩） |

## Testing Strategy

### 后端守卫（新建 3 个文件 + 扩展 2 个）

| 文件 | 内容 |
|---|---|
| `tests/four_table/test_e1_bank_accounts.py`（新建）| `parse_aux_dimensions` 三级降级 + 聚合 + 槽归属 + 勾稽 + PBT（任意账号集合下「各槽合计之和 == 全部账户合计」）|
| `tests/four_table/test_e1_bank_accounts_live.py`（新建，连库）| 真实库至少 1 项目命中账户级数据；aux 合计 == `tb_balance` 叶子；**反向自检：不带 dataset 过滤必翻倍** |
| `tests/four_table/test_e1_preset_coverage.py`（新建）| E 类每个 visible sheet 要么有预设块要么在 `E1_SHEETS_WITHOUT_PRESET`；预设 `sheet` 字面 openpyxl 直读比对；明细块禁 `WP()` 引审定表；脚本源码禁非 ASCII print |
| `tests/four_table/test_note_e1_structure.py`（扩展）| 新增：soe 八、1 六行 + 首行 `库存现金`；受限表六类 + 平台桶 + 合计；八、92 段 row_code 与 `report_config` 对账；**反向锁死 `BS-031` 仍归 H8**；listed docx 该标题下表格数 == 1（Property 37）；soe 主表缺两行的登记（Property 41）|
| `tests/four_table/test_e1_restricted_buckets.py`（扩展）| 新桶 + 「既有 6 项目分类结果逐条不变」+ 打乱顺序反向自检 + **`displayOrder` 与优先级序双向锁死**（Property 36）|

### 前端守卫（新建 2 个 + 扩展 2 个）

| 文件 | 内容 |
|---|---|
| `e1BankAccountPrefill.spec.ts`（新建）| 归一 / 种子行构造 / 账户级优先与叶子兜底 / **行 id 前缀不撞 key** / E1-10 保留零余额 |
| `e1HostSeedWiring.spec.ts`（新建）| 读宿主源码断言：账户级优先链、`E1-digital-detail-rows` 已 seed、`refetchFromFourTable` 覆盖 E1-4；替身反向自检 |
| `e1NoteTextsAndPayload.spec.ts`（扩展）| `noteLabel` 投影（底稿 `现金` → 附注 `库存现金`）；soe 主表 6 行；**受限表行序 = docx 六类 + 平台桶 + 合计**（Property 20）；**L2 原因不进第 4 列**（Property 38）|
| `e1CurrencyScope.spec.ts`（**诚实改写**）| 三条锁定旧行为的断言：`E1_MAIN_ROWS_SOE` `toHaveLength(5)` → 6；`sourceRef` 序列补新行；`soe.some(r => r.key === 'overseas') === false` → `true`。改写理由写进用例注释（Property 41）|
| `e1RestrictedScope` 既有用例（**诚实改写**）| `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` —— 标题所声称的等价关系不成立，改为按 `displayOrder`（Property 36）|
| `e1DisclosureScope` 主表预填（新增）| 三个 `crossKey: ''` 行的语义槽预填 + `found=False` 不写 0 + 手工值不覆盖（Property 35）|
| `e1FxNoteSectionMap.spec.ts`（扩展）| 段归属注释表与模板 `BS-041` 交叉锁死 |

### 变异检验（强制，按失败测试名集合差集判定）

`backend/scripts/diagnose/mutate_e_cycle_guards.py`，≥10 个变异，每个必须让**预期那一条**断言打红：

1. `get_active_filter` 换成裸 `is_deleted == False` → 连库勾稽必红（翻倍）
2. 聚合去掉 `GROUP BY 账号` → `a7fc75e5` 账户数与合计必红
3. `COALESCE` 去掉 → NULL 传播必红
4. `parse_aux_dimensions` 解析失败时臆造银行名 → level 3 断言必红
5. `unassigned` 改成塞进 `bank` → 归属断言必红
6. `reconcile.diff` 改成自动修正数据 → 勾稽如实暴露断言必红
7. 新受限桶挪到 `other` 之后 → 分类失效必红
8. 新受限桶关键词加 `保证金` → 「既有分类逐条不变」必红
9. soe 主表首行改回 `现金` → docx 三向比对必红
10. 八、92 段 row_code 改回 `BS-031` → 与 `report_config` 对账必红
11. 幂等脚本 print 加回 emoji → 非 ASCII 守卫必红
12. E1-3 种子行 id 前缀改成与叶子口径相同 → 撞 key 断言必红
13. **去掉 `await get_active_filter`** → Property 39 源码断言必红 **且**连库勾稽必红（两处同时红才证明该判据有实质意义，只源码红说明连库守卫没覆盖）
14. **`displayOrder` 改回取 `bucketDefs` 数组索引** → Property 36 展示序断言必红、分类结果断言保持绿（证明两语义已分离）
15. **打乱 `E1_RESTRICTED_BUCKETS` 声明序** → 分类断言必红、`displayOrder` 断言保持绿（同上，方向相反）
16. **主表 `finance_co` 预填链删掉** → Property 35 必红（这条最容易被漏做成 dead output）
17. **主表 `finance_co` 槽 `found=False` 时写 0** → Property 35 的「不写 0」必红
18. **L2 归集给 ②表加第 4 列 `reason`** → Property 38 必红
19. **多版原币字段由本位币反推填值** → Property 34 的「都不带值」必红
20. **非数据表白名单加一条不存在的 sheet 名** → Property 40 的「白名单命中数 == 8」必红

**三态判定**：`new_fails` 非空 = RED 有效 / 空 = 守卫缺陷 / 锚点命中数 ≠ 1 = ANCHOR-MISS 脚本缺陷。备份必须落 `.bak` 且提供 `--restore`（只靠 `finally` 在本仓库并发度下不可靠）。

### 真实库验收

`backend/scripts/diagnose/verify_e1_account_extraction_live.py`（只读，默认 dry-run）：

- 8 项目 × 账户级取数逐项目输出：账户数 / `parsed_level` 分布 / 勾稽 diff / `unassigned` 数
- 判据：每个有 aux 数据的项目 `diff` 绝对值 ≤ 0.005；`unassigned` 非空时打印明细
- 无法验证时输出 `UNVERIFIABLE` 并写明原因，**禁用 fixture 冒充**

### 回归基线

| 范围 | 改动前基线 | 要求 |
|---|---|---|
| E1 四个既有后端守卫 | **132 passed** | 全绿 |
| 三个幂等脚本 `--check` | 0 欠账（第三个 rc=1 属 emoji 崩） | 0 欠账且 rc=0 |
| `backend/tests/four_table` 全量 | 需在动手前实测记录 | 失败集合逐条相同 |
| 前端 E1 相关 | 需在动手前实测记录 | 失败集合逐条相同 |

**零回归双证**：① 既有守卫全绿 ② 未触碰模块的失败集合逐条相同（用「前后对照」而非 HEAD-swap —— 本 spec 要改的 `note_template_*.json` 混着并发会话未提交成果，HEAD-swap 会抹掉它们）。

## Correctness Properties

### Property 1: 账户级查询必经 active dataset 过滤

任意项目，`fetch_e1_bank_accounts` 的结果合计与 `tb_balance` 对应科目叶子合计之差绝对值 ≤ 0.005；把查询改成裸 `is_deleted == False` 时该断言必红（非 active 版本有完全重复行）。

**Validates: Requirements 1.1, 1.5**

### Property 2: 同账号多行必聚合

对 active dataset 内同一 `(account_code, account_no)` 出现多行的项目（实测 `a7fc75e5` 的 `1207014210004455` 有 ±25,954,468.80 两笔），输出的账户行数 == 去重后账号数，且该账号金额 == 两笔之和。

**Validates: Requirements 1.3**

### Property 3: 维度解析三级降级且不臆造

`parse_aux_dimensions` 对完整串返 level 1（账号+银行名）、仅含 `银行账户:` 返 level 2（银行名为空串）、完全无法解析返 level 3（账号取 `aux_name`、银行名空串）。任何一级的 `bank_name` 都不得由账号推导。

**Validates: Requirements 1.2**

### Property 4: 账户归属三态且不兜底

每个账户行的 `slot` ∈ {`bank`, `other`, `finance_co`, `""`}；`slot == ""` 的行必须出现在 `unassigned` 且不出现在任何具名槽中；`unassigned` 与三个具名槽的并集 == 全部账户行（无丢弃）。

**Validates: Requirements 1.4**

### Property 5: 勾稽差异如实暴露不修正

构造 aux 合计与叶子合计不等的替身，`reconcile[slot].diff` 必须等于实际差额且 `account_sum` / `leaf_sum` 各自保持原值（不得任一侧被改写成另一侧）。

**Validates: Requirements 1.5**

### Property 6: E1-10 保留零余额账户而金额明细过滤

同一批账户输入下，`buildAccountListSeedRowsFromAccounts` 的行数 ≥ `buildBankSeedRowsFromAccounts` 的行数；且存在全零账户时前者含该账户、后者不含。

**Validates: Requirements 1.7**

### Property 7: 账户级种子的行 id 不与叶子口径撞键

`buildBankSeedRowsFromAccounts` 与既有 `buildBankSeedRows` 对同一项目产出的行 id 集合交集为空（前缀分别为 `-acct-` 与 `-ft-`）。

**Validates: Requirements 1.1, 11.3**

### Property 8: 账户级优先、叶子兜底、零回归

`account_prefill.accounts` 全空时，宿主种子化产出与改造前**逐字节相同**（走既有 `buildBankSeedRows` / `buildAccountListSeedRows`）。

**Validates: Requirements 1.6, 11.3, 11.6**

### Property 9: 扩槽后既有三槽输出不变

`_DETAIL_SLOT_KEYS` 扩至 5 槽后，`build_e1_detail_rows` 对同一输入产出的 `cash`/`bank`/`other` 三键的值与字段顺序**逐字节相同**，仅多出 `digital`/`finance_co` 两键。

**Validates: Requirements 2.1, 11.6**

### Property 10: 槽未命中返空而不产生零值行

`found=False` 的槽，其明细数组为 `[]`（长度 0），而不是含金额为 0 的占位行。

**Validates: Requirements 2.2, 2.5**

### Property 11: 预设 sheet 名与源 xlsx 逐字一致

E 类每个预设块的 `sheet` 值必须存在于对应源 xlsx 的 `wb.sheetnames`（openpyxl 直读）；`审定表E0-1` 这类不存在的 tab 名必须打红。

**Validates: Requirements 3.1, 3.4**

### Property 12: 预设覆盖面完备且无静默漏项

E 类每个 visible sheet 要么有预设块、要么在 `E1_SHEETS_WITHOUT_PRESET` 登记（理由 ≥ 15 字）；两个集合无交集；登记表条目数只许减不许增（新增 sheet 必须先有预设或显式登记）。

**Validates: Requirements 3.2, 3.3**

### Property 13: 明细表预设无环

明细表块的公式不得出现引用同 wp_code 审定表的 `WP()`；审定表块可引用明细表。

**Validates: Requirements 3.5**

### Property 14: 幂等脚本输出在 GBK 控制台下可编码

E 类幂等脚本中**能到达控制台**的字符串字面量（`print(` 的参数 + `changes.append(...)` 这类被后续 `print` 输出的收集器）必须满足 `s.encode('gbk')` 不抛异常。

🔴 **判据是 GBK 可编码性，不是「U+2000 以上非 CJK」** —— 实测 GBK **可**编码 `→` `≥` `—` `─` `【` `·`，**不可**编码 `✅` `❌` `⚠` `✔` `✓` `🔴` `░`。过宽口径会误伤安全字符串。docstring 与注释不进扫描面。配「中文汉字与 GBK 可编码符号不打红」的正向断言。

**Validates: Requirements 4.1, 4.3, 4.4, 4.5**

### Property 15: 幂等且 --check 归零

各幂等脚本二次 `--apply` 后目标文件 md5 不变；`--check` 在 0 欠账时 rc == 0。

**Validates: Requirements 3.6, 4.2**

### Property 16: soe 八、1 行集与源 docx 三向一致

源 docx（python-docx 直读）的行标签序列 == `note_template_soe.json` 八、1 主表 `rows[].label` 序列 == 同步载荷行标签序列（去空白归一后）。全部附注结构改动必须由幂等脚本落地，守卫直读源 docx 做三向比对（不接受手改 JSON）。

**Validates: Requirements 5.1, 5.2, 10.3**

### Property 17: 底稿字面与附注字面双口径

`E1_MAIN_ROWS_SOE` 首行 `label == '现金'`（源 xlsx）且 `noteLabel == '库存现金'`（源 docx）；`buildE1SyncPayload` 产出的行标签用 `noteLabel`。

**Validates: Requirements 5.4**

### Property 18: 境外款项行不参与合计

`overseas` 行标 `isMemo`，`e1SummableRows()` 不含它；合计行金额 == 各非 memo 非 total 行之和。

**Validates: Requirements 5.5**

### Property 19: listed 五、1 与外币表行集不变

listed 五、1 主表 8 行、两版外币表段数（listed 3 / soe 5）与行数（16 / 25）在本 spec 改动前后**逐字节相同**。

**Validates: Requirements 5.6, 11.4**

### Property 20: 受限表行序 = docx 六类 + 平台补充桶 + 合计

两版受限表的类别行序列 == `[soe docx 受限表 r1~r6 的标签（按 docx 序）] + [平台补充桶标签] + [合计]`。

🔴 **不得写成「== docx r1~r6」** —— 平台兜底桶 `other 其他受限资金` 在 docx 与模板行集里都没有对应行，但推送时会作为一行出现（确属受限却归不进六类的科目落这里），照 docx 六类断言会把正确实现打红。合计行仍在（源 docx 无该行，偏离依据写在 guidance）。

**Validates: Requirements 6.1, 6.4, 6.8**

### Property 21: 新受限桶不抢夺既有分类

用 6 个真实项目的全部货币资金叶子科目名跑 `classify_e1_restricted_leaf`，新增桶前后的分类结果**逐条相同**；把新桶挪到 `other` 之后时「法定存款准备金」类科目分类失效必红。

**Validates: Requirements 6.3, 11.5**

### Property 22: 桶中文名单一真源

前端源码不得出现受限桶的中文标签字面量；标签只从 `bucketDefs` 取。

**Validates: Requirements 6.5**

### Property 23: 外币段 row_code 与 report_config 对账

两版外币表每个段首行的 `report_row_code` 在 `report_config` 中的 `row_name`（四准则任一）与段 `label` 归一后相等；`短期借款` 段必须是 `BS-041`。改 row_code 时段首行的 `account_codes`（短期借款 = `['2001']`）必须**逐字不变**。

**Validates: Requirements 7.1, 7.2, 7.5**

### Property 24: BS-031 仍归 H8 使用权资产（反向锁死）

`report_config` 的 `BS-031` 四准则 `row_name` 均为 `使用权资产`；`h8_account_scope` / `dual_family_codes` 仍引用 `BS-031`。防日后把 H8 的码改成 `BS-041`。

**Validates: Requirements 7.6**

### Property 25: 派生段清单与模板一致

`note_shared_table_segments.json` 中外币表的段 `row_code` 序列 == 模板 `rows[].report_row_code` 序列；`find_segment(rows, 'BS-041')` 在 soe 侧返非 None。

**Validates: Requirements 7.4**

### Property 26: 受限双链路并存且差异如实暴露

L1（四表叶子分类）与 L2（E1-3 逐户归集）合计不等时，勾稽面板产出 diff 条目且两侧金额各自保留；代码中不得出现「取其一覆盖另一」的分支。

**Validates: Requirements 8.1, 8.2**

### Property 27: 负余额如实显示

银行存款期末为负的项目（实测 `a7fc75e5`），审定表与披露主表显示的金额为负值本身，且代码路径中该值不经过 `abs()`。

**Validates: Requirements 8.5**

### Property 28: 自定义类别 key 稳定且不复用序号

删除某自定义类别后再新增，新 key 的序号 > 历史最大序号（走持久化计数器）；朴素 `max+1` 实现必红。

**Validates: Requirements 9.1, 9.2**

### Property 29: 条件表语义区分 undefined 与空数组

`restrictedRows === undefined` 时不推该表且不进 `_removed_table_keys`；`=== []` 时不推且**进** `_removed_table_keys`。

**Validates: Requirements 9.4**

### Property 30: 附注 row_type 取值域不变

本 spec 改动后 `note_template_*.json` 的 `row_type` 取值集合仍为 {`data`, `total`, `subtotal`, `header_label`, `unowned`}（不引入 `expandable`）。

**Validates: Requirements 9.5**

### Property 31: 连库守卫不污染共享池

连库测试用一次 `asyncio.run` + 专用 `NullPool` 引擎并在同一 loop 内 `dispose()`；「victim 单独 / 本文件在前 / victim 在前」三种顺序下 victim 结果逐条相同。

**Validates: Requirements 10.1, 10.2**

### Property 32: 既有取数链路与数据契约不变

`e_cycle_specs` 的 5 槽定义、`E1-adj-total-1001/1002/1012` 键形态、三个既有种子键名在改动前后**逐字节相同**。

**Validates: Requirements 11.1, 11.2, 11.3**

### Property 33: 外币段推送按底稿实际币种动态产出

`aggregateE1FxByCurrency` 的输出币种集合 == 底稿外币行里出现的非记账本位币集合（保持首次出现顺序）；**源码**中不得出现写死的币种清单常量（如 `['美元','欧元','港币']`）。给底稿加一个模板里没有的币种（如「英镑」）时该币种必须出现在推送载荷里。

🔴 判据只约束**源码/推送侧**。附注模板 seed 侧的三行「其中：美元/欧元/港币」是**源 docx 事实**（listed docx r2~r4 甚至预填了 2025 年汇率中间价 7.0288 / 8.2355 / 0.90322），Property 19 已冻结其行数 ⇒ 不得为满足本条去删模板那三行。

**Validates: Requirements 9.3**

### Property 34: 账户级种子按 E1-3 variant 分流且不丢外币账户

`rmb` variant 下产出的种子行不含 `fxCurrency`；`multi` variant 下含。两个 variant 下产出的**账户条数相同**（外币账户在 `rmb` 版不被丢弃，只是不带 `fxCurrency`）。

🔴 **原币金额与汇率一律留空** —— `tb_aux_balance` 只有 `opening_fc` 一列且 `aux_type='银行账户'` 下全库为 NULL，**无 `closing_fc`、无汇率列**（308 行 `currency_code` 全 `CNY`）⇒ `fxRate`/`openingFc`/`increaseFc`/`decreaseFc`/`adjustmentFc` 不得由记账本位币金额反推，断言这些键在两版种子里**都不带值**。

「存在非记账本位币账户 → `rmb` 版产出提示信号」这一分支当前全库 0 命中（潜伏态，同 `digital`/`finance_co` 恒空同性质）⇒ 用替身构造 `currency_code='USD'` 的账户验证分支可达，并断言恒空时载荷形态仍合法。

**Validates: Requirements 1.9, 1.10**

### Property 35: 披露主表三个无科目码行由语义槽预填

`E1_MAIN_ROWS_LISTED` 中 `crossKey === ''` 的行恰为 `finance_co` / `accrued` / `digital` / `total` / `overseas`（后两个是合计与备注行）。前三行在对应语义槽 `found=True` 且该行无手工值时必须自动带入；槽 `found=False` 时保持空白而**不写 0**；已有手工值时不覆盖（persist-first）。

反向自检：删掉预填链后这三行恒空必红 —— 它们的注释已明文承诺「由 render 的语义槽预填」，当前零实现（未兑现的承诺）。

**Validates: Requirements 2.6, 2.7**

### Property 36: 受限桶展示序与优先级序双向锁死

① 打乱 `E1_RESTRICTED_BUCKETS` 声明顺序 → `classify_e1_restricted_leaf` 结果必红、`displayOrder` 序列不变；② 改**展示序真源** `E1_RESTRICTED_DOCX_ROW_ORDER` → `displayOrder` 序列必红、分类结果不变。两条互不牵连即证明两个语义已分离。

🔴 **落地时对本条初稿的偏离（2026-08-09 实证）**：初稿第②条写「改 `source_ref` 的单元格行号」，前提是 `displayOrder` 由 `source_ref` 行号升序派生。实测不可行 —— **第 6 桶 `statutory_reserve` 的真源是附注 docx 不是底稿 xlsx**（xlsx R17~R21 只 5 类、R22 是 `…` 动态插行标记，压根没有该行），docx 行号（`r6`）与 xlsx 行号（`A17~A21`）不在同一坐标系，混排会把它排到最前。故展示序真源改为显式元组 `E1_RESTRICTED_DOCX_ROW_ORDER`（仍是零新增 dataclass 字段），并**保留初稿的洞察作交叉锁**：五个 xlsx 源桶的元组顺序必须与其 `source_ref` 行号升序一致（两个独立口径互证，任一侧被改都打红）。

`displayOrder` 序列必须等于 docx 行序（源类桶按 `source_ref` 行号升序、平台补充桶排最后）。既有用例 `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` 必须被诚实改写（其标题声称的等价关系不成立）。

**Validates: Requirements 6.7, 6.9**

### Property 37: listed 受限表的偏离已显式登记

listed 源 docx「货币资金」标题下只有 1 张表（9×3 主表），受限内容是文字段落 ⇒ listed 受限表是平台补充表。守卫必须①断言该事实（python-docx 直读 listed docx 该标题下表格数 == 1）②断言 listed 侧**不存在**「与 listed docx 三向一致」这类断言（那条不可能成立）③偏离依据出现在 guidance 与守卫注释里。

**Validates: Requirements 6.6**

### Property 38: L2 受限原因不进 ②表列

②表列 key 恒为 `['label','end_amount','prior_amount']`（3 列，源模板即 3 列）；L2 归集出的「受限原因」文本必须并入 `_note_texts` 的文字说明段（去重后拼接），不得新增第 4 列。

**Validates: Requirements 8.7**

### Property 39: `get_active_filter` 必须 await

源码级断言：`e1_bank_accounts.py` 中每处 `get_active_filter(` 前必须紧邻 `await`。反向自检：去掉 `await` 时该断言必红，且**连库勾稽同时必红**（证明漏 await 会让清单恒空而非只是风格问题）。

**Validates: Requirements 10.8, 10.9**

### Property 40: 预设覆盖面判据有白名单且基线冻结

E 类 visible sheet 集合分三段且**互不相交、并集完备**：有预设块 / 在 `E1_SHEETS_WITHOUT_PRESET` 登记 / 在非数据表白名单（`底稿目录` + `E1A` + `E26A` + `E0A`）。

🔴 **计数一律用「去重名」口径** —— `底稿目录` 在 5 个 workbook 各出现一张但只是 1 个名，按「出现次数」算会让白名单命中数与集合大小对不上（自检必假红）。基线冻结（实测复算）：visible 出现 **45** 次 / 去重名 **41** · 预设块 **17** 个（其中 `审定表E0-1` 错名 ⇒ 真实命中 **16**）· 白名单去重名 **4** / 出现 **8** · 缺口 **21**。白名单配「去重名命中数 == 4 且出现次数 == 8」双断言（防它退化成逃逸阀）。

判据只覆盖 visible sheet；sheet 名比对一律用全名（hidden 的 `银行函证其他信息核对表E0-5` 与 visible 的 `应付银行承兑汇票发函记录表E0-5` 同尾码）。

**Validates: Requirements 3.7, 3.8, 3.9, 3.10**

### Property 41: soe 主表两行缺失已登记且既有断言被诚实改写

soe docx 主表 6 行不含「存放财务公司款项」与「存款应计利息」（listed 有）⇒ 守卫断言该差异存在且**不得对齐两版**；同时断言三条旧断言已改写为新口径（`E1_MAIN_ROWS_SOE` 6 行 / `sourceRef` 序列含新增行 / soe 含 `overseas` 行），改写理由「附注行集真源是 docx 不是底稿 xlsx」出现在用例注释里。

**Validates: Requirements 5.7, 5.8**

## Notes

### 范围外（明确不做，勿再提议）

- 附注模板新增 `row_type: expandable` —— 归 `note-template-columns-and-legacy-snapshot-closure` R11（该 spec 已 21/23）
- 外币表扩列（4 列 → 7 列含期初）—— 跨循环共享表，波及 D2/K/L，需平台级 spec
- 银行账户完整性三方比对（四表 ∪ 央行已开立账户清单 OCR ∪ E0-3 回函）—— 涉及 OCR 数据源，够独立 spec
- `trial_balance` 父子双算修正 —— 平台级缺陷，E1 已用叶子口径规避
- E1 孤儿组件接线 —— 归 `e1-orphan-components-wiring`
- E0 发函清单专属组件 —— 归 `e0-send-list-dedicated-components`
- 存量项目附注数据回填 —— 模板改动只对新建/重新生成生效

### 已核实无需改动（防下个会话「顺手纠正」）

| 项 | 结论 | 依据 |
|---|---|---|
| listed 外币章节号 `五、73` | **正确** | 第五章 74 个 level=2 子节，外币是第 73 个（sort_index=72）；源 docx 正文写「五、81」是 docx 自身的陈旧交叉引用 |
| 外币表两版段数不对称 | **源 docx 事实** | listed 3 段（货币资金/应收账款/长期借款）、soe 5 段（+短期借款+应付债券），不得对齐 |
| 附注 `合计` / `项目` 字面 | **符合平台惯例** | listed 248/192 处、soe 160/130 处主流；docx 的 `合  计`/`项  目` 去空白归一后相等 |
| `digital`/`finance_co` 恒空 | **数据事实** | `account_chart` 全库对「数字货币/数字人民币/财务公司」**0 命中** |
| E1 子 Tab 无 `htmlData` prop | **架构如此** | 宿主种子化进 `allResponses`，子 Tab 经既有通道读 |
| 全零账户被金额明细过滤 | **设计如此** | 金额明细过滤 / 账户清单保留（完整性核对红线） |
| soe 主表比 listed 少「存放财务公司款项」「存款应计利息」 | **源 docx 事实，不得对齐** | soe docx 主表 6 行；连带 `finance_co` 槽在 soe 附注无落点（准则口径差异）|
| 外币表模板 seed 的「其中：美元/欧元/港币」三行 | **源 docx 事实** | listed docx r2~r4 甚至预填了汇率中间价；Property 33 只约束源码/推送侧 |
| 外币表「可无限量添加行」/「……」占位行 | **源 docx 事实**（listed 用前者、soe 用后者）| Property 19 冻结 16/25 行，防误删 |
| 优先级序 ≠ 展示序 | **两个语义，必须分离** | 优先级有硬理由（含包含关系者先声明）；展示序取自 docx |

### 两处方法论教训（本轮踩过，写进守卫设计）

1. **判 dead output 必须沿消费链从 render 输出键走到底**，只查子组件的 prop 与键名会得出「24 个 Tab 全是 dead」的错误结论 —— 平台有「宿主种子化」这条通道。故 `e1HostSeedWiring.spec.ts` 的判据是「render 键 → 宿主消费 → 写入哪个 `allResponses` 键 → 子 Tab 读该键」三段链，不是单点 grep。
2. **调共享件前先 `inspect.signature`**。本轮把 `find_segment(rows, code)` 当「在 segments 列表里查」用，得到全 `None`，一度误判「E1 外币段推送从来没成功过」；段字段名也是 `row_code` 不是 `owner_row_code`。

3. **spec 里出现的每个函数名/文件路径落地前必须核一遍**。本 spec 初稿写的 `refetchFromFourTable` 在宿主里 0 命中（真名 `reExtractFromFourTable`），按它写守卫会空转（同族已记：路径写错导致文件级失败而非断言失败，极易被当噪声跳过）。

4. **「同一份顺序被两个语义共用」是隐蔽的双真源**。受限桶的声明序同时承担「匹配优先级」与「附注行序」，两者实际不同（4 个位置互换），而既有用例的**标题**把它们写成等价 ⇒ 守卫在锁死一个错的不变量。判据：凡「顺序有语义」的常量表，都要问一句「有几个消费方？它们要的顺序是同一个吗？」

5. **「注释承诺了但没实现」要按 dead output 一类对待**。`E1_MAIN_ROWS_LISTED` 的三个 `crossKey: ''` 行注释写着「由 render 的语义槽预填」而零实现（同 E1-4 预设 description 那处）。排查手法 = grep 注释里的承诺词（「由…预填」「由…下发」「后续由…」）再核实现。

### 执行顺序硬约束

- Wave 1 三个守卫必须**先对当前状态打红**（先改后写无法区分守卫有效与空转）
- 组件 1（`e1_bank_accounts.py`）是 R1/R8 的共同前置
- 附注结构（Wave 4）与取数（Wave 2/3）无文件重叠，可并行
- 改 `note_template_*.json` 后必须重跑 `gen_note_shared_table_segments.py --write`
- 浏览器实测必须在全部守卫绿之后，且**实测前抓基线三件**（全文 + md5 + `jsonb_typeof`），测完复原
