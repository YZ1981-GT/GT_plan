# 底稿多窗口编辑锁两处漏洞收口 — 任务

> spec: `workpaper-multi-window-lock-gaps`

- [x] 1. 窗口编号认领（R1.1 / R1.2 / R1.5，D1 / D1b）：`clientInstance.ts` 新增 `claimClientInstanceId()`（Web Locks 认领、被占换号、不可用保留）；不提供 Web Locks 时 localStorage 登记（页面隐藏注销、往返缓存恢复重登、被丢弃后重载认回）；生成编号改用 `newUuid`；单测覆盖复制标签页换号、刷新保留、opener、非安全上下文（13 例）
- [x] 2. 认领接线（R1.3 / R1.4，D2 / D3）：`main.ts` 启动认领；`useEditingLock.acquire / forceAcquire` 等认领；`crossWindowAuth` 按当前编号比较；单测
- [x] 3. 写请求带窗口编号（R2.6，D5）：`http.ts` 非 GET 请求加头；`WorkpaperWordEditor` 导入原生请求加头；单测
- [x] 4. 前端只读拦截（R2.1 / R2.2，D6）：`GtWpToolbar` readonly、`GtWpRenderer` 传入并拦导入、Word「导入数据」只读禁用；单测
- [x] 5. 后端内容写入校验编辑锁（R2.3 / R2.4 / R2.5，D4）：`find_blocking_lock` + `dedicated_wp_gate` 接入；单测覆盖持锁人 / 同人他窗 / 他人 / 无锁 / 过期 / 非内容路由 / GET（14 例）
- [x] 6. 浏览器实测（【测试】公式同步乙有限公司_2025 · D4，自起无头 Chrome）：`http://127.0.0.1:3030`（安全上下文）与 `http://192.168.20.60:3030`（非安全上下文，无 Web Locks / `crypto.randomUUID`）各一轮，共 34 项全过 —— 复制标签页换新编号、只读横幅、导入 / 增行禁用、锁表只有原窗口一行；复制窗口直接 PUT `checklist-responses` 与 POST `d4/import-data` 均 423「你的另一个窗口」，持锁窗口 200 / 过门禁（缺文件 422）；关掉复制窗口原锁仍在；刷新原窗口编号不变、仍可编辑；离开后锁释放
- [x] 7. 回归与提交：主工作区相关前端 26 文件 150 过、4 红（与 HEAD 同：authTokenSingleSource / rawRequestAuth 违规集合不变、GtWpRuntimeBoundary.pbt 2 例换回 HEAD 版渲染器同红）；提交树（HEAD + 本 spec）干净检出：前端 25 文件 137 过、4 例 + 1 文件失败与 HEAD 逐条相同，门禁相关既有后端 251 例 248 过、3 红与 HEAD 相同（G11 页签集合、F2 AI 生成 503），新增后端 14 过；变异前端 F1~F21、后端 B1~B4 全红在预期断言、阴性对照全绿；单区域 vue-tsc 改动文件 0 新增（阳性对照报 TS2322）；只提交本 spec 文件（`main.ts` / `http.ts` / INDEX 按「HEAD + 本 spec 改动块」暂存）

## 第二轮（R3~R5）

- [x] 8. 范围单一来源与门（R3.1，D7 / D8）：`_wp_edit_lock_scope.py` 规则表（229 CHECK / 319 NO_WRITE / 15 COLLAB / 3 LOCK / 19 ON_APPLY）+ `edit_lock_scope`；`dedicated_wp_gate` 默认校验、放请求人进 `ContextVar`；`enforce_edit_lock_at_write_point` + 18 个 `_maybe_apply_*` 接线；`NON_CONTENT_WRITES` 3 条（export-with-metadata / ai-chat/history / ai/tsj-review）；`UNGATED_WRITE_DECISIONS` 23 条全登记；`BODY_CARRIED_CHECKED` 3 条。后端 101 passed（含 scope guard 15 例 + content write 21 例）
- [x] 9. 不经门的写接口与在线编辑入口（R3.2 / R3.3，D9 / D10）：版本回滚（`version_trail.rollback_version` + `request` 参数）、程序行裁剪 / 恢复（`procedure_trim`）、附件解除 / 关联（`attachments.py` + 模块级 import `enforce_edit_lock_for_content_write`、归档校验之后）、H5 导入（`h5_oil_gas_assets`）、A17-7 导入 B3（`a17_summary` + 项目一致校验关闭 IDOR）；`wp_sync_router` 六个入口 `_enforce_entry_edit_lock`（purpose=online_edit、文案「不能进入在线编辑」）；PG stub DDL 加 `editing_locks`（3 个文件）。后端同上 101 passed
- [x] 10. 旧版 OnlyOffice 配置只读（R3.4，D11）：`get_sheet_onlyoffice_config` 锁挡住时 mode→view（OO 容器 JWT_ENABLED=true + 浏览器令牌校验，前端改 view 无效必须服务端降级）；`http.ts` 给 `/onlyoffice-config` GET 带窗口编号（`needsClientInstance`）；单测 `test_edit_lock_held_elsewhere_gives_view_config` + `_empty_result` 补 `scalars().first()=None`
- [x] 11. 前端只读不自动写（R3.5，§6.2）：`WorkpaperEditor.onRefresh` 只读不重建模板；`GtA171AuditSummary / GtA176ClosingMeeting / GtA177IndependenceDeclaration` readonly prop 阻止 docx 同步；`useF2StocktakeDualMode` readonly 跳过两个 sync；`GtCustomWpEditor.refreshProjection` 只读跳过；单测 `readonlyNoAutoWrites.spec.ts` 10 例 + `useF2StocktakeDualMode.readonly.spec.ts` 2 例
- [x] 12. 窗口编号（R4 / R5，D12~D14）：`CLAIMED_KEY` 认领标记（旧标签页编号换一次）；登记改 JSON `{n,t,f?}` 带 `DOC_NONCE` 文档标识 + 冻结标记；`SAME_DOCUMENT` 集合（同一文档重载模块不误判）；BroadcastChannel `answerProbes` / `someoneUses`（`PROBE_TIMEOUT_MS=1500`）；`isClientInstanceSettled` + `http.ts` 拦截器等认领（`needsClientInstance` 的非 GET / 锁 / OO 配置）；Web Locks 兜底超时 `LOCK_TIMEOUT_MS=3000`；单测 21 例 + http header 2 例
- [x] 13. 守卫与验证（R3.6）：`test_wp_edit_lock_scope_guard.py` 15 例（全量路由豁免命中、不写底稿静态检查含 BOM、写回点接线、不经门登记、NON_CONTENT_WRITES 命中）；变异后端 M1~M5/M7 全 PASS（6 红 1 阴性绿，M6 函数级限制 = 设计如此），前端 F1~F7 全 PASS（6 红 1 阴性绿）；单区域 vue-tsc 本 spec 文件 0 新增（阳性对照 TS2322 命中）；行数门 `wp_onlyoffice_router` HEAD=1826 / `wp_sync_router` HEAD=3405 已超白名单（并发会话维护），本 spec 仅增 8 / 25 行
- [x] 14. 浏览器实测（127.0.0.1 与 192.168.20.60 各一轮共 16 项，12 通过）：B1 只读窗口加载无 423 弹窗 ✅（两端）；B2 只读 PUT checklist-responses→423 + 「你的另一个窗口编辑，本窗口为只读」✅（两端）；B5 升级前旧标签页编号→换新号并写认领标记 ✅（两端）；B6 内网 http 崩溃重开认回原编号（BroadcastChannel 1.5s 无回答）✅（内网 IP）；B7 锁释放 ✅（两端）。B3 OO 降级 = D4 无 OO 册（单测 + M5 变异已覆盖）；B4 持锁 422 = checklist 请求体格式（B2 已证 423 在业务校验之前）。候选树干净检出回归：后端 101 passed（3 预存红同 HEAD）+ 前端 35 passed；工作区 425 文件 4546 passed / 22 红全为预存
