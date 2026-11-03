# 任务：AI 待确认列表的目标标签修复

- [x] 1. 后端：`_parse_target` / `_enrich_target_labels` 改 ORM 分类查询、分保存点、项目限定、`wp_index.id` 兜底、`target_position`；
  SQLite 用例 + PG 用例（需求 1~5、7）
- [x] 2. 前端：横幅显示标签与位置、无标签回退原始 `target_cell`；采纳成功发 `ai-content:adopted`、横幅订阅 / 取消订阅；
  复制按钮；组件与 composable 用例（需求 6、8、9）
- [x] 3. 验证：变异、PG 守卫、裸 SQL 守卫口径（需求 10）、既有用例回归、单区域 vue-tsc
  - 后端变异 9 条（含阴性对照）全按预期：SQLite / PG 两侧逐条判定，恢复后 sha256 一致；裸 SQL 守卫变异 4 条全按预期
  - PG：`test_ai_content_pending_labels_pg.py` + `test_raw_sql_unqualified_column_contract.py` + `test_raw_sql_schema_contract.py`
    13 passed（后两者在 HEAD 上各红 1 例，本轮转绿）
  - 后端回归 104 passed（ai_content 四个用例文件、函数全局名棘轮、lazy import、端点鉴权基线、路由挂载、裸 SQL 守卫）
  - 前端 7 个 spec 与 HEAD 逐用例对比：新增失败 0；HEAD 红、本轮绿 1（横幅监听采纳事件）；两边同红 8（全在
    `ChatAdoptNoteTarget.spec.ts`，原因见 design「范围外」）；前端变异 9 条全按预期
  - 单区域 vue-tsc：本轮 4 条 / HEAD 6 条，新增 0（余 4 条为 `findLastIndex` lib 与 `apiProxy.ts` 既有）；注入 TS2322 命中横幅文件
- [x] 4. 实测：主工作区同步修复后调真实端点看标签；浏览器看横幅
  - 【测试】公式同步甲有限公司_2025 临时插 4 条待确认（底稿 id / 索引 id / 附注带位置 / 附注不带位置）：修复前真实后端 4 条
    `target_label` 全 null、无 `target_position`；`ai_content.py` 镜像进主工作区热重载后 4 条依次为「D2 应收账款审定表 · E5」
    「E1 底稿E1」「五、1 货币资金 · 正文第一段」「五、2 交易性金融资产」
  - worktree 前端另起 3031（代理共享后端）+ 自起无头浏览器：调整分录页横幅 4 段 → 明细卡片显示来源 · 标签 · 位置、元信息无 UUID、
    每张卡有「📋 复制」、控制台 0 错误；只读走查，未点确认 / 修订 / 拒绝
  - 4 条探针行已删，全库 `model='kiro-label-probe'` 剩 0；3031 已停
- [x] 5. 收尾：INDEX 登记、memory / dev-history 更新，随本 spec 代码单一提交带版本号推送
