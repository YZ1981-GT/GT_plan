# Implementation Plan

## Overview

两条主线：**横向补齐**缺入口的明细表四表库取数入口 + **纵向收敛**把两套 aux 归集实现合成共享件 `aggregate_aux_by_name_ex`。任务按 6 个 wave 推进（见 Task Dependency Graph）；下方复选框为唯一进度真源。

## Tasks

- [x] 1. 缺口清册（结构性推导，禁 grep 按钮文字）
  - 从 `htmlRendererRegistry` + `RENDERER_DISPATCH` / render-config / `wp_code_overrides.json` 推导已挂载宿主全集
  - 逐宿主判"具备四表库取数能力"三元组：科目码可解析 + 真库有对应四表数据 + 存在可承载行结构（store item_id + 字段）
  - 产出五列清册（wp_code / 宿主 / store item_id / 现有入口三态 / gap 类型 G-A~G-D）落 spec evidence，作为后续唯一真源
  - 核实 DEC-2：`D2TabDetail` 的 `importFromAuxBalance(projectId)` 实际打哪个端点（覆盖 JSON 里无 `d2/import-aux-balance`）
  - 登记 G-D（不适合取数）的理由，宁缺勿造
  - 产出清册 source digest，并规定后续任务必须校验 registry/render-config 快照未漂移；漂移时阻塞（Requirement 1.6）
  - 逐循环核定统一来源元数据是否可承载；不能承载的条目标为 blocked/deferred，不计入完成数（Requirement 5.4）
  - 核 DEC-2：D2 的 `importFromAuxBalance(projectId)` 实际打哪个端点，归入 G-C 或 G-B
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 5.4_

- [x] 2. 红基线核实与注释纠偏
  - 实测 D3/D5/D6/D7 端点当前是否真 500（读 SQL 列 vs `tb_aux_balance` schema，必要时真库跑一次）
  - 结论写入 spec evidence；确认「`period_type`/`balance` 必 500」已过期后，修正 `four_table/aux_aggregation.py` docstring + G7/K1/D1 注释里的该表述，改写为真实缺陷 ①②③④
  - 🔴 只改理由表述，不放宽"禁止照抄历史版本"的结论（结论仍成立，只是理由不同）
  - _Requirements: 2.1, 2.2_

- [x] 3. 共享件增强：reason 码 + ERROR 日志（fail-open 治理）
  - `aggregate_aux_by_name_ex(...) -> AuxAggregationResult`（entries / aux_type / total_units / reason）
  - 异常路径 `logger.exception` 记 ERROR 并带 project/year/前缀；`no_rows` 路径不记 ERROR
  - 旧 `aggregate_aux_by_name` 改薄壳，返回三元组逐字段不变（既有 4 消费者零改动，须有守卫断言）
  - 单测覆盖四个 reason 分支 + Property 6（ERROR 与 no_rows 不可混淆）
  - _Requirements: 5.1, 5.2_

- [x] 4. 历史端点迁移（G-C：D3/D5/D6/D7）
  - 四家改调共享件，删各自裸 SQL（含 `d_cycle_extraction/detail_aggregation.py` 的 `_D6_AUX_SQL` / `_AUX_QUERY`）
  - 科目前缀改由报表映射解析，兜底常量保留但注明 `source_ref`（DEC-3）
  - 账龄字段留空，不再把全额塞 `within1`；返回 message 提示需人工填账龄
  - 无四表来源的字段一律留空，禁止 0 / 上期值 / 全额塞首段（Requirement 5.3）
  - 迁移后 grep 自检：四文件必须能查到 `get_active_filter` / `pick_aux_type`（经共享件）真实调用链，旧裸 SQL 零残留
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 3.1, 3.5, 5.3_

- [x] 4.1 迁移前后金额对照（真库）
  - **必须先于 Task 4 执行并冻结**迁移前基线：同一 project/year/active dataset/account prefixes/selected aux_type，保存旧实现结果与输入快照 digest
  - Task 4 完成后用完全相同输入重算，落迁移后结果与差异解释；金额下降为整数倍须写明属 ① 数据集双算或 ② `aux_type` 双算的修正
  - dependency graph 中本任务不得与 Task 4 并行；Task 4 依赖本任务的 baseline artifact
  - _Requirements: 6.5_

- [x] 5. G-B 类新端点（照 K1 范式）
  - 按 Task 1 清册的 G-B 条目新增 `POST /api/workpapers/{wp_id}/{x}/import-aux-balance`
  - 一律调 `aggregate_aux_by_name_ex` + 各自纯函数行构建器；只写录入列（Property 4）
  - merge 语义：已有业务键不覆盖，`overwrite` 必须显式参数驱动（Property 3）
  - 🔴 若清册 G-B > 6 个，按 DEC-5 拆批次，每批 ≤3
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 6. 后端守卫 + 变异检验
  - 守卫断言三条铁律**行为**生效（active 过滤后金额不翻倍 / 结果只来自单一 `aux_type` / 前缀匹配命中子科目），非"函数存在"
  - 新增 `backend/scripts/diagnose/mutate_four_table_entry_guards.py`，锚点 ≥3：去 active filter · 去 `aux_type` 锁定 · merge→overwrite；四态判定，GREEN 即守卫缺陷
  - _Requirements: 6.1, 6.2_

- [x] 7. 前端入口补齐（G-A + G-B）
  - 明细表 toolbar 加「从余额表导入」（与 `+ 添加行` 同排，`:disabled="isReadonly"`，loading 防重复提交）；宿主已有「导入导出 ▾」则并入下拉（DEC-1）
  - K1 补手动入口（现仅 AutoSeed）；有 AutoSeed 的底稿保留 AutoSeed 并区分语义（Requirement 4.5）
  - 0 行按 reason 码给可辨别中文提示（无该科目辅助余额 / 未按维度挂账 / 数据集未激活 / 取数异常）
  - 成功后走宿主既有 reload，保证明细 → 审定表 → 附注级联刷新
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 8. 前端守卫（vitest）
  - 断言按钮存在 + `isReadonly` 禁用 + 点击真发请求到**字面量正确**的端点 URL（防接错循环）
  - 断言 reason → 提示文案映射覆盖全部分支
  - 变异：改错 URL 中的循环前缀必须打红（Property 7 的连接性）
  - _Requirements: 6.3, 4.4_

- [x] 9. 真栈实测（浏览器）
  - Playwright 选一张 G-A/G-B 底稿：0 行 → 点新按钮 → 行数 = 只读 SQL 查出的户数，抽 2 行金额逐字对齐
  - 再点一次验证 merge 不重复、不覆盖手工改过的行，并验证 reload 后明细 → 审定表 → 附注的下游值按同一业务 key 更新
  - 证据 JSON 必须记录 request/response reason、source_dataset_id、row source_kind、store item_id、下游值和 SQL 快照 digest
  - _Requirements: 6.4, 3.4, 4.6, 5.4_

- [x] 10. 收口
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记
  - `.kiro/specs/INDEX.md` 登记本 spec 状态；清册作为长期资产落 `docs/` 或 spec 目录
  - 清理 `tmp_*` / `_wip_*`
  - _Requirements: 1.5, 6.2_

## Tasks (Phase 2 — 账龄骨架与账龄枚举联动)

> 起因：用户复核指出账龄不能为空、须与账龄枚举（三年/五年/自定义）联动。核查确认四表库无账龄源、账龄由审计师手动录入；且 **K1 现状仍把余额整额塞首段（活体伪造，违红基线④/Property 5）**。本阶段修复伪造 + 让账龄骨架配置驱动、随枚举联动、切换时重映射不丢数据。Requirement 7 + 强化 2.5/Property 5。

- [x] 11. 修复 K1 账龄伪造 + 骨架改配置驱动（后端）
  - 删 `build_k1_detail_rows_from_aux` 的 `_aging()` 整额落首段（`bucket[first_key]=amount`）与 `["within1"]` 硬编码兜底
  - 改为 `_empty_aging(seg_keys)`（每段值=0）；`segments` 由 K1 端点 `await get_effective_segments(project_id, "K1", db)` 取得后传入，读取失败按 subject 默认 preset（FIVE_YEAR）兜底、不回退单段
  - message 仍提示「账龄留空，请按实际账龄人工填列」
  - _Requirements: 2.5, 7.1, 7.3, 7.6_

- [x] 12. D 循环账龄骨架审计与对齐（后端）
  - 核 D3/D5/D6/D7 迁移端点的行构建器：确认账龄字段已留空（非塞首段），并同样由端点读 `get_effective_segments(project_id, subject, db)` 生成骨架段键（subject 默认：D3/D5/D6/D7→THREE_YEAR），删任何硬编码段
  - 2-period 科目只生成 `agingPrior`/`agingAudited` 两组；3-period 科目三组（对齐 `useAgingConfig` 的 THREE_PERIOD_SUBJECTS）
  - _Requirements: 2.5, 7.1, 7.2, 7.3_

- [x] 13. 前端骨架同键 + 枚举切换重映射
  - 明细行 merge 后账龄段键与 `useAgingConfig` bands 同键；取数骨架经宿主 reload 后由 `useAgingConfig` 渲染当前枚举列
  - 项目切换账龄枚举（三年↔五年↔自定义）时调 `useAgingMigration.remapRowAgingData` 重映射已录账龄到新段，不丢/不错位；监听既有 `aging-config:changed` 事件
  - 审定表账龄汇总 / 附注账龄披露与骨架同一 `effective_segments` 真源，三处不各写一套
  - _Requirements: 7.2, 7.4, 7.5_

- [x] 14. 守卫 + 变异（后端 Property 5/8 + 前端）
  - 后端守卫：断言取数骨架 `sum(agingAudited)==0`（不塞首段，Property 5）、骨架键集逐项等于 `get_effective_segments` 返回（Property 8）；变异：把 `_empty_aging` 改回塞首段必红、把段键改成硬编码常量（改枚举不变）必红
  - 前端 vitest：三年/五年/自定义三种配置下骨架键集与 `useAgingConfig` bands 一致；`useAgingMigration` 重映射不丢已录值
  - _Requirements: 6.1, 6.2, 7.2, 7.4_

- [x] 15. 真栈实测 + 收口
  - Playwright：K1（或一张 3-period 底稿）取数 → 账龄各段值全空（非首段带数）；切项目账龄枚举三年↔五年 → 明细列与行骨架同步变、已录账龄段重映射保留；证据 JSON 记录段键集前后对照 + 某行手动录账龄后重取不被覆盖
  - `get_diagnostics` 校验三件套；`git status --porcelain` 核无 `??` 漏登记；清理 `tmp_*`/`_wip_*`
  - _Requirements: 6.4, 7.2, 7.4, 7.5_
  - ✅ 交付（Task 15 evidence `evidence/task15-aging-skeleton-realstack.json`）：真栈 K1 wp `6e6348d0`（重庆和平药房_2024，1221 有 3305 aux 行/1098 户）新取 400 行 —— **全 400 行 × 3 组 × 6 段 aging 值恒 0**（`max_abs_aging_value=0`、`any_segment_equals_balance=false`、`sum(agingAudited)==0`），message「账龄留空，请按实际账龄人工填列」，键集 = FIVE_YEAR（Property 5/8 实证）；某行手动录 `agingAudited.y2to3=4800` 后重取 `imported_count=0`、值不被覆盖、无重复（Requirement 3.4/7.4）；项目账龄枚举 FIVE_YEAR→THREE_YEAR（`PUT /api/projects/{id}/aging/config` 广播 `aging-config:changed`）后 `effective_segments` 6→4、K1-2 明细「账龄区段」列同步渲染为「1年以内/1-2年/2-3年/3年以上」、共享段 y2to3=4800 经 `useAgingMigration` 重映射保留（Requirement 7.2/7.4/7.5），测后已还原 FIVE_YEAR。三件套 `get_diagnostics` 全 clean；本 spec Phase 2 产物（5 守卫/测试 + 改动端点/服务 + 2 证据 + 三件套）已 `git add` 无 `??` 漏登记（未 commit）。**已知遗留（不在本 spec 修）**：THREE_YEAR 末段 `over3` 与 FIVE_YEAR `over5` 键不同 ⇒ 末段值在三↔五切换时会掉（PRESET_SEGMENTS 固有，非本 spec 缺陷）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "rationale": "纯只读：缺口清册与红基线核实。清册是全部后续任务的输入，红基线结论决定迁移理由表述" },
    { "wave": 2, "tasks": ["3"], "rationale": "共享件增强（reason + ERROR 日志）必须先于迁移与新端点，否则两批代码又要各自处理 fail-open" },
    { "wave": 3, "tasks": ["4.1"], "rationale": "先冻结四家历史实现的迁移前真库基线与输入 digest；没有基线不得开始迁移" },
    { "wave": 4, "tasks": ["4", "5"], "rationale": "历史端点迁移与 G-B 新端点都消费增强后的共享件；Task 4 必须消费 Task 4.1 的 frozen baseline，G-B 仍受 Task 1 清册 digest 约束" },
    { "wave": 5, "tasks": ["6", "7"], "rationale": "后端守卫与前端入口并行：守卫针对 Wave 4 的后端行为，前端入口依赖端点已可用" },
    { "wave": 6, "tasks": ["8", "9", "10"], "rationale": "前端守卫与真栈实测需要按钮已挂载；收口最后" },
    { "wave": 7, "tasks": ["11", "12"], "rationale": "Phase 2 后端：K1 修伪造 + D 循环账龄骨架改配置驱动（读 get_effective_segments），二者独立可并行" },
    { "wave": 8, "tasks": ["13", "14"], "rationale": "前端骨架同键+枚举切换重映射，与后端 Property 5/8 守卫+变异并行（守卫针对 wave 7 的后端行为）" },
    { "wave": 9, "tasks": ["15"], "rationale": "Phase 2 真栈实测（枚举切换联动）+ 收口，需前后端骨架已落地" }
  ],
  "blocking": {
    "1": "缺口清册未出或 source digest 与 registry/render-config 漂移 ⇒ Task 5 / Task 7 无输入，全部阻塞（Requirement 1.5/1.6）",
    "3": "共享件未带 reason 码 ⇒ Task 7 的可辨别提示（Requirement 4.4）无法实现",
    "4.1": "迁移前基线未冻结 ⇒ Task 4 不得开始；G-B 超过 6 个时必须拆为独立批次 gate"
  },
  "pending_decisions": {
    "DEC-1": "按钮摆法：倾向沿用平铺「从余额表导入」，仅在已有「导入导出 ▾」的宿主并入下拉",
    "DEC-2": "D2 实际端点归属，由 Task 1 核实后归入 G-C 或 G-B",
    "DEC-3": "无可证明报表映射时只能走有 source_ref 的声明式 fallback，否则 blocked",
    "DEC-5": "G-B > 6 个时按每批 ≤3 个拆成独立 release gate，不得以部分批次标记本 spec 全部完成"
  }
}
```

## Notes

交付实态与计划偏差（收口复盘）：

- **G-B = 0**：Task 1 结构性推导得 G-B 为空（D2 由 DEC-2 疑似 G-B 经核实归为 G-C），故 Task 5 为文档化 no-op（宁缺勿造，未编造端点）；DEC-5 拆批不触发。
- **D2 = G-C（带端点新建）**：D2 原走通用读端点 `/ledger/aux-balance-detail` + 客户端聚合，Task 4 新建 `POST /d2/import-aux-balance` 走共享件并删客户端聚合。
- **Task 4 父任务**：其唯一登记子任务 4.1（迁移前基线冻结）完成时被工具自动置完成，实际迁移实现另行补齐；进度以复选框为准。
- **K1 迁移到 `_ex`（收口阶段）**：K1 端点原用旧三元组薄壳 `aggregate_aux_by_name`（HTTP 无 `reason` 字段），收口时迁至 `aggregate_aux_by_name_ex` 并回传 `reason`/`selected_aux_type`，使 K1/D2/D3/D5/D6/D7 六端点统一（对齐 design Error Handling 契约）；配套 4 个 K1 端点测试 stub 同步改为返回 `AuxAggregationResult`。
- **来源元数据（Requirement 5.4 / DEC-4）**：不加统一 `source_kind`/`source_dataset_id` 列，改用行 `remark` 携带中文来源标记；统一列登记为 deferred 增强。
- **变异检验**：`backend/scripts/diagnose/mutate_four_table_entry_guards.py` 三锚点全 RED；前端 `fourTableAuxImportEntry.guard.spec.ts` 字面量 URL 连接性变异 RED 实证。
- **真栈实测**：Task 9 以 K1（canonical G-A）Playwright 实测 —— 503 户匹配、2 行金额逐字对齐、merge 幂等不覆盖手工编辑、明细→审定表→附注级联，证据 `evidence/task9-realstack-playwright.json`。
