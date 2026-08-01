# Design: D 类循环取数链路补齐（D2/D3/D5/D6/D7）

## Overview

复用 D1 已验证的三层结构，不新建机制：

```
report_config.formula（按 applicable_standard）
        │  resolve_report_line_account_codes(row_code, fallback)
        ▼
标准码集合  ──拆分──►  原值码集 / 备抵码集      （account_chart.direction / 名称关键字）
        │  account_mapping(project_id, standard→original)
        ▼
原始码集  ──►  tb_balance 叶子聚合  ──►  明细行 transient seed（Tier B）
        └──►  trial_balance 标量     ──►  审定表 TB 核对行（Tier A 公式 + seed 回退）
```

三条硬约束（均来自 D1 实测教训）：

1. **Tier A 预设与 render 回退标量必须同口径**。审定表「三、xx净值」被比较时，
   TB 侧必须是净额；两侧任一留在原值口径都会产生「差异恰好等于备抵」的假差异。
2. **`tb_source_codes` 必须有前端消费方**，否则是 dead output（D1/H1 都踩过）。
3. **附注模板 `columns` 与同步载荷 `columns` 两处都要表态 `flat`/`group`**，
   只改一侧会让另一条路径（seed / 推送）继续被前缀推断塞凭空父表头。

## Architecture

### 后端

| 层 | 文件 | 本 spec 动作 |
|----|------|-------------|
| 共享科目解析 | `app/services/four_table/{report_line_accounts,leaf_aggregation}.py` | 复用（K1/F1 已提升为共享件），**不再抄第二份** |
| D1 专用解析 | `app/services/d_cycle_extraction/d1_account_resolver.py` | 作为范式；D2/D6 若差异仅在 row_code+fallback，则**参数化复用**而非复制 |
| Tier A 预设数据 | `data/d_cycle_extraction/d_cycle_extraction_presets.json` | D2 改净额、D6 改 `1141`、D5 按裁决处理 |
| render 策略 | `app/routers/wp_render_strategies/_d{2,3,5,6,7}_*.py` | 接科目解析 + `tb_source_codes` + 净额归一 |
| 溯源登记 | `app/services/d_cycle_extraction/presets.py::_TIER_B_PROVENANCE` | 逐循环更新描述 |
| 附注模板修订 | `scripts/fix/fix_note_d2_ar_structure.py`（新建） | 两版 30 表 columns/guidance/占位行 |

### 前端

| 层 | 文件 | 本 spec 动作 |
|----|------|-------------|
| 取数溯源展示 | `D{2,6}TabAdjudication.vue` + 宿主 `Gt*.vue` | 消费 `tb_source_codes` / 净额溯源，消除 dead output |
| 披露小节标题 | `D{2,3,5,6,7}TabDisclosure*.vue` | 按源模板逐字修正 + 编号不重复 |
| 账龄枚举 | `composables/useAgingConfig` + `disclosureAgingLabels` | 复用单一真源，禁硬编码档位 |
| 同步映射 | `composables/d{2,3,5,6,7}NoteSectionMap.ts` | 列键/表名与模板对齐；历史表名进 `_removed_table_keys` |

## Components and Interfaces

### 1. 科目解析（参数化复用）

```python
# 每循环只声明 row_code + fallback + 备抵语义，解析逻辑共享
D_CYCLE_ACCOUNT_SPEC = {
    "D2": ReportLineAccountSpec(row_code="BS-006", fallback=["1122", "1231-02"]),
    "D3": ReportLineAccountSpec(row_code="BS-046", fallback=["2203"]),
    "D6": ReportLineAccountSpec(row_code="BS-011", fallback=["1141"]),
    "D7": ReportLineAccountSpec(row_code="BS-047", fallback=["2205"]),
}
```

### 2. 净额归一（D1 已落地，D2 复用同形）

```python
def _net_tb_amount(project_context: dict) -> None:
    """tb_amount 三口径统一减备抵，原值移入 tb_amount_gross*。
    无备抵数据 → 完全空操作（保灰度开/关逐字节等价）。"""
```

### 3. 附注模板幂等修订脚本

沿用 `fix_note_d1_notes_receivable_structure.py` 的结构：
`_flat_columns` / `_grouped_columns` / `_derive_column_groups` / `_rule(aliases=)` /
`apply_plan(游标只前进)` / `validate_section` / `titleize_text_sections` /
`LEGACY_TABLE_NAMES`，CLI 支持 `--dry-run` / `--check` / `--variant`。

## Data Models

### `tb_source_codes`（render → 前端，additive）

```jsonc
{
  "gross": ["1122"],              // 原始码（tb_balance 用）
  "provision": ["1231.02"],
  "gross_standard": ["1122"],     // 标准码（trial_balance 用）
  "provision_standard": ["1231-02"],
  "resolved_from": "report_config" // 或 "fallback"
}
```

### `project_context` 的 TB 核对标量（D2 与 D1 同形）

```jsonc
{
  "tb_amount": 19046910.15,        // 净额（与 Tier A 预设同口径）
  "tb_amount_gross": 20209198.18,  // 原值（仅溯源展示）
  "tb_provision_amount": 1162288.03
}
```

### 附注子表列定义（`ColumnDef`）

```jsonc
{ "key": "end_balance", "label": "账面余额", "group": "期末余额", "format": "amount" }
{ "key": "label", "label": "类别", "is_label": true, "flat": true }
```

## Correctness Properties

### Property 1: 取数科目来自报表映射且存在于标准科目表

对任意 D 类循环，其取数科目集合要么来自 `report_config.formula` 解析结果，
要么来自显式 fallback；两者的每个码都必须存在于 `account_chart`（`source='standard'`）。

**Validates: Requirements 1.1, 1.4, 2.1, 2.4, 4.1**

### Property 2: 备抵拆分正确

解析出的标准码集合按 `direction=='credit'` 或名含「坏账准备」/「减值准备」拆分后，
原值码集与备抵码集无交集，且并集等于解析结果。

**Validates: Requirements 1.2**

### Property 3: 叶子聚合守恒

对任意科目前缀，叶子科目期末余额之和等于该前缀父科目的期末余额。

**Validates: Requirements 1.3**

### Property 4: 灰度关时逐字节等价

灰度开关为 False 时，各 render 输出与本 spec 改动前逐字节相同。

**Validates: Requirements 1.6, 3.3**

### Property 5: TB 核对行两侧同口径

Tier A 预设求值结果与 render 下发的 seed 回退标量在同一项目上相等；
无备抵数据时两者都等于原值。

**Validates: Requirements 3.1, 3.2, 3.3, 8.2**

### Property 6: 取数输出必有消费方

render 输出的 `tb_source_codes` 与净额溯源键在前端源码中存在读取点。

**Validates: Requirements 1.5, 3.4**

### Property 7: 附注模板列表态完备

附注各表的 `columns` 恰好在 `flat` 与 `group` 之间表态其一，
`headers` 与 `columns[].label` 逐位一致且不含 HTML，`guidance` 不含 markdown 粗体。

**Validates: Requirements 5.3, 5.5, 6.5**

### Property 8: 附注模板无占位假行

模板 `rows` 中不存在 `row_type=header_label`，也不存在标签为
「可无限量添加行」/「出票人类型或账龄」/「……」的行。

**Validates: Requirements 5.4**

### Property 9: 表名与源模板小节标题一致

附注各表名（归一去小节编号 /「其中：」/「如下」/ 尾冒号后）出现在源 xlsx
对应披露 sheet 的标题集合中。

**Validates: Requirements 5.1, 6.1, 8.3**

### Property 10: 披露小节编号唯一

同一披露页内各小节标题的「（N）」编号不重复。

**Validates: Requirements 6.2**

### Property 11: 账龄档位由项目枚举驱动

披露表按账龄分档的行集与 `useAgingConfig` 返回的段集同构；
不属于当前段集的既有行名以只读提示呈现且数据不被删除。

**Validates: Requirements 6.3, 6.4**

### Property 12: 公式预设可信

`prefill_formula_mapping.json` 中 D 类各条目的 `sheet` ∈ 源模板真实 sheet 名集合、
科目码 ∈ `account_chart`、`TB_AUX` 维度 ∈ 平台已知维度；明细表侧不含 `WP()`。

**Validates: Requirements 7.1, 7.2, 7.3**

## Error Handling

取数链路一律 **fail-open**：任何一环失败都只降级、不阻断 render（底稿必须能打开）。

| 失败点 | 处理 | 可观测性 |
|--------|------|---------|
| `report_config` 无该报表行 / 解析抛异常 | 回退显式 fallback 码集 | `tb_source_codes.resolved_from='fallback'` + `logger.warning` |
| `account_mapping` 反解为空 | 回退「标准码去 `-` 作前缀」 | 同上（`provision_resolved_from`） |
| `trial_balance` / `tb_balance` 查询异常 | 不写对应键，前端按缺省 0 处理 | `logger.warning`，不抛 |
| 备抵科目无数据 | 净额归一**空操作**（净额恒等于原值） | 不造 `tb_amount_gross` 键 → 灰度开/关逐字节等价 |
| 明细 seed 异常 | 跳过 seed，明细表保持手工录入 | `logger.warning` |
| 已有手工数据 | **手工优先**，seed 一律不覆盖 | 判定用「完全空 / 全零骨架」而非「remark 非空」 |
| 附注同步跨主体类型 | 服务端 `detect_standard_conflict` → 409 | 前端静默（宁可不写也不写错章节） |

幂等脚本：`--check` 只读返回非零表示欠账；写入前先 `validate_section`，
校验不通过则**不落盘**（避免写出半对结构）。

## Testing Strategy

四层，与 D1 同构：

1. **纯函数单测**：科目拆分 / 叶子聚合 / 净额归一 / 行列构造。含 PBT（叶子和 == 父额）。
2. **render 集成（fake session）**：灰度开/关逐字节等价、seed 手工优先、fail-open。
   🔴 fake session 必须按 SQL/params **区分原值与备抵两次 `trial_balance` 查询**，
   否则备抵 == 原值、净额恒为 0，守卫变噪声（D1 实测踩过）。
3. **结构守卫**：附注模板 `columns`/`headers`/`rows`/`guidance` + **openpyxl 直读源 xlsx
   交叉比对表名**，每条都配反向自检（防正则/查询失效导致断言空转）。
   前端契约 `d2NoteSubtableContract.spec.ts` 锁死「载荷子表名 ↔ 模板表名」。
4. **浏览器实测**（chrome-devtools + postgres 只读）：四表入库 → 底稿有数 → 披露有数 →
   推送后附注落库；测试数据用后复原。**判「录入是否真落库」只能查 `checklist_responses`**，
   不能看界面显示值。

CI：新增 job `d-cycle-extraction-chain`（后端）与 `d-cycle-extraction-chain-frontend`。
