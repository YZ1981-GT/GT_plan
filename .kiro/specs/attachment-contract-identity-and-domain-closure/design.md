# Spec F — 设计与实施记录

## §1 架构决策

### ADR-F1: 死表删除策略
- V231 `DROP TABLE IF EXISTS` 三张死表 + 四个枚举类型。
- ORM 模型从 `ai_models.py` 删除，service 文件整文件删除。
- 测试文件一并删除：`test_contract_analysis.py`、`test_contract_analysis_service.py`。

### ADR-F2: contract_key 与 voucher_key 同形
- V232 完全镜像 V230 结构：单列 + 部分索引 + 位置唯一索引。
- `contract_evidence.py` 镜像 `voucher_evidence.py` 的三函数签名。
- 规范格式：`normalize_contract_key` 接受 JSON 列表 `['合同号','对方名称']`。

### ADR-F5: 领域边界扩展原则
- 只在实际 import 站点验证后才扩 `may_depend_on`（不 launder layering defects）。
- 16 个域添加了合法依赖，各由 import 现场实证。
- 基线 724 → 134（590 条 resolved），checker exit 0。

### ADR-F6.1: data_lifecycle admin gate
- restore_project / purge_project 使用 `Depends(require_role(['admin']))`。
- capacity / stats / import-queue 保持 `Depends(get_current_user)`（只读端点）。
- 依据：destroy/restore 是不可逆操作，只允许管理员。

### ADR-F6.2: QC/EQCR HTML readonly
- `WorkpaperEditor.vue` 中 GtWpRenderer 的 `:readonly` 绑定增加 `|| !canEdit`。
- `canEdit` = `!isArchived && canDo('edit', 'workpaper')`。
- QC/EQCR 用户 `canDo('edit', 'workpaper')` = false → `!canEdit` = true → readonly。
- 前端体验优化，后端 deps 层仍是安全边界。

## §2 实施记录

### FEAT-001 — 合同身份与死表删除
- V231: DROP contracts / contract_extracted / contract_wp_link + 枚举
- V232: evidence_links.contract_key + 索引
- 删除 contract_analysis_service.py（638 行）
- 删除 ai_models.py 中 Contract/ContractExtracted/ContractWpLink
- 新增 contract_evidence.py + contract-reuse 端点
- 新增 test_contract_evidence.py + test_contract_evidence_router.py

### FEAT-002 — 领域边界全修
- domain-boundaries.json: 16 域 may_depend_on 扩展
- 2 个未归属文件归入 frontend-shell
- 基线 724 → 134（590 条 resolved）
- checker exit 0, 18 self-tests pass

### FEAT-003 — 治理收口
- data_lifecycle.py: restore/purge 改 require_role(['admin'])
- WorkpaperEditor.vue: `:readonly` 增加 `|| !canEdit`
- test_data_lifecycle_admin_gate.py: 8 tests (含变异证明)
- WorkpaperEditorReadonly.spec.ts: 6 tests (含变异证明)

## §3 待拍板项汇总

| # | 来源 | 项目 | 状态 |
|---|------|------|------|
| 1 | Spec E | `SignatureBlock` 签字模型 | 已按建议定 |
| 2 | Spec E | `data_lifecycle` restore/purge 鉴权 | ✅ 本 spec F6.1 已修 |
| 3 | Spec C | QC/EQCR 只读是否接到 HTML 渲染器 | ✅ 本 spec F6.2 已修 |
| 4 | Spec D | 领域边界清单 `workpapers → evidence` | ✅ 本 spec F5 已修 |
| 5 | Spec D | 逐笔全满足 | 用户定「全按建议来」 |

## §4 勘误
- 无
