# Spec F — attachment-contract-identity-and-domain-closure 任务清单

## F1 — 死表删除
- [x] 1. grep 确认 Contract/ContractExtracted/ContractWpLink 零调用方
- [x] 2. V231 迁移：DROP TABLE + DROP TYPE
- [x] 3. 删除 ai_models.py 中 ORM 模型与枚举
- [x] 4. 删除 contract_analysis_service.py
- [x] 5. 删除 test_contract_analysis.py / test_contract_analysis_service.py
- [x] 6. 清理 service_lines_baseline / service-dependency 引用

## F2 — 证据链接合同身份
- [x] 7. V232 迁移：ALTER TABLE + 部分索引 + 位置唯一索引
- [x] 8. ORM EvidenceLink.contract_key: Mapped[str | None]
- [x] 9. contract_evidence.py: normalize / reuse / query
- [x] 10. workpaper_evidence_intake.py: contract_key 参数透传

## F3 — 合同复用端点
- [x] 11. POST .../evidence/contract-reuse
- [x] 12. upload 端点 contract_key Form 参数
- [x] 13. test_contract_evidence.py + test_contract_evidence_router.py

## F4 — 单据类型路由
- [x] 14. contract-ocr 按 document_type 返回字段映射

## F5 — 领域边界全修
- [x] 15. domain-boundaries.json may_depend_on 扩展（16 域）
- [x] 16. 未归属文件归入所属域
- [x] 17. --write-baseline 重生成（724 → 134）
- [x] 18. checker exit 0 + 18 self-tests pass

## F6 — 治理收口
- [x] 19. data_lifecycle restore/purge 改 require_role(['admin'])
- [x] 20. test_data_lifecycle_admin_gate.py: 8 tests（含变异证明）
- [x] 21. WorkpaperEditor.vue `:readonly` 增加 `|| !canEdit`
- [x] 22. WorkpaperEditorReadonly.spec.ts: 6 tests（含变异证明）

## 文档
- [x] 23. spec 三件套 requirements.md / design.md / tasks.md
- [x] 24. INDEX.md 更新
- [x] 25. 评估报告第十三节更新
