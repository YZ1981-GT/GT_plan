# Design Document

## Overview

8 项遗留分三类，按「平台级 → H 专属 → 活体」分层推进：

- **平台级数据卫生**（R1 `**` 残迹、R6 `report_row_code` 重映射）：都是「全库扫描 + 唯一解析才改 + 无法解析列示待人工 + 幂等脚本 + 守卫 + CI」范式，复用 `backend/scripts/fix/_note_structure_kit.py` 与 `fix_note_headers_plaintext.py` 的既有形态。
- **H 专属接线**（R2 H8/H9 AI+复核、R3 H1/H2/H4/H5/H6 补 AI、R4 H4 薄壳 map、R5 勾稽共享件 + 推广）：全部是前端接线 + 守卫，AI 走既有 `/ai/generate-text`，勾稽把 5 份重复实现提升为共享件后再铺开。
- **活体验证**（R7 上市变体、R8 真实数据端到端）：需临时改库开变体门（破坏性，须用户确认）+ 快照复原。

关键设计取舍：

1. **`**` 剥离只做成对替换**。实证 2 段是脱敏占位（奇数个 `**`），无脑 `replace('**','')` 会把它们也吃掉。用正则 `\*\*(.+?)\*\*` 非贪婪成对匹配，剩余的孤立 `**` 天然不动；并对「奇数个 `**` 的段」单独列示供人工确认。
2. **`report_row_code` 按行标签反查而非按位移猜**。旧编号看似整体位移，但位移量不一致（`BS-014` 固定资产 vs 现 `BS-028` 差 14；`BS-004` 应收票据 vs 现 `BS-005` 差 1），任何「统一加 N」的猜测都是错的。唯一可靠依据 = `report_config.row_name` 逐字等于附注行标签。标签含 `其中：` 前缀或以 `：` 结尾者先归一再查；仍无法唯一解析的保留并列示。
3. **勾稽共享件是纯函数 + 声明式规则**，不是 9 份 bespoke 引擎。`disclosureConsistency.ts` 已存在（N 循环建的 `composables/shared/disclosureConsistency.ts`），先核实其 API 覆盖度，能覆盖则各循环只写规则表；不足则扩展它而不新建。
4. **H4 薄壳必须内联字面量**。registry 生成器用 text-scan 抽 `listed: '…'`，写标识符引用会让整条 wp_code 从 registry 消失；对象体内也不能写注释（注释里的 `listed: '…'` 会被优先抓到）。这两条已在 H10 实证。
5. **AI 接线复用共享 composable**。`composables/useDisclosureNoteAi.ts`（D 循环建）与 `composables/shared/wpAiText.ts`（N 循环建）已封装正确端点/字段/响应解析，H8/H9 直接接，不再各写一份 `api.post`。

## Architecture

```
平台级数据卫生
  backend/scripts/fix/fix_note_bold_markers.py          (R1, 新建)
      └─ _note_structure_kit.py (复用 load/save/apply 与 --dry-run/--check/--apply 骨架)
  backend/scripts/fix/remap_note_report_row_codes.py    (R6, 新建)
      └─ report_config (DB, 只读) → row_name → row_code 唯一解析表
  backend/tests/test_note_bold_marker_hygiene.py        (R1 守卫)
  backend/tests/test_note_report_row_code_alignment.py  (R6 守卫)

H 专属接线
  frontend/src/components/workpaper/
    h8/core/H8TabDisclosure{Listed,Soe}.vue   → useDisclosureNoteAi + GtReviewTrigger   (R2)
    h9/core/H9TabDisclosure{Listed,Soe}.vue   → 同上                                     (R2)
    h1/h2/h4/h5/h6 披露 Tab                    → 补 AI 按钮 + prompt 登记                 (R3)
    composables/h4NoteSectionMap.ts            → 薄壳 re-export                          (R4)
    composables/shared/disclosureConsistency.ts→ 共享勾稽件（扩展既有）                    (R5)
    composables/h{2,3,5,7,8,9,10}DisclosureConsistency.ts → 规则表 + 委托共享件            (R5)
    shared/disclosure/WpDisclosureConsistencyPanel.vue    → 统一面板（既有，直接复用）       (R5)
  backend/app/routers/review_dialog.py         → _SECTION_PROMPTS 补 H1/H2/H4/H5/H6/H8/H9 (R2,R3)

守卫与 CI
  composables/__tests__/hDisclosureAiWiring.spec.ts          (R2,R3)
  composables/__tests__/h4NoteSectionMapShell.spec.ts        (R4)
  composables/__tests__/hDisclosureConsistency.spec.ts       (R5)
  composables/__tests__/noteSectionMapNamingCoverage.spec.ts (R4 平台级命名覆盖)
  backend/tests/test_review_dialog_h_cycle_prompts.py        (R2,R3 四处登记交叉)
  .github/workflows/governance-checks.yml → jobs:
    note-bold-marker-hygiene / note-report-row-code / h-cycle-ai-wiring / h-cycle-consistency
```

## Components and Interfaces

### `fix_note_bold_markers.py`（R1）

```python
BOLD_PAIR = re.compile(r'\*\*(.+?)\*\*', re.S)

def strip_pairs(text: str) -> tuple[str, int]:
    """成对剥离，返回 (新文本, 剥离对数)。不成对的 `**` 原样保留。"""

def scan(doc: dict) -> list[Finding]:
    """扫 text_sections / guidance / headers / rows[].label（含嵌套 children 与 tables）"""

def odd_marker_paragraphs(doc: dict) -> list[Finding]:
    """`**` 出现次数为奇数的段落，供人工确认（脚本不改）"""
```

CLI: `--dry-run`（默认） / `--check`（有成对残迹则 exit 1） / `--apply`。

### `remap_note_report_row_codes.py`（R6）

```python
@dataclass
class Resolution:
    variant: str; section: str; label: str
    old_code: str; new_code: str | None; reason: str   # 'ok' | 'ambiguous' | 'not_found' | 'unchanged'

def build_label_index(db) -> dict[str, set[str]]:
    """report_config: 归一化 row_name → {row_code}；多码即 ambiguous"""

def normalize_label(s: str) -> str:
    """去 `其中：` 前缀、尾部 `：`、全角空格、`减：` 前缀"""
```

`--apply` 只改 `reason == 'ok'` 的行。

### AI 接线（R2/R3）

各披露 Tab 统一：

```ts
const ai = useDisclosureNoteAi({ wpId: () => props.wpId })
async function runAi(sectionKey: string) {
  const text = await ai.generate({
    section: `H8-disc-${props.variant}-${sectionKey}`,
    context: { 变体: variantLabel.value, 表名: tableLabel(sectionKey) },   // 值必须是 string
    existingContent: noteTexts.value[sectionKey] ?? '',
  })
  if (text) { noteTexts.value[sectionKey] = text; persist() }
}
```

复核统一用 `<GtReviewTrigger :section-id="..." />`（H10 已是此形态，H8/H9 照抄），删掉 `emit('open-review')`。

### 勾稽共享件（R5）

先核实 `composables/shared/disclosureConsistency.ts` 现有 API；目标签名：

```ts
export interface ConsistencyCheck {
  label: string; rule: string
  left: number | null; right: number | null
  diff: number | null
  level: 'ok' | 'warn' | 'error' | 'na'
  detail?: string
  refs?: string[]        // GtIndexChip 追溯
}
export function eqCheck(opts: {label, rule, left, right, tol?, refs?}): ConsistencyCheck
export function subsetCheck(opts: {label, rule, part, whole, refs?}): ConsistencyCheck
export function summarize(checks: ConsistencyCheck[]): { ok: number; warn: number; error: number; na: number }
```

每循环一个 `h{N}DisclosureConsistency.ts` 只导出 `buildH{N}Checks(snapshot): ConsistencyCheck[]`，规则全部标注源模板依据。

### H4 薄壳（R4）

```ts
// h4NoteSectionMap.ts —— 薄壳；真源在 h4DisclosureSyncPayload.ts / h4SoeDisclosureSyncPayload.ts
export const H4_NOTE_SECTION = { listed: '五、23', soe: '八、23' } as const
export const H4_DISCLOSURE_SHEET_NAME = { listed: '<源 xlsx tab 名>', soe: '<源 xlsx tab 名>' } as const
export { buildH4ListedSyncPayload } from './h4DisclosureSyncPayload'
export { buildH4SoeSyncPayloads } from './h4SoeDisclosureSyncPayload'
```

注意：H4 与 H2 共用附注章节（H4 推「工程物资」子表），故章节号必须与 `h2NoteSectionMap` 一致 —— 契约测试交叉断言。

## Data Models

### `note_template_{listed,soe}.json` 受影响字段

| 路径 | R1 | R6 |
|------|----|----|
| `sections[].text_sections[]` | 成对 `**` 剥离 | — |
| `sections[].tables[].guidance` | 成对 `**` 剥离 | — |
| `sections[].tables[].headers[]` | 扫描（实测 0 处） | — |
| `sections[].rows[].label` / `tables[].rows[].label` | 扫描（实测 0 处） | 用于反查 |
| `sections[].rows[].report_row_code` | — | 重映射 |
| `sections[].rows[].account_codes` | — | **不动** |

### `report_config`（只读真源）

| 列 | 说明 |
|----|------|
| `row_code` | 报表行编号（`BS-xxx` / `IS-xxx`） |
| `row_name` | 行名，反查键 |
| `standard` | 准则（四条：`listed_standalone` / `listed` / `soe_standalone` / `soe`）；同一 row_code 四准则 `row_name` 一致，故反查不需按准则区分 |

### 实证陈旧样本（R6）

| 附注行标签 | 现写 `report_row_code` | 该码当前 `row_name` | 应为 |
|-----------|----------------------|-------------------|------|
| 固定资产 | `BS-014` | 其他流动资产 | `BS-028` |
| 短期借款 | `BS-031` | 使用权资产 | `BS-041` |
| 长期借款 | `BS-041` | 短期借款 | 需反查 |
| 应收票据 | `BS-004` | 衍生金融资产 | `BS-005` |
| 应收账款 | `BS-005` | 应收票据 | 需反查 |
| 存货 | `BS-008` | 预付款项 | `BS-010` |
| 应付账款 | `BS-033` | 开发支出 | `BS-045` |

位移量不一致（14 / 10 / 1 / 2 / 12）→ 证明不能用统一偏移，必须按标签反查。

## Correctness Properties

### Property 1: 成对剥离保内容

对任意文本 `t`，`strip_pairs(t)` 的结果去掉所有 `*` 后 SHALL 等于 `t` 去掉所有 `*` 后的结果；且结果中 `**` 的出现次数 SHALL 等于 `t` 中 `**` 次数减去 2×剥离对数。

**Validates: Requirements 1.2, 1.6**

### Property 2: 不成对保留

对任意只含奇数个 `**` 的文本，`strip_pairs` SHALL 返回原文本且剥离对数为 0。

**Validates: Requirements 1.3**

### Property 3: 幂等

对任意 `t`，`strip_pairs(strip_pairs(t)[0])[1] == 0`。

**Validates: Requirements 1.4, 6.5**

### Property 4: 重映射唯一解析

对任意附注行，若其归一化标签在 `report_config` 反查索引里对应**恰好一个** `row_code`，则重映射后该行 `report_row_code` SHALL 等于该码；否则 SHALL 保持原值且被列为待人工核对。

**Validates: Requirements 6.2, 6.3**

### Property 5: 重映射不越界

重映射前后，每行除 `report_row_code` 外的所有键值 SHALL 逐字不变。

**Validates: Requirements 6.3**

### Property 6: AI 请求体形态

对任意 H 循环披露 AI 调用，其 body SHALL 含 `section` / `prompt` / `existingContent` 三键，且 `context` SHALL 是对象且每个值 `typeof === 'string'`。

**Validates: Requirements 2.1**

### Property 7: 无孤儿事件按钮

对 `components/workpaper` 下每个披露 Tab，其模板中 `emit('X', …)` 的每个事件名 `X`，SHALL 或被本组件 `defineEmits` 声明且被至少一个宿主以 `@X=` 处理，或不属于 AI/复核语义。

**Validates: Requirements 2.6**

### Property 8: prompt 登记完备

对前端所有 H 循环披露 AI section 键集，后端 `_SECTION_PROMPTS` SHALL 全部登记；且 `_SECTION_PROMPTS` 中以 H 循环前缀开头的键 SHALL 全部能在前端找到调用点（无孤儿）。

**Validates: Requirements 3.2, 3.3**

### Property 9: registry 命名覆盖

对每个存在 `{code}DisclosureSyncPayload.ts` 或 `{code}NoteSectionMap.ts` 的循环码 `code`，`note_workpaper_sync_registry.json` SHALL 含该 `code` 条目，除非 `code` 在 allowlist 中且写明理由。

**Validates: Requirements 4.1, 4.4**

### Property 10: 薄壳字面量一致

`h4NoteSectionMap.H4_NOTE_SECTION` SHALL 逐字等于 `h2NoteSectionMap.H2_NOTE_SECTION`（共用章节），`H4_DISCLOSURE_SHEET_NAME` SHALL 逐字等于源 xlsx tab 名。

**Validates: Requirements 4.3**

### Property 11: 勾稽无数据不误报

对任意勾稽规则，若 `left` 与 `right` 任一为 `null`，则结果 `level` SHALL 为 `'na'` 且 `diff` SHALL 为 `null`。

**Validates: Requirements 5.4**

### Property 12: 勾稽容差

对任意 `eqCheck`，`|left - right| <= tol`（默认 0.01）时 `level` SHALL 为 `'ok'`；否则 SHALL 为 `'error'`。

**Validates: Requirements 5.1**

## Error Handling

| 场景 | 处理 |
|------|------|
| `**` 剥离遇到嵌套 `****` | 非贪婪成对匹配天然按最内层处理；剥离后重跑一次直到无变更（幂等循环 ≤3 轮，超出即报错并列示该段） |
| `report_config` 查不到某标签 | 归入 `not_found`，保留原码，`--check` 列示；不猜测 |
| 同一标签映射到多个 `row_code` | 归入 `ambiguous`，保留原码并列示两个候选码 |
| AI 端点 4xx/5xx | `useDisclosureNoteAi` 已有 `ElMessage.error` 提示 + 按钮 loading 复位；**禁止裸 `catch {}`**（会让失败无人察觉） |
| AI 返回空文本 | 不覆盖既有文本，提示「AI 未返回内容」 |
| 勾稽某侧取数为 `null` | `level='na'`，面板显示「暂无可比对数据」，不计入异常数 |
| registry 生成器扫不到新薄壳 | 命名覆盖守卫直接红，报出缺失的 code 与期望文件名 |
| 活体验证临时改 `entity_type` | 改前用 SQL 记录原值到快照文件；验证完立即复原并再查一次比对 |

## Testing Strategy

**后端**

- `test_note_bold_marker_hygiene.py`：全库断言无成对 `**`；含反向自检（内联 fixture：成对必被抓、奇数个必放行）；断言 `strip_pairs` 满足 Property 1~3（hypothesis PBT，`max_examples=5`）。
- `test_note_report_row_code_alignment.py`：对每条带 `report_row_code` 的行按标签反查断言一致；`ambiguous`/`not_found` 走 allowlist 且每条须写 `reason`；含反向自检（构造一条错码 fixture 断言检测器能抓到）。
- `test_review_dialog_h_cycle_prompts.py`：从前端 SFC 源码正则抽 AI section 键集 → 断言后端 `_SECTION_PROMPTS` 全登记、每条 ≥20 字且含「不得虚构」、无孤儿；抽取结果非空自检（防正则失效空转）。

**前端**

- `hDisclosureAiWiring.spec.ts`：扫 H1~H10 披露 Tab 源码（先 `stripComments()` 且对 `stripComments` 本身用内联 fixture 自检）—— 每个 AI 按钮必指向真调端点的函数；禁 `emit('open-ai'|'open-review')`；`context` 值非字符串字面量即红；按钮须有 `:loading` 与 `:disabled="isReadonly"`。
- `h4NoteSectionMapShell.spec.ts`：Property 10 交叉锁死。
- `noteSectionMapNamingCoverage.spec.ts`：Property 9，`import.meta.glob` 自动纳新循环。
- `hDisclosureConsistency.spec.ts`：Property 11/12 + 每循环规则表逐条断言（含 PBT：随机金额下 `eqCheck` 判定与 `|diff|<=tol` 等价）。

**活体**

chrome-devtools MCP 驱动浏览器 + postgres MCP 只读比对。每次实测前后完整快照/复原（`table_data` 键集、`text_content` 全文、`last_sync_at`、`checklist_responses` 计数）。

**CI**

`governance-checks.yml` 新增 4 job：`note-bold-marker-hygiene` / `note-report-row-code` / `h-cycle-ai-wiring` / `h-cycle-consistency`。
