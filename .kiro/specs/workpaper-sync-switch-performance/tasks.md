# 底稿 HTML ↔ 在线编辑切换提速 — Tasks

> 顺序说明：P2（指纹直通）以 P5（服务端直取）为前提 —— 指纹必须对「服务端亲手读的那份 store」记录才可证明正确，
> 所以两者合并为一个交付（任务 3）。第一批 = 1~4 已交付；P3/P4/P6 经评估延后（见 design §8~§10）。

- [x] 1. P0 分阶段计时
  - [x] 1.1 `sync_timing.py`（ContextVar 作用域 + mark + 结构化日志）+ 单测 6 passed
  - [x] 1.2 `ApplyJournal.record` 接 mark；router 三处开作用域；coordinator 关键阶段 mark
  - [x] 1.3 前端桥 `switchTimings`（`bridgeSwitchTimings.ts`：冲刷 / 取数或直取 / 物化 / 挂载 / 就绪 / 确认 + User Timing `wp-sync-switch:<stage>`）+ spec 5 passed
  - [x] 1.4 工具 `scripts/analyze/report_sync_switch_timings.py` + 守卫 4 passed；真库基线：和平药房 html_to_oo 全量 13.9~15.2s / 复用 1.9~2.4s

- [x] 2. P1 骨架无关业务身份复用
  - [x] 2.1 `business_identity.py` 纯函数 + 单测 22 passed（含 PBT max_examples=5）
  - [x] 2.2 coordinator `_find_skeleton_equivalent_reuse` 接线 + `_settle_reuse(verdict=)` + 单测 / PG 场景
  - [x] 2.3 变异 6/6 全杀
  - [x] 2.4 真库对拍 5/5

- [x] 3. P5 + P2 服务端直取投影 + store 指纹直通
  - [x] 3.1 `store_materialize.py`：读 store → 指纹 → 命中走快路径 / 否则服务端构造投影 → pending → materialize → **仅复用命中时**记录指纹
  - [x] 3.2 coordinator `reuse_for_unchanged_store`
  - [x] 3.3 router 端点 + 前端契约 + 路由普查同步
  - [x] 3.4 端点级 PG + 零库 + 真库测试；变异 16/16 + 2/2 全杀
  - [x] 3.5 前端 `materializeFromStore` + `withServerStoreFlush` + 桥接线 + spec 102 passed + 变异 11/11
  - [x] 3.6 变异汇总 29/29 全杀

- [x] 4. 第一批回归 + 两家企业浏览器实测
  - [x] 4.1 golden digest OK / 行数门 OK / 前端 134 passed / 后端 124 passed / 宽回归零业务回归
  - [x] 4.2 浏览器实测：和平药房 server_store_fast materialize **203ms** / 重药安徽首次 **1518ms** 再次 **195ms**；对比基线 13.9~15.2s

- [ ]* 5. P4 去重复提取 —— 延后（收益在 OO→HTML 保存方向，不在切换路径，见 design §10）
- [ ]* 6. P3 OO 保存后先回表单 —— 延后（独立体验改善，需迁移+17 宿主接线，见 design §10）
- [ ]* 7. 小项与评估
  - [x] 7.1 空闲预加载 OnlyOffice 脚本 —— 延后（OO 加载 ~3s 是 DocsAPI 自身行为，预加载的收益取决于用户停留时长不确定）
  - [x] 7.2 P6 进程池 ROI 评估：对切换路径零收益（design §8）；`.json.gz` 明文发现登记（design §9）

- [x] 8. 收尾
  - [x] 8.1 spec 三件套证据、design §8~§10 评估结论
  - [x] 8.2 tasks.md 勾选 + 延后标记
  - [ ] 8.3 memory.md 更新（下次会话做）
