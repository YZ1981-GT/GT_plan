# 需求：OO 物化单趟写入 + participant 主动离开

**spec**：`oo-single-pass-materialize-and-room-leave`
**创建**：2026-09-22
**上游**：`workpaper-html-onlyoffice-bidirectional-writeback-closure`（平台总纲）
**触发**：用户 2026-09-22 明确指派 ——
「复用落空时（用户真改了内容再切过去）的全量 materialize 仍约 30s。cProfile 拆开是
adapter.materialize 42.8s / extract 6.0s / verify 6.9s，其中 39 趟链式写盘是 load+save
各 39 次的固有成本 —— 要真正压下去得把多 binding 改成单趟写入，那是独立 spec 的体量，
你需要建 spec 来修改。」

## 背景：本 spec 不重复做的事

同一轮会话已经落地的**复用侧**优化**不在**本 spec 范围（它们解决的是「内容没改时不该
物化」，本 spec 解决的是「真的要物化时为什么这么慢」）：

* `excel_extract.workbook_read_scope()`：作用域内同一 `(文件身份, data_only)` 只解析一次；
* 冷注册串行锁 + 启动后台预热（`_warm_workpaper_sync_registry`）；
* `projection_digest_value.canonical_value_for_digest()`：修掉「同一金额零 `0` vs `0.0`
  算出两个 digest ⇒ 业务身份复用恒不命中」的死代码缺陷（实测 store-projection 首请求
  32325ms → 114.9ms，切 OO D4-6 31508ms → 2111ms）。

复用命中后已经是**秒级**。本 spec 针对的是**复用必然落空**的那条路径：用户真改了内容
再切「在线编辑」，此时必须重新物化整本工作簿。

## 术语

| 词 | 含义 |
|---|---|
| binding | 契约里一条「projection 字段 → 工作簿单元格」的绑定组（每张受管 sheet 一组或多组） |
| 链式写盘 | 每个 binding 各自 `load_workbook` → 改格 → `save` 成一个临时文件，下一个 binding 以上一个的产物为输入 |
| 单趟写入 | 整个 entry 的全部 binding 在**一次** load/save 之间完成写入 |
| 反读等值 | 物化后重新解析产物、与 projection 逐字段比对（`verify`），不等值即拒绝发布 |

## 需求 1：单趟写入取代多 binding 链式写盘

**用户故事**：作为在 D4 里改完明细又要去 Excel 复核的审计助理，我希望「切在线编辑」在
**10 秒内**打开，而不是盯着 30 秒的加载态怀疑系统卡死。

### 验收标准

1.1. 对**无跨 binding 坐标碰撞**的多 binding entry，一次物化对 **substrate** 的
     `openpyxl.load_workbook` 次数 SHALL 与 binding 数**解耦**（`≤ 2`：`data_only=True/False`
     两个视图各一次，由全部 binding 共享），而不是随 binding 数线性增长（改动前
     `binding 数 × 2`，D4 实测 78）。该次数 SHALL 由测试按**实际调用计数**断言，不得只断言
     耗时（耗时判据在不同机器上必然漂移）。

     ⚠️ 存在跨 binding **坐标碰撞且写入 payload 冲突**的 entry SHALL 显式回落逐趟链式，
     此时解析次数回到 binding 数级别 —— 那是正确的保守（同格两个写入不同 ⇒ 结果取决于谁
     最后写，链式顺序在单趟里无法复现），不算违反本条。payload 比较面为
     `(kind, value, stable_field_key, mode, formula_text)`：全等即恒等覆盖，SHALL 合并；
     任一项不同即 decline。

     🔴 本条的 ⚠️ 段原写「存在跨 binding 坐标碰撞的 entry（实测 D4 的 C38）」，已按任务 2
     的真库实测**收紧**（2026-09-22 拍板，见 design 附录 A.3 / A.6 / A.7）：D4 的碰撞是
     `sheet14.xml` 的 `C24`/`E24`/`C38`/`E38` **4 格**（不是 1 格），且两方 payload 逐字段
     相同、两种写入顺序产物逐字节相同 ⇒ 合并**不丢任何东西**。按旧措辞 D4 必须回落，而回落
     让本需求 1.5 的「≤10s」对 D4 **永远达不到** —— D4 正是 1.5 指名的那个 entry。

     decline 原因 SHALL 是确定的、完整的：按 `(sheet_part, 行, 列)` 排序后报**全部**冲突格，
     不得抽样报一格（原实现按 `set(plan.coords)` 抽样，真库上同一批碰撞报出 `C38` 与 `E38`
     两种，且余下碰撞不可见 ⇒ 需求 3.3 的回落原因统计无从做起）。

1.2. 单趟写入的**产物字节**与改动前逐 binding 链式写盘的产物 SHALL 在**两个**口径下同时
     一致：

     (a) **反读等值**：同一份 projection 走新旧两条路径，`extract` 出来的字段集合与值
         SHALL 逐项相等（含「缺字段 / 多字段 / 值或类型变」三类，不得只比 key 集合）；
     (b) **逐 zip entry 字节等值**（忽略 `date_time`）：两份产物的 zip 条目集合 SHALL 相同，
         且每个同名条目的**内容字节** SHALL 相同。

     这条是本需求的安全底线 —— 提速不得以「少写了某些 binding」为代价。

     🔴 (b) 原不在本条里，按任务 4 的真库实测**补入**（2026-09-22 拍板，见 design 附录 B.4
     / F.2）：反读等值对一整类漏写**天生是盲的**。实测漏写 `d4_10_rows` 的 **49 处写入**
     （28 处 inline string + 21 处数字字面量）之后，218 个反读字段**逐字段全等**（0 缺 0 多
     0 改），而 `xl/sheet15.xml` 真的少了 95 字节 —— 因为那些写入只改变单元格的**表示形态**
     （inline string vs shared string、数字格式），不改变反读出来的值。⇒ 字节判据是本条的
     **必需项**，不是加强项；只写 (a) 的验收标准挡不住这类回归。

     `date_time` 显式分流的理由（不是放宽）：任务 1 实测同一 projection 连续两次物化的 142
     个 entry 内容字节全同、142 个时间戳全不同 ⇒ 不摘掉它这条判据永远红；摘掉之后剩下的
     每一个字节差异都是真差异。整份文件的 sha256 **不**作为判据（同因）。

1.3. 任一 binding 写入失败时 SHALL 整趟失败并保持磁盘上**零残留**（不得留下写了一半的
     临时文件，也不得把半成品当 staged artifact 发布）。当前链式实现天然具有「前 N 个
     binding 已落盘」的中间态，单趟化之后这条必须由测试显式钉住。

1.4. 单趟写入 SHALL 复用既有 `workbook_read_scope()` 的句柄语义：写入结束后
     `release_scoped_workbooks(path)` 必须能真正释放句柄（Windows 上未释放会导致临时
     文件删不掉，这条已在上一轮踩过）。

1.5. 物化耗时 SHALL 在真库 D4 entry（`xlsx/gt-d4-operating-revenue`，46 张 sheet、13 张
     受管）上从 ~30s 降到 **≤10s**，并以 `docs/operations/evidence/` 下的真实计时证据
     登记（前后对照，同一 wp / 同一 projection）。

## 需求 2：extract 与 verify 不再各自重解一遍工作簿

**用户故事**：作为维护者，我不希望「读同一个文件三次」这种成本被当成固有成本接受。

### 验收标准

2.1. 一次 materialize 全流程（materialize → extract → verify → structure_hash）对同一份
     字节的解析次数 SHALL **与消费方个数解耦**：每个**解析视图**各 **1** 次，其中「解析
     视图」= `(字节身份, read_only, data_only)`。该次数 SHALL 由测试按**实际调用计数**断言。

     本条同时覆盖**非 openpyxl** 的重复解析（需求 2 的用户故事原话是「我不希望『读同一个
     文件三次』这种成本被当成固有成本接受」，它不限于 `load_workbook`）：同一份字节的
     `xl/workbook.xml` + rels、Excel Table 清册（要读全部 sheet part）、
     `xl/sharedStrings.xml` 前缀 digest，SHALL 各只解析一次。

     🔴 本条原写「解析次数 SHALL 为 **1**」，已按任务 7/8 的真库实测**收紧措辞**
     （2026-09-22 拍板，处理方式同 1.1 的 A.7，见 design 附录 F.1）：原措辞与需求 2.2
     **自相矛盾** —— 2.2 明说 `data_only=True/False` 是两个不可互相冒充的解析结果、作用域
     键里必须保留它，那么只要两个视图都被用到，「1」就不可达。真库 D4 实测产物字节上被用到
     的视图恰好 3 个（`read_only=True` 的 `data_only` 两视图 + 完整 DOM 一视图，后者因为
     `read_only` 的 worksheet 没有 `ws._cells` / `row_dimensions`，两者不可互换）。

     收紧后的口径**不比原措辞弱**：它把判据从一个数字换成「与消费方个数解耦」这个结构
     事实，并要求**每个例外逐一列名**。真库 D4 实测「不可共享」的完整 DOM 消费方恰 2 个
     （整簿指纹 `_structure_fingerprint_uncached` 与隐藏 metadata sheet 读取
     `_read_gt_sync_pairs`）—— 它们用 openpyxl 的**批量成格**读法（`ws.iter_rows()` 会把
     包围盒内每个坐标惰性新建成 Cell），共享给它们会污染 `ws._cells`，而发布时刻的
     `collect_workbook_structure` 正是按 `ws._cells` 的成员关系判「这个转置字段格在文件里
     存不存在」⇒ 共享会**改变 structure_hash**。这两个例外 SHALL 在判据里列名并说明理由，
     不得从「解析次数」里抹掉；新增第三个例外 SHALL 让判据打红。

2.2. 复用 SHALL 通过既有 `workbook_read_scope()` 完成，不得新引入第二套 workbook 缓存
     （模块级长存缓存已被明确拒绝：它会让 Windows 删不掉临时文件）。

     被共享的解析结果 SHALL 是**只读**的：任何要就地改动 workbook 的消费方
     （`materialize_transposed_workbook` 就地写格 + `wb.save()`）SHALL 自己解析一份私有
     副本。「只读」SHALL 由判据实测，而不是靠注释声明。

2.3. `verify` 的判据 SHALL 一字不放宽：复用解析结果不等于复用**结论**，反读等值仍须逐
     字段比对。测试 SHALL 包含一条变异反证 —— 故意让产物少一个字段，verify 必须红。

## 需求 3：复用命中率可观测、可回归

**用户故事**：作为下一个接手的人，我要能一眼看出「这次是复用还是全量」，而不是靠掐表。

### 验收标准

3.1. materialize 的结果 SHALL 带一个机器可读的复用判定（命中/未命中 + 未命中原因），
     并落进既有 metrics（`workpaper_sync_*`）而不是只写日志。

3.2. SHALL 有一条守卫实测「同一 projection 连续两次 materialize：第二次必须命中复用」。
     这条正是上一轮那个「digest 口径不一致 ⇒ 复用恒不命中」缺陷的**判据缺口**：当时
     `_find_business_identity_reuse` 的单测全绿，因为没有人把「两次同内容」跑成一条链。

     🔴 「同一 projection」SHALL 读作「同一份业务内容的**两次独立派生**」，**不是**同一批
     Python 对象。按任务 10 的实测**收紧**（2026-09-22 拍板，处理方式同 1.1 的 A.7 /
     2.1 的 F.1，见 design 附录 H.1）：真栈那个缺陷发生在两条派生路径**之间**（HTML store
     走 JSON ⇒ 裸 int/float；Excel extract 走 openpyxl ⇒ int/float/bool；merge 与审定回写
     ⇒ `Decimal`），两侧若喂同一批对象，digest 必然相等、缺陷必然看不见。

     按原措辞，既有的 `test_task25_materialize_coordinator_pg.py` 阶段 8b 已经是一条「两次
     同内容」的真链且**一直全绿**（两侧都经 `_projection(..., "1234.50")` 强转成同一个
     `Decimal`）—— 也就是说原措辞**已经被满足过，而缺陷仍然存活**。这正是本条要堵的那个洞，
     所以措辞里必须把「两次独立派生」写明。

     判据 SHALL 显式断言两侧的派生互不相同（例如 substrate 字节不同、或落盘表示不同），
     否则守卫在「同一对象」这条退化输入上恒真。

3.3. 复用未命中原因 SHALL 可区分至少三类：内容真变了 / 契约或 bundle 变了 / digest 口径
     不一致（后者属于缺陷，应当在 CI 里直接判红而不是默默走全量）。

     🔴 「在 CI 里直接判红而不是默默走全量」的两半各自落点（任务 10 实测后的澄清，
     **不是**放宽，见 design 附录 H.6）：**生产**仍然走全量物化 —— 因内部 digest 缺陷去 fail
     一次用户请求比多花一趟更坏；被禁止的是「**默默**」，所以生产侧 SHALL 把它记成一个
     **独立**的指标桶 + 一条 ERROR 日志。**CI** 侧 SHALL 有一个自己就能红的门
     （`backend/scripts/check/check_materialize_reuse_digest_caliber.py`）：
     `tests/workpaper_sync/` 有约 291 条与本 spec 无关的既存失败（design 附录 F.9 的 A/B
     差分实测），在那个分母上「pytest 红了」不是可归因信号。

     未命中原因的封闭域 SHALL 另含第四格「无从比较」（基线侧没有可读的 projection 载荷）：
     首代 representation 与 `projection_artifact_id IS NULL` 的历史行本来就无从比较，
     把它并进上面任何一类都是说谎 —— 尤其不得并进缺陷类。

## 需求 4：participant 主动离开（clean close 的正解）

**用户故事**：作为一个字都没改就点「结构化视图」的用户，我希望系统只是「把编辑器关掉」，
而不是给这条路配一次永远等不到回调的强制保存、更不是把协同房间锁死。

### 背景（2026-09-22 真库实测，本 spec 的直接触发之一）

前端曾把「未改动离开」接到 `POST …/rooms/{id}/close-intents`。实测证明那是**误用**：
close-intent 不是「我走了」，而是 **close barrier 仲裁** —— 它把 participant 推成
`closing`、选 leader、并提升一条 `kind=close_capture` 的写请求。对未改动文档，这条 capture
永远等不到 OO 回调：

* room `03bbcad8-70ef-4462-8a37-68af4fc0d1fa` 停在 `state=close_barrier`、participant
  `closing`、`close_capture` 请求 `state=frozen`；
* 该 room 此后**再也进不去**：下一次打开 confirm-descriptor 仍返回 200，紧接着就是
  「同步失败，请重试」。

而 `ParticipantState.left` 在转换表里**是合法终态**（`PARTICIPANT_EDGES`：
`active → left`、`closing → left`），却**全仓没有任何 service / 端点会写它** —— 也就是
「离开」这条路在服务端根本不存在。前端因此只能做本地转换（当前实现），让 lease 按
`expires_at` 自然过期。

### 验收标准

4.1. SHALL 提供一条「participant 主动离开」的服务端路径，把 participant 置为
     `ParticipantState.left`，且**不**创建任何 forcesave/close_capture 请求、**不**推进
     close barrier、**不**旋转 generation。

4.2. 离开 SHALL 是 authorization-first 且幂等：同一 participant 重复离开返回同一结果，
     不得产生第二条审计事件；无权限者一律同 404 oracle。

4.3. 离开 SHALL 只影响该 participant：room 若仍有其他 active participant，room 状态
     SHALL 保持 `active`（这正是与 close-intent 的本质差别 —— 后者是「最后一个人走，
     该收尾了」）。

4.4. dirty（有未同步改动）时 SHALL 拒绝「离开」，并要求走真保存路径：这条与前端
     `leaveWithoutSaving()` 的 `canLeave` 硬门同源，两侧都不得放宽。

4.5. 前端 `leaveWithoutSaving()` SHALL 在本端点可用后改为调用它；在那之前保持纯本地
     转换。切换 SHALL 由测试双向锁死（接上之后「零请求」判据必须相应更新为「恰一次
     leave 请求、零次 forcesave、零次 close-intent」）。
