# 合并附注明细模板与多企业行映射规则 — 设计

## §一 现状证据（2026-10-13 现读）

### 1.1 合并附注数据链路

| 层次 | 文件 | 关键函数 | 能力 |
|---|---|---|---|
| 聚合 | `consol_note_aggregation_service.py` | `aggregate_section` | 从数据叶子项目 `disclosure_notes` 按 `section_id` 拉行，`fuzzy_merge_same_label` 按 0.85 阈值合并同名行 |
| 编排 | `consol_disclosure_service.py` | `generate_full_consol_notes` → `_aggregate_common_section` | 173 共有 + 7 专用 = 180 章节；V2 持久化**只写 provenance 不落渲染 table_data** |
| 公式 | `consol_note_formula_service.py` | `fill_by_formula` / `fill_note_sections` | 从合并报表/TB 公式取金额写 `consol_note_data`；行定位按标签名 `_target_row` |
| 前端 | `ConsolNoteTab.vue` | `handleReaggregate` | 按钮"重新汇总"实际调用 `fill_note_sections`，走公式路径，不读下属企业附注明细 |
| 前端 | `ConsolNoteTab.vue` | `executeAggregate` | 单格汇总，按 `row_idx + col_idx` 同位置取数，不处理行不对齐 |
| 持久 | `consol_note_data_models.py` | `ConsolNoteData` | JSONB `data`（headers + rows + manual_cells）/ `cell_state` / `locked_cells` / `last_formula_value` |
| 模板 | `consol_note_sections_{soe,listed}.json` | 静态 JSON | 行为空占位，无稳定行 ID，行名可被用户直接编辑 |

### 1.2 现有自定义附注模板

- `NoteTemplateService`（`note_template_service.py`）：本机文件 `~/.gt_audit_helper/note_templates/custom/` 存储，UUID + 版本号 + CRUD + 回滚。
- `note_templates.py` 路由：`/api/note-templates/custom` CRUD。
- **不适用本需求**：文件存储不支持多用户共享，版本回滚只改标记不恢复内容，无来源指纹和映射规则。

### 1.3 缺口总结

| 能力 | 现有 | 缺口 |
|---|---|---|
| 明细模板行稳定 ID | ❌ 行号或标签名 | 需 `target_row_id` UUID |
| 模板版本与共享 | ❌ 本机文件 | 需 PG 表 + 项目绑定 |
| 来源行→目标行映射 | ❌ 只有模糊合并 | 需持久化规则 + 多动作 |
| 批量企业映射 | ❌ 逐格/逐企业 | 需按结构指纹分组 |
| 来源变更检测 | ❌ 无 | 需结构指纹 + stale |
| 刷新三阶段 | ❌ 一步到位 | 需 preview → confirm → apply |
| 穿透到企业来源行 | 部分（provenance） | 需行级 breakdown |

## §二 数据模型

### 2.1 合并明细模板

```sql
-- V186
CREATE TABLE IF NOT EXISTS consol_note_detail_template (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type   VARCHAR(20) NOT NULL,       -- soe / listed
    section_id      VARCHAR(64) NOT NULL,       -- 章节 ID
    visibility      VARCHAR(20) NOT NULL DEFAULT 'project',  -- draft / project / firm
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (template_type, section_id, created_by) -- 同人同章节只有一套模板（多版本）
);

CREATE TABLE IF NOT EXISTS consol_note_detail_template_version (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id     UUID NOT NULL REFERENCES consol_note_detail_template(id),
    version_number  INTEGER NOT NULL,           -- 递增 v1, v2, ...
    rows            JSONB NOT NULL,             -- [{target_row_id, canonical_name, aliases, sort_order, row_type}]
    change_note     TEXT,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (template_id, version_number)
);

CREATE TABLE IF NOT EXISTS consol_note_template_binding (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    section_id      VARCHAR(64) NOT NULL,
    template_version_id UUID NOT NULL REFERENCES consol_note_detail_template_version(id),
    bound_by        UUID REFERENCES users(id),
    bound_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, section_id)             -- 一个项目一个章节只绑一个版本
);
```

### 2.2 映射规则

```sql
-- V186（同一迁移文件）
CREATE TABLE IF NOT EXISTS consol_note_mapping_rule (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id),
    section_id              VARCHAR(64) NOT NULL,
    template_version_id     UUID NOT NULL REFERENCES consol_note_detail_template_version(id),
    source_structure_hash   VARCHAR(64) NOT NULL,   -- 来源结构指纹 SHA-256
    version_number          INTEGER NOT NULL DEFAULT 1,
    mappings                JSONB NOT NULL,          -- [{source_label, source_row_key, target_row_id, mapping_action, ignore_reason?}]
    confirmed_by            UUID REFERENCES users(id),
    confirmed_at            TIMESTAMPTZ,
    is_active               BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, section_id, template_version_id, source_structure_hash, version_number)
);

CREATE TABLE IF NOT EXISTS consol_note_mapping_binding (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    section_id          VARCHAR(64) NOT NULL,
    entity_node_key     VARCHAR(128) NOT NULL,       -- 数据叶子节点 node_key
    entity_project_id   UUID NOT NULL,               -- 叶子企业的 project_id
    rule_id             UUID NOT NULL REFERENCES consol_note_mapping_rule(id),
    bound_source_hash   VARCHAR(64) NOT NULL,         -- 绑定时该企业的来源结构指纹
    status              VARCHAR(20) NOT NULL DEFAULT 'confirmed', -- confirmed / stale
    bound_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, section_id, entity_node_key)
);
```

### 2.3 ORM

在 `backend/app/models/` 新建 `consol_note_mapping_models.py`，包含上述 5 个 ORM 类。全部主键 `default=uuid.uuid4`。

### 2.4 迁移

`V186__consol_note_detail_template_and_mapping.sql` + `R186__consol_note_detail_template_and_mapping.sql`（幂等对偶）。所有 `CREATE TABLE` 带 `IF NOT EXISTS`，`CREATE INDEX` 带 `IF NOT EXISTS`。

## §三 来源结构指纹算法

```python
import hashlib, json

def compute_source_structure_hash(section_id: str, rows: list[dict]) -> str:
    """排除金额，只包含结构信息。"""
    items = []
    seen: dict[str, int] = {}
    for row in rows:
        label = str(row.get("label") or row.get(0) or "").strip()
        row_type = str(row.get("row_type", "data"))
        stable_key = str(row.get("row_id") or row.get("item_id") or "")
        if not stable_key:
            # 无稳定键时用"名称+重复序号"生成伪键
            count = seen.get(label, 0)
            seen[label] = count + 1
            stable_key = f"{label}#{count}"
        items.append({"label": label, "row_type": row_type, "key": stable_key})
    payload = json.dumps({"section_id": section_id, "items": items},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

## §四 刷新状态机

```
                    ┌──────────┐
          用户选择   │  idle    │
          章节/企业  └────┬─────┘
                         │ preview
                         ▼
                    ┌──────────┐
                    │ previewed│  ← 生成 preview_token
                    └────┬─────┘
            无未映射行 │          │ 有未映射行
            且无 stale │          │ 或有 stale
                       ▼          ▼
              ┌────────────┐  ┌──────────────┐
              │ ready_apply│  │ needs_mapping │
              └─────┬──────┘  └──────┬───────┘
                    │                │ confirm_mapping
                    │                ▼
                    │         ┌──────────────┐
                    │         │  confirmed   │
                    │         └──────┬───────┘
                    │                │
                    ├────────────────┘
                    │ apply（校验 token + hash）
                    ▼
              ┌──────────┐
              │ applied  │  → 写 consol_note_data.data.rows
              └──────────┘
```

`409 Conflict`：apply 时若 `source_structure_hash` 已变化或 `preview_token` 过期，拒绝并要求重新 preview。

## §五 API 设计

### 5.1 模板

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/consol-note-templates` | 创建模板（首版本随模板一起创建） |
| GET | `/api/consol-note-templates?template_type=&section_id=&visibility=` | 列表（按可见范围筛选） |
| POST | `/api/consol-note-templates/{id}/versions` | 追加新版本 |
| GET | `/api/consol-note-templates/{id}/versions` | 查看版本历史 |
| PUT | `/api/consol-note-templates/{id}/visibility` | 修改可见范围 |
| DELETE | `/api/consol-note-templates/{id}` | 软删除 |

### 5.2 模板绑定

| 方法 | 路径 | 说明 |
|---|---|---|
| PUT | `/api/projects/{pid}/consol-note-template-binding/{section_id}` | 绑定/切换版本（需二次确认参数 `confirm=true`） |
| GET | `/api/projects/{pid}/consol-note-template-binding` | 查看当前项目所有绑定 |

### 5.3 映射规则

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{pid}/consol-note-mapping/rules?section_id=` | 列出规则 |
| POST | `/api/projects/{pid}/consol-note-mapping/rules` | 创建/升版规则 |
| PUT | `/api/projects/{pid}/consol-note-mapping/rules/{id}/deactivate` | 停用规则 |
| GET | `/api/projects/{pid}/consol-note-mapping/rules/{id}/versions` | 版本历史 |

### 5.4 刷新

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{pid}/consol-note-detail-refresh/preview` | 预览（只读，生成 preview_token） |
| POST | `/api/projects/{pid}/consol-note-detail-refresh/confirm-mapping` | 确认映射（写规则 + 绑定） |
| POST | `/api/projects/{pid}/consol-note-detail-refresh/apply` | 应用（校验 token，写 consol_note_data） |

### 5.5 建议

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{pid}/consol-note-detail-refresh/suggest-template` | 扫描来源并生成模板建议 |

## §六 映射建议算法

1. 遍历来源行标签列表。
2. 对每个来源标签，先精确匹配目标模板行的 `canonical_name` 和 `aliases`。
3. 未精确命中时，用 `SequenceMatcher.ratio()` 取 ≥0.75 的最高候选，标记为"模糊建议"。
4. 命中多个候选时全部返回，由用户选择。
5. 历史规则中已有同来源标签的映射时，优先沿用并标记"历史复用"。
6. 无任何候选时标记"需人工映射"。

## §七 前端设计

### 7.1 入口

ConsolNoteTab 工具栏新增按钮"📋 明细刷新"，与现有"ƒx 按公式填入"和"🔄 重新汇总"并列。

### 7.2 批量映射弹窗（`ConsolNoteMappingDialog.vue`）

- 顶部：当前章节标题 + 目标模板版本号。
- 左侧（来源分组表格）：

| 来源名称 | 涉及企业数 | 建议目标 | 操作 | 状态 |
|---|---:|---|---|---|
| 工资及奖金 | 8 | 职工薪酬 ✅ | `map` ▾ | 待确认 |
| 管理人员薪酬 | 2 | 职工薪酬 ✅ | `map` ▾ | 待确认 |

- 操作列下拉：`映射` / `合并映射` / `新增目标行` / `忽略（需说明）`。
- 可展开行查看各企业来源值和金额。
- 右侧或底部：目标模板预览（当前行列表 + 映射后的汇总金额预览）。

### 7.3 变更提示

`stale` 的企业高亮行背景为浅黄，标注变更详情（"行名由 X 变为 Y" / "新增行 Z" / "删除行 W"）。

### 7.4 规则管理面板（`ConsolNoteMappingRulesPanel.vue`）

- 表格展示各章节规则状态。
- 点击进入编辑模式时显示新旧 diff。
- 支持版本历史查看和回滚。

### 7.5 模板编辑器（`ConsolNoteDetailTemplateEditor.vue`）

- 行列表编辑（拖拽排序、新增、删除、改名）。
- 删除已引用行时弹出影响预览。
- 版本发布确认。
- 建议导入（从来源扫描结果一键导入）。

## §八 与现有机制的交互

### 8.1 与公式填入的关系

"明细刷新"写入 `consol_note_data.data.rows` 后，如果该章节也有 `ConsoleNoteFormula` 公式，后续执行"按公式填入"时，公式按标签名 `_target_row` 定位，会命中明细刷新写入的行。两者互补：明细刷新解决"哪些行该出现 + 多企业同名行归并"，公式填入解决"每个格子取什么金额"。

### 8.2 与 stale 标记的关系

明细刷新写入后应清除 `consol_note_data.is_stale = False`。如果后续下属企业有新的单体附注变化（`disclosure_notes` 更新），现有 `consol_note_stale_handler` 会重新标 stale，前端显示待刷新提示。

### 8.3 与合并锁定的关系

所有写操作（confirm_mapping / apply / 模板版本发布）均受 `check_consol_lock` 保护。锁定后只能查看规则和预览，不能修改。

### 8.4 与签字冻结的关系

签字冻结后合并附注所有数据不可修改，映射规则和模板版本绑定同样冻结。

## §九 ROI 与验证

| 批次 | 范围 | 文件数 | 测试预估 |
|---|---|---|---|
| Phase 1 | 数据模型 + V185 迁移 + ORM + 模板 CRUD API | ~6 | ~20 |
| Phase 2 | 来源扫描 + 结构指纹 + 建议算法 + preview API | ~4 | ~18 |
| Phase 3 | 映射规则 CRUD + confirm_mapping + 绑定管理 | ~4 | ~16 |
| Phase 4 | apply 写入 + 穿透 + 手工保护 + stale 联动 | ~4 | ~14 |
| Phase 5 | 前端模板编辑器 + 映射弹窗 + 规则面板 | ~5 | ~12 |
| Phase 6 | 集成回归 + Playwright 实测 | ~2 | ~10 |

合计约 25 个后端+前端文件，90 个测试。

隔离环境禁指向开发 PG；SQLite 与合成浏览器证据不升级为真实 PG 业务验收。真实项目写路径须另行授权。
