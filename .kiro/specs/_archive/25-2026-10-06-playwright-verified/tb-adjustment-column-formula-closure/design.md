# 设计：试算平衡表调整列取数收口

## 一、问题的真实形状

用户的提问是"公式管理里为什么没有调整分录的带入"。表层答案是"数据库里没有这列公式"，
但追查后问题分三层，**层次不同、优先级不同、可独立交付**：

```
第 3 层  UI          公式管理只展示一列公式          ← 观感层，用户看到的
第 2 层  数据模型    report_config 每行仅 1 个 formula  ← 能力缺失
第 1 层  取数口径    调整汇总未收敛到 adj_net        ← 🔴 正在产生错误数字
```

🔴 **第 1 层与用户的提问无关，却是最严重的**。用户问的是"为什么看不到"，
追查过程中撞见的是"看到的数字是错的"。本 spec 把第 1 层排在最前，
因为它独立于另两层、修的是正确性、且交付后才有真实非零数据可验证第 2/3 层。

> ⏱ **实施期勘误（Phase 0 Task 0.7）**：第 1 层的缺陷数由 3 个增至 **4 个**。
> 原记 B1（无 `review_status` 过滤）/ B2（无 `origin` 过滤）/ B3（查主表遗留冗余列）；
> 验证 P1 时新发现 **B4 —— 审定数用未归一的 `dr − cr`，致贷方正常类（负债/权益/
> 收入）方向反掉**。B4 独立于 B1~B3：即便三者全修，审定数仍错。
> 详见 `evidence/phase0-property1-verdict.md`。

## 二、四个方案与裁决

### 方案 A — 只注册 `ADJ()` 进内核（最小）

在 `formula_engine._REGISTRY` 注册 `ADJ`，让报表域也能写 `ADJ('6001','aje_net')`。

- ✅ 改动最小，消除"两套词汇表"
- ❌ **不解决用户的问题**：`report_config` 仍只有一列 formula，公式管理仍只能展示一列
- ❌ 不修第 1 层的错误数字

**裁决：不单独采纳**，但作为需求 2 纳入（它是需求 4 的前置能力）。

### 方案 B — 复用 `TB(code,'AJE调整')`，不引入新函数

列别名 `AJE调整`/`RJE调整` 三份映射表**都已存在**（E3 实测），`report_engine._COLUMN_MAP`
已映射到 `aje_adjustment` 字段。理论上不加任何函数就能用。

- ✅ 零新增语法
- ❌ **取到的是 stale 持久化列**（E5 实测真库全 0），而不是实时 `adj_net` 值
- ❌ 与底稿域既有的 `ADJ('1521','aje_net')` 语法**分裂**（同一语义两种写法）
- ❌ 无法表达 `aje_net` / `rje_net` 之外的口径参数（origin / status）

**裁决：否决**。它把"取数"和"取哪个快照"混在一起——`TB()` 的语义是"取试算表某列"，
而调整数的权威源是 `adjustments` 表而非 `trial_balance` 的派生列。让 `TB()` 兼职会
永久锁死 stale 问题。

> ⚠️ 但**不删除**这两个列别名：`adjudication_writeback` 与底稿审定表在用（E2 实测），
> 且 `address_registry` 地址目录在册。它们的正当语义是"取试算表的**已持久化**调整列"，
> 与 `ADJ()` 的"实时汇总"并存且正交，文档里必须写清二者差异。

### 方案 C — `report_config` 加 4 个调整列公式字段

`aje_dr_formula` / `aje_cr_formula` / `rcl_dr_formula` / `rcl_cr_formula`。

- ✅ 与现有 4 列显示一一对应
- ❌ **4 个字段是错的粒度**。借贷方向不是公式该关心的——`adj_net` 返回的是**净额**，
  借贷拆分是展示层按符号决定的。加 4 列会迫使配置者写 4 条公式表达同一件事
- ❌ 字段数膨胀，且未来加"其他调整"列还要再加字段

**裁决：否决粒度，采纳方向**。

### 方案 D — `report_config` 加 2 个净额公式字段（采纳）

`aje_formula` / `rje_formula`，各存一条返回**净额**的公式（如 `ADJ('6001','aje_net')`）。
借贷拆分仍由展示层按符号决定（与现有 `audited = unadj + aje_dr - aje_cr + ...` 口径兼容：
净额为正进借方列、为负进贷方列）。

- ✅ 粒度与 `adj_net` 的返回语义一致（净额）
- ✅ 与底稿域既有 `ADJ(code,'aje_net')` / `ADJ(code,'rje_net')` 语法**完全一致**
- ✅ 只加 2 字段，未来扩展走同一模式
- ⚠️ 需确认"净额 → 借贷两列"的拆分规则与现有 `aje_dr - aje_cr` 口径**数值等价**
  （设计阶段无法凭空断言，列为 Property 1 必验项）

**裁决：采纳。**

## 三、L1 纯同步 × `adj_net` 异步 的架构冲突（技术核心）

这是本 spec 唯一有真实技术难度的地方。

**约束**（实测自 `formula_engine.execute` docstring，非本 spec 引入）：
> L1 内核纯函数：同 formula + 同 ctx → 同 FormulaResult（确定性，可单测可缓存）。
> **无 DB/async 耦合**：所有取数由 L2 编排层预载进 ctx。

而 `adj_net` 是 `async def`，需要 DB。**不能在 `_handle_adj` 里 await**。

### 既有三种 L2 模式（实测）

| 模式 | 代表 | 做法 |
|---|---|---|
| ctx 注入 | `adjudication_writeback` | 批量查库 → 构造 `tb_data` 六键 → `FormulaContext(tb_data=...)` |
| 预替换 | `report_engine.evaluate_formula` | 正则找 token → `await resolver.resolve_*` → 替换成数值字面量 → 调 L1 |
| 简化注入 | `trial_balance_service` | `execute_formula(f, tb_map, {})` → `from_simple_map` 只产 3 键 |

### 裁决：`ADJ()` 走 **ctx 注入**，新增 `FormulaContext.adj_data`

```
adj_data: dict[str, dict[str, Decimal]]   # account_code → {'aje_net': …, 'rje_net': …}
```

`_handle_adj(args, ctx, trace)` 纯同步查 `ctx.adj_data`，与 `_handle_tb` 查 `ctx.tb_data` 同构。

**为什么不走预替换**：预替换要在每个 L2 各写一遍正则替换（`report_engine` 已有 9 个 pattern
的替换循环），而 ctx 注入只需各 L2 填一个 dict。且预替换路径把 `PREV/NOTE/WP/AUX` 一律
替换成 `"0"`——若 `ADJ` 也进那个列表会**恒 0 且无告警**，正是当前 `TB(code,'AJE调整')`
恒 0 的同型陷阱。

**L2 预载的单一入口**：新增 `adjustment_amount_source.adj_net_batch(db, project_id, year,
account_codes, *, include_statuses, exclude_origins) -> dict[str, dict[str, Decimal]]`，
三个 L2（试算平衡表 / 报表 / 底稿审定表）都调它。

🔴 **禁止**在任何 L2 内另写 `adjustments` 聚合 SQL——这正是 B1/B2/B3 三个缺陷的成因
（`summary_with_adjustments` 自写了一份，于是漏了 status 过滤、origin 过滤，还用错了表）。

### 口径参数在调用点显式传递

沿用 `adjustment_amount_source` 既有约定（实测其文件头注释即此表）：

| 调用点 | `include_statuses` | `exclude_origins` |
|---|---|---|
| 试算平衡表调整列 | `{approved}`（默认） | `{workpaper}`（防 V124 双计） |
| `ADJ()` 底稿呈现 | `{approved}`（默认） | `frozenset()`（不排除） |
| 交叉核对 | 同 `ADJ()` | 同 `ADJ()` |

⚠️ **`ADJ()` 在不同域的 `exclude_origins` 不同**，这是**语义差异不是缺陷**（ADR-ADJ-002 已裁定）。
因此 `adj_data` 的预载参数由 L2 决定，L1 只管查 dict——这恰好是 ctx 注入模式的额外好处：
口径差异留在 L2，L1 保持纯粹。

## 四、阶段划分与依赖

```
Phase 0 口径收敛（需求 1）          ← 独立可交付，修错误数字，必须最先
   │  产出：summary_with_adjustments 委托 adj_net_batch
   │  副产：真库开始出现非零调整值（供后续阶段验证）
   ▼
Phase 1 统一内核（需求 2 + 3）      ← 依赖 Phase 0 的 adj_net_batch
   │  产出：_REGISTRY 注册 ADJ + FormulaContext.adj_data + 三个 L2 填充
   ▼
Phase 2 数据模型（需求 4）          ← 依赖 Phase 1 的 ADJ() 可用
   │  产出：V166 迁移 + ORM + service 读写 + 默认退回逻辑
   ▼
Phase 3 前端（需求 5）              ← 依赖 Phase 2 的字段存在
      产出：公式管理多列展示 + 口径说明
```

**Phase 0 单独交付的价值**：即使后续阶段全部不做，Phase 0 也已修正错误数字。
这是把它排第一的理由，不是为了"先易后难"。

## 五、Property（必验不变式）

| # | Property | 验法 | 为何不能省 |
|---|---|---|---|
| **P1** | ~~净额拆借贷 ≡ 现有 `aje_dr - aje_cr`~~ → 🔴 **已验证为不成立**，见 `evidence/phase0-property1-verdict.md` | `test_adj_caliber_property1.py`（7 passed）：等价性边界恰为**科目方向** —— 借方类等价、贷方类**符号相反**，差额恒 `2×\|原始净额\|` | 方案 D 的前提假设，设计阶段无法凭空断言。**幸未假定等价** —— 否则会把新发现的 B4 固化进新代码 |
| **P2** | `summary_with_adjustments` 调整合计 == `adj_net_batch` 同参数值 | **调同一函数**比对，禁"两套算法碰巧相等" | 需求 1.4 |
| **P3** | draft 分录不计入 | 造 draft + approved 混合集，断言只含 approved | B1 的防回归 |
| **P4** | `origin=workpaper` 不计入试算平衡表列 | 同上，按 origin 分组断言 | B2 的防回归 |
| **P5** | 同一公式跨域等值 | `TB`/`ADJ` 在报表路径与试算平衡表路径结果相等 | 需求 3.2；E2 实测的不对称正是缺陷源 |
| **P6** | L1 内核纯同步 | `_handle_adj` 源码内 `await` 出现数 == 0；且 `inspect.iscoroutinefunction` 为 False | 需求 2.2；破坏它会让整个 L1 契约失效 |
| **P7** | 未配置调整列公式时行为零变化 | 761 条既有公式的求值结果前后逐条相等 | 需求 4.2 |
| **P8** | 迁移可重入 | V166 连跑两次不报错；`scan_migrations` 无同号冲突 | V040 冲突的教训（已有同号检测，须确认 V166 不撞） |
| **P9** | `_KNOWN_ADJ_EXEMPT` 豁免已删且不复活 | 该常量引用数 == 0；且 `validate_formula("ADJ(...)")` 正向返 `[]` | 需求 2.5；豁免留着 = 假绿 |

### Property 的反向自检（铁律㉒）

P3/P4 这类"某物不被计入"的断言，**必须配双向变异**：
- 正向：draft 集合 → 结果不含它
- 反向：把同一条改成 approved → 结果**必须**含它

只做正向的话，`adj_net_batch` 返回恒空也能让 P3/P4 通过。

## 六、对 memory.md 的勘误（本轮现算发现）

| 条目 | memory.md 记载 | 现算实测 |
|---|---|---|
| 最高迁移版本 | V044 | **V165** |

交付时须更新 memory.md。铁律②的意义正在于此——若照 V044 写迁移会直接撞号。
