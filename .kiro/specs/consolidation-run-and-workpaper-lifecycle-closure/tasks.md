# 实施计划：合并运行与底稿生命周期收口

> 执行纪律：全部任务（含 `*`）都做；只有外部压测环境/真实业务数据可如实保留 `[ ]*`。临时产物统一放仓库根 `tmp_consol_lifecycle/`；不改真实项目；迁移号实施时按磁盘、origin、共享库三路现取；每批验证候选树而非脏主工作树；最终一个 commit，经版本工具推送当前分支。

## 批 0　基线、契约和重叠治理

- [ ] 0.1 固化现状清单：动作语义、dirty、四表双源、页面/导出、快照 capturer、运行记录、附注来源、WorkingPaper/证据，保存可复现探针输出。
- [ ] 0.2 与 `formula-provenance-envelope`、`formula-writer-ownership-and-stale`、`attachment-platform-cross-module-closure` 建单向依赖和共享枚举/接口，不复制其真源。
- [ ] 0.3 建跨语言契约：operation、version vector、readiness、projection、artifact、snapshot manifest；生成 JSON Schema/OpenAPI 子集并支持 `--check`。
- [ ] 0.4 加入失败注入清单和基线测试；确认现有合并全链、映射、附件/归档测试在候选基线的真实通过/失败集合。

## 批 1　前端动作真语义与编辑保护

- [ ] 1.1 删除“转换规则”假写入和无效范围模板成功提示；年度/准则改为只读项目口径，并提供去项目设置入口。
- [ ] 1.2 节点按钮改名“重新读取”，删无效 worksheet 选项；所有计算按钮只调用 operation API并显示真实回执。
- [ ] 1.3 新建 `useConsolWorkspaceGuard`/draft registry，统一 registered sheet、dirty epoch、pending save、上下文和离页三选一。
- [ ] 1.4 接入所有 worksheet 子表：首次加载骨架并禁编辑，重载/切项目年度节点/公式变化前处理 dirty；错误保留旧数据。
- [ ] 1.5 合并附注“查看”改调 `leaveNoteEdit`，scope 切换也走统一 guard；保存中编辑、A-B-A 和请求取消继续有效。
- [ ] 1.6 统一主视图 loading/error/empty/stale/readonly 五态；权限与锁状态前置禁用并给中文原因。
- [ ] 1.7 前端单测、单区域 vue-tsc、键盘与 1280/1024/768 布局验收；变异证明假成功和丢编辑会打红。

## 批 2　持久 operation、上下文和版本向量

- [ ] 2.1 动态取迁移号，新增/回滚 `consol_operation` 与约束/索引；ORM、schema、service 三层一致。
- [ ] 2.2 实现 canonical request hash、幂等键、version vector/digest 和 `ConsolContext.run_id` 构建/验证。
- [ ] 2.3 实现 claim、active/pending 合并、revision CAS、lease/heartbeat、stale/cancel/reclaim 和步骤/metrics 更新。
- [ ] 2.4 新 operation 路由及 readonly/edit 鉴权；对象归属、年度、归档、合并锁检查和错误码契约。
- [ ] 2.5 `refresh-all`、手工 push、审批/撤销、公式变更接同一 operation；旧 API/status/SSE 保持兼容并带 operation_id。
- [ ] 2.6 后台 worker 改持久 claim；重启恢复、TTL/清理、优雅停机和同项目年度单飞。
- [ ] 2.7 真实 PG 双会话验证幂等、CAS、lease 抢占、旧 revision 不晚写；进程终止四阶段恢复验证。

## 批 3　计算复用、四表 projection 与版本化草稿

- [ ] 3.1 `recalc_full/recalculate_trial/generate_consol_reports` 接可选 CalcBasis，operation 每 target 只建一次 tree/context/basis。
- [ ] 3.2 `push_targets` 改一次预载/递归 CTE；记录 N/A/D 与各阶段耗时、读取/写入行数和锁等待。
- [ ] 3.3 实现四张抵销后表 canonical projection，自动列只读，manual override 显式分离；移除 `elimEquity/elimIncome` 骨架消费。
- [ ] 3.4 恢复并持久化 post_invest/post_income/minority/capital 完整手工字段；旧保存格式兼容读取一版。
- [ ] 3.5 Python 实现 worksheet→canonical groups，与前端现有 builder 全样本逐值对拍；发现差异先按会计口径裁决。
- [ ] 3.6 新预览/生成端点按 `expected_versions + preview_token` 现读工作表；分录写 `source_version/source_digest`。
- [ ] 3.7 前端生成只传版本向量；预览后变化 409 保持草稿零写；已提交/已审批不覆盖。
- [ ] 3.8 回归 approved/draft/orphan/分公司/多级集团与四表等式；真实 PG 竞争生成只有一方成功。

## 批 4　报表正式运行与不可变 artifact

- [ ] 4.1 实现 `formula-provenance-envelope` 报表域最小共享产物：`report_generation_run`、`financial_report.run_id/provenance`，不建同义表。
- [ ] 4.2 operation 报表阶段创建 report run、写根节点正式行和来源信封，失败行不覆盖旧正式版本。
- [ ] 4.3 报表 API 增 published/preview；页面默认 published，预览显式提示未发布，缓存键含 operation/run。
- [ ] 4.4 合并专用导出从指定 report run 读取；根/非根语义明确，逐格对拍页面与下载。
- [ ] 4.5 新增 `consol_artifact`、版本化存储和 hash；四 Sheet 临时生成端点改为一次生成、重复下载不重算。
- [ ] 4.6 合并工作底稿包改读企业树和统一 operation，包含范围、编制表、分录、试算、对账、报表、附注摘要与 manifest。
- [ ] 4.7 报表/导出/底稿 hash、失败恢复、无 run 禁止正式导出的 PG 与端点测试。

## 批 5　合并附注来源投影、自动汇总与 readiness

- [ ] 5.1 动态取迁移号，为 `consol_note_data` 增来源投影字段；共享 source/stale 枚举与 owner spec 对拍。
- [ ] 5.2 所有公式填入、明细 apply、子树汇总、手工保存更新 source projection/digest；手工与锁定格保持最高优先级。
- [ ] 5.3 公式/映射 owned-cell 交集校验，消除“最后点击者覆盖”；mixed 章节可逐格解释来源。
- [ ] 5.4 一键 operation 对 confirmed+fresh 映射自动 reaggregate；stale/未确认/无来源形成结构化待办。
- [ ] 5.5 批量加载目标章节公式和单体附注；保留每章 SAVEPOINT，SQL 数对章节 S 的斜率为 0。
- [ ] 5.6 实现七域五态 `ConsolReadiness` 服务/API，复用证据 readiness，不以前端拼事实。
- [ ] 5.7 新 `ConsolReadinessBar`、流程条和附注四组工具栏；主按钮按 source_mode 分派。
- [ ] 5.8 跨国企/上市子企业、同名行/分组/续表/Top-N/manual/locked/stale 映射回归与 Playwright。

## 批 6　薄 WorkingPaper、证据、复核与归档

- [ ] 6.1 动态取迁移号，新建 `consol_workpaper_instance`、artifact 关联；幂等创建 `A3-CONSOL` 的 WpIndex/WorkingPaper 壳。
- [ ] 6.2 壳接负责人、复核、回收站和项目权限；业务 JSON 不复制进 parsed_data。
- [ ] 6.3 设计稳定 sheet/row/cell identity，接通附件上传、引用、小眼睛预览和 EvidenceLink；插删行身份不漂移。
- [ ] 6.4 readiness 接证据充分性和复核状态；角色视图分别展示编制、审批、重大判断和质控待办。
- [ ] 6.5 archive inventory/provider 纳入成功 operation、artifact、snapshot、附件和审计清单；缺件 fail-closed。
- [ ] 6.6 端点权限配方、证据跨项目隔离、回收站恢复、复核状态转换和归档包 hash 验证。

## 批 7　完整签字快照和锁定

- [ ] 7.1 升级快照 v2 manifest：11 类分片、分片 hash、根 hash、operation/version refs；兼容读取旧快照。
- [ ] 7.2 manual 快照允许 partial 并列明失败；sign/lock required source、readiness、artifact 任一失败即拒绝。
- [ ] 7.3 快照 service 改只 flush；签字路由在一致事务边界写 snapshot、签字记录、operation terminal 和 `consol_lock`。
- [ ] 7.4 主工作台接快照列表、完整性、比较和下载；旧 developing 快照页退役或重定向。
- [ ] 7.5 故障注入逐个摘 capturer、篡改分片/hash、并发改数据，证明签字失败关闭与签字后还原。

## 批 8　性能、浏览器、真实数据与收尾

- [ ] 8.1 10/100/500 节点斜率基准：tree/basis 调用、SQL、CPU、内存、连接、附注章节；候选与 HEAD 对照。
- [ ] 8.2 完整【测试】集团 Playwright：单体 TB→工作底稿→草稿→审批→operation→报表/导出→附注→证据/复核→签字锁定，写入逐表恢复。
- [ ] 8.3 127.0.0.1 与内网 HTTP 各验一次；SSE 正常/断线/轮询、并发点击、超过 6 分钟和 worker 重启均有证据。
- [ ]* 8.4 交付 6000 并发 Locust/PgBouncer 场景、阈值和看板；仅在专用环境授权后实跑，未授权如实标“代码已改但未实测”。
- [ ]* 8.5 真实业务集团只读/dry-run 对账需用户再次授权；未授权不写库、不假绿。
- [ ] 8.6 全量相关回归、候选树相对 HEAD 新增失败 0、语义复审、INDEX/memory/dev-history 收尾、清理 tmp，单 commit 并版本化推送。
