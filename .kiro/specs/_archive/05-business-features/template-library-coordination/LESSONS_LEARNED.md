# 实施经验教训 — template-library-coordination

记录 spec 实施过程中暴露的流程问题、踩坑、修订过程。**非技术债**——这是历史事故记录，目的是让下一个 spec 不再犯同样错误。技术债登记在 `tasks.md` 的"已知缺口与技术债"章节。

---

## 事故 1：spec 创建期混入实施代码（2026-05-16）

**现象**：Sprint 0 verifier 跑出来发现 `template_library_mgmt.py` 913 行 / WorkpaperWorkbench 树形改造 / 4 个 Tab 组件 / Alembic 迁移**全部已经存在**——这些是在生成三件套 design.md / tasks.md 时一并写入的，并非 Sprint 实施阶段产出。

**后果**：
- Sprint 1-4 大部分 task 标 [x] 时只是"验证文件存在"而非"实施完成"
- 复盘时分不清边界——哪些是预先实施、哪些是 Sprint 实际推进
- task 粒度变得不可信

**根因**：spec 三件套阶段没有"代码 freeze"边界约束；orchestrator 在生成 design.md 时顺手写了实施代码。

**预防措施（写入 memory.md）**：
- spec 三件套阶段禁止动 production 代码
- design.md 想写代码骨架时放到独立"代码骨架示例"区块加注释"非实施"
- 实施 freeze 后才进入 Sprint 1

---

## 事故 2：spec 假设错位 5 处靠 Sprint 0 兜底而非创建时排查

**现象**：Sprint 0 verifier 才发现 5 处 spec 假设错位：
1. `accounting_standards_seed.json` / `template_sets_seed.json` 不存在（spec 假设存在）
2. `_DICTS` 硬编码在 `system_dicts.py`，不是 DB 表 → Task 6.3 整个降级为 405 stub
3. §43-§53 已被 audit-chain-generation 占用（spec 第一版以为 §43 起空闲）
4. `WpTemplateMetadata.subtable_codes` 字段不存在（D14 显式排除是 grep 后才加的）
5. CustomQuery.vue 不存在（spec 旧版以为已有）

**后果**：Task 6.3 整体降级为 405 stub，需求 21.3-21.5 无法兑现；Alembic 链路终点引用错误。

**根因**：spec 创建阶段没有强制"假设清单 grep 核验"步骤；ORM 字段、seed JSON、路由编号、前端文件、DB 表 5 类假设全凭印象。

**预防措施（写入 memory.md）**：spec 创建时强制 grep 核验 5 项：
1. ORM 字段 → `class XxxModel` 文件
2. seed JSON → `Test-Path backend/data/xxx.json`
3. 路由 §N → `router_registry.py` 当前编号占用
4. "前端已有 X.vue" → fileSearch 实测
5. DB 表/列 → grep models 文件确认

---

## 事故 3：9 个 PBT 全跳过未追责

**现象**：design.md 列了 17 条 Property，对应 9 个 PBT task（1.7-1.13、2.4、3.3、3.5、4.6、4.6b、5.3、5.4）**全部以可选标记 `[ ]*` 跳过**。集成测试间接覆盖了 Property 6/9/16/17 共 4 条，剩余 13 条 Property 无任何自动化校验。

**根因**：`[ ]*` 标记没有对应"接受测试缺口理由"的显式声明；orchestrator 默认全跳过赶进度。

**预防措施（写入 memory.md）**：
- PBT 区分 P0 / 可选两档
- P0 = authz / readonly enforcement / 数据正确性 — 不允许跳过
- `[ ]*` 必须在 design.md 显式写"接受测试缺口的理由"

---

## 事故 4：N_* 数字散落 narrative 区域

**现象**：requirements.md / design.md 中 `N_files=476 / N_primary=179 / N_account_mappings=206` 等快照值散落在十几处 narrative 文本里。修订到 v5 才完成 13 处硬编码清零，期间反复返工。

**根因**：spec 创建时未把数字快照独立成单一真源；narrative 引用快照值与 task 实施引用值混杂。

**修复（已落地）**：
- 创建 `.kiro/specs/template-library-coordination/snapshot.json` 作为单一真源
- 通用工具 `backend/scripts/verify_spec_facts.py` 加载 snapshot.json 自动核验
- 新 spec 创建时只需建对应 snapshot.json 即可复用

---

## 事故 5：TD 章节成为 task 退回避难所（二轮复盘 2026-05-16 修订）

**现象**：第一轮复盘新建"已知缺口与技术债"章节后，把 TD-3（usage-count 未真实数据验证）、TD-4（GtCoding CRUD 真实性未核）、TD-5（多文件占位）、TD-6（UUID 占位）等都登记为 TD，**但对应 task 仍标 [x]**。结果 tasks.md 出现"task 区已完成 + TD 区已知不完整"两套并行账目。

**根因**：TD 章节边界不清，混杂了三类不同性质的项：
1. 真技术债（实施完成但留有可识别局限）
2. 未完成的 task（占位实现 / 未真实数据验证）
3. 历史事故（如本文件其他事故）

**修复（已落地）**：
- TD 章节边界明确：只放第 1 类
- 第 2 类：`[x]` → `[ ]` 退回未完成（Task 6.2 / 6.3）
- 第 3 类：迁移到本文件 LESSONS_LEARNED.md
- 章节顶部加"边界说明"块明确收纳规则
