# 合并附注保存完整性收口 — 需求

## 背景

来源：`docs/proposals/consolidation-three-code-tree-and-formula-chain-review-2026-11-10.md`（v3，§0.5 勘误后的 P0-1 / P0-2 / P0-3）。立项前已按 HEAD `39777a020` 现读生产代码与共享库，结论如下（design §1 给出逐条落点）：

- 合并附注手工保存端点 `PUT /api/consol-note-sections/data/{project_id}/{year}/{section_id}` 遇到非 `HTTPException` 的异常时回滚并返回 **HTTP 200 + `{"ok": false}`**。主保存路径前端会识别 `ok === false`；Excel 批量导入路径不识别，失败仍计入「已导入 N 个附注表格」。
- 保存没有任何并发控制：服务端行锁之后直接整份替换 `data`，两人同时编辑同一章节、或保存与「🔄 重新汇总 / 按公式填入 / 明细映射」交错时，后写者静默覆盖先写者；首次插入撞唯一键时也是后写者赢。
- 自动写入方（明细映射、按公式填入、子树重新汇总、前 N 名重排）都会保留人工格，但人工保护元数据有三份解析实现：两份遇到坏项静默丢弃（被丢弃的格随即被覆盖），一份抛错。合并附注写入方没有登记表，也没有守卫阻止新写入方漏掉保护。
- 自定义查询单格回写改了格值，却不把该格标为手工格，之后「按公式填入」会把回写值覆盖掉。目前前端没有入口发起附注回写（全仓前端无 `note_record_id`），只能经 API 调用，但端点已开放。
- 共享库现状（只读查询）：`consol_note_data` 3518 行，带 `manual_cells` 的 3 行共 5 项，全部为合法 `{row, col}`；`locked_cells` 非空 0 行；`cell_state ≠ 'auto'` 0 行。

## 术语

- **内容摘要**：对某行 `consol_note_data.data`（非对象时按 `{}`）做规范化 JSON 后的 SHA-256 十六进制串，与 `consol_note_source_projection.source_digest` 同算法。只覆盖 `data`，不覆盖 `is_stale`、`updated_at`、来源投影列。
- **保存基准行**：GET 读取时实际返回的那一行（节点专属行；根合并节点没有专属行时回退的项目级 legacy 行）。
- **人工保护格**：`data.manual_cells` 与 `consol_note_data.locked_cells` 列出的坐标，以及 `cell_state = 'locked'` 的整节。

## R1 保存失败如实报错

1. 保存端点遇到未预期异常时，回滚事务并返回 HTTP 500，`detail = {error_code: "CONSOL_NOTE_SAVE_FAILED", message: <中文>}`；响应不得携带数据库原始错误文本，原始异常写服务端日志（含项目、年度、章节、节点）。
2. 已知错误保持原状态码与中文原因：作用域错误（`NodeScopeError` 的 400 / 404 / 409）、合并锁定 423、请求体格式错误 400。
3. 保存端点不再返回 `{"ok": false}` 形式的失败；成功响应保持 `ok: true` 及原有字段。
4. 前端保存请求不得被全局 5xx 自动重试（现行规则：无幂等键的 PUT 不重试），本需求不改变该规则，并由测试钉住。
5. Excel 批量导入逐个章节提交；单个章节失败不中断其余章节；结束时提示成功数与失败数，失败项列出 Sheet 名、章节号与中文原因。全部失败时不得出现成功提示。

## R2 保存内容摘要 CAS

1. GET 附注数据响应新增 `data_digest`：有记录时为保存基准行的内容摘要，无记录时为 `null`。
2. PUT 请求体新增二选一字段：
   - `expected_digest`：64 位小写十六进制串，或 `null`（表示「我读到时还没有数据」）；
   - `force_overwrite: true`：明确放弃并发检查（仅供「Excel 批量导入」这类整表替换动作使用）。
   两者都没有时返回 428 `CONSOL_NOTE_DIGEST_REQUIRED`；两者同时给出、或 `expected_digest` 格式不合法时返回 422。
3. 服务端在锁住保存基准行之后、写入之前计算当前内容摘要并比较；不一致时不写入，返回 409 `CONSOL_NOTE_CONFLICT`，`detail` 含 `current_digest`、`updated_at`、`last_write_source`（`data._last_write_source`，无则 `manual`）与中文说明，不返回对方的数据内容。
4. 两个请求同时首次创建同一节点行、撞唯一约束时：带 `expected_digest` 的请求若期望值与赢家内容不一致，按 R2.3 返回 409；带 `force_overwrite` 的请求保持现行「重读赢家后写入」语义。
5. 仅 `is_stale`、`updated_at` 或来源投影列变化（推送标待更新、公式设置传播等）不改变内容摘要，不触发冲突。
6. 保存成功响应返回写入后的 `data_digest`；「按公式填入」端点响应同样返回写入后行的 `data_digest`，前端采用其 `data` 时一并采用摘要。
7. 冲突重读赢家路径与正常路径一致地把来源投影写成 `manual`（现行赢家路径漏写）。
8. 前端：
   - 每次采用服务端数据（加载、重新读取、保存成功、按公式填入回执）时记录该章节的 `data_digest`；
   - 保存时带 `expected_digest`；
   - 收到 409 时保留本地编辑、脏标记与自动保存草稿，弹窗说明最近写入方与时间，提供「重新加载（放弃本地修改）」与「保留本地修改」两个选项，任何情况下不自动覆盖；
   - 依赖「先保存再执行」的动作（按公式填入、全部按公式填入、刷新前保存）在保存冲突时中止并给出原因；
   - Excel 批量导入带 `force_overwrite: true`。

## R3 人工保护格解析单一来源

1. 新建唯一解析模块，提供：`manual_cells` 解析（接受 `{row, col}`、`[row, col]`、`"row:col"` 三种现行写法）、`locked_cells` 列解析（`{row_index, col_index}`）、整节锁定判断、合并后的保护坐标集合。
2. 解析为严格模式：坐标缺失、非整数、布尔值、负数、容器类型错误一律抛出 `ProtectionMetadataError`，消息中文并指出第几项。
3. 明细映射、按公式填入、子树重新汇总、前 N 名重排四个自动写入方全部改用该模块；删除 `consol_note_detail_apply_service._parse_manual_cells` / `_parse_locked_cells`、`consol_note_formula_service._manual_cells` 及公式路径内联的锁定格解析，不保留转发别名。
4. 保护元数据损坏时，该章节（该节点）不写入任何格，并按各写入方已有的逐章节失败通道回报中文原因；HTTP 直调入口返回 422。不得静默丢弃坏项后继续写入。
5. 行为对合法元数据不变：现有四个写入方的「保留手工格」计数与写入结果逐值一致。
6. 自定义查询单格回写（`custom_query.snapshot_writer_modules.write_note_cell`）视为人工录入，与 Excel 批量导入同一口径（导入时非空数值格已标手工）：
   - 目标行为数组行且列号 ≥ 1 时，写值的同时把 `{row, col}` 加入 `data.manual_cells`（已存在不重复），之后「按公式填入 / 重新汇总 / 明细映射」都保留该值；
   - 追加前用 R3.1 的严格解析读取已有标记，标记损坏时拒绝回写并返回中文原因，不覆盖、不丢弃坏项；
   - 第 0 列（项目名）与字典形态的行不标手工（共享库现有 3518 行全部是数组行），回执中注明「未标手工」及原因；
   - 回写成功回执增加 `marked_manual: true|false`。

## R4 合并附注写入方登记与守卫

1. 新建合并附注写入方登记表，逐条列出写 `consol_note_data.data` 的生产入口：`writer_id`、入口（`模块:限定名`）、触发说明、角色（`automatic` / `manual` / `structural`），以及只改状态列的入口（`stale`，单独登记）。
2. 守卫测试按 AST 扫描 `backend/app`：构造 `ConsolNoteData(...)`、调用 `update_source_projection(...)`、`sa.update(ConsolNoteData).values(data=...)`、原生 SQL 字面量 `UPDATE consol_note_data ... SET data` 的函数都必须在登记表或带理由的排除表中；登记表中没有对应观测的条目同样打红。
3. 角色为 `automatic` 的入口，函数体必须引用 R3 模块的保护集合函数（AST 名字引用，不按文本匹配）；未引用即打红。
4. 守卫自身配变异证明：临时新增一个未登记写入方、删掉一个自动写入方对保护函数的引用，两种情况都必须打红。

## R5 文档与验收

1. 在【测试】合并项目上浏览器实测：两个标签页编辑同一章节，后保存方收到冲突弹窗且本地编辑仍在；「重新加载」后看到先保存方的内容；「保留本地修改」不清脏标记。保存失败与批量导入部分失败用拦截请求改响应的方式实测提示。写入内容在实测后恢复并对账。
2. 范围外发现与本轮未做的建议回写到 review 文档或本 spec design §6，不悄悄扩大范围。

## 非目标

- 不做「整节锁定 / 锁定格」的设置入口（`cell_state` / `locked_cells` 现无写入方，是否开放属产品决策）。
- 不改单体附注 `WriteGate` 与其归属矩阵。
- 不做拖拽改上级 CAS、树版本结构化、`tree_kind`、Excel 前导零、headless 后台化（review 文档 §10 其余条目）。
- 不新增数据库列与迁移。
