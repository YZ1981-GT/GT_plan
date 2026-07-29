# 附件↔底稿关联收敛 — 运维 Runbook

spec: `attachment-workpaper-linkage-convergence`

## 权威真源

| 存储 | 角色 |
|------|------|
| `attachment_working_paper` | **权威** M:N 关联（`association_type` / notes） |
| `attachments.reference_type/reference_id` | 兼容 1:1（process-record / associate 对称双写） |
| `confirmation_attachment_link` | 函证专属；反查只读纳入，解除不碰 |

## 回填（存量 reference → 权威链表）

```bash
cd backend
python -m scripts.backfill_attachment_wp_reference_links --dry-run
python -m scripts.backfill_attachment_wp_reference_links --reconcile
# gap_pct_of_reference 可接受后再：
python -m scripts.backfill_attachment_wp_reference_links --apply
# 必要时：
python -m scripts.backfill_attachment_wp_reference_links --rollback
```

成功标准：`--reconcile` 中 `reference_only_gap == 0`（或业务确认可忽略的残留）。

## Prometheus

`awp_fail_open_total{event=...}` — fail-open 次数。可对升高事件设告警（如 `awp_dual_write_fail_open`）。

## fail-open 可观测

检索日志字段 `event=awp_*_fail_open`，例如：

- `awp_dual_write_fail_open` — linkAttachment 权威写入失败
- `awp_associate_reference_fail_open` — associate 写 reference 失败
- `awp_confirmation_lookup_fail_open` / `awp_evidence_*` / `awp_stale_*` / `awp_ocr_*`

主流程不因上述失败而 500；若某事件持续升高，排查 DB/权限后再补写。

## reference 退役条件（中期）

1. 生产回填完成且 `reference_only_gap` 持续为 0 ≥ 1 个发版周期  
2. 监控确认无纯 reference 写入消费者依赖  
3. 再将 `linkAttachment` 标 deprecated → 仅写权威链表  

在此之前 **不要** 删除 `reference_*` 列或停写。

## 已知测试噪声

- 历史：`test_associate_api` 曾因 `wp_visibility` SQL 使用 PG `::text` 在 SQLite 失败；已改为 `CAST(... AS varchar)`。  
- 若仍失败，优先查 AccessGrant / FakeAuthUser admin 路径，而非回滚关联收敛。

## 证据声明配置

`backend/data/workpaper_evidence_requirements.json` — 宁缺勿造；扩面前缀需业务确认。
