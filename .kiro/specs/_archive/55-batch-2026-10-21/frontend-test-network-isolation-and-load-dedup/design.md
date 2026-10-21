# 设计文档：前端单测网络隔离与并发加载合并

> 关联：#[[file:.kiro/specs/frontend-test-network-isolation-and-load-dedup/requirements.md]]
> 锚点用符号名，不写死行号。

## 1. 拦截点：`net.Socket.prototype.connect`

- jsdom 25 的 XHR 在 `helpers/http-request.js` 里每次调用时 `const { request } = http`，经 `http.Agent`（keepAlive）建连，最终落到 `net.Socket.prototype.connect`；WebSocket（`ws`）和 Node http 也落到这里 ⇒ 一处覆盖全部传输。
- 不替换 `XMLHttpRequest`：要自己模拟 readyState / 事件序列，还要碰 jsdom 内部 impl。不改 axios adapter：只管得到 axios，管不到原生 XHR / WebSocket。
- 失败方式：把连接目标改成一个不存在的本地管道（Windows `\\.\pipe\gt-unit-test-no-network-<pid>`，其他平台 `/nonexistent-gt-unit-test/<pid>.sock`），仍由原始 `connect` 发起，由 libuv 异步返回 ENOENT。这样错误走 Node 正常的异步路径：`ClientRequest` 已挂好 error 监听，也不依赖 `setTimeout` / `setImmediate`（用例开了假定时器照样失败）。对 axios 而言它和 CI 上的 ECONNREFUSED 同为 Network Error。
- 安装幂等：在 prototype 上打 `Symbol.for('gt.test.networkGuard')` 标记；记录状态挂在 globalThis 的同名 symbol 上，setup 每个文件开头清空本文件的记录。

## 2. 记录与判定

- 每次被拦截的 connect 记录 host / port / path 与当时的 `testPath`、`currentTestName`。jsdom 每个文件新建窗口，setup 每个文件给 `XMLHttpRequest.prototype.open` 补一层记录（method + URL），只用于报错信息。
- 判定写成纯函数 `decideNetworkVerdict`（输入：本文件相对路径、拦截记录、清单、是否隔离、是否审计）→ `ok` / `new-leak` / `stale`，单独单测。
- setup 在每个文件的 `afterAll` 里调用：只有「本 worker 执行的第一个文件」才判定（默认 isolate 下每个文件独占新进程，恒为第一个）；共享模式第二个起的文件只拦不判。
- 判定结果的处置：常规运行 `console.warn`，`GT_TEST_NETWORK_AUDIT=1` 时抛错让本文件失败。
- 清单 `src/test/networkLeakInventory.json`：`files: { 相对路径: [端点证据, …] }`（键按字母排序）+ `intermittent: { 相对路径: 原因 }`（审计模式不判 stale）。守卫 spec 校验：只能是 2026-10-19 基线 25 个文件的子集、路径真实存在、证据非空、键已排序、间歇性条目必在 files 里且写明原因。

### 2.1 实施期发现：泄漏可以是间歇性的（据此改了判定处置）

- 首版设计「常规运行发现新泄漏即失败」。按清单跑审计模式时，`GtA121LegalConfirmation.pbt.spec.ts`、`GtA271ItAuditMemo.spec.ts` 判成 stale：探针那轮各连了 1 次，审计这轮 0 次。
- 两个组件都在 `onMounted` 里 `await import('@/services/apiProxy')`，用例 mock 了这个模块。推断机理：多个实例（PBT 连续挂载、或相邻用例的实例）并发 import 同一个被 vi.mock 的模块时，vitest 的 mocker 让第二路绕过 mock 走真实模块（与 `formula-manager-runtime-integrity-closure` 复验时 noteListFormulasWiring 的成因同型）。这条是推断，依据是代码形态 + 一连一不连的观测，没有单独复现。
- 结论：「是否连网」对这类文件不是确定的信号。拿它做常规门禁会随机变红，比没有门禁更糟；所以常规运行只告警，硬判定放在审计模式；这两个文件标为间歇性，不参与 stale 判定。拦截本身不受影响：不管走不走 mock，真实连接都会被拦下。

## 3. ACNR 并发合并下沉到 `useAcnr`

- 请求和模块级缓存都在 `useAcnr`，所以在这一层加模块级在途表（`listSheets`、`listCells` 各一张），键 = `${缓存纪元}:${缓存键}`。7 个调用方一起受益，弹窗的 `loadAcnrTree` 不用改。
- 写缓存前比对纪元：在途期间若被 `invalidateModuleCache`（纪元 +1），结果只交给已经在等的调用方，不回写缓存（原实现会把失效前的旧目录写回缓存，最长存活一个 TTL 即 5 分钟）。
- 在途 Promise 落定后（成功或失败）从表中移除；清理用 `then(clear, clear)`，避免派生 Promise 产生未处理拒绝。
- 每个调用方自己的 `loading` / `sheets` / `cells` 仍在各自的 try / finally 里设置；失败时各自 `console.warn` 并返回 `[]`（行为不变）。

## 4. 弹窗私有的加载函数（合并附注树、本章节用户编辑集）

- `loadConsolNoteTree` 的请求是弹窗私有的 `api.get(P_cn.list(模板))`，没有共享缓存层 ⇒ 沿用弹窗里已有的 `createKeyedSingleFlight`，键 = 模板类型（与请求参数一致）。
- `loadNoteUserFormulas`（任务 8 浏览器实测发现）：附注 scope 带章节打开时，`applyNoteScopeTarget` 预取一次（不 await），定位到章节叶子后 `onTreeNodeClick` 再调一次。函数里「已加载就跳过」的判断要等第一发返回才生效 ⇒ 同样用 `createKeyedSingleFlight`，键 = `${项目缓存键}|${章节}`（项目缓存键含项目 / 模板 / 年度，与请求地址的维度一致）。原函数改名 `fetchNoteUserFormulas`，逻辑不变。
- 既有守卫 `noteListFormulasWiring.spec.ts` 断言「打开只调 1 次」，但它的 mock 立即返回，第一发在第二次调用之前就已落定，测不到并发；新例把响应挂起到断言之后。

## 5. 不做的事（ROI 判断）

- **不给 25 个泄漏文件补 mock**：拦截后这些请求与 CI 一样立刻失败、走组件既有的降级分支；补 mock 只是把「网络错误」换成「mock 响应」，功能收益低。改动面 25 个文件、约 8 个业务域，多数属于其他工作流，冲突风险高。冻结为清单，修一处删一条。
- **不改 `utils/http` 的 GET 去重语义**（取消先发 → 合并在途）：全局行为变化，影响面超出本 spec。
- **不加「放行网络」开关**：目前没有需要真实网络的单测（两个被 vitest 收集的 Playwright 规格在导入期就失败，是另一个问题）。

## 6. 验证矩阵

| 层 | 必须证明 |
|---|---|
| 拦截守卫 | 本地回环服务器：拦截开着收到 0 次连接、请求以网络错误结束；临时换回原始 connect 后收到 1 次（变异反证）；开着假定时器也照样失败 |
| 判定纯函数 | new-leak / stale / ok / 共享模式不判 |
| useAcnr | 同参并发只请求一次、不同参各一次、在途失效不回写、失败后能重新请求；去掉合并即打红 |
| 弹窗挂载 | 附注 / 合并工作底稿 scope 打开时 ACNR 请求 1 次；合并附注 scope 章节请求 1 次；附注 scope 带章节时本章节用户编辑集 1 次；去掉合并即打红 |
| 浏览器 | 同一套数据、同一个对照服务，改动前（HEAD）与改动后（工作树）各跑三个入口，见 §7 |
| 全量 | 隔离模式全量对比改动前基线；审计模式跑清单内 25 个文件：23 个确定性条目全部仍泄漏、2 个间歇性条目不判；公式目录隔离 + 共享全绿 |

## 7. 浏览器对照实测（2026-10-19，任务 8）

方法：

- 3030 是并发会话在用的开发服务（带 HMR），不在它上面改源码做对照。另起 3031 对照服务（临时 Vite 配置，用完已删）：load 钩子在内存里把 `useAcnr.ts`、`FormulaManagerDialog.vue` 换成 HEAD 版本（改动前），或直接用工作树版本（改动后），不改任何源码文件；两种模式都在 `listSheets` 入口记录调用栈（同样只在内存注入）。独立 cacheDir（TEMP 下）、关 HMR、关 d.ts 生成；事后核对 `auto-imports.d.ts` / `components.d.ts` 哈希与修改时间未变。
- 浏览器用 chrome-devtools。Playwright 浏览器与并发会话共用，实测当前标签页会被对方的导航带走（新开的标签页被导航到了对方的页面）。页面初始化脚本记录全部 `/api/` XHR（起止时间、是否被中止）和相关 `console.warn`。
- 数据：附注 = 重药控股安徽有限公司_2025，选「货币资金」；合并工作底稿 / 合并附注 = 【测试】附注批量集团有限公司_2025（68e16afa）。只读操作，未编辑、未保存。

| 入口 | 改动前（HEAD） | 改动后（工作树） |
|---|---|---|
| 合并工作底稿 | `listSheets` 同一 tick 调 2 次（打开 watch + `applyConsolWorksheetTarget`）；ACNR XHR 1 个；告警「[useAcnr] listSheets 失败 canceled」 | `listSheets` 调 2 次，ACNR XHR 1 个，0 告警 |
| 合并附注 | `listSheets` 调 2 次（打开 watch + 末尾 `applyTargetNode()`，晚约 60 ms）；ACNR XHR 2 个，先发那个被中止；同一告警 | `listSheets` 调 2 次，ACNR XHR 1 个，0 中止，0 告警 |
| 附注（带章节） | `listSheets` 只调 1 次（ACNR 先于附注树返回，定位时目录已加载）；附注树 XHR 2 个、本章节用户编辑集 XHR 2 个，各中止先发那个 | 所有请求各 1 个、0 中止、0 告警；弹窗定位到「货币资金」 |

- 改动后第一轮附注入口里，本章节用户编辑集仍是 2 个 XHR、中止 1 个 ⇒ 补了 §4 的 `loadNoteUserFormulas` 单飞后重跑，降为 1 个。
- 网络面板的请求数不是可靠判据：合并工作底稿入口改动前后都只有 1 个 ACNR XHR（先发那次在发出前就被取消）。判据用「被中止的 XHR」和「listSheets 失败」告警。

顺带发现（不在本 spec 处理）：

1. HEAD 版弹窗引用了 `P_cn` 却没有导入：`loadConsolNoteTree` 一调用就抛 ReferenceError，被 `catch` 静默吞掉 ⇒ 合并附注树在弹窗里从不加载。HEAD 下三个入口里弹窗都没有发出合并附注章节请求，改动后的工作树有。工作树里的未提交改动已补上 `consolNoteSections as P_cn` 导入；它必须和本 spec 的改动一起提交，否则 §4 的合并附注树单飞没有对象。类型检查能抓到这类问题，但全量 vue-tsc 在本仓库会 OOM，目前没有门禁兜底。
2. 合并附注页（ConsolNoteTab）在点「公式管理」后约 60~120 ms 会再拉一次合并附注章节 + 合并附注公式。它与弹窗自己的请求先后发生、不互相取消，属于页面行为。
