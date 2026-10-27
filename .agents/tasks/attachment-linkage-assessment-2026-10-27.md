# 附件模块联动现状评估与改进建议（2026-10-27）

评估对象：附件模块本身，以及它与函证底稿、抽凭（凭证检查）底稿、合同检查类底稿、A 类与归档、OCR / 证据声明 / QC / AI / PBC / 年度结转等的联动。
方法：读代码、真实库只读查询、导出后端路由清单、扫描前端调用；路径穿越一项在沙箱里直接调用生产函数复现。没有跑浏览器。

---

## 一、结论

1. **真实库里附件相关业务表全是 0 行**：`attachments`、`attachment_working_paper`、`confirmations`、`confirmation_attachment_link`、`sampled_vouchers`、`evidence_links`、`archive_manifests` 等均为 0；同库 `tb_ledger` 有 960 万行，1738 张在用底稿全部是草稿未提交。附件与各底稿的联动目前只被单元测试覆盖，没有真实数据跑过。
2. **用户实际走的是旧上传链路**：前端 20 余个文件、约 30 处调用 `POST /api/projects/{pid}/attachments/upload`；证据治理侧的安全上传 / 读取 / 版本端点（`/years/{year}/evidence/attachments`）前端 0 处调用，该 spec 的最终发布门（Wave 10 · 11.4）仍未通过。旧链路没有服务端文件类型与恶意内容检查，不记上传人和审计年度，不查法定保全。
3. **底稿里「上传并识别」的主流做法不进附件表**：前端 106 处底稿 OCR 调用只有 6 处带 `attachment_id`；后端 26 个底稿 OCR 端点里只有 E1 的 4 个会自动建附件，其余把文件写到 `storage/workpapers/{wp_id}/…` 旁路目录。底稿附件面板、证据声明、QC、归档包都看不到这些文件。`/d4/contract-ocr`（按销售合同 20 个字段抽取）被 68 处调用当作通用识别口，包括函证替代程序和 C 类控制测试。
4. **「附件挂在哪」有 10 种以上互不相通的记法**（见 2.3）。行级最常用的 `ItemAttachment` 被 40 个文件直接引用（其中 6 个是 D1 / F1~F5 的表页附件包装组件，它们又被约 39 个页签引用）；它按 `title` 过滤列表，而后端从不返回 `title`，所以上传后列表恒为空，删除也只是本地隐藏。
5. **四个联动点**：函证的数据双向同步已通，但发函件 / 回函件只能在函证中心挂，底稿内跟函、对象核实、差异调节、可靠性等子模块 0 附件能力，回函 OCR 比对在默认配置下恒返回空；抽凭的数据链路完整，证据链缺失（34 个凭证检查页 0 处走统一上传）；合同检查行里存的是 OCR 临时 id，原件打不开；A 类 51 个前端文件只有 1 个能上传附件，归档打包与云端推送都不含附件目录。
6. **4 个应先修的安全 / 数据问题**（第四节）：上传路径穿越（已复现）、函证附件跨项目越权、确认 OCR 会把全文覆盖成 200 字预览、法定保全与归档锁对附件删除不生效。

---

## 二、现状全景

### 2.1 数据现状（真实库 `audit_platform`，只读查询）

| 表 | 行数 | 说明 |
|---|---|---|
| attachments / attachment_working_paper / attachment_versions / attachment_lineage | 0 / 0 / 0 / 0 | 自上次统计重置以来 attachments 有 11 次插入、0 次删除、0 行存活，推测是回滚事务里的测试写入 |
| confirmations / confirmation_attachment_link | 0 / 0 | 函证中心台账与挂载 |
| confirmation_lists / results / attachments / letters / summaries | 全 0 | 第二套函证模型，见 3.1-7 |
| contracts / contract_extracted / contract_wp_link | 全 0 | 合同分析模块，见 3.3-4 |
| sampled_vouchers / sampling_records / workpaper_extraction_log | 全 0 | 抽凭 |
| evidence_refs / evidence_links / ocr_jobs / ocr_results / legal_holds 等治理表 | 全 0 | |
| archive_jobs / archive_manifests / pbc_checklist | 全 0 | |
| tb_ledger | 9,608,941 | 对照：账务数据是真实的 |
| working_paper（在用项目） | 1738，全部 draft / not_submitted | |

本地磁盘 `backend/storage/` 下没有 `attachments/`、`workpapers/` 子目录，与库里 0 行一致。

### 2.2 两条上传链路

| | 旧链路（在用） | 治理链路（建成未发布） |
|---|---|---|
| 端点 | `POST /api/projects/{pid}/attachments/upload` | `POST /api/projects/{pid}/years/{year}/evidence/attachments` |
| 前端调用 | 20 余个文件、约 30 处 | 0 |
| 文件类型 / 恶意内容 / 可读性门 | 无（只限 50MB） | 有（`resolve_attachment_security_gates`） |
| 隔离区 / 上传尝试记录 | 无 | 有 |
| 上传人 created_by、audit_year | 都不写 | 写 |
| 版本 | `attachments` 行式 version（按文件名归链） | `attachment_versions` 不可变版本 |
| 法定保全 | 不查 | 替换版本时查 |

### 2.3 「附件挂在哪」的记法清单

| # | 记法 | 粒度 | 写入方 | 读取方 | 问题 |
|---|---|---|---|---|---|
| 1 | `attachment_working_paper` | 附件↔底稿 | associate、process-record、E1 OCR | 统一反查、QC-17、可见性门 | 权威表，有唯一索引 |
| 2 | `attachments.reference_type/reference_id` | 1:1 | 上传表单、associate 双写、函证挂载 | 侧栏附件页签、版本归链 | 后写覆盖先写；值有 `working_paper` / `workpaper` / `workpaper_item` / `confirmation_list` 四种写法，统一反查只认第一种 |
| 3 | `confirmation_attachment_link` | 附件↔函证（发函/回函、配对） | 函证中心抽屉 | 函证中心、统一反查 | 只在函证中心可用 |
| 4 | `evidence_links` | 底稿 sheet / 单元格 / 页码 / 证据类型 / 检查结论 | 侧栏「证据链接」面板 | `wp_evidence` 路由 | 表达力最强，但不进统一反查、QC、证据声明；真库缺 ORM 声明的 2 个外键和 2 个索引 |
| 5 | `attachment_lineage` | 单元格 / 报表行 / 附注节 | `POST /api/attachments/{id}/link` | `LineageGraphPanel`（未挂载） | 无前端入口；`attachment_id` 无外键 |
| 6 | `attachment_working_paper.row_ref`（V021） | 行 | **无写入方** | 无 | 对应 PBT 用的是假对象（`test_wp_attachment_row_property.py`） |
| 7 | `ItemAttachment` 的 title 伪绑定 | 表页 / 行 | 40 个文件 | 同组件 | 后端不回 title，列表恒空；不关联底稿 |
| 8 | 行 JSON 里存文件名或 OCR 临时 id | 行 | D4-12、7 个凭证检查页等 | 前端自身 | 不是附件表 id，原件打不开 |
| 9 | 函证表单「附件 UUID 或 URL」文本框 | 行 | `GtDFormConfirmation` | 同 | 手填，无校验 |
| 10 | `notes = "sheet:{名}"` | 表页 | `AttachmentDropZoneOverlay`（未挂载） | 无 | 字符串约定 |
| 另 | `contracts.file_path`、`confirmation_attachments.file_path`、`ai_chat_attachments` | | | | 各自独立存文件，不经附件表 |

### 2.4 文件落点与归档覆盖

| 内容 | 落点（相对 backend/） | 进归档打包 / 云端推送 |
|---|---|---|
| 底稿文件 | `storage/projects/{pid}` | 是 |
| 统一附件 | `storage/attachments/{pid}/{attachment_type}/` | 否 |
| 底稿 OCR 旁路文件 | `storage/workpapers/{wp_id}/{子目录}/` | 否 |
| 交付件（报告、附注等） | `storage/deliverables/{pid}/{task}/` | 否 |
| AI 对话附件 | `storage/ai_chat/` | 否 |

### 2.5 OCR 的三套实现

| 实现 | 任务持久化 | 写回附件 | 使用方 |
|---|---|---|---|
| 26 个底稿专用 `*-ocr` 端点 | 同步请求 | 仅传入 attachment_id 时写回；E1 的 4 个自动建附件 | 各底稿页 |
| 通用 `POST /api/attachments/{id}/ocr-fields` | 进程内字典 + `asyncio.create_task`，重启即丢 | 写回 | 只有 `OcrFieldsDrawer`，该组件未挂载 |
| 治理 OCR jobs（`ocr_jobs` 表） | 持久 | 经人工确认写回 | 证据治理中心 |

知识库已有一套可靠的后台 OCR（SKIP LOCKED、租约、退避重试），附件没有复用。

---

## 三、分联动点的问题

### 3.1 函证（D0/E0/F0/G0/H0/K0/L0、函证中心、A12-1）

已经做好的：汇总表保存后经 `batch-sync` 同步到函证中心，回函结果经 Reply_Backflow 回拉，行上存 `_hub_confirmation_id`；函证中心抽屉支持发函件 / 回函件角色、强配对、只增不改的操作留痕；底稿附件抽屉能看到函证附件（source=confirmation）。

问题：

1. **附件入口只在函证中心**。`ConfirmationAttachmentDrawer` 只挂在 `ConfirmationHub.vue`。汇总表 `GtConfirmationSummary` 回拉的就是同一个 `/confirmations` 列表（已含 `outbound_count` / `inbound_count`），但不展示件数，也打不开抽屉。
2. **子模块 0 附件能力**。跟函 followup（10 个文件）、对象核实 entityVerify（14）、差异调节 diffReconcile（11）、差异清单 diffChecklist（9）、可靠性 reliability（11）、发函清单 e0-send-list（12）、协调 coordination（17）、舞弊风险 fraudRisk（10）、K0（10）、L0（8），附件 / 上传相关代码命中都是 0。快递单、跟函照片、工商截图、调节依据都在这些环节产生。
3. **替代程序证据不留档**。H05 / K05 / K06 的行级上传（共用 `alternativeD05/CheckBlock.vue` 的 📎 列）走 `/api/workpapers/{wp_id}/d4/contract-ocr`，不带 `attachment_id`，文件落旁路目录、附件表无记录；而且用销售合同字段去抽取回款单、证券对账单。L05（借款函证替代程序）调用的是缺 `wp_id` 的 `/api/workpapers/d4/contract-ocr`，后端没有这个路由，识别按钮不可用；即便调通，`Object.assign(row, ocrData)` 也会把整个响应体（含 ocr_text、confidence 等）并进行数据。
4. **回函 OCR 比对恒为空**。`extract-compare` 只读 `attachments.ocr_text`。默认配置 `PAPERLESS_URL=""`，上传后 `ocr_status` 停在 pending；能触发通用识别的 `OcrFieldsDrawer` 未挂载；附件管理页「重试 OCR」只把状态改回 pending；`POST /retry-ocr` 引用了不存在的 `TaskType.ocr_upload`，异常被吞。抽屉里点「OCR 识别」得到的是「OCR 文本为空」。
5. **抽屉预览打不开**。调用 `/api/projects/{pid}/attachments/{id}/download`，后端没有这个路由；用 `window.open` 打开，也带不上 Authorization 头。
6. **跨项目越权**。函证路由 17 个端点只校验登录或全局角色，路径里的 `project_id` 不参与判定；`link_attachment` 不校验附件与函证同项目；解绑不校验 link 属于路径里的函证。（属于已冻结的「仅登录不校项目」棘轮，基线 200，没有单独登记。）
7. **两套函证模型**。在用的是 `confirmations` + `confirmation_attachment_link`；`confirmation_lists / results / attachments / letters / summaries` 在后端没有任何服务或路由引用。挂载时又把附件的 `reference_type` 写成 `confirmation_list`，名字指向那套死表。函证类型只有 receivable / payable / bank / loan，A12-1 律师询证函和 G / H / K 类函证进不了中心。
8. **函证表单附件列是手填文本**（「附件 UUID 或 URL」）。
9. **证据声明粒度太粗**。D0 只要底稿下有任意一份函证附件就算满足，看不出 50 笔函证里哪几笔缺回函、哪几笔做了替代程序。

### 3.2 抽凭（凭证检查）

已经做好的：抽凭引擎接入 22 个凭证检查页，序时账挂凭接入 20 页；`sampled_vouchers` 按 (凭证日期, 凭证号) 定位、带批次号、能发现同一凭证被多次抽中；归档包有抽样章节，归档完整性检查读未撤销的抽凭批次。

问题：

1. **证据文件没有进附件表**。34 个凭证检查类页面里，走统一上传 0 处、调用 associate 0 处；16 处走底稿 OCR 端点（旁路存储）；7 处行里只记 `file.name`（例：G10 `updateRow(row.id, { businessContent, attachment: file.name })`）；3 处用失效的 `ItemAttachment`。凭证影像、发票、出库单、银行回单都没有留档。
2. **样本与证据没有关联**。`sampled_vouchers` 没有附件字段；同一张凭证被多张底稿抽到时，证据无法复用，也看不出谁已经取得了原始单据。
3. **证据声明永远缺**。D2 / D3 要求 `voucher` 类型证据，但没有任何界面能把附件类型或关联类型设成 voucher。
4. 归档抽样章节只列批次和统计量，不附样本证据清单。

### 3.3 合同检查（D4-12，F2 采购 / 分包，K8 / K9，L1 / L3，H3，G1 等）

1. **D4-12 存的是假附件 id**。行里的 `attachmentId` 是 `contract-ocr` 返回的临时 id，附件表没有这一行；合同卡片只显示文件名，没有预览和下载。
2. K8 / K9 / L1 / L3 / H3 / G1 / F2 的合同检查同样只调 OCR 端点，不留档。
3. **同一合同多处重复**。年度框架合同、借款合同会在收入、采购、借款底稿里分别上传、分别识别，没有去重或共享引用。
4. **合同分析模块是死代码**。`contracts` / `contract_extracted` / `contract_wp_link` + `ContractAnalysisService`，后端没有路由；前端 `apiPaths.contracts` 与 `ContractAnalysis` / `ContractAnalysisPanel` 组件存在但未挂载。它和 D4-12 的合同数据并存，容易混淆。
5. 证据声明 D4 / F2 / F4 / H3 要求 `contract` 类型，只有在附件管理页手工把关联类型改成「合同」才满足；底稿内上传一律记为 evidence。

### 3.4 A 类与归档

1. **签字件无处挂**。A 类 51 个前端文件（39 个 `GtA*` 组件）中只有 `GtA173ConsultationRecord` 有附件能力。A16 管理层声明书、A12-1 律师询证函、A10-1 治理层沟通、A17-7 独立性声明、A18-1 / A18-2 监管报送与沟通、A9-1 缺陷函、A17-6 总结会纪要都需要留存签字件或外部回函，目前不能在底稿内挂原件。
2. **A30 电子底稿归档检查表**是通用 checklist-table，不读取归档完整性检查结果，也不检查附件。
3. **归档包不含附件**。归档编排的 `wp_storage` 步骤 tar 的是 `backend/storage/projects/{pid}`，云端推送同一目录；附件、旁路 OCR 文件、交付件都不在里面（见 2.4）。底稿下载 ZIP（`wp_download_service`）与导出包（`export_package_service`）里附件相关代码也是 0 行。
4. **打包失败被当成功**。`WpStorageService.archive_project` 在目录不存在或 tar 出错时返回 `{"error": …}`，不抛异常；编排器不看返回值，照样把该步记为 succeeded。
5. **归档完整性检查不查证据**。现有 5 类检查是缺失、未签字、未关闭复核、过期、抽样记录；没有证据声明缺口、未回函函证、未确认 OCR、孤儿文件。
6. **法定保全不生效**。治理中心可以建保全，但 `RetentionLegalHoldService.authorize_destructive` 在生产代码里 0 处调用，只有测试在调；旧删除端点不查保全。手册里「上锁后连管理员都删不掉」目前不成立。
7. **归档只读可以绕过**。`DELETE /api/attachments/{id}` 的归档检查用的是查询参数里的 `project_id`；它和附件真实所属项目不一致时检查落空，真实项目只做成员 / 级别检查（`_ensure_project_access` 不判归档）。
8. **QC-17「底稿至少关联 1 个附件」（blocking）口径不对**。只数 `attachment_working_paper`，不认函证附件、reference、evidence_links；对所有底稿一刀切，A31 审计标识一览表这类不需要附件的底稿也会报阻断级问题。真库附件为 0，平台一旦开始提交复核，自检会普遍报红。

### 3.5 其他联动

- **证据声明**：13 条前缀里 voucher（D2 / D3）、stocktake（F2 / H1）、note（F3）三类在任何界面都设不出来；底稿附件抽屉上传恒为 evidence，所以「缺 XX 证据」在上传后仍然提示缺。
- **版本**：两套模型并存。旧模型按「同项目 + 同文件名 + 同 reference」判定新版本，reference 为空时同名的不同文件（扫描件默认名很常见）会被串成版本；新版本是新行新 id，底稿和函证关联仍挂在旧版本上；路由层的回滚是另写的一份，不走服务层的链锁和失效信号；版本弹窗未挂载，前端路径 `/versions/{versionId}/rollback` 也和后端 `/rollback` 不一致。
- **留痕**：上传端点不传 `created_by`、不写 `audit_year`，附件没有上传人；治理回填会跳过 audit_year 为空的附件，这批附件无法纳入证据引用、保全和归档清单；替换版本的失效信号因 actor 为空而不发。
- **事件**：只有一个 SSE 广播 `attachment.uploaded`；没有关联、解除、替换、删除的领域事件，证据完成度、QC、stale 不能随附件变化刷新。
- **两套底稿内附件界面口径不同**：`GtWpRenderer` 的「本底稿关联附件」抽屉用统一视图（链表 ∪ reference ∪ 函证）；`WorkpaperSidePanel` 的附件页签走 process-record，只读 reference 字段。附件关联第二张底稿后，第一张的侧栏里就看不到了；挂到函证后，会从侧栏消失。
- **OCR 确认不落库**：附件管理页按 `row.ocr_confirmed` 显示「待确认」，后端不返回该字段；确认后刷新仍显示待确认，也没有确认人和时间。
- **AI**：AI 对话附件是独立存储，不能引用项目附件；文档级 AI 不注入附件 OCR 文本。
- **PBC**：`receive_item` 只把状态改为 received，不关联收到的文件。
- **年度结转**：连续审计继承基础信息、映射、团队、试算、调整、未更正错报，不含永久性档案附件（章程、营业执照、长期合同、产权证）。
- **删除与回收站**：前端没有删除入口（`ItemAttachment` 的删除是本地隐藏，注释还写着「后端暂无通用 DELETE」）；后端 DELETE 不进回收站，不检查是否被底稿或函证引用。
- **列表筛选**：附件管理页 9 个类型筛选里，PPT / 文本 / 压缩包 / 邮件 / OFD-CAD 与后端 `file_type`（存扩展名，如 pptx / txt / zip / eml）对不上。
- **零挂载组件 9 个**：AttachmentVersionsDialog、AttachmentImpactDialog、AttachmentEvidenceForm（来源 / 取得日期 / 提供方 / 关键证据）、EvidenceConfirmDialog、LineageGraphPanel、OcrFieldsDrawer、AttachmentDropZoneOverlay、useEvidenceLink、useRowAttachment。V106 加的证据属性列没有界面可填，`metadata_status` 恒为 incomplete。
- **质控跳转**：质控工作台生成 `/projects/{pid}/attachments/{aid}` 链接，前端没有这个路由。

---

## 四、应先修的 4 个问题（P0）

1. **上传路径穿越**。`AttachmentService._write_local_file` 把表单里的 `attachment_type` 直接拼进目录。沙箱里调用该生产函数、传 `attachment_type="../../escaped"`，文件写到了存储根之外。有项目编辑权的用户可以在后端进程可写的任意目录新建文件。修法：`attachment_type` 改白名单枚举（与证据声明类型共用一份），落盘前 resolve 并校验仍在存储根内。
   同类：14 个 `*-contract-ocr` 端点在 `wp_id` 不是 UUID 时兜底成全零 UUID，继续写盘并调用 OCR 和大模型；路由级底稿门禁对非 UUID 直接放行。改为非 UUID 直接拒绝。
2. **函证附件跨项目越权**。函证 17 个端点改项目级鉴权；服务层校验「附件所属项目 = 函证所属项目 = 路径项目」；解绑校验 link 归属。同批处理：`/api/attachments/{id}/ocr-fields` 与附件血缘 `/link`、`/links` 对未绑定底稿的附件只校验登录，补项目成员校验。
3. **确认 OCR 会覆盖全文**。列表接口把 `ocr_text` 截成 200 字；确认弹窗用截断文本初始化，确认时整段 `PUT /ocr-status` 回写，完整识别文本被替换成预览。修法：确认只记录「谁、何时、改了什么」，全文编辑走单独接口并以完整文本为底；列表另给 `ocr_text_preview`。（静态链路确认，修复时浏览器复现。）
4. **删除绕过保全和归档锁**。所有破坏性路径（删除、回滚、同名替换）接入 `authorize_destructive`；归档检查改用附件真实 `project_id`；删除改为进回收站，并检查是否仍被底稿、函证或证据引用指向。

---

## 五、改进建议（按交付单元拆 spec）

**Spec A　附件安全底线（P0，后端为主）**
- 第四节 4 项；上传写 `created_by` 与 `audit_year`；服务端文件类型白名单复用治理侧媒体类型门。
- 验收：穿越、跨项目、全文覆盖、保全下删除四类，各写一条先红后绿的接口级测试，故障注入放在被测函数的下一层。

**Spec B　证据采集单一入口（P1，前后端，B 是 C / D / E 的前提）**
- 所有底稿 OCR 端点改为「先建附件、再识别、结果写回该附件」：后端统一调用 `provision_wp_linked_attachment`（E1 已有先例），前端 106 处调用不必逐个改；旁路目录停止写入。真库为 0 行，不需要存量迁移，只加守卫。
- `ItemAttachment` 改造：上传后写行级关联，列表按位置查询，删除改为解除关联；一处改动覆盖 40 个引用方。
- 侧栏附件页签改用统一视图；统一视图加 `evidence_links` 来源。
- 上传时可选证据类型，默认按该底稿的证据声明预选；「缺 XX 证据」旁直接提供「上传此类证据」。
- 守卫：OCR 调用不带 `attachment_id` 时仍能建附件的接口测试；ItemAttachment「上传后列表可见」的组件测试，mock 用后端真实返回形状（不带 title）。

**Spec C　函证证据闭环（P1）**
- 汇总表每行显示发函 / 回函件数（复用 `/confirmations` 已返回的计数），点击用 `_hub_confirmation_id` 打开函证附件抽屉。
- 跟函、对象核实、差异调节、替代程序接入 Spec B 的行级附件；替代程序按单据类型（回款单、发运单、证券对账单、发票）用各自字段抽取；修 L05 缺 `wp_id` 的识别路径和整包并入行数据的写法。
- 抽屉「OCR 识别」在 `ocr_text` 为空时先识别（走本机优先 OCR 路由）再比对；预览改走已鉴权的预览组件。
- 函证类型补 legal / other，A12-1 律师询证函接入中心。
- 证据声明改按函证逐笔统计：已发函、已回函、做了替代程序、缺证据清单。

**Spec D　抽凭证据绑定（P1，可与 C 并行）**
- 样本与证据关联：凭证检查行上传后绑定到对应 `sampled_vouchers` 行；同一凭证（日期 + 凭证号）的证据在多张底稿间复用并提示。
- 证据声明 voucher 类型可被满足；归档抽样章节附样本证据清单与缺证据样本。

**Spec E　归档与 A 类（P1，依赖 B）**
- 归档打包改为按库枚举：底稿文件 + 附件当前版本 + 交付件，生成清单与哈希（可复用治理侧归档清单与验签设计）；打包失败让该步失败。
- 归档完整性检查增加：证据声明缺口、未回函且无替代程序的函证、未确认 OCR、孤儿文件。
- A30 按完整性检查结果自动勾选；A16 / A12-1 / A10-1 / A17-7 / A18 等提供「上传签字版」入口。
- QC-17 改为按证据声明判定，没有声明的底稿不提示，口径与统一视图一致。

**Spec F　合同台账（P2，需拍板）**
- 建议复活 `contracts` 做项目合同库：一份合同 = 一个附件 + 结构化字段，D4-12、F2、K8 / K9、L1 / L3、H3 的合同行引用台账 id，只识别一次。不复活就删除死表和死组件。

**Spec G　长期收敛（P2）**
- 治理发布门通过后，旧上传 / 下载 / 版本端点改为治理链路的薄壳，两套版本模型收敛到 `attachment_versions`。
- 附件领域事件（关联、解除、替换、删除）进事件总线，驱动 stale、证据完成度和 QC 重算。
- 通用附件 OCR 改为持久任务，复用知识库 OCR worker。
- AI：文档级 AI 注入已确认的附件 OCR 文本；AI 面板可引用项目附件。
- PBC 收到资料即生成附件并关联；连续审计结转永久性档案附件（引用，不复制文件）。
- 清理零挂载组件（接上或删除）、对齐筛选项、OCR 确认状态落库、补质控跳转路由。

推进顺序：A → B → C 与 D 并行 → E → F → G。A 是安全底线；B 让证据真正进附件表，C / D / E 都依赖它；E 需要附件可被枚举；F 要先拍板；G 要等治理发布门。

---

## 六、需要拍板的事项

1. 行级证据关联用 `evidence_links`（建议，已有 sheet / 单元格 / 页码 / 证据类型）还是 `attachment_working_paper.row_ref`？另一套是否下线。
2. 合同台账：复活 `contracts` 三表，还是删掉死代码、各底稿自存？
3. 第二套函证模型（`confirmation_lists` 等 5 张表）是否删除。
4. 治理链路：先把旧链路补到安全底线继续用，还是推动 Wave 10 发布后直接切换。
5. QC-17 是否改为按证据声明判定。
6. 是否建一个【测试】项目的附件 UAT 数据集（真库为 0），作为后续每个 spec 的真实写入验收底座。

---

## 七、局限

- 没有跑浏览器。ItemAttachment 列表恒空、确认 OCR 覆盖全文、函证抽屉预览 404 属于静态链路确认，修复时需要浏览器复现。
- 真实库附件相关表为 0 行，无法评估存量数据问题（重复关联、孤儿文件、版本错串）。

## 附录：数字口径

| 数字 | 口径 |
|---|---|
| 106 处 OCR 调用 / 6 处带 attachment_id | 前端非测试 .vue / .ts 中匹配 `/workpapers/${…}/{段}/{名}-ocr` 的调用点；调用点前 1200 字符内有 `append('attachment_id'` 计为带 |
| 26 个底稿 OCR 端点 / E1 的 4 个自动建附件 | 后端函数体内含 `Path("storage/workpapers") / wp_id / …` 的路由函数；函数体含 `provision_wp_linked_attachment` 计为自动建附件 |
| 14 个端点非 UUID 兜底 | 路由文件中 `UUID(int=0)` 命中（排除 qc_rules.py） |
| 17 个函证端点 | `routers/confirmations.py` 全部路由函数的依赖：只有 get_current_user 或 require_role |
| 40 个文件引用 ItemAttachment、约 39 个页签 | 逐行扫描 import 语句；页签数 = D1(1)+F1(7)+F2 盘点(7)+F3(7)+F4(9)+F5(8) 包装组件的引用方 |
| 34 个凭证检查页 | 文件名含 voucher 的非测试 .vue |
| 函证子模块文件数 | `components/workpaper/confirmation/` 下按子目录分组，统计「attachment / 附件」与上传相关命中 |
| A 类 51 个文件 / 1 个有附件能力 | 文件名以 GtA 开头或位于 a* 目录；匹配 uploadAttachment / `/attachments` / associate / ItemAttachment / el-upload 等 |
| 前端调用旧上传约 30 处 | 匹配 `/attachments/upload`、`uploadAttachment(`、`P_att.upload(`，含 apiPaths 定义行 |
| 路由与鉴权 | 导入 `app.main.app` 后遍历 `app.routes`，递归展开依赖（含路由级 `dedicated_wp_gate`） |

---

## 八、勘误与实施中的新发现（2026-10-27，Spec A `attachment-security-baseline` 实施后）

**更正原文**

1. 3.5「后端 DELETE 不进回收站」不对：`DELETE /api/attachments/{id}` 本来就是软删、进回收站。原文其余判断成立：删除不查保全、不查引用，归档检查读查询参数里的 `project_id`。
2. 3.1-6 漏写了一处反向缺陷：函证路由里的 `_EDIT_ROLES` 不含审计员，挂载 / 解绑 / 识别比对 / 自动匹配 / 人工指派对审计员恒 403；`_ASSIGN_ROLES` 全仓零引用。
3. 4-4 范围比原文大：回收站的单条、批量、清空三条永久删除路径同样不查保全；永久删除对 admin 不判归档。
4. 3.5「版本」更正：前端回滚按钮请求的 `POST /api/attachments/{id}/versions/{version_id}/rollback` 从未注册，按钮恒 404；路由里的 `POST /api/attachments/{id}/rollback` 零调用方。
5. 4-3 的范围更大：批量上传结果弹窗是同一种截断（「确认此文件 / 全部确认入库」同样把 200 字预览写回）。

**Spec A 已修**：上述 1–5；第四节 4 项；14 个 `UUID(int=0)` 兜底与 26 个旁路目录写法（`services/workpaper_side_storage.py`）；`retry-ocr` 引用不存在的 `TaskType.ocr_upload`（改走 `OcrFieldsService`）；OCR 确认落库（V211 四列）；上传写 `created_by` / `audit_year`。

**实施中新发现、已在 Spec A 修**

6. 浏览器原生加载带不上令牌，全仓 18 处。平台只认 Authorization 头，iframe / img 的 src、a / el-link 的 href、`window.open` 都带不上：OCR 确认弹窗与批量结果弹窗的原件区显示 `{"code":401,"message":"Not authenticated"}`；底稿附件页签的预览抽屉（server 分支）同样 401；`ItemAttachment` 与 C24 / C25 / C26 / 控制测试的 📎 下载新标签页 401；函证附件抽屉「预览」打开一条不存在的路由（即 3.1-5）；模板库详情的预览与下载、合并透视导出、批量导出 ZIP、上年底稿文件 401；交付件预览的「下载」是 `<el-button :href>`，点了没反应。已改为 blob: 地址或 `downloadFile`，守卫 `NativeLoadBearerGuard.spec.ts` 冻结为零。原 Spec C 的「抽屉预览改走已鉴权组件」随此完成。
7. 加载全文后的布局回归：3607 字时 OCR 确认弹窗的文本框高 688px，盖住「确认入库」，按钮点不到。已封顶高度、内部滚动。

**实施中新发现、未修（按归属登记）**

8. 永久删除不删物理文件：走查中回收站永久删除后，两份文件仍留在存储目录（Spec G）。
9. 项目级联删除 `_cascade_delete_project` 绕过附件保全、引用与归档守卫（Spec G）。
10. 识别字段缓存 `ocr_fields_cache` 被 `_write_ocr_cache` 等写入方整体覆盖，后写的会抹掉先写的字段（Spec G：通用附件 OCR 改为持久任务时一并收口）。
11. 关联权限矩阵：底稿编制人（assignee）不能 associate 自己底稿的附件（Spec B）。
12. 附件管理页的「已关联底稿」统计 `linkedCount` 恒为 0（Spec B，统一视图接线时改）。
13. `GET /api/attachments/paperless-health` 被 `/api/attachments/{attachment_id}` 先匹配，恒 422（Spec G）。
14. H1 盘点汇总「照片」列是用户手填文本，被当成链接打开（Spec B / D：盘点证据入附件表）。
15. 归档向导的 `output_url` 后端没有写入方，「下载」按钮不会出现（Spec E：归档打包时接线，按是否 /api 选下载方式）。

**局限更正**：OCR 确认弹窗与附件管理页已在浏览器走查（私有前后端实例 + 【测试】项目，数据已清理对账）；`ItemAttachment` 列表恒空、函证子模块无附件能力等仍属静态确认，留给 Spec B / C 复现。
