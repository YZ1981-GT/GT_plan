# 凭证运行完整性与可见性收口 (voucher-runtime-integrity-and-visibility-closure)

## 背景

凭证模块（序时账穿透 → 凭证消歧 → 挂凭/抽凭 → 凭证证据 → 抽样概览）经评估发现三类运行完整性与数据安全问题：

1. **鉴权缺口**：单笔挂凭端点不校验 `working_paper_id` / `sampling_record_id` 归属当前项目（批量端点有校验）；凭证链接查询与已抽凭证列表不走底稿可见性门禁（证据查询有）
2. **投影静默失败**：抽凭引擎的四个 sampling 投影函数全是 `except Exception` fail-open 且不用 `begin_nested()`，PG 事务 aborted 会被吞掉，投影登记可能**每次静默失败**而无人发现
3. **D2 合并口径不一致**：凭证检查 Excel 导入的 `mergeVoucherRows` 按 `voucherNo` 单字段去重，而 sampled_vouchers 唯一约束和共享回填函数按完整凭证键/分录指纹，同号不同日的凭证会被误合并

此外，真实库 30 条引擎登记行缺 `voucher_date` / `company_code` / `voucher_type`（旧身份债），1 条手工记录 `working_paper_id=NULL`（死路记录），需要数据治理。

本 spec 是凭证模块三批改进的第一批（Tier 1：运行完整性），后续 Tier 2（用户流程收敛）和 Tier 3（证据闭环）以本 spec 为前置。

## 关键源文件

| 区域 | 文件 | 说明 |
|------|------|------|
| 挂凭路由 | `backend/app/routers/voucher_links.py` | 6 个端点：单笔/批量挂凭、列表、删除、链接查询、证据查询 |
| 投影服务 | `backend/app/services/sampling_registry_service.py` | `register_sampling_batch` / `register_sampled_vouchers` / `undo_sampling_registration` / `update_sampling_record_evaluation` |
| 凭证证据 | `backend/app/services/voucher_evidence.py` | `_visible_wp_ids` + `voucher_evidence_by_keys`（有底稿可见性，参考基准） |
| D2 合并 | `audit-platform/frontend/src/components/workpaper/composables/useD2VoucherCheckEnhanced.ts` | `mergeVoucherRows`（按 voucherNo 单字段） |
| 共享回填 | `audit-platform/frontend/src/components/workpaper/shared/voucherCheckFill.ts` | `mergeVoucherCheckRows`（按分录指纹 lfp） |
| 凭证模型 | `backend/app/models/workpaper_models.py` | `SampledVoucher` ORM（V084/V139/V166/V210） |
| 凭证身份 | `backend/app/services/voucher_identity.py` | `VoucherKey` 单一来源 |

---

## 需求

### R1：单笔挂凭归属校验

**现状**：`POST /sample-voucher` 接受 `working_paper_id` 和 `sampling_record_id` 但不校验它们是否属于路径 `project_id`。攻击者可将凭证挂到其他项目的底稿。批量端点 `/sample-vouchers/batch` 通过 `_project_workpapers()` 校验了 `working_paper_id`。

**要求**：
- R1.1：`working_paper_id` 非空时必须校验属于 `project_id` 且未删除，否则 422 `WP_NOT_IN_PROJECT`
- R1.2：`sampling_record_id` 非空时必须校验属于 `project_id` 且未软删，否则 422 `SAMPLING_RECORD_NOT_IN_PROJECT`
- R1.3：复用批量端点已有的 `_project_workpapers()` 校验逻辑，不引入新查询模式
- R1.4：校验失败的错误码和文案与批量端点一致（`WP_NOT_IN_PROJECT`）

### R2：凭证链接查询底稿可见性

**现状**：`POST /voucher-links/query` 返回项目内所有底稿的挂凭记录，不走底稿可见性门禁。审计员能看到不该看到的底稿挂凭信息。`POST /voucher-evidence/query` 有完整可见性过滤（`_visible_wp_ids`）。

**要求**：
- R2.1：`/voucher-links/query` 返回结果按底稿可见性过滤——当前用户不可见的底稿的挂凭记录不列出（静默排除，不报错）
- R2.2：复用 `voucher_evidence.py` 已有的 `_visible_wp_ids()` 判定逻辑（同一判定口径）
- R2.3：`working_paper_id=NULL` 的记录（旧手工"抽中本凭证"无底稿）不受影响，照常列出
- R2.4：`wp_missing` 标记逻辑不变（底稿在项目中但已删除/不存在仍标 `wp_missing`）

### R3：已抽凭证列表底稿可见性

**现状**：`GET /sampled-vouchers` 只按 `project_id`/`year` 过滤，审计员能看到所有底稿的凭证记录。

**要求**：
- R3.1：未指定 `working_paper_id` 时按底稿可见性过滤（不可见的底稿的记录不列出）
- R3.2：指定 `working_paper_id` 时仍返回该底稿的全部凭证（调用方是底稿本身拉取自己的凭证，已有底稿级鉴权）
- R3.3：`working_paper_id=NULL` 的记录对所有项目成员可见（无归属底稿 = 项目级登记）

### R4：投影 SAVEPOINT 加固

**现状**：四个投影函数用 `except Exception` fail-open 但不用 `begin_nested()`。若投影 SQL 导致 PG 事务 aborted，后续 commit 也会失败——但异常已被吞，调用方不知道。代码注释自己承认了风险：「uq 索引表达式须逐字一致，否则 PG 推断不到该索引，抛错后被下方 fail-open 吞成 WARNING，登记每次都静默失败」。

**要求**：
- R4.1：每个投影函数的写操作包在 `async with db.begin_nested()` SAVEPOINT 内，失败只回滚投影、不污染主事务
- R4.2：保持 fail-open 语义（投影失败不阻断回填/撤销/评价主流程），但 WARNING 日志必须包含异常类名和消息
- R4.3：涉及四个函数：`register_sampling_batch`、`register_sampled_vouchers`、`undo_sampling_registration`、`update_sampling_record_evaluation`
- R4.4：不改变调用方的事务边界（仍由调用方 commit）

### R5：D2 凭证检查 Excel 导入合并口径对齐

**现状**：`mergeVoucherRows` 按 `voucherNo` 单字段去重，同号不同日的凭证（真实库实测 813 个凭证号跨日期复用）会被误合并。共享的 `mergeVoucherCheckRows` 按分录指纹 (lfp) 去重，口径更精确。

**要求**：
- R5.1：D2 Excel 导入合并改用 `voucherNo + voucherDate` 联合去重（不能只用 lfp，因为 Excel 导入行没有后端分录指纹）
- R5.2：保留「已有行的 check1~check5 不被覆盖」的业务语义
- R5.3：重编号逻辑不变（合并后 `seq = index + 1`）

### R6：存量旧身份数据治理

**现状**：真实库 `sampled_vouchers` 30 条引擎登记缺 `voucher_date`/`company_code`/`voucher_type`（来自旧 `filled_voucher_nos` 格式日志），1 条手工记录 `working_paper_id=NULL`。

**要求**：
- R6.1：编写 dry-run 治理脚本，按 `(project_id, year, voucher_no)` 回查当前 active 账套，无歧义（唯一匹配）的自动补全三列，有歧义的标记待人工确认
- R6.2：`working_paper_id=NULL` 的记录标记为 `legacy_orphan`（通过 note 字段），不自动删除
- R6.3：脚本放 `backend/scripts/fix/`，支持 `--dry-run`（默认）和 `--apply`
- R6.4：治理结果输出 JSON 报告（补全数 / 歧义数 / 孤儿数）

### R7：鉴权基线守卫

**要求**：
- R7.1：后端测试覆盖 R1（单笔挂凭归属校验）、R2/R3（可见性过滤）的正反两面
- R7.2：变异检测：去掉归属校验后测试必须打红
- R7.3：D2 合并口径的 PBT 用例（同号不同日 → 不合并）

---

## 范围边界

### 包含

- voucher_links.py 的 3 个鉴权缺口修复（R1~R3）
- sampling_registry_service.py 的 4 个投影函数 SAVEPOINT 加固（R4）
- useD2VoucherCheckEnhanced.ts 的 mergeVoucherRows 合并口径对齐（R5）
- 存量旧数据 dry-run 治理脚本（R6）
- 守卫测试（R7）

### 不包含

- 查账页 UX 收敛（深链参数 `?code=` vs `?account=`、路由重挂、响应式布局）→ Tier 2 spec
- "抽中本凭证"功能替换/下线 → Tier 2 spec
- 凭证证据 OCR 接入与审核闭环 → Tier 3 spec
- 迁移 V235~V251 的执行（属平台级迁移治理，非本 spec 范围）
- SamplingEnhanced 页面硬编码年度/基准日 → Tier 2 spec
- VoucherLinkTags 可点击/跳转 → Tier 2 spec
