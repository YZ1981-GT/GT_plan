# 需求文档：证据采集单一入口（attachment-evidence-intake）

来源：`.agents/tasks/attachment-linkage-assessment-2026-10-27.md` 第五节 Spec B 与第八节 11、12；用户 2026-10-27「按建议来」（拍板事项 1 按建议：行级证据关联用 `evidence_links`）。
范围：底稿内产生的证据文件一律进附件表并关联到底稿（整稿或行 / 单元格）；OCR 端点先建附件再识别；行级附件组件改造；底稿附件统一视图与侧栏口径统一；上传时选证据类型。函证底稿内挂件（C）、抽凭样本绑定与盘点照片（D）、归档与 QC（E）、合同台账（F）、治理链路与版本模型收敛（G）不在本 spec（design §1）。

## 实施前现查（2026-10-27）

| 项 | 现查结果 | 对需求的影响 |
|---|---|---|
| 底稿 OCR 端点 | 25 个文件 26 个路由写 `storage/workpapers/{wp}/…` 旁路目录；只有 E1 的 4 个先建附件（且仍另写一份旁路副本） | 需求 2 |
| OCR 复用口子 | 带 `attachment_id` 且不强制重识别时，`load_reusable_ocr` 不校项目、不校关联，直接返回该附件识别全文 ⇒ 能读任意项目附件的识别文本 | 需求 2.2 |
| OCR 上传体量 | 26 个路由无大小上限（上传端点限 50MB） | 需求 2.5 |
| 前端 OCR 前置上传 | `buildLinkedOcrFormData` 9 处调用：先走旧上传 + associate，再把 id 交给 OCR | 需求 2 落地后改为只组表单 |
| 底稿内上传点 | 旧上传端点 31 处调用、25 个文件；其中底稿内 20 个文件 22 处（ItemAttachment、侧栏拖放、底稿附件抽屉、F2 / F3 / F4 行内上传 6 处、C 类 7 处、B2-12、序时账穿透导出、三个 el-upload 弹窗等） | 需求 5 |
| 关联权限 | associate / 解除关联只登记 lead / admin / supervisor（`test_task10_entry_gate.py::test_associate_assignee_denied` 钉住）；编制人上传后 associate 失败被吞，侧栏拖放会留下孤儿附件并报「上传失败」 | 需求 1.4：新证据上传按底稿内容写判定 |
| `ItemAttachment` | 49 个标签、40 个文件；按 `title` 过滤而后端不回 `title` ⇒ 列表恒空；删除只本地隐藏；每行一个 GET | 需求 5.1 |
| `evidence_links` 路由 | 唯一调用方是侧栏「证据」页签：手填附件 UUID；`created_by` 取请求体、缺省全零；底稿 / 附件 / 链接都不校属于路径项目；证据类型选项有 `statement` / `other` 不在附件类型登记表 | 需求 3 |
| 侧栏附件页签 | 走 process-record，只读 `reference_type='working_paper'`；每个附件再发一次关联底稿请求 | 需求 4.3 |
| `POST /api/process-record/link-attachment` | 只要登录即可把任意附件挂到任意底稿；前端零调用方 | 需求 4.4 删除 |
| el-upload 原生上传 | 三个弹窗按 `response.id` 取 id，响应被信封包装 ⇒ 附件 id 从未记进表单；也不关联底稿 | 需求 5.4 |
| Spec A 扩展名白名单 | 无音视频扩展名；访谈录音、监盘录像弹窗（`accept="audio/*"` / `video/*`）自 Spec A 起上传恒 422 | 需求 6.1 |
| Spec A 原生加载守卫 | 扫描器把 `<script` 之前当模板，script 在前的单文件组件模板整段漏扫；已知漏网 `GtB212Evaluation` 步骤附件 `<a :href="/api/attachments/{id}/preview">` | 需求 6.2 |
| 迁移号 | 远端 V209 / V211，本地 V210 / V212（V212 为并发会话未提交） | 实施时现取，暂定 V213 |

## 需求 1　证据入口（后端）

1.1 新端点 `POST /api/projects/{project_id}/workpapers/{wp_id}/evidence/upload`（multipart：`file`，可选 `evidence_type`、`sheet_name`、`cell_ref`、`page_ref`）：一次事务内建附件并关联底稿。不带位置 ⇒ 写整稿关联（`attachment_working_paper`，关联类型 = 证据类型）；带 `sheet_name` 或 `cell_ref` ⇒ 只写行级证据链接（`evidence_links`），不写整稿关联。返回 `{attachment, evidence_link}`。
1.2 证据类型登记表 `evidence / support / voucher / contract / bank_statement / stocktake / note / confirmation`；不在表内 ⇒ 422。未传 ⇒ 底稿编码的证据声明恰好一类时取该类，否则 `evidence`。附件类型与关联类型都写证据类型。
1.3 上传过 Spec A 的上传策略（类型、扩展名、恶意内容）；大于上传上限 ⇒ 413；底稿不属于路径项目或已删除 ⇒ 404；项目已归档 ⇒ 423。任一不过不落盘、不建行。
1.4 权限：路径项目 edit + 底稿统一门的内容写（编制人可用；复核人、只读历史身份不可）。把项目里已有附件整稿关联到底稿仍按原矩阵（仅 lead / admin / supervisor）。
1.5 入口上传的附件不进旧的同名自动建版本：新证据一律是新附件（版本 1、不发替换信号）。整稿上传 `reference_type='working_paper'`、行级上传 `reference_type='workpaper_item'`，`reference_id` 都写底稿。
1.6 失败不降级：建附件失败直接报错，不再返回临时 id。

## 需求 2　底稿 OCR 端点先建附件再识别

2.1 26 个底稿 OCR 路由不带 `attachment_id` 时，经需求 1 的同一入口建附件（整稿关联；带可选表单字段 `evidence_sheet` / `evidence_cell` 时改写行级链接），提交后再识别，结果写回该附件；响应里的 `attachment_id` 是真实附件 id。
2.2 带 `attachment_id` 时：该附件必须属于底稿所在项目且已关联到本底稿（整稿关联、`reference` 或本底稿的证据链接），否则 404，不返回任何识别文本；不强制重识别且已有文本 ⇒ 复用；重识别读附件已存原件，不再用请求里重传的文件。
2.3 不再写 `storage/workpapers` 旁路目录；`workpaper_side_storage` 的目录函数删除。
2.4 证据类型：表单可带 `evidence_type`；未带时，底稿编码属于端点本循环（如 `d4/contract-ocr` 用在 D4 底稿）取端点的类型，否则按需求 1.2 的缺省规则（`d4/contract-ocr` 被其他循环当通用识别口时不再一律记成合同）。
2.5 上传上限、归档、上传策略与需求 1.3 相同（413 / 423 / 422）。
2.6 原来不写回识别结果的 8 个路由（N2、D2 终止确认、E1 截止 / 大额、H1 房屋 / 车辆权证、H1 监盘小结、H3 不动产权证）同样写回附件。

## 需求 3　行级证据链接（`evidence_links`）

3.1 列表返回链接与附件元数据（文件名、大小、类型、识别状态、附件类型），排除已软删附件；可按 `sheet_name`、`cell_ref` 过滤。
3.2 创建链接：附件必须属于路径项目且已在本底稿（统一视图任一来源），否则 404；`created_by` 取当前用户，请求体里的值不再采用；证据类型按 1.2 校验。批量同此，任一不过整批不写。
3.3 删除链接：链接必须属于路径底稿，否则 404；只删链接，不删附件。
3.4 底稿属于路径项目；写操作判归档（423）。
3.5 迁移：`evidence_links` 补 ORM 已声明的两个外键（`NOT VALID`）与两个索引，加 `(wp_id, sheet_name, cell_ref)` 组合索引，`cell_ref` 放宽到 100；可重放，带回滚脚本。
3.6 位置约定：`sheet_name` = 表页键；`cell_ref` = A1 单元格，或 `item:{序号}`（行级组件的槽位），或 `row:{行 id}`（留给 C / D）。`attachment_working_paper.row_ref`（V021，无写入方）不再使用。
3.7 只有行级链接的附件，按其所在底稿做可见性隔离（`_linked_wp_ids` 纳入证据链接）；OCR 写回的「已关联」判定同样认证据链接。

## 需求 4　统一视图与侧栏

4.1 `GET /api/working-papers/{wp_id}/attachments` 增加来源 `evidence_link`，每项带 `evidence_positions`（链接 id、表页、单元格 / 槽位、页码、证据类型）；每项带 `linked_wp_count`（附件出现的底稿数 = 整稿关联 ∪ 行级证据链接 ∪ `reference` 指向的底稿，去重；函证挂载不计。实施时由「整稿关联的底稿数」修订，见 design §8）。证据声明的满足判定照旧按附件类型 / 关联类型。
4.2 解除整稿关联同时删除该附件在本底稿的证据链接（「解除与本底稿的关联」= 全部解除）。
4.3 侧栏附件页签改用统一视图；关联底稿列表悬停时再取（不再每个附件一个请求）。悬停取的清单与 4.1 同口径，只列当前用户看得到的底稿，端点按附件所属项目判 readonly（原先只要登录）。
4.4 删除 `POST /api/process-record/link-attachment` 及前端零调用方的包装函数与路径。
4.5 附件列表每项带 `linked_wp_count`；附件管理页「已关联底稿」按它统计。

## 需求 5　前端

5.1 `ItemAttachment`：上传走需求 1（位置 = `sheetKey` + `item:{itemIndex}`）；列表按位置显示；同一底稿的全部实例共用一次请求；删除 = 移除本行链接（确认文案说明文件保留在附件管理）；新增可选 `evidenceType`、`readonly`。
5.2 底稿附件抽屉上传前选证据类型，缺省预选第一类未满足的声明；「缺 XX 证据」旁有「上传此类证据」；行级证据显示位置；提示文案改为「行级证据请在对应行移除」。
5.3 侧栏「证据」页签：显示文件名与位置；从本底稿附件里选附件，不再手填 UUID；证据类型选项用 1.2 登记表。
5.4 底稿内其余上传点改走入口：侧栏拖放、F2 / F3 / F4 行内上传（带位置）、C 类 7 处（带位置，并把附件 id 交给随后的识别调用，不再重复建附件）、B2-12 步骤附件、序时账穿透导出、三个 el-upload 弹窗（改 `http-request`，按入口回执取 id）。
5.5 `buildLinkedOcrFormData` 不再前置上传，只组表单（有 id 才带 `attachment_id`）。
5.6 守卫：旧上传端点只许附件管理页与函证附件抽屉（Spec C）调用，新增调用点打红。

## 需求 6　Spec A 遗留修正

6.1 扩展名白名单与附件管理页 `ACCEPT_TYPES` 同步加常见音视频（mp3 / m4a / wav / aac / amr / mp4 / mov / avi / wmv / mkv / flv）。
6.2 原生加载守卫按 `<template>` 块取模板（不再假设模板在前）；扫出的新违规改走已鉴权的预览 / 下载；扫描器自检加「script 在前」的合成样例。

## 需求 7　验证

7.1 接口级测试：OCR 不带 `attachment_id` 仍建附件并关联、写回识别结果、无旁路文件；带他项目或未关联本底稿的 `attachment_id` ⇒ 404 且响应不含识别文本；入口上传整稿 / 行级各自只写对应关联；编制人可上传、复核人不可；证据链接的跨项目、伪造 `created_by`、跨底稿删除；统一视图的新来源与解除关联。
7.2 组件测试：`ItemAttachment` 用后端真实返回形状（无 `title`）验证「上传后列表可见」「移除走删除链接」「同一底稿多实例只发一次列表请求」。
7.3 变异：design §6 逐条，红在预期断言，恢复后 sha256 一致。
7.4 走查：私有前后端实例 + 【测试】项目，浏览器验证 OCR 建附件、行级上传与移除、抽屉选类型后声明满足、侧栏两个页签；数据走平台路径清理并对账。
