# 需求：程序裁剪 → 生成计划后续优化

## 背景与现状（2026-10-29 现读 / 真库只读）

承接 `trim-generation-plan-linkage` design §6.8，用户要求将六项建议逐一完成。本 spec 只收口程序裁剪与底稿生成的运行安全、数据约束、分类单源和可重复验收，不扩展到“生成前模板细裁”或“先委派后生成”。

现状事实：

- 模板集生成和按编码生成都在项目级 transaction advisory lock 内写数据库并落正式文件；69 份约 6 秒，锁直到路由 commit 才释放。
- 请求没有稳定 operation id。响应丢失后重试只能得到“已存在”，不能恢复第一次完整回执；最终 commit 失败可能留下孤儿文件。
- `procedure_instances` 真库 613 条、active 613、规范化后重复组 0，但数据库没有 active `(project, cycle, normalized code)` 唯一约束。
- 粗裁确认每次扫描 54 条已消费 preview 的 JSON；另有 71 条未消费 preview，没有当前态投影。
- active 项目分类为 NULL 15、C 3、A1 1、IPO 1；`business_category` 同时承载 A/B/C 分类与 IPO/再融资场景，`scenario` 却全部为 normal。
- 标准模板 1,025 个编码，单循环最大 B=141；明细一次只展开一个循环，但没有专项浏览器性能基线。
- 仓库有 readonly 系统/项目权限和 BrowserContext 路由拦截零件，但没有真实项目专用的只读 UAT 账号工具与零写测试基座。

## 实施裁决

1. 两阶段生成采用**持久 operation + 同一请求内同步执行 + 可重入恢复**。本轮不新增常驻 worker：正常请求仍等待最终回执；响应丢失或进程重启后，用同一 operation id 查询并在租约过期后重入。
2. Phase A 短事务锁内冻结请求、生成分流和所选编码裁剪判定摘要，提交后释放锁；文件只写同卷 staging。Phase B 再取锁、重算所选编码裁剪判定并 CAS，通过后才创建可见数据库行和提升文件。
3. 客户端生成 UUID；同 id + 同规范请求幂等，同 id + 不同请求 409。terminal operation 永久返回保存的原回执，不按当前数据库重算。
4. 模板集路径保持整批原子语义；按编码路径保持逐项失败语义。operation 服务共享状态机，但不把两条端点的前置条件和表头行为混为一套。
5. `business_category` 收敛为质控分类码（允许 A、A1~A8、B、B1~B6、C、NULL）；IPO / listed / refinancing / transfer / restructure / fraud_response 只进 `scenario`。不猜 A2/A4/A6 等详细分类。
6. 只读 UAT 的安全边界是后端 readonly + 浏览器网络 fail-closed 双层；不依赖按钮隐藏，不对真实项目执行账号自动创建或写入验收。
7. 虚拟化必须由专项实测触发。141 项达标则冻结“不实施虚拟化”；超硬门才使用项目已有 Element Plus virtual-list，不引入新依赖。

## R1 两阶段生成与幂等 operation

1.1 两个生成请求接受 `operation_id`；前端模板集生成必须提供，旧内部调用方可由服务端生成兼容 id。

1.2 operation 至少记录项目、操作者、年度、生成类型、模板集、规范请求及 SHA-256、scope revision、状态、租约、尝试次数、进度、最终回执、公开错误和时间戳；item 记录预留 wp/index id、编码、名称、循环、staging/final 相对路径、文件摘要、模板来源摘要和状态。

1.3 状态机为 `prepared → materializing → materialized → finalizing → succeeded|partial_failed`，失败分支为 `failed|stale`。状态只能前进；terminal 不能重开。

1.4 Phase A 在项目锁内重读 scope 和 wp_index，冻结四类分流及模板身份后提交。提交前不得生成文件，不得创建 `wp_index` / `working_paper`。

1.5 文件物化在锁外写 `wp_storage/{project}/.generation/{operation_id}/`；路径由服务端 UUID 构造并校验位于 storage 根内。任何异常按 manifest 精确清理，不递归删除客户端路径。

1.6 Phase B 在项目锁内重查项目可写状态、调用人 edit 权限、scope revision 和 wp_index。scope 判定变化则置 `stale`、零正式行、零正式文件；并发 operation 已生成的编码改列 existing。

1.7 最终文件使用同卷 `os.replace` 提升；DB commit 或响应失败后，同 operation 重入能识别已提升文件 / 已提交行并恢复到同一 terminal 回执，不能重复生成。

1.8 GET 状态端点按路径项目校验归属；项目 readonly 可看状态，只有原请求者或项目 edit 成员可重入。active lease 未过期不允许第二执行者领取；过期可恢复。

1.9 前端把 operation id 与规范请求摘要存 `sessionStorage`。网络错误先查状态；active 轮询，terminal 显示原回执，可恢复态用同 id 重试。切项目、弹窗 epoch 变化后旧 operation 不能控制新弹窗。

1.10 operation / item 表、状态端点和回执进入迁移、ORM、契约、OpenAPI 与路由挂载测试；不使用进程内 map 或 FastAPI `BackgroundTasks` 作为真源。

## R2 active 程序行规范化唯一约束

2.1 写入边界统一规范化 `audit_cycle`、`procedure_code`、`wp_code`：去首尾空白、英文字母大写；空程序编码拒绝。

2.2 PG 建 active 部分表达式唯一索引：`project_id + upper(btrim(audit_cycle)) + upper(btrim(procedure_code)) WHERE NOT is_deleted`，并加 canonical CHECK。迁移发现冲突时 fail-closed，不自动合并或删除业务行。

2.3 初始化、补齐、自定义新增、custom-with-template、粗裁精确查找和 resolver 共用规范化函数；唯一冲突对用户返回稳定 409，初始化并发冲突重读为幂等结果。

2.4 软删程序行仍允许同规范码新建 active 行，但既有“自定义编号不复用”和 WpIndex 占位规则保持不变；软删必须同时写 `deleted_at`。

## R3 粗裁确认当前态投影

3.1 新增每项目每循环唯一的确认投影，记录 canonical cycle、来源 preview、确认人/时间、request id、cycle revision hash 与 revision number；preview 仍是不可变历史凭证。

3.2 trim apply 成功后，在同一事务内按请求中的 distinct scope cycle upsert 投影；即使 applied=0，只要成功保存也更新确认。row-only 请求不更新。

3.3 回填仅从已消费 trim preview 的 scope entries 生成，按 `(consumed_at, id)` 稳定取最新；不从旧 scheme 或 row history 猜测。

3.4 切换读取前逐项目逐循环对拍旧扫描与新投影；不一致 fail-closed。切换后正常请求只读投影，不扫描历史 JSON。

## R4 质控分类与业务场景拆分

4.1 `Project.business_category` 只允许 NULL、A/B/C 或详细 A1~A8、B1~B6；`Project.scenario` 增加 refinancing，并限制在登记值集合。

4.2 迁移把 legacy `IPO` / `refinancing` 搬到 scenario（仅 scenario 仍为 normal 时），随后清空该 legacy 分类值；合法分类码原样保留，NULL 不伪填 C。迁移前后逐行备份可回滚。

4.3 新增单一 `ProjectClassification` resolver，输出 category code/group、defaulted、scenario、`is_ipo` / `is_refinancing` / `is_capital_market`。程序生成、模板适用性和本次触达的 IPO 判断都从 resolver 读取。

4.4 项目创建、向导保存、详情和回填正式收返 `business_category` 与 `scenario`；前端把现有“业务类型”明确为“报告模板类型”，新增“质控业务分类”和“专项场景”。非法值 422，保存刷新后逐值一致。

4.5 客户端 query 不得自由覆盖项目分类。迁移期保留旧字段兼容读，但新增守卫禁止新增首字母 / substring 私有判断；已知旧读者形成只许减少的清单。

## R5 真实项目只读 UAT

5.1 新增正式脚本 `provision_readonly_uat_user.py`：默认 dry-run；apply 必须显式 project id、重复确认值和从环境/交互输入的密码。只创建/校验 `UserRole.readonly` 与目标 `ProjectUser(readonly, readonly)`，不改 StaffMember、ProjectAssignment 或业务表。

5.2 同名非 readonly、已有更高项目权限、项目不存在/已删除、确认不一致均拒绝；提供精确撤权命令，只软删该成员关系并停用专用账号。

5.3 前端权限矩阵显式识别 readonly，资源操作只保留 view/export 中后端确实允许的动作，不能降级成 assistant。

5.4 新增独立 Playwright 配置和 BrowserContext 级网络守卫：固定 `127.0.0.1:3030`、禁 Service Worker/WebSocket、无 global seed、无 trace/screenshot/video；除登录外任何 POST/PUT/PATCH/DELETE 都 abort 并使测试失败，未知 GET 也 fail-closed。

5.5 真实 UAT 参数全部来自环境变量，缺失即 skip/拒绝，不回退到 admin、第一个项目或硬编码 UUID。测试前后以请求记录和后端日志只读核对双证明确认零业务写。

## R6 生成计划明细性能裁决

6.1 新增固定 141/250/500/1025 项的浏览器性能夹具，必须断言真实渲染项数和 detail=1，不能空跑。

6.2 测量冷/热展开 click-to-two-RAF、Long Task、120 帧滚动和 DOM 节点数；桌面 1440×900 与窄屏 390×844 分开报告，workers=1、retries=0。

6.3 141 项发布硬门：展开 p95 ≤200ms、max ≤300ms、无 >100ms Long Task、平均滚动 ≥30 FPS、p95 frame ≤33.3ms。连续两轮超任一门才实施条件虚拟化。

6.4 若达标，保持当前单展开 + 普通列表并把“不虚拟化”写入测试和验收；若超标，只虚拟化展开明细，阈值由曲线决定，不改循环 checkbox，不引入新 npm 依赖。

## 非功能与验收

- 迁移号实施前同时现扫本地与 origin；每个 V 有配对 R，DDL 幂等，冲突 fail-closed。
- service 只 flush，路由 / operation 编排统一 commit；DB 与文件系统补偿必须有故障注入测试。
- 真实项目只读；所有写入验收只限名称带【测试】的项目，并经平台路径清理。
- 后端 SQLite + PG 并发/迁移/故障测试，前端 vitest + scoped vue-tsc + ESLint，契约/OpenAPI，磁盘变异和 Playwright 实测。
- 不新增依赖；UI 用户可见文字中文；不提交、不推送，除非用户另行要求。
