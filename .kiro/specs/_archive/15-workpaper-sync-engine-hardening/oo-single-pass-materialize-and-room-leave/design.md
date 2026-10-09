# 设计：OO 物化单趟写入 + participant 主动离开

**spec**：`oo-single-pass-materialize-and-room-leave`　**创建**：2026-09-22

## 一、现状实测（改动前基线，必须先复现再动手）

用户提供的 cProfile 拆解（真库 D4 entry，复用落空的全量物化）：

| 段 | 耗时 | 说明 |
|---|---|---|
| `adapter.materialize` | 42.8s | 39 趟链式 `load_workbook` + `save` |
| `extract` | 6.0s | 产物全量重解一遍 |
| `verify` | 6.9s | 反读等值再解一遍 |

端到端用户感知 ~30s（三段有重叠与 IO 等待）。

**39 趟怎么来的**：一个 entry 的契约有 N 个 binding（D4 受管 sheet 13 张、部分 sheet 多
binding），当前实现逐 binding 各开一次 workbook、写完存成临时文件、下一 binding 以它为
输入。于是同一份 ~7MB 工作簿被 openpyxl 解析 39 次、序列化 39 次 —— 这是**实现方式**带来
的成本，不是「写 39 组数据」的固有成本。

> 🔴 动手前的第一件事是**在测试里把 39 这个数字钉住**（`load_workbook` / `save` 调用计数），
> 否则「改完快了」无法与「改完少写了东西」区分开。需求 1.1 就是这条。

## 一.b、任务 2 的依赖调查结论（2026-09-22 真库实测，先于实现）

问题：39 个 binding 之间有没有「后一个 binding 读/写前一个的产物」的顺序依赖？

**答：读侧实证无依赖；写侧有 4 格同坐标重叠，但重叠是良性的（顺序不影响产物）。**

跨 binding 坐标碰撞的**完整**集合是 `xl/worksheets/sheet14.xml` 上的
**`C24` / `E24` / `C38` / `E38` 四格**，碰撞对只有一对：`customer_current_rows` ×
`customer_prior_rows`。四格背后是 D4-9 契约的第三张表 —— 表级标量 `customer_totals`
（C24/E24 本期总额·数量，C38/E38 上期总额·数量）；`managed_tables_of` 对**静态表**的归属
规则是「同 sheet 的每个 binding 都把它纳入自己的受管坐标」（有意的安全方向，见该函数
docstring），所以 sheet14 上两个行 binding 各把同 4 格写了一遍。

两次写入的 payload **逐字段相同**（coord/kind/value/stable_field_key/mode/formula_text），
且两边读的是**同一个** `stable_field_key` ⇒ 对任意 projection 都同写。两种顺序各 apply 一遍
后 `sheet14.xml` **逐字节相同** —— 「谁最后写」是恒等操作。

🔴 **本节此前的三处说法已被实测推翻，按实测更正**：

1. 碰撞**不是**一格（`C38`），是 4 格 —— 日志里报的列号随进程 hash 种子变（`set(plan.coords)`
   抽样），把它当成唯一碰撞点是误读；
2. 行 38 **不是**「两区共用的 footer/合计行」：本期段 footer 在 23、上期段 footer 在 37，
   行 24 与行 38 分别是两段各自的**总额行**。真因是静态表被两 binding 共同持有，与 footer 无关；
3. 因此「D4 整体必须 decline、要先改 D4-9 契约才能吃到单趟」这个结论**不成立**：碰撞良性，
   D4 可以合并。当前实现里那条「坐标相交即 decline」是**过度保守**，把 D4 挡在单趟之外。

落到实现（任务 3 的约束，完整版见文末附录 A）：decline 判据从「坐标相交」收紧为
「**同坐标且写入 payload 不同**」；`row_shift` 与 `openpyxl 全量重写` 两条 decline 原样保留
（那两条是真依赖）；decline 原因必须按排序后的**完整**碰撞集合报，不得再抽样报一格。

## 二、方案：单趟写入

```
现状：  load → write(b1) → save ─┐
                                 └→ load → write(b2) → save ─┐  … ×39
目标：  load → write(b1..bN) → save        （1 次 load / 1 次 save；仅当无跨 binding 坐标碰撞）
```

关键点：

1. **binding 之间是否真的有顺序依赖？** 需先实证。链式实现天然允许「后一个 binding 读到
   前一个的写入结果」。若契约里存在这种依赖（例如公式落格后另一 binding 读它），单趟化
   必须显式建模顺序，而不是假设无依赖。**这是本 spec 的第一个调查任务**，不是实现细节。
2. **写入顺序稳定**：单趟内按 binding 的契约声明序写，产物字节才可复现（digest 稳定是
   复用与幂等的前提）。
3. **失败即整趟回滚**：写入过程中任何异常 ⇒ 不产出 staged artifact、不留临时文件
   （需求 1.3）。单趟化让这条比链式更容易做实：只有一个产物文件。
4. **句柄释放**：写完 `release_scoped_workbooks(path)`，Windows 上才能删掉链路里的临时
   文件（上一轮已踩过）。

## 三、方案：解析结果复用（extract / verify）

`workbook_read_scope()` 已经提供「作用域内同一 `(文件身份, data_only)` 只解析一次」。
materialize 产出产物后，extract 与 verify 对**同一份字节**各解析一次 —— 把三段放进同一个
scope 即可省掉两次全量解析。

风险与边界：

* `data_only=True/False` 是**不同**的解析结果（公式 vs 公式值），两者不可互相冒充。scope
  的键里已含 `data_only`，复用时不得把它抹掉。
* verify 的**结论**不得复用（需求 2.3）：复用的是「解析出来的 workbook 对象」，不是「比对
  通过」这个判断。变异反证：少一个字段必须红。

## 四、方案：participant 主动离开

```
现状可用的终态： active ──closing──> (close barrier / close_capture / room 收尾)
需求 4 要的：    active ─────────────> left      （只释放这个人的 lease）
```

* 落点：`WorkpaperSyncRepository`（原子写，走 `PARTICIPANT_EDGES` 的 `assert_transition`）
  \+ `RoomService`（授权与策略）+ 一条 `POST …/rooms/{room_id}/participants/{id}/leave`。
* **不做**的事（这些正是 close-intent 在做、而「离开」不该做的）：不建 request、不选
  leader、不推 barrier、不旋转 generation、不改 room 状态（除非它是最后一个 active 且
  room 的收尾另有明文规则 —— 那属于 close barrier 的职责，本端点不越界）。
* 授权顺序与既有端点一致：`_guard(...)` 先行，scope index 命中后才锁业务行。
* 幂等：已 `left` 再 leave ⇒ 同一结果、不写第二条事件（`PARTICIPANT_EDGES[left]` 是空集，
  直接 `assert_transition` 会抛 —— 因此幂等分支必须**显式**先判当前状态，而不是靠捕获异常）。

## 五、Property（可被变异检验的判据）

| # | Property | 对应验收 | 反证方式 |
|---|---|---|---|
| P1 | 一次物化的 `load_workbook` / `save` 调用各恰 1 次 | 1.1 | 把实现改回链式 ⇒ 计数 39 ⇒ 红 |
| P2 | 新旧两条路径的 extract 结果逐字段相等 | 1.2 | 故意漏写一个 binding ⇒ 字段缺失 ⇒ 红 |
| P3 | 任一 binding 抛错 ⇒ 零产物、零临时文件残留 | 1.3 | 在第 k 个 binding 注入异常 ⇒ 扫目录必须为空 |
| P4 | 全流程同一份字节只解析一次 | 2.1 | 去掉 scope 复用 ⇒ 解析计数 >1 ⇒ 红 |
| P5 | verify 仍逐字段比对（复用解析 ≠ 复用结论） | 2.3 | **产物字节**上抹掉一个受管格（产物真的少一字段）⇒ 拥有该缺陷类的那道门必红。🔴 **不是**「漏写一个 binding」—— 实测那条在 steady state 上产出**逐字节相同**的产物（附录 G.4） |
| P6 | 同 projection 连续两次 materialize：第二次命中复用 | 3.2 | 把 digest 口径改回裸 `json_safe` ⇒ 第二次走全量 ⇒ 红 |
| P7 | leave 只改该 participant，其余 participant 与 room 状态不变 | 4.3 | 让 leave 顺手改 room.state ⇒ 红 |
| P8 | dirty 时 leave 被拒（前后端同源） | 4.4 | 放宽任一侧 ⇒ 红 |
| P9 | leave 幂等：重复调用不产生第二条事件 | 4.2 | 去掉幂等分支 ⇒ `assert_transition` 抛 / 事件数 2 ⇒ 红 |

## 六、非目标

* **不**动 `derive_doc_key`：doc_key 只由 `(wp_id, entry_id, generation)` 派生是 shared room
  的前提（同一工作簿的所有编辑者必须进同一个协同会话，否则两个会话各存一次整本、互相
  覆盖对方 sheet 的改动）。sheet 级定位由 contents token 的 `sheet` claim + config 的
  `actionLink` 两条腿承担，与本 spec 无关。
* **不**引入 workbook 的模块级长存缓存（Windows 删不掉临时文件）。
* **不**把 extract/verify 合并成一个函数：verify 的独立存在就是「不信任 materialize 的
  自述」，合并等于取消这条判据。

## 七、风险

| 风险 | 表现 | 对策 |
|---|---|---|
| ~~binding 间存在隐式顺序依赖~~ **已实测排除**（任务 2） | 单趟写入后某些格值不同 | 39 binding 逐一实测：读侧位置无关（0/39 漂移）、写侧 4 格重叠且 payload 全同 ⇒ 无需拓扑排序。判据按附录 A「任务 3 必须保住的四条」落地；契约一动就重跑 `analyze_d4_binding_dependencies.py` |
| openpyxl 单趟写入内存峰值升高 | 大工作簿 OOM | 实测峰值内存；必要时按 sheet 分组多趟（仍远少于 39 趟） |
| 复用命中率上升后掩盖单趟化缺陷 | 全量路径很少被走到、缺陷不易暴露 | 判据里强制走全量路径（改一个字段后立刻物化） |
| leave 端点被误当作 close | 有人拿它替代 close barrier | 端点文档 + 判据明写「room 收尾不在此」；close_capture 相关字段一个都不动 |

---

## 附录 A：binding 顺序依赖调查（任务 2 · 2026-09-22 真库实测）

**结论一句话**：39 个 binding 之间**不存在**「后一个读前一个写入结果」的依赖（读侧 0/39 漂移）；
写侧有 4 格跨 binding 同坐标重叠，但两边 payload 逐字段相同、两种顺序产物逐字节相同 ⇒
**不需要拓扑排序，任何写入顺序都得同一产物**。

**复现命令**（仓库根）：

```powershell
.venv\Scripts\python.exe backend/scripts/analyze/analyze_d4_binding_dependencies.py
```

证据：`docs/operations/evidence/oo-single-pass-materialize/binding-dependencies.json`
（39 binding 逐一入册，含每个碰撞格的逐方写入签名）。脚本是**常驻工具**（无 `_` 前缀）——
结论随**契约**变（受管表集合、静态表归属、受管区行列），契约一动必须重跑；任务 3 落地后
还要再跑一次确认前提仍成立，任务 4 的等值判据也复用同一份逐 binding 计划签名口径。

### A.1 调查对象与方法

| 项 | 值 |
|---|---|
| entry | `xlsx/gt-d4-operating-revenue`（46 张业务 sheet + `_GT_SYNC`） |
| binding | **39**（真实契约派生：`_align_specs_to_sibling_tables` + `_static_region_bindings`，与生产 attach/publish 同一内核） |
| 受管 sheet part | **33**（5 张承载多 binding：sheet3 / sheet14 / sheet26 / sheet44 / sheet46） |
| projection | substrate 自身反读结果 ⇒ 覆盖**每个** binding 的受管区 |
| 写入策略 | 39/39 `zip_patch`（无一走 openpyxl 全量重写） |
| `row_shift` | **0/39**（本次全无结构性插行） |

方法上刻意不用「读代码找引用」：计划期的读取面实际是**整本 zip**
（`_plan_materialize_step` 把 `substrate_entries` 全量喂给 `plan_managed_writes`），
靠读代码穷举不完。改为**两组计划对照实验**：同一 binding 的计划分别算在「原始 substrate
字节」与「前 k−1 个 binding 写入后的字节」上，逐字段比签名。

🔴 **输出确定性已验证**：脚本在两个**独立进程**（各自的 str hash 种子）里各跑一遍，
五类判决 + 顺序探针 + binding 清册**全部逐字相同**。这一条是刻意验的 —— 生产 decline 日志
报的列号会在 `C38`/`E38` 之间跳，正是因为它按 `set(plan.coords)` 抽样；本审计的结论若也随
种子漂移，就不能当依据用。

### A.2 逐类判决

| 类 | 判决 | 实证 |
|---|---|---|
| **D1 同格 / 坐标重叠写入** | ⚠️ **有 4 格**，但**良性** | 见 A.3 |
| **D2 读取前一 binding 的写入结果**（公式落格 / 区间 / runtime binding 全在内） | ✅ **实证无依赖** | 39/39 binding 的计划签名在「原始字节」与「链式字节」上**完全相同**，漂移 0 个 |
| **D3 公式落格** | ✅ **实证无依赖** | 52 处受保护公式格全走 `cached_value_only`（只改 `<v>`、`<f>` 逐字保留）；`formula_text` 改写 **0 处**；写入形态统计 `inline_text` 113 / `number_literal` 53 / `cached_value_only` 52 / `boolean_literal` 4 —— 没有任何一处写入会让别的 binding 读到**新公式** |
| **D4 跨 sheet 引用** | ✅ **实证无命中** | 扫全部 **47** 个 worksheet part 的 **168** 条 `<f>`，指向「另一 binding 写入面内某格」的引用 **0** 条（来自未受管 sheet 的也是 0）。即便有，也不构成写入顺序依赖：materialize 对受管公式格只写缓存值、不重算 |
| **D5 命名区域 / `_GT_SYNC` runtime binding** | ✅ **本次无依赖**（**有前提**） | 整趟写入面 = 33 个 worksheet part，`xl/workbook.xml` **未被写**、`_GT_SYNC`（`xl/worksheets/sheetGtSync.xml`）**未被写** ⇒ 计划期读到的 definedName 与 runtime binding 在整趟里逐字节不变。前提见 A.5 |

D2 的签名口径（逐项都进比对，不是只比汇总量）：全部 `CellWrite` 的
`coord/kind/value/stable_field_key/row_key/mode/formula_text` + `preserved_formulas` +
`footer_marker_row` + `row_shift` + `total_formula_rows` + `table_part` +
`managed_sheet_key` + `managed_table_name` + `workbook_row_change` +
`dynamic_column_columns` + **region 区间** + **`_GT_SYNC` runtime binding 全表** + 写入策略。
后两项是刻意加的：即使写入清单恰好没变，「读到的区间/绑定变了」也算依赖。

### A.3 完整碰撞集合（确定性求交，非抽样）

全部 39 binding 逐对求 `(sheet_part, coord)` 交集，排序输出：

| # | 单元格 | 写入方 | 驱动字段（两方同一个） | 写入形态 | 值敏感 | payload 全同 |
|---|---|---|---|---|---|---|
| 1 | `xl/worksheets/sheet14.xml!C24` | `customer_current_rows` / `customer_prior_rows` | `customer_totals/current_total_amount` | `number_literal` | 否 | ✅ |
| 2 | `xl/worksheets/sheet14.xml!E24` | 同上 | `customer_totals/current_total_quantity` | `number_literal` | 否 | ✅ |
| 3 | `xl/worksheets/sheet14.xml!C38` | 同上 | `customer_totals/prior_total_amount` | `number_literal` | 否 | ✅ |
| 4 | `xl/worksheets/sheet14.xml!E38` | 同上 | `customer_totals/prior_total_quantity` | `number_literal` | 否 | ✅ |

**碰撞对只有一对**：`customer_current_rows` × `customer_prior_rows`，共 4 格。其余 4 张
多 binding sheet（sheet3 `adjudication_main/other_rows`、sheet26 三区、sheet44 两区、
sheet46 两区）**零碰撞** —— 同 sheet 多受管区是常态，它们写的是互不相交的坐标。

**碰撞的真因**（与本节此前的猜测不同）：这 4 格是 D4-9 契约的第三张表 —— 表级标量
`customer_totals`（`phase5_d4_customer_structure.py`：C24/E24 本期总额·数量，
C38/E38 上期总额·数量）。`managed_tables_of` 对**静态表**的归属规则是「静态表没有行身份，
不按 binding 一一切分，同 sheet 的**每个** binding 都把它纳入自己的受管坐标」，并在该函数
docstring 里明写这是**有意的安全方向**（静态格被每个 binding 都当受管 ⇒ 没有任何一趟会把它
误判成 unmanaged drift；`_merge_projections` 对相同静态 key 幂等）。于是 sheet14 上两个行
binding 各把同 4 格写了一遍。行 24 / 行 38 分别是两段**各自**的总额行（本期段 footer=23、
上期段 footer=37），**不是**「两区共用的合计行」。

**为什么重叠是良性的** —— 两条实证，缺一不可：

1. **payload 逐字段相同**：4/4 格的两方写入在 `coord/kind/value/stable_field_key/mode/
   formula_text` 上完全一致（JSON 里 `per_writer` 逐方留档）；
2. **两边读的是同一个字段**（所以不是「当前值恰好都是 `Decimal('0')`」的巧合）：把
   `customer_totals/current_total_amount` 从 `0` 改成 `111111` 重算两边计划，两个 binding
   在 C24 上都写 `Decimal('111111')`（`both_bindings_agree=true` 且
   `changed_with_shared_field=true`）⇒ 对**任意** projection 值都同写。

**顺序不变性直接实测**：把这两个 binding 的计划按 A→B 与 B→A 各 apply 一遍，
`sheet14.xml` 部件**逐字节相同**（`sheet_part_bytes_equal_across_orders=true`）。比的是
整个 part 而不是只比那一格 —— 只比一格会漏掉「别处也被顺序影响」。

### A.4 拓扑排序？—— **不需要**，也无从建图

要拓扑排序得先有**有向**边（「B 必须在 A 之后」）。本次实测三类候选边全空：

* 读→写边（D2）：0 —— 没有 binding 的计划依赖别人的写入结果；
* 公式 / 跨 sheet 引用边（D3/D4）：0；
* 命名区域边（D5）：0（workbook.xml 与 `_GT_SYNC` 本趟未被写）。

唯一存在的跨 binding 关系是 D1 的 4 格**无向**重叠，且重叠上的写入是**恒等覆盖**
（幂等、可交换）。因此依赖图是 39 个孤立节点，**任何**写入顺序（含单趟内的契约声明序）
都产出同一份字节。「last-writer-wins 决定结果」这件事在 D4 上**不成立** —— 不是「顺序无关
碰巧成立」，而是「重叠格上两个写入是同一个写入」。

⚠️ 这个结论是**对本契约的实测结论**，不是对所有 entry 的定理。别的 entry 完全可能出现
「同坐标 + 不同 `stable_field_key`」（两个不同字段争一格）—— 那时 payload 会不同，顺序就
决定结果，必须 decline（或在契约层消歧）。判据要写成运行时可判的形态，不能写成「D4 没问题
所以都没问题」。

### A.5 本次调查**没有**覆盖到的（不得当成「已证无依赖」）

诚实列清，避免下游把「本次没测到」读成「不存在」：

1. **插行（`row_shift`）路径下的依赖没有被实测** —— 本次 39/39 全无插行，所以 D5 的「无依赖」
   是**有前提的**：`_apply_workbook_propagation`（引用侧 sheet + definedName）、
   `_grow_managed_table_ref`（Table ref）、`_refresh_gt_sync_runtime_binding`（`_GT_SYNC`
   重冻结）三段**全部**挂在 `plan.row_shift is not None` 分支下。一旦有 binding 插行，这三处
   都会被改写，后续 binding 的计划坐标就是陈旧的 —— 那是**真依赖**。现有实现对此已 decline，
   **必须保留**（`excel_materialize.materialize_projection_single_pass` 的第 2 条 decline）。
2. **本 projection 之外的值组合没有被穷举**。A.3 的第 2 条实证把「同值巧合」排除了，但
   D1 的 payload 相同性依赖 `_resolve_column(spec, table, region, binding)` 对两个 binding
   解出同一列 —— 这是**实测**（4/4 格同列），不是类型层面的保证。契约改了要重跑。
3. **OO→HTML 方向的 incoming substrate 未测**：本次 substrate 是 instrumented 模板
   （`html_to_oo` 方向）。incoming 路径多一层 `reinject_runtime_binding_from_base_if_needed`
   与 `intended_formulas`（本次传 `None`）。`intended_formulas` 非空时受保护格会产生
   `formula_text` 还原写入 —— 那是**新的写入形态**，本次统计为 0 处，不代表该路径也是 0。
4. **Excel 重算语义上的依赖没有也不可能在这里判**：D4 扫的是 `<f>` 文本引用，命中 0；但
   materialize 从不重算公式（只写缓存值），所以「引用了别人写的格」在本平台的两条写入路径上
   表现相同。如果将来有人让 materialize 去重算，本节结论**立即作废**。

### A.6 任务 3 必须保住的四条

1. **decline 判据从「坐标相交」收紧为「同坐标且写入 payload 不同」。**
   现行实现（`materialize_projection_single_pass` 第三条检查）只比坐标归属的 `table_key`，
   于是 D4 的 4 格良性重叠把**整个 entry** 挡在单趟之外 —— 单趟优化对 D4 当前**一点都吃不到**。
   收紧后 D4 可以合并。payload 比较面 = `(kind, value, stable_field_key, mode, formula_text)`
   全等即视为恒等覆盖（幂等，可合并）；任一项不同即 decline。
2. **decline 原因必须确定性、必须完整。** 现行实现按 `for coord in set(plan.coords)` 遍历、
   命中第一处即抛 ⇒ 报的列号随进程 hash 种子变（真库上见过 `C38` 与 `E38` 两种），且剩下的
   碰撞看不见。改为逐对求交、排序、把**完整**碰撞集合写进 `SinglePassDeclined.reason`
   （真库要能统计回落比例与回落原因，需求 3.3）。
3. **`row_shift` 与 `openpyxl 全量重写` 两条 decline 一字不动。** 它们是 A.5 第 1 条说的真
   依赖与真不兼容，不在本次「过度保守」的范围内。
4. **单趟内按 binding 的契约声明序写**（design 二.2 已有）。A.4 证明顺序不影响**本契约**的
   产物，但声明序仍是唯一可复现的顺序 —— 依赖「顺序无所谓」去用 `set`/`dict` 的偶然序，
   等于把一条未来会被契约变更打破的假设写进实现。

配套判据建议（留给任务 3/4 决定落在哪个文件）：

* 把「39 binding 的计划位置无关」做成回归判据 —— 它是单趟正确性的**前提**，不是一次性结论；
* 把「D4 的跨 binding 重叠恰为那 4 格且 payload 全同」钉住 —— 契约层若把静态表归属改了
  （例如让 totals 只归一个 binding），这条会红，届时 D4 连碰撞都没有，判据要相应更新。

### A.7 与 requirements 措辞的冲突 —— **已拍板并落地**（2026-09-22，任务 3）

原冲突：需求 1.1 的 ⚠️ 段写「存在跨 binding 坐标碰撞的 entry（实测 D4 的 C38）SHALL 显式
回落逐趟链式 …… 合并会丢失同格写入顺序」。本次实测与它两处不符：① D4 的碰撞是 4 格不是
1 格；② D4 的碰撞**不会**丢失任何东西（payload 全同、顺序不变），按该措辞 D4 必须回落，
而回落让需求 1.5 的「≤10s」对 D4 **永远达不到** —— 而 D4 正是需求 1.5 指名的那个 entry。

**拍板结论（用户 2026-09-22）**：收紧为「坐标碰撞**且写入 payload 冲突**」，并同步改
requirements 1.1。已落地：

| 落点 | 内容 |
|---|---|
| `requirements.md` 需求 1.1 ⚠️ 段 | 条件改为「坐标碰撞**且写入 payload 冲突**」，写明比较面与「原措辞为何不成立」，并补一条「decline 原因须确定、完整」 |
| `excel_materialize._cross_binding_payload_conflicts` | 逐对求交 → 排序 → 报**完整**碰撞集合；payload 比较面 `(kind, value, stable_field_key, mode, formula_text)`，`value` 取 `repr`（`0` / `0.0` / `Decimal('0')` 落盘字节不同，不得判等） |
| `excel_materialize.coord_sort_key` | 「先行后列」排序键的唯一实现；`analyze_d4_binding_dependencies.py` 的 D1 报告改为委托它 ⇒ 审计证据与生产日志同一排序口径 |
| `row_shift` / `openpyxl 全量重写` 两条 decline | **一字未动**（A.5 第 1 条说的真依赖与真不兼容） |

**payload 比较面为何不含 `coord` 与 `row_key`**：`coord` 是分组键（同格才比）；`row_key` 是
行身份元数据、**不进落盘字节** —— 两方 `row_key` 不同而其余全同时写出的 XML 逐字节相同，
仍是恒等覆盖。把 `row_key` 塞进比较面会让 D4 那 4 格良性重叠重新被误判成冲突。

**落地实测（任务 3 完成后，同一 world / 同一 projection）**：

| 量 | 链式（回落路径） | 单趟（默认路径） |
|---|---|---|
| 写入趟数 | 39 | **1** |
| `load_workbook` 合计 | 83 | **7** |
| 其中 substrate 链（文件） | 78 = 39×2 | **2**（需求 1.1 的 `≤ 2`） |
| 其中 BytesIO 固定开销 | 5 | 5（未变） |
| `Workbook.save` | 2 | 2（未变，全来自转置 sheet） |
| 墙钟 | 16.7s | **5.3s** |
| tracemalloc 峰值 | 118.1MiB | **26.0MiB** |

⇒ design 七「openpyxl 单趟写入内存峰值升高」这条风险**实测反向**：单趟少解析 76 次
workbook，峰值内存降了 4.5 倍，无需按 sheet 分组多趟。

**A.6 前提复核（任务 3 后重跑 `analyze_d4_binding_dependencies.py`）**：D2 计划位置无关
`True`（漂移 0/39）、D1 碰撞恰 4 格且 `payload 全同 4 / 值敏感 0`、D3 公式文本改写 0 处、
D4 跨 sheet 引用命中 0、D5 `workbook.xml` 与 `_GT_SYNC` 本趟未被写 —— 与任务 2 逐字相同。

**链式路径未删，且不应删**：它是 decline 三条（插行 / openpyxl 全量重写 / payload 冲突）的
正式回落路径，被 `_try_single_pass_materialize` 返回 `None` 时真实到达 ⇒ 不是不可达分支、
不是死代码。任务 3 的任务文本禁止的是「把旧实现留成**同一个函数内的不可达分支**」，本实现
不是那种形态：单趟与链式是两个独立函数，由 decline 显式分流。`force_chained_path()` 与
`test_chained_fallback_path_call_counts` 因此继续留着当回落路径的回归网（原注释里「链式被
删那天一并删除」的说法按本结论作废）。

---

## 附录 B：新旧产物等值判据（任务 4 · 2026-09-22 真库实测）

判据落 `backend/tests/workpaper_sync/test_single_pass_artifact_equivalence.py`（27 条）。
与趟数判据分文件：那边的标题命题是「提速有没有发生」（P1），这边是「提速有没有以少写
binding 为代价」（P2），失败时两问在文件名上就分得开。world 仍来自
`tests/workpaper_sync/d4_materialize_harness.build_world`（`_frozen_d4()` 带 `lru_cache`，
多一个测试模块只多付一次铺 world）。

### B.1 「旧链式」怎么取：不必 git 检出历史实现

任务文本允许「历史实现**或等价模拟**」。实际用的是比两者都强的第三种：链式路径**仍是活
代码**（附录 A.7 末段），`force_chained_path()` 只把单趟入口摘掉即可让 `adapter.materialize`
走它。于是比的是**两条今天都会被走到的真实路径**，「复刻件与真实实现漂移」这类风险不存在。

反空转前提**显式断言**（`test_both_artifacts_really_came_from_different_code_paths`）：
链式侧 39 趟 / 单趟趟次 0 / substrate 解析 78；单趟侧 1 趟 / 单趟趟次 1 / substrate 解析 2。
少了这一条，helper 哪天静默变成 no-op，两侧就跑同一条路径，「逐字段相等」永远绿。

### B.2 比较面：`repr` 口径的全字段比对，不复用既有两套「等值」

| 面 | 内容 |
|---|---|
| `Projection` | `contract_id` / `semantic_version` / `document_type` / `values` / `row_keys`（行身份**有序**） |
| `FieldValue` | `stable_key` / `value_type` / `mode` / `repr(value)` / `row_key` |

`value` 取 `repr` 与 `excel_materialize._write_payload`、
`analyze_d4_binding_dependencies._write_signature` **同口径**：`0` / `0.0` / `Decimal('0')` /
`False` 在 `==` 下两两相等而落盘字节不同，用 `==` 比会让 P2 退化成空话（6 个值对逐一反证）。
差异清单**完整且排序**，与 decline 原因同一条纪律（A.6 第 2 条）。

**为什么不复用现成 helper**（两条都做成了可执行判据，不是注释里的自我声明）：

* `projection_digest_value.canonical_value_for_digest()` —— 它的**设计目的**就是把 `0`/`0.0`
  折叠成同一表示（否则业务身份复用恒不命中）⇒ 拿它当等值判据等于主动放弃最该抓的那类差异；
* `excel_extract.verify_roundtrip_equivalence()` —— 生产发布门，比较范围刻意**只含
  `mode=editable`** ⇒ 一个整体落在受保护字段上的 binding（D4 `revenue_detail_rows` 那 12 处
  全是 `cached_value_only`）漏写了它一句话都不说。判据断言它的 `compared_keys` 是全量 key 的
  **真子集**，且它对本次两份产物给出 `equivalent=True`（与本判据不冲突）。

### B.3 实测结论

| 量 | 链式 | 单趟 |
|---|---|---|
| `extract` 字段数 | 218 | 218（**0 缺 / 0 多 / 0 改**，header 与 `row_keys` 全同） |
| zip entry | 142 | 142（内容**逐 entry 全同**；142/142 `date_time` 不同 ⇒ sha256 不同，字节数均 246110） |

⇒ 需求 1.2 的安全底线成立：单趟没有少写任何东西。sha256 不比（任务 1 已实测它本就不可
复现），字节判据逐 entry 比并**显式**把 `date_time` 分流。

### B.4 🔴 实测发现：反读判据单独**不够用**（需求 1.2 措辞待拍板）

变异反证按 design 五 P2 的「故意漏写一个 binding」做，注入点是生产内核
`_plan_materialize_step`（只改输入，不改判据 / adapter / 契约）。挑了**两类**受害者：

| 漏写 | 反读判据 | 字节判据 |
|---|---|---|
| `d4_32_groups`（34 处 `inline_text`） | **红**：24 个字段 `'1'` → `1` | 红：`sheet41.xml` |
| `d4_10_rows`（49 处 = 28 `inline_text` + 21 `number_literal`） | **绿 ⇐ 窟窿** | **红**：`sheet15.xml` −95 字节 |

两处与原措辞不符，按实测记：

1. **漏写一个 binding 不表现为「字段缺失」**。design 五 P2 的反证方式写「⇒ 字段缺失 ⇒ 红」，
   实测是**值/类型变**（218 → 218，0 缺 0 多）。因为 projection 取自 substrate 自身，漏写
   等于「保留原值」，key 集合不会少。⇒ 判据面必须同时覆盖「缺字段 / 多字段 / 值变」三类；
   只查 key 集合的判据在这条反证下是**绿**的。
2. **「反读等值」对一整类漏写天生是盲的**：写入只改变单元格的**表示形态**（inline string vs
   shared string、数字格式）而不改变反读值时，漏写在 `extract` 侧完全看不出来 —— `d4_10_rows`
   的 49 处写入整个丢掉，218 个字段逐字段全等，而产物真的少了 95 字节。

⇒ 结论：**逐 zip entry 字节判据（忽略 `date_time`）是必需项，不是加强项**。需求 1.2 目前只
指名反读等值，建议把字节判据一并写进验收标准；这属于 requirements 措辞变更，**待拍板**后再
改（不擅自改验收标准，参照 A.7 的处理方式）。任务 9 的 verify 变异反证（P5）也受这条影响：
「产物少一个字段 ⇒ verify 必红」在自反读 projection 上未必成立，需按本节重新设计反证输入。

---

## 附录 C：失败原子性判据（任务 5 · P3 · 2026-09-22 真库实测）

判据落 `backend/tests/workpaper_sync/test_single_pass_failure_atomicity.py`（22 条）。world 仍
来自 `d4_materialize_harness.build_world`，注入一律拦**生产内核**（与附录 B 同一纪律：只改
输入/只让它抛，不改判据、不改 adapter、不改契约）。**生产代码本次零改动。**

### C.1 三个断言面各自实际验了什么

| 面 | 形态 | 实测 |
|---|---|---|
| ① 无 staged artifact | 分两种：`output` 此前不存在 ⇒ 必须**仍不存在**；此前已有成功产物 ⇒ 必须**逐字节未变**（sha256 比） | 两种都成立 |
| ② 临时目录扫描为空 | 把 `tempfile.tempdir` 重定向到私有目录（共享系统 temp 上求差必假红）⇒ 扫描面 = workdir（含 `.staging`）+ 该私有目录，**前后快照求差**（新增/消失/内容变更三类，含 sha256） | 新增条目 0 |
| ③ DB 无半条记录 | **materialize 根本不碰库** —— 见 C.3。不伪造「查库 0 行」那种在任何实现下都绿的断言 | 全程 DB 调用 0 |

②的非空转由 `NamedTemporaryFile` 清册证明：链式 k=first/middle/last 实测中间产物
**1 / 20 / 38** 个**真的落过盘**（design 二.3 说的「前 N 个 binding 已落盘」中间态确实存在），
失败后一个不剩；单趟侧一个都没建过（中间态全在内存）。

### C.2 覆盖面：k × 路径 × 注入点（15 次注入失败）

* **k**：第一个 / 中间（19）/ 最后一个（38）binding，`trips` 实测 = k+1；
* **路径**：单趟（默认）**与**链式（`force_chained_path()`，decline 三条的正式回落路径）；
* **注入点**三处，越靠后盘上的中间态越真：`_plan_materialize_step`（算计划时炸）/
  `_apply_step_to_bytes`（改字节时炸）/ `os.replace`（改名时炸 —— 唯一能让
  `*.materializing` 半成品**真实存在**的时刻，实测 237925 字节，事后被 `finally` 删净）。

**判据非空转已由定向变异实测**（改生产码 → 跑判据 → 复原）：摘掉单趟 `finally` 的
`tmp.unlink()` ⇒ 单趟侧改名判据红（链式侧仍绿，归因精确）；摘掉链式 `finally` 的中间产物
`unlink` ⇒ 链式 k=first 红 1 个残留、k=middle 红 20 个（单趟侧全绿）。

### C.3 ③ 的诚实答案：DB 侧原子性不住在 materialize 里

`excel_materialize` / `adapters/excel` / `excel_extract` / `workpaper_sync/models` 的**全部**
import（含函数体内延迟 import）里没有任何 DB 模块（判据逐条扫 AST），且一次注入失败的
materialize 全程 SQLAlchemy 侧 `Engine.connect` / `AsyncEngine.connect` / `Session.execute` /
`AsyncSession.execute` 调用数为 **0**（观察者自身由「真连一次内存 sqlite 必须记到」反证）。

⚠️ 诚实边界：第一条是**直接** import 面的完整扫描，不是传递闭包（同包确有 `repository.py` 与
ORM 模型模块，coordinator 当然要用）。「全程没碰库」由第二条运行时证据承担。

DB 侧原子性真正的落点是 `ContentMutationService.commit()`：materialize 是第 4 步、**全在事务
外**，DB 写入是第 6 步的单事务 + `_CommitLatch` 恰一次 commit ⇒ binding 写入失败时**一行都还
没写**（判据按 AST 钉住 `_stage_and_verify` 先于 `_commit_once`，且之前一次都没碰
`self._session`）。需要 PG 的运行时版本归 coordinator 层既有的 `_TransactionWitness`
（`test_task15_content_mutation*.py`），本任务不越界重造。

### C.4 🔴 实测发现：`os.replace` **不是**最后一步（登记在案，不在本任务修）

改名之后 `adapter.materialize` 还会把转置 sheet **就地**写进 `output`
（`_transposed_materialize_file(output, ...)`，D4 两张，`Workbook.save` 那 2 次正是它）：实测
改名那刻 237925 字节 → 最终产物 246110 字节，差 8185。`_stage_and_verify` 的注释也明写「此时
adapter.materialize 已完成全部写入（**含转置 sheet 覆盖**）」⇒ 有意结构，不是疏漏。

后果：那一段抛错会在 `output` 上留下一份「只完成 zip 改写、缺转置列」的文件。判据
`test_writes_continue_after_the_atomic_rename_and_the_residue_is_bounded` 如实断言这个事实并把
**边界**锁死：残留**恰好**只有 `output` 一个条目，`*.materializing` 与中间产物照旧删净，整趟
仍失败，DB 仍零调用。

它**不算**需求 1.3 说的「把半成品当 staged artifact 发布」：`output` 由 `_stage_and_verify` 用
`uuid4()` 的 `stage_id` **每次尝试现开**一个 staging 目录算出（`work_dir /
f"materialized.{document_type}"`）⇒ 不覆盖任何既有产物、不被下次读到；发布是后面独立的内容
寻址 `stage_stream + publish_representation`，materialize 抛错时压根不执行。那正是该协议明文
定义的 **orphan**（Task 11 reconciliation 收）。要连它一起收干净的正解是「转置写 `tmp`、改名
放最后一步」，需同时改 `materialize` 三条分支（单 binding / 单趟 / 链式）与 `artifact_sha256`
口径 ⇒ **独立改动**，待拍板（处理方式参照 A.7 / B.4：不擅自改验收标准，也不擅自动生产结构）。

---

## 附录 D：句柄释放判据（任务 6 · 2026-09-22 真库实测 · Windows）

判据落 `backend/tests/workpaper_sync/test_single_pass_handle_release.py`（12 条）。world 仍来自
`d4_materialize_harness.build_world`；残留扫描机具（`scan` / `diff_scans` / `temp_file_witness`）
**复用**附录 C 那一套（从 `test_single_pass_failure_atomicity` import，不另造第三份）。
**生产代码本次零改动。**

### D.1 两个作用域函数的真实语义（读实现得来）

| 函数 | 语义 |
|---|---|
| `workbook_read_scope()` | `ContextVar` 上挂 dict，键 `(_file_cache_key(path), bool(data_only))`，其中 `_file_cache_key = (str(path.resolve()), st_mtime_ns, st_size)`。**嵌套沿用外层缓存**、关闭责任留最外层；退出时无条件 `close()` 全部（含异常路径） |
| `release_scoped_workbooks(path)` | 按 `k[0][0] == str(path.resolve())` 匹配 —— **只比路径**，不比 mtime/size、不比 `data_only` ⇒ 一次调用清掉两个视图。作用域外是安全空操作 |

进缓存的**唯一**入口是 `_acquire_read_only_workbook` ← `_read_cell_view` ←
`extract_projection` / `_extract_static_projection`。materialize 的计划阶段走
`extract_projection(artifact=substrate, …)`（`_plan_materialize_step` 唯一实现）⇒ **substrate
路径必然进缓存**：单趟 2 条（两视图），链式 78 条（39 趟 × 2）。

### D.2 判据的 oracle 与非空转（这条任务最容易空转的地方）

「release 之后删得掉」单独看可以空转：workbook 没进缓存时不释放也删得掉。三层各自立分母：

| 层 | 实测（win32） |
|---|---|
| ① 缓存快照（单趟写入**刚返回**那一刻，还在生产自己的作用域里） | 针对 substrate 恰 **2** 条（`data_only` False/True）⇒ 句柄确实被持有 |
| ② 反证：不 release 直接 `unlink` | `PermissionError` **WinError 32**「另一个程序正在使用此文件」——`…\temp-substrate.xlsx`；随后 release ⇒ 视图 2 → **0** ⇒ `unlink` 成功 |
| ③ **生产调用点承重反证**：把 `adapters.excel.release_scoped_workbooks` 换 no-op | 真库链式 materialize **当场抛** `PermissionError WinError 32`（`…tmp9wupt5s3.sheet0.xlsx`），盘上留下 **38** 个删不掉的中间产物 |

③ 是 design 六「不引入 workbook 模块级长存缓存」那条非目标的实测依据 —— 长存缓存等于把 ③ 的
no-op 变成永久状态。

⚠️ 平台诚实：oracle 是 Windows 专属（POSIX 允许删已打开的文件）。判据**不 skip**、按平台分支
断言（skip 会让文件在 CI 换 Linux 那天静默变空壳）；本平台 `win32`，跑到的是 Windows 分支。

### D.3 覆盖面与结论

| 面 | 实测 |
|---|---|
| **单趟**（任务点名） | 趟数 1 / substrate 解析 2；写完 release ⇒ `unlink` **成功**；不 release ⇒ WinError 32 |
| 单趟的 `*.materializing` | **从不进缓存**（写出即 `os.replace`，无人解析）⇒ 生产在它上面不调 release 是**对的**，不是缺陷。该判据同时是未来守卫：有人改名前去反读 `tmp` 就会红 |
| **链式回落** | 38 个中间产物**全部**进过缓存、**全部**被 release、**全部**删净（`release` 与 `unlink` 的清册逐个比对，不是只看目录空不空） |
| `data_only` 两视图 | 一次 release 清两条（2 → 0）；漏一条就还握一个句柄 ⇒ 结构与后果两面都断 |
| 定点性 | release 只清指定路径；同作用域内别的文件缓存**仍可用**（读出值仍正确，不是只剩个 key） |
| 结构守卫（AST） | `_materialize_within_scope` 里 **3** 处 `unlink` 每处前一条语句都是对同一对象的 `release_scoped_workbooks`；检查器自身有「缺 release 的源码必须被报出」的反证 |

### D.4 触类旁通：全仓 `unlink` 复查结论

写盘/校验面上只有两处删除**没有**配 release：`verify_unmanaged_regions` 的 `d429_before`
（转置 sheet 重投影副本）与 `g7_before_sanitized`。**不是缺陷** —— verify 全程只用 `zipfile`
与字节比对、不走 `_read_cell_view` ⇒ 这两个临时文件从不进缓存、上面没有句柄。该理由做成了
**运行时**判据（真跑一次 D4 verify，`temp_file_witness` 证明 `d429_before` 真被创建过、
缓存清册证明它没进去），而不是读代码下结论。

🔴 首版 AST 检查器用 `ast.unparse(statement)` 找 `.unlink(`，当场被自己咬：`unparse` 会把整棵
子树摊平，外层 `try:`/`for:`/`if:` 的文本里都含 `.unlink(` ⇒ 3 处删除被算成 8 处，且外层语句的
「前一条」必然不是 release ⇒ **写对了的生产代码被报成违规**。改判 AST 结构（只认 `ast.Expr`
包 `Attribute` 调用的叶子语句），并加一条形态覆盖自检：函数里 `.unlink` 的 `Call` 节点总数必须
等于被识别的处数，不等即报错而不是放过（检查器看不懂的写法不能算通过）。

---

## 附录 E：需求 1.5 的前后对照判定（任务 7 · 2026-09-22 真库实测）

证据 `docs/operations/evidence/oo-single-pass-materialize/task7-segment-before-after.json`
（协议 / 逐段数字 / 口径说明见同目录 README「任务 7」节）。工具仍是任务 1 那一份常驻脚本，
本任务给它加了 `--segment`（量生产 CPU 段五步）+ `--repeat`（多轮取 min/median/max）+
`--mode both`（两条路径交错）。

```powershell
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py `
    --segment --mode both --repeat 3 --label task7-segment-before-after
```

### E.1 判定：**部分达成**。「≤10s」在 `adapter.materialize` 这一段成立，在用户那个口径上不成立

| 口径 | 链式（前）median | 单趟（后）median / max | ≤10s |
|---|---|---|---|
| `adapter.materialize` | 17.127s | **5.490s / 5.602s** | ✅ 达标（连最慢轮） |
| CPU 段合计（materialize+extract+roundtrip+unmanaged+structure_hash） | 24.791s | **12.800s / 12.876s** | ❌ 未达标 |

🔴 **不得把 5.5s 记成「需求 1.5 已满足」**：requirements 1.5 的「~30s」与设计一的 cProfile
拆解（42.8 / 6.0 / 6.9）是 **materialize + extract + verify 合计**的口径，而任务 1/3 那两份
证据量的是 `adapter.materialize` 一段 —— 拿后者比前者是换口径。本任务两条路径同段对同段量，
结论是单趟化省了 11.6s（17.1→5.5），CPU 段合计 24.8→12.8s，**还差 2.8s**。

剩余成本逐段是明的（单趟侧 median）：`extract` 2.747 + `unmanaged_verify` 2.113 +
`structure_hash` 2.408 = **7.269s**，`roundtrip_verify` 0.001s 可忽略。这 7.3s 在任务 8/9
（解析复用）落地前一分没动过 ⇒ **需求 1.5 的剩余部分归任务 8**，够不够 2.8s 由它实测。

⚠️ CPU 段合计**不是**端到端：`stage_stream`/`publish_*` 的 IO、DB 单事务、HTTP/OO 握手、
前端加载态都在段外，用户感知的 ~30s 含它们。真实端到端数字**未取到**（本地栈是活的，但要让
复用落空必须改真实项目底稿内容、「前」侧还要把后端切回旧 HEAD 重启 ⇒ 登记为待拍板，不拿
12.8s 冒充端到端）。

### E.2 量 verify 时抓到的两件事（登记，不在本任务修）

1. **`ExcelSyncAdapter.verify_unmanaged_regions` 逐 binding 比完就 assert**，第一个 binding
   报漂移即抛 ⇒ 首版计时只含 39 分之一的比对量，把它记进证据会把「后」这侧记少。改为在
   verify 段内把 `UnmanagedRegionReport.assert_equivalent` 换成**收集器**，让生产那个循环跑完
   39 个 binding（生产 verify 通过时也是跑完 39 个），并把 39 条结论逐一写进证据。
2. **harness world 上那些漂移是「模板 → 第一代产物」造成的**：steady-state 探针（拿第一次
   物化的产物当 substrate 再跑一整段）实测 **39/39 等价、drifted 0**，而正常 runs 是
   drifted 39/39、首个差异恒为 `workbook_and_styles`。原因是 harness base 的 `styles.xml`
   从未被 openpyxl 重序列化过、而转置 sheet 的 `wb.save()` 会重写整簿状态；生产 substrate 恒是
   上一次发布的产物（已归一化）。探针那一段合计 12.790s 与正常 runs 的 12.800s 一致 ⇒ 12.8s
   **不是**靠「verify 提前抛出」省出来的。verify 的**结论**仍归任务 9（同附录 D.2 纪律）。

### E.3 给任务 8 的实测坐标

全 CPU 段的 `load_workbook`：链式 95 次（80 文件 + 15 内存）/ 单趟 **19 次（4 文件 + 15 内存）**。
单趟侧按调用点拆：`resolve_managed_sheet` 12（转置 sheet，materialize 4 + verify 8）、
`_acquire_read_only_workbook` 4（substrate 两视图 + **产物两视图**）、
`_structure_fingerprint_uncached` 2（before + after）、`_read_gt_sync_pairs` 1。

⚠️ 顺带暴露一个**口径冲突**，留给任务 8 拍板（本任务只记实测，不擅自改验收标准，参照 A.7 /
B.4 的处理方式）：需求 2.1 要「对同一份产物字节的解析次数为 **1**」，而实测是 **2**
（`data_only` 两视图），且需求 2.2 明说两视图不可互相冒充 —— 按字面 2.1 与 2.2 打架，
可达下界应是 2（与需求 1.1 对 substrate 的 `≤2` 同理）。

---

## 附录 F：解析复用（任务 8 · P4 · 2026-09-22 真库实测）

判据落 `backend/tests/workpaper_sync/test_single_pass_parse_reuse.py`（16 条）。world 仍来自
`d4_materialize_harness.build_world`。证据
`docs/operations/evidence/oo-single-pass-materialize/task8-segment-after-parse-reuse.json`
（任务 7 那份 `task7-segment-before-after.json` **未覆盖**，前后两份都留着）。

**一句话结论**：产物字节的解析从 **12 次降到 5 次**（其中「可共享」那一类 8 → 1），
整段 `load_workbook` **19 → 12**，`_sheet_part_map` 的 549 次调用塌成 **6 次真解析**；
CPU 段合计 median **12.800s → 7.463s**（max 12.876 → 7.470）⇒ **需求 1.5 达成**。

### F.1 两处 requirements 措辞变更（本任务拍板并落地，处理方式同 A.7）

| 条 | 原措辞 | 改后 | 为什么原措辞不成立 |
|---|---|---|---|
| **2.1** | 「对同一份产物字节的 workbook 解析次数 SHALL 为 **1**」 | 「每个**解析视图** `(字节身份, read_only, data_only)` 各 1 次，与消费方个数**解耦**」；并明确覆盖非 openpyxl 的重复解析；并要求**每个不可共享的消费方逐一列名** | 与需求 **2.2 自相矛盾**：2.2 明说 `data_only` 两视图不可互相冒充、键里必须留它 ⇒ 两个视图都被用到时「1」不可达。任务 7（附录 E.3）已把这个冲突登记为待拍板 |
| **1.2** | 只写「反读等值」 | 加 (b)「逐 zip entry 字节等值（忽略 `date_time`）」为**必需项** | 附录 B.4 实测：漏写 `d4_10_rows` 的 49 处写入后，218 个反读字段**逐字段全等**，而 `sheet15.xml` 真少了 95 字节 —— 反读判据对「只改表示形态」那一类漏写**天生是盲的** |

两处都**不放宽**任何既有判据：2.1 把一个在自己 spec 内部就自相矛盾的数字换成可判定的结构
事实 + 例外列名义务；1.2 是**新增**一个判据面。需求 2.2、2.3 一字未动。

### F.2 改了什么（四处，全部走既有 `workbook_read_scope()`）

| # | 改动 | 位置 |
|---|---|---|
| ① | 作用域支持**字节身份**的共享 workbook：键 `(("bytes:sha256", digest, len, read_only), data_only)` | `excel_extract.shared_workbook_from_bytes` |
| ② | 转置 sheet 的**只读**消费方共用一次全簿解析（`share_parse=True`） | `phase5_transposed_sheet.resolve_managed_sheet` / `extract_transposed_workbook` / `extract_file`；调用点 `adapters/excel.verify_unmanaged_regions`、`published_identity_observer.collect_workbook_structure` |
| ③ | **根因修复**：`extract_transposed_workbook` 改成真正的纯读（`_cell_ro` 非惰性取格） | `phase5_transposed_sheet._AbsentCell` / `_cell_ro` |
| ④ | 纯 XML/zip 解析在同一作用域内按文件身份记忆化 | `excel_extract.scoped_parse_memo` + `_sheet_part_map` / `_tables_of` / `_shared_strings_prefix_digest` |

③ 是这批改动里唯一动了既有读取语义的一处，而它是**前提**而不是附带优化：openpyxl 的
`ws.cell(r, c)` 在格子缺失时会**新建**一个空 Cell 塞进 `ws._cells`（那是就地改动），而发布
时刻的 `collect_workbook_structure` 正是按 `(row, col) not in ws._cells` 判「这个转置字段格
在文件里存不存在」⇒ 不先把读侧的惰性新建去掉，②的共享会**改变 structure_hash**。
`_AbsentCell` 与「openpyxl 刚新建的空 Cell」观测等价（`value is None` / `data_type == "n"`），
所以答案一字不变；`ws.max_column` 也不受影响（`range(...)` 只求值一次，新建的格全在既有
包围盒内）。

④ 的量比①②大得多：`_sheet_part_map` 在整段被调 **549** 次，而 `parse_tables` 要把 **46 张**
sheet part 全读一遍（单次 ~30ms）。549 次按段与字节形态拆开（实测）：

| 段 | 读的字节 | 调用次数 |
|---|---|---|
| materialize | substrate（`d4-base.xlsx`） | 156 |
| materialize | BytesIO（单趟计划阶段，每 binding 一次） | 39 |
| materialize | 转置写入前的中间产物 | 2 |
| extract | 最终产物 | 156 |
| unmanaged_verify | 最终产物 | 118 |
| unmanaged_verify | substrate | 78 |
| **合计** | | **549** |

### F.3 实测：解析次数（逐调用点清册，判据逐项对账）

| 调用点 | 复用前 | 复用后 | 说明 |
|---|---|---|---|
| `resolve_managed_sheet`（转置全簿 DOM） | **12** | **4** | 省下的 8→1 全在产物字节上；留下的 4 是 materialize 私有（每张转置 sheet 读一次 + 写一次，中间字节各不相同，写完再没人读） |
| `shared_workbook_from_bytes` | 0 | **1** | 产物字节的完整 DOM 视图，8 个消费方共用 |
| `_acquire_read_only_workbook` | 4 | 4 | substrate 两视图 + 产物两视图（各由 39 binding 共享，任务 3 已达成） |
| `_structure_fingerprint_uncached` | 2 | 2 | **不可共享**（`iter_rows()` 批量成格）：substrate 侧 1 + 产物侧 1 |
| `_read_gt_sync_pairs` | 1 | 1 | **不可共享**（同上） |
| **合计** | **19** | **12** | |

产物字节单独看：**12 → 5**（2 个 `read_only` 视图 + 1 个可共享完整 DOM + 2 个不可共享完整 DOM）。

纯 XML/zip 解析（④）：

| 量 | 实测 |
|---|---|
| `_sheet_part_map` 调用 | **549** 次 |
| 其中**有文件身份**的真解析 | `xl/workbook.xml` **3** 次 + Table 清册 **3** 次 = 6（段内 3 个字节形态：substrate / 转置写入前的中间产物 / 最终产物，每形态各一次 ⇒ 已是下界） |
| 其中 **BytesIO**（无身份，退化成不记忆化） | `xl/workbook.xml` **39** 次（= binding 数，单趟计划阶段每 binding 在内存 zip 上读一次 sheet part 映射）；贵的 `parse_tables` 在那条路径上 **0** 次 |
| `sharedStrings` 前缀 digest | 调用 117 次 → 真算 ≤4 次（键含 `limit_count`：before 侧 `None` / after 侧一个具体数） |

### F.4 实测：需求 1.5 的最终判定 —— **达成**

同一轮 `--segment --mode both --repeat 3`（两条路径交错、每轮前清结构指纹缓存）：

| 口径 | 任务 7（改动前）median | 任务 8（本次）median / max | ≤10s |
|---|---|---|---|
| `adapter.materialize` | 17.127（链式）→ 5.490（单趟） | **4.651 / 4.876** | ✅ |
| CPU 段合计 | 24.791（链式）→ **12.800 / 12.876** | **7.463 / 7.470** | ✅ **达成（连最慢轮）** |

逐段对照（单趟侧 median，任务 7 → 任务 8）：

| 段 | 任务 7 | 任务 8 | 差 |
|---|---|---|---|
| materialize | 5.490 | 4.651 | −0.839（计划阶段 156 次 `_sheet_part_map` 塌成 1 次真解析） |
| extract | 2.747 | 1.461 | −1.286 |
| roundtrip_verify | 0.001 | 0.001 | 0 |
| unmanaged_verify | 2.113 | 0.208 | **−1.905**（sharedStrings digest 117 → ≤4） |
| structure_hash | 2.408 | 0.991 | −1.417（转置 4 次解析 → 0 次新解析） |
| **合计** | **12.800** | **7.463** | **−5.337** |

任务 7 说「还差 2.8s、归任务 8」—— 实交 **5.34s**，余量 2.5s。

⚠️ 口径提醒一字不改：CPU 段合计**不是**端到端。`stage_stream`/`publish_*` 的 IO、DB 单事务、
HTTP/OO 握手、前端加载态都在段外；真实端到端数字仍**未取到**（同附录 E.1 的理由，
登记为待拍板），不拿 7.463s 冒充端到端。

同轮里**链式回落**路径也跟着降（20.383 median，其中 materialize 17.739 / 尾段 2.6）——
④的记忆化对两条路径都生效。因此本证据的 `chained` 一列**不是**改动前的基线（那份在
`task7-segment-before-after.json` 里），只是同一轮的同机参照；「≤10s」的判定只读 `default`
一侧，不依赖 `chained`。

### F.5 复用解析 ≠ 复用结论（需求 2.3 的前提，实测四面全等）

同一个 world / 同一份 projection 把整段跑两遍（开复用 / `reuse_disabled()` 关复用），
四个面逐项相同：

| 面 | 结果 |
|---|---|
| extract projection | `repr` 口径全字段比对（与附录 B.2 同一套 helper）⇒ **0 差异** |
| verify 的**逐 binding** 结论 | 39 条逐一相同（`assert_equivalent` 换成收集器让循环跑完，同 E.2 纪律） |
| `structure_hash` | 逐字符相同 —— 它是对共享对象最敏感的那个消费方（读 `ws._cells` 成员关系） |
| 产物字节 | 逐 zip entry 内容全同（`date_time` 分流，同 B.3 口径） |

另有三条结构判据守着「共享对象不得被改」：①同一张受管 sheet 在 4 次共享调用之间的
`_cells` 键集合摘要逐次相同；②段末（最后一个消费方之后）再取一次仍相同（覆盖「最后一个
消费方改了」那个前 4 次盖不到的窗口）；③记忆化的 `sheets`/`tables` 与段末一次干净解析
逐字相等。

design 六 第 3 条（不合并 extract/verify）也做成了判据：生产 CPU 段里两句调用都在、
`unmanaged.assert_equivalent()` 仍被调用、`verify_unmanaged_regions` 的形参里没有 extract
的产物（它自己从字节重算，不接受别人递过来的结论）。

### F.6 承重反证（非空转）

`reuse_disabled()` 把 `share_parse` 一律掐成 `False`（不改判据、不改调用点、不改 adapter）：
产物字节上 8 个消费方**真的**各解析一遍、整段 `load_workbook` 回到 **19**、逐调用点清册与
任务 7 附录 E.3 逐项相同。⇒ 主判据的「8 → 1」不是空转。

`fresh`（这次调用有没有真解析）不靠数行号统计：直接看调用前后作用域缓存的键数有没有增长。

### F.7 登记在案、**本任务不做**的剩余杠杆（按实测大小排序）

诚实列清，避免下游把「没做」读成「不存在」：

1. **`adapter.materialize` 仍占 4.651s / 7.463s 的 62%** —— 那是任务 3 的地盘（链式 17.7s →
   单趟 4.7s 已 3.8×），本任务未动其写入逻辑。
2. **产物字节上还有 2 次不可共享的完整 DOM 解析**（`_structure_fingerprint_uncached` +
   `_read_gt_sync_pairs`，实测合计 ~1.3s 真实耗时）。要收掉它们得先把这两处也改成非惰性
   取格（`iter_rows()` → `ws._cells` 直读），那是对 `excel_structure_fingerprint` 这个
   **高扇入**模块的读取语义改动（`identity_inventory` 全仓在用），风险面与收益不匹配 ⇒
   独立改动，待拍板。判据已把「恰 2 个、各自列名」钉住，第三个出现即红。
3. **单趟计划阶段 39 次 BytesIO 上的 `xl/workbook.xml` 解析**（每 binding 一次）。那种 zip
   拿不到文件身份 ⇒ 记忆化不覆盖。只涉及便宜的那一半（读 `workbook.xml` + rels，~2ms），
   实测合计 ~80ms，且贵的 `parse_tables` 一次都没被调 ⇒ 性价比低。要收得在
   `excel_materialize` 侧按字节摘要给它一个身份。
4. **`unmanaged_region_digest` 的逐 binding 其余部件 digest**（117 次调用里 sharedStrings
   之外的部分）。它们随 `region.sheet_part` 变，不是同一份入参，不属本条的「同一份字节读
   多遍」，要优化得改比对口径（那会动 verify 的**判据面**，需求 2.3 明令不放宽）⇒ 不做。

### F.8 顺手给任务 9 的两条实测（登记，不在本任务修）

1. **`collect_workbook_structure` 里那次 `extract_transposed_workbook` 的返回值被丢掉**
   —— 它在那里纯粹是个 fail-closed **校验器**（只靠抛异常起作用）。因此「转置 sheet 少一个
   字段」在生产里是被**结构漂移**（`assert_no_structure_drift` / `ws._cells` 成员关系）抓住的，
   **不是**被 `verify_unmanaged_regions` 抓住的。任务 9 设计 P5 的变异反证输入时要区分这两条
   路径，否则会在一个本来不该由 verify 负责的面上找反证（这与附录 B.4 末段的提醒同源）。
2. **harness world 上 verify 的 39 条结论与复用开关无关**：开/关复用两侧逐 binding 全等，
   首个差异恒为 `workbook_and_styles`（= 附录 E.2 说的「模板 → 第一代产物」效应，
   steady-state 探针实测 39/39 等价）。所以任务 9 若在 harness world 上做变异反证，
   分母要用 steady-state substrate，否则「必红」这件事在首代 world 上本来就红。

### F.9 A/B 差分（证明本任务没引入新失败）

`tests/workpaper_sync/` 有约 291 条与本 spec 无关的既存失败（任务 3 已用 A/B 差分实测），
所以「这次跑出来多少失败」本身说明不了任何事。本任务用**运行时开关**做同一份代码的 A/B：
一次性 pytest 插件在 `pytest_configure` 里把本任务改的三件事整体关掉，同一条命令跑两遍，
失败集合相减。这样比「`git stash` 再跑」更干净：stash 会把任务 3~7 的改动一起摘掉，差出来的
就不是本任务的账。

插件的全部内容（一次性，用完即删；要复现照抄即可）：

```python
def pytest_configure(config):
    from app.services.workpaper_sync import excel_extract as EE
    from app.services.workpaper_sync import phase5_transposed_sheet as PT
    _resolve = PT.resolve_managed_sheet                       # ② share_parse
    PT.resolve_managed_sheet = lambda b, *, spec, share_parse=False: _resolve(
        b, spec=spec, share_parse=False)
    EE.scoped_parse_memo = lambda kind, identity, compute: compute()   # ④ 记忆化
    PT._cell_ro = lambda ws, row, col: ws.cell(row, col)              # ③ 非惰性读格
```

```powershell
# backend cwd，两侧只差一个 -p
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync -p no:randomly -q --tb=no -rf
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync -p no:randomly -q --tb=no -rf `
    -p tests.workpaper_sync._task8_reuse_off_plugin
```

| 侧 | 结果 |
|---|---|
| **开复用**（本任务的代码） | **291 failed / 8168 passed / 2 skipped / 16 xfailed / 6 errors**（33:10） |
| **关复用**（运行时掐掉三件事） | **296 failed / 8163 passed / 2 skipped / 16 xfailed / 6 errors**（34:35） |
| 只在「开」侧失败 | **0 条** ⇒ 本任务**没有引入任何新失败** |
| 只在「关」侧失败 | **恰 5 条**，全是本任务的解析复用判据 ⇒ 判据**承重**（关掉就红），不是空转 |

只在「关」侧失败的 5 条：`test_cpu_segment_parses_the_artifact_bytes_once_per_view` /
`test_segment_load_workbook_total_drops_by_the_shared_parses` /
`test_repeated_zip_xml_parses_collapse_to_one_per_file` /
`test_the_memoised_parse_results_were_never_mutated_in_place` /
`test_parse_memo_entries_share_the_workbook_scope_without_being_closed_as_workbooks`。

两侧的 6 个 error 与 291 条失败**逐条同名** ⇒ 全是既存问题。ON 侧失败清单里
**没有任何**属于 `test_single_pass_*` / 转置 / observer / `excel_extract` / 静态受管区 /
D4-29 / D4-12 的条目 —— 直接受影响的那几套全绿。

`tests/workpaper_sync/` 之外还有两个文件会碰到本任务改的模块，单独跑过
（`tests/test_d4_29_customer_detail_sync.py` + `tests/test_structure_fingerprint_memoization.py`
= 34 passed / 1 failed）。那 1 条失败是
`test_production_adapter_dispatch::AttributeError: 'Host' object has no attribute
'_materialize_within_scope'` —— **任务 3 遗留**（它引入了 `_materialize_within_scope`，而这条
判据用的 `Host` duck-type 桩没有这个方法），开/关复用两侧**同样失败** ⇒ 与本任务无关，
登记给任务 3 的收尾。

---

## 附录 G：verify 判据不放宽（任务 9 · P5 · 2026-09-22 真库实测）

判据落 `backend/tests/workpaper_sync/test_single_pass_verify_not_relaxed.py`（25 条）。world
仍来自 `d4_materialize_harness.build_world`，**但分母换成 steady state**（见 G.2）——
harness 新增 `rebased_world()` 一个函数承担它（纯增量，既有 5 个判据文件 98 条全绿）。
**生产代码本次零改动**（G.6 的三次定向变异是「改 → 跑 → 按 sha256 复原」，两份文件复原后
逐字节等于改前）。

**一句话结论**：需求 2.3 **无需改措辞**（这是本 spec 里第一条经实测毫发无损的验收标准）；
要收紧的是 design 五 P5 的**反证方式** —— 「产物少一个字段」必须在**产物字节**上做，
「漏写一个 binding」在自反读 projection 上**不产生**缺陷产物。

### G.1 verify 不是一道门，是五道 —— 各自的比较面（先测清再变异）

| 门 | 实现 | 比较面（真库 D4 实测） | 在生产哪条链上 |
|---|---|---|---|
| **G1** 反读等值 | `ContentMutationService._assert_roundtrip_equivalent` | 受管 key 去掉 `word_only` + `PROTECTED_MODES` ⇒ **166**（218 − 52 个 `formula`），逐 key `merge.values_equal` | CPU 段第 3 步（**需求 2.3 指名的那道**） |
| **G2** 反读等值（另一份实现） | `excel_extract.verify_roundtrip_equivalence` | 只含 `mode=editable` ⇒ 实测同为 **166** | `verify_before_commit`（OO→HTML） |
| **G3** 受保护公式区 | `excel_extract.verify_formula_regions` | G1/G2 排除的那 **52** 个 `formula` 格归它 | 同上 |
| **G4** 未管理区域 | `adapters/excel.verify_unmanaged_regions` → `excel_extract.verify_unmanaged_regions` × 39 binding + `assert_equivalent()` | 8 个 aspect 的逐 part digest；每 binding 覆盖 **132** 个 part（`shared_strings_prefix` 1233 项 / `managed_sheet_unmanaged_cells` 225 项 / `relationships` 35 项 …） | CPU 段第 4 步 |
| **G5** 发布时刻结构身份 | `publish_time_structure_hash.compute_structure_hash_from_artifact` → `collect_workbook_structure` + `assert_no_structure_drift` | **775** 条受管结构坐标（含转置 sheet 字段格存在性，按 `ws._cells` 成员关系判） | CPU 段第 5 步 |

**需求 2.3 是关于哪道门的**：条文「反读等值仍须逐字段比对」指名 **G1**。但任务 8 的解析
共享真正碰到的是 **G4 + G5**（`share_parse=True` 的两个调用点就在它们身上），G1 只经由
`adapter.extract` 的两个 `read_only` 视图间接受影响。⇒ 本任务三道门全测，不只测被点名那道。

🔴 **实测：三道门两两不重叠，每道门对另两类缺陷一定是绿的**（G.3 的归因表）。所以需求 2.3
的「verify 必红」要读成「verify **这一段**失败、发布被拦住」，由**拥有那类缺陷**的门负责；
其余门保持绿是分工正确，不是盲区。判据把这张表逐格钉住 —— 哪天某类缺陷变成「一个门都不红」，
对应那条会红。

### G.2 分母：steady-state substrate 是 materialize 的**不动点**

附录 F.8 第 2 条要求「变异反证的分母要用 steady state」。本任务实测了它成立的强形式：

| world | G1 | G4 | G5 | 说明 |
|---|---|---|---|---|
| 第一代（instrumented **模板** substrate） | 绿 | **红 39/39**，首个差异恒 `workbook_and_styles` | 绿 | 附录 E.2 的「模板 → 第一代产物」效应，**不能**当分母 |
| **第二代 = steady state**（第一代产物当 substrate） | 绿 | **绿 39/39** | 绿（hash `972c3404…`） | 分母 |

并且：steady-state 产物与其 substrate **逐 zip entry 内容全同**（142/142，字节数同为
246110，`date_time` 分流，同 B.3 口径）⇒ **materialize 在 steady state 上是不动点**。
生产 substrate 恒是上一次发布的产物，所以这才是生产的形态。两条判据把分母钉住：
第一代**必须**是红的（`test_the_first_generation_world_cannot_be_the_denominator`）、
第二代**必须**三门全绿且是不动点（`..._is_a_fixed_point_and_every_gate_is_green`）。

### G.3 变异反证：产物**真的**缺东西 ⇒ 必红（四类缺陷 × 三道门的完整归因表）

变异只改**产物字节**（抹掉恰好一个 `<c>` 元素），不改生产代码、不改 projection、不改契约。
靶点从**生产计划**（`_plan_materialize_step` 的 `plan.writes`）与真实产物里取，不写死坐标。

| 变异（抹掉一个 `<c>`） | extract | **G1** | **G4** | **G5** |
|---|---|---|---|---|
| 受管 `editable` 格（`sheet7!A13`） | 218 → **217** | **红** | 绿 | 绿 |
| 行身份载体格（`sheet7!O13`，隐藏 UUID 列） | 218（该行被重铸 `GTROW-MINTED-…`） | **红** | 绿 | 绿 |
| 非受管 sheet 的格（`sheet1!A1`） | 218 | 绿 | **红 39/39** | 绿 |
| 转置 sheet 的字段格（`sheet37!C11`） | 218 | 绿 | 绿 | **红** |

**真实失败输出**（判据断言里逐条点名，不只断「红了」）：

```
# 受管 editable 格被抹掉 —— 这就是需求 2.3 字面要的那条反证
RoundtripEquivalenceError: staged representation 反读后缺少受管字段
  ['other_revenue_detail_rows/GTROW-D43-0013/item']（共 1 个）——
  materialize 没有把它们写进 OOXML，或 extract 找不到 identity 载体

# 非受管 sheet 的格被抹掉
other_sheet_parts: 5f4fb6a47705… → 0f7893ec3427…（before 覆盖 11 项，after 覆盖 11 项）

# 转置字段格被抹掉（= 附录 F.8 第 1 条预言的那条路径）
ContractDriftError: contract d4.revenue_detail: 结构漂移，首个不一致位置
  sheet='d4-29-managed' table='customer_detail_transposed'
  field='customer_detail_transposed/{row_uuid}/creditcode' locator='C:row_identity'
```

两条与既有认识吻合、刻意做成判据留痕：

1. **转置字段缺失归 G5，不归 verify**（附录 F.8 第 1 条）：`collect_workbook_structure` 里
   那次 `extract_transposed_workbook` 的返回值被丢掉（纯 fail-closed 校验器），抹掉 anchor
   字段格只是让它从 `transposed[key]` 里消失 ⇒ `assert_no_structure_drift` 抓。**不把这条
   红记到 verify 的账上**；哪天有人「优化」掉 `assert_no_structure_drift`，这类缺陷就没有
   任何门看得见 —— 判据 `..._is_caught_by_structure_drift_not_by_verify` 就是那天的告警。
2. **G4 对受管区域内的缺失是绿的**，这是**对的**（受管区按定义排除在未管理区域比对之外，
   否则每次合法写入都判漂移）；`<dimension>` 之内「格子不存在」与「格子为空」同构，所以
   `managed_sheet_structure` 也不变。

### G.4 🔴 为什么「漏写一个 binding」**不是** P5 的反证（design 五 P5 措辞收紧）

附录 B.4 末段提醒过这一条，本任务量到了底。在 steady state 上按 design 五 P5 的字面做法
（漏写某个 binding 的**全部**写入）实测：

| 受害 binding | 产物 vs 正确产物 | G1 | G4 | G5 |
|---|---|---|---|---|
| `d4_10_rows`（49 处写入） | **逐 zip entry 内容全同**（142/142，字节数同为 246110） | 绿 | 绿 | 绿 |
| `d4_32_groups`（34 处写入） | **逐 zip entry 内容全同** | 绿 | 绿 | 绿 |

**这不是盲区，是产物根本没有缺陷**：不动点上每处写入都是把「已经在那儿、形态也一样」的值
再写一遍（恒等覆盖）⇒ 不写 == 写。连任务 4 那条字节判据（B.4 里唯一抓到 `d4_10_rows` 的
判据）在 steady state 上也是绿的 —— 它在**第一代** substrate 上抓得到，是因为那里漏写会
改变单元格的**表示形态**（inline string vs shared string / 数字格式）。两半合起来：

> 「漏写一个 binding」是**计划层**的省略。在自反读 projection 上，它在第一代产物上只改变
> 表示形态（⇒ 只有字节判据看得见，反读判据天生盲），在 steady state 上**什么都不改变**
> （⇒ 任何判据都看不见，因为没有东西可看）。P5 要的「产物少一个字段」必须是**产物层**的
> 缺陷 —— 只能靠对产物字节做变异得到。

**落地**（处理方式同 A.7 / F.1：收紧措辞，不放宽保证）：

| 落点 | 内容 |
|---|---|
| design 五 P5「反证方式」 | 改为「**产物字节**上抹掉一个受管格（产物真的少一字段）⇒ 拥有该缺陷类的那道门必红」，并明写「**不是**漏写一个 binding」 |
| `requirements.md` 需求 2.3 | **一字未改** —— 它写的是「故意让产物少一个字段，verify 必须红」，实测**字面成立**（218 → 217，G1 报缺失并点名那个 key）。这是本 spec 里第一条经实测毫发无损的验收标准（对比 1.1 / 1.2 / 2.1 都被收紧过） |

判据没有放宽：G.3 那四条比原措辞**更严**（要求点名缺的那个 stable key / 那个 aspect /
那个 sheet，且要求「别的门恰好是绿的」）。「漏写之后产物逐字节相同」这条实测本身也做成了
判据（`..._produces_a_byte_identical_artifact`）—— 它哪天红了说明不动点前提变了，届时本节
的叙述要一起改，而不是让一个已不成立的实测继续挂在结论上。

### G.5 任务 8 的解析共享**没有**削掉任何一寸判据面（比较面逐项对账）

任务 8 已断「开/关复用**结论**相同」（附录 F.5）。本任务往前一步断**面本身** —— 理由是
「结论相同」对**削面**这类改动天生免疫：面窄了两侧会一起变绿，差分看不出来。

| 面 | 怎么量 | 开复用 | 关复用（`reuse_disabled()`） |
|---|---|---|---|
| G1 比了哪些值 | 拦 `content_mutation.values_equal`，记 `(value_type, repr(左), repr(右))` 多重集 | **166** | 166，**逐项相同** |
| G4 看了多少东西 | 拦 `excel_extract.unmanaged_region_digest`，记 `(sheet_part, aspect 名单, 每 aspect 覆盖项数, part_count)` —— 刻意**不记 digest 值**（那是结论） | **78** 次（39 × before/after） | 78 次，**逐项相同** |
| G5 观测了哪些坐标 | 直接调 `collect_workbook_structure` 取 `structure` 元组集合 | **775** 条 | 775 条，**逐项相同** |

G1 的面另外用**三条互不依赖**的路子交叉验证，三个数必须相等（判据
`..._surface_is_the_editable_field_set_measured_three_ways`）：

1. G1 实际拿去比的值对数 = **166**；
2. intended projection 里 `mode=editable` 的字段数 = **166**（按 `FieldValue.mode` 数，
   不复述门的排除逻辑）；
3. G2 报出的 `compared_keys` 数 = **166**（**另一份实现**的「editable 面」）。

只钉一个常数的话三处一起改的重构照样绿；只钉「两侧相同」的话两侧一起削窄照样绿。另断分工：
被排除的 **52** 个全是 `PROTECTED_MODES`（实测全为 `formula`），归 G3 管；`editable ∪ protected`
必须等于全部 218 个 key —— 出现第三类 mode 就意味着它落在**任何门之外**，判据直接红。

#### 🔴 实测发现：`inspected_aspects` 是硬编码的 ⇒ 覆盖面判据看不见「比对循环跳过 aspect」

`UnmanagedRegionReport.inspected_aspects` 在 `verify_unmanaged_regions` 的两个 return 里都
被填成常量 `UNMANAGED_ASPECTS`。于是有人在比对循环里加一句
`if aspect == "other_sheet_parts": continue`，报告照样声称检查了全部 8 项、结论照样
`equivalent=True`，而上面那张覆盖面表**一点变化都没有**（它记的是 digest 的**采集**面，
不是**比对**面）。G.6 的第二次定向变异实测证实了这个缺口：三条判据红，但
`..._changes_no_comparison_surface` **是绿的**。

⇒ 本任务补一条 **AST 判据**（`..._skips_no_aspect`）：遍历 `UNMANAGED_ASPECTS` 的那个 `for`
必须「只有一条 `if`、判据是两侧按同一 aspect 下标取值后 `!=`、循环体内没有 `continue` /
`break`」。检查器自带反证（一份人为写了 `continue` 的源码必须被它报出来），纪律同附录 D.3
的 AST 检查器。**未改生产代码** —— 把 `inspected_aspects` 改成「实际比过的 aspect」是更根本
的修法（报告就不会再撒谎），但那会动 `UnmanagedRegionReport` 的公开语义与全部调用方 ⇒
**独立改动，待拍板**（处理方式同 C.4 / F.7）。

### G.6 承重反证：三次定向变异生产代码（改 → 跑判据 → 按 sha256 复原）

留着判据全绿只说明「没坏」。三次变异各证一组判据**承重**（两份文件改前/复原后 sha256 逐位
相同：`content_mutation.py` `1C7E91C7…`、`excel_extract.py` `B16F5F53…`）：

| # | 变异（生产代码） | 红了哪些判据 | 绿的那些说明什么 |
|---|---|---|---|
| V1 | G1 改成**只比两侧交集**（`left` 取交集 + `extra` 恒空）—— 即「别对 key 集合较真」这种放宽 | `..._turns_the_roundtrip_gate_red`（受管格）/ `..._row_identity_carrier...` / `..._invisible_to_the_other_two_gates` / `..._verdict_is_recomputed...` 共 **4 条** | 主判据不是空转：G1 一放宽，「产物少一字段」立刻无人看见 |
| V2 | G4 比对循环加 `if aspect == "other_sheet_parts": continue` | `..._skips_no_aspect`（AST）/ `..._unmanaged_drift_is_caught_only_by...` / `..._unmanaged_verdict_is_recomputed...` 共 **3 条** | 🔴 `..._changes_no_comparison_surface` **绿** ⇒ 覆盖面判据看不见比对循环被削（G.5 的发现），AST 那条是唯一看得见的 |
| V3 | 给 G1 加一个按 `contract_id` 记忆的**结论**缓存（`if 已验过: return`） | `..._verdict_is_recomputed_for_every_artifact_in_one_scope` / `..._surface_is_the_editable_field_set...`（比较面掉到 0 对） 共 **2 条** | 🔴 `..._turns_the_roundtrip_gate_red` **绿**（它是该 fixture 里第一次调用，缓存还空）⇒ 「缓存结论」这一类**必须**由同作用域「好 → 坏 → 好」序列那条判据抓，单点反证抓不到 |

V3 的那一格正是需求 2.3 「复用解析结果不等于复用**结论**」的判据缺口所在，本任务为它单立
三条：同作用域内 G1 结论必须 绿→红→绿、G4 必须 0→39→0、G4 的 before 侧 LRU 必须**内容
寻址**（AST 确认 `before_sha` 真的进了键 + 同一路径换内容后结论必须翻），另加一条结构判据
「五道门都不得被 `functools` 记忆化（不得有 `cache_info` / `cache_clear`）」。

### G.7 登记在案、**本任务不做**的

1. **`UnmanagedRegionReport.inspected_aspects` 改成实际比过的 aspect**（G.5 的根本修法）——
   动公开语义与全部调用方，独立改动，待拍板。当前由 AST 判据兜住。
2. **G3（`verify_formula_regions`）没有做变异反证**：它只在 OO→HTML 的 `verify_before_commit`
   链上跑，本 spec 的 CPU 段压根不调它（52 个 `formula` 字段在 html→oo 方向由 materialize
   写缓存值、不由它把门）。诚实列清：本任务只证了「G1/G2 排除那 52 个是有意的、且它们归 G3」，
   **没有**证「G3 真的抓得到公式篡改」—— 那是 Task 37/38 判据的地盘。
3. **端到端（含发布/DB/HTTP）没有测**：本任务与附录 E.1 / F.4 同口径，只量 CPU 段那三道门。
4. **`_file_sha256_cached` 的键是 `(路径, mtime_ns, size)`**：sha 本身是字节的纯函数，唯一
   误命中窗口是「同路径 + 同 mtime_ns + 同 size + 不同字节」，普通写入不可达（判据实测重写
   同一路径后结论确实翻了）。要彻底关掉这个窗口得改成每次重算，与 ROI-4 的目的冲突 ⇒ 不做。

---

## 附录 H：复用可观测（任务 10 · P6 · 2026-09-22 真库实测）

判据落 `backend/tests/workpaper_sync/test_materialize_reuse_observability.py`（51 条）+
`test_task25_materialize_coordinator_pg.py` 新增阶段 8e 与 2 条断言（真 PG，53 条全绿）。
CI 门 `backend/scripts/check/check_materialize_reuse_digest_caliber.py`（4 段），
workflow job `materialize-reuse-digest-caliber`。

**一句话结论**：复用判定已是机器可读的四值封闭域 + 落进既有 `workpaper_sync_*` 目录；
「连续两次必命中」在**两个层**上各有一条真链（CPU 段 + PG coordinator），两条在 digest 口径
退化下**同时变红**；单趟 decline 与复用未命中**保持两个维度**。requirements 3.2 / 3.3 各收紧
一处措辞（H.1 / H.6），需求 3.1 与 design 五 P6 **一字未改** —— P6 是本 spec 里第二条经实测
毫发无损的判据（第一条是 2.3）。

### H.1 复用实现在哪、与任务 8/9 的「复用」不是一回事

| 项 | 位置（实测确认，不是按 requirements 的说法照抄） |
|---|---|
| 业务身份复用判定 | `materialize_coordinator.MaterializeCoordinator._find_business_identity_reuse`（约 2871 行）—— 与 requirements 背景所述一致 |
| digest 的值表示口径 | `projection_digest_value.canonical_value_for_digest`（唯一实现，被 `content_mutation._projection_payload` 逐字段调用） |
| digest 计算 | `content_mutation.projection_canonical_digest` / `_canonical_projection_bytes`（coordinator 与 commit 共用同一份，模块文档 §五已锁） |
| 判定的两条腿 | 腿①`WorkpaperContentVersion.projection_sha256 == token.payload_sha256`；腿②当前 published representation 是否挂在那个 content version 上（bundle digest 是该行上的冻结列，所以腿②同时固定 substrate 与 bundle） |

**两个「复用」必须分开说**（本 spec 内最容易串的一处）：

* 任务 8/9 的复用 = `workbook_read_scope()` 的**解析**复用（一次 CPU 段内同一份字节只解析
  一次）。它在 materialize **内部**，与「要不要 materialize」无关。实测收益 12.8s → 7.5s。
* 本任务的复用 = **业务身份**复用（内容一字未改 ⇒ 根本不 materialize）。实测收益
  store-projection 首请求 32325ms → 114.9ms、切 OO D4-6 31508ms → 2111ms。

⇒ 两者的判据面、失败模式、指标都不共用。本任务不碰前者一个字。

#### requirements 3.2 措辞收紧（已落地）

原文只写「同一 projection 连续两次 materialize」。**实测证明这个措辞已经被满足过、而缺陷
仍然存活**：`test_task25_materialize_coordinator_pg.py` 阶段 8b 就是一条「不同 token、相同
业务身份 ⇒ 复用」的真 PG 链，它在缺陷存活期间一直全绿 —— 因为两侧都经
`_projection(period, total)` 把金额强转成同一个 `Decimal`，digest 必然相等。

真栈缺陷发生在两条**派生路径之间**：HTML store 走 JSON（裸 int/float）、Excel extract 走
openpyxl（int/float/bool）、merge 与审定回写走 `Decimal`。所以「同一 projection」必须读作
「同一份业务内容的**两次独立派生**」，并且判据要**显式断言两侧派生互不相同**（否则守卫在
「同一对象」这条退化输入上恒真）。已同步改 `requirements.md` 3.2，处理方式同 A.7 / F.1。

**不放宽任何既有保证**：这是把一条可以被空转满足的措辞换成可判定的结构事实，并新增一条
反空转义务。

### H.2 🔴 实测发现：真库 D4 上**今天**就有 4 个字段在两条派生路径上表示不同

这是本任务量到的新事实，也是这条链「真的是两条派生路径」的最硬证据。

链条：模板 substrate ──extract①──> projection A ──materialize①──> 产物 gen1 ──extract②──>
projection B。A 是「已提交」那侧，B 是「下一次 flush 会算 digest」那侧。

| 量 | 实测 |
|---|---|
| 两侧字段数 | 218 / 218 |
| `repr` 口径逐字段比对（任务 4 的 `projection_differences`，最严那套） | **4 处不同** |
| 业务比较面（表示无关）差异 | **0** |
| canonical payload 字节 | **逐字节相同** |
| projection digest | **相同**（`eff46616…`）⇒ 第二次命中复用 |
| 第三代（gen2 字节当 substrate）再反读 | digest 仍是 `eff46616…` ⇒ 不动点 |

那 4 处（`value_type=boolean`，一侧 `int:1`、另一侧 `bool:True`，`==` 相等）：

```
undisclosed_rp_rows/GTROW-D427-0015/is_customer_legal
undisclosed_rp_rows/GTROW-D427-0015/is_production_dept
undisclosed_rp_rows/GTROW-D427-0016/is_finance_dept
undisclosed_rp_rows/GTROW-D427-0016/is_personal_customer
```

成因与真栈那条 `0` vs `0.0` **同构**：instrumented 模板里这些格是数字字面量，openpyxl 反读成
`int 1`；materialize 按 `boolean_literal` 写进产物后再反读成 `bool True`。

**三条后果，都已落成判据**：

1. **`canonical_value_for_digest` 在 D4 上今天就在承重**，不是为将来准备的：哪怕一个金额零都
   不参与，光这 4 个 boolean 就足以让业务身份复用恒不命中。判据
   `test_the_boolean_fields_alone_are_enough_to_break_reuse` 只把这 4 个字段退回旧口径、其余
   全用新口径，digest 仍然分叉。
2. **既有值级判据漏了这个折叠方向**：`test_projection_digest_is_representation_stable.py` 对
   boolean 只测了**反向**（`True` 不得折成数字 `1`，即 `test_boolean_is_not_folded_into_numbers`），
   `boolean` 的 `1 → True` 这一折叠从来没有判据。已补进 CI 门第 ① 段的等价矩阵
   （`(boolean, 1, True)` / `(boolean, 0, False)`）。
3. **本任务的主判据措辞按实测写**：原本想断「两侧连表示都一样」，实测不成立 ⇒ 判据改成
   「差异恰是这 4 个、形态恰是 `int → bool`、且 payload 把它们折成同一个 JSON `true`」。
   多一处、少一处、或形态变了都会红 —— 这比「差异为空」更严，也不是假设。

### H.3 未命中原因四类：各自怎么被**区分**（requirements 3.3）

判词住 `app/services/workpaper_sync/materialize_reuse_verdict.py`（纯函数、零 IO）。
`ReuseVerdict(decision, miss_reason, differences, compared_field_count)`，其中
`decision ∈ {hit, replayed, miss}`、`miss_reason` 与 `decision` 由 `__post_init__` **互相约束**
（miss 缺原因要抛、hit/replayed 带原因也要抛）⇒「未命中但说不出为什么」在**构造上**不可表达。

| # | 原因 | 判别依据（机器可判，不是人工归类） | 是缺陷 |
|---|---|---|---|
| 1 | `content_changed` | 腿①未命中 + 业务比较面报 `values` / `row_keys` 差异 | 否 |
| 2 | `contract_or_bundle_changed` | 腿①未命中 + 业务比较面报 `contract_id`/`semantic_version`/`document_type` 差异；**或**腿①命中而腿②未命中（substrate/bundle 身份前进） | 否 |
| 3 | `digest_representation_drift` | 腿①未命中 + 业务比较面报 **0** 差异 | 🔴 **是** |
| 4 | `no_base_projection` | 基线侧读不到 projection 载荷（`projection_artifact_id` 为 NULL / artifact 缺失 / 载荷不是 JSON 对象） | 否 |

展平成一维 `result` 标签（`hit` / `replayed` / `miss_<reason>`，共 6 格）：既有 `SyncMetrics`
只认一个 `result` 标签，不认「结果 + 子原因」两层。`ReuseVerdict.metric_result` 是唯一构造处。

#### 🔴 第 3 类可达的前提：业务比较面**刻意**独立于 digest 口径

这是整个分型里唯一一个非平凡的设计决定。第 3 类要回答的是「digest 说不一样，业务内容到底
一样不一样」。若比较面复用 `canonical_value_for_digest`，答案就是同一条口径的**自证** ——
口径分叉时两侧 payload 本来就不同 ⇒ 分类器只会说 `content_changed`，第 3 类**永远不可达**，
requirements 3.3 那条验收标准退化成空话。

所以 `compare_projection_payloads` 用一套**表示无关**的业务相等
（`business_value_equal`：数值族一律 `Decimal(str(x))` 比值、`None` 只与 `None` 相等、
其余 `==`），并且**只**用于给未命中归因，**从不**参与「要不要复用」的裁决（那条永远只由
`projection_sha256` 的字节相等决定）。

这与附录 B.2「为什么不复用现成 helper」是同一条纪律、方向相反：那边拒绝用宽口径当**等值**
判据，这边拒绝用窄口径当**差异**判据。两侧各有反向锁：
`TestBusinessComparisonIsIndependentOfTheDigestCaliber` 的 5 条正向（表示差异必须判等）
+ 7 条反向（语义差异必须判不等）—— 少了反向锁，`business_value_equal` 可以恒 `True`，
于是**每一次**未命中都被报成缺陷，那比看不见缺陷更坏。

#### 归因的成本（诚实列清）

未命中路径上多付**一次** `SELECT count(*)`（腿①复查）+ 一次 projection 载荷读盘
（~120KB JSON）。它只在未命中时发生，而那条路径紧接着就是整趟物化（真库 D4 实测 CPU 段
7.5s）⇒ 相对成本可忽略。**命中路径一个字节都不多读。**
归因只在 `_open_operation` **之前**做（同 session、其间零写入 ⇒ 两条腿复查结果与探测逐字相同），
AST 判据 `test_the_verdict_is_computed_before_the_operation_is_opened` 把这个顺序钉住。

### H.4 落进哪个 metrics 家族、怎么登记（requirements 3.1）

家族 = `app/services/workpaper_sync/metrics.py`：`METRIC_CATALOG`（唯一指标词汇表）+
`SyncMetrics`（唯一记数入口，`result`/`landed` 无默认值）+ `sync_metrics` 生产单例，
并与 `alerting.py` 的规则表**双向锁死**。生产 emit 的惯例是**全在 router 里**
（`wp_sync_router.py` 已有 13 处），本任务照此办理，不另起机制。

登记的两条（都过了 `validate_catalog()` 与 `validate_registry()` 自检，目录从 32 → **34** 条）：

| 指标 | kind | 归因等级 | result 域 |
|---|---|---|---|
| `workpaper_sync_materialize_reuse_total` | counter | `platform_scoped` | 6 格（H.3） |
| `workpaper_sync_single_pass_decline_total` | counter | `platform_scoped` | 6 格（H.5） |

**归因等级为什么是 `platform_scoped`（project + wp，emit 侧再补 entry）**：复用判定是**内容
身份**事实 —— 它只取决于 `(projection digest, bundle, substrate)`，与「谁在问」「哪个 room」
无关；materialize 那一刻 room/participant 甚至可能还不存在（复用命中时复用的正是既有 room）。
按 `room_scoped` 记就必须填 participant，而那与本家族 route 级指标 docstring 里写的
「此时填 participant 就是编造」同构。先例：`workpaper_sync_bundle_candidate_finalize_total`
（同样是 representation / content version 层的事，也是 `_PLAT`）。

**`alert_required` 都是 `False`**，理由是两条而不是省事：①`AlertCondition` 是**封闭**枚举且
明文对应「Requirement 13.9 逐条点名的状况」，为另一个 spec 的需求往里加成员会污染那份一一
对应；②requirements 3.3 要的是**CI 判红**，不是运行时告警 —— 告警面归属另一个 spec 的 13.9，
本任务不越界。缺陷类的运行时可见性由「独立指标桶 + ERROR 日志」承担（H.6）。

判据（`TestTheVerdictIsMachineReadableAndRegistered`，10 条）覆盖：
`MaterializeOutcome.reuse_verdict` 字段存在且**无默认值** / 4 处构造点逐一传值（AST）/
归因顺序（AST）/ 两条指标在目录里且封闭域与判词模块逐项一致 / `SyncMetrics` 接受域内每个值且
拒绝域外值与缺维度 / router 的 emit 存在且 `result=` 取自 `outcome.reuse_verdict.metric_result`
（AST 断言 `attr='metric_result'`，禁 `getattr` 默认值）。

🔴 顺带补了一个既有判据的洞：`test_task29_timeline_evidence` 的
`test_every_metric_name_used_by_the_router_is_in_the_catalog` 只收**字符串字面量**的第一个
实参 ⇒ 用常量名 emit 的指标它一个都看不见。本任务的判据 `_emit_metric_names` 把 `ast.Name`
也收进来并在调用侧解析成真值，所以这两个 emit 也在覆盖面里。

### H.5 单趟 decline：**折进来还是分开** —— 裁定「分开」

任务 3 在 `adapters/excel._try_single_pass_materialize` 留了明文：「复用判定的可观测面归
Requirement 3 / Task 10 在 coordinator 层做（那里有 scope），此处不越界造第二个未注册指标」；
附录 A.6 第 2 条也写了「完整碰撞集合写进 `SinglePassDeclined.reason`，因为需求 3.3 要能统计
回落比例与原因」。所以它**确实归本任务**，但**是另一个维度**，用另一个指标。

**理由（两条都是具体后果，不是洁癖）**：

1. 两者回答不同的问题：复用未命中答「这次**要不要**物化」（每次 materialize 恰落一格）；
   decline 答「既然要物化，**用哪条写盘路径**」（只在未命中之后才存在）。
2. 折成一个 result 域会有两个可观测的坏结果：①同一次 materialize 要往同一个封闭域里记两次值，
   **复用命中率的分母就没了** —— 而那个命中率正是 requirements 3.1「一眼看出这次是复用还是
   全量」要看的数；②「内容真变了 + 单趟命中」与「内容真变了 + 回落链式」会被迫二选一地压成
   一个值。

判据 `test_the_two_result_domains_do_not_overlap` 把「保持两个维度」钉成机器事实（两个封闭域
零交集）。

**engine 拿不到 scope 怎么办**：engine 只**登记分型**，emit 与归因在 router。
`materialize_reuse_verdict.single_pass_decline_scope()` 是一个 `ContextVar` 作用域
（与 `excel_extract._workbook_scope` 同形态、同理由：并发请求各自独立；嵌套沿用外层桶），
`record_single_pass_decline(reason)` 在作用域外是**安全空操作**（观测设施不得让业务路径失败，
同 `release_scoped_workbooks` 的纪律）。

回落分型封闭域 `SinglePassDeclineClass` 与 `excel_materialize` 里 **5** 处
`raise SinglePassDeclined` 一一对应：`empty_bindings` / `openpyxl_roundtrip` / `row_shift` /
`payload_conflict` / `missing_primary_binding`，另加兜底 `unclassified`（**不抛** —— 指标记不准
不该把一次真实物化搞失败；可见性由 CI 门第 ③ 段承担：AST 逐 raise 点还原原因串后分型，
落进 `unclassified` 判红，枚举里有没有 raise 点的僵尸成员也判红）。
`payload_conflict` 的原因串由判据调用**生产那一份** `_payload_conflict_decline_reason` 现算，
不在测试里抄格式。

### H.6 CI 门：机制 + 实测它真的会红（requirements 3.3）

**为什么必须是一个独立的门，不能靠 pytest**：`tests/workpaper_sync/` 有约 **291** 条与本 spec
无关的既存失败（附录 F.9 的 A/B 差分实测）。在那个分母上「CI 里 pytest 红了」既不是新信号也
不是可归因信号 —— 值班看到的永远是同一片红。

`backend/scripts/check/check_materialize_reuse_digest_caliber.py`：stdlib + backend 依赖、
零 DB、零网络、亚秒级，`exit 1` 即违规。四段：

| 段 | 守什么 | 反证（改什么让它红） |
|---|---|---|
| ① 口径探针 | **11** 组等价表示 digest 必须全同 + **6** 组异义值 digest 必须全异 | 把 `canonical_value_for_digest` 退回裸 `json_safe` ⇒ **11/11 全报**；把口径改成「全折叠」⇒ 异义组报 |
| ② 缺陷类接线 | `digest_representation_drift` 在缺陷集合 / 指标封闭域 / 目录三处齐；分类器在「payload 逐键全等却未命中」上真的返回它；反向输入必须返回 `content_changed` | 从 `DEFECT_MISS_REASONS` 摘掉它 / 让分类器恒判一类 |
| ③ 回落分型完整性 | AST 逐 `raise SinglePassDeclined` 还原原因串 → 必须归进非 `unclassified`；枚举无僵尸成员；**检查器认不出的写法判红而不是放过**（同 D.3 / G.5 的纪律） | 新加一处 decline 不登记 |
| ④ falsifier 仍在 | 判据文件里还留着 `digest_representation_drift` 与 `ReuseDecision.hit` | 删判据 |

**健康态实测**：`全部通过：11 组等价表示 digest 全同、6 组异义值 digest 全异；缺陷类接线完整；
回落分型 5 类逐一对上 raise 点。`（exit 0）

**门真的会红（承重反证，生产文件零改动）**：用运行时替换把口径退回裸 `json_safe`
（等价于 `mutate_projection_digest_stability_guards.py` 的第 1 条变异）后重跑，段 ① 报 **9/9**
（那一轮矩阵还没加 boolean 两组；加完是 11/11），exit **1**，逐条点名是哪一对值、
以及「materialize 的业务身份复用对这类值**恒不命中**」。判据
`TestTheCiGateIsWiredAndFires` 把「健康态 exit 0」「退化态 exit 1 且报的全是 `[口径分叉]`」
「报出的组数 == 矩阵组数」「门无残留状态」四条都做成自动判据，另断 workflow 里真的有一行跑它
且**不带** `|| true` / `continue-on-error`（解析 YAML 而不是切字符串 —— 注释里提一句脚本名
也能让「字符串包含」通过）。

workflow job：`.github/workflows/governance-checks.yml` 的 `materialize-reuse-digest-caliber`
（跑门 + 跑本判据文件 + 跑既有的值级判据 `test_projection_digest_is_representation_stable.py`）。

#### requirements 3.3 措辞澄清（已落地，**不是**放宽）

原文「后者属于缺陷，应当在 CI 里直接判红而不是默默走全量」有两半，实测后各自落点写明：

* **生产**仍然走全量物化 —— 因一个内部 digest 缺陷去 fail 一次用户请求比多花一趟更坏
  （用户会连「在线编辑」都进不去）。被禁止的是「**默默**」：生产侧记一个**独立**指标桶
  （`miss_digest_representation_drift`）+ 一条 ERROR 日志（带完整差异清单）。
* **CI** 侧才是「判红」的落点，就是上面那个门。

另外把封闭域里的第四格 `no_base_projection`（无从比较）写进了 requirements 3.3 ——
首代 representation 与 `projection_artifact_id IS NULL` 的历史行本来就无从比较，把它并进上面
任何一类都是说谎，尤其不得并进缺陷类。这是**新增**一格诚实分型，不削任何既有判据。

### H.7 「连续两次必命中」守卫：两层各一条真链，真实输出

#### 层 1：CPU 段真链（`test_materialize_reuse_observability.py`，无 DB，51 条）

```
模板 substrate ──extract①──> projection A ──materialize①──> gen1
                                                             │
                                       projection B <──extract②
                             ──materialize②──> gen2   （B 喂进去）
```

两次**真** `adapter.materialize` + 两次**真** `extract` + 真 `_projection_payload` /
`projection_canonical_digest` + 真分类器，零 mock。反空转前提三层：两侧不是同一个对象 /
两代 substrate 字节不同（⇒ 两次真解析）/ 两侧都覆盖 218 个受管字段。

| 判据 | 实测 |
|---|---|
| 第二次的判词 | `decision=hit`、`miss_reason=None`、`metric_result="hit"` |
| 两侧派生的表示差异 | **恰 4 处**，形态 `int → bool`（H.2），payload 折成同一个 `true` |
| 业务比较面 | 0 差异（218 字段全比） |
| canonical payload 字节 | 逐字节相同 |
| 第二趟产物 vs 第一趟 | 142 entry 内容**逐 entry 全同**、142 个 `date_time` 全不同、整份 sha256 不同 ⇒ 第二趟整个是白干 |
| 第三代 digest | 与前两代同 ⇒ 不动点（复用不会「隔一次命中一次」） |

#### 层 2：coordinator 真链（真 PG，`test_task25_materialize_coordinator_pg.py` 新增阶段 8e）

层 1 跑的是 CPU 段，**判定本身**住在 coordinator（要真库）。所以在那份已经绿的 PG harness 上
补一条 leg：当前已提交的是阶段 8c 的 `Decimal("8888.00")`，本次 flush 送 float `8888.0`
（同一个金额、不同 Python 表示、不同落盘字节）⇒ 走完整 `authorize → create_pending_mutation
→ authorize → materialize`。

| 量 | 实测 |
|---|---|
| `business_identity_reused` | `True` |
| `reuse_verdict.metric_result` | `hit` |
| `commit_count` / `commits_invoked` | 0 / 0（**没进 `commit()`**） |
| `revision_delta` | 0 |
| 命中的 content version | 恰是 8c 提交的那一个（不是新建） |
| 反空转 | `flushed_value_repr="8888.0"` ≠ `committed_value_repr="Decimal('8888.00')"`，判据显式断言 |

同时给三条幂等路径的判词各加了一格断言（`replayed` / `hit` / `miss_content_changed` 三值互不
相同，且 `miss_content_changed` 真的比过 2 个字段、差异清单非空）。为什么重放与复用不能共用
一个值：触发条件不同（一个靠 pending mutation 的 `state=committed`，一个靠三元组身份），压成
一个桶会让**复用命中率被重放次数注水**。

PG 侧实测：**53 passed**（原 51 + 新增 2），13s。

#### 两层在同一个变异下**同时**变红（本任务的核心承重证据）

一次性 pytest 插件把口径退回裸 `json_safe`，同一条命令再跑一遍（生产文件零改动；插件用完即删，
全部内容如下，要复现照抄即可 —— 判据文件里的 `digest_caliber_reverted()` 上下文管理器是同一段
替换的**进程内**版本）：

```python
# tests/workpaper_sync/_task10_caliber_off_plugin.py
def pytest_configure(config):
    from app.services.workpaper_sync import content_mutation as CM
    from app.services.workpaper_sync.definitions import json_safe
    CM.canonical_value_for_digest = lambda field: json_safe(field.value)
```

```powershell
..\.venv\Scripts\python.exe -m pytest `
    tests/workpaper_sync/test_task25_materialize_coordinator_pg.py `
    tests/workpaper_sync/test_materialize_reuse_observability.py `
    tests/workpaper_sync/test_projection_digest_is_representation_stable.py `
    -p no:randomly -q --tb=line -rf `
    -p tests.workpaper_sync._task10_caliber_off_plugin
```

| 侧 | 结果 |
|---|---|
| 健康态 | `test_task25_materialize_coordinator_pg.py` 53 passed · `test_materialize_reuse_observability.py` 51 passed · `test_projection_digest_is_representation_stable.py` 全绿 |
| 口径退化 | **18 failed / 112 passed** |

18 条逐一可归因：层 2 的 `test_the_same_content_in_a_different_python_representation_still_reuses`
红（同内容两种表示没能复用）+ 层 1 的 `test_the_second_materialize_hits_business_identity_reuse`
红（报文里直接给出 `miss_digest_representation_drift` / `is_defect=True` /
`compared_field_count=218` / 「业务内容逐键全等（218 个字段，0 缺 0 多 0 改）却没命中复用」）
+ CI 门那 2 条按设计红 + 既有值级判据 7 条红 + 4 条是 PG harness 的级联
（8e 在变异下真提交了一次 revision ⇒ 后续 candidate 阶段的 `multi_generation_reuse` 也复用不到）。

⇒ 「第二次必命中」不是空转：口径一动，**两个层 + 值级矩阵 + CI 门**四处同时报警。

### H.8 改了什么（生产侧五处，全部**加法**）

| # | 位置 | 改动 |
|---|---|---|
| ① | `app/services/workpaper_sync/materialize_reuse_verdict.py` | **新模块**（纯函数、零 IO）：`ReuseDecision` / `ReuseMissReason` / `DEFECT_MISS_REASONS` / `ReuseVerdict` / `verdict_for_miss` / `compare_projection_payloads` / `business_value_equal` / `SinglePassDeclineClass` / `single_pass_decline_scope` / `record_single_pass_decline` / 两个指标名与两个封闭域 |
| ② | `metrics.py` | 目录 +2 条（32 → 34），`result_domain` **从判词模块 import**（不抄第二份域） |
| ③ | `materialize_coordinator.py` | `MaterializeOutcome.reuse_verdict`（必填）；`materialize()` 在 `_open_operation` **之前**算判词；新增 `_classify_reuse_miss` + `_read_base_projection_payload`。`_find_business_identity_reuse` 的**签名与返回一字未动**（`mutate_task25_materialize_coordinator_guards.py` 的 M35 锚点因此仍然有效） |
| ④ | `adapters/excel.py` | `_try_single_pass_materialize` 的 decline 分支：`record_single_pass_decline(exc.reason)` + 日志带上分型。**仍然不在 engine 里 emit**（那里没有 scope，emit 必然是假归因），原注释里「归 Requirement 3 / Task 10」的交接就此完成 |
| ⑤ | `wp_sync_router.py` | materialize 端点：`single_pass_decline_scope()` 包住 `coordinator.materialize(...)`；之后两处 emit + 缺陷类 ERROR 日志 |

判词/域/缺陷集合**单源**：coordinator / router / metrics / CI 门四处都 import ①，谁都不抄枚举
（判据 `test_no_second_reuse_verdict_vocabulary_exists` 按「谁 import 了它」判，而不是按
「谁没有字面量」—— 后者会被本 spec 满篇的示例名误伤）。

**没有动 DB**：判词是请求内的派生事实，不需要落列 ⇒ 不加 `V0XX__*.sql` / `R0XX__*.sql`
（迁移最高位仍是 V044）。`_read_base_projection_payload` 读的是**既有**的 projection artifact。

### H.9 登记在案、**本任务不做**的

诚实列清，避免下游把「没做」读成「不存在」：

1. **`alert_required` 两条都是 `False`** —— 理由见 H.4（`AlertCondition` 是别的 spec 的封闭
   枚举 + requirements 3.3 要的是 CI 判红）。若将来要给缺陷类配运行时告警，那是 13.9 的地盘，
   需要同时加 `AlertCondition` 成员 + 规则表条目 + 把 `alert_required` 翻 True（三处，
   `validate_registry` 会逼齐）。
2. **`no_base_projection` 的三种成因没有分开** —— `projection_artifact_id` 为 NULL / artifact
   行或文件缺失 / 载荷不是 JSON 对象，三者都归这一格。前者是正常的首代，后两者是数据问题；
   要分开得再加两格。当前靠一条 INFO 日志区分，没做成指标。
3. **端到端（HTTP → 前端）没有测** —— 同附录 E.1 / F.4 / G.7 的口径：本任务只量到 router 的
   emit 面。真实浏览器上「切两次在线编辑、第二次秒开」的端到端计时仍**未取到**（要改真实项目
   底稿内容才能让复用落空/命中各来一次），登记为待拍板，不拿判据数字冒充端到端。
4. **单趟 decline 的**比例**没有在真库上统计** —— 真库 D4 当前 39/39 走单趟（任务 3 落地后
   decline 恒 0），所以 `workpaper_sync_single_pass_decline_total` 在 D4 上是 0 样本。分型的
   正确性由 CI 门第 ③ 段（AST 逐 raise 点）+ 判据的 5 条原因串对账承担，**不是**由真库样本承担。
   要真库样本得有一个会插行（`row_shift`）的 entry 走一次物化。
5. **`UnmanagedRegionReport.inspected_aspects` / `os.replace` 不是最后一步 / 两次不可共享的完整
   DOM 解析** 三条与本任务无关，仍挂在 G.7 / C.4 / F.7 上待拍板。

### H.10 A/B 差分（证明本任务没引入新失败）

`tests/workpaper_sync/` 有约 291 条与本 spec 无关的既存失败（附录 F.9 实测），所以「这次跑出来
多少失败」本身说明不了任何事。同 F.9 的做法：**运行时开关**做同一份代码的 A/B（`git stash`
会把任务 3~9 的改动一起摘掉，而 `adapters/excel.py` 是任务 3 与 10 共用文件，按文件 stash 也
不干净）。

一次性插件 `tests/workpaper_sync/_task10_observability_off_plugin.py`（用完即删，全部内容如下）
把任务 10 在生产路径上加的**四件行为**整体关掉：

```python
def pytest_configure(config):
    from app.services.workpaper_sync import alerting as AL
    from app.services.workpaper_sync import materialize_coordinator as MC
    from app.services.workpaper_sync import materialize_reuse_verdict as RV
    from app.services.workpaper_sync import metrics as MX
    new_metrics = {RV.REUSE_METRIC, RV.SINGLE_PASS_DECLINE_METRIC}

    async def _no_classification(self, **_kwargs):                       # ① 归因
        return RV.ReuseVerdict(decision=RV.ReuseDecision.miss,
                               miss_reason=RV.ReuseMissReason.no_base_projection)
    MC.MaterializeCoordinator._classify_reuse_miss = _no_classification
    RV.record_single_pass_decline = RV.classify_single_pass_decline      # ② 回落登记
    original = MX.SyncMetrics.record_outcome                             # ③ router emit
    MX.SyncMetrics.record_outcome = lambda self, metric, **kw: (
        None if metric in new_metrics else original(self, metric, **kw))
    catalog = tuple(d for d in MX.METRIC_CATALOG if d.name not in new_metrics)   # ④ 目录
    by_name = {k: v for k, v in MX.METRICS_BY_NAME.items() if k not in new_metrics}
    MX.METRIC_CATALOG, MX.METRICS_BY_NAME, AL.METRICS_BY_NAME = catalog, by_name, by_name
```

**唯一关不掉**的是 `MaterializeOutcome.reuse_verdict` 这个必填字段（dataclass 字段无法在运行时
变回可选）。它的影响面由构造点穷举承担：全仓 `MaterializeOutcome(` 恰 **4** 处、全在
`materialize_coordinator` 里、全已传值、无任何测试构造它 —— 两条判据把这个事实钉住。

```powershell
# backend cwd，两侧只差一个 -p
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync -p no:randomly -q --tb=no -rf
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync -p no:randomly -q --tb=no -rf `
    -p tests.workpaper_sync._task10_observability_off_plugin
```

| 侧 | 结果 |
|---|---|
| **ON**（本任务的代码） | **291 failed / 8246 passed / 2 skipped / 16 xfailed / 6 errors**（35:01） |
| **OFF**（运行时关掉四件事） | **299 failed / 8238 passed / 2 skipped / 16 xfailed / 6 errors**（35:44） |
| 只在 ON 侧失败 | **0 条** ⇒ 本任务**没有引入任何新失败** |
| 只在 OFF 侧失败 | **8 条**（7 条是本任务的判据 + 1 条是插件自身的副作用） |

ON 侧那 291 条与 F.9 记录的 291 条**同数**，且里面**没有任何**属于
`test_materialize_reuse_observability` / `test_task25_materialize_coordinator*` /
`test_single_pass_*` / `test_projection_digest_*` 的条目 —— 直接受影响的几套全绿。

只在 OFF 侧失败的 8 条：`test_both_metrics_are_registered_in_the_existing_catalog` /
`test_the_recorder_accepts_every_result_and_rejects_anything_else` /
`test_the_router_emits_the_verdict_on_the_materialize_endpoint` /
`test_the_engine_records_into_the_scope_and_is_a_noop_outside_it` /
`test_the_gate_script_exists_and_passes_on_healthy_code` /
`test_the_gate_fires_when_the_caliber_regresses` /
`test_the_reuse_verdict_labels_each_idempotency_path_distinctly`（真 PG）—— 7 条承重；
第 8 条 `test_task29_timeline_evidence::test_record_outcome_has_no_default_for_result_or_landed`
是**插件自身的副作用**（它把 `record_outcome` 换成了带 `**kw` 的包装器，那条 AST 判据看的是
签名），如实登记、不算本任务的账。

`tests/workpaper_sync/` 之外单独跑了会碰到本任务改的模块的两个文件
（`tests/test_d4_29_customer_detail_sync.py` + `tests/test_structure_fingerprint_memoization.py`）
= **35 passed / 0 failed**（F.9 当时是 34 passed / 1 failed，那条任务 3 遗留的
`_materialize_within_scope` duck-type 桩问题已不复现）。全仓 grep 实测
`tests/workpaper_sync/` 之外**没有**任何测试引用 `wp_sync_router` /
`materialize_coordinator` / `workpaper_sync.metrics` / `sync_metrics` / `METRIC_CATALOG`。

**另一处既存红，登记清楚**：`backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py
--check` 报 8 个 section stale（`blocking_points` / `data_restoration` /
`multi_resolver_adjudication` / `mutation_coverage` / `source_commit` / `task_declarations` /
`upstream_inputs` / `verdict`）。实测与本任务**无关**：把两条新指标从目录里运行时摘掉后重跑，
stale 的 section 清单**逐字相同**。它的红来自该门刻意保留的 `source_commit` stale 轴
（「源码变了但证据没刷新」）—— 任务 3~9 已改了 5 个生产模块并新增 6 个判据文件，证据 JSON 需要
由它的 owner 刷新，不在本任务范围。
