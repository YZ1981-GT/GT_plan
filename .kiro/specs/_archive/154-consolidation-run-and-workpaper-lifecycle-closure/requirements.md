# 需求文档：合并运行与底稿生命周期收口

> spec：`consolidation-run-and-workpaper-lifecycle-closure`  
> 用户目标：按 2026-11-01 合并模块评估建议，逐一修复合并报表、合并工作底稿、合并附注、单体联动、处理顺序、速度和审计生命周期问题。

## 1. 范围与边界

- 本 spec 收口已有合并能力，不重写三码企业树、`consol_calc_basis`、`consol_report_values`、V186 附注明细映射或标题行库。
- 复用既有 `ConsolContext`、`elimination_entries`、`ConsolPushRun`、`ConsolSnapshot`、`WorkingPaper`、`EvidenceLink`、通用复核/归档接口。
- 与 `formula-provenance-envelope` 共用报表 `run_id/provenance`，与 `formula-writer-ownership-and-stale` 共用写入方/过期词表，不创建同义真源。
- 不复活已下线的合并附注 V2/cross-template 路径；不自动审批任何草稿分录；不擅自改真实业务项目。

## 2. 需求

### R1　界面动作真实且不会丢编辑
1. “转换规则”、范围模板、节点刷新等入口不得在没有后端状态变化时提示“已应用/已刷新”。
2. 年度和准则若由项目元数据决定，应显示为只读；若允许修改，必须经后端保存、影响预览和重算确认。
3. 合并工作底稿首次加载完成前不得编辑；后续重载、切项目/年度/节点/Tab/路由前须统一处理 dirty。
4. 合并附注“查看”、节点切换和上下文切换须提供“保存并继续/放弃/取消”，保存中产生的新编辑不得被旧响应清除。
5. 错误、真实空态、加载中、旧数据和只读态必须区分，不得把请求失败显示为业务空数据。

### R2　合并工作底稿只有一个正式抵销来源
1. `elimination_entries` 是调整与抵销分录唯一正式来源，只有 `approved` 且归属成功的分录进入合并数。
2. 抵销后长投、抵销后投资收益、少数股东权益损益、资本公积抵销列必须读取服务端 canonical projection，不再读取旧 JSON 骨架。
3. 自动列只读；用户判断只写明确的 manual override，不得反向形成第二份分录事实。
4. 旧 `consol_worksheet_data['elimination']` 只保留可审计迁移入口，不再参与计算。

### R3　工作底稿生成草稿必须绑定来源版本
1. 客户端只提交来源表范围、预览 token 和期望 version vector，不提交权威计算后的 `groups`。
2. 服务端在同一快照下读取工作表、校验版本、计算 canonical groups、预览并幂等生成草稿。
3. 预览后任一来源版本变化须返回 409，且不得创建、更新或软删任何草稿。
4. 草稿保留来源 sheet/version/hash；已提交、已审批分录不得被自动生成覆盖。

### R4　合并运行可持久、可恢复、可并发校验
1. 一键刷新、审批后推送和公式变更推送共用持久 `consol_operation` 根记录与状态机。
2. operation 必须保存幂等键、请求 hash、`ConsolContext`、输入 version vector、revision、lease/heartbeat、步骤、错误与输出引用。
3. 同项目同年度最多一个 active operation，并只保留一个合并后的 pending revision；进程重启后不得永久 running 或返回“任务过期”。
4. 各阶段写入和最终发布必须用 revision CAS，旧输入不得晚写覆盖新输入。
5. `succeeded/partial/failed/stale/cancelled` 必须如实区分；下游失败不得伪装整体成功。

### R5　报表页面、导出、底稿和快照使用同一正式运行
1. 合并报表页面默认展示最近一次已发布 operation，并明确区分“正式结果”和“实时预览”。
2. Excel 导出、合并底稿包和正式签字快照必须引用同一 `report_generation_run/run_id` 与输入 revision。
3. 页面与导出逐行金额、行次、口径和上期来源必须一致；不一致时阻止正式下载并说明原因。
4. 合并底稿文件必须一次生成、版本化保存、带 SHA-256；下载不得再次临时重算。
5. 非根节点结果属于分析视图，须明确标识；若允许导出，也必须绑定同一 operation。

### R6　合并附注来源权责与自动汇总清晰
1. 合并附注须记录章节/行/格的 `detail_mapping/subtree_aggregate/formula/manual/mixed` 来源投影及来源 operation/revision/digest。
2. 手工格和锁定格优先，自动任务不得覆盖；公式与明细映射不得继续依赖“最后点击者覆盖”。
3. 一键更新对已确认且结构未变的映射自动拉数和汇总；stale/未确认映射进入待办，不得猜测。
4. 附注公式一次批量加载；单体附注按目标章节和全部叶子批量读取；仍保留每章节 SAVEPOINT。
5. 工具栏按数据准备、计算更新、复核和更多分组，主操作根据来源模式选择正确路径。

### R7　建立统一 readiness 和可理解流程
1. 服务端提供版本化 `ConsolReadiness`，覆盖 tree、worksheet、elimination、calc、report、note、lifecycle 七域。
2. 状态使用 `ready/not_ready/unknown/not_applicable/warning`，事实与阻断策略分离。
3. 工作台标题改为“集团合并工作台”，展示企业树版本、输入版本、最近正式 run、报表/附注新鲜度、待审批与待映射数量。
4. 主流程为：企业树 → 数据准备 → 抵销审批 → 更新合并结果 → 试算/报表复核 → 附注 → 签字锁定；专家用户仍可直接跳转。
5. 前端按能力和锁状态禁用写操作并解释原因，不让只读用户编辑后才收到 403。

### R8　合并工作区成为正式审计底稿
1. 每个合并项目/年度建立一个薄 `WpIndex + WorkingPaper` 壳，业务数据仍以合并专用表为权威。
2. 壳接入负责人、复核状态、附件证据、版本、回收站和归档；不得复制合并 JSON 到 `parsed_data` 形成第二真源。
3. 证据可按 `sheet_key/node_key/row_identity/cell` 定位；复用通用 `EvidenceLink` 和证据 readiness。
4. 归档 provider 按正式 operation 生成不可变工作底稿包，清单和文件 hash 必须闭合。

### R9　正式签字快照必须完整且失败关闭
1. 手工诊断快照可 partial；`sign/signed/lock` 快照必须捕获全部 required source，否则不得创建或锁定。
2. required source 至少含企业树 revision、工作表 JSON/version、分录及审批、差额表、试算、报表 run、`ConsolNoteData`、映射/公式版本、底稿复核/证据摘要与 artifact hash。
3. 每类分片独立 hash，manifest 再计算根 hash；恢复与比较须校验全部 hash。
4. 签字、snapshot、项目锁和 operation terminal state 必须在可证明的一致边界内完成。

### R10　性能、可观测性与容量
1. 每 target/run 企业树最多构建一次，calc basis 最多装载一次；现有调用方必须复用同一 `ConsolContext` 和 basis。
2. 上层目标解析及章节公式加载的 SQL 数不得随层级/章节线性增长；大批写入使用分块批处理。
3. operation 记录每阶段 duration、SQL/行数摘要、节点 N、科目 A、章节 S、层级 D、queue/lock wait 和 retry。
4. 前端收到任务回执应在 1 秒内显示真实 job 状态；长任务不得阻塞在线请求事件循环。

### R11　兼容、安全与验收
1. 所有读写端点保持项目级鉴权、归档/合并锁门和项目/年度/节点身份校验；写服务只 flush，编排路由统一 commit。
2. 旧 refresh/push API 保留兼容壳并返回 operation_id；旧无版本草稿生成入口在迁移期只允许 dry-run，随后退役。
3. 必须有 SQLite/纯函数、真实 PG 并发与崩溃恢复、前端单测、Playwright 全链和性能斜率证据。
4. Playwright 只使用名称含“【测试】”的集团，写入后按涉及表逐项恢复；真实业务集团仅经用户再次授权做只读/dry-run。
5. 6000 并发执行依赖专用压测环境；代码、脚本、指标和小规模斜率测试须交付，未获环境授权时如实标环境待测。
