# Requirements Document

## Introduction

两件在 `e-cycle-extraction-formula-and-disclosure-completion`（24/24，2026-08-15 归档）收口时**登记未修**的事，本 spec 承接：

- **A 组（业务缺陷）**：E1-3 银行存款明细在两个 variant（`仅人民币` / `人民币及外币`）之间切换时，**本位币金额被抹成 0 并可落库**。归档 spec 的 Task 22 已在真实浏览器确定性复现，但判定为「超出该任务范围」而只登记。
- **B 组（工程治理）**：把 `mutate_e_cycle_guards.py` 的**覆盖面分母**范式推广到平台其余变异脚本 —— 该范式在 21 条变异「全 RED」的情况下仍报出 7 个守卫文件从未被反证过，是 memory 假绿第①源在守卫层的对应防法。

两组同处一个 spec 的理由：A 组缺陷之所以能穿过 **29 条变异 + 568 例守卫**，正是因为没有一条断言把「写入侧的 variant」与「消费侧的 variant」串起来；B 组要推广的分母机制，就是用来把这类「守卫文件在、但从未被反证」的欠账显形的。A 组的新守卫必须用 B 组的范式写，两组互为验证。

---

## 实证基线（2026-08-15，只读零改动）

### A 组：抹零链路已定位到行级

四段代码共同构成缺陷，**每一段单独看都是合理的**：

```
① e1BankAccountPrefill.buildBankSeedRowsFromAccounts(p, 'rmb')   L281~L285
   rmb 版有意「不下发 fxCurrency 与任何原币列」（AC 1.9 的 variant 分流设计，
   守卫「两 variant 账户条数相同、字段集不同」已锁死 ⇒ 不能改这里）

② useE1BankDetail.loadFromResponses()                            L176~L179
   fxRate:   parseNum(r.fxRate) || 1     ← 缺失回落 1
   openingFc: parseNum(r.openingFc)      ← 缺失回落 0，无兜底
   increaseFc/decreaseFc 同上            ← 不对称就在这里

③ useE1BankDetail.recalcRow(row, 'multi')                        L105~L119
   opening = calcFxConvert(row.openingFc, row.fxRate)   ← 无条件由原币派生
   return { ...row, opening, increase, decrease, ending, adjustment, audited, ... }
                    ↑ 真实本位币金额被派生值覆盖

④ watch(variant, next => rows.value.map(row => recalcRow(row, next)))   L193
   variant 一变立即全表重算（设计意图正确）
```

代入：rmb 形态的行（有 `opening=2046.75`，无 `openingFc`）在 multi 版下 → `openingFc=0`、`fxRate=1` → `calcFxConvert(0,1)=0` → `opening` 被 0 覆盖。

### A 组：影响面比归档 spec 登记的更大（本轮新查）

归档 spec 只登记了「种子行」。实际上 `loadFromResponses` 与 `watch(variant)` 对**所有行**同等生效：

1. **审计师在 `仅人民币` 版手工录入的行同样被抹零** —— 手填 `opening/increase/decrease` 而不填原币列是该版的正常用法（该版界面本就不显示原币列）。
2. **落库形态确证为数据损坏**：`USER_FIELDS`（L92~L98）**同时包含** `opening/increase/decrease/adjustment` 与 `fxRate/openingFc/increaseFc/decreaseFc/adjustmentFc`。`serializeRows()` 按 `USER_FIELDS` 序列化 ⇒ 被抹成 0 的 `opening` 会写进库，**原始录入值不可从库恢复**。
3. **落库触发条件很低**：`updateCell` / `addRow` / `removeRow` / `onConfirmationReceived` 任一调用 → `scheduleSave()` → **2 秒后** `persistToResponses()` → `saveImmediate()`；`onBeforeUnmount` 亦会 flush 待保存定时器。即「切一次 variant 再改任一格」。
4. **污染同步扩散到 E1-1 审定表**：`watch(() => rows.value.map(row => [..., row.opening, row.ending]), () => syncCrossSheetTotals(), { deep: true, immediate: true })`（L248~L250）在 rows 归零后立即重算四个跨 sheet 聚合键并 `allResponses.value.set(...)`；`persistToResponses` 把它们一并写库（L262）。这就是实测看到的横幅「E1-1 审定合计 0.00 ≠ TB数 4467536.12，差异 -4467536.12」。

### A 组：`|| 1` 把 fxRate 的三态压成两态（本轮新查，独立于抹零）

账户级种子对**非本位币**账户下发 `fxRate: 0`，表达「四表无汇率数据、需手工录入」（Property 34 禁止由本位币反推，守卫 + 变异 M19 已锁死）。但 `parseNum(r.fxRate) || 1` 使 **`0` 与 `缺失` 都变成 `1`**：

| 写入侧意图 | 存储值 | 加载后 | 后果 |
|---|---|---|---|
| rmb 形态（无此字段） | `undefined` | `1` | 需要的正是 1（本位币恒等），巧合正确 |
| multi 非本位币「待录入」 | `0` | **`1`** | 「待录入」标记丢失，界面显示汇率 1 = 事实上的臆造 |
| multi 本位币恒等 | `1` | `1` | 正确 |

⇒ 任何「按 fxRate 是否为 0 判断该不该反填」的修复方案，若不先修这个归一，都会误伤非本位币账户。

### A 组：既有守卫为什么没拦住

`e1BankAccountPrefill.spec.ts` 有一条 `🔴 multi 版必须下发原币列，否则 recalcRow 会把本位币金额抹成 0` —— **措辞已准确描述了本缺陷的机制**，但它只断言「种子行带原币列」，断言半径停在纯函数输出。跨过 `loadFromResponses` → `recalcRow` → `watch(variant)` 的那一段无人断言。同 Property 28 那次一样属「注入点在、消费方在、两者口径不一致」。

### B 组：17 个变异脚本的形态与归属

```
backend/scripts/check/     9 个（procedure-trimming 系 8 个 + note-conversion 1 个）
backend/scripts/diagnose/  8 个（各业务循环）
合计 9657 行
```

**判据满足度（粗筛，按字符存在计，仅用于定缺口规模）**：

| 判据 | 满足 | 缺口 |
|---|---|---|
| 覆盖面分母（守卫文件全集 + 末尾 tally） | **3/17** | 14 |
| 静态锚点自检（只读子命令） | **1/17** | 16 |
| 冻结基线常量（passed 数） | **1/17** | 16 |
| WRONG-TEST 态 | 13/17 | 4 |
| 锚点唯一性断言 | 16/17 | 1（`i_cycle`） |
| md5 还原核验 | 16/17 | 1（`g7`） |
| RED / GREEN / ANCHOR-MISS | 17/17 | 0 |

仅 `mutate_e_cycle_guards.py` 11 项全满。

**重复度**：15 个强复制函数（`main` 17/17 · `md5`/`_md5` 各 8/17 · `restore_all` 8/17 · `apply_mutation` 7/17 · `_env` 5/17），`Mutation` dataclass **14/17**（e-cycle 叫 `Mut`），`hashlib.md5` 16/17、`finally` 还原 17/17、pytest 调用 13/17、vitest 调用 12/17。可共享函数占各脚本顶层函数的比例中位数约 **67%**、最高 81.8%。

**🔴 git 归属矩阵（决定哪些能动）**：

| 脚本 | 所属 spec | spec 状态 | git |
|---|---|---|---|
| `mutate_e_cycle_guards.py` | e-cycle | 已归档 | clean（**范式基准**） |
| `mutate_h_cycle_guards.py` | h-cycle | 已归档 | clean |
| `mutate_g7_column_alignment_guards.py` | g7 | 已归档 | clean |
| `mutate_trim_decision_guards.py` | procedure-trimming | 已归档 | clean |
| `mutate_note_conversion_section_mapping_guards.py` | note-conversion | 已归档 | clean |
| `mutate_note_text_hygiene_and_expandable.py` | note-template-columns | 已归档 | clean |
| `mutate_task13/14/18/19/20/21/23_*.py`（**7 个**） | procedure-trimming | **已归档** | **`??` 未入库** |
| `mutate_wp_export_resolver_guards.py` | 待定 | 待定 | **`??` 未入库** |
| `mutate_ie_lifecycle_guards.py` | workpaper-import-export | **在办 24/25** | clean |
| `mutate_i_cycle_guards.py` | i-cycle | **在办 23/24** | `A `（staged 未提交） |
| `mutate_k_cycle_guards.py` | k-cycle | **在办 19/25** | `??`（mtime 距本次调查 5 分钟内） |

`procedure-trimming-and-delegation-intelligence`(26/26) 于 2026-08-12 归档，归档 commit 只带了 `mutate_trim_decision_guards.py`，**漏掉同 spec 的 7 个变异脚本**。它们是已归档 spec 的正式产物，目前只存在于工作树。

---

## Requirements

### Requirement 1: variant 切换不得抹掉已录入的本位币金额

**User Story:** 作为审计师，我在「仅人民币」版 E1-3 录好银行存款明细后切到「人民币及外币」版查看，金额必须还在，否则我会以为账没录上、或更糟：没注意到金额变 0 就继续往下做，把 0 带进审定表和附注。

#### Acceptance Criteria

1.1 从 `rmb` 切到 `multi` 时，原本非 0 的 `opening`/`increase`/`decrease`/`ending`/`audited` **不得变 0**；从 `multi` 切回 `rmb` 亦然（双向）
1.2 判据必须落在**行为**上：给定一批只有本位币列的行，`recalcRow(row,'multi')` 的返回值里本位币六列与输入逐字相等（不是「不抛异常」，也不是「字段存在」）
1.3 该保护对**三类行同等生效**：账户级种子行（`buildBankSeedRowsFromAccounts(p,'rmb')` 产出）· 叶子口径种子行（`buildBankSeedRows(p)` 产出）· 审计师手工录入/新增行（`addRow` + `updateCell` 产出）
1.4 修复**不得改动种子侧的 variant 分流**：`buildBankSeedRowsFromAccounts` 的 `rmb` 版仍不下发 `fxCurrency` 与原币列（既有守卫「两 variant 账户条数相同、字段集不同」与 AC 1.9 的设计意图必须继续成立）
1.5 修复后 `multi` 版对**真正的外币账户**行为不变：非本位币且汇率未录入时本位币列仍为 0 且 `note` 带手工录入提示（Property 34 不得被本次修复破坏）
1.6 `rmb` 版的既有行为**零回归**：`rmb` 分支 `recalcRow` 的输出与修复前逐字相同

### Requirement 2: fxRate 的三态不得在加载时被压扁

**User Story:** 作为审计师，「汇率还没填」和「汇率就是 1」是两件事 —— 前者要提醒我去填，后者是人民币账户的事实。系统把两者显示成同一个 1，我就永远不知道哪些外币账户还缺汇率。

#### Acceptance Criteria

2.1 `loadFromResponses` 必须能区分三态：字段缺失（rmb 形态/历史数据）· 显式 `0`（multi 版「待录入」标记）· 真实值（含 1）
2.2 显式存储的 `fxRate: 0` 加载后**仍为 0**，不得回落成 1
2.3 字段缺失时的回落值必须与「本位币恒等」的语义一致，且该选择在代码注释里写明**为什么**（不是「历史如此」）
2.4 非本位币且 `fxRate` 为 0 的行，界面必须有可见提示（沿用既有 `FOREIGN_FC_HINT` 单一真源，不新造第二份文案）
2.5 三态判据必须有守卫，且守卫对「把 `|| 1` 改回去」这个变异必须打红
2.6 历史已落库数据的兼容性必须显式验证：库里既有 `E1-bank-detail-rows` 的行若无 `fxRate` 字段，加载后行为与修复前相同（不得因三态改造让历史数据显示变化）

### Requirement 3: 抹零不得落库，且不得污染跨 sheet 聚合

**User Story:** 作为审计师，显示错了我还能刷新页面救回来；写进库就救不回来了。系统不能把算错的 0 当成我的录入值保存。

#### Acceptance Criteria

3.1 `serializeRows()` 落库的 `opening`/`increase`/`decrease`/`adjustment` 必须是**审计师录入或取数产出的值**，不得是 variant 派生失败后的 0
3.2 `syncCrossSheetTotals()` 产出的四个跨 sheet 聚合键（`E1-bank-detail-{principal,institution,finance,other}-*`）在 variant 切换前后必须一致
3.3 判据必须覆盖**落库形态**而非仅内存态：断言 `serializeRows()` 的输出 JSON 里本位币列非 0
3.4 若某行确实无法在 `multi` 口径下算出本位币金额（真外币未录汇率），落库值必须与该行**写入时**的值一致，而不是被派生结果覆盖
3.5 E1-1 审定表读取的 TB 核对基准不得因 variant 切换而改变（用既有跨 sheet 聚合键作判据，不新建取数路径）

### Requirement 4: 守卫必须跨越「写入侧 variant」与「消费侧 variant」

**User Story:** 作为维护者，我要的不只是这个 bug 被修好，而是同类 bug 下次会被守卫拦住 —— 这次它穿过了 29 条变异和 568 例守卫。

#### Acceptance Criteria

4.1 必须新增至少一条**端到端**守卫：从 `buildBankSeedRowsFromAccounts(p, variantA)` 的输出出发，经 `allResponses` 序列化，到 `useE1BankDetail`（`variant = variantB`）的 `rows`，断言金额守恒。`variantA × variantB` 四种组合全覆盖
4.2 同类端到端守卫必须覆盖叶子口径种子（`buildBankSeedRows`）与手工录入行两条路径
4.3 守卫必须在**修复前**先打红（先写守卫、跑一次确认 RED、再改实现）
4.4 每条新守卫必须配一条变异，且变异检验结果为 RED；变异声明里要写明**为什么这条变异不是无效变异**（e-cycle 的 M3/M15 曾各踩过一次无效变异）
4.5 断言半径必须写进守卫文件的注释：说明它跨了哪几层、以及为什么单层守卫不够

### Requirement 5: 已归档 spec 的变异脚本必须入库

**User Story:** 作为维护者，已归档 spec 的守卫产物只存在于某台机器的工作树里，等于没有 —— 干净 checkout 下 CI 跑不了它，工作树一丢它就没了。

#### Acceptance Criteria

5.1 7 个 `mutate_task*.py`（属已归档的 `procedure-trimming-and-delegation-intelligence`）必须入库
5.2 `mutate_wp_export_resolver_guards.py` 必须先查清所属 spec 再决定入库或删除，结论写进 tasks 实录（不得因「不知道是谁的」而留在 `??`）
5.3 入库前必须逐个确认它们**当前可运行**（至少 `--list` 或等价只读子命令不报错），不得把坏掉的脚本入库充数
5.4 **不得动**在办 spec 的脚本（`mutate_k_cycle_guards.py` / `mutate_i_cycle_guards.py` / `mutate_ie_lifecycle_guards.py`）—— 包括不得代它们 `git add`
5.5 入库动作必须能被独立复核：给出 `git ls-files --error-unmatch` 对每个路径的验证结果
5.6 必须顺手补一条**通用**守卫，防止同类欠账再发生：扫 `backend/scripts/{check,diagnose}/mutate*.py`，任一未被 git 跟踪即失败（对在办 spec 的脚本给显式豁免登记表，豁免项必须带原因与登记日期）

### Requirement 6: 变异范式收敛为共享件

**User Story:** 作为维护者，17 个脚本 9657 行里有约三分之二是互相抄来的样板（备份、还原、md5 核验、跑 pytest/vitest、判四态），每次新写一个都要重抄一遍，抄漏哪一项就是一个假绿入口。

#### Acceptance Criteria

6.1 必须新建共享模块，至少收敛：`Mutation` 数据类 · 锚点定位（含唯一性断言） · 备份/应用/还原（含 `finally` + md5 逐字核验） · 测试执行（pytest / vitest） · 四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST） · 覆盖面分母 tally · 静态锚点自检子命令
6.2 共享件必须支持**覆盖面分母**：调用方声明本 spec 的守卫文件全集，报告末尾打印未被任何变异打红的文件清单
6.3 共享件必须支持**冻结基线**：passed 数常量 + 不符时的显式 WARN，且注释要求改基线时必须说明来源
6.4 共享件的**静态锚点自检**（`--check-anchors` 或等价）必须只读：不写生产代码、不留 `.bak`
6.5 共享件本身必须有守卫，且守卫必须能对「把唯一性断言删掉」「把 md5 核验删掉」「把分母 tally 删掉」三种变异各自打红
6.6 共享件必须零新增第三方依赖（只用 stdlib + 仓库已有）
6.7 共享件的 `--list` 不得只打印：必须同时校验「锚点命中恰好 1 次 + 替换文本与锚点不同 + 声明的 want 测试可定位」（g7 spec 沉淀的教训：只打印的 `--list` 在 CI 里恒绿）

### Requirement 7: 已归档 spec 的脚本迁到共享件，在办的只登记

**User Story:** 作为维护者，我要的是范式真的生效，不是多一个没人用的库；但我也不能去改并发会话正在写的文件。

#### Acceptance Criteria

7.1 6 个已入库且所属 spec 已归档的脚本（`e_cycle` / `h_cycle` / `g7` / `trim_decision` / `note_conversion` / `note_text_hygiene`）必须迁到共享件
7.2 Requirement 5 入库的脚本迁移与否由「迁移后能否复现原判定」决定；不迁的必须写明原因
7.3 迁移必须是**行为等价重构**：迁移前后对同一条变异的判定（四态 + 打红的测试名集合）逐一相同，且该等价性有可复核的证据
7.4 迁移后每个脚本都必须具备 Requirement 6 的七项能力（含覆盖面分母与静态锚点自检），不得「迁了但仍没有分母」
7.5 **在办 spec 的 3 个脚本不迁**，但必须登记进待迁清单（含所属 spec、当前进度、建议迁移时机），登记项要能被守卫识别为「已登记豁免」而非「漏了」
7.6 迁移过程中若发现某脚本的既有判定本身有缺陷（如无效变异、锚点已漂移），如实登记而**不在本 spec 顺手改**（除非不改就无法完成迁移，此时须在 tasks 写明）

### Requirement 8: 范式不得退化

**User Story:** 作为维护者，这次收敛完，下一个 spec 新写变异脚本时不能又抄一份不带分母的样板出来。

#### Acceptance Criteria

8.1 必须有守卫钉死：`backend/scripts/{check,diagnose}/mutate*.py` 里任一脚本若未使用共享件，即失败（豁免走显式登记表，带原因与日期）
8.2 该守卫必须对「新增一个不带分母的变异脚本」这个变异打红
8.3 共享件与守卫必须挂进 `governance-checks.yml`，且引用的每个文件在干净 checkout 下可解析（沿用本轮复盘用的「37/37 exists+tracked」判据形态）
8.4 挂 CI 时对 `governance-checks.yml` 的改动必须用**归因型**验收（变动落在本 spec 的字节区间内），不得用「其他 job 一个都没变」的全局等值型 —— 并发会话同时改该文件是常态
8.5 豁免登记表必须带**失效检测**：登记的在办 spec 一旦归档，守卫要提示该项豁免应当撤销
