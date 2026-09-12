# Implementation Plan

- [ ] 1. 缺口清册（结构性推导，禁 grep 按钮文字）
  - 从 `htmlRendererRegistry` + `RENDERER_DISPATCH` / render-config / `wp_code_overrides.json` 推导已挂载宿主全集
  - 逐宿主判"具备四表库取数能力"三元组：科目码可解析 + 真库有对应四表数据 + 存在可承载行结构（store item_id + 字段）
  - 产出五列清册（wp_code / 宿主 / store item_id / 现有入口三态 / gap 类型 G-A~G-D）落 spec evidence，作为后续唯一真源
  - 核实 DEC-2：`D2TabDetail` 的 `importFromAuxBalance(projectId)` 实际打哪个端点（覆盖 JSON 里无 `d2/import-aux-balance`）
  - 登记 G-D（不适合取数）的理由，宁缺勿造
  - 顺带核 DEC-4：逐循环记录"取数行是否已有可判来源的字段"，作为 Requirement 5.4 的可追溯性结论（多数已有则升级为本 spec 范围）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.4_

- [ ] 2. 红基线核实与注释纠偏
  - 实测 D3/D5/D6/D7 端点当前是否真 500（读 SQL 列 vs `tb_aux_balance` schema，必要时真库跑一次）
  - 结论写入 spec evidence；确认「`period_type`/`balance` 必 500」已过期后，修正 `four_table/aux_aggregation.py` docstring + G7/K1/D1 注释里的该表述，改写为真实缺陷 ①②③④
  - 🔴 只改理由表述，不放宽"禁止照抄历史版本"的结论（结论仍成立，只是理由不同）
  - _Requirements: 2.1, 2.2_

- [ ] 3. 共享件增强：reason 码 + ERROR 日志（fail-open 治理）
  - `aggregate_aux_by_name_ex(...) -> AuxAggregationResult`（entries / aux_type / total_units / reason）
  - 异常路径 `logger.exception` 记 ERROR 并带 project/year/前缀；`no_rows` 路径不记 ERROR
  - 旧 `aggregate_aux_by_name` 改薄壳，返回三元组逐字段不变（既有 4 消费者零改动，须有守卫断言）
  - 单测覆盖四个 reason 分支 + Property 6（ERROR 与 no_rows 不可混淆）
  - _Requirements: 5.1, 5.2_

- [ ] 4. 历史端点迁移（G-C：D3/D5/D6/D7）
  - 四家改调共享件，删各自裸 SQL（含 `d_cycle_extraction/detail_aggregation.py` 的 `_D6_AUX_SQL`）
  - 科目前缀改由报表映射解析，兜底常量保留但注明 `source_ref`（DEC-3）
  - 账龄字段留空，不再把全额塞 `within1`；返回 message 提示需人工填账龄
  - 无四表来源的字段一律留空，禁止 0 / 上期值 / 全额塞首段（Requirement 5.3）
  - 迁移后 grep 自检：四文件必须能查到 `get_active_filter` / `pick_aux_type`（经共享件）真实调用链，旧裸 SQL 零残留
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 3.1, 3.5, 5.3_

- [ ] 4.1 迁移前后金额对照（真库）
  - 对四家各跑迁移前/后归集，落对照表；金额下降为整数倍须写明属 ① 数据集双算 或 ② `aux_type` 双算 的修正
  - _Requirements: 6.5_

- [ ] 5. G-B 类新端点（照 K1 范式）
  - 按 Task 1 清册的 G-B 条目新增 `POST /api/workpapers/{wp_id}/{x}/import-aux-balance`
  - 一律调 `aggregate_aux_by_name_ex` + 各自纯函数行构建器；只写录入列（Property 4）
  - merge 语义：已有业务键不覆盖，`overwrite` 必须显式参数驱动（Property 3）
  - 🔴 若清册 G-B > 6 个，按 DEC-5 拆批次，每批 ≤3
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 6. 后端守卫 + 变异检验
  - 守卫断言三条铁律**行为**生效（active 过滤后金额不翻倍 / 结果只来自单一 `aux_type` / 前缀匹配命中子科目），非"函数存在"
  - 新增 `backend/scripts/diagnose/mutate_four_table_entry_guards.py`，锚点 ≥3：去 active filter · 去 `aux_type` 锁定 · merge→overwrite；四态判定，GREEN 即守卫缺陷
  - _Requirements: 6.1, 6.2_

- [ ] 7. 前端入口补齐（G-A + G-B）
  - 明细表 toolbar 加「从余额表导入」（与 `+ 添加行` 同排，`:disabled="isReadonly"`，loading 防重复提交）；宿主已有「导入导出 ▾」则并入下拉（DEC-1）
  - K1 补手动入口（现仅 AutoSeed）；有 AutoSeed 的底稿保留 AutoSeed 并区分语义（Requirement 4.5）
  - 0 行按 reason 码给可辨别中文提示（无该科目辅助余额 / 未按维度挂账 / 数据集未激活 / 取数异常）
  - 成功后走宿主既有 reload，保证明细 → 审定表 → 附注级联刷新
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 8. 前端守卫（vitest）
  - 断言按钮存在 + `isReadonly` 禁用 + 点击真发请求到**字面量正确**的端点 URL（防接错循环）
  - 断言 reason → 提示文案映射覆盖全部分支
  - 变异：改错 URL 中的循环前缀必须打红（Property 7 的连接性）
  - _Requirements: 6.3, 4.4_

- [ ] 9. 真栈实测（浏览器）
  - Playwright 选一张 G-A/G-B 底稿：0 行 → 点新按钮 → 行数 = 只读 SQL 查出的户数，抽 2 行金额逐字对齐
  - 再点一次验证 merge 不重复、不覆盖手工改过的行
  - 证据 JSON 落 spec evidence
  - _Requirements: 6.4, 3.4_

- [ ] 10. 收口
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记
  - `.kiro/specs/INDEX.md` 登记本 spec 状态；清册作为长期资产落 `docs/` 或 spec 目录
  - 清理 `tmp_*` / `_wip_*`
  - _Requirements: 1.5, 6.2_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "rationale": "纯只读：缺口清册与红基线核实。清册是全部后续任务的输入，红基线结论决定迁移理由表述" },
    { "wave": 2, "tasks": ["3"], "rationale": "共享件增强（reason + ERROR 日志）必须先于迁移与新端点，否则两批代码又要各自处理 fail-open" },
    { "wave": 3, "tasks": ["4", "4.1", "5"], "rationale": "历史端点迁移与 G-B 新端点都消费增强后的共享件；4.1 的金额对照紧随 4" },
    { "wave": 4, "tasks": ["6", "7"], "rationale": "后端守卫与前端入口并行：守卫针对 Wave 3 的后端行为，前端入口依赖端点已可用" },
    { "wave": 5, "tasks": ["8", "9", "10"], "rationale": "前端守卫与真栈实测需要按钮已挂载；收口最后" }
  ],
  "blocking": {
    "1": "缺口清册未出 ⇒ Task 5 / Task 7 无输入，全部阻塞（Requirement 1.5）",
    "3": "共享件未带 reason 码 ⇒ Task 7 的可辨别提示（Requirement 4.4）无法实现"
  },
  "pending_decisions": {
    "DEC-1": "按钮摆法：倾向沿用平铺「从余额表导入」，仅在已有「导入导出 ▾」的宿主并入下拉",
    "DEC-2": "D2 实际端点归属，由 Task 1 核实后归入 G-C 或 G-B",
    "DEC-4": "取数行统一 source 标记字段本 spec 暂不加，Task 1 若发现多数循环已有等效字段则升级为范围内",
    "DEC-5": "G-B > 6 个则拆批次交付，每批 ≤3"
  }
}
```
