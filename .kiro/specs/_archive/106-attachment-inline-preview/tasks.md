# 任务：底稿附件就地预览与易用性（attachment-inline-preview）

- [x] 1. 共用件：`attachmentPreviewTarget.ts`、`rowEvidence.ts`、`AttachmentEyeButton.vue`、`RowEvidenceEye.vue`；`AttachmentPreviewDrawer` 加 `downloadable` / `size`；`OcrStatusBadge` 认 `completed`；`evidencePositionLabel` 的 `row:` 位置文案；组件测试（需求 1、3.1，ADR-AIP-01/02/03/05）
- [x] 2. 已有预览处改用统一判型：右侧附件页签（加小眼睛）、函证附件抽屉；`ItemAttachment` 点名即预览 + 小眼睛 + 下载（需求 2.1、2.2，ADR-AIP-04）
- [x] 3. 记了附件编号的展示处加小眼睛（design §1.2）；G6 悬浮提示、证据分组「附件ID」列改文件名（需求 2.3、3.2、3.3）
- [x] 4. 只记文件名的：D2 终止确认向导（编号早已记，补小眼睛）、G7 减值测试（改行级位置 + 识别摘要读对字段，需求 3.4）
- [x] 5. 行内识别带位置 + `RowEvidenceEye`：D / E / F 循环（design §1.4），修 D1 质押检查缺底稿 id 的识别路径；F1 / F3 / F4 弹窗识别落到 ⑤ 同一位置；E1-10 / 11 / 18 表页级
- [x] 6. 行内识别带位置 + `RowEvidenceEye`：G 循环
- [x] 7. 行内识别带位置 + `RowEvidenceEye`：H / I / K / L 与其他（修 K1、K3 缺底稿 id 的识别路径；H3 四页改按行 id；L1 / L3 删行附件随行前移）
- [x] 8. 覆盖守卫与豁免清单（ADR-AIP-06，16 条豁免带 `verify`）；只读不可见的小眼睛判据；识别表单断言 `rowEvidence.spec.ts`（需求 4）
- [x] 9. 变异（design §4 七条 + 守卫四条 + 路由守卫三条，全部红在预期断言）与回归：相关 vitest 两条线各 1150 过 / 8 红（均为基线即红）、单区域 vue-tsc 新增 0、行数门（design §6.3）
- [x] 10. 浏览器走查（远端线候选树 + 独立无头浏览器 +【测试】项目，G8 / L1 / E1 / F1 + 右侧页签 + 只读 + 已删附件）；走查发现 E1 三个识别端点从未挂上并修复 + 路由挂载守卫；数据经平台路径清理并对账为 0（design §6.3）
- [x] 11. 文档收尾（design §6、INDEX、记忆），提交并推送
