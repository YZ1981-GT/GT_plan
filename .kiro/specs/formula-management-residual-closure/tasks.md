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
## 推送与基线归因（2026-11-01）

- 推送：单 commit `84be89d2d55c8c70e0a2c3c8a12922ab59a4fbea`（22 文件 +449 −340），标签 `v1.0.92`（附注标签 `d266635`）。`git ls-remote` 核对远端 `spec/disclosure-note-doc-upload-and-batch-fill` 与本地 HEAD 同值。pre-commit 三门（gitleaks / 行数 / UTF-8）与 pre-push 版本门全过。
- 远端在本轮回归期间推进两次，各自逐路径确认重叠面后变基，而非整文件拷贝：`4390aaaa3` → `e4755bc7b`（66 文件，与本批仅 `INDEX.md` 重叠）→ `93402de37`（只改 `memory.md`，与本批重叠）。
- `memory.md` 的 300 行上限处置：远端 `93402de37` 已把该文件填到 299 行，本批原占 3 行即超限。git 三方合并的自动结果是删掉文件头 3 个空行（含 `## 用户偏好` 标题前的空行）来凑数——那是改他人刚推的格式，且标题前无空行在部分 markdown 解析器下不被识别为标题。改为沿用文件内既有写法（`### 标题（进度）—— 正文` 同一行），以远端版为底插入 1 行，最终 300 行、BOM 保留、远端 299 行逐行零缺失。
- 暂存树自洽门：首跑报 `Filename too long`，根因是 `check_staged_tree_self_consistency.py` 用 `tempfile.mkdtemp()` 落在 `C:\Users\<用户>\AppData\Local\Temp\`（前缀 46 字符），与仓库最长已跟踪路径 209 字符相加超 Windows 260 限制。现算后改用仓库根短目录（预算：父目录 ≤25 字符）重跑，**真正跑满**：物化 26152 文件、2 道门 exit 0、无非预期 SKIP。
- 预存失败归因（本批新增 0）：`test_multi_standard_notes.py` 的 `1 failed + 6 errors` 在**基线 worktree**（远端头 `e4755bc7b`，不含本批）复跑后逐节点完全一致（`1 failed, 62 passed, 6 errors`）。失败 `test_all_cycle_prefixes_present` 是 `Missing cycle prefix: Q`（读 `gt_coding_service` 与 `gt_template_library.json`，两者不在本批 diff 内）；6 个 error 是 fixture 建表阶段 `attachment_versions.blob_id` 外键找不到 `asset_blobs`。
- 行数门全仓模式报 73 个超限/膨胀，经逐条核对本批 22 文件无一在列；pre-commit 的暂存文件模式（权威判据）通过。
- 主工作区处置：**未强行前移分支 ref**。现算依据——`git merge --ff-only` 被拒（HEAD 未变、无破坏）；强行前移需更新 276 个文件，且会把并发会话正在改的 `backend/app/routers/adjustment_import.py`（远端 `e4755bc7b` 也改过）变成「反向脏」，并可能破坏并发会话**已暂存**的 6 组迁移重命名（V233/V235/V236 → V250/V251/V252）。改为只消除回退风险：本批 22 路径已逐一对齐推送版（`git diff` 规范化口径现算，残余差异仅 `components.d.ts`）。
- `components.d.ts` 刻意取主工作区那一侧：它相对主 HEAD 是 10 insertions + 1 deletion，1 个删除正是本批的 `FormulaParamPicker`（已生效），10 个新增是并发会话的新组件（`AdjustmentCentralStatusTag` / `ConsolReadinessBar` / `DshPanelLoadError` / `ReportProvenanceTooltip` 等）。推送版基线更旧、不含这 10 条，写入会吞掉他人改动——按铁律「生成文件不取并集：取一侧或让生成器重建」取更新的那一侧。
- 比对口径教训：首版对齐探针用裸 SHA-256 比工作树与 blob，18 个文件**全报 DIFF**，实为工作树 CRLF 与 blob LF 的规范化差异。改用 `git hash-object --path` / `git diff` 的 git 自身口径后，16 个代码文件其实早已逐字节一致、真正需要对齐的只有 2 个。
