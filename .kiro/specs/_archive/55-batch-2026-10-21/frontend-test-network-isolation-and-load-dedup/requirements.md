# 需求文档：前端单测网络隔离与并发加载合并

> spec：`frontend-test-network-isolation-and-load-dedup`
> 来源：`formula-manager-runtime-integrity-closure` 实地复验时的两处发现（2026-10-19）。
> 类型：测试基座修复 + 前端加载去重；不改后端、不改接口契约。

## 现状（2026-10-19 现算，探针只记录不改行为）

- 全量前端单测里有 **25 个测试文件**在发真实 TCP 连接，共 132 次，全部打到 `localhost:3000`（jsdom 默认 origin）。本机该端口是 Metabase，CI 上该端口无服务（连接被拒）⇒ 同一用例在本机与 CI 走不同分支。`src/test/setup.ts` 只短路了 `fetch`，axios 在 jsdom 里走 XHR，没有被拦。
- `useAcnr.listSheets / listCells` 有模块级缓存（所有实例共享），但只在响应回来后写入，同参数的并发调用全部穿透。公式管理弹窗打开时 `loadAcnrTree` 会被 watch（未 await）与定位函数（await）同时调用 ⇒ 发两次相同 GET；`utils/http` 的 GET 去重取消先发的那一发，被取消方被当成失败：控制台打「[useAcnr] listSheets 失败」，并短暂写入空目录。`loadConsolNoteTree` 在合并附注入口是同一写法。
  - 浏览器实测补充（任务 8）：同一 tick 内的两次调用，先发那次在 XHR 发出前就被取消，网络面板只看到 1 次请求；晚一点的第二次调用会中止已发出的 XHR，看到 2 次、先发那次被取消。两种情况下「listSheets 失败 canceled」告警都会出现，它才是稳定的观测信号。
  - 附注 scope 的 ACNR 并发取决于时序：本机 ACNR 目录比附注树先返回，定位函数到达时目录已加载，不撞。合并工作底稿 scope 是同一 tick 内连调两次，必撞；合并附注 scope 由末尾的 `applyTargetNode()` 再调一次，实测也撞。
  - 同类还有 `loadNoteUserFormulas`（任务 8 实测发现）：附注 scope 带章节打开时，预取与定位后的节点点击各调一次，先发那次被取消。

## R1：单测禁止真实网络连接

1. WHEN 单测中任何代码尝试建立连接（jsdom XHR、WebSocket、Node http 等）THEN 测试基座 SHALL 不触达网络，以连接失败结束该请求（与 CI 上「端口无服务」同语义）；失败 SHALL 经 Node 自身的异步错误路径到达调用方——不受测试开启的假定时器影响，也不得在请求挂好错误监听之前抛出。
2. 拦截 SHALL 在隔离与共享模块图两种模式下都生效；同一 worker 内多次执行 setup 不得重复包裹。
3. 既有 `fetch` 短路行为保持不变。
4. WHEN 去掉拦截 THEN 守卫测试 SHALL 打红（以本地回环服务器实际收到的连接数为判据，不以源码字符串为证）。

## R2：网络泄漏可见、只减不增

1. 现存 25 个泄漏文件 SHALL 登记为清单，每条带观测到的端点作证据；清单只许删除条目（守卫测试以 2026-10-19 基线集合为上界）。
2. WHEN 隔离模式下某测试文件发生被拦截的连接且该文件不在清单内 THEN 常规运行 SHALL 在输出里告警并列出被拦截的请求；以 `GT_TEST_NETWORK_AUDIT=1` 运行时该文件 SHALL 失败。
   （实施期勘误：原写「常规运行即失败」。实测有 2 个文件一轮连网、下一轮不连——泄漏可以是间歇性的；拿不确定的信号做常规门禁会随机变红，故常规运行只告警，硬判定留给审计模式。）
3. WHEN 以 `GT_TEST_NETWORK_AUDIT=1` 运行 THEN 清单内但本次未发生连接、且未标为间歇性的文件 SHALL 失败（提示删除该条）；清单路径不存在 SHALL 失败（守卫测试）。
4. 共享模块图模式下只拦截、不判定（迟到的异步请求可能落到下一个文件，归因不可靠）。

## R3：ACNR 目录并发请求合并

1. WHEN `listSheets` / `listCells` 以相同参数被并发调用（同一或不同 `useAcnr()` 实例）THEN SHALL 只发一次请求，所有调用方拿到同一结果，各实例的 `sheets` / `cells` / `loading` 状态正确。
2. WHEN 在途期间缓存被失效 THEN 之后的调用 SHALL 另发请求，在途的旧响应 SHALL NOT 写入缓存。
3. WHEN 在途请求失败 THEN 每个调用方各自得到降级结果 `[]`，下一次调用重新请求。
4. 公式管理弹窗以附注 / 合并工作底稿 / 合并附注 scope 打开时，ACNR 目录 SHALL 只发一次请求，且没有被取消的请求、没有「listSheets 失败」告警；以合并附注 scope 打开时，合并附注章节 SHALL 只请求一次；以附注 scope 带章节打开时，本章节用户编辑集公式 SHALL 只请求一次。

## R4：验证与文档

1. 公式目录 36 个测试文件在隔离与共享两种模式下全绿；全量前端套件对比改动前无新增失败。
2. 本 spec 登记 INDEX；tasks 只凭实测证据勾选，做不到的如实标注。
