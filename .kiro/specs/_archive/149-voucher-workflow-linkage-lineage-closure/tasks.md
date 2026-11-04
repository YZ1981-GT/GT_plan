# 凭证模块联动、流程与溯源收口 — 任务

标完成须有代码 + 测试通过证据；依赖外部环境的如实留 `[ ]*`。

## 批次 A：P0 安全与完整性

- [x] 1. 承接前序 spec 收尾：旧身份治理脚本在共享库 `--dry-run`（只读），核对分类与真实数据一致；前序 4 个变异靶点并入任务 19
  - AC：报告落 `tmp_voucher_closure/legacy_dry_run.json`；32 行存活登记逐行有分类；不改库
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`tmp_voucher_closure/legacy_dry_run.json`：32 行 = auto_resolve 31 / ambiguous 0 / no_match 0 / legacy_orphan 1，`applied=false`；前序 4 个靶点并入任务 19（全红）
- [x] 2. 挂凭写门（R1.1~R1.4，design §3）
  - 单笔必填底稿、单笔 / 批量 / 删除写门、按底稿列表读门；前端 `attachVoucher` 底稿必填
  - AC：端点级用例覆盖可写、不可写、无底稿、删除无权、列表无权；承接的 13 例照旧全绿
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_voucher_links*.py`（含承接的 `test_voucher_links_ownership.py` 7 例、`_voucher_links_gates.py`）、`AttachVoucherToWpDialog.spec.ts`；临时库真实 HTTP：别的项目底稿 → 422 `WP_NOT_IN_PROJECT`
- [x] 3. 外围端点（R9，design §11）
  - `report_trace` 两端点、`wp_chat` 序时账分析补项目只读；单据识别两端点 410；删 `DocumentRecognizeDialog.vue`
  - AC：无成员 403；识别端点 410 且不读附件；鉴权基线 / 路由清单守卫按实际更新并全绿
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_voucher_peripheral_endpoints_authz.py`；`DocumentRecognizeDialog.vue` 已删、`components.d.ts` 只删它一行；鉴权棘轮「仅登录不校项目」远端头 154 → 148（`_IDENTITY_ONLY_BASELINE` 下调，design §15）
- [x] 4. 迁移未执行 503（R2，design §4）
  - `app/core/migration_pending.py` + `generic_exception_handler`；调整分录页显示后端说明
  - AC：链上识别、有 / 无待执行、判定失败、缓存四类用例；前端单测覆盖 `MIGRATION_PENDING` 文案
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_migration_pending_503.py`、`httpMigrationPending.spec.ts`（含 503 非迁移业务码反例）

## 批次 B：P1 序时账 ↔ 底稿

- [x] 5. 凭证行索引服务（design §8.1~8.2）
  - `services/voucher_row_index.py` + 取值表 JSON + 前端 `voucherVerdict.ts`
  - AC：身份行、旧行、上限截断、取值表判定用例；前后端取值表契约测试
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_voucher_row_index.py`、`voucherVerdict.spec.ts`（与 `voucher_check_verdict_vocab.json` 逐值对拍）
- [x] 6. 删除「抽中本凭证」；挂凭弹窗结果页（R3.1、R3.2，design §5.1~5.2）
  - AC：组件测试覆盖分组、失败原因、打开底稿事件；源码守卫确认按钮与函数已删
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`AttachVoucherToWpDialog.spec.ts`、`voucherLinkageWiring.spec.ts`（「抽中本凭证」按钮与函数已删的源码判据，任务 19 补）；浏览器 s1 / s2
- [x] 7. 已挂标签可点 + 失败态 + 导入状态（R3.3、R3.4，design §5.3、§8.3）
  - AC：`useVoucherLinkTags` 失败态单测；标签点击事件；后端 `imported` 三态用例
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`useVoucherLinkTags.spec.ts`、`test_voucher_links_import_status.py`；浏览器 s1（标签可点）/ s3（查询失败显示「挂接状态未知」可重试）
- [x] 8. 统一序时账地址 + 返回序时账（R3.5、R3.7，design §5.4~5.5）
  - AC：地址往返用例；`safeReturnTo` 拒绝外链 / 协议 / `//`；编辑页按钮显示条件
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`voucherLedgerRoute.spec.ts`、`voucherLinkageWiring.spec.ts`；浏览器 s1（「← 返回序时账」回凭证层）/ s7b（「← 返回上一张底稿」）
- [x] 9. 底稿待导入提示（R3.6，design §5.6）
  - 后端 `attached-voucher-status` + `VoucherAttachPendingBanner.vue`
  - AC：端点级（读门、只算手工、已导入排除）；横幅显示 / 展开 / 关闭 / 失败不显示
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_attached_voucher_status.py`、`VoucherAttachPendingBanner.spec.ts`；浏览器 s1（默认收起）/ s2（从挂凭结果打开默认展开）/ s7（导入后横幅消失）

## 批次 C：P1 抽凭

- [x] 10. 抽凭引擎只读与单飞、预览只读与分页（R4.1~R4.3，design §6.1）
  - AC：运行时只读禁用回填与撤销；双击只发一次；超过 100 行分页
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`SamplingPreviewDialog.readonlyPaging.spec.ts`、`samplingReviewWiring.spec.ts`、`samplingConfirmFillReachability.spec.ts`、`useEngineUndo.spec.ts`；浏览器 s4（可编辑 / 归档 / 被别的窗口锁定）、s6（120 笔分页、表头勾选只改本页、双击「确认填充」只提交一次）
- [x] 11. 抽样增强页（R4.4、R4.5，design §6.2）
  - AC：年度与基准日来自项目；未填年度不发请求；切页签才加载；失败重试；行跳转
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`SamplingEnhanced.voucher.spec.ts`（10 例）、`test_sampling_coverage_year_scope.py`（4 例，浏览器实测补）；浏览器 s5

## 批次 D：P1 客户入账

- [x] 12. 凭证选择器替换粘贴凭证键（R5.1，design §7.1）
  - AC：404 / 409 候选 / 成功三态；提交用选中凭证的凭证键
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`ClientBooking.spec.ts`（404 / 409 候选 / 成功）；浏览器 s8（查不到说明原因、0075 同号 50 张列候选、选一张加入、确认后撤销恢复）
- [x] 13. 建议条权限与全部建议、跨页打开、影响说明（R5.2~R5.4，design §7.2）
  - AC：无权只显示文字；多条建议逐条确认；当前页没有时按 id 取分录
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`ClientBooking.spec.ts`、`useAdjustmentHallResource.spec.ts`（无权只显示文字、逐条确认、当前页没有时按 id 取分录）

## 批次 E：P2 跨底稿与处置

- [x] 14. 他稿结论查询端点（R6，design §8.3）
  - `POST …/ledger/voucher-conclusions/query`
  - AC：端点级（只读成员可查、不可见底稿被过滤、500 键上限 422）
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_voucher_conclusions_query.py`
- [x] 15. 他稿结论徽标（R6.1、R6.3、R6.4，design §9）
  - `useVoucherConclusionIndex.ts` + `VoucherConclusionTag.vue` 接入 `VoucherRowMetaCell`
  - AC：合批、失败态、排除本底稿、打开底稿；`VoucherRowMetaCell` 既有用例照旧
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`VoucherConclusionTag.spec.ts`、`useVoucherConclusionIndex.spec.ts`、`VoucherRowMetaCell.wiring.spec.ts`；浏览器 s7b（K8 来源列「他稿异常」，弹层 K9 异常 2 行，打开底稿带返回地址）
- [x] 16. 异常样本处置（R7，design §9）
  - `VoucherDispositionButton.vue`
  - AC：只在异常且可写时出现；金额必填 > 0；事件载荷字段与 A13 桥归一化逐项一致
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`VoucherDispositionButton.spec.ts`；浏览器 s7（只在异常行出现，金额必填，记入后临时库 `unadjusted_misstatements` 落一笔：描述带凭证称呼、科目 6602.01.08、1673.00、事实错报）

## 批次 F：P2 溯源

- [x] 17. 试算表行溯源子源（R8.1、R8.3，design §10.1）
  - AC：四类节点用例；无年度报 partial；附件子源不受影响；统一溯源既有用例照旧
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_tb_row_lineage.py`、`formula_hub/test_unified_lineage_contract_pg.py`（tb_row 用例；和平药房活项目两年度致 `test_heping_d2_*` 预存红）；浏览器 s9（右键 1002「数字溯源」带年度，构成 + 28 张底稿，「定位」打开 E1）
- [x] 18. 附注章节溯源去伪（R8.2，design §10.2）
  - AC：按年度与科目取数；序时账前 10 笔带口径；失败不再返回空结果
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_report_trace_section.py` 8 例 + `test_phase10_step4_to_21.py` 共 39 passed；`ReportTracePanel.basis.spec.ts`；浏览器 s10（八、1 写明口径、五、1 说明没有对应底稿）

## 批次 G：收尾

- [x] 19. 磁盘变异（design §12 变异表 + 前序 spec 4 个靶点）
  - AC：每个变异至少一条用例打红且形态符合预期；全部逐字节还原（sha256 核对）
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：106 条：104 打红、2 条阴性对照保持绿，逐字节还原；浏览器实测后补 q1~q6（含 q5b）全红（`tmp_voucher_closure/mutations/report.md`）
- [x] 20. 浏览器实测（design §13 隔离临时库）
  - 走查：挂凭结果页 → 打开底稿 → 待导入提示 → 返回序时账；标签点击与失败态；抽凭只读；抽样增强页；
    客户入账选择器；他稿结论与处置；试算表行数据溯源
  - AC：每条走查有截图或快照记录在 `tmp_voucher_closure/browser/`；console error 0；临时库与进程清理
  - `[ ]*` 依赖临时库可建
  - 走查记录（2026-11-04，`tmp_voucher_closure/browser/` s1~s11 截图与 JSON）：全部场景走通；发现并修 3 处（概览不按年度、读取失败留旧行、报告溯源失败整页换成英文报错，design §15.3）；范围外 2 处未修（K1~K13 重开页面后保存 428、D2 导入导出端点不存在，design §15.4）。console 只剩故意造的失败与 409 候选协议。临时库与进程待收尾时清理
  - 用户定后（2026-11-04）：428 修复后重启隔离后端复测 s12（K9-8「是否异常」重开页面切换 4 次，PUT 全 200）/ s12b（D2 明细表审计说明改字再改回，PUT 全 200），design §15.5；D2 导入导出另立 spec。走查结束后停隔离前后端、删临时库与容器内临时文件、删候选 worktree 里的走查副本（`.env`、`wp_storage` 副本），共享 `backend/wp_storage` 未动
- [x] 21. 登记与提交
  - INDEX.md 登记本 spec 与前序 spec 状态（只动本 spec 的行，CRLF）；分离头 worktree 基于远端头提交本 spec 全部文件；
    暂存树自洽检查；推送前请用户放行（同时列出：共享库迁移、`--apply`）
  - AC：干净检出跑本 spec 全部测试通过；全量 vue-tsc 相对 HEAD 不新增；行数门通过
  - 证据（2026-11-04；收尾期间远端两次前移，候选树逐次换到新远端头重放本 spec，最终 = 远端头 98332962c + 本 spec）：
    用户放行（「按建议来，之后推送」）后执行 `--apply`（前序 spec 任务 11）；后端选集 141 个文件与远端头逐节点对比，
    新增只有 PG 用例在不存在的测试库下由失败变报错（临时库 `GT_REQUIRE_PG=1` 实跑 34 passed，余下失败远端头同样存在
    或属快照库限制）与 1 条 hypothesis 随机反例（MUS 抽样，被测模块与用例都未改动）；全量 vitest 相对远端头新增 2 条均为
    PBT 随机种子、同种子在远端头复现，修复 9 条；本 spec 前端用例 26 文件 282 例全过；全量 vue-tsc 2962 = 远端头 2962；
    行数门通过；领域边界与远端头违规集合相同（design §15.6）；ruff 不新增；提交按前后端与 428 修复拆分，经
    `push_version.py` 推送（版本号见推送回执与远端标签）

## 批次 H：用户定后修复（2026-11-04「按建议来，之后推送」）

- [x] 22. render 快照条目带 CAS 版本：K1~K13 / D2 重开页面后保存 428（design §15.4 → §15.5，单独提交）
  - `checklist_response_cas.checklist_snapshot_entry` 产出快照条目；共享 `load_responses_snapshot` 与 K1 / K2 / D2 内联查询加选 `updated_at`；K1 坏账 seed 保留版本
  - AC：四个快照构造点逐个有用例且漏选 `updated_at` 即红；真 PG 往返（快照版本过严格预检、不带 `if_match` 为 428）；前端快照 → `if_match` 契约；浏览器 K9-8 与 D2 重开页面保存 200
  - 证据（2026-11-04，候选树 = 远端头 33d1aa5a2 + 本 spec）：`test_render_snapshot_cas_version.py` 11 例、`test_render_snapshot_cas_version_pg.py` 2 例（临时库 GT_REQUIRE_PG=1）、`renderSnapshotCasBaseline.spec.ts` 4 例；K 选集 3603 例对远端头新增失败 4 条均为候选 worktree `.env` 打开 AI 服务所致（移走后全过）；变异 11 条 10 红、1 条等价变异已换写法补红；浏览器 s12（K9-8 4 次 PUT 全 200）/ s12b（D2 审计说明 2 次 PUT 全 200）
