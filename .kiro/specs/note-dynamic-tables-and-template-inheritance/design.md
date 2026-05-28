# 附注模块全维度增强 — 设计文档

> 版本：v0.3（草稿，2026-05-28）
> 关联需求：requirements.md（92 验收 / 11 维度 D1-D11）

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

### D8 合并附注衔接

```python
# 改进 ConsolDisclosureService
class ConsolDisclosureServiceV2:
    """合并附注衔接，与单体附注 173 章节深度融合."""

    async def integrate_with_standalone_notes(
        self, project_id: UUID, year: int
    ) -> list[DisclosureNote]:
        """
        合并项目（consol_level >= 2）独有：
          1. 单体附注 173 章节生成（基础数据用 parent project 的合并 TB）
          2. 合并专用 7 章节插入合理位置（不再 sort_order=100 写死）
          3. 抵销前后双列：内部交易章节自动加「抵销前/抵销后」列
          4. 多层级 lineage：subsidiaries 列表自动汇总
        """
        # 改用 sort_order 的章节序号语义（"五、合并财务报表主要项目注释" 大类下分小类）
        ...

    async def expand_consol_subsidiaries_realtime(self, project_id: UUID, year: int):
        """每次生成附注时，重新拉取子公司清单（动态行）."""
        subs = await self.db.execute(...)  # consolidation_subsidiaries
        return [{'label': s.name, 'col_holding_pct': s.holding_pct, ...} for s in subs]
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

## 三、CI 卡点（共 14 项）

- CI-1：`_dynamic_regions` idx/col_id 有效性
- CI-2：row_type=dynamic_* 在 region 内
- CI-3：column_id 全表唯一
- CI-4：REGION/WP 公式解析
- CI-5：动态行/列删除合计 PBT
- CI-6：round-trip 无丢失 PBT
- CI-7：apply_baseline 后 lineage 必有 baseline_id
- CI-8：auto_trim v2 三级互斥
- **CI-9（v0.3）：fallback 链最多 3 级（防深嵌套性能崩）**
- **CI-10：`_cell_provenance` 必有 source 字段**
- **CI-11：D7 段落 Jinja 模板必有变量声明（防 undefined 静默）**
- **CI-12：D8 合并章节序号不与单体冲突（uniq check）**
- **CI-13：D9 锁释放必触发（with 退出 + 5min 超时）**
- **CI-14：D11 版本树无环（DAG 校验）**

## 四、变更影响范围（v0.3）

| 模块 | 改动 | 工作量 |
|------|------|--------|
| 模板 JSON 数据 | 60+ 动态 + 30+ wp_data + 20+ Jinja | 2.5 人天（依赖 P-1/P-2/P-3） |
| `disclosure_engine.py` | _expand_dynamic + _extract_wp + fallback 链 | 2 人天 |
| `note_cell_merge.py` | 行+列三态合并 | 0.5 人天 |
| `note_formula_generator.py` | REGION/WP 函数 | 0.5 人天 |
| `note_trim_service.py` | auto_trim v2 三级 | 0.5 人天 |
| 新建 `group_note_baseline_service.py` | 集团基线 | 1 人天 |
| 新建 `note_text_template_engine.py` | Jinja 渲染 | 0.5 人天 |
| 改造 `consol_disclosure_service.py` | D8 衔接 | 1 人天 |
| 新建 `note_section_lock_integration.py` | D9 集成 | 0.5 人天 |
| 扩展 `note_ai.py` | D10 三个新接口 | 1 人天 |
| 新建 `note_section_version_tree_service.py` | D11 版本图 | 1 人天 |
| `note_word_exporter.py` | 动态行/列 + 空表替换 + Jinja Word + 合并双列 | 1 人天 |
| 新增 router 文件（4 个） | 20 端点 | 1 人天 |
| 前端 `NoteTableEditor.vue` 大改 | 全维度 UI | 2.5 人天 |
| 前端 6 个新 composable | 调动态/基线/段落/AI/版本/锁 | 1.5 人天 |
| 前端段落变量编辑器 | D7 编辑 + 实时预览 | 1 人天 |
| 前端版本树可视化 | D11 git-like 图 | 1 人天 |
| 前端 AI 建议侧栏 | D10 集成 | 0.5 人天 |
| DB migrations（V019/V020/V021） | lineage / baseline / version_tree | 0.5 人天 |
| 测试 | 单测 + PBT + UAT | 2 人天 |
| **合计** | | **22 人天** + P-1/P-2/P-3/P-4 共 3 人天 |

## 五、ADR 新增

- ADR-011：附注双 sidecar 设计
- ADR-012：集团模板 lineage 模型
- **ADR-013（v0.3）：多源 fallback 链 vs 单源 binding**
- **ADR-014（v0.3）：文字段落 Jinja 渲染 vs 字符串模板**
- **ADR-015（v0.3）：合并附注章节序号策略**
- **ADR-016（v0.3）：章节级版本图 git-like vs 线性**

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
NOTE_CONSOL_INTEGRATION_V2_ENABLED: bool = false  # 待 D8 完成
NOTE_SECTION_LOCK_INTEGRATION: bool = true
NOTE_AI_DYNAMIC_SUGGEST: bool = false  # 依赖 LLM
NOTE_SECTION_VERSION_TREE: bool = false  # v2 考虑前置
```

任一维度出问题 → flag 关掉回退。
