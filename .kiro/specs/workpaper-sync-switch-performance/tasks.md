# 底稿 HTML ↔ 在线编辑切换提速 — Tasks

> 顺序说明：P2（指纹直通）以 P5（服务端直取）为前提 —— 指纹必须对「服务端亲手读的那份 store」记录才可证明正确，
> 所以两者合并为一个交付（任务 3）。第一批 = 1~4，第二批 = 5~8。

- [x] 1. P0 分阶段计时
  - [x] 1.1 `sync_timing.py`（ContextVar 作用域 + mark + 结构化日志）+ 单测 6 passed
  - [x] 1.2 `ApplyJournal.record` 接 mark；router 三处开作用域；coordinator 关键阶段 mark
  - [x] 1.3 前端桥 `switchTimings`（`bridgeSwitchTimings.ts`：冲刷 / 取数或直取 / 物化 / 挂载 / 就绪 / 确认 + User Timing `wp-sync-switch:<stage>`）+ spec 5 passed
  - [x] 1.4 工具 `scripts/analyze/report_sync_switch_timings.py` + 守卫 4 passed；真库基线：和平药房 html_to_oo 全量 13.9~15.2s / 复用 1.9~2.4s

- [x] 2. P1 骨架无关业务身份复用
  - [x] 2.1 `business_identity.py` 纯函数 + 单测 22 passed（含 PBT max_examples=5）
  - [x] 2.2 coordinator `_find_skeleton_equivalent_reuse` 接线 + `_settle_reuse(verdict=)` + 单测 / PG 场景
  - [x] 2.3 变异 6/6 全杀（去掉骨架剥离 / 位置无关改保序 / 未声明判据写反 / 表示腿去掉 / 逐字节恒真 / 未声明骨架值不忽略）
  - [x] 2.4 真库对拍 5/5：和平药房 44→45/46→47 等价（8 行 26 字段忽略、12 骨架行位置无关）；47→48 真实编辑不等价；重药 10→11/14→15 等价（20 行 86 字段忽略）；canonical 幂等成立

- [x] 3. P5 + P2 服务端直取投影 + store 指纹直通
  - [x] 3.1 `store_materialize.py`：读 store → 指纹 → 命中走快路径 / 否则服务端构造投影 → pending → materialize → **仅复用命中时**记录指纹（提交 / 重放不记）；`StorePhaseRejectedError` 包 store 阶段→422，物化阶段走 `classify_materialize_rejection`（未登记→500）
  - [x] 3.2 coordinator `reuse_for_unchanged_store`（open_operation → room/descriptor → apply，零 revision）
  - [x] 3.3 router 端点 `materialize-from-store` + 写 action 登记 + `_attach_launch_urls` 共用尾段；`recovery_case_listing.py` 迁出腾行数门；前端契约重生成（digest `b63cdae1`，21 routes，8 idempotent）；路由普查同步（slashed suffix +1 / guard-first +7 / `expected_required` +1）
  - [x] 3.4 端点级 PG 测试 S15（401 / 统一 404 / 403 锁定 / 非 store 型 422 零副作用）；零库 30 passed（编排分支 + 指纹口径 + 状态码分段 + 响应体指标）；真库 11 passed（同源 / 直通 / 世界前进让路 / 提交后真比 / 记录不符回落）；变异 16/16（后端）+ 2/2（路由）全杀
  - [x] 3.5 前端 `materializeFromStore` + `withServerStoreFlush`（哨兵一次性、同 scope 作废旧窗口、revision=-1、写端点发出前拒哨兵）+ `SERVER_STORE_FALLBACK_CODES` + 桥 `flushForSwitch`/`materializeViaServerStore`/`retryAfterFirstPublication`；spec 84+13+5=102 passed；前端变异 11/11 全杀；ESLint 0 errors；后端 `test_frontend_fallback_codes_match_the_backend_error_codes` 钉住前后端 error_code 逐字一致
  - [x] 3.6 变异汇总：后端 16/16 + 路由 2/2 + 前端 11/11 = 29/29 全杀

- [x] 4. 第一批回归 + 两家企业浏览器实测
  - [x] 4.1 golden digest OK；本 spec 文件行数门 OK；前端 sync 7 spec 134 passed；后端 6 文件 124 passed；宽回归（127 文件）对 HEAD 新增仅 2 条（`test_committed_code_imports_only_committed_modules` = 新文件未提交 + `test_production_manifest_registers_nothing_for_g7` = 进程内缓存 flaky），零业务回归
  - [x] 4.2 浏览器实测（和平药房 / 重药安徽 D2-2，无改动来回切）：
    - 和平药房：server_store_fast, materialize **203ms** / confirmed 3.9s；DB revision=49 不变，stage=store_fingerprint_reused
    - 重药安徽首次：server_store, materialize **1518ms** / confirmed 4.4s；第二次 server_store_fast, materialize **195ms** / confirmed 3.3s；DB revision=15 不变
    - 对比基线：13.9~15.2s → 首次 1.5s / 再次 0.2s（OO 就绪 ~3.3s 含 DocsAPI 自身加载 ~3s）
    - 网络请求：只有 materialize-from-store + confirm-descriptor，无 store-projection / pending / materialize

- [ ] 5. P4 去重复提取
  - [ ] 5.1 `projection_extract_key` + overlay 改键 + 单测
  - [ ] 5.2 `extract_three_way` 去重 + journal 不变 + 单测
  - [ ] 5.3 提交成功后回填缓存（失败不写）+ 守卫
  - [ ] 5.4 变异

- [ ] 6. P3 OO 保存后先回表单
  - [ ] 6.1 V185/R185 `leave_requested_at` + ORM；leave `defer_until_settled`；终态结算执行延迟离开 + PG 守卫
  - [ ] 6.2 桥 `html_pending_apply` + `returnToFormWhileApplying` + 追踪器归桥 + 机器审计通过
  - [ ] 6.3 EditorHost 接线 + 宿主只读 + 横幅
  - [ ] 6.4 前端 spec + 浏览器实测

- [ ] 7. 小项与评估
  - [ ] 7.1 空闲预加载 OnlyOffice 脚本 + spec
  - [ ] 7.2 P6 进程池 ROI 评估写入 design；`.json.gz` 明文发现登记

- [ ] 8. 第二批回归 + 浏览器实测 + 收尾（spec 证据 / INDEX / memory / 清理探针）
