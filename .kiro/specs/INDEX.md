# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-07-19
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active 0 / Archived 409 = 总计 409
**最高迁移**：**V119**（以 `migration_status` 实测为准）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs（0个）

| Spec | 说明 | 状态 |
|------|------|------|
| (无) | | |

---

## 二、已归档 Spec（408个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          1
├── 04-infra-architecture/            34
├── 05-business-features/            187  (+2: workhour-entry-frontend, workhour-table-unification)
├── 06-engineering-governance/        12
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/               7
├── 09-consolidation-phases/           4
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        10
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     4
```

### 最近归档（2026-07-19，工时模块重构）

**→ 05-business-features（+2）**

| Spec | 任务 | 说明 |
|------|------|------|
| workhour-entry-frontend | 6/6 | Phase7 细粒度工时填报前端入口（Dialog+List+ProjectView+路由） |
| workhour-table-unification | 8/8 | 两套工时表统一迁移（V117 数据迁移+审批改造+兼容层+WeeklyTimesheet 改写） |

### 上次归档（2026-07-18，26个 spec）

**→ 04-infra-architecture（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| acnr | 76/76 | ACNR 地址坐标名称库（五层模型+resolver+grammar） |
| acnr-consumer-wiring | 100/100 | ACNR 消费者接入（P1-P15全实现） |
| acnr-runtime-convergence | 25/25 | ACNR 运行时闭环修复（Phase1+2，509测试） |
| formula-runtime-convergence | 18/18 | 公式运行时真实写入/回滚/并发收敛 |
| platform-global-hardening | 79/79 | 全局工程治理（displayPrefs/GtWorkpaperShell/CI守卫） |

**→ 05-business-features（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| confirmation-alternative-factory-convergence | 13/13 | 函证 alternative 八套收敛为工厂（-47%代码） |
| d5-enhancement-polish | 15/15 | D5 应收账款底稿精美化打磨 |
| d6-enhancement-polish | 17/17 | D6 合同资产底稿增强打磨（列设置/勾稽/AI/结论模板） |
| d7-enhancement-polish | 15/15 | D7 合同负债底稿增强打磨（列设置/TB勾稽/公允判断） |
| procedure-delegation-notification | 17/17 | 程序委派通知机制 |

**→ 06-engineering-governance（+6）**

| Spec | 任务 | 说明 |
|------|------|------|
| procedure-delegation-visibility-isolation | 18/18 | 服务端 fail-closed 底稿可见性隔离（V113） |
| visibility-isolation-go-live-hardening | 8/8 | 可见性隔离上线加固（Go_Live_Gate=LIVE） |
| workpaper-maintainability-convergence | 37/37 | 底稿可维护性收敛（GtWpRenderer 465能力槽位） |
| workpaper-maintainability-convergence-followup | 36/36 | 可维护性收敛后续（FormData工厂化） |
| version-trail-full-coverage | 38/38 | 版本链全覆盖（89个D~N主入口+CI守卫） |
| ui-pattern-unification | 18/18 | UI模式统一（抽凭dialog-mode+版本链Toolbar） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
