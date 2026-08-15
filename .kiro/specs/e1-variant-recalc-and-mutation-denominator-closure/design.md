# Design Document

## Overview

两组改动，共用一条主线：**断言半径必须覆盖到「跨层口径不一致」这类缺陷**。

- **A 组**修 E1-3 的 `multi` 口径重算：让它区分「本位币恒等形态」与「外币待录入形态」，而不是无条件由原币列派生。改动落在**消费侧**（`useE1BankDetail`），种子侧一行不动。
- **B 组**把变异检验的样板收敛成共享件 `backend/scripts/_mutation_kit/`，把 `mutate_e_cycle_guards.py` 里那套「覆盖面分母 + 静态锚点自检 + 冻结基线 + 四态判定」变成所有脚本默认具备的能力，并用守卫钉死不许退化。

A 组的新守卫用 B 组的共享件写 —— 这既是推广的第一个真实用例，也让「跨层守卫」和「分母机制」互相验证。

---

## Architecture

### A 组：为什么修消费侧而不是种子侧

E1-3 的行有**三个来源**，它们对「原币列」的能力根本不同：

| 来源 | 本位币列 | 原币列 | 能不能改成「下发真实原币」 |
|---|---|---|---|
| 账户级 `buildBankSeedRowsFromAccounts(p,'multi')` | 有 | 本位币账户 = 恒等；外币 = 0 + 提示 | 已是最优（四表无原币数据） |
| 账户级 `buildBankSeedRowsFromAccounts(p,'rmb')` | 有 | **不下发**（AC 1.4 有意如此） | 不能（守卫 + AC 1.9 锁死字段集差异） |
| 叶子口径 `buildBankSeedRows(p)` | 有 | 无条件 `fxRate:1` + `fc` 全 **0** | **不能** —— 叶子行是科目级汇总，没有账户更没有币种 |
| 手工录入（`addRow` + `updateCell`） | 审计师填 | `rmb` 版界面不显示，故留空 | 不能（不能要求审计师在人民币版填原币） |

叶子口径那一行是关键：它的 `fc` 全 0 是**结构性**的，改不动。所以「让写入侧总是给出真实原币」这条路走不通 —— 必须让消费侧能正确处理「只有本位币列」的行。

这同时解释了一个比归档 spec 登记的更严重的事实：**走叶子口径兜底的项目（aux 侧无银行账户数据），E1-3 的 `multi` 版金额恒为 0，连 variant 都不用切**。这是改造前就存在的存量缺陷，账户级取数把它改善成「先开 multi 即正确」，但兜底路径至今未修。

### A 组：三形态判定

```
                      ┌─ fc 列有任一非 0 ────────────────► 形态 C「原币权威」
recalcRow(row,'multi')─┤
                      └─ fc 列全 0 ─┬─ fxCurrency 是本位币 ─► 形态 A「本位币恒等」
                                    └─ fxCurrency 非本位币 ─► 形态 B「外币待录入」
```

| 形态 | 本位币六列 | 原币小计列 | fxRate | note |
|---|---|---|---|---|
| **A** 本位币恒等 | **保留输入值**，`ending`/`audited` 按本位币链式算 | 按本位币镜像（原币 == 本位币） | 1 | 不变 |
| **B** 外币待录入 | 保持 0（现状） | 0 | 0（**不得回落 1**） | 带 `FOREIGN_FC_HINT` |
| **C** 原币权威 | 由 `原币 × fxRate` 派生（现状） | 按 fc 链式算 | 输入值 | 不变 |

**判据选 `fxCurrency` 而不选 `fxRate`**：`fxRate` 当前被 `|| 1` 压成两态（见下），拿它区分形态会把形态 B 误判成 A ⇒ 给外币行臆造汇率 1，正是 Property 34 禁止的。`fxCurrency` 有 `String(r.fxCurrency || '人民币')` 的确定回落，且 `isBaseCurrency()` 已是单一真源。

### A 组：fxRate 三态归一

```
现状  fxRate: parseNum(r.fxRate) || 1
      ├─ undefined / ''  → 0 → 1   ← 需要的正是 1（恒等），巧合正确
      ├─ 显式 0          → 0 → 1   🔴 「待录入」标记丢失
      └─ 真实值          → 原值      正确

改为  fxRate: (r.fxRate === null || r.fxRate === undefined || r.fxRate === '')
               ? 1                    ← 缺失 = 本位币恒等（形态 A 的默认）
               : parseNum(r.fxRate)   ← 显式值原样保留，含 0
```

只有一处改动，但它是形态 B 能否成立的前提：形态 B 的行要靠 `fxRate === 0` 让界面显示「汇率待录入」而不是一个看起来已填好的 1。

### A 组：数据损坏路径的封堵点

```
watch(variant) / loadFromResponses
        ↓ recalcRow(row, 'multi')            ← ★ 唯一修复点（形态判定）
   rows.value 归零
        ↓ watch(rows → syncCrossSheetTotals)  immediate:true
   4 个跨 sheet 聚合键归零（E1-1 审定表取数源）
        ↓ 任一 updateCell/addRow/removeRow/onConfirmationReceived
   scheduleSave() → 2s → persistToResponses()
        ↓ serializeRows(rows, USER_FIELDS)    USER_FIELDS 含 opening/increase/decrease
   0 落库，原值不可恢复
```

修复只需堵住 `recalcRow`：上游 `watch` 的设计意图（variant 变则重算）正确，下游持久化与聚合是正常机制。**不在下游加防御**（例如「落库前检查是否变 0」），那种防御会掩盖真因，且无法区分「合法的 0」与「派生失败的 0」。

### B 组：共享件的位置与导入方式

```
backend/scripts/_mutation_kit/
    __init__.py     公开 API（Mutation / run_cli / CoverageTally / ...）
    spec.py         Mutation 数据类 + 声明期校验（kind/anchor/want 完整性）
    anchor.py       锚点定位：行级唯一 + 行号消歧 + 逐字相等 + CRLF 安全
    apply.py        备份 / 应用 / 还原（finally + md5 逐字核验）
    runner.py       pytest / vitest 执行 + 失败测试名集合提取
    verdict.py      四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST）
    coverage.py     覆盖面分母 tally（守卫文件全集 → 未被打红清单）
    cli.py          --list / --check-anchors / --run / --restore 统一入口
```

放 `backend/scripts/` 下而不是 `check/` 或 `diagnose/` 之一，因为两个目录都要用。调用方顶部：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/scripts
from _mutation_kit import Mutation, run_cli
```

与现有 `REPO = Path(__file__).resolve().parents[3]` 的惯例同族（都靠 `parents[n]` 定位，不依赖 cwd）。**零新增第三方依赖**：只用 `argparse` / `hashlib` / `subprocess` / `dataclasses` / `pathlib` / `json` / `re`。

### B 组：迁移批次由「所属 spec 是否在办」决定

```
批次 1（先入库，不改内容）  7 个 mutate_task*.py + wp_export_resolver（?? 未跟踪）
批次 2（迁共享件）          e_cycle · h_cycle · g7 · trim_decision
                            · note_conversion · note_text_hygiene  （6 个，已归档）
批次 3（迁共享件）          批次 1 入库后视其可运行性决定
不迁（登记豁免）            k_cycle · i_cycle · ie_lifecycle       （3 个，在办）
```

`mutate_e_cycle_guards.py` 是范式基准，**它的迁移要最先做**：它已具备全部七项能力，迁移中若某项能力在共享件里表达不出来，说明共享件设计不足，此时改共享件而不是削减该脚本的能力。

### B 组：豁免登记表

```json
// backend/data/mutation_kit_exemptions.json
{
  "exemptions": [
    {
      "script": "backend/scripts/diagnose/mutate_k_cycle_guards.py",
      "spec": "k-cycle-extraction-formula-and-disclosure-closure",
      "reason": "spec 在办（19/25），并发会话正在编辑该脚本，迁移会与其打架",
      "registered_at": "2026-08-15",
      "revoke_when": "spec 归档后"
    }
  ]
}
```

守卫读它做两件事：① 未跟踪/未用共享件的脚本若在豁免表内则跳过；② 若某豁免项的 `spec` 已不在 `.kiro/specs/` 下（= 已归档），**提示该豁免应当撤销**（防止豁免变成永久免责声明 —— 这正是 e-cycle spec 的 M20 变异所针对的形态）。

---

## Components and Interfaces

### A 组改动清单

| 文件 | 改动 | 性质 |
|---|---|---|
| `composables/useE1BankDetail.ts` | `recalcRow` 加三形态判定；`loadFromResponses` 的 `fxRate` 三态归一 | 行为修复 |
| `composables/useE1BankDetail.ts` | 抽 `classifyFxForm(row)` 纯函数（形态判定单一真源） | 新增 |
| `composables/__tests__/e1BankVariantIntegrity.spec.ts` | 新建：跨层端到端守卫（variantA × variantB 四组合 × 三来源） | 新增守卫 |
| `composables/__tests__/e1BankDetailFxForm.spec.ts` | 新建：三形态判定 + fxRate 三态 + 零回归 | 新增守卫 |

`classifyFxForm` 单独抽出来的理由：形态判定要被 `recalcRow` 与守卫共同引用，且它是纯函数（无 Vue 依赖）便于 PBT。签名：

```typescript
export type FxForm = 'base-identity' | 'foreign-pending' | 'fc-authoritative'
export function classifyFxForm(row: Pick<BankDetailRow,
  'openingFc' | 'increaseFc' | 'decreaseFc' | 'adjustmentFc' | 'fxCurrency'>): FxForm
```

### B 组共享件公开 API

```python
@dataclass
class Mutation:
    id: str
    side: str                 # be | fe
    path: str                 # 仓库相对路径
    kind: str                 # replace | delete | insert | swap | move
    anchor: str               # 行级唯一，不含 \n
    want: str                 # 期望打红的测试名（子串匹配）
    why: str                  # 为什么这条变异有效（防无效变异）
    new: str = ""
    anchor2: str = ""
    line: int = 0             # 多处命中时的消歧行号
    block_open: str = ""
    tags: tuple[str, ...] = ()

def run_cli(
    *,
    mutations: list[Mutation],
    guard_files: dict[str, str],        # 覆盖面分母：守卫文件 → 归属说明
    backend_args: list[str] | None,     # pytest 参数
    frontend_args: list[str] | None,    # vitest 参数
    baseline_backend_passed: int | None,
    baseline_frontend_passed: int | None,
    repo: Path,
) -> int: ...
```

`guard_files` 是必填参数而非可选 —— 让「没有分母」在**签名层面**不可能，而不是靠约定。

### B 组守卫

| 守卫 | 判据 |
|---|---|
| `test_mutation_kit_scripts_tracked.py` | 扫 `mutate*.py`，未被 git 跟踪且不在豁免表 ⇒ 失败 |
| `test_mutation_kit_adoption.py` | 扫 `mutate*.py`，未 `from _mutation_kit import` 且不在豁免表 ⇒ 失败 |
| `test_mutation_kit_exemptions.py` | 豁免项的 spec 已归档 ⇒ 失败（提示撤销）；豁免项缺 reason/registered_at ⇒ 失败 |
| `test_mutation_kit_capabilities.py` | 共享件自身七项能力的行为测试（不是「函数存在」） |

---

## Data Models

### A 组：不新增字段

`BankDetailRow` 的字段集**不变**，`USER_FIELDS` 不变，持久化键不变（`E1-bank-detail-rows` / `E1-bank-variant`）。形态是从现有字段**推导**出来的，不落库 —— 落库一个 `fxForm` 字段会立刻产生「存的形态与实际字段不一致」的第二真源。

### A 组：形态 A 下原币小计列的口径

形态 A 认定「原币 == 本位币」，故：

```
endingFc  = calcCashBalance(opening, increase, decrease)   // 镜像本位币，而非由 fc 全 0 算出 0
auditedFc = endingFc + adjustmentFc
```

不这么做的话，界面会出现「本位币期末 327,095.20 / 原币期末 0」的自相矛盾，审计师无法判断哪个可信。`endingFc`/`auditedFc` 不在 `USER_FIELDS`，是派生列，不落库，所以镜像不产生数据污染。

### B 组：豁免表 schema

```
exemptions[].script         必填，仓库相对路径
exemptions[].spec           必填，`.kiro/specs/` 下的目录名（失效检测靠它）
exemptions[].reason         必填，≥10 字
exemptions[].registered_at  必填，YYYY-MM-DD
exemptions[].revoke_when    必填，撤销条件的自然语言描述
```

---

## Error Handling

| 场景 | 处理 | 理由 |
|---|---|---|
| 形态判定遇到 `fxCurrency` 为空串 | 按本位币处理（`isBaseCurrency('')` 已如此） | 与既有单一真源一致，不新增分支 |
| 形态 A 但本位币列也全 0 | 仍走形态 A（结果全 0，与现状同） | 空账户是合法数据，不需要特殊分支 |
| 形态 B 且审计师后来填了 fc 列 | 自动转为形态 C（判定是每次 recalc 时算的） | 形态不落库，故无需迁移 |
| 共享件里锚点命中数 ≠ 1 | 报 ANCHOR-MISS 并**中止该条变异**，不改文件 | 脚本缺陷不能伪装成代码缺陷 |
| 共享件还原后 md5 与变异前不符 | 抛异常并显式打印两个 md5 | 「写回成功」不等于「内容相同」 |
| 豁免表 JSON 解析失败 | 守卫**失败**（不静默跳过） | fail-closed：解析不了就等于没有豁免 |
| 迁移后判定与迁移前不一致 | 视为迁移失败，回退该脚本 | R7.3 的行为等价是硬要求 |

**不用 `except Exception` 兜住取值层**：memory 记录的 fail-open 是最贵的一类缺陷（把「函数名拼错」吞成「本项目无此数据」）。共享件里任何异常都要么带明确的态（ANCHOR-MISS）要么向上抛。

---

## Testing Strategy

### A 组

1. **形态判定纯函数**（`classifyFxForm`）：三形态各若干例 + PBT（`fast-check`，已在仓库）验「fc 列任一非 0 ⇒ 恒为形态 C」。
2. **`recalcRow` 行为**：三形态 × 两 variant 的输出断言。零回归支点 = `rmb` 分支输出与修复前逐字相同。
3. **跨层端到端**（R4.1）：`variantA × variantB` 四组合 × 三来源（账户级/叶子/手工），断言金额守恒。这一层是本 spec 的核心新增 —— 它是唯一能反证「写入侧与消费侧口径一致」的层级。
4. **落库形态**（R3.3）：断言 `serializeRows` 输出的 JSON 里本位币列非 0，而不是只看内存 `rows`。
5. **跨 sheet 聚合**（R3.2）：断言 variant 切换前后四个聚合键值相同。
6. **历史数据兼容**（R2.6）：用不含 `fxRate` 字段的行 JSON 作输入，断言行为与修复前一致。

### B 组

1. **共享件能力**：每项能力一条行为测试，判据是「故意破坏后必失败」而非「函数可调用」。
2. **迁移等价性**（R7.3）：对每个迁移的脚本，迁移前跑一遍全量变异存下判定矩阵（变异 id → 四态 + 打红测试名集合），迁移后再跑一遍逐一比对。**这一步必须真跑**，不能只比代码结构。
3. **采纳守卫的变异**：新增一个不带分母的临时脚本 ⇒ `test_mutation_kit_adoption.py` 必红；把某脚本从豁免表移除 ⇒ 必红；把某在办 spec 标成已归档 ⇒ 失效检测必红。
4. **本 spec 自己的变异脚本**：用共享件写（自举），至少覆盖 A 组的每条新守卫。

### 变异检验四态（沿用 e-cycle 的定义，写进共享件）

- `RED` 新增失败集合非空且**包含**声明的 `want` ⇒ 守卫有效
- `WRONG-TEST` 新增失败集合非空但不含 `want` ⇒ 污染残留或锚点落错位置
- `GREEN` 新增失败集合为空 ⇒ **守卫缺陷**
- `ANCHOR-MISS` 锚点命中数 ≠ 1 或行号消歧后逐字不符 ⇒ **脚本缺陷**

退出码不作判据（pytest 收集错误、vitest 噪声 warning 都会让退出码非零）。

### 不做的事

- 不跑全量 `backend/tests`（1522 个测试文件，前台无中间输出会被误判卡死）⇒ 按引用关系反查辐射面。
- 不重跑在办 spec 的变异脚本（会改并发会话正在编辑的文件）。
- 不在本 spec 顺手修迁移中发现的他 spec 判据缺陷（R7.6），只登记。

---

## Correctness Properties

### Property 1: 形态 A 下本位币六列保留输入值

`classifyFxForm(row) === 'base-identity'` 时，`recalcRow(row,'multi')` 返回的 `opening`/`increase`/`decrease`/`adjustment` 与输入逐字相等，`ending`/`audited` 按本位币链式算出（`calcCashBalance(opening,increase,decrease)`）。

**Validates: Requirements 1.1, 1.2**

### Property 2: 形态 B 下不臆造汇率、本位币列保持 0

`fxCurrency` 非本位币且 fc 列全 0 时，`recalcRow(row,'multi')` 的本位币六列为 0、`fxRate` 保持 0，且该行 `note` 含 `FOREIGN_FC_HINT`（单一真源，不新造文案）。

**Validates: Requirements 1.5, 2.4**

### Property 3: 形态 C 行为与修复前逐字相同

fc 列任一非 0 时，`recalcRow(row,'multi')` 的输出与修复前实现逐字相同（零回归支点）。

**Validates: Requirements 1.6**

### Property 4: rmb 分支输出与修复前逐字相同

`recalcRow(row,'rmb')` 对任意输入的输出与修复前实现逐字相同 —— 本次改动只碰 `multi` 分支与加载归一。

**Validates: Requirements 1.6**

### Property 5: 三个来源的行在两 variant 下金额守恒

账户级种子（`rmb`/`multi` 两版）· 叶子口径种子 · 手工录入行，三类行经 `variantA` 写入、`variantB` 消费后，本位币金额与写入时相等（外币待录入行除外，见 Property 2）。`variantA × variantB` 四组合全覆盖。

**Validates: Requirements 1.3, 4.1, 4.2**

### Property 6: 叶子口径兜底路径在 multi 版下不再恒零

`buildBankSeedRows(p)` 产出的行（`fxCurrency:'人民币'`、`fxRate:1`、fc 全 0、本位币列有值）在 `multi` 版下本位币金额非 0。这是改造前就存在的存量缺陷，与 variant 切换无关。

**Validates: Requirements 1.3**

### Property 7: 种子侧 variant 分流不变

`buildBankSeedRowsFromAccounts(p,'rmb')` 仍不下发 `fxCurrency` 与任何原币列；两 variant 产出的账户条数仍相等、字段集仍不同。

**Validates: Requirements 1.4**

### Property 8: fxRate 三态在加载后可区分

`loadFromResponses` 对 `fxRate` 的处理满足：缺失（`null`/`undefined`/`''`）→ `1`；显式 `0` → `0`；其他 → `parseNum` 原值。三态互不混淆。

**Validates: Requirements 2.1, 2.2**

### Property 9: 缺失回落值与本位币恒等语义一致

`fxRate` 缺失时回落 `1`，且该选择的理由写在代码注释里（「缺失 = 该行只有本位币列 = 原币与本位币恒等」），而非「历史如此」。

**Validates: Requirements 2.3**

### Property 10: 历史落库数据行为不变

库中既有的 `E1-bank-detail-rows` 行若不含 `fxRate` 字段，加载后的 `rows` 与修复前实现的输出在**本位币列**上相同（形态 A 下本位币列现在更正确，故断言为「不比修复前更差且非 0」）。

**Validates: Requirements 2.6**

### Property 11: 落库的本位币列不是派生失败的 0

`serializeRows(rows, USER_FIELDS)` 输出的 JSON 里，每行的 `opening`/`increase`/`decrease`/`adjustment` 等于该行**写入时**的值。判据落在序列化输出上，不是内存 `rows`。

**Validates: Requirements 3.1, 3.3, 3.4**

### Property 12: 跨 sheet 聚合键在 variant 切换前后一致

`syncCrossSheetTotals()` 产出的四个键（`E1-bank-detail-{principal,institution,finance,other}-{opening,total}-unaudited`）在 variant 切换前后取值相同。

**Validates: Requirements 3.2, 3.5**

### Property 13: 形态 A 下原币小计列镜像本位币

形态 A 时 `endingFc === calcCashBalance(opening,increase,decrease)`、`auditedFc === endingFc + adjustmentFc`，不出现「本位币有值而原币为 0」的自相矛盾展示。

**Validates: Requirements 1.2**

### Property 14: 新守卫在修复前先打红

跨层端到端守卫（Property 5 的载体）在修复前的实现下必须失败；每条新守卫配一条变异且变异结果为 RED，变异声明写明「为什么这条变异不是无效变异」。

**Validates: Requirements 4.3, 4.4**

### Property 15: 守卫注释写明断言半径

新增守卫文件的头部注释说明它跨了哪几层（种子 → 序列化 → 加载 → 重算）以及为什么单层守卫不够（引用本缺陷穿过 29 条变异 + 568 例守卫的事实）。

**Validates: Requirements 4.5**

### Property 16: 所有变异脚本被 git 跟踪或显式豁免

`backend/scripts/{check,diagnose}/mutate*.py` 的每个文件要么被 git 跟踪，要么在豁免表内且带完整字段。

**Validates: Requirements 5.1, 5.5, 5.6**

### Property 17: 入库的脚本可运行

入库的每个脚本的只读子命令（`--list` 或等价）退出码为 0 且输出非空 —— 不入库坏脚本充数。

**Validates: Requirements 5.3**

### Property 18: 在办 spec 的脚本未被本 spec 触碰

`mutate_k_cycle_guards.py` / `mutate_i_cycle_guards.py` / `mutate_ie_lifecycle_guards.py` 三个文件在本 spec 的全部提交中零改动，且未被本 spec `git add`。

**Validates: Requirements 5.4, 7.5**

### Property 19: 归属未明的脚本有结论

`mutate_wp_export_resolver_guards.py` 的所属 spec 有明确结论（入库或删除），写进 tasks 实录，不留 `??`。

**Validates: Requirements 5.2**

### Property 20: 共享件覆盖七项能力

共享件提供：`Mutation` 数据类 · 锚点定位（唯一性断言） · 备份/应用/还原（`finally` + md5 逐字核验） · pytest/vitest 执行 · 四态判定 · 覆盖面分母 tally · 静态锚点自检子命令。每项由行为测试证明（故意破坏必失败）。

**Validates: Requirements 6.1, 6.5**

### Property 21: 覆盖面分母是必填参数

`run_cli` 的 `guard_files` 是必填关键字参数 —— 调用方不声明守卫文件全集时**无法调用成功**，而不是靠约定。报告末尾打印未被任何变异打红的文件清单。

**Validates: Requirements 6.2**

### Property 22: 冻结基线不符时显式告警

`baseline_backend_passed` / `baseline_frontend_passed` 与实测不符时打印 WARN（含实测值与基线值），且共享件注释要求改基线必须说明来源。

**Validates: Requirements 6.3**

### Property 23: 静态锚点自检只读

`--check-anchors` 执行后：目标文件 md5 全部不变、无 `.bak`/`.mutbak` 残留、无新增文件。

**Validates: Requirements 6.4**

### Property 24: `--list` 同时校验而非只打印

`--list` 校验每条变异的「锚点命中恰好 1 次 + 替换文本与锚点不同 + `want` 可定位到真实测试」，任一不满足即非零退出。

**Validates: Requirements 6.7**

### Property 25: 共享件零新增第三方依赖

共享件的 import 全部来自 Python 标准库或仓库已有依赖，`backend/requirements.txt` 零改动。

**Validates: Requirements 6.6**

### Property 26: 迁移是行为等价的

对每个迁移的脚本，迁移前后对同一变异集的判定矩阵（变异 id → 四态 + 打红测试名集合）逐一相同，等价性由真实执行的两份矩阵比对证明。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 27: 迁移后能力齐全

迁移后的每个脚本都具备 Property 20 的七项能力 —— 不出现「迁了但仍没有分母」。

**Validates: Requirements 7.4**

### Property 28: 迁移中发现的他 spec 缺陷只登记不改

迁移过程中发现的既有判据缺陷（无效变异、锚点漂移等）如实登记在 tasks 实录，且本 spec 的提交对应文件零功能改动（除非不改无法完成迁移，此时须在 tasks 写明理由）。

**Validates: Requirements 7.6**

### Property 29: 采纳守卫对退化打红

新增一个不使用共享件的变异脚本时，采纳守卫必须失败；把某脚本从豁免表移除时同样失败。

**Validates: Requirements 8.1, 8.2**

### Property 30: 豁免失效可检测

豁免项引用的 spec 目录已不在 `.kiro/specs/` 下（= 已归档）时，守卫提示该豁免应当撤销。

**Validates: Requirements 8.5**

### Property 31: CI 引用在干净 checkout 可解析

挂进 `governance-checks.yml` 的每个文件路径在干净 checkout 下都存在且被 git 跟踪（沿用本轮复盘的「exists + tracked」判据形态）。

**Validates: Requirements 8.3**

### Property 32: yml 改动用归因型验收

对 `governance-checks.yml` 的验收判据是「变动是否落在本 spec 的字节区间内」，不是「其他 job 一个都没变」—— 并发会话同时改该文件是常态，全局等值型判据必假红。

**Validates: Requirements 8.4**

---

## Notes

### 立项时已被实证的事实（勿再重新论证）

- `calcFxConvert(fc, rate) = fc * rate`（`useE1FormulaEngine.ts` L126~L128），纯乘法 ⇒ `fc=0` 或 `rate=0` 都归零。
- `parseNum(undefined) = 0`（L28~L33），无兜底。
- `serializeRows(rows, userFields)`（L194~L203）只保留 `userFields` 指定字段 ⇒ 落库形态由 `USER_FIELDS` 决定。
- `USER_FIELDS`（`useE1BankDetail.ts` L92~L98）**同时含**本位币四列与原币五列 ⇒ 被抹零的 `opening` 会落库。
- `buildBankSeedRows` 的 `mk()` 无条件给 `fxRate:1` + fc 全 0 ⇒ 叶子口径兜底路径在 `multi` 版恒零（Property 6）。
- 既有守卫 `e1BankAccountPrefill.spec.ts` 的「multi 版必须下发原币列，否则 recalcRow 会把本位币金额抹成 0」**措辞已准确描述本缺陷机制**，但断言半径只到纯函数输出。

### 立项时被推翻的两个初始判断

| 初始判断 | 实证结果 | 处置 |
|---|---|---|
| 归档 spec 建议的「种子键按 variant 分离」是修复方向 | 会割裂两版数据（同一批账户两套录入）、破坏历史持久化键、需改 E1-1 跨 sheet 取数，且**修不了叶子口径兜底恒零** | 否决，改修消费侧 |
| 缺陷只影响「切 variant」这一操作序 | 叶子口径兜底路径下 `multi` 版**恒零，无需切 variant**；手工录入行同样被抹零 | 影响面扩大，写进 R1.3 / Property 6 |

### 严重度依据（为什么优先做 A 组）

| 维度 | 事实 |
|---|---|
| 触发难度 | 低。「先点`仅人民币`再点`人民币及外币`」是按目录顺序的自然操作；aux 无账户数据的项目连切都不用切 |
| 可见性 | 差。表格显示 `-`（`fmtAmount(0)` 的平台默认），像「没录数据」而不像「算错了」 |
| 可逆性 | **不可逆**。切 variant 后动任一格，2 秒后 0 落库覆盖原值 |
| 扩散 | E1-1 审定表的 TB 核对基准同步归零，出现「审定合计 0.00 ≠ TB 4467536.12」的错误差异结论 |

### 与并发会话的边界

- **不动** `mutate_k_cycle_guards.py`（k-cycle 在办，调查时 mtime 距当时 5 分钟内）· `mutate_i_cycle_guards.py`（i-cycle 在办，`A ` staged）· `mutate_ie_lifecycle_guards.py`（wp-import-export 在办）。
- 改 `governance-checks.yml` 用 `fs_append` 或精确 `str_replace`，验收用归因型判据（Property 32）。
- `useE1BankDetail.ts` 与 `e1BankAccountPrefill.ts` 当前工作树状态需在开工时复查 —— 若并发会话正在编辑，先协调再动。

### 明确不做

- 不改 `buildBankSeedRowsFromAccounts` 的 variant 分流（Property 7）。
- 不在持久化层加「落库前查是否变 0」的防御（会掩盖真因，且分不清合法 0）。
- 不落库 `fxForm` 字段（会产生第二真源）。
- 不迁在办 spec 的 3 个脚本（Property 18）。
- 不顺手修迁移中发现的他 spec 判据缺陷（Property 28）。
- 不重跑归档 spec 的全量变异去「再证明一次」—— 复盘轮已用 `--check-anchors` 证明 29/29 锚点未漂移。
