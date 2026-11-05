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

- [ ] 9. 三件如实标注项逐一收口（2026-11-01 续做，详见 design §9）
  - [x] 9.1 第一件根因排查：候选后端起不来 ≠ 没做；定位三个 HEAD 级 P0（均非本 spec 引入）
        —— `adjustment_import.py:82` 漏 import `require_project_permission`（`app.main` 导入即
        NameError）· `ThreeColumnLayout.vue` 重复 import `useMountOnFirstOpen`（前端 500）·
        三组迁移撞号。修完 `app.main` 导入通过（2619 条路由）、候选后端 9981 / 前端 3032 起来
  - [x] 9.2 迁移撞号按"改未应用的那一侧"处置：删 V233 的 display_preferences 残留 + 配对 R233；
        display_preferences → V250、formula_provenance → V251；同步改模型版本注释与按文件名
        钉死的测试。`scan_migrations` 248 个最高 251 无重复，4 条既有撞号守卫由红转绿
  - [ ] 9.3 共享库 `audit_platform` 应用 V235~V251（**待用户放行**，属共享记账类写操作）；
        现算只有 `projects.amount_unit`（V250）落在 OO 往返路径上（`GET /api/projects/{id}`
        恒 500 ⇒ 年度闸门不渲染）。本轮已用 `GT_BOOTSTRAP_DONE=1` 确保未改共享库 schema
  - [x] 9.4 第二件：D4-8 / D4-33 / D4-34 / D4-36 逐个按**各自真实载荷形态与身份键**的最小
        非空基线实测——空投影下 `applied=0` 且基线逐字段原样带回；新守卫 17 例，并加
        "手写基线的键必须等于 merge 自己产出的键"防漂断言（前三版判据全是夹具误报）
  - [x] 9.5 第三件残留 1：flag 闸门改注册表不变量（每个 dedicated item_id 必须在本 adapter
        声明的 store item 集合里，现算 7/7）；stale 注释改勘误说明
  - [x] 9.6 第三件残留 2：K1 载荷是 dict 却接到 rows 分支，该分支 `isinstance(parsed, list)`
        使 dict 基线留 `[]` ⇒ **每次镜像清空既有行与未受管标量**（真库 0 行，潜伏缺陷）。
        改 `merge_state_fn="merge_k1_from_projection"` 并删永不执行的 `dedicated_items`；
        按运行期解析全仓扫 69 个 rows 分支 plan，K1 唯一一例、零无法解析
  - [x] 9.7 第三件残留 3 / 4 / 6 / 7：`FOR UPDATE` 合并为一条 `ANY(:ids)`（46 item 时
        92 → 47 次往返）而 advisory lock 保持逐条有序 · 屏障文案摊进真实原因并暴露 `reasons` ·
        14 个文件 15 处裸 PUT 补 `_dedupe: false` · F2 保存事件加同步 `accept()` 回执
  - [x] 9.8 第三件残留 5（14 个 G formData 迁 strict CAS）
        - 14 家（G1 / G3 / G4 ECL / G4 SPPI / G5 / G6 main+SPPI / G8~G14）全部接入
          `createChecklistCasClient`：GET 回执先 `remember` 版本，所有 checklist 保存经 helper 带
          `require_if_match=true`、已有行带 `if_match`、成功只从服务端回执推进版本；直连
          `api/http.put(...checklist-responses)` 为 0。
        - 五家有网络退避的 formData 对 4xx（409 / 428 / 423 / 422）先停止并抛出，不再把同一
          陈旧版本重试三次；网络/5xx 保留原退避。`isNonRetryableChecklistSaveError` 单测覆盖。
        - R1.3 的 14 项 LWW 豁免清单已清零；strict 覆盖守卫扩到全部调用面，pending 屏障守卫
          同时反查 helper / remember / 零直连 PUT / 4xx 先于退避，防止任一调用方退回兼容写法。
        - 证据（2026-11-05 最终复核）：前端 strict/pending + 草稿身份边界 **12 files / 153 passed**；
          后端 strict CAS / render-snapshot 契约 **17 passed**；相关 Python Ruff 通过；ESLint **0 error**
          （4 条既有 warning）。语义审查 High / Medium / Low 均为 **0**；`git diff --check` 通过。
          区域 `tsc` 仅报 2 个未改 G7 依赖文件的 3 条既有类型债，本轮改动路径零新增；
          浏览器验收仍归任务 6（受 9.3 共享库迁移阻断）。
        - 顺带收口草稿会话边界：G7 main / 子公司 / 权益法、H10、存货与固定资产监盘均改为
          `sessionStorage.user.id` 分区；本地与真实跨窗口 logout 同步清理新旧敏感键。
  - [x] 9.9 顺带解决两条预存红：`migration_drift_ledger` 的 V200 / V201 条目对应文件已按裁决
        移除，台账加可伪证的 `file_removed` 并断言"确实不在磁盘上"（原判据对已移除条目恒红）
  - [x] 9.10 回归与变异（重放树 = 最新远端 + 本轮）：前端 rc=0、后端 488 passed、
        真实 PG 107 passed、6 条变异逐个 RED 且逐字节恢复；ruff 32 errors 为预存（干净 HEAD 33）

- [ ] 6. 浏览器验收
  - [ ] 6.1 【测试】项目在 HTML 修改后立即切在线编辑，OO 显示新值
  - [ ] 6.2 注入一次保存失败，确认保持 HTML、错误中文可见且零 materialize；恢复后可重试
  - [ ] 6.3 OO 修改后回表单并刷新，HTML / API / 已发布 representation 三方一致；恢复验收数据
  - [ ] 6.4 后端侧 OO 往返浏览器实测（**被 9.3 阻断**：共享库缺 V250 使项目详情恒 500）
  - [ ] 6.5 D4-8 / D4-33 / D4-34 / D4-36 四表浏览器必测（同上阻断）

- [ ] 7. 收尾
  - [x] 7.1 语义审查并修复高优先级发现（第一轮 P0/P1 已闭合；第二轮 P1-1~P1-3 见任务 8）
  - [x] 7.2 更新 INDEX / memory（memory 精简至 299 行），锁定分离头候选树复跑关键验证
  - [x] 7.3 只提交本 spec 文件与改动块；同步远端后按版本工具推送当前分支
        —— 单提交 `68458e2e3`（41 files，+871/-195）+ 附注标签 **v1.0.98**，已在远端
        `spec/disclosure-note-doc-upload-and-batch-fill` 核对一致。推送前远端前移两次
        （`a77026baf` → `61997c4fc` → `79d07ccad`），各变基一次并在变基后重跑验证：
        前端 14 files / 116 passed、后端 488 passed、真实 PG 107 passed、ruff 32 F401
        全部落在只改了注释的三个文件里（预存）。pre-push 对分离头跳过其余检查，
        已手工补跑 `check_staged_tree_self_consistency.py`（26207 个文件，2 道门 exit 0）
