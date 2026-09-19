# Design: report_config 科目码完整性修正与守卫

## Overview

两件事：**一次性修正**（幂等 SQL 迁移）+ **永久守卫**（CI 自动对账）。

修正走 `backend/migrations/V138__*.sql`，判据全部来自 `account_chart` 双向对账；
守卫走 `backend/tests/four_table/test_report_config_account_integrity.py`，
使 Requirement 6 的不一致在 CI 打红。

**设计立场**：不引入新机制。`report_config` 仍是报表行→科目码真源，
`semantic_account_resolver` 仍把它当层③提示；本 spec 只让这张表的内容与
`account_chart` 一致，并把「一致」变成可执行断言。

### 全表对账实测基线（2026-08-03）

| 指标 | 值 |
|---|---|
| `TB*('code')` 引用总数（排除 `project:` 覆盖行） | 132 |
| 涉及报表行数 | 102 |
| 引用码在 `account_chart` 零命中 | 10 条引用 |
| 判定为错码（本 spec 修正范围） | **13 行** |
| 判定为业务事实（白名单） | 5 行 |
| 已由 V137 修好 | 5 行 |

### 修正清单（每条都有双向实证）

| row_code | row_name | 现 formula 码 | 现码实际是 | 处置 | 实证 |
|---|---|---|---|---|---|
| BS-082 | 其他权益工具 | `4003` | 其他综合收益 | → `4401` | client 5 项目 = 其他权益工具 |
| BS-084 | 减：库存股 | `4005` | **零命中** | → `4201` | client 5 / standard 3 = 库存股 |
| BS-085 | 其他综合收益 | `4102` | **零命中** | → `4003` | client 8 项目 = 其他综合收益 |
| BS-086 | 专项储备 | `4103` | 本年利润 | → `4301` | client 4 项目 = 专项储备 |
| EQ-015 | （五）专项储备 | `4201` | 库存股 | → `4301` | 同上 |
| BS-090 | 少数股东权益 | `4201` | 库存股 | → **NULL** | 合并派生项，CAS 无对应科目 |
| BS-033 | 开发支出 | `1703` | 无形资产减值准备 | → `1704` | client 4 / standard 3 = 开发支出 |
| BS-043 | 衍生金融负债 | `2102` | 短期应付债券 | → **NULL** | `3201` 一码两义不可用 |
| BS-053 | 其他流动负债 | `2901` | 递延所得税负债 | → **NULL** | 与 BS-067 双算 |
| IMP-008 | 七、债权投资减值准备 | `1502` | 持有至到期投资减值准备 | → `1505` | standard 6 项目 = 债权投资减值准备 |
| IMP-017 | 十六、商誉减值准备 | `1711` | 商誉（原值） | → **NULL** | `1712` 全库零命中 |
| BS-013 | 一年内到期的非流动资产 | `1503` | 可供出售金融资产 | → **NULL** | 重分类派生行 |
| CFSS-016 | 存货的减少 | `1401` | 材料采购 | → **NULL** | 变动额 + 区间口径 |
| BS-014 | 其他流动资产 | `1901` | 待处理财产损溢/损益 | **待用户裁决** | 见 Requirement 5 |

### 白名单（业务事实，不改）

| row_code | 码 | 依据 |
|---|---|---|
| BS-004 | `1102` 衍生金融资产 | 码与名在全库均零命中 |
| BS-007 | `1124` 应收款项融资 | 同上（memory 已记） |
| BS-037 | `1911` 其他非流动资产 | 同上 |
| BS-066 | `2811` 递延收益 | 同上 |
| BS-068 | `2911` 其他非流动负债 | 同上 |

### 🔴 本轮附带查清的编码体系事实（守卫必须内建）

`account_chart` 的 `source='standard'` 并存**两套完整编码体系**，
不是零散错码（这解释了 memory 记的「一码两义」现象）：

| 体系 | 权益 | 成本 | 损益 | 项目数 |
|---|---|---|---|---|
| 旧《企业会计制度》(2001) | 3xxx | **4xxx** | 5xxx | 6（`c8621493` `b39809ed` `0ec33ac9` `df5b8403` `f064f5e4` `4f6dbc36`）|
| CAS 2006 | **4xxx** | 5xxx | 6xxx | 4（`52c04ed1` `12c15a96` `2aa00f57` `a7fc75e5`）|

两条推论：

1. **`4001`/`4101`/`4301`/`4401` 在旧制项目是成本类**（生产成本/制造费用/研发支出/工程施工）
   → 守卫比对名称时必须**分 source 各判**，混在一起会把 `4101` 判成「一码多名」。
2. **`3101`/`3201` 在同一 `source='standard'` 内一码两义**：
   旧制 `3101 盈余公积`/`3201 利润分配` ↔ CAS 2006 `3101 衍生工具`/`3201 套期工具`。
   实测 `df5b8403` 的 `3201 套期工具` = **−4,314,686.92**（全库唯一带真金额的 3xxx/5xxx 行）
   → 任何「按名定位落到 3xxx」的路径都必须先判体系，**故 BS-043 不改指 `3201`**。

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│ 一次性修正                                                  │
│  V138__fix_report_config_equity_and_asset_codes.sql        │
│   · 每行一条 UPDATE，WHERE 带 row_code + 已实证错值           │
│   · 幂等：错值不命中 → 0 行影响                               │
│   · 跳过 applicable_standard LIKE 'project:%'                │
└────────────────────────────────────────────────────────────┘
                            │  改变
                            ▼
        report_config.formula（报表行 → 科目码真源）
                            │  被读
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
 resolve_report_line   semantic_account_    附注 REPORT()
 _account_codes        resolver（层③）        公式引擎
        │                   │
        ▼                   ▼
  D~N 循环四表取数 / 审定表预填 / 溯源面板
                            ▲
┌───────────────────────────┴────────────────────────────────┐
│ 永久守卫（CI，连库 job）                                     │
│  test_report_config_account_integrity.py                    │
│   · 抽 TB*('code') → 分 source 与 account_chart 双向对账      │
│   · 别名表（单一真源）吸收合法用语差异                          │
│   · 白名单须带 reason；反向自检注入已知错码必红                  │
└─────────────────────────────────────────────────────────────┘
```

### 为什么修正用迁移而不是脚本

`report_config` 是**运行时表**，不是仓库里的 JSON —— 已有 V136/V137 两个先例走迁移，
沿用同一机制（`MigrationRunner`，启动时应用）。用 `scripts/fix/*.py` 会造第二条修改路径，
且无 checksum 记账。

### 为什么不在本 spec 顺手改「派生行的下游」

置 NULL 的 5 行（BS-090/BS-043/BS-053/BS-013/CFSS-016/IMP-017）会让
`resolve_report_line_account_codes` 返空 → 调用方按既有语义回退自己的兜底码
（`return codes or fallback`）。这是**既有平台行为**，不是本 spec 新增分支。
需要改的只是确认回退结果正确（Requirement 8.3）。

---

## Components and Interfaces

### 1. `V138__fix_report_config_equity_and_asset_codes.sql`（新建）

```sql
-- 形态（每行一条，防链式命中）
UPDATE report_config
SET formula = REPLACE(formula, '''4003''', '''4401'''), updated_at = NOW()
WHERE row_code = 'BS-082'
  AND formula LIKE '%TB(''4003''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- 置 NULL 形态
UPDATE report_config
SET formula = NULL, updated_at = NOW()
WHERE row_code = 'BS-090'
  AND formula = 'TB(''4201'',''期末余额'')'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;
```

**约束**：
- `REPLACE` 只允许在「该 row_code 的 formula 里该码唯一出现」时使用；
  多次出现或与别的码共存时必须整体重写 formula 字面量（EQ-015 的
  `TB('4201','期末余额') - TB('4201','期初余额')` 属此类，两处都要换）。
- 每条 UPDATE 上方注释写「现码实际是什么科目 + 实证项目数」。

### 2. `backend/app/services/four_table/report_config_account_names.py`（新建）

别名与白名单的**单一真源**，被迁移的校验脚本与 CI 守卫共读：

```python
#: 报表行名 ↔ 科目名 的合法差异（报表用语 vs 会计科目用语）
ROW_NAME_ACCOUNT_ALIASES: tuple[tuple[str, str], ...] = (
    ("未分配利润", "利润分配"),
    ("预收款项", "预收账款"),
    ("预付款项", "预付账款"),
    ("公允价值变动收益", "公允价值变动损益"),
    ("资产处置收益", "资产处置损益"),
    ("其他流动资产", "待处理财产损溢"),   # ← 仅在 BS-014 裁决为「保留」时才加
)

#: 引用码全库零命中但属业务事实的行；value 必须写明实证
ZERO_HIT_WHITELIST: dict[str, str] = {
    "BS-004": "1102 衍生金融资产：码与名在全库 account_chart 均零命中（2026-08-03 实证）",
    ...
}

#: 语义上不应挂单一科目的派生行（守卫要求它们 formula 为 NULL）
DERIVED_ROWS_WITHOUT_ACCOUNT: frozenset[str] = frozenset({
    "BS-090", "BS-013", "BS-053", "BS-043", "CFSS-016", "IMP-017",
})

def normalize_name(s: str) -> str:
    """去 △ / 加：/ 减：/ 中文序号前缀 / 空格，供名称比对。"""
```

### 3. `backend/tests/four_table/test_report_config_account_integrity.py`（新建）

```python
async def load_refs(db) -> list[Ref]:
    """抽 report_config 全部 TB*('code') 引用（排除 project: 覆盖行）。"""

async def load_chart(db) -> dict[tuple[str, str], set[str]]:
    """{(code, source): {account_name, ...}} —— 分 source，不合并。"""
```

断言组：
- `TestNoMismatchedCodes` —— 行名 ↔ 科目名（经别名归一）必须对应
- `TestZeroHitCodesWhitelisted` —— 零命中码必须在白名单且有 reason
- `TestDerivedRowsHaveNoAccount` —— 派生行 formula 必须为 NULL
- `TestNoCrossRowDoubleClaim` —— 同一码不得被两个**同表**报表行认领为主科目
  （BS-053 与 BS-067 双算即此条抓的）
- `TestReverseSelfcheck` —— 注入 `BS-090 = TB('4201')` 必判红；
  别名表清空后已知合法行必判红（证明别名确实在起作用）

### 4. 诊断工具（复用已有）

`backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db`
已实现「码→名 + 名→码」双向对账与分 source 覆盖率，
本 spec 增一个 `--report-config` 模式复用同一对账函数，避免两份判据。

---

## Data Models

### `report_config`（既有，不改结构）

| 列 | 类型 | 说明 |
|---|---|---|
| `row_code` | text | 报表行号（`BS-*` / `IS-*` / `EQ-*` / `IMP-*` / `CFSS-*`）|
| `row_name` | text | 行名；**同一 row_code 在不同准则下行名可不同**（实证 `BS-017` listed=其他流动资产 / soe=△买入返售金融资产）→ 比对必须按 (row_code, applicable_standard) 逐行做 |
| `applicable_standard` | text | `listed_standalone` / `listed_consolidated` / `soe_standalone` / `soe_consolidated` / `project:{uuid}` |
| `formula` | text \| NULL | `TB('code','列')` 组合；NULL = 该准则下不取数 |
| `is_deleted` | bool | 软删 |

### `account_chart`（既有，只读）

| 列 | 说明 |
|---|---|
| `project_id` | 项目 |
| `source` | `client`（客户科目表，8 项目）/ `standard`（标准科目表，10 项目）—— **分母不同，覆盖率必须分 source 算** |
| `account_code` | 科目码 |
| `account_name` | 科目名（比对基准）|

### `Ref`（守卫内部）

```python
@dataclass(frozen=True)
class Ref:
    row_code: str
    row_name: str
    applicable_standard: str
    code: str            # TB('1231-03') → '1231-03'
    head: str            # → '1231'（查 account_chart 用）
```

---

---

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 迁移某条 UPDATE 影响 0 行 | **正常**，不报错 | 幂等设计：错值不命中即已修正过 |
| 迁移某条影响行数 > 预期（4 个准则变体） | **中止并人工复核** | 说明 WHERE 过宽命中了 `project:` 行或别的 row_code |
| `resolve_report_line_account_codes` 对置 NULL 行返空 | 调用方按既有 `return codes or fallback` 走兜底 | 既有平台行为，非本 spec 新增分支 |
| 循环兜底码与新解析结果不一致 | **打红**，两处真源打架必须一并收敛 | 静默取其一会让下次复盘重查 |
| 守卫无 DB 连接 | `pytest.skip(reason=...)`，reason 非空 | 静默 skip 是假绿源 |
| 守卫抽到 0 条 `TB()` 引用 | **打红** | 正则失效导致断言空转，比不一致更危险 |
| 名称比对遇到未登记的合法差异 | **打红**，要求人工加别名并写实证 | 宁可多一次人工裁决，不放宽模糊匹配 |
| `project:` 覆盖行引用被修正码 | 输出清单，**不自动改** | 客户自定义公式，改动可能破坏其已出报表 |

**fail closed 原则**：判据不确定时打红，不放行。本 spec 修的正是「静默错了很久」的问题，
再引入静默兜底等于复制病根。

---

## Testing Strategy

### 分层

| 层 | 内容 | 判据 |
|---|---|---|
| 纯函数单测 | `normalize_name()` / 别名归一 / 分档判定 | 不连库，含边界（`△`、`加：`、`一、`、全角空格）|
| 连库守卫 | `test_report_config_account_integrity.py` 五组断言 | 真实 `report_config` × `account_chart` 对账 |
| 迁移幂等 | 重启两次后 `formula` 逐字节相同 | Property 1 |
| 未受影响面 | BS-081/083/087/088 与 `project:` 行前后逐字节相同 | Property 2, 3 |
| 真实 DB 取数回归 | 受影响循环修正前/后金额对照 | 两套编码体系各一个项目 |
| 后端全量 | `backend/tests/four_table/` | 新增失败数 = 0 |

### 反向自检（每条都必须有，防守卫空转）

1. 注入 `BS-090 = TB('4201')` → 必红（证明不一致检测有效）
2. 清空 `ROW_NAME_ACCOUNT_ALIASES` → `BS-088 未分配利润` 必由绿转红（证明别名在起作用）
3. 合并 `client` 与 `standard` → `BS-087 4101` 必由绿转红（证明分域判定必要）
4. 白名单某条 reason 置空 → 必红（证明 reason 必填生效）
5. 把 `DERIVED_ROWS_WITHOUT_ACCOUNT` 中某行的 formula 填回一个码 → 必红

### 🔴 关键顺序

**守卫必须先在修正前的现状下打红 13 行**（tasks Wave 1 Task 3）。
先改数据再写守卫无法区分「守卫有效」与「守卫空转」—— 这正是
`test_semantic_resolver_coverage.py` 第一版成为假绿源的机理。

### 不用替身

取数回归一律真实 DB 直跑。替身 session 与错误假设同构：
`_f2_prefill_gray` 的 `MagicMock()` 过滤器曾把 fail-open 吞成空结果并让测试「通过」，
`_d1` 的 fake session 不区分两次 `trial_balance` 查询导致备抵 == 原值。

## Correctness Properties

### Property 1: 修正迁移幂等
重复应用 V138 对 `report_config` 内容无二次影响（每条 UPDATE 的 WHERE 含已实证错值，
修正后不再命中）。
**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.5**

### Property 2: 已正确行不被波及
BS-081 / BS-083 / BS-087 / BS-088 的 formula 在迁移前后逐字节相同。
**Validates: Requirements 1.7**

### Property 3: project 级覆盖行零改动
`applicable_standard LIKE 'project:%'` 的行在迁移前后逐字节相同，且被列入待人工确认清单。
**Validates: Requirements 1.8**

### Property 4: 修正后码↔名双向一致
对每个修正行，其新码在至少一个项目的 `account_chart` 中的 `account_name`
经别名归一后与 `row_name` 对应；且该 `row_name` 对应的科目名在库中不挂在别的码上
（同 source 内）。
**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.5, 2.7**

### Property 5: 派生行返空而非返错
`DERIVED_ROWS_WITHOUT_ACCOUNT` 中每行的 `formula` 为 NULL，
且 `resolve_report_line_account_codes` 对它们返回空列表（调用方因此走自己的兜底）。
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 6: 零命中分档判据可执行
「码零命中 + 名有归属」→ 判错码；「码零命中 + 名亦零命中」→ 判业务事实。
两档各有真实样本（前者 BS-084/BS-085，后者 BS-004/BS-007），且白名单条目
在其科目名出现于库中时打红。
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 7: 守卫按 source 分域判定
名称比对分 `client` / `standard` 各自进行；把两 source 合并会让 `4101`
（client 盈余公积 / standard 制造费用+盈余公积）被误判为一码多名。
反向自检：合并 source 后该行必须由绿转红。
**Validates: Requirements 6.1, 6.2, 6.7**

### Property 8: 守卫反向自检非空转
注入 `BS-090 = TB('4201')` 必判红；清空别名表后 `BS-088 未分配利润 = TB('4104')`
必由绿转红。
**Validates: Requirements 6.5**

### Property 9: 白名单 reason 必填
`ZERO_HIT_WHITELIST` 每个 value 去空白后非空，否则视为未登记并打红。
**Validates: Requirements 6.4, 3.3**

### Property 10: 跨行不重复认领
同一科目码不得被同一张报表内两个不同 `row_code` 认领为**原值**科目
（备抵可与原值行重合）。BS-053 与 BS-067 同认领 `2901` 即违反本条。
**Validates: Requirements 2.4, 8.4**

### Property 11: 循环兜底码与解析结果一致
对每个被修正的行，若有循环 spec 声明了兜底码，两者必须相等
（实证已一致：M9 `4003` / M10 `4401` / M3 `4201` / M7 `4301`）。
**Validates: Requirements 8.3, 8.5**

### Property 12: 无 DB 时 skip 可见
守卫在无 DB 环境 `pytest.skip` 且 skip 原因非空字符串（静默 skip 是假绿源）。
**Validates: Requirements 6.6**

### Property 13: V138 注释记录 V136 失效事实
V138 文件内容包含「V136」与「BS-086」，说明失效原因与真正需修的行。
**Validates: Requirements 7.2, 7.3**

### Property 14: 修正前后金额可比
受影响循环的真实 DB 直跑结果在修正前后被记录，差异逐项有解释
（预期变化 vs 意外变化）。
**Validates: Requirements 8.1, 8.2, 8.6**
