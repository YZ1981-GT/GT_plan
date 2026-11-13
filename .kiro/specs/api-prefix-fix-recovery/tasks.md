# 任务：恢复丢失的 /api 前缀修复

- [x] 1. 守卫先在当前工作区跑一次，确认打红（R2 变异证明的前半）
- [x] 2. 按设计 §2 三方恢复 14 个文件（11 取 theirs、H5 三方合并、DocumentRecognizeDialog 跳过、3 个守卫补回）（R1）
- [x] 3. 恢复后守卫与相关单测转绿；全仓扫描剩余缺 /api 字面量并逐条判定（R2、R4）
- [x] 4. A18-2 实际组件加「导出 Word」与未完成项检查（R3）
- [x] 5. A16 bundle 子底稿缺失时的空态（R3）
- [x] 6. 区域类型检查 + ESLint 新增 0；浏览器在【测试】项目复走 residual 任务 28 五项（R4）
- [x] 7. 回填 residual 任务 26 / 27 / 28 证据，INDEX 登记

## 任务 7 回填：residual 任务 26 / 27 / 28 证据与状态

本节只回填当前恢复工作树可复核的证据，不改写 `platform-performance-residual-findings-closure/tasks.md` 的既有勾选与 2026-11-11 勘误。证据目录 `tmp_api_prefix_verify/` 为任务 6 的临时验证产物，未纳入提交。

### residual 任务 26 / 27

- 恢复依据仍是本 spec requirements/design 记录的三方版本：`base=10810c01e`、`theirs=8eed682ec`；恢复结果包含请求前缀修复、A18-2 实际组件补入口、A16 空态，以及 `apiPathPrefixGuard.spec.ts`、`k10OcrContract.spec.ts`、`iCycleDualModeHealth.spec.ts`。
- `tmp_api_prefix_verify/vitest_wt.log`：5 个文件 **46 passed / 0 failed**，其中 API 前缀守卫 7、K10 契约 3、A16 空态 5、I 循环健康 10、A18-2 组件 21；API 前缀守卫同时报告扫描面达到 2000 以上。
- 区域 ESLint：`eslint_wt2.log` 的退出码为 0，**0 error / 10 warning / 14 files_checked**。warning 是既有规则提示，不写成全无告警。
- 区域类型检查：`tsc_wt_batch1.log` 与 `tsc_wt_batch2.log` 均为 `EXIT=2`；与对应 `tsc_head_batch*.log` 对比，`diff_tsc.py` 两批均为 **ADDED=0、RESOLVED=0、OOM=false**。因此结论是“相对 HEAD 无新增类型错误”，不是“类型检查通过”。
- 任务 26 / 27 的恢复代码与守卫在当前工作树已存在并通过上述定向验证，但尚未提交或推送；原 residual spec 的历史任务状态保持 append-only。

### residual 任务 28 五项界面走查

- 统一无头浏览器探针 `tmp_api_prefix_verify/out_all.json` 使用 `http://127.0.0.1:3091` 与【测试】项目，页面加载阶段记录 `consoleErrors=[]`、`pageErrors=[]`，所记录的 API 请求没有 HTML 响应替代 JSON。该结果只覆盖页面加载与可达性，不能替代五项功能逐项通过。
- **A18-2**：实际组件 `a18-2-regulatory-communication` 显示“导出 Word”，检查请求返回 200，未完成项弹窗列出 4 项未填议题；同一探针拿到编辑锁 409 并进入只读态，未形成可复核的读写保存往返，也未完成真实 docx 下载。因此只记为部分证据，不记任务 28 通过。
- **A16 推荐标记**：`out_all.json` 明确显示 A16-1~A16-7 均未生成，组件显示缺失子底稿空态和“去底稿列表生成”。没有真实子底稿就无法验证推荐标记，不能写成通过。
- **I 循环在线编辑**：I1 健康请求 `/api/workpapers/onlyoffice/health` 返回 200 JSON，但 I1 页面仍没有“在线编辑”控件；这证明健康探针可达，不证明 I1 能切换在线编辑。能力已注册的 I4 对照探针显示切换控件可见，不能替代 I1 验收。
- **H3 勾稽**：专用探针记录 `/api/custom-query/wp-id-by-code` 返回 404，并显示“对方数据不可用”；最终合并页面探针未实际进入可观测的勾稽取数请求。因此 H3 勾稽未通过，不能按页面无 console error 推断通过。
- **K10 识别**：`probe5_report` 通过真实 UI 在 K10-6 新增临时行，`POST /api/workpapers/{wp_id}/d4/contract-ocr` 返回 200，且该次 `consoleErrors=[]`、`pageErrors=[]`、无其他写请求；但 `probe6_report` 清理时遇到编辑锁 409，行数保持 **1 → 1**，删除请求未完成，临时数据未闭合。故只记端点与界面路径部分通过，不记五项走查通过。
- PBC 页签的 200 / 空态是 residual spec 任务 23 的独立证据，不与本任务 28 五项合并计数。

### 任务状态结论

- 本 spec 任务 7 的交付物是证据回填与 INDEX 登记，现已完成；它不等于 residual 任务 28 已完成。
- residual 任务 26 / 27：当前恢复工作树已有实现与定向守卫证据，待提交/推送后才具备分支级交付状态。
- residual 任务 28：仍为 `[ ]*`，五项中 A16 推荐、A18-2 完整读写/下载、I1 切换、H3 勾稽、K10 清理均没有足够的闭环证据。现有证据不得升级为“浏览器五项通过”。
- 已知限制：类型检查命令退出码为 2（HEAD 同样存在类型债）；A16 缺真实子底稿；A18-2 有编辑锁 409；I1 仍无在线编辑控件；H3 专用探针返回 404；K10 临时行未清理。