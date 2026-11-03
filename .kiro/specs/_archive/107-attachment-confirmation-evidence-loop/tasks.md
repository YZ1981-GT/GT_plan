# 任务：函证证据闭环（attachment-confirmation-evidence-loop）

- [x] 1. 函证类型单一来源：后端枚举加 legal / other、`confirmation_types.py` + 三个请求体校验；前端 `confirmationTypeLabels.ts`、函证中心创建 / 导入 / 标签 / 筛选；接口与组件测试（需求 5.1，ADR-ACE-05）—— `test_confirmation_types.py`、`confirmationTypeLabels.spec.ts`；变异 M10
- [x] 2. 回函识别前置：`confirmation_reply_ocr.py`、`extract-compare` 先识别、失败如实报错；接口测试（需求 2.1、2.2，ADR-ACE-02）—— `test_reply_ocr_first.py`；变异 M1、M2
- [x] 3. 函证附件抽屉：`readonly`、按 `link_id` 解绑、真实字段、识别状态文案与「识别比对」；组件测试（需求 1.3、1.4、2.3）—— `confirmationEvidenceLoop.spec.ts`；变异 M8、M9、M24、M25
- [x] 4. 汇总表计数列 + 抽屉接线（`useHubAttachmentCounts`、`ConfirmationMaster`、`GtConfirmationSummary`）；组件测试（需求 1.1、1.2、1.5，ADR-ACE-01）—— 同上 + `syncHubFromSummary.transition.spec.ts`；变异 M16、M20~M23
- [x] 5. 替代程序单据识别端点 + 登记 + 入口守卫路由表；接口测试（需求 3.1、3.2，ADR-ACE-03）—— `test_alt_doc_ocr.py`、`test_ocr_intake.py`（路由表 27）；变异 M3
- [x] 6. 替代程序前端：映射表、识别弹窗、行内附件组件、`CheckBlock` 附件列，9 页接线（删 H0-5 / K0-5 / K0-6 / G0-6 私有识别、修 L0-5），删 5 条 `spec-c` 豁免；映射守卫与组件测试（需求 3，ADR-ACE-03）—— `alternativeDocMapping.spec.ts`、`AlternativeRowEvidence.spec.ts`、覆盖守卫；变异 M4、M5、M12、M29
- [x] 7. 跟函 / 对象核实 / 差异调节行级附件（`ItemAttachment.cellRef`、`DiffRowEvidenceCell`）；组件测试（需求 4，ADR-ACE-04）—— `confirmationRowAttachments.spec.ts`；变异 M11、M18
- [x] 8. A12-1 接入函证中心（`LegalConfirmationHubCard`、证据声明 `A12-1`）；组件测试（需求 5.2、5.3，ADR-ACE-06）—— `LegalConfirmationHubCard.spec.ts`、`test_a12_1_legal_letter`；变异 M19
- [x] 9. 证据声明逐笔判定（`confirmation_evidence_status.py`、`attachment_wp_view` 接线、附件抽屉显示）；接口与组件测试（需求 6，ADR-ACE-07）—— `test_confirmation_breakdown.py`、`WorkpaperAttachmentsDrawer.spec.ts`；变异 M6、M7、M13~M15、M17、M38、M39
- [x] 10. 变异（design §6）与回归：后端相关目录、前端相关 vitest 两条线、单区域 vue-tsc、行数门、覆盖守卫 —— 结果见 design §8.4（两条线失败均为 HEAD 子集，vue-tsc 0 / 0 带变异证明）
- [x] 11. 浏览器走查（远端线候选树 + 独立无头浏览器 +【测试】项目），数据经平台路径清理对账 —— design §8.4；走查新发现（回函三态、时间解析、输入框、会话接力、编辑锁只读）已修并各带测试与变异（M21~M37），见 requirements「走查新发现」与 design §8.1
- [x] 12. 文档收尾（design 实施记录、INDEX、记忆、评估报告勘误），提交并推送
