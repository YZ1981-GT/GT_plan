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

1.1. 对同一个 entry 的一次物化，`openpyxl.load_workbook` 与 `Workbook.save` 的调用次数
     SHALL 各为 **1**（当前实测各 39 次），且该次数 SHALL 由测试按**实际调用计数**断言，
     不得只断言耗时（耗时判据在不同机器上必然漂移）。

1.2. 单趟写入的**产物字节**与改动前逐 binding 链式写盘的产物 SHALL 在「反读等值」口径下
     一致：同一份 projection 走新旧两条路径，`extract` 出来的字段集合与值 SHALL 逐项相等。
     这条是本需求的安全底线 —— 提速不得以「少写了某些 binding」为代价。

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

2.1. 一次 materialize 全流程（materialize → extract → verify）对同一份产物字节的
     workbook 解析次数 SHALL 为 **1**（当前 extract 6.0s + verify 6.9s 里各含一次全量解析）。

2.2. 复用 SHALL 通过既有 `workbook_read_scope()` 完成，不得新引入第二套 workbook 缓存
     （模块级长存缓存已被明确拒绝：它会让 Windows 删不掉临时文件）。

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

3.3. 复用未命中原因 SHALL 可区分至少三类：内容真变了 / 契约或 bundle 变了 / digest 口径
     不一致（后者属于缺陷，应当在 CI 里直接判红而不是默默走全量）。

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
