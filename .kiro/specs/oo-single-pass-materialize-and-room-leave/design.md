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

## 二、方案：单趟写入

```
现状：  load → write(b1) → save ─┐
                                 └→ load → write(b2) → save ─┐  … ×39
目标：  load → write(b1..bN) → save        （1 次 load / 1 次 save）
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
| P5 | verify 仍逐字段比对（复用解析 ≠ 复用结论） | 2.3 | 产物少一字段 ⇒ verify 必红 |
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
| binding 间存在隐式顺序依赖 | 单趟写入后某些格值不同 | 先做依赖调查（任务 1），有依赖就显式排序并加判据 |
| openpyxl 单趟写入内存峰值升高 | 大工作簿 OOM | 实测峰值内存；必要时按 sheet 分组多趟（仍远少于 39 趟） |
| 复用命中率上升后掩盖单趟化缺陷 | 全量路径很少被走到、缺陷不易暴露 | 判据里强制走全量路径（改一个字段后立刻物化） |
| leave 端点被误当作 close | 有人拿它替代 close barrier | 端点文档 + 判据明写「room 收尾不在此」；close_capture 相关字段一个都不动 |
