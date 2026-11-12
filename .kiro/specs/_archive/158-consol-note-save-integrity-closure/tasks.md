# 合并附注保存完整性收口 — 任务

需求 `requirements.md` R1~R5；设计 `design.md`。按交付单元分批，每批独立可验证。验证一律在「最新 HEAD + 本 spec 改动」的干净分离头 worktree（仓库根 `tmp_consol_note_save/verify_wt`）上跑；连 PG 的用例显式设 `DATABASE_URL` 指向一次性库，不写共享库。

- [x] 1. 保护元数据解析单一来源（R3；design §4）
  - [x] 1.1 新建 `backend/app/services/consol_note_protection.py`：`parse_manual_cells` / `parse_locked_cells` / `section_locked` / `protected_cells` 与 `ProtectionMetadataError`（严格模式，中文消息指出第几项）
  - [x] 1.2 明细映射、按公式填入、子树重新汇总、前 N 名重排改用该模块；删除 `_parse_manual_cells` / `_parse_locked_cells` / `_manual_cells` 与公式路径内联锁定格解析；`remap_protected` 改为分别取 manual / locked 集合
  - [x] 1.3 坏元数据的失败通道：明细映射 `ApplyError(422, "PROTECTED_CELLS_INVALID")`、公式 `NoteFormulaError(status=422)`、汇总与前 N 名走章节级失败回报，`apply_topn_refresh` HTTP 入口 422
  - [x] 1.4 测试：`backend/tests/services/test_consol_note_protection.py`（三种合法写法、各类坏项、空值、四写入方坏元数据零写入且有原因）；既有 detail_apply / subtree_reaggregate / topn / formulas 回归，合法元数据下「保留手工格」计数逐值不变
  - [x] 1.5 变异：四个写入方各改回「跳过坏项」一条，须红在坏元数据用例上
  - [x] 1.6 自定义查询单格回写标手工格（R3.6；design §4.1）：数组行第 1 列起追加 `manual_cells`、严格解析已有标记、第 0 列 / 字典行不标并回执说明、回执加 `marked_manual`
  - [x] 1.7 测试 `backend/tests/test_custom_query_note_writeback_manual.py`：回写后再「按公式填入」回写值保留（调生产函数，不在测试里重写流程）；变异：去掉追加标记，须红在该用例

- [x] 2. 保存失败如实报错（R1；design §3.2）
  - [x] 2.1 `save_note_data` 的 `except Exception` 改为记日志 + 500 `CONSOL_NOTE_SAVE_FAILED`（中文通用文案，不带原始异常文本）；已知错误状态码不变
  - [x] 2.2 前端批量导入逐章节 try/catch，汇总成功数 / 失败项（Sheet、章节、原因），全失败不弹成功
  - [x] 2.3 测试：路由注入写库异常得 500 且响应不含原始异常文本；423 / 作用域错误不变；vitest 导入部分失败与全失败、保存 PUT 遇 500 不被自动重试
  - [x] 2.4 变异：500 分支改回 200；导入失败仍计成功

- [x] 3. 保存内容摘要 CAS（R2；design §3）
  - [x] 3.1 `consol_node_scope.py`：`digest_of`、`NoteSaveConflict`、`save_scoped_note_record(..., expected_digest=_UNCHECKED)`（基准行同 GET、撞唯一键赢家再比较、赢家路径补来源投影 `manual`）
  - [x] 3.2 路由：GET 回 `data_digest`；PUT 校验 `expected_digest` / `force_overwrite` 二选一（428 / 422 / 409）并回写入后摘要；`fill-by-formula` 回 `data_digest`
  - [x] 3.3 测试：服务层用例（设计 §7 第 1 行全部情形）；新 `backend/tests/test_consol_note_save_cas.py` 走真实依赖链；`test_consol_task15_p0p2_http_orm.py` 改带 `force_overwrite`
  - [x] 3.4 变异：去掉摘要比较；改用 `updated_at` 比较；赢家路径不比较；缺令牌放行

- [x] 4. 前端接入 CAS（R2.8；design §3、§8）
  - [x] 4.1 新建 `components/consolidation/composables/consolNoteSaveConflict.ts`：冲突 / 缺令牌判定与冲突信息提取（纯函数）
  - [x] 4.2 `ConsolNoteTab.vue`：加载、重读、保存成功、按公式填入（单章与全部）采用数据时记录 `dataDigest`；保存带 `expected_digest`；导入带 `force_overwrite: true`
  - [x] 4.3 409：保留脏标记与草稿，弹窗显示最近写入方与时间，「重新加载」走 `reloadCurrentSectionAfterRefresh`，「保留本地修改」不动状态；先保存再执行的动作遇冲突中止并说明
  - [x] 4.4 vitest：设计 §7 前端行全部情形；纯函数单测
  - [x] 4.5 变异：不带 `expected_digest`；409 分支清脏标记；按公式填入后不更新摘要（下一次保存应得 409）

- [x] 5. 写入方登记与守卫（R4；design §5）
  - [x] 5.1 新建 `backend/app/services/consol_note_writers.py`：按扫描结果登记全部入口与角色，排除项写理由；自定义查询单格回写登记为 `manual`
  - [x] 5.2 新建 `backend/tests/test_consol_note_writers_guard.py`：四种形态观测、登记与观测双向一致、`automatic` 必须引用 `protected_cells` / `section_locked`
  - [x] 5.3 守卫内置变异：临时源码新增未登记写入方、删掉保护引用，各须打红

- [x] 6. 回归与门禁
  - [x] 6.1 后端：本 spec 新增与改动的测试 + 合并附注相关既有测试（`backend/tests/services/test_consol_note_*.py`、`backend/tests/test_consol_note_*.py`、`test_consol_node_scope.py`）；失败项与干净 HEAD 逐节点比对，新增失败 0
  - [x] 6.2 前端：`ConsolNoteTab.spec.ts`、`consolNoteView.spec.ts` 等合并附注相关 vitest；改动文件区域 vue-tsc 相对 HEAD 新增 0
  - [x] 6.3 行数门、暂存树自洽检查（`backend/scripts/check/check_staged_tree_self_consistency.py`）通过

- [x] 7. 浏览器实测（R5.1）
  - [x] 7.1 【测试】合并项目两标签页并发编辑同章节：后保存方得冲突弹窗、本地编辑保留；两个按钮行为符合设计
  - [x] 7.2 用 `initScript` 拦截改响应实测保存 500 与导入部分失败提示；同时在 `http://192.168.20.60:3030` 再测一次冲突弹窗
  - [x] 7.3 写入内容恢复原值并对账（实测前备份该章节 `data` 与摘要，实测后摘要一致）

- [x] 8. 收尾
  - [x] 8.1 review 文档 §0.5 / §10 标注已落地项；design §6 待确认项交用户
  - [x] 8.2 在 `.kiro/specs/INDEX.md` 登记本 spec（基于最新 HEAD 副本只加本行，CRLF 与表格列数校验）
