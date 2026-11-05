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
  - [x] 9.3 共享库 `audit_platform` 迁移只读预检（原计划应用 V235~V251；**无需执行写入**）
        —— 2026-11-05 以 PostgreSQL 只读查询确认 `schema_version` 已含 V235~V251 及 V261~V263，
        V235/V236/V250/V251/V261/V262/V263 的候选树规范化 checksum 与登记值逐项一致，
        `schema_migration_failures=[]`，`projects.amount_unit` 与两个 V250 CHECK 均已存在，vector 0.8.5
        已安装。故没有备份、回退或 migration 写入动作，6.4/6.5 的 V250 缺列阻断解除；另见平台 spec
        Task 24：V233/V234 为既有 checksum 漂移，未经用户批准不改共享记账。
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
          共享库迁移阻断已由 9.3 只读预检解除。写入型浏览器验收仍归任务 6，须先获得用户授权。
        - 顺带收口草稿会话边界：G7 main / 子公司 / 权益法、H10、存货与固定资产监盘均改为
          `sessionStorage.user.id` 分区；本地与真实跨窗口 logout 同步清理新旧敏感键。
  - [x] 9.9 顺带解决两条预存红：`migration_drift_ledger` 的 V200 / V201 条目对应文件已按裁决
        移除，台账加可伪证的 `file_removed` 并断言"确实不在磁盘上"（原判据对已移除条目恒红）
  - [x] 9.10 回归与变异（重放树 = 最新远端 + 本轮）：前端 rc=0、后端 488 passed、
        真实 PG 107 passed、6 条变异逐个 RED 且逐字节恢复；ruff 32 errors 为预存（干净 HEAD 33）

- [ ] 6. 浏览器验收
  - [x] 6.0 无写入主链烟测（2026-11-05）——以【E2E】公式管理运行时门禁_2025
        (`b71db997-0bca-4528-9a03-0b92e6a6b4e0`，2025) 登录后访问项目、TB、底稿列表、
        报表、附注与交付中心；每次导航前注入拦截器，拒绝 `GET/HEAD/OPTIONS` 以外的请求。
        页面均正常渲染：TB 为 0 个科目、底稿列表为 2 张、报表加载 129 行、交付中心显示
        缺失交付物的非阻断空态。空项目的报表页 `notes-tree` 查询和附注页
        `GET /api/disclosure-notes/{project}/{year}` 均返回 404，浏览器保留对应的资源加载日志，
        但页面均接住为空态；附注展示“附注数据不存在”并弹出“生成附注”确认框，已点击取消，
        未触发生成。平台业务 API 实际请求均为 GET，未观察到 POST/PUT/PATCH/DELETE；拦截日志中的
        POST 仅为浏览器注入的 Kaspersky 外部遥测。Element Plus 两条既有 warning 未影响页面。
  - [x] 6.1 【测试】项目在 HTML 修改后立即切在线编辑，OO 显示新值（2026-11-05）
        —— 候选 3032 / 9981，【测试】公式同步乙有限公司_2025 的 D4
        (`d7fa0522-12b3-4e43-b7d4-5242562e6fd3`，entry `xlsx/gt-d4-operating-revenue`)。
        该 entry 原无 representation，首版经 `ensure_first_publication` 正式发布
        (`content_revision=1`)，definition 链经 `fix_task76_provision_projection_definitions.py
        --apply` 正式 provision（+3 artifact / +1 bundle，非手工插表）。
        HTML 侧把 D4-8 产品A 1月销量改为 202 后切在线编辑，在 OnlyOffice iframe 内以
        `#ce-cell-name` 定位 `B16`、`#ce-cell-content` 读回 **202**，证实 HTML 值进入 OO。
  - [x] 6.2 注入一次保存失败，确认保持 HTML、错误中文可见且零 materialize；恢复后可重试（2026-11-05）
        —— 四条判据逐条实测通过（D4-8，产品A 1月销量）：
        ① 中文错误可见：`el-message el-message--error`、文案「保存失败，请稍后重试」；
        ② HTML 保留：失败后单元格仍是新值 210，未回滚、未清空；
        ③ 零 materialize：整个失败窗口内 `materialize` 请求 **0** 次（只有 1 次
           `PUT …/checklist-responses` 且其 `error` 事件确凿触发）；
        ④ 恢复后可重试：恢复网络、再次编辑即成功落库（`revQty=211`，10:21:06）。
        🔴 **两条测量纪律（本轮各踩一次，判据差点写反）**：
        · **假注入**：`xhr.dispatchEvent(new ProgressEvent('error'))` **不被 axios 消费**
          （console 零 Network Error、前端无任何反应）⇒ 用它得出的「无错误提示」是假结论。
          真实失败必须用 CDP `Network.emulateNetworkConditions` Offline。
        · **读太晚**：`ElMessage` 3 秒自动消失，事后查 DOM 必然查不到 ⇒ 提示类判据必须用
          `MutationObserver` 从操作前开始录，不能操作后再查快照。
  - [ ] 6.3 OO 修改后回表单并刷新，HTML / API / 已发布 representation 三方一致；恢复验收数据
        🔴 **现无任何路径可通**（2026-11-05 实测，非「等环境」）：在 OO 内把 `B16` 改成 303
        并 forcesave 后，`oo_to_html` operation `11809f53-a34e-44fc-8182-efc5bc68e019` 落
        `state=conflict` / `conflict_count=24`，303 回不到 HTML。两个缺陷叠加，见 6.6 / 6.7。
        该 operation **按决策不裸改**（裸 SQL 结算会破坏版本链与审计链），如实留在测试项目
        作缺陷证据。
  - [ ] 6.4 后端侧 OO 往返浏览器实测
        🔴 被 6.3 同一条链挡住：OO→HTML 的 merge 跑的是**整 entry 的 combined projection**，
        D4-32 必产生的 24 条冲突对本 entry 任何 sheet 的回写都成立。
  - [ ] 6.5 D4-8 / D4-33 / D4-34 / D4-36 四表浏览器必测
        🔴 同上 —— 四表都在 `xlsx/gt-d4-operating-revenue` 内，共用同一次 merge。
        （四表各自的**非破坏性 merge** 判据已由 9.4 的 17 例离线守卫覆盖，不受此阻断影响。）

- [ ] 6.6 缺陷登记：D4-32 同步建模三面皆错（阻断 6.3/6.4/6.5 之一）
  - openpyxl 逐格实测 `D/D4 收入底稿.xlsx` 的 `客户、供应商等资金流水检查D4-32`：
    `A11` 表头逐字是**序号**；`A13..A46` 里 **24** 格是整数、5 格是「……」、5 格是组标题行空格
    （6 组数据槽 5/5/2/2/5/5 = 24，与 24 条冲突逐一对应）；6 个分组标题在 **B 列**
    (`B12/B19/B26/B30/B34/B41`)，不在数据行上。
  - 面 A（OO→HTML 恒冲突）：`phase5_d4_ipo_interview_sheets._SHEETS['D4-32'].fields` 把 A 列
    声明为 `("group_label", "A", "editable", "text", "groupLabel", "分组")` —— `header_text`
    与模板的「序号」不符，且那 24 个整数在 `value_type=text` 下 `merge.normalize_value` 抛
    `ValueNormalizationError` ⇒ 每次保存恒产 24 条 `type_normalization_failure`，而三侧
    (base/current/incoming) 同为整数、本该判 `kept_current`。
  - 面 B（HTML→OO 清空模板序号）：六组业务行的 store 无 `groupLabel` 键（前端 `FlowRow` 只有
    id/name/amount/ratio/bank/account/method/hasAnomaly/indexRef）⇒ 投影恒 `None` ⇒
    materialize 把 A 列序号写空。
  - 面 C（一有数据就打挂整个 entry）：真实 store 是六段分组 `[{key, rows}]`，而 `_rows()`
    按扁平行数组解析 ⇒ 实测抛 `ValueError: D4-32 缺稳定身份` ⇒ store-projection 422 ⇒
    **整个 D4 entry 进不了在线编辑**；回写侧 `merge_projection_into_store` 又返回扁平数组，
    前端 `D4TabFundFlow.loadData` 的 `!Array.isArray(group.rows)` 会把六组全判空 ⇒ 镜像一次
    清空 D4-32。**当前未炸只因测试底稿的 D4-32 是空表。**
  - 影响面已现算：共享库里 `xlsx/gt-d4-operating-revenue` **只有**上述测试底稿有已发布
    representation，真实业务项目 **0** 条 ⇒ 修它在数据层只需重 provision + 重发布这一张。
  - 🔴 本轮**未改**：正确修法要重做投影/回写、按模板基线区分「模板内容」与「用户填在模板空行
    的内容」（否则 `B19='主要客户'` 这类组标题会被当业务行写进 store）、未归属新行落
    `__unknown__` 走前端已有人工映射，并连带刷新契约 / `_sync_provider_golden_digest.json` /
    单趟反证基线（`TEXT_VICTIM=d4_32_groups`、`TEXT_VICTIM_CHANGED_FIELDS=24`、
    `EXTRACTED_FIELD_COUNT=218`）与 harness `_text_safe` 退役。按「>3 组件 / 跨前后端 / 改冻结
    契约先写 spec 三件套」的铁律，应另立 spec。试探性改动已逐字节回退（契约 digest 仍
    `75fca57d9d2c9bf1…`）。

- [ ] 6.7 缺陷登记：**平台级** —— schema 冲突一律无法人工裁决（阻断 6.3/6.4/6.5 之二）
  - 实测（候选 3032，经真实前端 `workpaperSyncApi.getOperationConflicts`）：同一条冲突 item 上
    `suggested_action: "manual_merge"`（让人工合并）与 `adjudicable_by_value_choice: false`
    （不许按值裁决）**同时成立**，且 payload 里没有 `schema_anomaly`。
  - 三处合成死路：
    ① `working_paper_sync_conflict` 表**无 `schema_anomaly` 列** —— merge 判定的 anomaly 落库即丢；
    ② `conflict_resolution.py:680` 的 preview 判据是 `return self.kind is not ConflictKind.schema`
       —— 把**所有** schema 冲突一律判为不可裁决；
    ③ 而域内 `conflicts.py:165` 是按 anomaly 分两类的，`type_normalization_failure` /
       `multi_location_divergence` 明确「可以由人选一个值收敛」。
  - 后果：前端面板把这些项从所有批量范围排除、单条也不给选边，真去 resolve 会撞
    `StructuralConflictNotAdjudicableError`。**与 D4-32 无关，对任何 entry 的任何 schema
    冲突都成立** —— 一旦落库就再也救不回来。同一判据两份实现、口径分叉。
  - 顺带：`useWorkpaperSyncBridge.resolveConflicts` 的注释称 `room_latest_durable_*`
    「在当前 16 条用户路由里没有任何读取面」**已过期** —— `GET /operations/{id}` 自 Task 32
    起就返回这两项（`_fold_observability_facts`），缺口在冲突面板没去读。

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
