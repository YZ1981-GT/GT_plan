# 任务：底稿双向回写保存安全与镜像一致性收口

- [x] 1. 基线与设计
  - [x] 1.1 核对 HEAD / 远端、迁移号、相关文件是否有并发改动；建立锁定分离头候选工作树
  - [x] 1.2 运行前端与后端相关基线；记录干净 HEAD 的 app import 阻断，不误归因本轮
  - [x] 1.3 逐文件复核 pending 旧基线：108 = 106 活路径 + 2 零消费者；确认 10 条父保存链
  - [x] 1.4 比较 durable job 与同事务 mirror，裁定本轮采用 content commit hook 内原子镜像且不新增迁移

- [x] 2. checklist 渐进式 CAS
  - [x] 2.1 后端增加 strict 标志；既有行缺版本 428、过期 409、新行可建、legacy LWW 保持
  - [x] 2.2 新增前端 checklist CAS 单一 helper，保存请求携带 `if_match` 并推进版本
  - [x] 2.3 接入通用 `useChecklistPersistence` 和本轮双向父 formData；错误保脏并透传给 pending tracker
  - [x] 2.4 增加严格/兼容/并发创建/保存中再编辑测试与 CAS 调用面守卫

- [x] 3. pending 保存闸门
  - [x] 3.1 `pendingWrites` 收集 flusher / in-flight 的全部失败，等全部结算后抛结构化错误
  - [x] 3.2 10 个父宿主及 D4 注入保存按完整批次调用 `trackPendingWrite`
  - [x] 3.3 106 个活 writer 接 pending-only flusher；timer 为空零写，清 timer 后不二次触发
  - [x] 3.4 修 F2Adjustment 双写、F4/F5 卸载重排、D4 三个自桥未清 timer 等特例
  - [x] 3.5 清空旧未登记基线并新增语义守卫；2 个死项以零消费者断言登记

- [x] 4. OO→HTML 原子镜像
  - [x] 4.1 把 cleared/recomputed store view 与 `mirror_projection_into_store(commit=False)` 移入 commit hook
  - [x] 4.2 删除 content commit 后的第二次 mirror；保持 client baseline settlement 顺序
  - [x] 4.3 dedicated item 缺 provider 门面时 fail-visible；全部 `commit=False` 分支零内部 commit
  - [x] 4.4 增加中途失败回滚、同一 incoming retry、单 revision 和调用顺序测试

- [x] 5. 回归与变异
  - [x] 5.1 前端定向 18 files / 206 passed；全量 vue-tsc baseline 2990 → candidate 2984（added 0 / resolved 6）
  - [x] 5.2 后端定向 366 passed；真实 PG 107 passed；改动 Python 文件 Ruff 全绿
  - [x] 5.3 23 类变异逐个 RED，靶点各恰 1 次命中并逐字节恢复（报告 `mutation_report.txt`）

- [x] 8. 语义审查驱动的修复（第二轮，P1-1 ~ P1-3）
  - [x] 8.1 P1-1：CAS 与 mirror 共用同一逻辑键锁域——mirror 在任何 base SELECT 前冻结
        `_ResolvedMirrorTargets` 全集并一次加锁，清单外 item fail-visible，multi-store 内部
        commit 收敛到顶层一次；新增真实 PG 的 CAS↔mirror 交错测试
  - [x] 8.2 P1-2：删除 F2 监盘私有 `_fieldFlushers`，rows/fields 各自 `registerPendingFlusher`；
        保存事件改 resolve/reject 协议（`dispatchF2StocktakeSave`），不再把 8 秒超时当成功；
        F2-21 分离 `businessReadonly`；F2-22/23 的 `syncDocToOo/FromOo` 返回 false 时保持原模式
  - [x] 8.3 P1-3：G 共享切换器 16 个宿主建立过渡静止点
    - [x] 8.3.1 14 个 formData 的 `flushPending` 改 `Promise<void>` 并真 await 下层写入
          （批量型 `await _doSave`，逐项型 `await Promise.all(inFlight)`）
    - [x] 8.3.2 写入失败必须到达调用方：`_doSave` 的 catch 重抛（canceled 除外）；
          带草稿重试的 5 个在落本地草稿后抛错，不再把「未落库」伪装成成功
    - [x] 8.3.3 14 个 formData 接入 `registerPendingFlusher`；补上 G4ECL / G4SPPI
          从未导出的 `flushPending`（宿主一直在调用一个不存在的方法）
    - [x] 8.3.4 16 个宿主拆 `businessReadonly` / `isReadonly`：OnlyOffice 挂点绑前者，
          HTML 结构化输入（含 `GtGridSheet`、13 个 `G5Tab*`）绑后者，过渡期间冻结
    - [x] 8.3.5 宿主 `flushHtml` 改 `await formData.flushPending()`；卸载路径改显式 catch 的
          void 调用（含已迁移的 G2，原为裸调 async flushPending）
    - [x] 8.3.6 守卫：宿主分母由 `useGRenderModeSwitch` 真实 import 反查并与清单双向相等；
          `:readonly` 绑定按标签名判定；两种失败传递形态分别证明；新增 G9/G1 运行时行为测试

- [ ] 6. 浏览器验收
  - [ ] 6.1 【测试】项目在 HTML 修改后立即切在线编辑，OO 显示新值
  - [ ] 6.2 注入一次保存失败，确认保持 HTML、错误中文可见且零 materialize；恢复后可重试
  - [ ] 6.3 OO 修改后回表单并刷新，HTML / API / 已发布 representation 三方一致；恢复验收数据

- [ ] 7. 收尾
  - [x] 7.1 语义审查并修复高优先级发现（第一轮 P0/P1 已闭合；第二轮 P1-1~P1-3 见任务 8）
  - [ ] 7.2 更新 INDEX / memory，干净候选树复跑关键验证
  - [ ] 7.3 只提交本 spec 文件与改动块；同步远端后按版本工具推送当前分支
