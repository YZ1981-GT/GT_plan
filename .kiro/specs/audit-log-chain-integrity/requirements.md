# 需求文档：S10　审计哈希链加固

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
原 ADR-FHIC-12 的全部内容 + `append_audit_log` 调用方吞异常逐个裁决（阶段一 p1-00 现算 **41 处 / 25 个文件**）。

**设计输入（design §8.1 原文抄入，实施时逐条现算复核）**：

1. **链尾按链接关系唯一**（不是按 `ts`）：新表 `audit_chain_head(chain_key PK, tail_entry_id, tail_hash, updated_at)`
   一次性回填；写入时锁内读 head、用 `EXISTS(prev_hash = head.tail_hash)` 判「绕过写入」、插入后更新 head；
   全链反连接只用于校验与分叉工具。
2. **`append_fork_ack(db, key, *, survivor_entry_id, dead_entry_id, operator_id, reason)`**：锁内校验
   「未确认链尾集合 == {survivor, dead}」后，以 survivor 的 `entry_hash` 为 `prev_hash` 直接插入，不经链尾查找。
3. **worker `_write_batch` 每条链一个 SAVEPOINT**：链损坏只回滚该链、条目进 `audit:log:quarantine:<chain>`
   （不计重试上限、不丢弃）。
4. **上线前置**：目标库只读分叉扫描「未确认分叉 = 0」（本机全局链现有 **1 处**，F44）；`/api/health` 增
   `audit_chain.unacknowledged_forks`（> 0 即 degraded）；**确认工具必须先于 fail-closed 代码交付并执行**；
   公式发布等写全局链的路径在确认前不得改为 fail-closed。
5. **锁顺序**：审计链咨询锁是事务内**最后**获取的咨询锁；先写审计后取锁的调用点要逐个登记。
6. **v2 可重放哈希**：`_hash_v: 2`、`_resource_id` 原样字符串、`_year`（兼容本 spec 在公式审计载荷里写入的 `year`）；
   float 落库前转定点字符串（`format(Decimal(repr(x)), 'f')`）、拒绝 NaN / Inf；往返测试含 `1e20`；
   v1 兼容计 `legacy_verified` / `legacy_unverifiable`。
7. **verify-chain** 增片外前驱锚点，以及 `fork` / `orphan` / `missing_prefix` / `content_mismatch` 四类原因。
8. **helper 与 worker**：取锁、读链尾失败**不写 GENESIS**；删掉 `hash(lock_key)`（进程随机）与无锁降级。

相关事实：F18（无项目链锁、按 `ts DESC` 取尾、异常返回 GENESIS、worker 锁键进程随机、一批多链同事务、
重试超上限即丢弃）、F44（真库 1736 行 / 387 条链各恰 1 个 genesis；同链同 `ts` 49 组；全局链 893 行有 1 处未确认分叉；
`prev_hash` 无索引；helper 用请求 `resource_id` 字符串参与哈希而 `object_id` 只存 UUID；唯一 `formula.changed` 行
按 v1 公式重算不等于存值）、F50（verify-chain 的鉴权与排序口径）。

## 2. 依赖与先后
独立 —— `formula-hub-integrity-closure` 不阻塞它，它也不依赖本 spec（需求 11.3 已钉住本 spec 对三个审计文件 0 改动）。

## 3. 触发条件

审计留痕的可信度被质疑时，或 F44 的那 1 处未确认分叉需要处置时立即启动；决策项 X1 推送前不必等它。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
- 本 spec 需求 11.3 的验收是「`audit_log_helper.py` / `workers/audit_log_writer_worker.py` / `routers/audit_logs.py`
  在最终提交中 **0 改动**」—— 已用 `git diff` 核实为空，S10 启动时这三个文件即其主战场。
- 本 spec 只做了公式域的入口收口（载荷加 `year`、客户端提交端点改「人工补记」），写入语义一个字没动。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1，交接后新发现：3 个绕过 helper 的写入方（都写不进去）、4 份哈希函数副本、按 v1 重算不符的行有 12 行；其中 11 行查明是 `object_id` 参与哈希时用了无连字符写法，v1 重算试两种 UUID 写法后只剩 `formula.changed` 那 1 行不可重算（design §1 设计复核补充①）。
- 对设计输入 I1（一次性回填链尾）与 I3（一个事务内逐链保存点）各有一处变形，理由见 design ADR-ALC-02、ADR-ALC-06；待拍板见 design §7。
