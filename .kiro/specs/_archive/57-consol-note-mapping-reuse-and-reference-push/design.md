# 设计文档：合并附注映射规则复用与标准科目参考下推

## §一、架构概览

### 1.1 数据流全景

```
集团层（合并项目）
┌──────────────────────────────────────────────────┐
│  合并明细模板 ConsolNoteDetailTemplate           │
│    └─ rows[].recommended_account_codes  (US-3)   │
│  映射规则模板库 ConsolNoteMappingRuleTemplate     │
│    └─ 从项目规则提升，不绑 project_id  (US-1)    │
│  结构锁 ConsolNoteStructureLock  (US-6)          │
│  值确认 ConsolNoteValueConfirmation  (US-5)      │
└──────────────────────┬───────────────────────────┘
                       │ 推送（规则模板 + 科目参考）
                       ▼
子企业层（子公司项目）
┌──────────────────────────────────────────────────┐
│  底稿 → 公式推送 → 单体附注  ← 完全不变         │
│                        ↓                         │
│  规则模板预填映射建议（新项目开局）               │
│  科目参考展示在公式管理页（只读参考）             │
│  结构锁拦截行增删（金额不受影响）                │
│  值变化事件 → 合并层通知  (US-4)                 │
└──────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

1. **不断底稿链路**：子企业的底稿→公式推送→单体附注链路零改动（E-1/E-4）
2. **推规则不推结构**：集团推送的是映射规则模板和科目参考，不是附注行结构
3. **复用优先于重建**：同集团跨年/跨项目的映射规则可复用，减少重复确认
4. **通知不自动覆盖**：值变化只通知合并组，由用户决定何时刷新（保护 manual_cells）
5. **确认是快照**：值确认记录当时的值指纹，后续改数自动降级为过期

---

## §二、数据模型

### 2.1 新增表：映射规则模板（V200）

```sql
-- V200__consol_note_mapping_rule_template.sql

CREATE TABLE IF NOT EXISTS consol_note_mapping_rule_template (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type   VARCHAR(20)  NOT NULL,  -- soe / listed
    section_id      VARCHAR(64)  NOT NULL,
    source_structure_hash VARCHAR(64) NOT NULL,
    version_number  INT NOT NULL DEFAULT 1,
    mappings        JSONB NOT NULL DEFAULT '[]',
    -- 推荐的科目映射（从模板行读取，冗余存储便于查询）
    account_code_hints JSONB DEFAULT '{}',
    -- 溯源
    source_project_id UUID,          -- 提升来源项目
    source_rule_id    UUID,          -- 提升来源规则
    promoted_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    promoted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 生命周期
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_cnmrt_template_type CHECK (template_type IN ('soe','listed')),
    CONSTRAINT ck_cnmrt_hash_length CHECK (length(source_structure_hash) = 64),
    CONSTRAINT ck_cnmrt_version_positive CHECK (version_number > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnmrt_active_rule
    ON consol_note_mapping_rule_template (
        template_type, section_id, source_structure_hash, version_number
    ) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_cnmrt_section
    ON consol_note_mapping_rule_template (template_type, section_id)
    WHERE is_active = TRUE;
```

### 2.2 新增表：结构锁（V200）

```sql
CREATE TABLE IF NOT EXISTS consol_note_structure_lock (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consol_project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id      VARCHAR(64) NOT NULL,
    locked_version_id UUID NOT NULL
        REFERENCES consol_note_detail_template_version(id) ON DELETE RESTRICT,
    lock_scope      VARCHAR(20) NOT NULL DEFAULT 'rows_only',
    locked_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_cnsl_scope CHECK (lock_scope IN ('rows_only','full'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnsl_project_section
    ON consol_note_structure_lock (consol_project_id, section_id)
    WHERE is_active = TRUE;

-- 子企业锁定关联表——避免 check_structure_lock 每次 build_tree
-- 激活锁时由 service 从合并树 data_leaves 写入，解除时级联删除
CREATE TABLE IF NOT EXISTS consol_note_structure_lock_entity (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lock_id         UUID NOT NULL
        REFERENCES consol_note_structure_lock(id) ON DELETE CASCADE,
    entity_project_id UUID NOT NULL,
    entity_node_key VARCHAR(128) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnsle_lock_entity
    ON consol_note_structure_lock_entity (lock_id, entity_project_id);

-- 子企业保存时只需 SELECT EXISTS 即可判断是否被锁：
-- SELECT EXISTS(SELECT 1 FROM consol_note_structure_lock_entity e
--   JOIN consol_note_structure_lock l ON l.id = e.lock_id
--  WHERE e.entity_project_id = :pid AND l.section_id = :sid AND l.is_active)
CREATE INDEX IF NOT EXISTS idx_cnsle_entity_project
    ON consol_note_structure_lock_entity (entity_project_id);
```

### 2.3 新增表：值确认（V200）

```sql
CREATE TABLE IF NOT EXISTS consol_note_value_confirmation (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id      VARCHAR(64) NOT NULL,
    entity_node_key VARCHAR(128) NOT NULL DEFAULT '_self',
        -- '_self' = 本项目自身（单体确认场景）；
        -- 非 NULL 以避免 PG 唯一索引对 NULL 不去重问题。
    confirmed_value_hash VARCHAR(64) NOT NULL,
    confirmed_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    CONSTRAINT ck_cnvc_status CHECK (status IN ('confirmed','outdated')),
    CONSTRAINT ck_cnvc_hash_length CHECK (length(confirmed_value_hash) = 64)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnvc_project_section_entity
    ON consol_note_value_confirmation (project_id, section_id, entity_node_key);

CREATE INDEX IF NOT EXISTS idx_cnvc_project_status
    ON consol_note_value_confirmation (project_id, status);
```

### 2.4 现有表扩展

#### ConsolNoteDetailTemplateVersion.rows JSONB 扩展（US-3）

每行新增可选字段：

```json
{
  "target_row_id": "uuid",
  "canonical_name": "应收账款——关联方",
  "aliases": ["关联方应收"],
  "recommended_account_codes": ["1122_01", "1122_02"],
  "sort_order": 10,
  "row_type": "data"
}
```

无需迁移——JSONB 字段新增 key 向后兼容，旧版本读到 `undefined` 即无推荐。

#### ConsolNoteMappingRule 新增可选字段

```sql
-- V200 追加
ALTER TABLE consol_note_mapping_rule
    ADD COLUMN IF NOT EXISTS promoted_to_template_id UUID
        REFERENCES consol_note_mapping_rule_template(id) ON DELETE SET NULL;
```

记录该项目规则是否已提升为模板，防止重复提升。

---

## §三、服务层设计

### 3.1 映射规则模板服务 `consol_note_mapping_template_service.py`（新建）

```python
# 核心方法签名

async def promote_rule_to_template(
    db: AsyncSession,
    *,
    rule_id: UUID,
    promoted_by: UUID,
) -> dict[str, Any]:
    """将项目级映射规则提升为规则模板。
    
    校验：
    1. 规则必须是 active 的
    2. 规则的映射完整性（无 target=None 的手动行）
    3. 同 section+hash 不存在 active 模板（否则升版）
    """

async def find_template_for_hash(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
    source_structure_hash: str,
) -> dict[str, Any] | None:
    """按结构指纹精确查找规则模板。"""

async def find_templates_for_section(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
) -> list[dict[str, Any]]:
    """列出某章节的所有活跃规则模板（用于模糊匹配场景）。"""

async def suggest_from_templates(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
    source_groups: list[dict[str, Any]],
    fuzzy_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """从规则模板库生成映射建议。
    
    匹配策略：
    1. 精确匹配：source_structure_hash 完全一致 → confidence=0.92
    2. 逐行模糊：hash 不匹配时，逐行用 SequenceMatcher 匹配 → confidence=max(ratio, 0.75)
    """
```

### 3.2 预填匹配增强（改造 `consol_note_detail_source_service.py`）

`suggest_template_rows` 的五级匹配扩展为七级：

| 优先级 | match_type | confidence | 来源 |
|--------|-----------|------------|------|
| 1 | `exact` | 1.0 | canonical_name 精确匹配 |
| 2 | `alias` | 0.95 | aliases 匹配 |
| 3 | `rule_template` | 0.92 | **新增**：规则模板库精确匹配 |
| 4 | `previous_year` | 0.88 | **新增**：上年同集团项目历史 |
| 5 | `fuzzy` | ≥0.75 | SequenceMatcher 模糊 |
| 6 | `history` | 0.85 | 本项目历史规则 |
| 7 | `manual` | 0.0 | 未匹配，需手动 |

**上年项目查找逻辑**：

```python
async def _find_previous_year_rules(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    source_structure_hash: str,
) -> list[dict[str, Any]]:
    """查找同集团上年项目的确认过的映射规则。
    
    ⚠ projects 表无 client_id 字段，按以下双条件定位同集团：
    1. 主条件：projects.client_name 精确匹配（同一审计客户名称相同）
    2. 辅条件：projects.ultimate_company_code 非空且一致（最终控制方代码）
    两个条件取 OR——client_name 覆盖面广但有重名风险，
    ultimate_company_code 精确但可能为空（首汽租车即为 NULL）。
    
    步骤：
    1. 读当前项目的 client_name + ultimate_company_code
    2. 查满足双条件的其他合并项目（project_type='consolidated'），
       按 audit_period_end DESC 排序
    3. 在上年项目中查 section_id + source_structure_hash 匹配的 active rule
    """
```

### 3.3 值变化通知服务 `consol_note_value_change_service.py`（新建）

```python
def compute_value_fingerprint(
    rows: list[Any],
    headers: list[Any],
) -> str:
    """计算值指纹——只含数值列的 SHA-256。
    
    排除：第一列（标签列）、row_type、key 等结构信息。
    只取数值列的内容，按固定精度（小数点后 2 位）序列化。
    """

async def on_note_section_saved(
    db: AsyncSession,
    event: EventPayload,
) -> None:
    """NOTE_SECTION_SAVED 事件处理器。
    
    1. 计算新的 value_fingerprint
    2. 查该子企业是否参与某个合并项目的映射
    3. 如果参与且 fingerprint 变化：
       a. 标合并侧 ConsolNoteData.is_stale = True
       b. 发 CONSOL_NOTE_VALUE_CHANGED 事件
       c. 检查是否有 value_confirmation，如有则降级为 outdated
    """

async def get_stale_summary(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str | None = None,
) -> dict[str, Any]:
    """返回 stale 汇总：{section_id: [stale 企业列表]}。"""
```

### 3.4 值确认服务 `consol_note_value_confirmation_service.py`（新建）

```python
async def confirm_entity_value(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    entity_node_key: str | None,
    confirmed_by: UUID,
) -> dict[str, Any]:
    """确认某企业某章节的当前值。记录确认时的 value_fingerprint。"""

async def get_confirmation_status(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str | None = None,
) -> list[dict[str, Any]]:
    """查询确认状态汇总。返回每个 section × entity 的状态。"""

async def check_all_confirmed(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
) -> dict[str, Any]:
    """签发前闸门检查。返回 {passed: bool, blocking_items: [...]}。"""
```

### 3.5 结构锁服务 `consol_note_structure_lock_service.py`（新建）

```python
async def activate_lock(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    locked_version_id: UUID,
    locked_by: UUID,
) -> dict[str, Any]:
    """激活结构锁。校验版本存在且与当前绑定一致。"""

async def check_structure_lock(
    db: AsyncSession,
    *,
    entity_project_id: UUID,
    section_id: str,
) -> dict[str, Any] | None:
    """检查子企业某章节是否被结构锁。
    
    直接查 consol_note_structure_lock_entity JOIN consol_note_structure_lock，
    不需要 build_tree（激活锁时已展开写入关联表）。
    返回 None 表示未锁定，否则返回锁定信息。
    """

async def release_lock(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    released_by: UUID,
) -> dict[str, Any]:
    """解除结构锁。需 review 级权限。"""
```

---

## §四、API 端点设计

### 4.1 映射规则模板端点（新增路由文件 `consol_note_mapping_templates.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{pid}/consol-note-mapping/rules/{rid}/promote` | 提升规则为模板 |
| GET | `/api/consol-note-mapping-templates` | 列出规则模板（按 template_type/section_id 筛选） |
| GET | `/api/consol-note-mapping-templates/{tid}` | 获取规则模板详情 |
| DELETE | `/api/consol-note-mapping-templates/{tid}` | 停用规则模板（soft delete） |

### 4.2 值变化与确认端点（扩展现有路由）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{pid}/consol-note-value/stale-summary` | stale 汇总 |
| POST | `/api/projects/{pid}/consol-note-value/confirm` | 确认某企业某章节 |
| GET | `/api/projects/{pid}/consol-note-value/confirmation-status` | 确认状态汇总 |
| GET | `/api/projects/{pid}/consol-note-value/readiness-check` | 签发前闸门检查 |

### 4.3 结构锁端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{pid}/consol-note-structure-lock` | 激活结构锁 |
| DELETE | `/api/projects/{pid}/consol-note-structure-lock/{section_id}` | 解除结构锁 |
| GET | `/api/projects/{pid}/consol-note-structure-lock` | 查询锁状态 |

---

## §五、前端设计

### 5.1 映射确认弹窗增强

现有 preview→confirm 弹窗扩展：

- 建议来源标识：`rule_template`=蓝色标签"规则模板"、`previous_year`=灰色标签"上年"、现有匹配保持不变
- 一键确认按钮：所有行置信度 ≥ 0.88 时，显示"全部确认"按钮
- 确认后显示"提升为模板"入口（只对 admin/review 角色显示）

### 5.2 标准科目参考展示

子企业公式管理页（附注章节区域）：

- 每个附注章节旁显示"集团推荐"图标（📋），hover 展开推荐科目码列表
- 科目码与当前实际使用的科目码不一致时，显示橙色提示"与集团推荐不一致"
- 不阻断任何操作，纯展示

### 5.3 合并附注编辑器 stale 横幅

```
┌─────────────────────────────────────────────┐
│ ⚠ 3 家子企业的附注数据已更新                │
│   甲公司（应收账款）· 乙公司（存货）        │
│   丙公司（应收账款、固定资产）              │
│                          [点击刷新] [稍后]  │
└─────────────────────────────────────────────┘
```

### 5.4 确认状态面板

合并附注编辑器侧边栏增加"确认状态"面板：

- 按章节分组，每个章节下列出所有子企业
- 状态图标：✅ 已确认 / ⚠️ 已过期 / ⬜ 未确认
- 可选操作："确认当前值"（对单个企业×章节）

### 5.5 结构锁标识

子企业附注编辑器：

- 被锁定的章节表头显示 🔒 图标
- 行操作按钮（新增行/删除行）置灰，tooltip "该章节行结构已被集团锁定"
- 金额单元格正常可编辑

---

## §六、事件流设计

### 6.1 值变化通知链路

```
子企业附注保存
  → NOTE_SECTION_SAVED (已有事件)
    → on_note_section_saved handler (新增)
      → compute_value_fingerprint
      → 查 consol_note_mapping_binding 找合并项目
      → fingerprint 变化？
        → 标 ConsolNoteData.is_stale = True
        → 发 CONSOL_NOTE_VALUE_CHANGED 事件
        → 降级 value_confirmation.status = 'outdated'
      → SSE 推送到合并项目前端
```

### 6.2 新增事件类型

```python
# 注册到 event_bus
CONSOL_NOTE_VALUE_CHANGED = "CONSOL_NOTE_VALUE_CHANGED"
# payload: {consol_project_id, section_id, entity_node_key, 
#           entity_company_name, old_fingerprint, new_fingerprint}
```

该事件是进程内 EventBus 事件（C-3 约束），不跨实例。

---

## §七、迁移策略

### V200/R200 单文件

V200 创建三张新表 + 一个 ALTER。R200 为幂等回滚。

三张表互不依赖，可并行创建。`ALTER TABLE consol_note_mapping_rule` 的 `promoted_to_template_id` FK 指向新表，必须在 CREATE TABLE 之后。

### 存量数据

无需迁移存量数据——规则模板库初始为空，由用户主动提升。值确认初始为空，结构锁初始为空。

---

## §八、与现有架构的衔接点

| 现有模块 | 衔接方式 |
|----------|---------|
| `consol_note_detail_source_service.suggest_template_rows` | 插入第 3/4 级匹配来源 |
| `consol_note_mapping_rule_service.confirm_mapping` | 确认后返回结果增加 `can_promote` 标志 |
| `consol_note_detail_template_service.add_version` | rows 校验兼容新增的 `recommended_account_codes` |
| `EventBus.NOTE_SECTION_SAVED` | 新增 handler 计算值指纹 |
| `ConsolNoteData.is_stale` | 值变化时设置，与现有结构变化的 stale 共用同一字段 |
| `deliverable_readiness_check` | 新增检查项"合并附注值确认完整性" |
| `consol_note_formula_service.fill_by_formula` | 不改动，stale 横幅的刷新按钮调用现有逻辑 |

---

## §九、测试策略

### 9.1 后端

- 映射规则模板：提升/查找/升版/停用 CRUD + 完整性校验 + 重复提升幂等
- 预填匹配增强：七级匹配优先级 + 规则模板库匹配 + 上年项目匹配 + 回退到旧五级
- 值变化通知：fingerprint 计算确定性 + 事件触发条件 + stale 标记 + confirmation 降级
- 值确认闸门：confirm/outdated/readiness-check + 集成到签发清单
- 结构锁：激活/释放/检查 + 子企业保存时拦截 + 金额不受影响
- 迁移：V200 幂等 + R200 回滚

### 9.2 前端

- 映射确认弹窗：来源标识渲染 + 一键确认 + 提升入口角色门控
- stale 横幅：展示/隐藏/刷新联动
- 确认状态面板：状态图标渲染 + 确认操作
- 结构锁标识：🔒 图标 + 行操作置灰 + 金额可编辑
- 科目参考：展示 + 不一致提示

### 9.3 真库守卫

- PG-only 测试覆盖规则模板的唯一索引行为
- PG-only 测试覆盖值确认的 UPSERT 行为
- 值指纹计算的浮点精度一致性测试
