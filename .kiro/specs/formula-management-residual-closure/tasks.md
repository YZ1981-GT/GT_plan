# 实施计划：公式管理残留安全与可用性收口

> 基线：`29b4028810445050da0d0d26b0007dc8c42740d`。本任务主会话直接实施，不使用工作流。

- [x] 0. 现场复核与范围冻结
  - AST 核验 12 个无鉴权路由、模板路径拼接、建议类型错配、死行内分支、假空态和 warnings 丢失。
  - 排除 S2/S3/S5/S8/S9/S10；保护 S5 三个未跟踪文件。

- [x] 1. 附注模板端点安全
  - 全端点加登录；写操作限 admin/partner；身份取服务端用户。
  - 模板路径仅接受 UUID，阻断目录穿越。
  - 跑现有多准则附注与端点鉴权回归。

- [x] 2. 修复报表公式建议
  - `_upstream` 定义对象与 `_upstream_snapshot` 比较摘要分离。
  - 验证上游有公式、项目层为空时建议非空，保存层级判定不回归。

- [x] 3. 接通真实公式编辑器
  - `FormulaEditDialog` 接 `FormulaInput` 和统一语法校验，错误时禁保存。
  - 删除主弹窗不可达行内编辑模板和参数选择器；既有编程式适配只委托统一保存链；删除零调用的孤儿 `FormulaParamPicker`。

- [x] 4. 读取错误诚实展示
  - 历史区增加错误态、重试与请求序号隔离。
  - TB 明细公式移除宽状态放行，失败走中文提示。

- [x] 5. 自动补公式 warnings 全链展示
  - `/fill-formulas`、`seed-all`、单种子重载、CLI 原样展示。
  - warnings 只作提示，不改变成功事务状态。

- [x] 6. 回归与浏览器验收
  - 删除公式管理宿主 `ThreeColumnLayout` 的重复 import，恢复 Vite 构建。
  - 定向后端/前端测试、ESLint、单区域 vue-tsc；候选新增红为 0。
  - 【测试】项目浏览器只读走查，console/page error 为 0。
  - 更新 INDEX / memory，单 commit，fetch 后用 `push_version.py` 推送。

## 实施验收记录（2026-11-01）

- 最终基线：`933023edc6b11f5d7af0b9cb1edeac767fd1e6b6`；干净候选树只含本 spec 的代码差异，逐文件 SHA-256 与主工作区一致。
- 后端：`test_report_formula_generator_guard.py` 10 passed；`TestCustomNoteTemplateService` 12 passed；ruff 0 error。独立 ASGI 探针验证匿名读 401、普通用户读 200/写 403、partner 写 200、服务端 actor 与路径穿越阻断；三入口 warnings 探针通过；7 组磁盘变异全部按预期红并逐字节恢复。
- 既有 `TestNoteTemplateAPI` 6 例与模板库 7 例在 fixture 建表前被 HEAD 既有 `attachment_versions.blob_id → asset_blobs` 缺表 FK 阻断；候选与主树同因，未把它们记为通过。
- 前端：核心与本轮临时行为探针 32 passed；孤儿组件/全页入口/编辑器选择器 46 passed、3 skipped；全公式目录首轮 614 passed / 2 failed / 3 skipped，其中历史回滚断言同步请求选项后单文件 9 passed，余 `consolFormulaWiring` 1 条所需接线在 HEAD 已不存在、属基线红；本批新增失败 0。ESLint 0 error（5 个既有 warning）。单区域 vue-tsc：HEAD 12 errors，候选 10 errors，`added=[]`、`resolved=2`。
- Vite production build 最终通过。首轮发现并修复 HEAD 既有的 `ThreeColumnLayout` 重复导入构建阻断。
- 独立 Playwright 临时页验证：真实 `FormulaInput`、初始非法公式即时红线与中文原因、保存禁用、历史 503 显式错误与重试；`consoleErrors=0`、`pageErrors=0`。证据：`tmp_formula_manager_direct/browser/formula-residual-editor.png`、`formula-residual-history.png`。
- 共享服务当时未运行；磁盘 V249、共享库只读查询最高 V236。为避免未经授权执行 V237~V249，本轮没有启动 `start-dev.bat`，没有写共享库或真实项目。