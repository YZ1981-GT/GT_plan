# 双向回写提速后遗留问题收口 — Requirements

承接 `workpaper-sync-save-path-cpu-hotspots`（design §9）与本会话汇报的 18 个遗留问题（下称 P1~P18）。每条先复现、定根因，再修主代码、加守卫、浏览器实测。

## R1 保存过的文档 key 不得再发给编辑器（P1）

1. 文档服务器发来 status 2（最终保存）且平台回 `error 0`（incoming 已 durable，无论归组成 application、已有 application 还是 recovery case）⇒ 本次回调里的 apply（若有）结束后，该代 room 落 `closed` 并记 `closed_at`。room 已是 `superseded` / `closed` / `recovery_required` 时不动。
2. status 2 在 durable 之前被拒（回非零）⇒ room 不变（文档服务器保留未保存的修改，同 key 重开可以找回）。
3. status 4（关闭且无修改）⇒ room 不变（文档服务器没有保存这个 key，可以复用；偏离契约 `room_transition` 的理由写进 design）。
4. 关闭后再进在线编辑 ⇒ 走既有「终结代际换代」路径：新 generation、新 doc key，内容 = 当前 content version。
5. 已关闭 room 上的 apply / retry / 重驱不得因 room 状态边失败：client 基线、refresh-required、supersede 对终态 room 跳过；apply 的结果语义不变。
6. `notmodified` 的 status 2 照旧下载并 durable（契约明文「不得因 notmodified 跳过 durable」），本 spec 不改归组规则。

## R2 编辑器加载期间文档服务器的对话框必须可点，版本过期要有出口（P2）

1. 等待文档就绪（`descriptor_mounted`）时遮罩不拦截点击，只在顶部显示状态条；确认中与失败态仍然拦截。
2. 声明 `onRequestRefreshFile` 与 `onOutdatedVersion`：收到即进入可见失败态，中文提示「文档已在服务器端保存，请回到表单后重新进入在线编辑」，不自动重载。

## R3 OO→HTML apply 中断后可恢复（P14）

1. per-room apply 串行锁的加锁与解锁必须在同一条数据库连接上（现会话级锁可能在中途 commit 后换连接解锁 ⇒ 泄漏）。
2. 后台重驱：已 durable、application 停在可重入的非终态且超过阈值未更新 ⇒ 用同一协调器入口重跑（attempt + 1），单进程一次一个，多副本选主。
3. 文档服务器重发已应用过的回调 ⇒ 回 `error 0`，不得 500。
4. 回调后 apply 找不到 adapter ⇒ 失败写到 operation 上（可见、可重试），不只打日志。
5. 前端等待超时后仍能看到「重试」入口（operation 可重试时）或「刷新状态」。

## R4 启动预热与同步请求不得长时间占住事件循环（P4）

1. 模板结构指纹按文件 sha 记忆（只存哈希），entry manifest 按 (路径, mtime, size) 缓存，`SyncContract.canonical_sha256` 记忆化。
2. 回调后 apply 的注册冷建走与端点同一条带锁、写缓存的路径。
3. 预热期间事件循环最大停顿较改动前显著下降（探针实测前后对比）。

## R5 `/api/address-registry` 不得每次数秒占住事件循环（P5）

1. 序列化不在事件循环上做整包重编码。（原列的「静态 JSON 按 mtime 缓存」「自定义单元格去掉逐底稿 N+1」实测可忽略，已撤回，依据见 design D8。）
2. 与并发会话正在改的同文件（`formula-fetch-and-wp-generation-defect-closure` 的截断回报）不冲突：只改不重叠的代码块。
3. 同一请求前后实测耗时与事件循环停顿。

## R6 前端轮询不得在后端堆积（P6）

1. operation 轮询单飞：上一轮响应回来才排下一轮；出错指数退避；轮询请求不走 5xx 自动重试。
2. `GET operation` 不再每次重解析 manifest。（R4 的清册缓存之后已满足：每次请求只建一个 0.3 ms 的空注册，实测见 design D7。）

## R7 回调下载与附注刷新（P15、P16）

1. 回调下载记住上次连通的地址族，只用于对已校验地址重新排序，不放宽任何下载安全判据。
2. 底稿保存触发的附注刷新不得因占位用户 / 底稿 id 触发外键 autoflush 报错；保存事件带真实用户。

## R8 HTML 保存挂起约 5 分钟（P3）

复现并定位；与 R3.1 锁泄漏、行锁等待、浏览器连接耗尽逐一排除或坐实。坐实则修根因并加守卫；复现不出则如实记录排查过程与可观测手段。

## R9 保存链路剩余耗时（P7、P8、P9、P11、P12）

1. 线上 apply 比离线多出的 3~4 s 先拆分归因再处理。
2. 物化计划阶段复用 incoming 提取；跨请求 base 投影缓存；GC 调优；首发路径的读文件 / 提取不在事件循环上。每项给出前后实测与等价证明（摘要不变）。（前两项实测收益各约 0.8 s，都要改并发会话已暂存的核心文件并先证等价，交用户拍板，见 design D11。）

## R10 保存后先回表单、后台合并（P10）

只评估：用户感知收益、迁移与宿主接线范围、冲突与待合并态的交互代价，交用户拍板，不实施。

## R11 数据（P13、P18）

1. 和平药房 2025 D2 的 12 行幽灵骨架行：先备份，再经正常路径删除，复跑 `republish_entry_from_template.py --apply`；同项目其他只含骨架行的表逐张核对。
2. 重药安徽 D2 对账差异：逐项列出来源并给出处置。

## R12 预存测试失败（P17）

179 个相关测试文件在 HEAD 上的 379 条失败按错误签名归类：属本链路缺陷的修主代码；断言过期的按现行为修正并写明依据；环境依赖的如实标注。

## 不在范围

- 文档服务器自身加载与 forcesave 组装耗时。
- 并发会话的 address-registry 截断语义改动（只避让，不接手）。
