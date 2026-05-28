# 附注模块全维度增强 — 设计文档

> 版本：v0.6.2（2026-05-28，新增 D15 离线分发）
> 关联需求：requirements.md（151 验收 / 15 维度 D1-D15）
> v0.6 关键变更：
> 1. Phase 化重组：Phase 1 单体修复（主线）/ Phase 2 合并连带 / Phase 3 高级特性
> 2. D14 国企↔上市丝滑切换独立成项
>
> v0.6.1 修复：
> 1. 影响范围标题 v0.4 → v0.6
> 2. CI 卡点表加 CI-20（D14 互转 round-trip PBT）
> 3. ADR 列表加 ADR-021（国企↔上市丝滑切换）
>
> v0.6.2 新增：
> 1. **D15 离线分发与一键导入**（人机互补，xlsx 导出 + 字段级 diff 导回）
> 2. CI 卡点 +CI-21/CI-22（_meta_ sheet 完整性 + 导出/导入 round-trip PBT）
> 3. ADR-022（离线分发包格式标准）
> 4. 影响范围 +1.5 + 0.5 = 2 人天，**总 38.5 人天**

## 一、设计核心决策

### D1 「动态」统一概念

`row_type` 枚举：`data | subtotal | total | header_label | dynamic_anchor | dynamic_data | dynamic_marker_end`

`column.col_type` ：`fixed | dynamic`

判定 = `row.is_dynamic = row.row_type.startswith('dynamic_')` / `column.is_dynamic = col_type == 'dynamic'`

### D2 双 sidecar + 列元数据扩展

```json
{
  "table_data": {
    "headers": [...],   // 兼容旧路径
    "rows": [...],

    "_columns_meta": [   // 新：列元数据
      {
        "id": "col_label",
        "label": "项目",
        "header_path": ["项目"],          // 单层
        "col_type": "fixed",
        "value_type": "text",
        "width": 200,                     // 拖动调宽存这里
        "is_frozen": true                 // 冻结首列
      },
      {
        "id": "col_amount_end",
        "header_path": ["本年", "期末余额"], // 二级合并表头
        "col_type": "fixed",
        "value_type": "amount",
        "width": 120
      },
      {
        "id": "col_user_currency",
        "header_path": ["币种"],
        "col_type": "dynamic",
        "added_by": "user_xxx",
        "added_at": "2026-..."
      }
    ],

    "_dynamic_regions": [
      {"name": "客户明细", "axis": "row", "start_idx": 1, "end_idx": 5, "expandable": true,
       "dynamic_source": "aux_balance", "source_config": {...}},
      {"name": "扩展列", "axis": "column", "start_col_idx": 3, "end_col_idx": 999,
       "expandable": true, "dynamic_source": "manual"}
    ]
  }
}
```

### D3 7-source 全支持 + 多源 fallback 链（D4）

```json
{
  "binding": {
    "primary": {
      "source": "wp_data",
      "wp_code": "h08",
      "sheet": "分类构成",
      "extract": "table",
      "row_filter": {"is_total": false, "exclude_label_pattern": "合计|小计"},
      "label_col": "A",
      "value_cols": {"col_amount_end": "F", "col_amount_start": "G"}
    },
    "fallback": [
      {"source": "trial_balance", "account_codes": ["1601"], "field": "audited_amount"},
      {"source": "manual", "default_value": null}
    ],
    "show_provenance": true
  }
}
```

**provenance 记录**（每 cell 实际取数来源）：

```json
"_cell_provenance": {
  "row_3:col_amount_end": {
    "source": "wp_data",
    "wp_code": "h08",
    "fetched_at": "2026-...",
    "fallback_used": false,
    "value": 12345.67
  },
  "row_4:col_amount_end": {
    "source": "trial_balance",
    "account_codes": ["1601"],
    "fallback_used": true,    // primary wp_data 失败回退到 TB
    "fallback_index": 0,
    "value": 0.0
  }
}
```

### D4 wp_data 数据源接入（核心）

```python
# disclosure_engine.py 新增
async def _extract_wp_data(self, project_id: UUID, year: int, source_config: dict):
    """从底稿 parsed_data 提取数据."""
    wp = await self._get_workpaper(project_id, year, source_config['wp_code'])
    if not wp or not wp.parsed_data:
        return None  # 触发 fallback

    sheet_data = wp.parsed_data.get(source_config['sheet'], {})
    extract_type = source_config['extract']

    if extract_type == 'table':
        return self._extract_wp_table(sheet_data, source_config)
    elif extract_type == 'cell':
        return self._extract_wp_cell(sheet_data, source_config)
    elif extract_type == 'sum_column':
        return self._extract_wp_column_sum(sheet_data, source_config)


async def _resolve_with_fallback(self, binding: dict, ctx) -> tuple[Any, dict]:
    """多源 fallback 解析，返回 (value, provenance)."""
    primary = binding.get('primary') or binding   # 兼容旧路径
    val = await self._resolve_single(primary, ctx)
    if val is not None:
        return val, {'source': primary['source'], 'fallback_used': False, 'value': val}

    for idx, fb in enumerate(binding.get('fallback', [])):
        val = await self._resolve_single(fb, ctx)
        if val is not None:
            return val, {'source': fb['source'], 'fallback_used': True, 'fallback_index': idx, 'value': val}

    return None, {'source': 'none', 'fallback_used': True, 'value': None}
```

### D5 auto_trim v2 三级裁剪

详见 v0.2 design D5（三级 prune）。补充：

- 章节级（已有）→ 不变
- 表格级（新）→ `_render_as: 'no_business_paragraph'` 标记
- 段落级（新）→ `note.is_deleted=true` + `deletion_reason='auto_trim_v2_empty'`

### D6 集团模板继承（含多层级 lineage）

```python
class GroupNoteTemplateBaseline(Base):
    __tablename__ = "group_note_template_baseline"
    id: UUID
    name: str
    parent_project_id: UUID
    version: str  # "v1.2"
    parent_baseline_id: UUID | None  # 多层级（孙合并基线 → 子合并基线 → 总基线）
    template_type: str
    sections_data: JSONB  # 完整 sections（文字+表样+text_template_vars）
    is_active: bool = true

# DisclosureNote 字段
class DisclosureNote(Base):
    template_lineage: JSONB  # [{baseline_id, version, applied_at}, ...]
    is_local_override: bool = false
    text_template_vars: JSONB | None  # D7 段落变量
```

### D7 文字段落 Jinja 渲染（v0.3 新增）

```python
# 新建 backend/app/services/note_text_template_engine.py
from jinja2 import Environment, BaseLoader

NOTE_TEXT_ENV = Environment(loader=BaseLoader())
NOTE_TEXT_ENV.filters['format_amount'] = lambda v: f"{v:,.2f}"
NOTE_TEXT_ENV.filters['cn_number'] = _to_chinese_number  # 阿拉伯 → 中文数字

def render_text_paragraph(template_str: str, vars: dict) -> str:
    """渲染附注文字段落.

    vars 来源：
      - project.wizard_state（公司基本信息）
      - client master（行业/法人）
      - consolidation_models（子公司清单）
      - prior_notes_cache（上年数据）
    """
    tmpl = NOTE_TEXT_ENV.from_string(template_str)
    return tmpl.render(**vars)
```

模板示例（章节「公司基本情况」）：

```jinja
本公司经{{ registration_authority | default("XX工商行政管理局") }}核准，
于{{ registration_date | date_cn }}注册成立，
{% if is_listed %}
并于{{ list_date | date_cn }}在{{ list_exchange }}{% if list_board %}{{ list_board }}{% endif %}上市（股票代码：{{ stock_code }}）。
{% else %}
是{{ company_type | default("有限责任公司") }}。
{% endif %}
注册资本{{ registered_capital | format_amount }}元，
注册地址：{{ registered_address }}，
法定代表人：{{ legal_representative }}。
{% if subsidiary_count > 0 %}

本公司控股子公司{{ subsidiary_count }}家，主要从事{{ business_industry }}业务，
{% if controlled_subsidiaries %}
具体包括：{{ controlled_subsidiaries | map(attribute='name') | join('、') }}。
{% endif %}
{% endif %}
```

### D8 合并附注完整开发（v0.5 升级 ⭐⭐⭐）

#### 现状再确认（grep 实测）

| 模块 | 文件 | 状态 |
|------|------|------|
| `consol_disclosure_service.py` | 7 章节生成 | ✅ 不消费子公司单体 |
| `ConsolNoteTab.vue` (1466 行) | UI | ✅ 框架完整 + aggregation 弹窗已就绪 |
| `consol_tree_service.build_tree` | 子公司树 | ✅ 已存在但未被附注模块调用 |
| `consol_aggregation_service.query_node` | TB 汇总 | ✅ 已存在（self/children/descendants），**附注未复用** |

#### 改造架构（V2 完整服务）

```python
# 改造 consol_disclosure_service.py 为 V2

class ConsolDisclosureServiceV2:
    """合并附注完整服务（v0.5）.

    取代 generate_consol_notes 的 7 章节限制，提供：
    1. generate_full_consol_notes: 173 + 7 = 180 章节完整生成
    2. aggregate_from_children: 调用 ConsolNoteAggregationService 从子公司汇总
    3. integrate_consol_specific: 7 个合并专用章节（保留现有逻辑）
    4. 章节序号按 scope='consolidated' 重排（依赖 D13）
    5. lineage 链记录（多层合并）
    """

    async def generate_full_consol_notes(
        self,
        parent_project_id: UUID,
        year: int,
        template_type: str = "soe",
    ) -> list[DisclosureNote]:
        # 1. 加载子公司树
        tree = await consol_tree_service.build_tree(self.db, parent_project_id)
        if not tree:
            raise ValueError("非合并项目或无子公司")

        # 2. 加载 P-5 章节映射
        mapping = await self._load_consol_section_mapping(template_type)

        # 3. 生成共有章节（150+，从子公司汇总）
        common_sections = []
        for consol_section_id, mapping_cfg in mapping.items():
            if mapping_cfg["is_consol_only"]:
                continue
            section = await self._aggregate_common_section(
                parent_project_id, year,
                consol_section_id, mapping_cfg, tree,
            )
            common_sections.append(section)

        # 4. 生成合并专用章节（保留现有 _generate_xxx_section）
        consol_only = self._generate_consol_only_sections(parent_project_id, year)

        # 5. 章节序号重排（D13）
        all_sections = common_sections + consol_only
        rendered_numbers = await NoteSectionNumberingService(self.db).render_all(
            parent_project_id, year, scope='consolidated'
        )

        # 6. 文字段落 Jinja 渲染（合并版 vars）
        for section in all_sections:
            if section.text_template:
                section.text_content = render_text_paragraph(
                    section.text_template,
                    vars=self._build_consol_vars(parent_project_id, tree),
                )

        # 7. 写 lineage（多层合并支持）
        for section in all_sections:
            section.template_lineage = self._build_lineage_chain(parent_project_id, section)

        return all_sections


    async def _aggregate_common_section(
        self,
        parent_project_id, year,
        consol_section_id, mapping_cfg, tree,
    ) -> DisclosureNote:
        """从子公司单体附注汇总单个共有章节."""
        # 子公司列表
        children = self._get_active_subsidiaries(tree, mapping_cfg.get("child_filter"))

        # 调 ConsolNoteAggregationService.aggregate_section
        agg_service = ConsolNoteAggregationService(self.db)
        aggregated = await agg_service.aggregate_section(
            parent_project_id=parent_project_id,
            year=year,
            consol_section_id=consol_section_id,
            child_section_ids=mapping_cfg["child_section_ids"],
            child_projects=children,
            aggregation_method=mapping_cfg["aggregation_method"],
            elimination_rules=mapping_cfg.get("elimination_rules", []),
        )

        # 写 _cell_provenance: 每个 cell 来自 N 家子公司 + 各贡献金额
        return self._build_disclosure_note_with_provenance(aggregated)
```

#### 8.4 前端 ConsolNoteTab 升级

```vue
<!-- 章节树新增「来自 N 家子公司」标识 -->
<el-tree :data="consolNoteTree">
  <template #default="{ data }">
    <span>{{ data.title }}</span>
    <el-tag v-if="data.is_aggregated" size="mini">
      来自 {{ data.children_count }} 家子公司
    </el-tag>
    <el-tag v-if="data.is_consol_only" type="warning">仅合并</el-tag>
    <el-tag v-if="data.has_local_override" type="danger">已修改</el-tag>
  </template>
</el-tree>

<!-- cell 单击 → 溯源对话框 -->
<ConsolCellProvenanceDialog
  :provenance="selectedCellProvenance"
  :child-contributions="cellChildContributions"
/>

<!-- 工具栏 -->
<el-button @click="triggerReaggregation">🔄 重新汇总</el-button>
<el-button @click="showLineageGraph">🗂️ 多层合并 lineage</el-button>
```

#### 8.5 合并范围变化联动

```python
@on_event("CONSOL_SUBSIDIARY_CHANGED")  # 新事件
async def handle_subsidiary_changed(event):
    """子公司变化（增删/持股变化）→ 触发合并附注 stale."""
    parent_id = event.parent_project_id
    affected_sections = await get_aggregated_sections(parent_id)
    for section in affected_sections:
        await mark_stale(section, reason="subsidiary_changed")
```

### D14 国企↔上市丝滑切换（v0.6 新增 ⭐⭐⭐）

#### 14.1 改造 note_conversion_service 接入 section_id

```python
class NoteConversionServiceV2:
    """国企↔上市互转服务（v0.6 接入 D13 section_id）."""

    async def preview(
        self,
        project_id: UUID,
        year: int,
        target_type: str,  # 'soe' | 'listed'
    ) -> dict:
        """切换前预览：影响章节数 + 用户编辑保留 + diff."""
        current = await self._load_notes(project_id, year)
        diff = await self._compute_diff(current.template_type, target_type)

        result = {
            "common_sections": diff.common_count,           # 共有 ~150
            "to_archive_sections": diff.target_only_in_current,  # SOE 独有归档
            "to_create_sections": diff.target_only_in_target,    # Listed 新增
            "format_changed_sections": diff.format_changed,      # 格式略不同 ~10
            "user_edits_preserved": self._count_user_edits(current, diff),
            "warnings": [...],
        }
        return result

    async def execute(
        self,
        project_id: UUID,
        year: int,
        target_type: str,
        confirmed: bool = False,
    ) -> dict:
        """执行互转 — 调用方必须先 preview 确认."""
        if not confirmed:
            raise ValueError("Must call preview() and get user confirmation first")

        current = await self._load_notes(project_id, year)
        target_template = await self._load_template(target_type)

        # 1. 共有章节直接复制（按 section_id 匹配）
        # 2. 当前独有章节 → archive 表保留 30 天
        # 3. 目标独有章节 → 创建空章节
        # 4. 格式不同章节 → 字段映射 + 旧字段归档
        # 5. 更新 project.template_type
        # 6. 触发 NOTE_TEMPLATE_TYPE_CHANGED 事件
```

#### 14.2 章节差异加载（P-7 数据驱动）

```json
// backend/data/note_soe_listed_diff.json
{
  "version": "2025.1",
  "common_sections": [
    {"section_id": "section_cash", "title": "货币资金"},
    ...  // 150+ 共有
  ],
  "soe_only_sections": [
    {"section_id": "section_state_owned_disclosure", "title": "国资委特别披露"}
  ],
  "listed_only_sections": [
    {"section_id": "section_treasury_stock", "title": "库存股"},
    {"section_id": "section_perpetual_bond", "title": "永续债"}
  ],
  "format_diff_sections": [
    {
      "section_id": "section_fixed_assets",
      "soe_format": {"layout": "movement", "columns": [...]},
      "listed_format": {"layout": "category_sum", "columns": [...]},
      "field_mapping": {
        "soe.col_purchase": "listed.col_buildings_increase",
        ...
      }
    }
  ]
}
```

#### 14.3 集团内子公司不同模板共存

```python
# Project ORM 已有 template_type 字段
# v0.6 增强：合并项目的 template_type 由 partner 锁定（独立于子公司）

class ProjectTemplateLock(Base):
    __tablename__ = "project_template_lock"
    project_id: UUID
    template_type: str  # soe | listed
    locked_by: UUID
    locked_at: datetime
    lock_reason: str | None  # "合并项目固定上市版" 等

# apply_baseline 时检查
async def apply_baseline_with_template_check(child_id, baseline_id):
    child = await load_project(child_id)
    baseline = await load_baseline(baseline_id)
    if child.template_type != baseline.template_type:
        # 弹警告 + 提示用户先转换
        return {"error": "TEMPLATE_TYPE_MISMATCH", "child": child.template_type, "baseline": baseline.template_type}
```

#### 14.4 跨模板合并汇总（B.2 联动）

```python
# ConsolNoteAggregationService.aggregate_section 加 template_translate

async def aggregate_section_cross_template(
    self,
    consol_template: str,        # 'soe' | 'listed'
    child_section_id: str,
    children: list[Project],
):
    """跨模板汇总：子公司模板可能与合并不同."""
    aggregated = []
    for child in children:
        child_notes = await self._load_child_notes(child)
        if child.template_type != consol_template:
            # 跨模板：用 P-7 字段映射 translate
            translated = await self._translate_section(
                child_notes[child_section_id],
                from_type=child.template_type,
                to_type=consol_template,
            )
            aggregated.append(translated)
        else:
            aggregated.append(child_notes[child_section_id])

    return self._merge(aggregated, ...)
```

#### 14.5 前端切换器组件

```vue
<!-- DisclosureEditor.vue 顶部新增 -->
<el-radio-group v-model="templateType" size="small" @change="onTemplateChange">
  <el-radio-button label="soe">国企版</el-radio-button>
  <el-radio-button label="listed">上市版</el-radio-button>
</el-radio-group>

<TemplateConversionPreviewDialog
  v-model="showPreview"
  :preview-data="previewData"
  @confirm="executeConversion"
/>
```

切换流程：

```
点切换 → preview API → 弹预览框 → 用户确认 → execute API → 切换完成 toast
```

### D9 协作锁集成

```python
# 所有动态编辑入口前置锁
@router.post("/dynamic-rows")
async def add_dynamic_row(...):
    async with NoteSectionLockService.acquire(note_section, user, timeout=300):
        # 编辑逻辑
        ...
    # 退出 with 自动释放锁
```

### D10 AI 辅助扩展

```python
# 新增 service
class NoteAIAssistantService:
    async def suggest_dynamic_rows(self, note_section: str, project_id: UUID) -> list[dict]:
        """AI 建议哪些行该动态化."""
        # 1. 查 TB 该章节涉及科目的辅助账
        aux_data = await self._query_aux_balance(...)
        # 2. 若 aux_code 数 > 3 → 建议动态化
        if len(aux_data) > 3:
            return [{'region_name': 'aux_客户', 'rationale': f'检测到 {len(aux_data)} 个辅助账码'}]

    async def generate_paragraph_from_workpaper(self, wp_code: str, section: str) -> str:
        """从底稿摘要 LLM 生成段落（如 H 减值评估 → 商誉减值披露）."""

    async def check_wp_tb_consistency(self, project_id: UUID, year: int) -> list[Issue]:
        """校核 wp_data 取数与 TB 一致."""
```

### D11 章节级版本图

```python
class NoteSectionVersionTree(Base):
    __tablename__ = "note_section_version_tree"
    id: UUID
    project_id: UUID
    note_section: str
    branch: str  # "main" | "v2024_inherit" | "user_branch"
    parent_node_id: UUID | None
    snapshot_data: JSONB
    created_by: UUID
    created_at: datetime
    label: str  # 用户标签
```

支持 git-like 操作：

- `fork(section, branch_name)` 创建新分支
- `merge(branch_a, branch_b, strategy='ours'|'theirs'|'manual')` 合并
- `diff(node_a, node_b)` 对比

### D12 合并↔单体附注映射（v0.4 新增 ⭐）

#### 12.1 模板字段扩展

```json
// 合并版模板章节示例：
{
  "section_id": "consol_section_ar_top5",      // 稳定 ID
  "section_title": "应收账款 - 按欠款单位列示前五名",
  "level": 3,
  "is_consol_only": false,                     // 共有章节，但合并版多列
  "is_standalone_only": false,
  "consol_section_mapping": {
    "child_section_ids": ["section_ar_top5"],   // 单体附注的对应章节 ID
    "format_diff": {
      "extra_columns": [                        // 合并版多的列
        {"column_id": "col_minority_share", "label": "少数股东权益部分"}
      ]
    }
  }
}
```

#### 12.2 binding 新 source 类型 `consol_aggregation`

```json
{
  "primary": {
    "source": "consol_aggregation",
    "child_section_id": "section_ar_top5",
    "aggregation_method": "top_n_after_elimination",
    "child_filter": {
      "scope": "all",                            // all | exclude_inactive | [subsidiary_id_1, ...]
      "subsidiaries": null
    },
    "elimination_rules": [
      {
        "type": "internal_ar",
        "wp_code": "consol_internal_ar",
        "match_by": "label_fuzzy"
      }
    ],
    "aggregation_config": {
      "top_n": 5,
      "merge_same_label_threshold": 0.85         // 模糊合并同名（不同子公司与同一外部客户）
    }
  },
  "fallback": [
    {"source": "manual"}
  ]
}
```

#### 12.3 聚合算法接入

```python
# 新增 backend/app/services/consol_note_aggregation_service.py
class ConsolNoteAggregationService:
    """合并附注从子公司单体附注汇总核心服务."""

    AGGREGATION_METHODS = {
        "simple_sum": _simple_sum,
        "sum_after_elimination": _sum_after_elimination,
        "top_n_after_elimination": _top_n_after_elimination,
        "weighted_avg": _weighted_avg,
        "first_n_concat": _first_n_concat,  # 文字章节拼接
    }

    async def aggregate_section(
        self,
        consol_project_id: UUID,
        consol_note_section_id: str,
        year: int,
    ) -> dict:
        """从所有子公司单体附注汇总到合并附注章节.

        步骤：
          1. 拉取合并项目的子公司清单（consolidation_subsidiaries）
          2. 加载每家子公司单体附注的对应章节（child_section_id）
          3. 按 aggregation_method 聚合 cells
          4. 应用 elimination_rules 抵销内部往来
          5. 按 aggregation_config 重排（如 top_n）
          6. 写入合并附注 + 记录 _cell_provenance（来自 N 家子公司）
        """
        ...
```

#### 12.4 子公司单体附注更新事件 → 合并 stale

```python
# 现有 EventBus 已有 NOTE_SECTION_UPDATED 事件
@on_event("NOTE_SECTION_UPDATED")
async def handle_child_note_updated(event):
    project = await load_project(event.project_id)
    if project.consol_level == 1:  # 是子公司
        # 找出哪些 parent 项目消费了这个子公司
        parents = await find_consol_parents(project.id)
        for parent in parents:
            # 对 parent 的对应章节标 stale
            await mark_stale_by_section_mapping(parent.id, event.note_section)
```

#### 12.5 多层合并 lineage 链

```
孙公司 N 个 (consol_level=1)
  → 子合并项目 (consol_level=2)
    → 总合并项目 (consol_level=3)
```

每层合并附注的 `consol_aggregation` 都引用下一层的 `child_section_id`，通过 `parent_project_id` 链向上递归。

#### 12.6 内部往来抵销规则注册器

```python
# backend/app/services/consol_elimination_rules.py
ELIMINATION_RULES = {
    "internal_ar": {
        "name": "内部应收账款抵销",
        "wp_code": "consol_internal_ar",
        "match_logic": "by_company_pair",  # 按公司对匹配
    },
    "internal_revenue": {...},
    "internal_inventory_unrealized": {...},
    "internal_dividend": {...},
}
```

### D13 标题序号动态层级（v0.4 新增 ⭐）

#### 13.1 数据模型重构

```python
# 模板 JSON 字段重构（V021 migration 迁移历史数据）

# 旧格式：
{
  "section_number": "八、22",      # 字符串，无法重排
  "section_title": "固定资产",
  "sort_order": 822
}

# 新格式：
{
  "section_id": "section_fixed_assets",   # 稳定 ID（不变）
  "section_title": "固定资产",
  "level": 2,                              # 层级 1-5
  "parent_section_id": "section_main_account_notes",  # 父章节 ID
  "sort_index": 22,                        # 同 parent 同 level 内排序
  "auto_numbering": true,                  # 自动编号
  "lock_number": false,                    # 用户锁定
  "rendered_number": null                  # 渲染时计算（不存）
}

# DisclosureNote ORM 也加这些字段
class DisclosureNote(Base):
    section_id: str = mapped_column(String(100), nullable=False)  # 替代 note_section
    level: int
    parent_section_id: str | None
    sort_index: int
    auto_numbering: bool = True
    lock_number: bool = False
    # 兼容字段（迁移期保留）
    note_section: str | None  # 旧 section_number
```

#### 13.2 编号格式注册器

```python
# backend/app/services/note_section_numbering.py

CN_NUMBERS = "一二三四五六七八九十"
CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

def cn_number(i: int) -> str:
    """阿拉伯转中文数字（1-99 支持）."""
    if i <= 10: return CN_NUMBERS[i-1]
    if i < 20: return f"十{CN_NUMBERS[i-10-1]}" if i > 10 else "十"
    tens = i // 10
    ones = i % 10
    return f"{CN_NUMBERS[tens-1]}十{CN_NUMBERS[ones-1] if ones else ''}"

LEVEL_FORMATS = {
    1: lambda i: f"{cn_number(i)}、",
    2: lambda i: f"（{cn_number(i)}）",
    3: lambda i: f"{i}.",
    4: lambda i: f"({i})",
    5: lambda i: CIRCLED_NUMBERS[i-1] if i <= 15 else f"({i})",
}

def render_section_number(level: int, sort_index: int, custom_format: str | None = None) -> str:
    """渲染单层级序号."""
    if custom_format:
        return custom_format.format(i=sort_index, cn=cn_number(sort_index))
    return LEVEL_FORMATS[level](sort_index)
```

#### 13.3 NoteSectionNumberingService 核心

```python
# backend/app/services/note_section_numbering_service.py

class NoteSectionNumberingService:
    """章节编号动态计算服务."""

    async def render_all(
        self,
        project_id: UUID,
        year: int,
        scope: str = "both",  # standalone | consolidated | both
    ) -> dict[str, str]:
        """对所有章节重新计算 rendered_number.

        Returns:
            {section_id: rendered_number}
        """
        notes = await self._load_visible_notes(project_id, year, scope)

        # 按 level + parent_section_id 树形分组
        tree = self._build_section_tree(notes)

        result = {}
        # DFS 遍历，每层维护 sort_index 计数器
        def dfs(node, parent_path: str = ""):
            counter = {}  # level → counter
            for child in sorted(node.children, key=lambda c: c.sort_index):
                if child.is_deleted or child.scope not in (scope, 'both'):
                    continue
                if child.lock_number and child.locked_number:
                    # 用户锁定的序号
                    rendered = child.locked_number
                elif child.auto_numbering:
                    counter.setdefault(child.level, 0)
                    counter[child.level] += 1
                    rendered = render_section_number(child.level, counter[child.level])
                else:
                    rendered = ""
                full = parent_path + rendered
                result[child.section_id] = full
                dfs(child, full)

        for root in tree.roots:
            dfs(root)

        return result
```

#### 13.4 内部引用 ref() 函数

```python
# Jinja filter 注册
def ref(section_id: str, ctx: dict) -> str:
    """渲染章节引用为最新序号."""
    rendered_numbers = ctx['rendered_numbers']
    return rendered_numbers.get(section_id, f"[未知章节: {section_id}]")

NOTE_TEXT_ENV.globals['ref'] = ref
```

模板示例：

```jinja
本期增加情况详见 {{ ref("section_revenue_breakdown") }}。
```

#### 13.5 表格标题参与编号

```json
// 表格也有 level
{
  "section_id": "section_ar",
  "level": 2,
  "tables": [
    {
      "table_id": "ar_classification",
      "title": "应收账款分类",
      "title_level": 3,                  // 表格标题层级
      "title_sort_index": 1
    },
    {
      "table_id": "ar_aging",
      "title": "按账龄披露",
      "title_level": 3,
      "title_sort_index": 2
    }
  ]
}
```

#### 13.6 历史模板迁移策略

```python
# scripts/migrate_section_number_to_section_id.py（一次性）
def migrate():
    """旧 section_number 字符串 → 新 section_id + level + parent_section_id."""
    for note in load_all_notes():
        # 解析 "八、22" → level=2, parent="section_main_account_notes", sort_index=22
        section_id = generate_stable_id(note.section_number, note.section_title)
        level, parent_id, sort_index = parse_section_number(note.section_number)
        note.section_id = section_id
        note.level = level
        note.parent_section_id = parent_id
        note.sort_index = sort_index
        note.note_section_legacy = note.section_number  # 兼容保留
```

#### 13.7 单体↔合并切换

```python
# 同一份 sections，scope='standalone' vs scope='consolidated' 重新渲染
standalone_numbers = await numbering_service.render_all(project_id, year, scope='standalone')
consolidated_numbers = await numbering_service.render_all(project_id, year, scope='consolidated')

# 单体下：
#   一、公司基本情况
#   二、财务报表编制基础
#   三、遵循企业会计准则的声明
#   四、重要会计政策
#   五、税项
#   六、财务报表主要项目注释
#   ...

# 合并下：
#   一、公司基本情况
#   二、财务报表编制基础
#   三、遵循企业会计准则的声明
#   四、重要会计政策
#   五、合并范围                ← 仅合并
#   六、合并财务报表的编制方法     ← 仅合并
#   七、税项
#   八、财务报表主要项目注释
#   九、合并财务报表主要项目注释   ← 仅合并
#   ...
```

#### 13.8 拖拽排序

```typescript
// 前端拖拽 → PATCH /sections/:id/move + body: { new_parent_id, new_sort_index }
// 后端：调整 sort_index → 调用 NoteSectionNumberingService.render_all → 返回新序号字典
// 前端：实时刷新所有章节序号显示
```

## 二、API 变化

### 新增端点（约 20 个）

```
# D1/D2 动态行/列
POST/DELETE /api/disclosure-notes/{note_id}/dynamic-rows{,/{idx}}
POST/DELETE /api/disclosure-notes/{note_id}/dynamic-columns{,/{column_id}}
PUT /api/disclosure-notes/{note_id}/dynamic-rows/sort
PUT /api/disclosure-notes/{note_id}/columns-meta  # 调宽 / 冻结 / 合并表头

# D5 auto_trim v2
POST /api/disclosure-notes/{project_id}/{year}/auto-trim-v2

# D6 集团基线
GET/POST /api/group-note-baselines
GET /api/group-note-baselines/{id}/versions
GET /api/group-note-baselines/{id}/preview-diff
POST /api/projects/{project_id}/apply-group-baseline
GET /api/projects/{project_id}/baseline-sync-status

# D7 文字段落
GET /api/disclosure-notes/{note_id}/text-template-vars
PUT /api/disclosure-notes/{note_id}/text-template-vars
POST /api/disclosure-notes/{note_id}/preview-text  # 实时渲染预览

# D8 合并附注
GET /api/projects/{project_id}/consol-notes-integration-preview

# D10 AI 辅助
POST /api/disclosure-notes/{note_id}/ai/suggest-dynamic-rows
POST /api/disclosure-notes/{note_id}/ai/generate-from-workpaper
POST /api/disclosure-notes/{project_id}/{year}/ai/check-consistency

# D11 章节版本图
GET /api/disclosure-notes/{note_id}/version-tree
POST /api/disclosure-notes/{note_id}/fork
POST /api/disclosure-notes/{note_id}/merge
GET /api/disclosure-notes/{note_id}/diff?node_a=...&node_b=...
```

## 三、CI 卡点（共 22 项）

- CI-1：`_dynamic_regions` idx/col_id 有效性
- CI-2：row_type=dynamic_* 在 region 内
- CI-3：column_id 全表唯一
- CI-4：REGION/WP 公式解析
- CI-5：动态行/列删除合计 PBT
- CI-6：round-trip 无丢失 PBT
- CI-7：apply_baseline 后 lineage 必有 baseline_id
- CI-8：auto_trim v2 三级互斥
- CI-9：fallback 链最多 3 级（防深嵌套性能崩）
- CI-10：`_cell_provenance` 必有 source 字段
- CI-11：D7 段落 Jinja 模板必有变量声明
- CI-12：D8 合并章节序号不与单体冲突
- CI-13：D9 锁释放必触发
- CI-14：D11 版本树无环（DAG 校验）
- **CI-15：D12 consol_aggregation source 必有 child_section_id**
- **CI-16：D12 多层合并 lineage 链无环**
- **CI-17：D12 elimination_rules 引用的 wp_code 必存在**
- **CI-18：D13 section_id 全局唯一 + level 1-5 范围 + parent_section_id 引用有效**
- **CI-19：D13 章节序号渲染后 rendered_number 在 scope 内唯一**
- **CI-20（v0.6）：D14 国企↔上市互转 round-trip PBT（用户编辑 cell 切换两次后必无丢失）**
- **CI-21（v0.6.2）：D15 离线导出包 _meta_ sheet 必有 section_id + binding hash**
- **CI-22（v0.6.2）：D15 导入时 section_id 匹配 + 字段级 diff 完整性 PBT（导出→导入 round-trip 无丢失）**

## 四、变更影响范围（v0.6.2）

| 模块 | 改动 | 工作量 |
|------|------|--------|
| 模板 JSON 数据 | 60+ 动态 + 30+ wp_data + 20+ Jinja + **150+ 合并↔单体映射** + **173 章节 section_id 化** | 4.5 人天（依赖 P-1~P-6） |
| `disclosure_engine.py` | _expand_dynamic + _extract_wp + fallback 链 | 2 人天 |
| `note_cell_merge.py` | 行+列三态合并 | 0.5 人天 |
| `note_formula_generator.py` | REGION/WP 函数 | 0.5 人天 |
| `note_trim_service.py` | auto_trim v2 三级 | 0.5 人天 |
| 新建 `group_note_baseline_service.py` | 集团基线 | 1 人天 |
| 新建 `note_text_template_engine.py` | Jinja 渲染 | 0.5 人天 |
| 改造 `consol_disclosure_service.py` | D8 衔接 | 1 人天 |
| **新建 `consol_note_aggregation_service.py`** | **D12 合并↔单体汇总** | **1.5 人天** |
| **新建 `consol_elimination_rules.py`** | **D12 抵销规则注册** | **0.5 人天** |
| **新建 `note_section_numbering_service.py`** | **D13 序号动态计算** | **1 人天** |
| 新建 `note_section_lock_integration.py` | D9 集成 | 0.5 人天 |
| 扩展 `note_ai.py` | D10 三个新接口 | 1 人天 |
| 新建 `note_section_version_tree_service.py` | D11 版本图 | 1 人天 |
| `note_word_exporter.py` | 动态 + 空替换 + Jinja + 合并双列 + **序号自动重排** | 1.2 人天 |
| 新增 router 文件（5 个） | **25 端点（+5: 汇总/抵销/序号/单体↔合并切换/拖拽排序）** | 1.2 人天 |
| 前端 `NoteTableEditor.vue` 大改 | 全维度 UI | 2.5 人天 |
| 前端 8 个新 composable | 调动态/基线/段落/AI/版本/锁 + **汇总/序号** | 2 人天 |
| 前端段落变量编辑器 | D7 编辑 + 实时预览 | 1 人天 |
| 前端版本树可视化 | D11 git-like 图 | 1 人天 |
| 前端 AI 建议侧栏 | D10 集成 | 0.5 人天 |
| **前端合并↔单体切换 + 章节树拖拽** | **D12/D13 UI** | **1.5 人天** |
| **前端章节序号实时渲染** | **D13 实时序号** | **0.5 人天** |
| DB migrations（V019/V020/V021/**V022**） | lineage / baseline / version_tree + **section_id 重构** | 1 人天 |
| **历史模板迁移脚本** | **`migrate_section_number_to_section_id.py`** | **0.5 人天** |
| **新建 `note_conversion_service` 升级 + `note_template_diff.py`** | **D14 国企↔上市丝滑切换 + 跨模板合并汇总 + 章节差异管理** | **2.5 人天** |
| **前端切换 UI（D14 切换器 + 预览弹窗 + 进度条）** | **D14 互转 UX** | **1 人天** |
| **新建 `note_offline_export_service.py` + `note_offline_import_service.py`** | **D15 xlsx 导出 + 一键导入字段级 diff** | **1.5 人天** |
| **前端导入冲突 diff 预览 UI** | **D15 章节级 / cell 级冲突选择** | **0.5 人天** |
| 测试 | 单测 + PBT + UAT（含 CI-20 / CI-21 / CI-22） | 2.5 人天 |
| **合计** | | **38.5 人天** + P-1~P-7 共 5 人天 |

## 五、ADR 新增

- ADR-011：附注双 sidecar 设计
- ADR-012：集团模板 lineage 模型
- ADR-013：多源 fallback 链 vs 单源 binding
- ADR-014：文字段落 Jinja 渲染 vs 字符串模板
- ADR-015：合并附注章节序号策略
- ADR-016：章节级版本图 git-like vs 线性
- **ADR-017（v0.4）：合并↔单体附注章节映射（consol_aggregation source 类型）**
- **ADR-018（v0.4）：内部往来抵销规则注册器（按 wp_code 配置）**
- **ADR-019（v0.4）：附注章节编号体系重构（section_number 字符串 → section_id + level + parent + sort_index）**
- **ADR-020（v0.4）：章节序号 5 级层级格式注册器**
- **ADR-021（v0.6）：国企↔上市丝滑切换（差异清单驱动 + 互转 round-trip 数据保留 + 跨模板合并汇总）**
- **ADR-022（v0.6.2）：附注离线分发包格式（xlsx + _meta_ sheet stable section_id + 4 色单元格语义 + DataValidation 锁定 + 字段级 diff 导回）**

## 六、回退策略

各维度 feature flag 独立：

```python
# settings.py
NOTE_DYNAMIC_ROWS_ENABLED: bool = true
NOTE_DYNAMIC_COLUMNS_ENABLED: bool = true
NOTE_WP_DATA_BINDING_ENABLED: bool = true
NOTE_FALLBACK_CHAIN_ENABLED: bool = true
NOTE_AUTO_TRIM_V2_ENABLED: bool = true
NOTE_GROUP_BASELINE_ENABLED: bool = false  # v1 默认关
NOTE_TEXT_JINJA_ENABLED: bool = true
NOTE_CONSOL_INTEGRATION_V2_ENABLED: bool = false
NOTE_SECTION_LOCK_INTEGRATION: bool = true
NOTE_AI_DYNAMIC_SUGGEST: bool = false
NOTE_SECTION_VERSION_TREE: bool = false
# v0.4 新增：
NOTE_CONSOL_AGGREGATION_ENABLED: bool = false  # D12 合并↔单体汇总
NOTE_DYNAMIC_NUMBERING_ENABLED: bool = false   # D13 动态序号（默认关，迁移期）
```

任一维度出问题 → flag 关掉回退。

## 七、实施顺序优化（v0.4 关键路径）

由于 D13 序号重构影响所有现有章节，建议**优先级提到 Sprint 0**（在数据模型之前）：

```
Sprint 0 (新增, 1.5 人天)：D13 section_id 数据迁移
  ├─ V022 migration（DisclosureNote 加 section_id/level/parent_section_id/sort_index）
  ├─ migrate_section_number_to_section_id.py 一次性脚本
  └─ NoteSectionNumberingService 核心 + 单测

Sprint 1 (1.5 人天)：双 sidecar 数据模型（其他维度）
Sprint 2-12 (按 v0.3)
Sprint 13 (新增, 2 人天)：D12 合并↔单体映射
  ├─ consol_aggregation source 类型
  ├─ ConsolNoteAggregationService
  ├─ elimination rules
  └─ 多层 lineage 链
```
