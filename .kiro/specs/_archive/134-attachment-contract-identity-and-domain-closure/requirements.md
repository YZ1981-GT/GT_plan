# Spec F — attachment-contract-identity-and-domain-closure 需求

> 承接 `.agents/tasks/attachment-linkage-assessment-2026-10-27.md` 评估报告 Spec F（用户「删掉死表和死代码，照 Spec D 的做法给证据链接加合同身份」）

## 背景

评估报告发现三类问题：
1. 死表/死代码：`contracts` / `contract_extracted` / `contract_wp_link` 三张表和 `contract_analysis_service.py`（638 行）从未注册路由、前端组件已删，属于纯死代码。
2. 证据链接缺合同身份：Spec D 给 `evidence_links` 加了凭证键 `voucher_key`（V230），合同需要同样的 `contract_key`。
3. 领域边界违规：`check_domain_boundaries.py` 在候选树 v1.0.63 上报 674 条新违规（基线 724 条）。
4. 治理收口：`data_lifecycle` 的 restore/purge 只检查登录无角色门禁；QC/EQCR 审计人员在 HTML 底稿应为只读。

## 六个工作包

### F1 — 死表删除
- 删除 `contracts`、`contract_extracted`、`contract_wp_link` 三张表的 ORM 模型、迁移（V231 DROP）、service（`contract_analysis_service.py`）和测试。
- 前端 `ContractAnalysis*` 组件已在候选树中移除。

### F2 — 证据链接合同身份
- `evidence_links` 新增 `contract_key TEXT`，带位置唯一索引（V232，与 V230 同形）。
- ORM `EvidenceLink.contract_key: Mapped[str | None]`。
- `contract_evidence.py`：normalize / reuse / query 三函数。

### F3 — 合同复用端点
- `POST .../evidence/contract-reuse`（与 voucher-reuse 同形）。
- 上传时接受 `contract_key` 参数。

### F4 — 单据类型路由
- 31 个凭证检查文件调 `/d4/contract-ocr` 时按 `document_type` 返回凭证或合同字段映射。

### F5 — 领域边界全修
- `domain-boundaries.json` 扩 `may_depend_on`（16 个域，逐条验证 import 站点）。
- 未归属文件归入所属域。
- 基线从 724 缩至 134，checker exit 0。

### F6 — 治理收口
- F6.1 `data_lifecycle` restore/purge 改 `require_role(['admin'])`。
- F6.2 QC/EQCR 看 HTML 底稿只读：`WorkpaperEditor` 把 `!canEdit` 加入 GtWpRenderer 的 `:readonly` 绑定。
