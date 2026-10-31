# 任务：`{pid}` 项目接口鉴权覆盖

> 规则：标完成须有代码 + 测试证据；未实测标 `[ ]*`；不提交不推送；只改本 spec 拥有的改动块。

- [x] 1. 扫描口径：`_has_project_segment` + `_PROJECT_SEG` 正则 + 分母；8 个新 token（底稿门 / 任务门 / 参与者判定 / 抽样辅助函数），各有可伪证断言；`{pid}` 自检样本 5 正 2 反；HEAD 上跑确认 review_prompt 3 none、cutoff 4 identity、voucher 2 identity — 6 failed 49 passed
- [x] 2. review_prompt 7 个端点补鉴权：batch-review review / progress+export readonly / 单底稿 authorize_wp_read+assert_project_permission review / finding_status 按发现所属项目 review / coverage+metrics get_current_user
- [x] 3. 截止测试 `_authorize_cutoff_wp`（edit/read + 底稿属于路径项目）；抽凭历史 authorize_wp_read + pid 比较；对比两条记录 project_id==pid + authorize_wp_read
- [x] 4. `test_pid_path_authz_endpoints.py` 12 例（SQLite 真 ORM 行 + 真实依赖链）全绿；`test_review_prompt_integration.py` 改 SQLite 真项目+底稿+review 级成员；`test_cutoff_sampling_integration.py` / `test_voucher_sampling_integration.py` / `test_voucher_sampling_actor.py` / `test_voucher_sampling_exclusion.py` 适配新鉴权（428 passed 0 failed）
- [x] 5. 台账 review_workpaper 改 native_authz + JUSTIFIED_ALLOWLIST + test_ids；`_PREFIXED_IDENTITY_ONLY_BASELINE` 227（HEAD 232 → 含本 spec 修的 6 条降至 227；wt 现算 219 含并发改动）；drift 对比：wt 的 wp_bound_ungated 仍报该条（台账改动未入库），derived 正确 native_authz，native_authz_unaudited 不含本条
- [x] 6. 回归：鉴权基线 + X-3 台账 + note-edit-gate + 抽样 / AI 复核 / 撤销鉴权等 428 passed 0 failed；白名单 review_prompt.py=945 + authorization_baseline.py=879；INDEX Active 14
