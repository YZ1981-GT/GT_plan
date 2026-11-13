# 凭证模块联动、流程与溯源收口 — 设计

## 1. 现状（2026-11-03 现读，行号会漂，锚点用函数名）

| 区域 | 现状 | 后果 |
| --- | --- | --- |
| 挂凭三端点 `routers/voucher_links.py` | 只有项目级 `require_project_access`；单笔 `working_paper_id` 可空 | 项目内任何编辑者能改别人底稿的抽样清单；无底稿的挂凭没有落点 |
| 无底稿挂凭的调用方 | 全仓只有序时账「抽中本凭证」（`LedgerPenetration.vue` `sampleCurrentVoucher`） | 共享库 32 行存活登记中 1 行无底稿 |
| 共享库迁移 | `schema_version` 最高 V234，磁盘 V251 | 客户入账、项目列表等 500「服务器内部错误」，`generic_exception_handler` 不区分 |
| 挂凭弹窗 `AttachVoucherToWpDialog.vue` | 多底稿成功只有 toast；单底稿弹确认后跳转；跳转不带参数 | 挂完不知道去哪导入、看完回不到查账位置 |
| `VoucherLinkTags.vue` / `useVoucherLinkTags.ts` | 纯标签不可点；查询失败被 catch 吞掉 | 查询失败显示成「尚未挂到底稿」 |
| 底稿侧导入 | 40 处宿主各自调 `pullSamplesForWorkpaper`；平台没有「待导入」提示 | 挂了的凭证可能永远没进检查表 |
| 抽凭引擎 `GtVoucherSamplingEngine.vue` | 78 个宿主无一传 `readonly`；`canEditRow` 只看 props；`handleConfirmFill` 无单飞 | 归档、复核身份下仍可回填；双击重复登记 |
| 抽样增强页 `SamplingEnhanced.vue` | 年度 2025、基准日 2025-12-31 写死，上限 2030；默认页签是截止测试却在挂载时加载凭证总览；行无跳转 | 非 2025 项目默认值全错；无谓请求 |
| 客户入账 | 无候选时要求粘贴凭证键 JSON；建议条不看权限、只开第一条；`openBookingSuggestion` 只在当前页找分录 | 实际不可用 |
| 他稿结论 | `VoucherRowMetaCell`（76 个宿主的「来源」列）已有他稿证据提示，没有他稿结论 | 同一凭证在两张底稿结论相反无人知晓 |
| 异常处置 | 约 35 个宿主各有「推送错报至 A13」，凭证检查行没有通用入口 | 其余宿主的异常样本没有处置路径 |
| 试算表行溯源 | 前端请求 `/lineage?object_type=tb_row`，服务端该类型没有子源（ADR-FHIC-16） | 恒「暂无溯源信息」 |
| 附注溯源 `ReportTraceService.trace_section` | 取第一个底稿编码；试算表 `.limit(5)` 不按年度；序时账按借方取前 10；吞异常 | 结果与章节无关，失败与「无数据」不可区分 |
| 外围端点 | `report_trace` 两端点、`wp_chat` 序时账分析、`wp_document_recognize` 两端点只校登录；识别按附件 id 读、不校项目；桩实现回 `recognized` | 越权读取；假成功 |

共享库数据（只读核对）：`checklist_responses` 907 行，含 `"_gt"` 的 0 行、含 `voucherNo` 的 6 行，单行 `remark`
最长约 82 万字符；`sampled_vouchers` 存活 32 行（30 引擎 + 2 手工），全部缺主体或凭证字，30 行引擎登记缺日期。

## 2. 决策（ADR-VWL）

- **01 底稿写门复用矩阵动作 `save_checklist`**：挂凭改变的是底稿的抽样清单，受众与保存凭证检查表相同，不新增矩阵条目。
  用静默门 `try_gate_wp`；拒绝时返回业务错误码（单笔 403、批量逐条），不走 404：挂凭弹窗列的就是用户可见的底稿，
  403 不多透露信息。
- **02 停止新增无底稿挂凭**：删除唯一调用方，后端 422 `WP_REQUIRED`；存量无底稿行由治理脚本标 `legacy_orphan`，不删。
- **03 迁移未执行 503 只在确有待执行迁移时生效**：在 `generic_exception_handler` 内判定，其余情况保持 500。
- **04 凭证行索引是只读惰性扫描**：扫 `checklist_responses`，不建投影表。写入方有 HTML CAS、在线编辑镜像、导入三类，
  投影表需要每个写入方维护，漂移风险大；SQL 先按 `"_gt"` / `voucherNo` 预筛，再逐条解析并设上限。
- **05 结论判定只认白名单字段 + 固定取值表**：前后端各一份，契约测试逐值对拍。
- **06 待导入提示不做一键导入**：导入的科目前缀与行映射在各宿主，平台层复制不了；提示给张数、凭证与说明，
  导入仍由宿主按钮完成，用户在宿主的预览里确认。
- **07 异常处置走既有 A13 错报桥事件**：金额必须人工填写，与 D4-19 守卫同一原则（不把分录金额自动当错报额）。
- **08 试算表行溯源作为统一溯源的独立子源**：与 `note_cell → report_trace` 同一写法；不改 `_SOURCE_BY_OBJECT_TYPE`
  （ADR-FHIC-16 的底稿溯源来源表保持原样）。
- **09 单据识别退役，不修补**：替代路径（底稿证据入口 + 附件识别）已有鉴权、项目校验与真实识别；修补要补的三样都已在替代路径。
- **10 `LedgerPenetration.vue` 不拆分**：本次只删代码、改一个导航函数，行数下降；整体拆分与收益不成比例。

## 3. R1 挂凭写门（`routers/voucher_links.py`）

新增 `_wp_writable(db, user, wp_id) -> bool`：`try_gate_wp(entrypoint="workpaper.checklist_save",
action="save_checklist", method="PUT", wp_id=…)` 非空即可写（`entry_family` 与凭证检查表保存端点的实参一致，实施时现读）。
读门 `_wp_readable` 同理用 `workpaper.checklist_read` / `GET` / `read_checklist`。

| 端点 | 顺序 |
| --- | --- |
| `POST /sample-voucher` | 未给底稿 422 `WP_REQUIRED` → 不在本项目 422 `WP_NOT_IN_PROJECT` → 不可写 403 `WP_NOT_WRITABLE` → 抽样记录归属 → 定位凭证 |
| `POST /sample-vouchers/batch` | 先按项目取底稿，再逐张判可写；不可写的底稿逐条 `failed` + `WP_NOT_WRITABLE`，`wp_code` 置空 |
| `DELETE /sampled-vouchers/{id}` | 记录有底稿且不可写 → 403；无底稿的旧行只要项目级编辑权限 |
| `GET /sampled-vouchers?working_paper_id=` | 不可读 → 404「底稿不存在或无权查看」；不带底稿时沿用承接 spec 的可见性过滤 |

`_SampleVoucherRequest.working_paper_id` 类型保持可空（让 422 走中文业务码，不走 pydantic 英文报错）。
前端 `attachVoucher` 的 `workpaperId` 改必填；它在本次之后只剩测试调用，保留作为接口封装。

承接 spec 的未完成项（干跑、变异、浏览器、提交）并入本 spec 任务 1、19、20、21。

## 4. R2 迁移未执行（`app/core/migration_pending.py` + `middleware/error_handler.py`）

- `is_missing_schema_error(exc)`：沿 `exc` → `orig` → `__cause__` → `__context__` 链找 `sqlstate`（或 `pgcode`）属于
  `{"42P01", "42703"}`，深度上限 6。
- `pending_migration_info()`：用全局 `engine` 新开连接读 `schema_version.version`，与 `MigrationRunner.scan_migrations()`
  的磁盘版本按**数字**比较（与运行器去重口径一致），返回 `{db_max, disk_max, pending_count}` 或 `None`；结果缓存 60 秒，
  用 `asyncio.Lock` 防并发重复查询；任何异常返回 `None`（按 500 处理，R2.3）。
- `generic_exception_handler`：`is_missing_schema_error` 且有待执行迁移 → 503
  `{code: 503, error_code: "MIGRATION_PENDING", message: "数据库结构未升级：程序需要 V251，库里最高 V234，还有 17 个迁移未执行。请联系管理员重启后端（启动时会自动执行迁移）。"}`；
  否则原样 500。日志照旧记堆栈。
- 前端：调整分录页资源加载失败时，错误信封里 `error_code === 'MIGRATION_PENDING'` 就显示后端 message（R2.5），
  在 `useAdjustmentHallActions` 或资源加载函数里取信封，不改全局拦截器。

## 5. R3 序时账 ↔ 底稿

### 5.1 序时账页（`LedgerPenetration.vue`）

- 删除「抽中本凭证」按钮、`sampleCurrentVoucher` 与只为它存在的导入。
- `onNavigateToWp({ workpaperId })` 改为
  `router.push({ name: 'WorkpaperEditor', params: { projectId, wpId }, query: { returnTo: route.fullPath, from: 'voucher-attach' } })`。
- `VoucherLinkTags` 新增事件 `open-wp(workpaperId)`，同一导航函数处理（`from` 不带 `voucher-attach`）。

### 5.2 挂凭弹窗结果页（`AttachVoucherToWpDialog.vue`）

提交后（只要有返回结果）切到结果视图，不再分单底稿 / 多底稿两套提示：

| 列 | 内容 |
| --- | --- |
| 底稿 | 编码 + 名称（结果没给编码时用弹窗自己的候选清单补；仍没有则写「无权编辑或不在本项目」） |
| 结果 | 新挂 n · 已挂 m · 失败 k；失败原因逐条列出 |
| 操作 | 新挂 + 已挂 > 0 时「打开底稿」→ emit `navigateToWp` |

页脚「完成」关闭；「继续挂入」回到选择视图（保留已选底稿）。顶部说明改为：挂入后目标底稿顶部会提示待导入的凭证，
在凭证检查表点「从序时账挂入导入」带入检查行（每张底稿只导入本科目的分录）。

### 5.3 已挂标签（`VoucherLinkTags.vue` / `useVoucherLinkTags.ts`）

- `useVoucherLinkTags` 记失败的键（`failed: Set<string>`，响应式），`linkStatusOf(key)` → `'loading' | 'ready' | 'error'`；
  `refresh` / 重新查询时清除失败标记。凭证层传 `linkStatus`，`error` 时显示「挂接状态未知」+「重试」，不显示「尚未挂到底稿」。
- 有底稿编码且底稿未删除的标签渲染为可点按钮（`role=button`、键盘可达），点击 emit `open-wp`。
- 手工挂凭的条目带 `imported`（后端 §8 索引给出）：`true` 文本加「已导入」，`false` 加「未导入」，`null` 不加。

### 5.4 统一序时账地址（`utils/voucherLedgerRoute.ts`）

`ledgerRouteOfVoucherKey(projectId, voucherKey, opts?: { accountCode?, returnTo? })`：解析凭证键 JSON（5 元素数组），
返回 `{ name: 'LedgerPenetration', params: { projectId }, query: buildLedgerQuery({ level: 'voucher', account, voucherNo,
voucherDate, voucherType, voucherCompany }, year) }`；解析失败返回 `null`（调用方不显示入口）。待导入提示、
他稿结论弹层、抽样增强页共用。

### 5.5 返回序时账（`WorkpaperEditor.vue`）

`safeReturnTo(query.returnTo)`：只接受以 `/projects/` 开头、不含 `//`、不含协议的字符串，否则 `null`。有值时在编辑页
头部显示「返回序时账」（`router.push(returnTo)`）。

### 5.6 待导入提示（`VoucherAttachPendingBanner.vue`，挂在 `GtWpRenderer` 的 `VoucherSurvivalBanner` 旁）

- 后端 `GET /api/projects/{pid}/ledger/workpapers/{wp_id}/attached-voucher-status?year=`（底稿读门）：取本底稿手工挂凭
  （`batch_id IS NULL`、未软删），用 §8 索引判断每张凭证在本底稿是否已有检查行，返回
  `{ attached: n, pending: [{ voucher_key, label, voucher_date, account_code }], judged: bool }`；最多列 200 张。
- 前端：`pending.length > 0` 时显示「有 N 张凭证已从序时账挂到本底稿，尚未导入凭证检查表」，列前 5 张（可点开序时账），
  说明「在凭证检查表点『从序时账挂入导入』」；`route.query.from === 'voucher-attach'` 时默认展开；关闭记在 `sessionStorage`
  （键含底稿 id）；宿主导入后通过 `notifyVoucherSurvivalRowsChanged` 已有的通知（`voucherSurvivalRegistry`）触发重查。
- 请求带 `_dedupe: false`、`_silent: true`；失败不显示横幅（这是提示，不能挡住底稿）。

## 6. R4 抽凭引擎与抽样增强页

### 6.1 `GtVoucherSamplingEngine.vue`

- `const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null`；
  `effectiveReadonly = computed(() => !!props.readonly || !!runtime?.readonly.value)`，替换模板与脚本里对 `props.readonly`
  的全部读取（`canEditRow`、确认回填、撤销、配置保存）。
- `handleConfirmFill`：`confirming` 为真时直接返回；`try/finally` 复位；按钮 `:loading="confirming"`。
- `SamplingPreviewDialog`：新增 `readonly` 与分页（每页 100 行，`el-pagination` 只在超过 100 行时出现）；只读时隐藏
  编辑控件与「确认」，只留关闭。

### 6.2 `SamplingEnhanced.vue`

- 年度：`resolveAuditYearOrNull`（项目审计年度）；为 `null` 时页头显示「项目未填审计年度」并给去填的入口，各页签请求不发。
- 账龄基准日：项目审计期末（`audit_period_end`），没有时 `${year}-12-31`；年度上限 `max(year, 当年) + 1`。
- 凭证总览：首次切到该页签才加载；失败显示后端原因与「重试」；行上「打开底稿」（有底稿 id）与「序时账」（§5.4）。

## 7. R5 客户入账

### 7.1 凭证选择器（`ClientBookingVoucherPicker.vue`，供 `ClientBookingDialog` 用）

- 输入凭证号（必填）、日期（可选）→ `fetchVoucherLines`（`GET …/ledger/voucher/{no}`，按当前账套）；
  成功：显示凭证称呼、日期、分录表（科目、借、贷、摘要），「加入」后进已选列表；
  409 `VOUCHER_KEY_AMBIGUOUS`：列候选（称呼、日期、分录数、借方合计、摘要），选一张再取分录；404：显示「当前账套没有这张凭证」。
- 已选列表可移除；提交时取各凭证的 `voucher_key`。删除粘贴凭证键的文本框。

### 7.2 建议条与跨页

- `ClientBookingSuggestionBar` 新增 `canEdit` 属性：为假时只显示提示文字（「请有编辑权限的成员确认」），不显示按钮。
  展开后列出全部建议：调整编号、摘要、候选凭证数，每条「确认」。权限取调整分录页现有的编辑判定（实施时现读，
  与「标记客户已入账」按钮同一判定）。
- `openBookingSuggestion`：当前页找不到分录时，按 `entry_group_id` 取单组分录（现有分录详情接口，实施时现读）再打开；
  取不到提示「分录已删除或不在本年度」。
- 弹窗说明改为 R5.4 的文字。

## 8. 凭证行索引（R3.4 / R3.6 / R6 / R7 共用，`services/voucher_row_index.py`）

### 8.1 扫描

```sql
SELECT wp_id, item_id, conclusion, remark FROM checklist_responses
WHERE project_id = :pid [AND wp_id IN (:wps)]
  AND (remark LIKE '%"_gt"%' OR conclusion LIKE '%"_gt"%' OR remark LIKE '%voucherNo%' OR conclusion LIKE '%voucherNo%')
```

- 两列都解析（与 `entry_payload_reader` 同一结论：载荷可能在任一列）；只解析以 `[` / `{` 开头的 JSON。
- 上限：单条载荷 2,000,000 字符（实测最长约 87 万）、遍历深度 6、单次请求最多 200,000 个字典；超限停止并在结果里标 `truncated`。
- 每个字典：`_gt.vk` 是合法凭证键 → 身份行；没有 `_gt`、但有凭证号（`voucherNo` / `voucher_no` / `voucherNumber`）
  与日期（`voucherDate` / `voucher_date` / `date`）→ 旧行，按「号|日期」认（与前端 `legacyIdentity` 的号、日期取法相同）。
- 输出 `RowHit(wp_id, item_id, vk | None, legacy_key | None, verdict)`。

### 8.2 结论取值表（`backend/data/voucher_check_verdict_vocab.json`，前端 `voucherVerdict.ts` 同值，契约测试对拍）

| 字段 | 异常 | 正常 |
| --- | --- | --- |
| `isAbnormal` / `abnormal` | `是` `Y` `true` `异常` | `否` `N` `false` |
| `checkResult` | `ERR` `不一致` `异常` `有异常` `×` `不符` | `OK` `一致` `无异常` `正常` `√` `相符` |
| `checkConclusion` | `不符` `有异常` `未取得权证` | `相符` `无异常` |
| `auditConclusion` | `需调整` `差异需调整` | `无差异` `差异可接受` `无异常` |
| `isConsistent` | `不一致` `否` `false` | `一致` `是` `true` |

取值来自 63 个宿主映射文件里的比较式与下拉选项（探针 `tmp_voucher_closure/probes/verdict_values.py`）。`conclusion`
字段不进白名单：它同时是程序表结论（`Y` / `completed` / `设计无效`），在凭证行上含义不定。一行任一字段为异常即异常；
否则任一为正常即正常；否则未判定。同一底稿同一凭证有任一行异常即该底稿异常。

### 8.3 用途

- `/voucher-links/query`：对手工挂凭条目给 `imported`（该底稿有该凭证键的身份行，或有同「号|日期」的旧行）；扫描出错时为 `null`。
- `attached-voucher-status`：§5.6。
- `POST …/ledger/voucher-conclusions/query {year, keys ≤ 500}`（项目只读 + 逐底稿可见性 `_visible_wp_ids`）：
  `{ conclusions: { key: [{ working_paper_id, wp_code, wp_name, verdict, rows, legacy }] } }`。

## 9. R6 他稿结论 / R7 异常处置（前端，均挂在 `VoucherRowMetaCell`）

- `composables/useVoucherConclusionIndex.ts`：与 `useVoucherEvidenceIndex` 同一合批写法（按「项目 + 年度」合批、
  60 秒、500 键分段、晚到旧响应丢弃、403 / 失败分开、`project:reset` 与身份切换清空）。年度取凭证键自带的年度
  （同 VoucherEvidenceTag：不少宿主给「来源」列缺省年度 0）。
- `VoucherConclusionTag.vue`：排除本底稿后，有异常 →「他稿异常」（danger）；有其他行 →「他稿 n」（info）；失败 →
  「他稿结论加载失败」+ 重试。弹层逐底稿列编码、结论、行数，`legacy` 时注明「旧行按凭证号和日期认出」，可「打开底稿」
  （带 `returnTo` = 当前页）。
- `VoucherDispositionButton.vue`：本行 `rowVerdict(row) === 'abnormal'`、`runtime.readonly` 为假且非年审锁定行时显示「处置」。
  - 「记入未更正错报」：弹窗填金额（必填、> 0）与类型（事实 / 判断 / 推断）；`eventBus.emit('a13:push-misstatement',
    { wpCode, accountCode, amount, misstatementType, description: '凭证 FY-0003（2025-01-07）抽查异常', voucherNo })`；
    科目取自分录指纹第 6 项。去重靠桥的 `source_identity`（底稿 + 描述 + 金额 + 科目 + 类型），同分录同金额同类型只落一笔。
  - 「去调整分录」：`router.push({ name: 'Adjustments', params: { projectId } })`（路由名实施时现读）。
- `wpCode` 取运行时上下文（实施时现读字段名）；取不到时不显示「处置」。

## 10. R8 溯源

### 10.1 试算表行子源（`services/tb_row_lineage.py`，`UnifiedLineageService.query_lineage` 内 `object_type == "tb_row"` 分支）

`object_id` = 标准科目编码，年度取请求参数，缺省用项目审计年度；取不到年度时该子源报 `TB_LINEAGE_YEAR_REQUIRED`（partial）。
输出 `LocateTarget` 列表（`wp_code` 为空串表示非底稿节点，前端照常显示 label、不触发定位）：

1. 构成：`未审 x · 调整 y · 重分类 z · 审定 w`（`trial_balance` 本科目、本年度、全部主体合计）。
2. 已批准调整：`adjustments`（未删除、`review_status = approved`、本年度、科目为本科目或下级）逐组一条，
   label「AJE-003 摘要 借 1,000.00」，有来源底稿时 `wp_code` 为来源底稿编码。
3. 发布审定数的底稿：本科目在 `wp_account_mapping` 对应的底稿中、本项目已生成的，label 带最近一次发布时间（有记录时）。
4. 抽凭 / 挂凭：`sampled_vouchers` 按底稿聚合 `account_code` 前缀为本科目的存活登记，label「D2 抽凭 30 张 · 挂凭 2 张」。

每项最多 50 条，超出写「另有 n 条未列出」。查询失败按 `_run_source` 报 partial（R8.3）。

### 10.2 `ReportTraceService.trace_section`

- 试算表行按 `year`（缺省项目审计年度）+ 章节对应科目（章节 → 报表行 → 科目映射，实施时现读既有映射）取，不再 `.limit(5)` 任取；
- 序时账按年度 + 科目前缀取 `abs(借 − 贷)` 最大的前 10 笔，结果带 `basis: "按金额降序前 10 笔"`；
- 去掉吞异常：查询失败抛出，由路由返回 500（`/report-review` 直调）或由统一溯源记 partial；`ADR-FHIC-16` 的裸会话写法保留。

## 11. R9 外围端点

- `report_trace.trace_section` / `findings_summary`：`Depends(require_project_access("readonly"))`。
- `wp_chat.generate_ledger_analysis`：同上（项目 id 从路径取，实施时现读签名）。
- `wp_document_recognize` POST 与 `/types`：处理函数直接 `raise HTTPException(410, {error_code: "ENDPOINT_RETIRED",
  message: "单据识别入口已停用，请在底稿内用「上传证据」或附件识别"})`，删除对附件表、模型的读取与相关导入；
  删除 `DocumentRecognizeDialog.vue` 与 `components.d.ts` 中它的那一行（只提交这一行）。鉴权基线与路由清单守卫按实际结果更新。

## 12. 测试与变异

| 范围 | 用例 |
| --- | --- |
| R1 | 端点级：可写底稿成功；不可写 403 / 批量逐条失败且无编码；无底稿 422；删除无权 403；按底稿列表无权 404；承接 13 例照旧 |
| R2 | 链上找 sqlstate（直接、`orig`、`__cause__`）；有待执行 → 503 文案含版本；无待执行 → 500；判定读库失败 → 500；缓存 60 秒 |
| R3 | 地址函数往返（凭证键 → query → `readFromUrl`）；`safeReturnTo` 拒外链；弹窗结果分组；标签失败态与可点；横幅显示 / 关闭 / 展开 |
| R4 | 运行时只读禁用回填；确认单飞；预览分页 |
| R5 | 选择器 404 / 409 候选 / 成功；建议条无权只读；跨页取分录 |
| R6/R7 | 取值表前后端对拍；扫描上限与旧行认法；结论查询可见性过滤；处置金额必填、事件载荷 |
| R8 | 试算表行子源四类节点；附注溯源按年度与科目、失败不吞 |
| R9 | 无成员 403；识别端点 410 且不触库 |

变异（磁盘注入、逐字节还原、备份在 `tmp_voucher_closure/mutations/`）：删写门判定；删 `WP_REQUIRED`；503 判定改恒真 / 恒假；
删标签失败态；取值表删一项；扫描旧行认法去掉日期；结论查询去掉可见性过滤；确认单飞去掉；处置金额必填去掉；
`tb_row` 分支去掉；`trace_section` 恢复 `.limit(5)`；外围三处鉴权依赖逐个删；承接 spec 的 4 个靶点。
每个变异记录「红在哪条用例、红的形态」。

## 13. 浏览器实测环境（隔离临时库）

共享库落后 17 个迁移，项目列表本身 500，无法在共享环境走查；且未经放行不改共享库。做法：

1. `docker exec audit-postgres pg_dump` 共享库结构 + 数据，`--exclude-table-data` 排除 `tb_aux_ledger`、`tb_ledger` 等大表，
   导入新库 `gt_tmp_voucher_e2e`；再把小项目（宜宾临港 `c8621493…`，序时账 4,409 行）的序时账行复制进去。
2. 对临时库跑 `MigrationRunner(...).run_pending()`（V235~V251），确认迁移本身能执行。
3. 后端 9981（`DATABASE_URL` 指临时库、Redis 另用库号、存储根指 `tmp_voucher_closure/storage`、不热重载）；
   前端 3031（Vite 代理在配置文件里定死 9981）。浏览器只用 `http://127.0.0.1:3031`。
4. 走查完删除临时库、停进程、删临时目录。

## 14. 非目标、风险与需要用户放行的事

- 非目标：一键导入（ADR-VWL-06）；投影表；`LedgerPenetration.vue` 拆分；`suggest_bookings` 全量载入序时账的性能
  （观察到的风险，另立）；V246 / V251 两个迁移对 `report_generation_run` 的定义冲突（`formula-provenance-envelope` 会话负责）；
  启动时按结构漂移拒绝启动（稳定模式启动本就会执行迁移，本次只做请求期的明确报错）。
- 风险：索引扫描对超大项目（C24 单项目百万空骨架行）走 `project_id` 索引后逐行判 `LIKE`，耗时随行数增长；
  结论取值表只覆盖白名单，宿主新增字段要同步登记（契约测试守住两份一致，不守新字段）。
- 需要用户放行：共享库执行 V235~V251；旧身份治理脚本 `--apply`；推送。

## 15. 实施勘误

（实施中与本设计不一致之处追加在这里。）

### 15.1 与设计不同的做法

- §3 / R1 之外顺带修：抽凭登记的科目改为「被抽中分录」的科目（`sampling_registry_service._filled_unit_lines`），原先写筛选条件的
  第一个科目（E1 筛 1001 / 1002 / 1012 时一律写 1001）；分录回查失败按查不到处理、不让登记整批失败。
- §6.1：预览弹窗表头勾选只改当前页（`handleSelectAll`），不分页时才通知引擎全选；表格数据用响应式切片，行内改核查结果不清勾选。
  引擎只读时「记入未更正错报汇总（推断错报）」同样禁用（原 A13 推送只看宿主只读）。
- §6.2：抽样增强页三个取数端点（截止测试 / 账龄分析 / 月度明细）原先只校登录，任意登录用户可按任意项目 id 取序时账，
  补 `require_project_access("readonly")`（设计 §11 未列）。
- §7.2：建议条「确认」在当前页没有那组分录时，按 `focus_entry_group_id` 取它所在的一页（每页 1 条即本组）；找不到 / 取数失败分别说明。
- §9：处置的描述里已带凭证称呼，不再传 `voucherNo`（错报桥会再追加一次「（凭证:…）」）。
- §10.1：试算表行子源按标准科目精确取构成；本年度试算表没有该科目时返回空（合并项目的试算表在合并模块），查询失败照常抛出记 partial。
  合并页（`ConsolidationIndex.vue`）的试算表行溯源同样带页面年度、子源失败如实提示。
- §10.2：返回新增 `year` / `account_codes` / `trial_balance_basis` / `ledger_basis`；序时账走 `get_active_filter(strict=True)`；
  章节没有对应底稿、项目没有审计年度时写明原因不取数。
- §13：临时库改用重药安徽（`0ec33ac9`）——凭证 0075 的手工挂凭与 E1 引擎登记都在这个项目；`pg_dump` 排除 6 张大表数据后只补本项目
  `tb_ledger` 702,013 行；760 个底稿 `file_path` 改指候选 worktree 的存储副本；项目名加「（临时库）」作可见标记。共享库此时已在
  V251（V235~V251 由别的会话执行），临时库没有待执行迁移，未跑 `run_pending()`；§14「共享库执行 V235~V251」不再需要放行。

### 15.2 变异（任务 19）补出的缺口

首轮 106 条变异里有存活，按缺口补用例而不是改变异：页面接线源码判据 `voucherLinkageWiring.spec.ts`（任务 6 的 AC 写了
「源码守卫确认按钮与函数已删」但原先没有）、`VoucherRowMetaCell.wiring.spec.ts`、`ReportTracePanel.basis.spec.ts`（顺带修查询前
不清旧结果）、`samplingReviewWiring` 补单飞置位与 A13 推送只读、`test_sampling_projection_savepoint_pg.py`（承接 spec 的 R4 保存点
原无用例：真 PG 回滚事务里注入除零 + 反向对照）、`httpMigrationPending` 补 503 非迁移业务码反例、`ConsolidationIndex` 行溯源带年度
与子源失败提示。`mergeVoucherRows` 的 PBT 用了 fast-check 4 已删的 `fc.char` / `fc.stringOf`，从未真正执行过，改写为小值域 +
逐行模型。最终 104 条打红、2 条阴性对照保持绿，逐字节还原（报告 `tmp_voucher_closure/mutations/report.md`）。

### 15.3 浏览器实测（任务 20）发现并修复

| 走查 | 发现 | 修复与证据 |
| --- | --- | --- |
| 抽样增强页把概览年度改成 2024 | 仍列 2025 的 E1 批次：`project_sampling_coverage` 的按底稿汇总不看年度，而同一结果的重复抽凭、存续核对按年度 | `_record_in_year`：批次已抽凭证的年度 → 抽样框账套年度 → 项目审计年度；路由传项目年度。`test_sampling_coverage_year_scope.py` 4 例，变异 q2~q4 全红；临时库 API 现算 2024 为空、2025 仍是 E1 |
| 同页改年度后读取失败 | 表里留着上一次（别的年度）的行 | 读取前清空、表格写「读取失败」；`SamplingEnhanced.voucher.spec.ts` 加一例，变异 q1 红 |
| 报告复核溯源查询失败 | 整页被全局错误边界换成英文「Request failed with status code 500」—— 任务 18 让后端不再吞异常后这条路径变得可达；原用例用 `errorHandler: () => undefined` 吞掉了它 | 页面接住错误、经 `handleApiError` 提示，请求带 `_silent`（`commonApi.traceSection` / `findingsSummary`）；用例改为断言错误不冒出页面，变异 q5 / q5b / q6 全红；浏览器复测页面保留、提示「溯源查询失败」 |

### 15.4 范围外，未修

- 🔴 K1~K13 底稿保存 428（远端头 v1.0.89 起）：渲染快照（`tb_fetch.load_responses_snapshot` 与 K1 / K2 的内联查询）只取
  `item_id / conclusion / remark`，不带 `updated_at`；宿主 `persistence.hydrate(snapshot)` 后 CAS 客户端不知道版本，而保存总是
  `require_if_match: true` ⇒ 重新打开页面后对已有条目的任何保存都 428（走查 s7：K9-8 标「是否异常」保存被拒）。凡在这些宿主里
  「从序时账挂入导入」第二次导入也受影响。修法建议：快照条目带 `version = updated_at.isoformat()`（与 GET 同一口径）。待用户定。
  → 2026-11-04 用户定按建议修，见 §15.5（D2 同根因一并修）。
- 🔴 D2 凭证检查「导入导出」整组不可用：`useD2VcImportExport` 调的 `POST /api/workpapers/{wp}/d2/vc-import-data`、
  `vc-export-template`、`vc-export-data` 后端都不存在（走查 s11 两次导入均 404，界面还会多弹一条英文
  「Request failed with status code 404」）。前序 spec R5 改的 `mergeVoucherRows` 只被这条导入路径调用，目前不可达。
  → 2026-11-04 用户定另立 spec `d2-voucher-check-import-export-endpoints`（只写三件套，未实施）。
- 预览统计「已勾选样本金额」是借 + 贷的代数和，样本含红字分录时显示负数（走查 s6 实测 −1,400,026.83）。
- 同号多张凭证按 409 返回候选是设计内协议，浏览器 console 会记一条「Failed to load resource: 409」。
- 临时库复制自共享库，健康检查因 V233 / V234 checksum 漂移与审计链分叉报 degraded，页面顶部「部分功能暂时不可用」横幅与本 spec 无关。
- `--gt-color-danger` 全站未定义（`VoucherLinkTags` 错误态用它并回退 coral）。

### 15.5 用户定后修复：render 快照条目带 CAS 版本（任务 22，单独提交）

- 范围现扫：只用 render 快照建编辑基线（快照非空就不 GET）的宿主是 K1~K13 与 `GtD2AccountsReceivable.selfLoad`
  （`.hydrate(` 全仓调用点逐个看过；J1~J3、K5 组合式、D4 / F 系列都先 GET）。快照构造点四处：共享
  `tb_fetch.load_responses_snapshot`（K3~K13，K8~K13 经 `pl_render`）、K1 / K2 / D2 各自的内联查询。
- 改法：`checklist_response_cas.checklist_snapshot_entry(row)` 一处产出快照条目（`conclusion` / `remark`，有 `updated_at` 时加
  `version`），版本写法 `checklist_response_version` = `updated_at.isoformat()`，与 GET 回执、`lock_and_check_versions` 预检同口径；
  四处查询加选 `updated_at`；K1 坏账 seed 换显示内容时保留原条目的 `version`（编辑基线仍是库里这一行）。前端零改动
  （`collectChecklistResponses` 展开原条目、D2 映射本来就读 `entry.version`）。
- 守卫：`test_render_snapshot_cas_version.py`（fake 会话只在 SELECT 列表含 `updated_at` 时给行带该列 ⇒ 漏选即红；四个构造点逐个；
  seed 保留 / 新行不造版本）；`test_render_snapshot_cas_version_pg.py`（真 PG：快照版本原样当 `if_match` 过严格预检，
  反向对照不带 `if_match` 为 428）；前端 `renderSnapshotCasBaseline.spec.ts`（快照 → hydrate → PUT 带 `if_match`、不偷偷 GET；
  D2 `selfLoad` 映射源码判据）。变异 11 条：10 条打红；「hydrate 不调 `cas.remember`」存活，是等价变异（版本另经条目本身进
  `save`），换成「hydrate 丢掉条目版本」后打红。
- 浏览器（隔离临时库，后端重启加载新代码）：K9-8「是否异常」新开页面切两次、重新加载再切两次，4 次 PUT 全 200，首次
  `if_match` 等于快照版本、之后等于上次回执版本（`browser/s12-k9-cas-save.json`）；D2 明细表「三、审计说明」改字再改回，
  2 次 PUT 全 200（`browser/s12b-d2-cas-save.json`）。D2 修复前的 428 未在浏览器复现，依据是同一快照路径与 K9 的实测。
- 归因：K 选集（3603 例）与远端头对比新增失败 4 条，全是 `*_ai_generate_route_registered` —— 候选 worktree 里走查用的
  `.env` 打开了 AI 服务、请求连到不存在的测试库；移走 `.env` 后 157 例全过，属环境差异。

### 15.6 提交前复查补出的问题

- 领域边界检查（`check_domain_boundaries.py`，远端头本身已有 34 条基线外违规）候选树比远端头多 1 条：任务 18 的
  `report_trace_service._section_account_codes` 引了底稿域的 `WpMappingService`（报表域不得依赖底稿域）。改用报表域
  `report_stale_service.account_codes_for_wp_code`，两者读同一份 `wp_account_mapping.json`，1025 个编码逐个同值
  （无 BOM、无小写编码）；复跑后候选树与远端头违规集合相同，报告溯源与 stale 用例 46 例全过。

### 15.7 §14 放行事项的执行记录

- 共享库迁移：共享库已由别的会话升到 V251，无需执行（§15.1）。
- 旧身份治理 `--apply`（2026-11-04 用户放行）：执行前干跑与 11-03 报告逐行一致；32 行备份 + 回退 SQL 存
  `tmp_voucher_closure/backups/`；31 行补全、1 行孤儿标记，改动只落在五列；复跑干跑只剩孤儿 1 行（前序 spec 任务 11）。
- 推送：经 `push_version.py`（任务 21）。
