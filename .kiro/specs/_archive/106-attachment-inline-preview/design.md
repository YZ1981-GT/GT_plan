# 设计：底稿附件就地预览与易用性（attachment-inline-preview）

## 0. 决策

**ADR-AIP-01 一个小眼睛组件。** `components/attachment/AttachmentEyeButton.vue`：入参只要附件编号，文件名 / 类型 / 识别状态可选。点开时取附件信息（`GET /api/attachments/{id}`，已有项目门 + 底稿可见性门），识别文本超过预览长度时再取全文（`GET …/ocr-text`）；404 / 403 ⇒「附件不存在或无权查看」。预览容器第一次点开才挂载（`v-if`），之后复用；用已鉴权的预览抽屉（server 变体：PDF / 图片 blob 地址，Office 转 PDF）。

**ADR-AIP-02 判型单一来源。** `components/attachment/attachmentPreviewTarget.ts` 的 `toAttachmentPreview()` 统一构造 `AttachmentForPreview`：类型提示按扩展名给 MIME（PDF、图片），其余沿用 `file_type`；识别状态 `completed` 归一为 `ok`。右侧附件页签、函证附件抽屉、小眼睛都改用它；`OcrStatusBadge` 另认 `completed`（防御，旧调用方传原值也显示中文）。

**ADR-AIP-03 行内附件 = 行级证据链接。** 行内识别请求带 `evidence_sheet`（本页表页键）与 `evidence_cell`（`row:{行 id}`，分区表 `row:{区}-{行 id}`；没有稳定行 id 的页面用 `row:{序号}`，删行时 `shiftIndexedRowEvidence` 让附件随行前移、被删行的附件转表页级；整页一个的识别按钮只带表页 = 表页级。实施勘误：原写「`item:{序号}` 与 ItemAttachment 同口径」，见 §6.1），后端照 Spec B 只写行级证据链接；成功后让本底稿共享链接仓失效。`RowEvidenceEye` 按位置读共享链接仓：0 份不显示，1 份显示小眼睛，多份显示「👁 n」点开列表。行数据结构不变（行数据同步到在线编辑与导出，新增字段有契约风险）。28 个识别端点中 26 个已接 Spec B 入口；`/api/d4/contract-ocr`（缺底稿 id，后端无此路由，3 处）在本 spec 改为带底稿 id 的路径。

**ADR-AIP-04 `ItemAttachment` 点名即预览。** 文件名点开预览；行尾小眼睛、下载、移除三个按钮。

**ADR-AIP-05 预览抽屉可选下载与宽度。** `AttachmentPreviewDrawer` 加 `downloadable`（底部「下载」按钮）与 `size`（缺省 480px 不变）；小眼睛传 `downloadable` 与较宽尺寸。旧调用方不传，DOM 不变。

**ADR-AIP-06 覆盖守卫。** `src/__tests__/AttachmentEyeCoverageGuard.spec.ts` 扫描 `components/workpaper/**` 与 `composables/**`：模板展示附件（📎 链接、`downloadAttachment(` 调用、附件名字段）或调用识别端点的文件，必须带 `AttachmentEyeButton` / `RowEvidenceEye` / `ItemAttachment`（composable 由其宿主组件带）；豁免清单 `attachmentEyeExemptions.json` 每条写原因与归属，只许删，且断言条目文件存在、确实未接。

## 1. 现状盘点（2026-10-27，探针 `tmp_attachment_spec_b/probes/inventory.py`）

前端调用识别端点的文件 106 个（111 处），其中 `d4/contract-ocr` 68 处；展示附件但只能下载 / 只显示文件名的组件 18 个。

### 1.1 已有预览（改用统一判型）

| 文件 | 现状 | 改法 |
|---|---|---|
| `AttachmentTabPanel.vue` | 整行点击预览；类型提示传 `file_type`（分类词）⇒ 图片判不出 | `toAttachmentPreview`；每项加小眼睛 |
| `ConfirmationAttachmentDrawer.vue` | 私有 `typeHintOf` | 改用 `toAttachmentPreview` |
| `WorkpaperAttachmentsDrawer.vue`、`AttachmentManagement.vue` | 弹窗预览（client 变体认分类词，判型正确） | 不动 |

### 1.2 记了附件编号的展示处（加 `AttachmentEyeButton`）

C22 控制表（证据区列表、样本行 📎）· C23 样本 · C24 异常事项 · C 类控制测试样本 · C25 内审 · C26 信息系统 · B2-12 步骤附件 · D4-12 合同卡片（`D4TabContract` 记 `attachmentId`）· D1 备忘卡片（`D1TabMemoReconciliation` 记 `attachmentId`）· G6 凭证检查（`useG6EclVoucherCheck` 记 `attachmentId`，悬浮提示改文件名）· H1 盘点汇总识别弹窗 · E1 四个识别确认弹窗（账户清单 / 承诺 / 征信 / 关键人员流水，状态里有 `ocrAttachmentId`）· C 类识别附件选择器 · 证据链接列表 · 证据分组展开（「附件ID」列改文件名）· 识别字段抽屉 · 血缘图附件节点。

### 1.3 只记文件名（补记编号）

D2 终止确认向导（`useD2Derecognition`，回执有 `attachment_id` 未记）· G7 减值测试估值依据（回执字段读错，见需求 3.4）。实施勘误：D2 的组合式函数早已记了 `attachmentId`，只缺小眼睛；G7 改为行级位置（`G7-17` · `row:{行 id}`）而不是记编号。

### 1.4 行内识别（带位置 + `RowEvidenceEye`）

| 循环 | 文件 |
|---|---|
| D | D3 凭证检查弹窗；D4 检查页 9 个（完整性、截止前后、贴现、出口、退货、其他检查、其他合同、关联定价）；D1 质押检查（composable，修 URL）；D2 凭证 OCR 核对（composable） |
| E | 截止测试 |
| F | F1 综合检查、F1 / F3 / F4 凭证检查弹窗、F3 利息测算、F5 数量核对；F2 五个识别 composable（采购、分包、专项合同、监盘、跌价） |
| G | G1 衍生工具 / 证券盘点 / 凭证检查、G2、G4、G7 子公司凭证、G8 ~ G12 |
| H / I | H1 增加 / 处置 / 监盘计划 / 盘点 composable、H2 增加、H3 公允价值 / 增加 / 关联方 / 权属 / 租金、H4 增加、H6、I1 增加 |
| K / L | K1 凭证（composable，修 URL）、K3 关联方（修 URL）、K5 诉讼、K8 合同 / 销售费用、K9 管理费用 / 合同、K12 明细 / 营业外、K13 营业外、L1 / L3 合同 |
| 其他 | B1 风险评估、C1 实体层面控制、C 类控制测试、I2 增强辅助、J1 凭证（composable） |

表页键用本页编码（如 `G8-6`），与页面标题一致；行 id 取各页行对象已有的稳定 id 字段。

### 1.5 豁免（守卫清单）

| 文件 | 原因 / 归属 |
|---|---|
| `d1/D1TabVoucherCheck.vue`、`d4/inspection/D4TabVoucherCheck.vue`、`composables/useD3VoucherCheck.ts`、`e1/E1TabBankFlowReconcile.vue`、`e1/E1TabLargeCheck.vue` | 并发会话（凭证身份 / 抽凭回填）正在改；合入后另行接入 |
| 函证替代程序 H05 / K05 / K06 / L05 / G06 | Spec C（替代程序改走入口、按单据类型识别）一并接入 |
| `composables/useOcrGovernance.ts` | 证据治理链路，非底稿页 |

## 2. 组件接口

```ts
// attachmentPreviewTarget.ts
export function previewTypeHint(fileName: string, fileType?: string | null): string
export function normalizeOcrStatus(s?: string | null): AttachmentForPreview['ocr_status']
export function toAttachmentPreview(a: { id: string; file_name?: string | null; file_type?: string | null;
  ocr_status?: string | null; ocr_text?: string | null }): AttachmentForPreview

// rowEvidence.ts
export function rowEvidenceCell(rowKey: string | number): string          // `row:${rowKey}`
export function appendRowEvidence(form: FormData, sheetKey: string, cellRef: string): void
export function refreshRowEvidence(projectId: string, wpId: string): void  // 失效共享链接仓
```

`AttachmentEyeButton` props：`attachmentId`、`fileName?`、`fileType?`、`ocrStatus?`、`label?`（读屏名里的文件名缺省取 fileName）。
`RowEvidenceEye` props：`projectId?`（缺省取路由参数）、`wpId`、`sheetKey`、`cellRef`。

`evidencePositionLabel` 对 `row:` 位置：纯数字显示「第 n 行」，否则显示「行内证据」（不把行 id 显示给用户）。

## 3. 测试

- `attachmentPreviewTarget.spec.ts`：判型（pdf / png / jpg / docx / 无扩展名）、状态归一。
- `AttachmentEyeButton.spec.ts`：点开取详情、截断时取全文、404 中文提示、只读可用、未点开不挂抽屉。
- `RowEvidenceEye.spec.ts`：0 / 1 / 多份；mock 用 `GET …/evidence` 真实形状。
- `ItemAttachment.spec.ts`：文件名点开预览、小眼睛、下载。
- 抽样页面（G8、H3 增加、K3）：识别表单带 `evidence_sheet` / `evidence_cell`，成功后链接仓重取。
- 覆盖守卫（ADR-AIP-06）+ 自检样例（违规样例必须被抓到）。

## 4. 变异（逐条，红在预期断言）

1. `previewTypeHint` 图片不给 MIME ⇒ 判型用例红。2. 小眼睛不取详情直接用空文件名 ⇒ 用例红。3. 404 不提示 ⇒ 用例红。4. `RowEvidenceEye` 不按 cell 过滤 ⇒ 计数用例红。5. 某抽样页面删掉 `appendRowEvidence` ⇒ 表单断言红。6. 守卫删除一个页面的小眼睛 ⇒ 覆盖守卫红。7. 豁免清单加一条已接入的文件 ⇒ 失效条目断言红。

## 5. 走查

远端线候选树私有前后端（同 Spec B）+【测试】项目：行级附件预览 PDF / 图片 / Word；右侧页签图片预览；行内识别后小眼睛与份数（G8 / H3）；只读可预览；已删除附件提示；数据走平台路径清理对账。结果见 §6.3（实际走查 G8 / L1 / E1 / F1，H3 由单测与守卫覆盖）。

## 6. 实施记录（2026-10-27）

规模：行内小眼睛 `RowEvidenceEye` 82 个文件 102 处，`AttachmentEyeButton` 21 个文件 24 处；识别请求带位置 78 个文件；守卫扫描面 识别站点 98 / 展示站点 21（近似复算）。

### 6.1 偏离与勘误

1. **没有行 id 的表用 `row:{序号}`，不是 `item:{序号}`**（ADR-AIP-03 原文）：`item:` 是 `ItemAttachment` 的上传位，与识别附件混在一起会互相显示。删行时 `shiftIndexedRowEvidence` 逐条「先建新位置再删旧位置」，被删行的附件转表页级（仍在本底稿附件里），失败条数 > 0 时提示去右侧附件页签核对（L1-6、L3-6）。
2. **H3-5 / H3-8 / H3-13 / H3-14 改按行 id**：这几页行对象本来就有稳定 `rowId`，原设计按序号会在删行后错位。
3. **F1 / F3 / F4 逐笔凭证一个位置**：F1 表格 📎、逐笔核对弹窗里各单据的识别、弹窗「⑤ 本笔附件」三处统一为 `F1-7-{debit|credit|postPeriod}` · `item:{f1VoucherAttSlot(行 id)}`（新文件 `f1/f1VoucherEvidence.ts`，散列槽位与弹窗 ⑤ 既有口径一致、单测钉值）；F3 / F4 弹窗识别落到 ⑤ 的 `F3-7-{区}` / `F4-8-{区}` + `item:{attSlot}`，表格「单据核对」旁加小眼睛。原先弹窗里识别的单据只挂整稿，⑤ 和表格行里都看不到。
4. **E1-10 / 11 / 18 表页级**：整页一个识别按钮，附件挂表页（不带单元格），按钮旁表页小眼睛 + 确认框里的小眼睛；E1-32 在「最近 OCR」标签旁。
5. **只读可见**：小眼睛不放在只编辑态的位置。原先 H1 七列、H3-12、K9 两处、K1-9 两处、F2 六处、H1-10 表、G1-14 合同识别行的整列 / 整块是 `v-if="!isReadonly"`（复核人看不到），改为列常显、只把上传入口收进编辑态。
6. **`RowEvidenceEye` 外层恒为 span**：多份时的按钮若直接挨着宿主按钮，会吃到 `.el-button + .el-button` 的 12px 间距；份数紧贴图标（走查量得多份时由 35px 外加 12px 间距收到 31px，单份 24px）。
7. **守卫比设计多两条判据**：识别请求须带位置或读回附件编号（`KEEP_RE`）；「藏起来」按任意祖先元素的 `v-if` 判（`v-else` 分支不计），同一位置在只读分支另有小眼睛则放行。

### 6.2 顺带修的缺陷（走查 / 实施中发现）

| 缺陷 | 修法 |
|---|---|
| **E1-10 账户清单 / E1-11 账户承诺书 / E1-18 征信报告识别端点从未挂到应用上**（2026-07 建好后漏登记 `router_registry`，前端恒 404，三个按钮恒报「识别失败」） | 登记进 `router_registry/workpaper.py`（与同组识别端点一起挂 `dedicated_wp_gate`）；守卫 `backend/tests/test_router_modules_mounted.py`：路由模块的每条路由须有应用路由在服务（端点身份 / 同路径），既有 23 条无人服务的导入导出路由冻结（只许删），E1 三条须由本模块端点服务，合成孤儿模块自检 |
| E1-10 / 11 / 18 第二次上传带上次的附件编号 ⇒ 后端按编号复用上次识别结果，新文件被忽略 | 每次都是新选的文件，不再带编号 |
| K3 / K5 / K8 / K12 / K13 / B1 / C 类控制测试读错识别正文字段（`text` / `full_text`，回执是 `ocr_text`） | 改读 `ocr_text` |
| D1 质押检查、K1 凭证、K3 关联方识别地址缺底稿 id（`/api/d4/contract-ocr`，后端无此路由 ⇒ 恒 404） | 改为 `/api/workpapers/{wpId}/d4/contract-ocr` |
| G7 减值测试识别摘要读不存在的 `businessContent` / `summary` / `amount` ⇒ 恒「未识别到结构化字段」 | 读 `extracted_fields`（服务内容 / 对方 / 金额）与识别全文前 120 字 |
| 右侧附件页签把分类词 `image` 当类型提示 ⇒ 图片「暂不支持在线预览」；识别状态 `completed` 显示英文 | `toAttachmentPreview` 按扩展名给 MIME；状态归一为中文徽标 |
| G6 凭证检查 📎 悬浮提示与识别回显显示附件编号；证据分组「附件ID」列只显示编号前 8 位 | 显示文件名，附件列改「原件」+ 小眼睛 |
| `k3Integration.spec.ts` 两条断言写死 `k3QueryCodes()` 无参形态（接注入后 HEAD 即红） | 改为 `k3QueryCodes(` |

### 6.3 验证

- **前端用例**：相关 81 个文件 1158 例，本地线候选树与远端线候选树各跑一次，均 1150 过 / 8 红；8 红在两条线的干净基线上逐条复现（C22 集成 5、D4-34/36 导入导出字面量 2、抽样方法学 allowlist 1），与本 spec 无关；`k3Integration` 两条由本 spec 修绿。
- **单区域 vue-tsc**：144 个文件，两条线「候选树 vs 基线」新增报错签名均为 0（唯一差异是同一条 TS2367 的联合类型打印顺序不同）。
- **行数门**：`GtC1EntityControl.vue`（HEAD 即 3154 未登记）登记 3167；`GtCControlTest.vue`（HEAD 即 1904 > 基线 1778 +5%）基线改 1905，均写明拆分方向。
- **变异**（`tmp_attachment_spec_b/probes/mut_aip.py`、`mut_router_guard.py`，磁盘注入 + 逐字节复原）：§4 七条 + 「去掉藏起来判据」「H1 产权列恢复只编辑态」「豁免核对：声称未接线的宿主已接线」「扫描面塌缩」共 11 条全部红在预期断言；路由守卫三条（撤掉一条登记 / 冻结清单多登记已服务路由 / 扫描器只看路径）全部红在预期用例。
- **浏览器走查**（远端线候选树：后端 9988、前端 3038，独立无头浏览器，不占共享标签页；【测试】项目 + 2 行最小试算表，生成 G8 / H3 / L1 / E1 / F1 / K3 / D4）：

| 走查项 | 结果 |
|---|---|
| G8-6 行内识别后本行小眼睛 → 预览 | 图片原件（blob）、徽标「OCR ✓」、识别全文、底部「下载」；详情请求只在点开时发 |
| 同一行再识别一份 PDF | 「👁 2」、读屏名「本行附件 2 份，点开逐个预览」，列表逐个预览，PDF 原件（blob） |
| 右侧附件页签 | 两份都标「行级证据」，图片正常预览（原先判型错） |
| 只读（平台真实只读态：后台合并期间整张底稿只读） | 横幅出现、「+ 新增」与 OCR 按钮隐藏，小眼睛照常可见可预览 |
| 页面打开期间附件被删除 | 点小眼睛：详情 404 ⇒「附件不存在或无权查看」，不打开空白预览；刷新后只剩一份 |
| L1-6 删第 2 行 | 第 3 行的附件前移到 `row:2`，被删行的附件转表页级，界面逐行小眼睛与库里一致 |
| E1-10 连传两份 | 修登记前 404；修后两个新附件（编号不同）、确认框有小眼睛并可预览、表页小眼睛计数随之增加 |
| F1-7 行识别 + 逐笔核对弹窗 | 行内小眼睛；弹窗 ⑤ 列出同一份；点文件名即预览；⑤ 上传 Word ⇒ 转 PDF 预览（blob 头 `%PDF-`，43 KB；首次转换约 10 秒，期间显示「原件加载中…」） |

  走查数据经平台路径清理：解除 8 条证据链接 → 删 9 个附件 → 回收站永久删除 → 删项目（软删）→ 按 id 删 2 行试算表；对账附件 / 整稿关联 / 证据链接 / 版本 / 试算表行全部为 0。

### 6.4 范围外登记（未改）

1. **合同识别回执字段与页面映射对不上**：回执是 `contractNo` / `counterparty` / `contractAmount`…，L1-6 / L3-6 / H3-5 / H3-8 按 `contract_no` / `borrower` / `amount` 取 ⇒ 确认框列英文键名、「填入」什么也没填；凭证检查页借用合同识别端点 → Spec D。
2. **借合同识别端点的凭证附件证据类型记错**：缺省规则对非本循环底稿取底稿声明的唯一证据类型，F1 声明的是「函证」⇒ F1 逐笔凭证附件被记成函证 → Spec D 按单据类型显式传 `evidence_type`。
3. **L1-6 删行后末行键残留**（按 `L1-con-{n}-{field}` 平铺存储，重载后出现幻影行；L3 已按 JSON 数组改过）→ L 循环收口。
4. **L1 页面打开时 `checklist-responses` 被同地址请求去重取消**，弹「L1数据加载失败，可手动填写」（远端线基线同样出现）→ `createChecklistFormData` 应忽略取消。
5. **23 条导入导出路由无人服务**（H5 / H9 / L7 / L8 / N4 全部，H7 / L1 / L3 / L5 的导出两条；L5、N4 前端调用的方法 / 路径也与后端不一致）→ 已冻结在路由守卫里，归各循环导入导出收口。
6. **窄列里小眼睛换到按钮下一行**（如 G8-6 📎 列「OCR」按钮 41px + 小眼睛 24px > 格内 51px），行高略增，功能不受影响。
7. 豁免 16 条见 `attachmentEyeExemptions.json`（并发会话 6、Spec C 5、非底稿页 1、无界面 1、设计如此 1、零挂载 2），每条带可核对的 `verify`。
