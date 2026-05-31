# ADR-CONSOL-206: ConsolSnapshot 存真实数据实现签字冻结（P2）

## 状态
已接受 (2026-05-30)

## 背景

`create_snapshot`（report_trace.py）只存 `{created_at}` 空壳，不快照真实合并数据（"框架在内容空"，P2）。合并报告签字后若子公司数据被改，合并结果会变，但无法证明"签字时合并数是多少"。

## 决策

新建 `consol_snapshot_service`：

- `create_consol_snapshot(db, project_id, year, reason, *, user_id, lock=None)`：序列化签字时刻 consol_trial / worksheet / report / notes 全量结果（金额一律 `str(Decimal)` 避免 float 精度丢失），每源独立 try/except 记 captured_sources（单源失败不阻断）。
- 哈希 + 压缩存储（EH8）：`snapshot_data = {_format:"gzip+base64", _payload: base64(gzip(raw_json)), _hash: sha256(raw_json), _locked: bool, _meta: {counts, captured_sources, ...}}`；SHA-256 在压缩前的原始 canonical JSON（sort_keys）上计算（S8 完整性）。
- 签字锁定只读：reason ∈ {sign,signed,lock,...} 或 lock=True → `_locked=True`（无 update 端点，锁定快照天然不可变）。
- `restore_consol_snapshot(snapshot)`：解压+反序列化+SHA-256 校验，返回 `{data, hash_valid, hash, locked}`；兼容旧空壳（legacy=True, hash_valid=False），损坏 payload 不抛错。
- `compare_snapshot_to_current(db, snapshot)`：还原签字时 trial vs 当前 consol_trial，逐科目 `consol_amount` 差异（5E.3）。
- 审计留痕（5E.4）：复用 Phase 0 `consol_audit_helper.log_consol_action`（action='consol.snapshot.create'），与快照同事务 commit；审计失败仅 warning 不破坏快照创建。
- report_trace.py：create_snapshot 端点改调新服务 + 新增 `.../snapshots/{id}/restore` 和 `.../snapshots/{id}/compare` 只读端点。

## 后果

- 正向：签字冻结有真实数据可还原 + 合规可追溯（S8）。
- 代价：快照存储开销（gzip+base64 压缩 + _meta 大小监控缓解）。
- 守门：S8 由 `test_consol_phase2_snapshot_pbt.py`（10 测试）验证 round-trip 还原+哈希校验+篡改检测+旧空壳兼容。
