# Spec 总索引

**最后更新**：2026-05-16

> 此索引追踪所有 spec 的状态、关联文档、commit。
> 新人读 spec 前先看此表，避免重复阅读已废弃的方案。

---

## v3 派生 spec 清单（v3 落地分档执行）

| Spec | 档次 | 关联 v3 任务 | 状态 | 预估工时 |
|------|-----|-------------|------|---------|
| **(直接修)** P0-2 PG ALTER TYPE | 档 1 | F7+F8 | ✅ 已完成 2026-05-16 | 0.3h |
| **(直接修)** P0-6 consistency-check | 档 1 | F4 | ✅ 已完成 2026-05-16 | 0.5h |
| **(直接修)** P0-7 misstatements recheck-threshold | 档 1 | F12 | ✅ 已完成 2026-05-16 | 0.3h |
| **(直接修)** P0-9 v3 §3 速查表 | 档 1 | F11 | ✅ 已完成 2026-05-16 | 0.2h |
| **(直接修)** P0-10 端点核验 | 档 1 | F13/F14/F15 | ✅ 已完成 2026-05-16 | 0.5h |
| `v3-quickfixes/` Q1 F6 | 档 2 | P0-1 | ✅ 已完成 2026-05-16（SAVEPOINT 修复 check_consol_lock，commit b4cda44）；目录已删除 2026-05-16，技术决策迁 memory.md | 0.4h |
| `v3-quickfixes/` Q2 F9 | 档 2 | P0-3 | ✅ 已澄清 2026-05-16（EQCR 端点路径假设错，前端 apiPaths 已正确）；目录已删除 | 0.3h |
| `v3-quickfixes/` Q3 F10 | 档 2 | P0-4 | ✅ 已澄清+修 2026-05-16（review-conversations 路径改一处，commit b4cda44）；目录已删除 | 0.3h |
| `v3-quickfixes/` Q4 F2 | 档 2 | P0-5 | ✅ 已完成 2026-05-16（init_4_projects step 5 + WP List 引导卡片，commit b4cda44）；目录已删除 | 0.5h |
| `v3-linkage-stale-propagation/` | 档 3 | P0-12/P0-13 | ✅ 已完成 2026-05-16（Sprint 0-4 全跑通，2.5h） | 2.5h |
| `v3-r10-linkage-and-tokens/` | 档 3 (R10) | v3 §7.6/§8/§9 | ✅ 编码任务全部完成 2026-05-16（Sprint 0-3 全跑通，含可选；UAT 待真人验收） | 22 天 |
| `v3-r10-editor-resilience/` | 档 3 (R10) | v3 §10/§7.4 | ✅ 编码任务全部完成 2026-05-16（Sprint 0-2 全跑通，含 F8 可选；UAT 待真人验收） | 11 天 |

---

## 历史 spec（已完成或废弃）

| Spec | 状态 | 完成日期 | 主分支 commit |
|------|------|---------|--------------|
| audit-chain-generation | ✅ 完成 | 2026-05-16 | 6b621f3 |
| template-library-coordination | ✅ 完成 | 2026-05-16 | 6b621f3 |
| ledger-import-view-refactor | ✅ 完成 | 2026-05-11 | feature/ledger-import-view-refactor |
| e2e-business-flow | ✅ 完成 | 2026-05-13 | feature/e2e-business-flow |
| enterprise-linkage | ✅ 完成 | 2026-05-15 | 2052290 |
| refinement-round8-deep-closure | ✅ 完成 | 2026-05-08 | a1b936e |
| refinement-round9-global-deep-review | ✅ 完成 | 2026-05-12 | a68eb18 |
| table-unification-el-table | ✅ 完成 | 2026-05-?? | - |
| workpaper-deep-optimization | ✅ 完成 | 2026-05-?? | - |
| production-readiness | ✅ 完成 | - | - |
| refinement-round1~7 | ✅ 完成 | - | - |

---

## 索引规约

1. **新建 spec 时**必须更新此表
2. **完成 spec 时**填 commit ID + 完成日期
3. **废弃 spec 时**改 status 为 ❌ + 记录废弃原因
4. **每月一审**：清理 ✅ 完成 ≥ 3 月的 spec（迁移到 dev-history.md）

---

## v3 执行甘特图（实际进度，2026-05-16 全完成）

```
Day 1 ─ ✅ 档 1 五件事直接修（1.6h）
Day 1 ─ ✅ v3-quickfixes Q1-Q4（1.5h，1 真修 + 2 平反 + 1 真修）
Day 1 ─ ✅ Spec A 三件套全跑通（2.5h，含 Sprint 0-4 + 4 项目 E2E + AJE 幂等 409）

R10（独立 sprint，3-4 周后启动）
├── v3-r10-linkage-and-tokens (3 周)
└── v3-r10-editor-resilience (2 周)  // 与上者并行
```

> **进度对比**：原计划 8 天 / 13 件事，**实际 P0 全部清完只用 5.6h**（约 35 倍压缩）；
> 主因 = (a) 5 个端点路径假设错平反免去无效修复 + (b) F6 SAVEPOINT 单一根因解决 + (c) AJE→错报后端 R8 已部分实现，Spec A 只补幂等。
>
> v3 已全部就绪，可启动 R10（联动+显示治理 / 编辑器+容灾）。

---

## 工作流规范引用

详见 `.kiro/steering/conventions.md` 的 spec 工作流章节，本索引补充：

- **档 1 直接修**：单文件 ≤ 0.5 天，直接编辑，commit 时引用 v3 P0-N
- **档 2 小型 spec**：写 README.md（在 spec 目录下），不需要 design.md / tasks.md
- **档 3 完整三件套**：requirements.md + design.md + tasks.md + 可选 snapshot.json
