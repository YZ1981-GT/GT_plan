# Design — 守卫判据归因化改造

## Overview

把平台上 20+ 处「某集合总数必须等于硬编码基线」的守卫断言，改造成在多 spec 并发下
不会假红的形态。本 spec 不新增功能、不改业务代码，只改**判据形态**与**登记表语义**。

改造的收益是可量化的：一次真源变更（2026-08-12 K 循环补共享表段首码）当前造成
**3 个 blocking CI job 挂、7 条断言红、6 条仍然有效的归因断言被连坐**，
且归因成本落在与该变更无关的人身上（本次实测约 15 分钟才定位到真凶）。

判据形态分级（requirements 已定义，此处给出可执行的识别与替换规则）：

| 级别 | 形态 | 识别正则 | 处置 |
|---|---|---|---|
| A | 违规清单为空 | `expect(<var>).toEqual([])` | 目标态，保留 |
| B | 地板 / 天花板 | `toBeGreaterThanOrEqual` / `toBeLessThanOrEqual` | 可用，须命名常量 + 注释记实测值 |
| C | 包含式重点项 | `toContain` / `assert x in inventory` | 可用 |
| D | 全局等值 | `expect(<集合>.length).toBe(<数字>)` | **禁用**，按配方替换 |
| E | 跨文件抠数字再等值 | 同 `it` 内既读别的守卫源码又 `toBe(<数字>)` | **禁用**，改语义存在性 |

## Architecture

### 真源与副本拓扑（实证）

```
note_template_listed.json  ┐
note_template_soe.json     ┴─→ gen_note_shared_table_segments.py --write
                                  │  EXPECTED_COUNTS = {listed:24, soe:8}   ← 副本 ①（已同步）
                                  ↓
                    backend/data/note_shared_table_segments.json            ← 真源
                                  │
                     ┌────────────┴────────────┐
                     ↓                         ↓
  backend/tests/test_note_shared_        frontend .../__tests__/
  table_segments.py                      disclosureSharedTableRowScope.spec.ts
  assert len(listed) == 24  ← 副本 ②     expect(counts).toEqual({23, 6})  ← 副本 ③
  assert len(soe)   == 8      （已同步）  expect(tables.length).toBe(29)     （未同步 = 全红）
  payload["counts"] == {24, 8}
  len(payload["tables"]) == 32
```

同一个数字 **3 处副本**。改动方同步了 ① ②（都在后端视野内），③ 在另两个 spec 的前端
产物里，改动方的 CI 视野里没有它。

改造后的目标拓扑：副本 ③ **不再存在**，前端只做结构自洽校验（不变式）与
地板/包含式断言，「生成器与真源是否漂移」这一职责单独留在后端（副本 ② 侧的 `--check`，
它正是本次唯一没红的一侧，说明该机制有效）。

### 三个守卫的判据代际

| 守卫 | 代际 | 形态构成 |
|---|---|---|
| `disclosureSharedTableRowScope` | 最旧 | 7 条形态 D（全红）+ 若干形态 A |
| `disclosureAutoSyncCoverage` | 混合 | 主体形态 A + 1 条形态 D（纯提醒锚点）+ 被形态 E 外部锁死 |
| `disclosureColumnsCoverage` | 最新 | 形态 B（地板/天花板）+ 形态 A（归因清单）+ 局部等值（按 builder 归因） |

`disclosureColumnsCoverage` 是**现成范本**：`BUILDER_FLOOR = 12` / `TABLE_FLOOR = 60`
注释明写「当前实测 22 个披露 builder / 92 张表，设为 12/60 留出循环下线余量」
—— 留余量 + 注释记实测值，正是形态 B 的正确写法。

## Components and Interfaces

### 受影响文件

| 文件 | 所属 spec | 改动性质 |
|---|---|---|
| `.../__tests__/disclosureSharedTableRowScope.spec.ts` | disclosure-note-row-level-merge | 7 处判据替换 + 拆 `it` |
| `.../__tests__/disclosureAutoSyncCoverage.spec.ts` | disclosure-sync-path-buildout | 登记表拆分 + 1 处形态 D 改天花板 |
| `.../__tests__/disclosureColumnsCoverage.spec.ts` | n-cycle-tax-disclosure-alignment | 天花板注释 + 失败消息分类 |
| `.../composables/__tests__/l2l4DisclosureWiring.spec.ts` | l-cycle-…-completion | 形态 E 改语义存在性（**跨 spec 改动**） |
| `backend/scripts/check/audit_guard_assertion_grades.py` | 本 spec（新建） | 全库普查脚本 |
| `backend/data/guard_assertion_grades.json` | 本 spec（新建） | 普查产物 |
| `backend/scripts/check/mutate_guard_attribution.py` | 本 spec（新建） | 变异检验脚本 |
| `.kiro/steering/conventions.md` | 平台 | 补形态分级口径 |

⇒ 4 个被改文件里 **3 个属于别的 spec**。这是本 spec 的固有属性（判据缺陷天然跨 spec），
故 Task 4 明确要求提交说明点出跨 spec 改动与原因。

### 形态 D → B+C 替换配方

| 原断言（形态 D） | 替换（形态 B/C） |
|---|---|
| `counts).toEqual({listed:23, soe:6})` | 结构不变式：两键存在、值为正整数、`counts.listed + counts.soe === tables.length` |
| `tables.length).toBe(29)` | 地板 `>= 20`（实测 32，注释记值） |
| `narrowed.length).toBe(15)` | 地板 `>= 10`（实测 18）+ 原 6 条归因断言拆到独立 `it` |
| `SCANNABLE.length).toBe(15)` | 地板 `>= 10`（实测 26）+ 包含式 `toContain('外币货币性项目')` |
| `leaky.length).toBe(4)` | 天花板 `<= 4`（脏名只许减少，实测已降到 2） |
| `leaky.some(含 <br/>)).toBe(true)` | **删除**（真源已无此类名，锁死正在消失的脏数据无意义） |
| 脏名登记表每条必须仍在清单 | 反转为形态 A：「条目若已不在清单则报请移出」并列出条目 |

`counts.listed + counts.soe === tables.length` 这条**替代两个硬编码且判据更强**
—— 校验的是真源结构不变式（清单与计数自洽），任何 spec 改真源都不打红它，
但生成器出 bug 会。

### 等值污染归因的具体位置

`disclosureSharedTableRowScope.spec.ts` L155-171 单个 `it` 内：

```ts
expect(narrowed.length, `受影响段数变了：${narrowed.join(' / ')}`).toBe(15)   // ← 形态 D，先炸
expect(narrowed.some((x) => x.includes('八、93'))).toBe(true)                 // ↓ 以下 6 条
expect(narrowed.some((x) => x.includes('外币货币性项目'))).toBe(false)        //   仍然成立
for (const key of ['五、32', '五、71', '八、91', '八、81']) {                 //   却拿不到反馈
  expect(narrowed.some((x) => x.includes(key)), `${key} 应在清单里`).toBe(true)
}
```

后 6 条经真源静态复算**全部仍然成立**（18 条窄段确实含 `八、93`、不含 `外币货币性项目`、
含四个指定章节）。同段还有形态 3.2 问题：`for` 循环内逐个 `expect`，首个失败即中止。

### 外部锚定

`l2l4DisclosureWiring.spec.ts` L842-849：

```ts
const m = /expect\(MISSING_SYNC_PATH\.length\)\.toBe\((\d+)\)/.exec(COVERAGE_RAW)
expect(m, '[类 A] …它是「收敛时别忘了改它」的提醒锚点…').not.toBeNull()
expect(Number(m![1])).toBe(6)
```

数字 6 被两个 spec 拥有的两个文件锁死。改造为语义存在性：

```ts
expect(COVERAGE_RAW).toMatch(/PERMANENT_EXEMPT[\s\S]{0,4000}L2TabDisclosureListed\.vue/)
expect(COVERAGE_RAW).toMatch(/SYNC_PATH_GAP[\s\S]{0,2000}L4TabDisclosureListed\.vue/)
```

⇒ L4 被补齐时改动方从 `SYNC_PATH_GAP` 移出条目 → 第二条断言红，**这是正确的红**
（L 循环守卫应当感知自己关注的缺口被填），而不再因为「别人把 6 改成 4」而红。

## Data Models

### 登记表拆分

```
MISSING_SYNC_PATH (6)
   ├─→ PERMANENT_EXEMPT (4)   H5 listed / L2 ×2 / N4 soe
   │     语义：源模板 / 附注模板依据决定「不该有链路」
   │     判据：每条 ≥40 字依据 + 文件存在 + 天花板「只许缩」
   └─→ SYNC_PATH_GAP (2)      L4 ×2
         语义：真实缺口，待重建
         判据：地板 0（可清零）+ 天花板「只许缩」+ 补齐后必须移出
```

语义混装的实证：

| 条目 | 语义 | 依据 |
|---|---|---|
| `H5TabDisclosureListed.vue` | 永久豁免 | variant_matrix 两个 listed 键均 null / listed 模板 204 章节含「油气」0 个 / `H5_NOTE_SECTION` 只有 soe 键 |
| `L2TabDisclosure{Listed,Soe}.vue` | 永久豁免 | 附注模板无「应付利息」独立章节；披露归 K3 §五、42/§八、42，`buildK3SyncPayload` 已实装，L2 再推会同表名互覆盖 |
| `N4TabDisclosureSoe.vue` | 永久豁免 | 源模板 `附注披露信息（国企）` 内容为「附注披露信息：无」；`shui_jin_ji_fu_jia.soe_*` 为 null |
| `L4TabDisclosure{Listed,Soe}.vue` | **真实缺口** | 需按 G6 范式结构对齐重建（两级表头 9 列 + 定性段） |

拆开后「真实缺口应为 0」才成为可断言、可收敛的目标。

`hasAnySyncPath` 的扫描结果与两个常量的关系仍用形态 A：
`unexpected = actual − (PERMANENT_EXEMPT ∪ SYNC_PATH_GAP)` 必须为 `[]`。

### 普查产物 schema

`backend/data/guard_assertion_grades.json`：

```jsonc
{
  "items": [
    {
      "file": "audit-platform/frontend/src/.../disclosureSharedTableRowScope.spec.ts",
      "line": 126,
      "assertion": "expect(manifest.counts).toEqual({ listed: 23, soe: 6 })",
      "current_value": "{listed:23,soe:6}",
      "grade": "D",
      "verdict": "must_fix",
      "reason": "真源 note_shared_table_segments.json 由 note_template_*.json 生成，被 K/L/E 多个 active spec 触及"
    }
  ]
}
```

`verdict` 取 `must_fix` | `keep`；`keep` 的 `reason` 必须写明作用域为何安全。

## Correctness Properties

### Property 1: 真源规模无等值断言

`disclosureSharedTableRowScope.spec.ts` 内不得出现对真源规模的等值断言。
判据：源码经 `stripComments()` 后不得匹配
`/expect\((?:manifest\.counts|manifest\.tables\.length|SCANNABLE\.length|narrowed\.length|leaky\.length)[^)]*\)\.(?:toBe|toEqual)\(/`。

**Validates: Requirements 1.1, 2.1**

### Property 2: 真源结构不变式

真源结构不变式成立：`counts.listed + counts.soe === tables.length`，且两键均为正整数。
该断言不含任何硬编码规模值。

**Validates: Requirements 2.1**

### Property 3: 地板天花板须命名常量

所有地板/天花板常量以命名常量声明（不得内联字面量），且注释含「当前实测 N」字样，
使余量可复核。

**Validates: Requirements 2.2, 5.1**

### Property 4: 脏名登记表判据方向反转

`GENERIC_TABLE_NAMES` 的判据方向为「登记条目若已不在真源清单则报请移出」（形态 A）；
不得断言「每条必须仍在清单」。

**Validates: Requirements 1.3**

### Property 5: 归因断言独立于规模断言

原 L155-171 的 6 条归因断言全部保留，且位于**独立的 `it`** 中，与任何规模型断言不同 `it`。

**Validates: Requirements 3.1**

### Property 6: 禁循环内逐个 expect

归因型断言不得在 `for` 循环内逐个 `expect`；必须收集违规清单后单次 `toEqual([])`。
判据：源码内 `for` 块体中不得出现 `expect(`（`it.each` 不受限）。

**Validates: Requirements 3.2**

### Property 7: 失败消息可归因

每条改造后断言的失败消息含至少一个具名对象（表名/文件名/章节号）与真源路径或生成器命令。

**Validates: Requirements 3.3**

### Property 8: 登记表拆分不丢不增

`MISSING_SYNC_PATH` 已拆为 `PERMANENT_EXEMPT` 与 `SYNC_PATH_GAP`，
两者条目集合之并等于拆分前的集合（不丢不增）。

**Validates: Requirements 4.3**

### Property 9: 永久豁免依据保留

每条 `PERMANENT_EXEMPT` 保留原依据说明且长度 ≥40 字符；
H5/L2/N4 三组依据的关键字（`variant_matrix`、`buildK3SyncPayload`、`附注披露信息：无`）
仍在源码中可检索。

**Validates: Requirements 4.4**

### Property 10: 缺口数只许天花板

`disclosureAutoSyncCoverage.spec.ts` 内不得出现 `expect(PERMANENT_EXEMPT.length).toBe(`
或 `expect(SYNC_PATH_GAP.length).toBe(` 形态；只许天花板。

**Validates: Requirements 4.2**

### Property 11: 禁跨文件抠数字

`l2l4DisclosureWiring.spec.ts` 不得用正则从别的守卫源码里抠数字再等值断言。
判据：同一 `it` 内含 `COVERAGE_RAW` 时不得出现 `/\)\.toBe\(\d+\)/`。

**Validates: Requirements 4.1**

### Property 12: allowlist 漂移消息分类

`INFERENCE_FALLBACK_ALLOWLIST` 的「实扫集合 === 声明集合」断言失败消息
区分「新增 None 态表」与「已修好未删条目」两类并分别给出明细。

**Validates: Requirements 5.3**

### Property 13: 天花板只许缩语义

天花板断言在「实际条目数 < 天花板」时不报红（只许缩语义成立）。
以替身 fixture 验证：条目数为天花板 − 1 时通过。

**Validates: Requirements 5.2**

### Property 14: 普查产物机器可读

普查产物为机器可读 JSON，含 `file` / `line` / `assertion` / `current_value` / `grade` /
`verdict` / `reason` 字段，且每条 `keep` 的 `reason` 非空。

**Validates: Requirements 6.1, 6.3, 6.4**

### Property 15: keep 判定的真源隔离

判为 `keep` 的断言，其真源不被本 spec 之外的其它 active spec 触及；
判据脚本列出真源路径并与 `.kiro/specs/*/` 下 active spec 的改动面比对。

**Validates: Requirements 6.2**

### Property 16: 变异检验四态

每个被改造的判据都有对应变异检验记录（脚本 `--only <锚点>` 可复现），
四态判定为 RED 且命中预期测试名。

**Validates: Requirements 7.1, 7.2**

### Property 17: 扫描面非空自检

每个归因清单型断言配有「扫描面非空」地板断言。
判据：含 `toEqual([])` 的 `it` 内或同 `describe` 内存在 `toBeGreaterThan` 系断言。

**Validates: Requirements 7.3**

### Property 18: 反向自检失效风险登记

绑定具体真实文件的反向自检处，注释登记「该文件被改/删则自检失效」的风险。

**Validates: Requirements 7.4**

### Property 19: 口径写入 steering

`conventions.md` 含守卫判据形态 A/B/C/D/E 分级口径与「D/E 禁用」的明确表述。

**Validates: Requirements 8.5**

### Property 20: 前端不重复承担生成器职责

前端守卫不重复承担「生成器与真源是否漂移」职责（该判据已由后端
`test_note_shared_table_segments.py` 的 `gen.main() == 0` 承担且工作正常）。
判据：前端 spec 源码不得出现 `gen_note_shared_table_segments` 字样，
也不得自行重算 payload 与真源逐字比对。

**Validates: Requirements 2.3**

### Property 21: 规模常量注释含变更来源

每处保留的规模型常量注释含变更来源信息：或指向真源路径与重生成命令，
或写明「当前实测 N」。判据：常量声明前 5 行内匹配 `/实测|真源|note_shared_table_segments/`。

**Validates: Requirements 1.2**

## Error Handling

- **普查脚本遇到无法解析的测试文件**：记入 `skipped` 数组并计数，**不静默跳过**；
  若 `skipped` 占比 >5% 视为脚本缺陷（正则覆盖不足），必须修脚本而非放过
- **变异脚本改真源 JSON**：一律走临时副本 + 环境变量/`monkeypatch` 重定向路径，
  **绝不直接改** `backend/data/note_shared_table_segments.json`（并发会话可能正在读它）
- **变异后恢复失败**：脚本必须在 `finally` 里恢复，并在退出前二次校验文件 md5 与变异前一致；
  不一致则以非零码退出并打印待手工恢复的路径
- **跨 spec 文件改动冲突**：改 `l2l4DisclosureWiring.spec.ts` 前先 `git status` 确认它不是
  `M`（并发会话在改）；若是，先逐行 diff 归因，不覆盖他人在途改动
- **fail-open 禁令**：普查/变异脚本不得用裸 `except Exception` 吞异常后返回「无问题」；
  解析失败必须记 ERROR 态并影响退出码

## Testing Strategy

### 判据自身的验证层次

1. **静态形态校验**：新增 `guardAssertionForms.spec.ts`，用 design 的识别正则扫本 spec
   改过的 4 个守卫文件，确认形态 D/E 已清零（Property 1/6/10/11/20）
2. **替身 fixture 验证语义**：天花板「只许缩」（Property 13）、
   普查脚本识别力（形态 D 替身必被识别、A/B/C 替身必不被识别）
3. **变异检验**：6 个锚点，四态判定（Property 16）
4. **真源静态复算**：改造后的地板/包含式断言用 python 直读真源 JSON 复算一遍，
   确认与 vitest 结果一致（防「读法不同导致两侧结论不一致」）

### 验收执行方式

- 一律**串行**（`--no-file-parallelism`）：本仓 4-worker 并发下全量跑会产出大量
  资源竞争型 flaky（实测 1999 files 全量跑报 73 failed，单独复跑只剩 1 个真红）
- 干净 checkout 模拟：在临时 worktree 上跑 3 个 blocking job 的命令行，
  证明不依赖工作树里的未提交文件
- 后端侧回归确认：`backend/tests/test_note_shared_table_segments.py` 仍全绿
  （本 spec 不碰后端判据，它是对照组）
