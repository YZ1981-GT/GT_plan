# Design Document

## Overview

本设计把 K 循环全链收口拆成**六层**，每层的判据真源与守卫形态先定死，再谈实现顺序。

核心设计判断六条：

**① row_code 改正走「按 row_name 连库反查」而不是静态表。** 声明表现有的错位正是「有人抄了一张静态实证表、之后数据变了没人知道」造成的。故守卫必须连库、按 `row_name` 反查四变体，声明表只存结论、判据在 DB。这条同时解决 R1 与 R13.1。

**② 错位后果分三级，修复优先级按级排。** 实测发现同样是「row_code 写错」，后果差别极大：**活错数**（公式非 NULL + 科目在客户表存在 ⇒ 解析成功 ⇒ 取到别的科目的钱）→ **恒空**（科目存在但方向被判成备抵 ⇒ gross 空 ⇒ 显示 0）→ **仅溯源失真**（公式 NULL ⇒ 退兜底 ⇒ 金额对、`resolved_from` 谎报）。K9/K6 属第一级、K4 属第二级、其余属第三级。Wave 1 先修前两级。

**③ 「宁缺勿造」要逐个复核，不能整循环钉死。** 实测 K6 的三个科目在 client 侧确实存在、三条报表行公式都在，原判断错了；而 K4 的四变体公式确实全 NULL 且按名按码零命中，判断对。故 `has_account` 是**逐循环实证结论**不是设计偏好，且必须保留「本项目无该科目时空取数」的运行时降级（两者是不同层：前者是「标准科目表里有没有这个科目」，后者是「这个项目有没有用它」）。

**④ 附注侧 `report_row_code` 全缺是行级合并的前置阻塞，且它是「写入侧 fail-closed」而非「读取侧降级」。** 声明 `_row_scope` 后 `find_segment` 返 None 会**整表跳过写入**（不是退化成表级覆盖），故 R11 必须排在「让 K1 与 G2/G3 共存」之前，否则接了 `_row_scope` 反而让推送静默失效。

**⑤ 动态插行区的判据复用 `note_expandable_markers`，不新建词表。** 平台已有该 service（`row_type_for_label` + 词表三常量）且 `_note_structure_kit.data_row()` 已 marker-aware。K 类只需「逐处判定作行/作列头」+ 让改 rows 的幂等脚本走 kit。**判据词表按实测收敛**：K 类实际出现 5 种写法（`……` 91 / `?` 41 / `…` 10 / `可无限量添加行` 4 / `......` 2），`…`（单字符）**确实存在**（K6-6 三处、K8/K9 合同检查表各一）不得排除；而 `预留` / `可改名` 在 K 类零命中，加进判据即空转分支。

**⑥ 列 key 风格分叉不做统一。** K1 用中文字面量、K2~K7 用英文 key，改 key 会让 `_cell_meta`/`_cell_modes`（按数据列 key 索引）失联 = 丢已录入数据。故只登记裁决理由 + 守卫钉死「同循环内一致」，跨循环差异作既有事实。这与「禁硬编码」铁律的冲突是**有意接受的代价**，理由写进登记表。

## Architecture

### 六层与依赖

```
L1 科目定位声明真源（k_cycle_specs.py）
   ├─ row_code 改正（R1）
   ├─ 负债方向声明（R2）
   └─ K1/K2 纳入（R3）
        ↓ 提供正确的 ReportLineAccountSpec
L2 取数装配（各 render + 共享件）
   ├─ parent_check 补齐（R4.2）
   ├─ K6 adjudication_prefill（R4.1）
   └─ 语义驱动接线或撤回（R5）
        ↓ 提供 tb_values / tb_source_codes / adjudication_prefill
L3 公式预设（prefill_formula_mapping.json）
   ├─ 科目与口径改正（R6）
   └─ 覆盖面补齐（R7）
        ↓ 独立于 L2，可并行
L4 披露表结构（源 xlsx → 底稿 UI → 载荷）
   ├─ sheet 名与列头对齐（R8）
   ├─ 动态插行识别（R9）
   └─ 账龄枚举（R10）
        ↓ 提供载荷 columns 与 sub_table_data
L5 附注模板（note_template_*.json）
   ├─ report_row_code 补齐（R11）← 阻塞 L4 的 _row_scope
   ├─ expandable 标记（R9.2）
   └─ 子表名与列定义收口（R12）
        ↓
L6 守卫 / CI / 验收（R13 / R14）
```

**关键依赖**：R11（附注 `report_row_code`）**必须早于** R12.6（`_row_scope` 声明），否则接了就 fail-closed。R9.2（expandable 标记）**必须晚于** R8（列头对齐），因为标记落在行上、而行集可能随列头修订变化。

### 判据真源表

| 维度 | 真源 | 读取方式 | 禁止 |
|---|---|---|---|
| row_code ↔ 科目 | `report_config`（DB） | 按 `row_name` 反查 + 四变体全列 | 静态冻结表 / 按码正查 |
| 科目 ↔ 方向 / 是否存在 | `account_chart`（DB） | 按 source 分域（client / standard）双向查 | 只查一侧 |
| 标准码 ↔ 客户原始码 | `account_mapping`（DB） | 反解 + 最长前缀归属 | 手工替换分隔符 |
| 披露 sheet 名 / 列头 / 行集 / 动态标记 | `backend/wp_templates/K/*.xlsx` | openpyxl 直读 + `sheet_state` | 记忆 / 控制台输出 |
| 附注章节结构 | `docs/模版/` 两份 docx（结构）+ `note_template_*.json`（现状） | python-docx 顺序流 + JSON 逐表 | 只看 JSON |
| 动态标记判据 | `note_expandable_markers.py` | import service | 另写词表 |
| 账龄档位 | `disclosureAgingLabels.ts` | import | 各写字面量 |

## Components and Interfaces

### C1 `k_cycle_specs.py` 改写（L1）

`KCycleSpec` 新增字段（additive，默认值保持既有行为）：

```python
@dataclass(frozen=True)
class KCycleSpec:
    # 既有字段不变 ...
    is_liability: bool = False          # → ReportLineAccountSpec.is_liability
    gross_direction: str | None = None  # → 弱形式，负债类报表行仍可能引用备抵
    extra_standard_codes: tuple[str, ...] = ()   # K3 的 2231
    provision_row_code: str | None = None        # K6 的 IMP-007
    trust_report_config: bool = True             # 派生行 / 已知错码时关闭
    row_code_evidence: str = ""                  # 原值 + 该原值实指科目 + 后果分级
```

`spec_for(applicable_standards)` 行为不变（仍只挑一个行号），但因两准则同号，错位风险大幅下降。新增 `severity_of(wp_code)` 返回后果分级供守卫与验收脚本消费。

### C2 取数装配补齐（L2）

- `build_k6_adjudication_prefill`：镜像 K4 的 `build_adjudication_prefill`（按叶子建行 + 金额全零跳过 + 降序），资产侧保留符号、负债侧 `abs()`
- `parent_check` 接入 K1/K2/K4/K6：直接调共享件 `four_table/parent_check.build_parent_check`，`occurrence=False`
- **contra 子科目**：凡「叶子和 ≠ 父额」的族一律走 `resolve_leaf_totals`（方向自校验），不裸 `aggregate_leaves`

### C3 语义驱动接线决策（L2 / R5）

先做一次实证：K 循环各科目码在项目间是否一致（同 §Data Models 的对账口径）。

- **若基本一致**（如 `2241` 在 10+8 项目全同）⇒ 语义解析买不到东西 ⇒ **撤回** `to_semantic_spec`/`semantic_spec_of`，删除两个零消费方函数 + 守卫钉死结论
- **若存在项目间漂移或旧准则并存** ⇒ **接线**，且必须修 `to_semantic_spec` 硬编码 `row_code_soe` 的问题 + 多槽关闭报表兜底层

判据不预设，由 Wave 1 的对账结果决定。**无论哪条路都要留守卫**，防下个会话重新发起批量迁移（平台已因此返工过一轮）。

### C4 幂等脚本（L3 / L4 / L5）

| 脚本 | 作用域 | 判据 |
|---|---|---|
| `fix_k_cycle_prefill_presets.py`（扩展既有） | 26 块预设 | R6 全部 AC；round-trip 自检 |
| `fix_k_cycle_disclosure_presets.py`（新建） | 26 张披露 sheet 预设 | R7；白名单非空自检 |
| `fix_note_k_report_row_codes.py`（新建） | 26 章节的 `report_row_code` | R11；与 `report_config` 对账 |
| `fix_note_k_expandable_rows.py`（新建） | 披露 sheet 内 11 处动态区（全册 148 处中） | R9；import `note_expandable_markers` |
| 既有 4 个 `fix_note_k*_structure.py` | 列头 / 行集 | R8；改 rows 处须 marker-aware |

全部带 `--dry-run` / `--check` / `--apply`，`--check` 归零是 CI 判据。

### C5 前端载荷收口（L4 / L5）

- `k1AccountScope.ts` 新建（读 render 下发的 `tb_source_codes.gross_standard`，常量只作兜底+展示）
- K7 两个空数组填值；K8~K13 子表名常量剔除混入的表头文字与英文 key
- K1 的推送路径：先探明它走的是哪条（`sync-batch-from-workpaper`？map 内部封装？），再决定「补 `build*Columns` + `buildK1SyncPayload`」还是「登记既有路径 + 加守卫」

## Data Models

### 对账 SQL（判据口径，守卫与验收脚本共用）

```sql
-- 按 row_name 反查（正向判据）
SELECT row_name, applicable_standard, row_code, formula
FROM report_config
WHERE row_name IN (:names) AND is_deleted = false
  AND applicable_standard NOT LIKE 'project:%'
ORDER BY row_name, applicable_standard;

-- 按 row_code 正查（反向自检：声明的码实际指向什么）
SELECT row_code, applicable_standard, row_name, formula
FROM report_config
WHERE row_code IN (:codes) AND is_deleted = false
  AND applicable_standard NOT LIKE 'project:%';

-- 科目存在性与方向（按 source 分域）
SELECT account_code, source, direction, COUNT(DISTINCT project_id) AS projects,
       MIN(account_name) AS nm
FROM account_chart
WHERE account_code IN (:codes) AND is_deleted = false
GROUP BY account_code, source, direction;
```

### 后果分级判定

```
severity(wp_code):
  formula 非 NULL 且解析出的码在 account_chart 存在:
      direction 与主体方向一致  → ACTIVE_WRONG   （活错数）
      direction 相反且未声明方向 → SILENT_EMPTY   （恒空）
  formula 是 ROW() 派生         → TRACE_ONLY     （退兜底，溯源失真）
  formula NULL                  → TRACE_ONLY
```

## Correctness Properties

### Property 1: 声明表 row_code 与 report_config 按名对账一致

对每个 K 循环，用 `row_name` 反查 `report_config` 四变体，声明的 `row_code_listed` / `row_code_soe` 必须落在该科目名对应的 row_code 集合内。守卫连库、不用静态表。

**Validates: Requirements 1.1, 1.2, 13.1**

### Property 2: 逐条改正值不得回退

K3→`BS-050` / K5 soe→`BS-065` / K7→`BS-066` / K6→`BS-012`+`BS-051`+`IMP-007` / K8 soe→`IS-004` / K9 soe→`IS-005` / K10~K13 soe→`IS-010`/`IS-017`/`IS-020`/`IS-021`，逐条断言。

**Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7**

### Property 3: 派生行不得作为取数 row_code

声明的每个 row_code 在 `report_config` 中的 formula 若是 `ROW()` 组合（无 `TB()`），则必须 `trust_report_config=False` 或改指非派生行。反向自检：`BS-015`/`BS-069`/`IS-022` 确为派生行。

**Validates: Requirements 1.10, 13.5**

### Property 4: 宁缺勿造是逐循环实证结论

`has_account=False` 的循环，其科目在 `account_chart` 按名按码**两侧都零命中**且 `report_config` 公式为 NULL。K4 满足、K6 不满足。反向自检：把 K6 强标 `False` 必须打红。

**Validates: Requirements 1.8, 1.9**


### Property 5: 负债类必须声明方向

科目在 `account_chart` 为 `direction='credit'` 的循环，其 spec 必须 `is_liability=True` 或 `gross_direction='credit'`。反向自检：去掉声明后 `split_gross_provision` 会把原值判成备抵、`gross` 变空。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 13.4**

### Property 6: 声明方向后 resolved_from 为 report_config

对有公式的负债类循环，声明方向后 `resolve_report_line_accounts` 的 `resolved_from` 必须是 `report_config` 而非 `fallback`。

**Validates: Requirements 2.5**

### Property 7: 全部 14 循环在声明真源内且守卫覆盖

`K_CYCLE_SPECS` 含 K1~K13（K0 是函证循环、无科目余额，显式登记豁免）；`test_cycle_specs_row_code_evidence._all_specs()` 必须包含 K。

**Validates: Requirements 3.1, 13.2**

### Property 8: K1/K2 收进真源后 render 行为不变

characterization：收进 `K_CYCLE_SPECS` 前后，K1/K2 的 render 输出（除 `tb_source_codes` 的溯源字段外）逐字节相同。

**Validates: Requirements 3.4**

### Property 9: K1 既有语义不丢

K1 的声明保留 `provision_row_code` / `provision_name_filter` / `extra_standard_codes=(1131, 1132)`；K2 保留 `BS-014` + 兜底 `1901`。

**Validates: Requirements 3.2, 3.3**

### Property 10: 前后端科目真源交叉锁死

`k1AccountScope.ts` ~ `k13AccountScope.ts` 的 row_code / 兜底码与后端声明逐字一致（前端守卫直读后端 py 源码）。

**Validates: Requirements 3.5**

### Property 11: 同一 row_code 不得被两循环认领

跨全部循环声明（含 D/F/G/H/I/L/M/N）求 row_code 重复；已知合法共享（如 `BS-028`/`BS-029`）走白名单。

**Validates: Requirements 13.3**

### Property 12: 余额类循环全部输出 adjudication_prefill 与 parent_check

K1/K2/K3/K4/K5/K6/K7 七个余额类循环的 render 输出必须含这两个键。

**Validates: Requirements 4.1, 4.2**

### Property 13: parent_check 三态语义

槽 `found=False` 时 `parent_check` 不产生该键（不得填 0）。

**Validates: Requirements 4.3**

### Property 14: contra 子科目按方向聚合

族内存在反方向子科目时，`resolve_leaf_totals` 的结果与父额勾稽成立（`diff_parent == 0`）；裸 `aggregate_leaves` 不成立。

**Validates: Requirements 4.4**

### Property 15: 预填手工优先

已有持久化审定数时 `adjudication_prefill` 为空；无该科目时前端显示「本项目无此科目」而非 0.00。

**Validates: Requirements 4.5, 4.6**

### Property 16: 语义驱动结论已落地且被钉死

`to_semantic_spec` / `semantic_spec_of` 要么有真实生产消费方，要么已删除且守卫断言「不得重新引入」。撤回时理由含实证对账结果。

**Validates: Requirements 5.1, 5.4, 5.5**

### Property 17: 语义规格按准则选行 + 多槽关闭兜底层

若接线：`to_semantic_spec` 不得硬编码 `row_code_soe`；多槽规格 `allow_report_config_tier` 为 False。

**Validates: Requirements 5.2, 5.3**

### Property 18: 预设块科目与 wp_code 一致

每块的 `account_codes` 必须属于该 wp_code 的科目族；`wp_name` 与该循环科目名一致。反向自检：K8 `分析程序K8-3` 的旧值（管理费用 + 6602/6603）必须打红。

**Validates: Requirements 6.1**

### Property 19: formula_type 齐备

K 前缀全部预设块的每个 cell 必须有 `formula_type`。

**Validates: Requirements 6.2, 6.11**

### Property 20: 损益类口径正确

K8~K13 的取数列必须是 `本期发生额`；「上年数」必须走 `PREV()`，不得与本期同一个 `TB()` 表达式。

**Validates: Requirements 6.3, 6.4**

### Property 21: 列名已注册或显式 PLACEHOLDER

预设中出现的 TB 列名必须在 `COLUMN_ALIASES` 已注册；未注册者必须改注册名或 `PLACEHOLDER` + description 写明真源。

**Validates: Requirements 6.5**

### Property 22: 无项目专属污染

预设不得含具体辅助项编码（`YG01`/`SKT211`/`A001` 等）。

**Validates: Requirements 6.6**

### Property 23: 预设 sheet 名与源 xlsx 一致（含实参与 block.sheet 互相一致）

`block.sheet` 与公式实参里的 sheet 名都必须是源 xlsx 真实 tab 名（**空格是源模板事实，必须保留**：K4 `审定表 K4-1` / K5 `审定表 K5-1`、`明细表 K5-2` / K6 `审定表 K6-1`）。另断言「同一 sheet 在 `block.sheet` 与 `PREV()`/`WP()` 实参中的写法逐字相同」——实测 K5 两处实参丢了空格（`PREV('K5','审定表K5-1',…)` / `WP('K5','明细表K5-2',…)`），指向源 xlsx 不存在的 tab。

反向自检：把某处实参的空格删掉必须打红；断言源 xlsx 中确实存在带空格的 tab 名（防「把空格当笔误一起清掉」）。

**Validates: Requirements 6.7, 6.10, 6.12, 6.13, 7.5**

### Property 24: 月度明细覆盖 12 月

K8/K9 的 `LEDGER_DETAIL` 块覆盖 1~12 月。

**Validates: Requirements 6.8**

### Property 25: 幂等脚本 check 归零且 round-trip 安全

`--apply` 后 `--check` 归零；二次 apply 文件 md5 不变；`json.dumps` 不能逐字复现原文则 exit 2。

**Validates: Requirements 6.9, 13.11**

### Property 26: 预设覆盖面达标且缺口显式登记

26 张披露 sheet 有预设；无预设的 sheet 在登记表内且有理由；白名单（`底稿目录`/`GT_Custom`/`*A`）非空自检。

**Validates: Requirements 7.1, 7.2, 7.6**

### Property 27: WP() 联动无环

审定表块有 `WP()` 引用明细表；明细表块不得反向引用同 wp_code 的审定表。

**Validates: Requirements 7.3, 7.4**

### Property 28: 披露 sheet 名逐字一致（openpyxl 直读）

13 个 `X_DISCLOSURE_SHEET_NAME` 与源 xlsx `wb.sheetnames` 逐字相等（含混合括号与「国有企业」）。

**Validates: Requirements 8.1, 13.6**

### Property 29: 列头分变体且两级表头不压扁

两版用语不同的列头分变体声明（禁共用一份常量）；源模板有跨列合并父表头的表必须用 `group` + 叶子 label；反向断言「两版列头必须不同」。

**Validates: Requirements 8.2, 8.3**

### Property 30: flat/group 两侧都表态

单级表在模板 JSON 的 `columns` 与载荷 `columns` **两侧**都标 `flat`；两级表都声明 `group`。反向自检：缺一侧时 `_infer_groups_from_headers` 会推出凭空父表头。

**Validates: Requirements 8.4, 8.5**

### Property 31: 源模板缺陷按意图实现且登记

K6 两版合计行账面价值按「账面余额 − 减值准备」派生（不推说明文字）；K3 soe 按性质表标签列用 listed 字面；K1 的 11 处 `#REF!` 登记为已知源模板缺陷。

**Validates: Requirements 8.6**

### Property 32: K11 符号翻转在载荷层

K11 明细表正数、披露表负数（源模板注文），翻转在载荷层实现。

**Validates: Requirements 8.7**

### Property 33: 动态插行区逐处判定且作行者标 expandable

**披露 sheet 内的 11 处**标记逐处有「作行/作列头」判定（全册 148 处里其余 137 处在底稿 sheet，不属附注结构范围）；作行者在附注模板对应行 `row_type='expandable'`；作列头者展开为实际类别名。判据词表**必须含 `…` 单字符**（实测 K6-6 三处 + K8/K9 合同检查表两处确实使用它），撤回初稿「`…` 未出现」的记载。

**Validates: Requirements 9.1, 9.2, 9.3, 9.8**

### Property 34: expandable 零可见内容且判据单一真源

`expandable` 行被投影与 Word 导出视为零可见内容；判据 import `note_expandable_markers`，K 类不得另写词表；词表按实测收敛 —— `…`（单字符）在 K 类确有 10 处命中必须纳入，`预留`/`可改名` 零命中不得纳入（配「零命中写法命中数确为 0」的空转自检）。

**Validates: Requirements 9.4, 9.5, 9.7**

### Property 35: 改 rows 的脚本 marker-aware

凡重写整表 rows 的 K 类幂等脚本走 `_note_structure_kit.data_row()`；两写者 `--check` 同时归零。

**Validates: Requirements 9.6**

### Property 36: 账龄单一真源且首档分变体

K1/K3 的账龄行集由 `disclosureAgingLabels` 驱动；soe 首档取 `DISCLOSURE_AGING_WITHIN1_SOE`。反向自检：listed 与 soe 首档字面必须不同。

**Validates: Requirements 10.1, 10.2**

### Property 37: 账龄作列维度者保持为列

K1 两版的前五名表与政府补助表共 4 处账龄列保持为列；月度细分行保留；K3 的「账龄超过1年」段保持独立表。

**Validates: Requirements 10.3, 10.4, 10.5**

### Property 38: 无账龄循环反向锁死

11 个无账龄维度的循环源码不得引用 `disclosureAgingLabels`/`useAgingConfig`/`AGING_BANDS`；配扫描面非空自检。

**Validates: Requirements 10.6**

### Property 39: 多科目表有 report_row_code 且与 report_config 对账

承载多科目的附注表必须有 `report_row_code`，且该码在 `report_config` 中对应的科目与该表语义一致。

**Validates: Requirements 11.1, 11.2**

### Property 40: _row_scope 缺 report_row_code 时 fail-closed 可诊断

模板缺 `report_row_code` 而载荷声明 `_row_scope` 时跳过该表写入，并记录可诊断原因（不得静默）。

**Validates: Requirements 11.3**

### Property 41: 共享章节各写自己的段

K1 与 G2/G3 共用 `五、8`/`八、9` 时，`_row_scope` 下各自只替换自己 owner 的行；单 owner 独占整表者登记豁免。

**Validates: Requirements 11.4, 11.5**

### Property 42: 子表名与模板逐字一致且无污染

每个 `X_SUBTABLE` 值存在于附注模板 `tables[].name`；常量不得含表头文字或英文列 key；K7 两个数组非空。反向自检：K8~K13 的旧值（含 `项目`/`本期发生额`/`non_recurring_amount`）必须打红。

**Validates: Requirements 12.1, 12.2, 12.3**

### Property 43: K1 推送路径已明确

K1 有 `build*Columns` + `buildK1SyncPayload`，或其既有路径已登记且有守卫覆盖。

**Validates: Requirements 12.4**

### Property 44: 列 key 风格同循环一致且分叉已登记

同一循环内列 key 语言一致；跨循环分叉在登记表内且理由含「改 key 会丢已录入数据」。

**Validates: Requirements 12.5**

### Property 45: 载荷元数据齐备

载荷带 `_removed_table_keys`（与本次推送键求差集）；`_note_texts` 带中文 title 且过滤空文本；标签列 key 为 `label`。

**Validates: Requirements 12.6, 12.7, 12.8**

### Property 46: 附注结构三向比对

源 xlsx ↔ 模板 JSON ↔ 载荷 columns 三向一致（openpyxl 直读源侧）。

**Validates: Requirements 13.7**

### Property 47: 每个守卫有反向自检

每个新增守卫配至少一条「复现旧缺陷形态必打红」的自检。

**Validates: Requirements 13.8**

### Property 48: 变异检验 ≥12 项且按失败集合差集判定

变异脚本按「失败测试名集合差集」判 RED/GREEN/ANCHOR-MISS 三态，不看退出码；锚点命中数必须为 1；备份落 `.bak` 且 md5 还原核验。

**Validates: Requirements 13.9**

### Property 49: CI 覆盖

新增 job 覆盖后端守卫 + 前端契约 + 幂等脚本 `--check`；yml 可 `yaml.safe_load` 且无重名 job。

**Validates: Requirements 13.10**

### Property 50: 真实库验收覆盖全组合且独立交叉核对

全部在册项目 × 14 循环逐组合直跑；叶子和 == 父额用独立 SQL 核对；改正前后差异逐条归因到三级分类。

**Validates: Requirements 14.1, 14.2, 14.3**

### Property 51: 浏览器实测覆盖四项且数据复原

覆盖审定表带入 / 溯源面板 / 披露表两变体 / 推送落库；查 `disclosure_notes` 的子表数与列元数据与 expandable；数据按基线逐字节复原并独立只读核实；无活体变体如实登记「未实测」。

**Validates: Requirements 14.4, 14.5, 14.6, 14.7**

### Property 52: 零回归用前后对照

用「当前态 → 施加幂等改动 → 对照」判零回归，不用 HEAD-swap（本 spec 改的数据文件混着并发会话成果）。

**Validates: Requirements 14.8**

## Error Handling

| 场景 | 处理 | 理由 |
|---|---|---|
| `report_config` 无该行 / 公式 NULL | 退兜底码 + `resolved_from='fallback'` | 既有 fail-open，不阻断 render |
| 解析出的码在本项目 `account_chart` 不存在 | 返空 + `empty_reason` | 宁缺勿造；区别于「余额为 0」 |
| 声明的 row_code 是派生行 | `trust_report_config=False` 跳过报表层 | 避免静默退兜底而溯源谎报 |
| 附注模板缺 `report_row_code` 而载荷声明 `_row_scope` | 跳过该表写入 + 记原因 | fail-closed，绝不退化为整表覆盖 |
| 幂等脚本 round-trip 不一致 | exit 2 拒绝写盘 | 防重排整个文件与并发会话互相回退 |
| 变异锚点命中数 ≠ 1 | ANCHOR-MISS（第三态） | 既非 RED 也非 GREEN，是脚本缺陷 |
| GBK 控制台输出含非 ASCII | 脚本内 `write_text(encoding='utf-8')` | 防 `UnicodeEncodeError` 在写库前中止 |

## Testing Strategy

| 层 | 文件 | 形态 |
|---|---|---|
| L1 | `backend/tests/four_table/test_k_cycle_row_code_evidence.py` | **连库**按名反查 + 逐条改正值 + 派生行 + 撞码 + 方向 |
| L1 | `backend/tests/four_table/test_k_cycle_specs.py`（扩展） | 声明表结构 + K1/K2 纳入 + characterization |
| L2 | `backend/tests/four_table/test_k_cycle_extraction.py` | `parent_check` 三态 + K6 prefill + contra 方向 |
| L3 | `backend/tests/four_table/test_k_cycle_formula_presets.py`（扩展） | 科目一致 + 口径 + 覆盖面 + 无污染 + 环检测 |
| L4 | `backend/tests/test_k_source_template_facts.py` | **openpyxl 直读** 26 sheet：名 / 列头 / 两级表头 / 动态标记 / 账龄 |
| L5 | `backend/tests/services/test_note_k_structure_closure.py` | 三向比对 + `report_row_code` + expandable |
| L4/L5 前端 | `composables/__tests__/kCycleNoteContract.spec.ts` | 子表名 / 列 key / flat-group / 账龄真源 / 载荷元数据 |
| L1 前端 | `composables/__tests__/kCycleAccountScope.spec.ts`（扩展） | 读后端 py 源码交叉锁死 |
| L6 | `backend/scripts/diagnose/verify_k_cycle_live.py` | **只读**全组合直跑 + 独立 SQL 交叉核对 |
| L6 | `backend/scripts/diagnose/mutate_k_cycle_guards.py` | ≥12 变异 / 三态判定 / md5 还原 |

**守卫设计约束**（来自平台既有教训）：

- 连库守卫用「一次 `asyncio.run` 取快照 + 全部断言同步」，禁每个测试各自 async（连接池绑首个 loop）
- 源码守卫先 `stripComments()` + AST 剥 docstring，且配「剥注释确实生效」的反向自检
- 截函数体先圆括号配对跳参数列表与返回类型注解，再取含语句特征的花括号块
- 断言「某调用存在」用调用形态 `name\s*\(` 且另加「必须真有调用」断言（import 行会冒充）
- 参数化集合为空 ⇒ 整条 SKIP = 空转，判据抽纯函数 + 无条件替身自检
- 全量扫描类判据做 `(path, mtime_ns, size)` memoization（键必须含 mtime，否则变异检验假绿）

### Property 53: 声明表 docstring 与改正留痕

`k_cycle_specs.py` 的 docstring 不得再出现本次被推翻的旧「实证表」形态 —— 守卫按「旧表特征串」（如 `BS-094` 与 `预计负债` 同现于 docstring 的表格行、`2245` 与「三表零命中」同现）扫描，命中即打红；且每条被改正的循环在声明中必须留下三段留痕（原值 / 该原值实际指向的科目名 / 后果分级取值 ∈ {活错数, 恒空, 仅溯源失真}），缺任一段打红。

反向自检：把某条留痕的「后果分级」删掉必须打红；把 docstring 换回旧表必须打红。

**Validates: Requirements 1.11, 1.12**
