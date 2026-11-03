# 平台全局显示设置收口：需求

## Summary

本 spec 收口平台级字体、字号、金额显示、账号持久化、项目默认金额单位、账套导入单位归一、正式导出边界和全局接线。范围覆盖前后端公共层、核心页面、合并与底稿运行时，不以单页修补、纯函数存在或既有单测通过作为完成依据。

已批准的产品边界如下：平台 UI 只使用 GT 品牌字体回退策略，不提供任意字体族选择；四档显示字号固定为 `xs/sm/md/lg = 11/12/13/14px`；屏幕金额单位优先级为“用户覆盖 > 当前项目默认 > 平台默认元”；正式 Excel/Word/PDF 不读取个人浏览器偏好；新导入账套统一按元存储并保留来源单位证据；未经再次放行，不批量改写共享真实 PG 的既有金额。

本 spec 采用以下已评审假设：账号金额单位覆盖可为 `null`，表示“跟随项目”；小数位为 0~6 的整数；项目正式输出金额单位由具有 `project:edit` 权限的项目成员修改；直接 PDF 只接受当前界面已有的审计报告、四张财务报表和附注类型。既有数据若无法证明存储口径，只能标为 `legacy_unknown`，不得因页面或导出需要而伪称已按元归一。

## Functional Requirements

### R1. 固定字体策略
- UI 主字体必须使用一条固定、可审计的 GT 品牌回退链，不得提供字体族选择，也不得新增许可证不明确的商业字体或远程字体依赖。
- 公式/代码使用固定等宽字体族；数字使用固定数字字体族并启用等宽数字；正式附注、审计报告和模板导出的字体由文档/模板语义决定。个人偏好只改变显示字号，不改变这些字体族。
- 前端包内无授权字体时必须明确使用系统回退字体，并在开发文档说明各平台回退顺序。

### R2. 账号级显示偏好
- 当前登录用户可配置：金额单位覆盖（跟随项目/元/千元/万元）、四档字号、0~6 小数位、零值显示、负数红色、变动高亮阈值、表格密度、表格编辑方式和按页面保存的固定列。
- 后端提供只操作当前用户的 GET/PATCH API。无记录时完整响应必须为 `amount_unit_override=null`、`font_size=sm`、`show_zero=false`、`decimals=2`、`negative_red=true`、`highlight_threshold=0.2`、`density=default`、`grid_edit_mode=excel`、`fixed_columns={}`、`revision=0`、`updated_at=null`；PATCH 成功返回完整归一结果。
- PATCH 必须严格拒绝额外字段、空业务补丁、非法枚举/范围和超限固定列；`base_revision` 只用于 CAS，不是偏好字段。无记录的两个 revision=0 首写发生唯一键竞争时，失败方返回带 `current` 的 409，不得伪装成功。
- `fixed_columns` 在线协议仍是完整对象，但客户端的并发重放粒度必须是 `pageKey`。客户端必须分别跟踪脏 `pageKey` 与删除 tombstone；收到 409 后以服务端 `current.fixed_columns` 为基底，只重放本机脏页或删除对应页，再以新 revision 最多重试一次。不同页的并发成功修改必须合并保留；同一页冲突按本机最后一次明确修改重放。
- 每个标量字段、固定列 `pageKey` 和删除 tombstone 必须持有单调本机 mutation epoch。PATCH 发出时冻结值、操作和 epoch；成功或 409 只可清除 epoch 未变化的发送项。在途期间产生的较新值必须覆盖响应 `current` 并进入下一次 flush，409 的一次重试只处理该发送代际，不得清除或降格新代际。账号切换必须取消请求并清除全部 epoch、脏页、tombstone 和待同步请求。
- 设置必须跨浏览器/设备同步。`localStorage` 只能作为按 `userId` 分区、TTL 固定 30 天的非权威缓存；旧的未分区键 `gt_display_prefs` 不得继续读取或上传为任一账号的权威偏好。
- 损坏、过期或越界的缓存/响应必须逐字段归一到安全默认值；过期缓存连同待提交补丁均不得应用。`localStorage` 的 SecurityError/QuotaExceededError 和非法小数位不得阻塞登录或让 `Intl`/`toLocaleString` 抛出 `RangeError`。

### R3. 唯一有效显示偏好层
- 前端必须有唯一的 effective display preferences 层，屏幕金额单位按“用户覆盖 > 当前项目 `amount_unit` > `yuan`”计算，其他显示项按“账号值 > 平台默认”计算。
- 账号加载、项目切换、账号切换、刷新和重新登录必须保持响应式；旧账号的缓存、晚到响应、保存定时器和待提交补丁不得污染新账号。
- project store 必须持有可空 `projectAmountUnit`：项目 ID 改变时同步清空，只有 `contextSeq` 仍匹配的详情响应才能赋值；缺失/非法值降级为元并记录开发告警，请求失败保持 `null`，不得沿用上一项目单位。
- 偏好 API 不可用时，登录和页面挂载仍应继续：同账号可使用未过期且已校验缓存，无缓存则用平台默认，并明确显示“仅本机/待同步”状态。
- 现有 `/settings` 继续保持 admin-only。新增所有登录用户可访问、只挂载显示偏好面板的 `/display-settings`；普通用户不得因本功能接触 JWT、数据库、模型或存储配置。

### R4. 项目默认金额单位
- `projects.amount_unit` 必须在迁移、ORM、响应 schema、service 和 router 五层一致，合法值仅为 `yuan/qian/wan`，既有项目安全默认 `yuan`。
- `GET/PUT /api/projects/{project_id}/config` 不得再用 `getattr/hasattr` 静默回退或忽略写入；读取需项目只读权限，修改需 `project:edit` 权限，非法值整单拒绝。
- 项目详情和前端项目上下文必须携带该值；修改后，选择“跟随项目”的用户立即看到新单位，显式个人覆盖不被改写。

### R5. 字号、密度、固定列和底稿运行时接线
- DefaultLayout 必须初始化账号偏好、根 CSS 变量和全局表格重排监听；`--el-font-size-base`、Element Plus 表格表头/正文/`.cell`/表内输入、Teleport 弹窗/抽屉及底稿数据格必须读取统一显示字号。`gt-polish.css` 等高优先级固定 12px 规则必须删除或改读变量。
- 11/12/13/14px 必须在仪表盘、TrialBalance、ReportView、DisclosureEditor、HTML 底稿和合并页的真实数据单元格 `computedStyle` 成立；仪表盘只验字号、密度和非金额不缩放，不新增虚假金额卡。
- `GtWpRenderer` 必须绑定 `runtime.fontStyle`；无生产调用方的 `GtWorkpaperShell` 不能被当作生产接线证据。局部固定 `header-cell-style/cell-style/font-size` 不得覆盖核心数据表的有效偏好。
- 新增 wrapper 与原生 `el-table` 共用的固定列策略。有效集合固定为 `mandatory ∪ (saved ∩ allowed)`，用户列只允许左侧固定；过期列键不生效且设置面板必须提示。TrialBalance、ReportView、DisclosureEditor、`workpaper:<componentType>` 和 `consolidation:<tab>` 必须各有稳定 pageKey、allowed/mandatory 列矩阵。
- 表格密度与编辑方式必须由同一账号偏好驱动；切字号后所有已挂载 `el-table` 必须执行重排。

### R6. 金额格式化语义和核心模块覆盖
- 跨后端、API、前端和 Word 克隆路径必须使用同一度量枚举：`amount|quantity|count|ratio|exchange_rate|unit_price|text`。附注详情下发与 headers 等长的稳定列 ID、`column_kinds` 和 `column_ratio_scales`；底稿 `GtColumn` 与 render schema 显式携带同一语义。只有 `amount` 可使用金额单位除数，其余 kind 的除数恒为 1。
- `ratio` 必须同时携带 `ratio_scale=fraction|percent_points`，其他 kind 禁止携带该字段。`fraction` 原值 0.2 与 `percent_points` 原值 20 都显示为 `20.00%`（比例固定 2 位，design §17 G4），两者均不得使用金额除数；核心列无法确定比例尺度时必须 fail closed，不得默认乘或不乘 100。
- `GtAmountCell` 与公共 formatter 必须消费唯一有效偏好，并覆盖试算表、财务报表、附注、底稿运行时、合并模块、LedgerPenetration 及其核心弹窗/抽屉。Dashboard/项目看板仅接字号和密度，因为当前没有金额业务字段。
- 数量、笔数、比例、汇率、单价、期间、行号等非金额度量不得套用金额单位换算；可编辑原始值、计算值和复制/求和用的原始元值不得因显示单位改变。核心未知 kind 必须 fail closed，不能靠列名正则临场猜测。
- 附注标题行库及逐表 override 是列语义来源；四版附注模板必须生成并校验逐列 kind 目录，`NoteWordExporter` 的普通路径和 `note_template_table_look.render_cloned_table` 克隆路径必须共同消费。
- 未在本 spec 清完的全仓遗留必须生成可伪证台账，记录真实数量、稳定 AST 锚点、语义类别、豁免理由和后续批次，不得宣称清零。

### R7. 附注、查账与数据集单位状态
- 附注屏幕金额单位必须直接跟随全局 effective 单位，删除 `gt_note_amount_unit`、独立选择器及第二套状态；正式附注导出仍使用项目/模板单位。
- LedgerPenetration 与 TrialBalance 必须共用数据集单位状态合同和 presenter，并把来源/存储口径与用户显示单位分开。只有 `normalized_v1` 可显示“存储单位：元”和换算因子；`legacy_unknown` 显示“来源未知、换算未确认、存储口径未知（历史数据未归一）”；旧顶层声明只能显示为“历史声明，存储口径未验证”。
- 加载/切换数据集、页面切换和刷新不得重置用户显示单位；显示单位始终来自 effective preferences，与三类数据集状态独立。
- `GtInfoBar` 的“单位”仍指项目/组织单位而非金额单位；如修改可见名称，必须使用清晰中文并验证全部调用方仍传项目列表。

### R8. 新账套导入单位归一
- `/api/projects/{project_id}/ledger-import/detect`、`/account-chart/preview` 与 `/ledger/smart-preview` 必须从 `upload_token` 对应的不可变 bundle 在服务端校验文件 SHA-256 后生成同一 `UnitDetectionSummary`，包含 `status/candidates/unsupported_labels/suggested_unit/detector_version/evidence_digest`。`元/千元/万元` 映射为三枚举；`百元/亿元/外币单位` 等进入 `unsupported`；旧 bundle 缺 hash 必须要求重新上传。所有会创建 bundle、预览账套文件或读取增量基准的已注册 preview/detect 端点，包括 `/account-chart/preview`、`/ledger/smart-preview`、`/ledger-import/detect`、`/import/preview` 和 `/ledger-data/incremental/detect`，均必须先通过当前路径项目的 `edit` 权限校验；只有登录态不得读取或创建其他项目的导入证据。
- `/api/projects/{project_id}/account-chart/import` 与 `/api/projects/{project_id}/import` 两个无生产前端调用、但仍已注册且可直接写四表的同步 POST 必须在项目 `edit` 鉴权后固定退役为 410 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB`。退役路由不得再导入或调用 `run_account_chart_import`、`import_service.start_import/start_import_streaming`、四表 writer 或任何 ImportJob 创建函数；既有 E2E 应改验固定 410 与零写。
- `/ledger-import/submit`、仍在生产使用的 `/account-chart/import-async` 与 `/ledger/smart-import` 必须共用无默认值的 `UnitConfirmationInput` 和服务端合同构造 helper，在创建队列锁或 ImportJob 前重新计算 bundle hash、检测摘要和 digest。确认必须与摘要绑定；检测结果变化返回 409，unsupported 或未确认返回 422。兼容入口收到没有 `upload_token + evidence_digest` 的直接文件请求时，只能落不可变 bundle 并返回 428 `SOURCE_UNIT_CONFIRMATION_REQUIRED` 及新 token/摘要，不得 enqueue 或修改账套数据。
- 服务端必须先校验并构造 `UnitNormalizationContract`，再校验增量基准，随后把完整合同、合同 digest、`payload_style` 与增量计划持久化进 ImportJob；在此之前不得执行任何 incremental 删除、覆盖或合并。合同中的 factor 只能由 `source_unit` 派生并固定为 `yuan=1/qian=1000/wan=10000`，不得由客户端或调用方决定；检测摘要、确认人、作业创建人和 canonical contract digest 必须相互一致。`ImportJobRunner` 每次 claim、retry 或 resume 都必须在 feature flag 分流前重新验证持久化合同；v2 与降级 worker 都把合同作为无默认必填参数，部署时已排队但缺失或被篡改的旧作业 fail closed。
- `POST /api/projects/{project_id}/ledger-data/incremental/apply` 必须退役并固定返回 410 `INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB`，不得调用任何删除 service。`/ledger-data/incremental/detect` 必须返回检测时当前 active 的 `base_dataset_id`、其 `source_summary.unit_normalization.contract_digest` 形成的 `base_unit_contract_digest` 和检测出的 periods；前端只能把这两个不可变 CAS token 连同 `incremental/overlap_strategy/file_periods` 随统一 submit 原样提交。submit、seal 和 activation 在项目+年度锁内均必须要求当前 active ID 与 unit contract digest 逐值相同；`LedgerDataset` 不新增或伪造整数 version。删除/合并算法只能由 worker 在合同与三次基准复验后调用，不得直接修改当前 active dataset。
- 导入必须采用 staged 原子可见协议，而不是把百万行放进一个长事务。每次执行尝试从不可变 bundle 创建新的 staged dataset；四张 Tb 表的 staged 行统一写 `dataset_id=<stage>`、`is_deleted=false`，convert→normalize 后的批次可提交，但全部生产读者必须通过 fail-closed active predicate：有 active 时只读该 dataset_id，无 active 时只读 `dataset_id IS NULL` 的 legacy 行，active 状态查询失败直接上抛且不得 rollback 后退化。绑定历史版本的读取只可使用显式 `force_dataset_id`。同步裸过滤、`project/year/is_deleted=false` 裸读和“无 active 即读所有未删行”均禁止。
- `AccountChart` 使用独立可见性协议以保留现有 `(project_id, account_code, source) WHERE is_deleted=false` 唯一索引：标准科目不参与切换；staged 客户科目写 `is_deleted=true`。短激活事务先隐藏旧 active 或 legacy NULL-dataset 客户科目，再放开新 dataset 客户科目，同时完成数据集状态、激活记录、outbox 与 attempt 终态；任一步失败整单回滚。数据集 rollback 必须执行严格逆操作，seal/cleanup 始终按 dataset_id 统计和删除，不受软删位影响。
- 完整 row-count/post-hash 封存前 active dataset 和所有登记生产读者的有效结果必须保持不变。失败或中断的 stage 必须标记 failed 并确定性清空其科目表及四表行；只有合同、bundle hash、base dataset ID+unit contract digest、row counts 与 post-hash 已封存且复验一致的完整 stage 可走 activation-only 恢复，其他 retry/resume 必须先清旧 stage、再创建新 attempt 重建，禁止对已写 staged 行再次归一。四表读取面与客户科目读取面必须由真实查询符号反查的 AST 注册表闭合；未登记读取、裸读或失效 helper 均使守卫失败。
- incremental 只允许基于 `source_summary.unit_normalization.storage_unit=yuan`、受支持 normalization_version、可重算 `contract_digest` 且证据完整的 active dataset。`legacy_unknown`、只有旧顶层单位、hash 不完整或 detect 返回的 active ID/digest 已变化时返回 409 `BASE_DATASET_UNIT_UNVERIFIED` 或 `BASE_DATASET_CHANGED`，不得写入或自动迁移一行。
- 两条导入执行引擎共用 `_AMOUNT_FIELDS_BY_TABLE` 和同一 Decimal 归一内核。余额/辅助余额只换算 `opening_balance/opening_debit/opening_credit/debit_amount/credit_amount/closing_balance/closing_debit/closing_credit`，序时账/辅助明细只换算 `debit_amount/credit_amount`；数量字段及全部 `*_fc` 原币字段不换算。converter 输出的金额字段合同只能是 `Decimal|None`：空值/空白归一为 None 并在 canonical hash 中使用稳定 null token；非空不可解析值为 fatal。非空值在乘法前必须 `is_finite()`，NaN/±Infinity 固定报 `LEDGER_AMOUNT_NOT_FINITE`；随后执行 `value * factor`、以 `ROUND_HALF_UP` 量化到 `0.01`，最后按 Numeric(20,2) 的 18 位整数边界检查溢出。两 converter、normalizer、dry-run/hash 与恢复路径不得采用不同解析、空值或舍入规则。
- 每个新数据集必须保存来源单位、存储单位 `yuan`、换算因子、检测摘要、确认人/时间、字段合同版本、合同 digest、attempt id 和归一版本；同一批数据不得重复换算，重试、恢复和激活不得改变已确定合同。
- 必须维护一份从应用实际已注册 router 反查的“账套导入可执行入口注册表”：逐个登记 preview/detect、固定 410 退役入口、三个 ImportJob submit、纯读 status、受控 recovery、worker、四表/科目表 writer 与恢复入口之间允许的调用关系。status 必须按对象反查项目并至少 readonly；recovery 必须验证对象属于路径项目、走 edit 门且不得接收新文件/金额值。TestClient 与 AST 守卫必须从真实 app route table 和 writer/ImportJob 创建符号双向校验；任何未登记且可触达四表 writer、active 切换或 ImportJob 创建的旁路都必须失败，不能靠只扫描三个已知 URL 或随意新增豁免行证明闭集。
- 既有数据只做兼容分类和共享 PG 的数据库级只读调查。共享 PG baseline/dry-run 必须在任何业务查询前进入 PostgreSQL `READ ONLY` 事务、全程复用同一连接且禁止另开可写连接，最终统一 rollback。任何真实 apply 或 rollback 都必须走与共享 dry-run 分离的显式写入口，并具备等价的授权闸门、单数据集事务、溢出检查、确定性前后 hash/history 及可逆证据；apply history 必须保存变更前单位元数据 canonical snapshot+digest，rollback 反向 hash 等于 before-hash 后精确恢复原 `legacy_declared|legacy_unknown` 状态并追加独立 history，绝不得残留为 `normalized_v1`。本 spec 未获再次放行时不得执行真实批量改值。

### R9. 正式导出单位边界
- 正式 Excel/Word/PDF 的每个输出区域必须有且仅有一个机器可读权威单位。受 `--check` 守护的模板 sidecar 声明文档默认单位、稳定 `section_id/table_id` 对应的局部表单位及有限 label binding；表级 > 文档默认 > 项目 `amount_unit` > 平台元。仅校验 binding 指定的标签槽，章节叙述/表体自由文本不参与推断或冲突判断。
- 自定义底稿不得把“xlsx 本体”或 `divisor=1` 当作无声明兜底。权威确认采用可到达的两阶段协议：首次 `ingest` 只保存不可变文件并返回 artifact ID/SHA-256；服务端 preflight 再产生稳定 sheet/region 身份、measure kind 与 label 候选；用户随后以 artifact hash+preflight digest CAS 对全部 amount region 确认 `yuan/qian/wan` 和 label binding；finalize/instantiate 只接受已绑定且 hash 未变化的 manifest。实例化 WorkingPaper 时保存与完整文件 SHA-256 绑定的 authority 行，逐个金额 region 声明稳定 region/sheet 身份、单位、label binding 与 `values_already_in_declared_unit=true`。结构或标签漂移必须回到 preflight 并重新确认；旧 `/api/custom-templates` 元数据链不得进入正式实例化。缺声明、当前 hash 不匹配、未知 region、金额 region 漏登或标签冲突均固定返回 `EXPORT_UNIT_POLICY_INVALID`，不得正式导出或归档。
- 后端统一返回结构化 `ExportUnitPolicy`（来源、单位、除数、中文标签、版本和区域策略）；正式导出服务只接项目/模板 policy，不接 user preference。前端 `exportUnit.ts` 必须在试算表、报表、附注和底稿正式导出入口消费只读 policy preflight，仅展示/校验 authority，不在浏览器自行决定单位。项目或模板单位非法、区域 authority 缺失/冲突、稳定 ID 失效或金额列 kind/比例 scale 不明时必须 fail closed。
- 附注 `export`、`export_with_meta`、template/programmatic 模式、普通表、clone 表、OnlyOffice 在线编辑保存和交付件章节刷新必须显式消费或继承同一 policy；不得从 exporter 实例状态或“当前项目 policy”猜测既有文件单位。所有 `doc_type=disclosure_notes` 且有 `file_path` 的正式版本，不论 `created_via`，都必须成对持久化可严格还原的 canonical policy snapshot 与 SHA-256 digest。OnlyOffice 打开前必须校验底版证据，回调只能按 `base_version_no` 原样继承并重算底版 digest；编辑期间项目单位变化也不得改用当前 policy。历史无证据底版返回 409 要求整份重建；refresh 继承当前版本 pair，只有整份 rebuild 解析并建立新 policy。章节增量刷新发现证据缺失、pair 不完整或当前解析 digest 与版本不一致时，必须返回 409 `EXPORT_POLICY_CHANGED_REQUIRES_FULL_REBUILD` 且零改动。
- 必须从实际文件 sink 反向建立 `EXPORT_SURFACE_REGISTRY`，覆盖前端 `XLSX.writeFile/exportData/exportMultiSheetData/exportToBytes` 和后端 Office/PDF/ZIP `FileResponse/StreamingResponse` 生产出口；每个出口必须且只能分类为 `formal|data_exchange|template|non_amount`。`formal` 显式走 ExportUnitPolicy；`data_exchange` 只输出规范原值并在文件中写机器可读来源单位和可见“非正式出具”说明，禁止读取 display preferences；`template/non_amount` 必须由可执行谓词证明没有金额载荷。未登记、重复分类或分类谓词失效均 fail closed。
- 试算表 HTTP/summary/bulk、单张/整套财务报表、附注 Word、底稿公共 Excel 的两个生产调用方、审计报告五个财务金额占位符、组合导出包、项目归档包和直接 PDF 必须登记为 formal consumer 并共用 policy；`ReportBodyService.fill_placeholders` 必须以无默认参数接收 policy，五个金额占位符各有稳定 region ID/kind，报告生成、全套执行、组合包和 PDF 逐跳传入。`useAuditSheetTable` 的“可直接归档”导出必须改走受控正式底稿 exporter；合并试算/差额/附注本地数据导出固定归为 data_exchange 并输出元口径原值与说明。
- 复制既有文件的消费者不得用 exporter 调用扫描代替。普通底稿归档必须绑定当前不可变内容版本、文件 SHA-256 与 policy snapshot/digest；若明确归为 data_exchange，则必须绑定该版本的机器可读存储单位。无版本证据的历史金额文件阻断归档。底稿导出路由必须先执行 `authorize_wp_read`。
- 直接 PDF 请求必须严格使用 `project_id + year + 非空且去重的 document_types`；create 按 body 项目鉴权，status/download 按 task 反查项目后鉴权，history 按路径项目鉴权。可选 `password` 仅允许 `null` 或 UTF-8 长度 1~127 bytes 的原字符串，空串/超限均为 422 `EXPORT_PASSWORD_INVALID`，不得 trim。全局 `RequestValidationError` 处理器必须对该路由结构化删除所有错误项的 `input/context`，密码错误使用固定消息；错误类型、额外字段或嵌套输入也不得在 422 回显密码，禁止用字符串替换脱敏。密码只在同步执行期间以内存参数传给最终 `PdfWriter.encrypt`；数据库只保存 `password_protected`，日志、任务 options、policy snapshot 和错误文本不得保存明文。引擎从真实报表/附注/审计报告产物取内容，不能使用空占位数据；请求 PDF 时转换失败返回中文 503，不得回退 HTML。
- 导出值与单位标签必须一致。由 Office 文件转换出的 PDF 继承同一源 policy；组合包不得以空 bytes、placeholder 或捕获 policy/source 错误后漏件的方式宣称成功，任一必需产物失败必须整包失败。归档清单必须绑定每个交付任务的精确最新版本、版本号、文件 SHA-256 和 policy snapshot/digest；打包前重算文件 hash 与当前项目/模板 policy，缺失、pair 非法、文件不符或 policy 已变化均以 blocking code 要求先重建。归档 `manifest.json` 必须逐件记录 version id/no、file hash 和 policy digest。个人偏好变化不得改变正式产物。

### R10. 守卫、文档和全链验证
- `check-format-single-source.mjs` 与 `no-bare-amount-cell` 必须共用 AST/结构化语义分析器，区分金额与非金额、只读展示与编辑控件、生产与测试；解析崩溃、输出缺键或扫描文件/候选为 0 必须 fail closed。扫描器必须从固定生产根按 Git 跟踪文件加未跟踪候选文件计算 `eligible_files`，逐 scope 输出 eligible/parsed/skipped；任何未登记 parser exemption 的 skipped 文件和 include root 缩窄均为 `SCAN_SCOPE_DRIFT`。核心页面、公共组件、正式导出/复制入口必须由符号 manifest 逐项证明存在且被分析，不能用全局非零计数替代覆盖闭合。
- 退役 `no-bare-amount-cell-tables=92` 与 `no-bare-amount-cell-violations=88` 双口径，只保留一个由 `--update-baseline` 生成且拒绝上调的真实基线。新口径若高于历史有效上限 88，必须继续修真实违规，不得抬高基线。
- 遗留台账必须通过 JSON Schema；每项使用有限 verify 谓词、AST fingerprint、reason code、owner 和 next batch。CI 必须验证条目仍命中、理由仍成立、已合规条目已删除，禁止自由文本 allowlist 蒙绿。
- 更新 `docs/frontend/display-preferences.md`，纠正默认万元等过期内容，写清优先级、账号同步、项目默认、显示/正式导出边界、数据集单位状态、非金额语义和开发接入方式。
- 验证必须包含后端 pytest、前端 vitest、ESLint/格式守卫、候选树或单区域 vue-tsc、与 HEAD 的失败归因、隔离 Playwright 逐页实测和全部新守卫/关键接线的故障注入；PBT `max_examples=5`。

## Non-Functional Requirements

- **安全与隔离**：账号 API 无用户 ID 写入口；项目配置和全部账套 preview/detect/submit 执行项目级权限；日志不得记录完整偏好载荷、固定列 pageKey、令牌、账套内容或 PDF 密码，任何任务/options/policy 快照也不得持久化密码明文。已注册的 `AuditLogMiddleware` 必须对偏好 PATCH 结构化脱敏，只落 revision 和顶层 changed_fields。
- **可用性**：偏好加载/保存失败不得阻塞登录；保存防抖，单账号每次变更只提交增量；6000 并发目标下读取走用户主键、写入无全表锁。
- **数据安全**：迁移号实施时动态现扫并创建 V/R 配对；迁移 DDL 幂等；R 在项目非默认单位、任一偏好/导入 attempt/custom authority 行、不可由旧字段无损表示的 export task、正式 Word policy snapshot/digest 或底稿内容版本单位证据存在时必须 `RAISE EXCEPTION` 并整单回滚，不得以 warning 后删列。共享真实 PG 的 baseline/dry-run 必须在第一条业务 SQL 前执行 `SET TRANSACTION READ ONLY`（或使用专用只读角色并仍验证只读状态），全调用图复用该连接、禁止另开连接、finally rollback；真实批量金额更新不在本轮授权内。
- **兼容性**：所有用户可见文案为中文；不引入 i18n、字体主题或新字体依赖；现有金额原值、公式和正式模板字体不得被显示偏好改写。

## Acceptance Criteria

1. **AC-01**：无偏好记录的 GET 返回 R2 规定的完整 snake_case 默认 JSON；四档线值逐一映射 11/12/13/14px；PATCH 仅改提交字段、revision+1，并返回完整归一结果。
2. **AC-02**：偏好 API 未登录为 401；A 用户不能读写 B 用户偏好；额外字段、空业务 patch、非法枚举、越界小数位/阈值和超限 fixed_columns 均为 422；旧 revision 为 409 且含 current。TestClient 成功 PATCH 后读取 `logs.new_value`，只见 revision 与顶层 changed_fields，金额单位、字号、小数位、阈值、固定列内容及 pageKey 均未落日志；移除实际注册中间件 redactor 的变异必须打红。
3. **AC-03**：两个无记录 revision=0 首写竞争时恰一方成功、另一方得到 409 current；service 测试证明只 flush，端点测试证明 router commit/异常 rollback。
4. **AC-04**：缓存键只为 `gt_display_prefs:v3:${userId}`，TTL 恰为 30 天；旧 key 不读取。损坏 JSON、过期 pending patch、`decimals=999`、SecurityError/QuotaExceededError 均不抛异常，账号 A→B→A 无泄露，切换时全部 mutation epoch、脏 fixed pageKey、删除 tombstone 与在途重试清空。挂起首个 PATCH 后再次修改同一标量、覆盖或删除同一页、修改另一页时，首个成功/409 均只能清发送 epoch；较新值保留并由下一代 PATCH 提交。
5. **AC-05**：项目 `amount_unit` 在动态 V/R 迁移、ORM、响应 schema、service/router 和前端 store 逐层往返；三值成功、非法值 422、非成员 403、归档写 423，任何一层删接线的变异均失败。
6. **AC-06**：project store 在项目 ID 变化时先把 `projectAmountUnit` 清为 null，只接受匹配 `contextSeq` 的响应；A(wan)→B(慢/失败) 不沿用 A，用户 qian 覆盖始终优先，无项目/失败时 effective 为 yuan。
7. **AC-07**：普通审计员可进入 `/display-settings` 并保存 R2 字段，但仍不能进入 admin-only `/settings`；管理员两处复用同一 `DisplayPreferencesPanel`；本 spec 不挂载 UserSettingsExtension 的默认准则/审计类型。
8. **AC-08**：真实 Element Plus DOM 的 body cell、header cell、表内编辑输入、Teleport 弹窗 cell、HTML 底稿 cell 在四档下 `computedStyle.fontSize` 逐一为 11/12/13/14px；`gt-polish.css` 不再以固定 12px 覆盖，字体族豁免只改变 family 不阻断字号。
9. **AC-09**：固定列策略在 TrialBalance、ReportView、DisclosureEditor、一个 `workpaper:<componentType>` 和一个 `consolidation:<tab>` 上等于 `mandatory ∪ (saved ∩ allowed)`；过期 key 被忽略并提示，刷新和账号切换保持隔离；字号变化触发已挂载表格 `doLayout`。两个设备从同一 revision 修改不同 pageKey 后最终两项并存；修改同一 pageKey 时本机最后一次明确值重放；删除页以 tombstone 在 409 后仍删除且不抹掉其他页。首次 PATCH 在途时对同页再次覆盖/删除所产生的新 epoch 不得被首次成功或冲突重试清掉；第二次冲突保持全部尚未确认 epoch 为待同步。
10. **AC-10**：真实金额 10000 元在 effective 万元显示为 1.00、元显示为 10,000.00；零值、负数、高亮和小数位按账号设置变化，复制/求和读取的 `data-gt-value` 始终为 10000。
11. **AC-11**：跨层稳定列 ID、`column_kinds`、`column_ratio_scales`、render schema 与 GtColumn 对 amount、quantity、count、ratio、exchange_rate、unit_price、text 逐类对拍；`ratio/fraction` 原值 0.2 与 `ratio/percent_points` 原值 20 都输出 `20.00%`（比例固定 2 位，design §17 G4），两者 divisor 恒为 1。切万元后数量 10000、汇率 7.2、两种比例和单价 10000 均不除以 10000，四版附注普通与 clone Word 路径结果一致；删除或互换任一 ratio_scale 的故障注入必须在预期夹具打红，核心 ratio 缺 scale 时 fail closed。
12. **AC-12**：Dashboard 只验证字号/密度以及年度、项目数、工时、进度等非金额不缩放；金额 10000 的页面实测来自 TrialBalance、ReportView、DisclosureEditor、HTML 底稿、合并页和 LedgerPenetration，不新增虚假金额卡。
13. **AC-13**：附注源码与运行时均不再读写 `gt_note_amount_unit`；LedgerPenetration 与 TrialBalance 对 normalized_v1、legacy 声明、legacy_unknown 三类使用同一 presenter，只有第一类显示“存储单位：元/因子”，加载数据集不重置 effective 单位。
14. **AC-14**：三条正式 preview/detect 响应都返回逐字段相同的 `unit_detection`；bundle manifest 含每文件 SHA-256，三个 submit 入口均在建锁/job 前从 bundle 重算摘要并核对 evidence_digest。元/千元/万元可确认，旧 bundle 缺 hash 或内容变化要求重传，百元/亿元/外币单位为 422 unsupported，摘要变化为 409；兼容 submit 直接传文件但无 token+digest 时只建 bundle，返回 428 `SOURCE_UNIT_CONFIRMATION_REQUIRED`，ImportJob、队列和四表均 0 写。所有已注册账套 preview/detect 端点对非成员/只读成员分别为 403，具备 edit 权限才可调用；`/account-chart/import` 与 `/api/projects/{project_id}/import` 固定返回 410 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB`，且旧 import service、ImportJob、队列和科目表/四表 writer 调用数均为 0。
15. **AC-15**：`ledger-import/submit`、`account-chart/import-async` 和 `ledger/smart-import` 都必须向共享 helper 传无默认的 `UnitConfirmationInput`，并在合法 UnitNormalizationContract 与适用的 active baseline 门通过后，把完整 contract、contract_digest、payload_style 和增量计划持久化进 ImportJob。`incremental/detect` 对 normalized active 返回 `base_dataset_id + base_unit_contract_digest + detected periods`，前端逐值原样提交；submit、seal、activation 三次更换 active ID 或篡改 digest 都固定失败 `BASE_DATASET_CHANGED` 且 active/四表零变化，模型、DTO 和代码中不得出现虚构的 `base_dataset_version`。model/runtime 校验拒绝 `wan+factor=1`、确认人与 job.created_by 不同、检测/确认 digest 不同及 canonical digest 被篡改；runner 在每次 claim/retry/resume 且 feature flag 分流前重验。v2 与降级 worker 的支持单位夹具均正确换算，缺合同旧作业均以 `SOURCE_UNIT_CONFIRMATION_REQUIRED` 失败。入口注册表从真实 app route table 反查 ImportJob 创建、科目表/四表 writer、active 切换和恢复入口，任何未登记旁路或登记符号失效均打红。
16. **AC-16**：`POST /ledger-data/incremental/apply` 在有效登录下固定返回 410 `INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB` 且删除 service 未被调用，LedgerDataManager 不再请求该端点。incremental 基准只有 `storage_unit=yuan`、受支持 normalization_version、可重算 unit contract digest 且完整证据/hash 时可用；legacy_unknown、摘要变化、unsupported 或 active ID/digest 变化时 PG 四表 0 行变化。每个 attempt 只写一个新 staged dataset；四张 Tb staged 行均为 `is_deleted=false`，但每次批次提交后所有登记生产读者仍只返回旧 active，首次导入无 active 时只返回 `dataset_id IS NULL` legacy 行、没有 legacy 时返回空，active 查询故障必须上抛且不得扩大结果。AccountChart staged 客户科目均为 `is_deleted=true`，激活按“隐藏旧/legacy→放开新”顺序满足 partial unique；在 convert、任一批次、seal、staged merge 或 activation 故障后，有效读结果与 active 状态不变，失败 stage 的科目表/四表行均为 0、dataset/job 为 failed 且 attempt `state=cleanup_done` 并保留 failure_code。只有 sealed 且合同、bundle、base ID+digest、row counts、post-hash 复验一致的 stage 可 activation-only 恢复；其他 retry 必须清旧 stage后创建新 stage。最终 staged merge、四表/客户科目可见性切换、active 状态、激活记录、outbox 与 attempt activated 在同一短事务内全成或全败；dataset rollback 后四表与客户科目都只显示恢复版本。AST 逐个删除四表 reader 的 active predicate、恢复裸 `is_deleted=false` 或放宽无 active fallback 均打红。
17. **AC-17**：按 `_AMOUNT_FIELDS_BY_TABLE` 导入万元夹具后余额八类字段和明细借贷字段恰乘 10000，数量与全部 `*_fc` 不变；yuan/qian 同理；两个 payload_style、两条 converter 真实输出、normalizer、dry-run 与 hash 对拍。空单元格/空白字符串在 converter 后均为 None、归一后仍为 None，hash 使用同一 null token；非空非法字符串以带 file/sheet/row/field 的 `LEDGER_AMOUNT_INVALID` 失败，NaN/+Infinity/-Infinity 均在写库前报 `LEDGER_AMOUNT_NOT_FINITE`。有限值归一固定为 `value*factor` 后 `ROUND_HALF_UP` 到 0.01，正负 0.005 分别得到 0.01/-0.01，Numeric(20,2) 的正负边界可写、越界 fail closed；二次归一、篡改合同或在非 sealed stage 上 activation-only 恢复均失败。
18. **AC-18**：共享 PG baseline 与 legacy dry-run 在任何业务 SELECT 前执行 `SET TRANSACTION READ ONLY`，`SHOW transaction_read_only` 为 on，全调用图无第二连接并 finally rollback；专用 PG 集成测试在该入口故障注入 UPDATE 必须得到 `ReadOnlySqlTransaction`，随后 scoped row count、金额 hash 和完整 source_summary hash 前后相同。真实 apply 与 rollback 使用与共享 dry-run 分离的显式写入口；分别缺少环境变量、`--apply`、双录 dataset ID 或版本/来源参数中的任一项都拒绝。apply history 保存变更前单位元数据的 presence-aware canonical snapshot+digest；rollback 先要求当前 hash 等于 apply after-hash，反向结果等于 before-hash，再精确恢复快照并追加 rollback history。恢复后原 legacy_declared/legacy_unknown 分类逐值相同且 incremental 再次返回 `BASE_DATASET_UNIT_UNVERIFIED`；四表、单位元数据和 history 任一步失败整单回滚。本轮不执行真实 apply/rollback。
19. **AC-19**：模板 sidecar 通过 `--check`，四版附注每个稳定 section/table/column ID 均有效，每个输出区域恰有一个 authority；失效 ID、冲突单位、错误标签或未知金额 kind 返回机器码和中文原因且不生成正式文件。自定义 workbook 首次 ingest 仅返回 artifact ID/SHA-256且不要求客户端预知 region；preflight 后返回稳定 sheet/region、kind、label 候选与 preflight digest，unit-authority PUT 以 artifact hash+digest CAS 覆盖恰好全部 amount region。只有 authority 已绑定的 ACTIVE publication 可经生产 instantiate 路由生成 WorkingPaper 与 authority 行；旧 `/api/custom-templates` 无法进入该链。缺 manifest、改一字节、漏 region、标签冲突或结构漂移均返回 `EXPORT_UNIT_POLICY_INVALID`/明确 409，结构漂移 UI 回到逐区域确认；两个底稿导出调用方与归档复制路径都不得产出文件。
20. **AC-20**：`EXPORT_SURFACE_REGISTRY` 与前后端实际文件 sink 双向闭合，每个生产出口恰有一个 `formal|data_exchange|template|non_amount` 分类；新增未分类 sink、重复分类、失效谓词或 formal 读取 displayPrefs 均打红。TrialBalance HTTP/summary/bulk、单张/整套报表、底稿 HTTP 与 WpExportEngine、`useAuditSheetTable` 正式数据导出、直接 PDF、组合包，以及附注 `export`、`export_with_meta` 两个生产调用方、template/programmatic、普通/clone 表、OnlyOffice 保存与 refresh rebuild 全部显式传 ExportUnitPolicy/region policy、column kinds、ratio scales 或按底版版本继承 policy pair。审计报告五个财务占位符有稳定 region ID+amount kind，`fill_placeholders` 无默认必传 policy，逐调用方删除参数均失败。合并试算/差额/附注本地导出解析后只含规范元值、机器可读 `source_storage_unit=yuan` 和可见“非正式出具”说明。所有有文件的正式附注版本不论 created_via 都保存可重算的 canonical policy snapshot+digest，DB pair CHECK 成立；generate→OnlyOffice save→refresh 全链保持底版 pair，编辑期间项目 policy 变化也不把旧字节标成新 policy。底稿非成员导出为 403；组合包任一来源/policy 失败时不生成 zip，包内无空文件和 placeholder。
21. **AC-21**：PDF create 只接受 project_id、year、非空去重 document_types 和可选 password；额外/缺失字段、空字符串密码、UTF-8 长度 128 bytes 密码均为 422，1 与 127 bytes（含中文边界）成功。用唯一可识别密码分别构造空/超长/错误类型/含额外字段请求，真实全局 `validation_exception_handler` 的响应 detail 不含任何 `input/context` 或该明文，应用日志、审计日志、ORM、task options 和 policy snapshot 同样搜不到；移除结构化 redactor 的变异必须打红。create、status、download、history 的未登录/跨项目访问分别为 401/403；产物含真实数据且 MIME/后缀均为 PDF，转换器缺失为中文 503，绝不返回 HTML。R 迁移对多文档、仅年度、仅 policy、任一正式 Word policy snapshot/digest、任一底稿内容版本单位证据、任一 import attempt 或 custom workbook authority、非默认项目单位或偏好行均 `RAISE EXCEPTION` 并保留全部数据；仅纯旧镜像或可先回填旧 `document_type` 的单元素任务允许回滚。
22. **AC-22**：个人屏幕单位 yuan/wan 两次导出时，项目与模板 authority 未变则五类正式产物的数值、标签和规范化内容不变；项目或模板 authority 改变时数值与标签按同一 divisor 改变。既有 Word 版本的 policy digest 缺失或与当前 policy 不同后，OnlyOffice 打开、单节/批量增量刷新和归档打包均返回 409 `EXPORT_POLICY_CHANGED_REQUIRES_FULL_REBUILD`（归档可使用对应 blocking code）、文件与版本数不变；整份重建后新版本值、标签、snapshot 和 digest 一致。归档只复制精确最新版本且重算文件 hash，manifest 逐项包含 version id/no、file hash、policy digest；普通金额底稿还必须以当前 Workpaper 内容版本的 artifact hash+policy pair（或已登记 data_exchange 的 source_storage_unit）匹配，缺证据历史文件阻断。项目单位改变后旧版本不可归档。legacy_unknown 需要非元缩放时 fail closed。
23. **AC-23**：唯一 AST 守卫 JSON 含完整键，并按每个生产 scope（固定 include/exclude 规则下 `src/` 的各顶层目录与根文件，口径见 design §15 A8）输出非零 eligible/parsed、该 scope 的 candidates 计数与逐项 skipped，全局 candidates 非零；`eligible = parsed + 已登记 parser exemptions`，任何其他 skipped 均失败。解析崩溃、空扫描、include root/核心文件被排除、核心符号 manifest 未命中、台账 schema/谓词/fingerprint 失效、核心违规、新增遗留或基线上调均以 `SCAN_SCOPE_DRIFT` 或对应机器码非零退出。后端四表/客户科目 read registry 与前后端 `EXPORT_SURFACE_REGISTRY` 都必须和实际 AST 读表/文件 sink 双向相等，任何裸四表读取、未分类出口或失效分类谓词失败。新增生产文件自动进入 eligible；旧 92/88 指标已退役，唯一真实基线不高于 88 且只减不增。
24. **AC-24**：相关 pytest/vitest/ESLint/格式守卫通过；vue-tsc 候选树相对同一 HEAD 无新增错误并以 TS2322 注入证明真运行；所有新守卫和关键安全/接线点均有逐项故障注入，PBT `max_examples=5`。所有 spec/INDEX 变更完成后由私有 index 生成 candidate commit/tree 并冻结；受测 worktree、自身解析的 `HEAD^{tree}`、验收清单和最终本地提交的 tree OID 必须逐值相同，任一受跟踪文件后改即使证据失效并重跑。
25. **AC-25**：Playwright 只能从锁定的分离头 candidate commit worktree 启动本任务独占前后端端口；后端启动钩子与 Vite config 必须各自在自身 cwd 解析 `HEAD^{tree}`，与只读 expected tree OID 不等时拒绝启动，并在启动日志、health header/body 与前端 build marker 同时暴露 expected/actual；仅回显环境注入值不算证据。工作树启动前后均须无受跟踪改动，禁止复用共享 3030/9980。幂等【测试】fixture manifest 通过平台 API/受控 seed 准备 standalone+consolidated 项目、两者企业树父子关系、A/B 两账号成员关系及 TrialBalance、ReportView、DisclosureEditor、HTML 底稿、合并页、LedgerPenetration 六处原值 10000；逐页验证四档 computedStyle、元→万元、页面切换、刷新/重登、另一账号隔离、固定列/密度和正式下载边界。`finally` 按记录对象 ID 走平台路径恢复/删除并核对 before/after 行数与 hash；缺账号、项目、LibreOffice 或独占服务时本项保持未完成，禁止随机现存数据、DOM 注入或共享服务替代。
26. **AC-26**：开发文档、核心页面/正式导出矩阵、现算遗留数量和后续批次与代码一致；未清遗留、未完成浏览器证据或未获放行的真实数据迁移保持未完成，不得标 completed。

## AC 与交付阶段对应

交付分为阶段 A（显示偏好与屏幕显示）、阶段 B（账套导入单位归一）、阶段 C（正式导出单位策略）和终验（任务 13），拆分说明见 design §14。本表只分配验收责任，不改变上列 AC 的文本和含义；跨阶段 AC 在各阶段只验收所列部分，终验在最终候选树上重跑全部 AC。

| AC | 阶段 | 各阶段承担的部分 |
|---|---|---|
| AC-01~AC-04 | A | 全部 |
| AC-05 | A | 全部（A 组 V/R） |
| AC-06~AC-10 | A | 全部 |
| AC-11 | A、C | A：跨层七类 kind、column_ids/kinds/ratio_scales、render schema 与 GtColumn 对拍、屏幕格式化及 ratio_scale 故障注入；C：四版附注普通与 clone Word 路径结果一致及 Word 夹具故障注入（任务 6C） |
| AC-12 | A | 全部 |
| AC-13 | A、B | A：删除 `gt_note_amount_unit`、三态 presenter、加载数据集不重置显示单位（normalized_v1 用 DTO 夹具）；B：新导入数据集由后端严格解析为 normalized_v1，两页显示存储元与因子 |
| AC-14~AC-18 | B | 全部；AC-15/AC-16 的 attempt 存储依赖 B 组 V/R；AC-18 的只读纪律同样约束 1A/1C 的 baseline 只读探针 |
| AC-19、AC-20、AC-22 | C | 全部；稳定 section/table/column ID 与 measure catalog 由阶段 A 任务 6A 提供，附注普通/clone 内核由任务 6C 承接 |
| AC-21 | C（A、B 承担各自 R） | A：R_A 对非默认项目单位与偏好行的阻断；B：R_B 对 import attempt 的阻断；C：PDF DTO、422 脱敏、对象鉴权、真实产物，以及 R_C 其余阻断与单元素回填 |
| AC-23 | A、B、C | A：前端 AST 守卫 scope/核心符号/legacy ledger、唯一基线 ≤88、CI 单一步骤；B：四表/客户科目 read registry 与账套入口注册表双向闭合；C：`EXPORT_SURFACE_REGISTRY` 双向闭合与正式导出核心符号 |
| AC-24 | A、B、C、终验 | 各阶段：本阶段 pytest/vitest/ESLint/格式守卫、vue-tsc 相对同一 HEAD 无新增（TS2322 注入）与本阶段全部故障注入，A 另交付候选 tree 身份工具；终验：最终 candidate tree 冻结，受测 tree 与最终提交 tree OID 逐值相同 |
| AC-25 | 终验 | 全部；各阶段冒烟复用候选 tree 身份工具，但不作为本 AC 证据 |
| AC-26 | A、B、C、终验 | A：屏幕文档、核心页面矩阵与遗留台账现算数量；B：导入文档；C：导出文档与正式导出矩阵；终验：三份文档与代码一致，未完成项如实保留 |

## Out of Scope

- 开放任意字体选择、字体主题、远程字体下载、购买或分发商业字体许可证。
- 重做正式附注/审计报告的版式字体，或把个人字号带入权威 Excel/Word/PDF 模板。
- 未经用户再次明确放行，对共享真实 PG 的既有四表金额执行批量换算；本轮只交付分类、dry-run、受控脚本和回滚证据设计。
- 在本轮清零约 700 个文件的全部历史金额展示遗留；本轮必须修核心/公共路径并建立可信单调台账，余项按后续批次收敛。
- i18n、暗色主题重构、默认会计准则/默认审计类型的账号化、与显示设置无关的页面重构、业务公式/会计口径调整。