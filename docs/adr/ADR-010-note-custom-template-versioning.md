# ADR-010: 自定义附注模板的版本化与回滚策略

**Status**: Accepted
**Date**: 2026-05-27
**Sprint**: disclosure-note-full-revamp / Sprint 4 Task 4.5

## 背景

附注模板分两层：

| 层 | 路径 | 职责 |
|---|------|------|
| 基线模板 | `backend/data/note_template_{soe,listed}.json` | 致同标准版（173 章节，全公司共享） |
| 自定义模板 | `storage/projects/{pid}/templates/custom_note_template.json` | 项目级覆盖与扩展（D8 schema） |

R4.3 验收要求 36 / 37 / 38（spec requirements.md）规定：

- 项目模板更新基线时，**不得**触碰 `custom_note_template`。
- 项目级模板支持 **版本（version + updated_at）**，可回滚到任意历史版本。
- 项目导出 / 导入必须能完整还原自定义内容。

实测 `NoteCustomTemplateService`（Sprint 3 Task 3.2 已落地）已经具备保存 + 回滚能力，但需要一份 ADR 沉淀**版本化的根本约定**，以避免后续误操作（覆盖历史 / 多写入路径串台 / 路径越界）。

## 决策

自定义附注模板采用 **「主文件 + 不可变 v{N}.json 快照 + history 元数据」** 三件套，回滚必产生新版本，绝不覆盖历史。

### 决策 1：三件套存储拓扑

```
storage/projects/{project_id}/templates/
├─ custom_note_template.json     当前活动版本（含 history 元数据 + sections）
├─ v1.json                        第 1 次 save 的不可变快照（含 sections）
├─ v2.json                        第 2 次 save 的不可变快照
├─ v3.json                        Restore 到 v1 后产生的第 3 个新版本（不覆盖 v1.json）
└─ ...
```

主文件 schema（与 `v{N}.json` 同样含 `sections`，主文件多 `history`）：

```jsonc
{
  "version": 3,
  "updated_at": "2026-05-26T14:00:00Z",
  "updated_by": "uuid-of-user",
  "history": [
    {"version": 1, "snapshot_path": "v1.json", "updated_at": "..."},
    {"version": 2, "snapshot_path": "v2.json", "updated_at": "..."},
    {"version": 3, "snapshot_path": "v3.json", "updated_at": "..."}  // 自身入 history
  ],
  "sections": [...]
}
```

### 决策 2：写入语义 — 单调递增 + 原子 temp+rename

`NoteCustomTemplateService.save_custom_template` 三步固定顺序：

1. **读旧主文件** → 取 `prev_version`（缺省 0）。
2. **生成 v{prev_version + 1}.json** 并先写 `tmp` 后 `replace`（`Path.replace` Windows / Unix 都是原子语义）。
3. **重写主文件**：把新版本号、时间戳、history 追加项一起写主文件，同样走 temp+rename。

**不变量**：

- `v{N}.json` 一旦写出**永远不可变**；任何 `save` / `restore` 都只新增 `v{N+1}.json`。
- `version` 字段单调递增；并发场景退化为「按版本号顺序排队」，不会跳号。
- `updated_at` 用 UTC ISO8601（`timespec="seconds"`），跨时区可比较。

### 决策 3：回滚 = 复制旧 sections 写新版本

`restore_to_version(target_version=N)`：

1. 读 `v{N}.json` 取 `sections` 字段。
2. 调 `save_custom_template(sections, updated_by)` 生成 `v{current+1}.json`。
3. **不修改** `v{N}.json` 自身（不可变快照原则）。

回滚后 `history` 形如 `[v1, v2, v3, v4]`，其中 v4 = 复制 v2 的 sections，记录人是当前操作人。前端可以通过 `history` 元数据看到「v4 是从 v2 回滚来的」（实现：在主文件多记 `restored_from` 元字段属未来增强，本 ADR 不强制）。

### 决策 4：路径越界保护（安全约束）

- `project_id` 必须经 `UUID(...)` 校验；非法格式 → `ValueError`。
- `v{N}.json` 中 `N` 必须 `int > 0`；任何 `..` / 绝对路径 / 字符串拼接均拒绝。
- 测试隔离用 `storage_root` 注入（`tmp_path`），生产硬编码 `REPO_ROOT/storage/projects`。

### 决策 5：与基线模板的合并

运行时 `disclosure_engine._load_templates`（D3 算法）按以下顺序：

1. 读基线 `note_template_{soe,listed}.json`。
2. 读 `custom_note_template.json`（不存在 → 跳过）。
3. `merge_templates(baseline, custom)` → custom 优先，按 `sort_order` 排序。

**自定义模板独立存储 + 版本化的隐含价值**：基线模板升级（重新跑 `cleanup_note_templates.py` / 重新生成 `note_templates_seed.json`）时不会影响自定义层，下次合并自然带上新基线 + 旧自定义。

## 后果

### 正面

- **回滚永远安全**：`v{N}.json` 不可变 + 主文件 atomic 写，断电 / 进程崩溃只会丢失「未提交的当前 save」，不会污染历史。
- **审计可追溯**：`history` 元数据 + `updated_by` + `updated_at` 三段还原任何时刻的修改链。
- **跨项目隔离**：`storage/projects/{pid}/templates/` 物理路径隔离；备份 / 迁移项目时 `templates/` 目录可整体打包。
- **基线升级零冲击**：基线层（`backend/data/`）与自定义层（`storage/projects/`）物理分离，CI 重生成基线不会动用户自定义。

### 代价

- **磁盘占用** = O(版本数 × sections 大小)。单项目 173 章节模板 ~200 KB；100 次 save 约 20 MB，可接受。如确需限制，可将"截断保留 N 个最近版本"作为后续增强（不在 R4.3 验收范围内）。
- **任何 save 都产生新版本**，无 "增量更新当前版本" 概念；这是设计目标，不是缺陷。
- 多人并发编辑同一项目模板时仍有 **last-writer-wins** 风险（历史版本不会丢，但当前活动版本会被后写者覆盖）。建议前端上锁或加版本号 OCC 校验（spec 后续可演进）。

### CI 卡点

- `test_note_custom_template_service.py`（Sprint 3）必须覆盖：
  1. 首次保存产生 `v1.json` + 主文件 `version=1`。
  2. 二次保存产生 `v2.json`，`v1.json` 内容不变。
  3. `restore_to_version(1)` 产生 `v3.json`，sections 与 `v1.json` 完全一致。
  4. 非法 `project_id` / 非法 `version` 必须抛 `ValueError`。
- 端点 `POST /api/projects/{pid}/note-template/save` / `/restore` 必须在 `router_registry/report.py` 注册。

## 关联

- **ADR-007**：附注三式联动单一真源 — 自定义模板是 `table_data` 的来源之一（基线 + 自定义 union 后供引擎消费）。
- **ADR-008**：附注单元格三态模式持久化 — 自定义模板新增的章节同样适用 D1 sidecar。
- **ADR-009**：致同 Word 排版规范命名空间 — 自定义章节在导出时同样走 GTNote* 样式。
- **Spec**：`.kiro/specs/disclosure-note-full-revamp/` D8 自定义模板存储与版本 + R4.3 验收 36/37/38。
- **代码**：
  - 服务实现：`backend/app/services/note_custom_template_service.py`
  - 路由：`backend/app/routers/note_custom_template.py`（`/save` / `/load` / `/restore` / `/versions`）
  - 注册：`backend/app/router_registry/report.py` §52b
  - 单测：`backend/tests/services/test_note_custom_template_service.py`

## 考虑过但未采用

### 直接覆盖 `custom_note_template.json` 不留 `v{N}.json` 快照

**否决原因**：R4.3 验收要求"可回滚到任意历史版本"，无快照 = 无法回滚。仅靠 `updated_at` 做"最近编辑回退"无法满足审计师跨多次修改回到某个具体节点的需求。

### 只存 patch / diff 不存全量 sections

**否决原因**：sections 单文件 < 200 KB，全量存储简单且鲁棒。patch 模式需要可靠的 diff 算法 + 应用顺序，复杂度大幅上升，回滚到非线性历史时还会出现冲突 — 与"版本快照即真理"的设计目标背离。

### 用 git 子仓库管理模板文件

**否决原因**：项目级模板归属业务数据，不应纳入工程代码版本控制；引入 git 子仓库会让运维（备份 / 迁移 / 删除项目）变得复杂，且 git 对二进制 / 大量小文件的性能不优。

### 把版本化能力下沉到 PostgreSQL（额外 `disclosure_note_template_versions` 表）

**否决原因**：模板是 JSON 文件且与项目目录强相关，PG 表会让"导出项目（含模板）"必须额外做 SELECT + 拼装；当前的「项目目录直接 zip」一键导出方案已能完整还原（R4.3 验收 38），无需引入数据库表的复杂度。

### 通过软链接 / 引用让 `restore` 不产生新文件

**否决原因**：软链接在 Windows 需要管理员权限不通用；引用计数模型让"备份恢复"变成图遍历，违反「快照即不可变文件」的简单心智模型。文件冗余存储是为可观测性付出的合理代价。
