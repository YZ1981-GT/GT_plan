# 核对表底稿完整渲染 Design

## Overview

A1-15/A1-16 是大型 docx 核对表（934/653 行），当前被错误路由到 `a-program-console`（仅 18 步骤）。修复策略：新增 `checklist-table` componentType + docx 解析器 + 前端核对表组件。

**设计原则**：以"如何最好地呈现原始内容"为第一目标，不拘泥于现有渲染框架的形式约束。

## 实证数据（已用 python-docx 验证）

### A1-15 结构
```
表1: 封面信息 (25行, 忽略)
表2: 目录 (49行, 35个章节目录项 + 适用Y/N)
表3: 核对表主体 (934行 × 3逻辑列)
  - col0: 准则索引号 (如 "CAS 30.5", "CAS 33.4")
  - col1: 核对条目正文 (如 "1 财务报表编制应当以持续经营假设为基础。")
  - col2: 适用(Y)/不适用(N) (模板中为空，待用户填写)
  
  章节切分标记: 表头行重复出现 "准则索引号 | x.x 标题 | 适用..."
  35个章节 (1.1~5.0)，覆盖 CAS 全部列报和披露准则
  章节内小节标题: 合并单元格行 (363个)
  实际核对条目: 570行
```

### A1-16 结构
```
表1: 653行 × 14物理列 → 3逻辑列 (大量合并单元格)
  - 逻辑col0: 法规索引 (如 "Art. 13", "法规：编报规则15号")
  - 逻辑col1: 核对条目正文
  - 逻辑col2: 适用标记 (最后一列)
  
  前9行: 封面+使用说明 (忽略)
  数据行: ~640行
```

### 两份文件共性
- 逻辑结构一致：**索引号 + 核对条目 + 适用标记**
- 内容分层：大章节(表头行重复) > 小节标题(合并单元格) > 核对条目
- 原模板仅有 Y/N 标记列，平台需扩展：备注 + 底稿索引

## Root Cause（代码验证）

```python
# backend/app/services/wp_classification_service.py
_WP_CODE_OVERRIDE = {
    "A1": "a1-dashboard",
    "A2": "a2-adjustment-console",
    "A16": "word-template",       # ← 注意: "A16" ≠ "A1-16"
    ...
    # A1-15 和 A1-16 不在此字典中
}
# → 落入前缀匹配: class_code "A-程序表" → "a-program-console"
```

**关键细节**: `"A16"` 是管理层声明书（wp_code=A16），`"A1-16"` 是核对表（wp_code=A1-16），两者不同。

## Fix Design

### P0: 完整渲染核对表内容（核心）

#### Change 1 — componentType 路由注册

**File**: `backend/app/services/wp_classification_service.py`

```python
_WP_CODE_OVERRIDE["A1-15"] = "checklist-table"
_WP_CODE_OVERRIDE["A1-16"] = "checklist-table"
# VALID_COMPONENT_TYPES 加 "checklist-table"
```

#### Change 2 — docx 核对表解析器

**File**: `backend/app/services/checklist_docx_parser.py`（新建）

核心逻辑：将两种不同格式的 docx 统一解析为同一结构化 JSON。

```python
# 输出格式
{
  "wp_code": "A1-15",
  "title": "企业会计准则有关财务报表列报及披露核对表",
  "sections": [
    {
      "id": "S01",
      "title": "1.1 财务报表的列报",
      "items": [
        {
          "id": "S01-001",
          "type": "actionable",           # actionable=需填Y/N | guidance=提示性 | header=小节标题
          "standard_ref": "CAS 30.5",     # 准则索引号
          "content": "1 财务报表编制应当以持续经营假设为基础。",
          "children": [                    # 提示性子项挂在主条目下
            {
              "id": "S01-001-a",
              "content": "a. 具体条件说明...",
              "standard_ref": "CAS 30.5(1)"
            }
          ]
        }
      ]
    }
  ],
  "toc": [                                  # 仅 A1-15 有目录表
    {"id": "S01", "title": "1.1 财务报表的列报", "applicable": null}
  ],
  "stats": {
    "total_actionable": 570,              # 需要填Y/N的主条目数(非合并行+有准则索引)
    "total_guidance": 145,                # 提示性子项数(合并行a/b/c)
    "total_sections": 35
  },
  "parsed_at": "..."
}
```

**解析策略**：
- 主条目判定（actionable）：非合并行 + col0 有准则索引号（匹配 `^(CAS|IG|ISA|Art|法规)` 等）
- 提示性子项（guidance）：合并单元格行 + col1 以 a~j 字母加点开头（如 "a. "/"b. "）→ 挂到最近上方 actionable 的 `children`
- 小节标题（header）：合并单元格行 + 非字母子项开头（如 "列报基础"/"财务报表的组成"）
- A1-15: 跳过表1(封面)，解析表2(目录→toc)，解析表3(章节切分靠"准则索引号"表头行重复出现)
- A1-16: 跳过前9行(封面+说明)，按相邻列值去重得到3逻辑列，章节切分靠章节标题行

#### Change 3 — 模板解析全局缓存

**设计决策**：模板内容是静态的（所有项目共享同一 docx），不应每个 working_paper 实例存一份。

```python
# 缓存策略：内存 LRU + 文件 mtime 检测
_CHECKLIST_TEMPLATE_CACHE: dict[str, tuple[float, dict]] = {}  # wp_code → (mtime, parsed)

async def get_checklist_template(wp_code: str) -> dict:
    """全局缓存，mtime 变化才重新解析"""
    file_path = _get_template_path(wp_code)
    mtime = os.path.getmtime(file_path)
    if wp_code in _CHECKLIST_TEMPLATE_CACHE:
        cached_mtime, cached_data = _CHECKLIST_TEMPLATE_CACHE[wp_code]
        if cached_mtime == mtime:
            return cached_data
    parsed = parse_checklist_docx(file_path, wp_code)
    _CHECKLIST_TEMPLATE_CACHE[wp_code] = (mtime, parsed)
    return parsed
```

#### Change 4 — render-config 集成

**File**: `backend/app/routers/wp_render_config.py`

```python
if component_type == "checklist-table":
    # 模板结构从全局缓存取（静态，不存每个 wp）
    template_data = await get_checklist_template(wp_code)
    # 用户填写数据从 checklist_responses 表取
    responses = await get_checklist_responses(db, wp_id)
    sheet_html_data = {
        "template": template_data,
        "responses": responses,  # {item_id: {conclusion, remark, wp_ref}}
    }
```

#### Change 5 — 用户填写数据持久化

**File**: `backend/migrations/V085__checklist_responses.sql`

```sql
CREATE TABLE IF NOT EXISTS checklist_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    item_id VARCHAR(20) NOT NULL,       -- 如 "S01-001"
    conclusion VARCHAR(5),              -- 'Y'/'N'/'NA'/null
    remark TEXT,
    wp_ref VARCHAR(100),                -- 底稿索引引用
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(wp_id, item_id)
);
CREATE INDEX idx_checklist_resp_project ON checklist_responses(project_id);
```

**File**: `backend/app/routers/checklist_responses.py`（新建）

- `GET /api/workpapers/{wp_id}/checklist-responses` — 获取已填写数据
- `PUT /api/workpapers/{wp_id}/checklist-responses` — 批量保存（单次提交整章节）
- 注册到 `router_registry/workpaper.py`

#### Change 6 — 前端核对表组件

**File**: `audit-platform/frontend/src/components/workpaper/GtChecklistTable.vue`（新建）

**呈现设计**（以最佳内容呈现为第一目标）：

```
┌─────────────────────────────────────────────────────────────────┐
│ 📋 企业会计准则有关财务报表列报及披露核对表    进度: 128/570 (22%) │
├─────────────────────────────────────────────────────────────────┤
│ [目录导航侧栏]          │ [核对表主体]                           │
│                          │                                       │
│ ▼ 1 通用列报项目         │ § 1.1 财务报表的列报                  │
│   1.1 财务报表列报 ✓     │ ┌──────┬───────────────┬────┬────┬──┐ │
│   1.2 现金流量表         │ │索引号│核对条目        │适用│备注│索引│ │
│   1.3 合并财务报表       │ ├──────┼───────────────┼────┼────┼──┤ │
│ ▼ 2 资产负债表项目       │ │CAS   │列报基础        │    │    │  │ │
│   2.1 存货               │ │30.5  │1 财务报表编制应│ Y ▼│    │  │ │
│   2.2 金融工具           │ │      │  当以持续经营  │    │    │  │ │
│   ...                    │ │CAS   │2 如企业以持续  │ NA▼│注1 │  │ │
│                          │ │30.4  │  经营...       │    │    │  │ │
│                          │ └──────┴───────────────┴────┴────┴──┘ │
└─────────────────────────────────────────────────────────────────┘
```

**内容分类（实证分析）**：

934 行中按角色分为 3 类：
- **可操作条目**（~570 行）：非合并行 + 有准则索引号(col0非空) = 用户需要填 Y/N 的核对项
- **提示性子项**（~145 行）：合并单元格行且 a/b/c/d 开头 = 是上方主条目的条件/细节展开，默认折叠
- **结构性行**（~218 行）：合并单元格的小节标题 + 章节表头 = 纯导航/分组用

**判定规则精确定义**：
- actionable 判定 ≠ "有数字编号开头"（太窄，只匹配~25行）
- actionable 判定 = "非合并行 + col0 有准则索引"（如 CAS/IG/ISA 开头均算）
- guidance = 合并行且 a~j 字母开头（条件列举子项）
- header = 合并行且非字母子项开头（纯标题文字）

**交互设计原则**：提示性子项(a/b/c条件)默认折叠在主条目下，避免信息重复和视觉噪音。主条目数量~570，每章节平均~16条，交互密度适中。

**核心特性**：
1. **左侧目录导航**：35 章节树形结构，点击跳转，已完成章节标绿 ✓
2. **右侧核对表主体**：
   - **主条目行**（有编号）：完整展示 = 索引号 + 条目正文 + Y/N/NA 下拉 + 备注 + 底稿索引
   - **提示性子项**（a/b/c 条件说明）：默认折叠在主条目下方，点击主条目展开/收起
     - 展开后灰色缩进显示，仅供参考不可编辑
     - 展开图标（▶/▼）提示有详细内容
   - **小节标题**：加粗分隔行，不可交互
3. **适用性填写**：仅主条目行有 Y/N/NA 下拉，选择后变色（Y=绿/N=红/NA=灰）
4. **根据项目情况隐藏不适用章节**：
   - 目录表（表2）有"适用Y/不适用N"列 → 章节级适用性标记
   - 标记为 N 的章节默认折叠+灰显（节省视线，需要时展开查看）
   - 弹窗确认：首次打开时弹窗让用户勾选本项目适用的章节（如非上市→跳过 A1-16 全部内容；无保险合同→跳过 4.6）
5. **自动保存**：修改后 debounce 2s 调 PUT
6. **进度条**：仅计算可操作主条目(~570)的已填/总数（不含提示性子项和标题）
7. **性能**：按章节切换渲染（最大章节 208 行，普通 DOM 足够）

#### Change 7 — htmlRendererRegistry 注册

```typescript
// htmlRendererRegistry.ts
{
  componentType: 'checklist-table',
  component: () => import('./GtChecklistTable.vue'),
  icon: '✅',
  label: '核对表',
  emits: ['save'],
}
```

### P1: 搜索 + 批量操作

- 全局搜索框：按条目文本/准则索引过滤，高亮匹配
- 章节批量标记：整章节"全部适用"/"全部不适用"
- 筛选视图：仅看未填/仅看"不适用"

### P2: 跨底稿联动（可选）

- 监听 `WORKPAPER_SAVED` 事件
- 核对条目中如果引用了某个底稿（wp_ref 填了 "D2-3"），当 D2-3 完成时自动标记该条目
- 前端显示绿色"已完成"徽章
- 需要 `checklist_responses.linked_wp_code` 字段 + `checklist_linkage_service.py`

## Testing Strategy

### 核心验证
1. `derive_component_type` 对 A1-15/A1-16 返回 `checklist-table`
2. docx parser 对 A1-15 提取 35 章节、570 个核对条目
3. docx parser 对 A1-16 提取 ~640 行核对条目
4. 前端组件接收 template+responses 数据正确渲染
5. PUT 端点批量保存/GET 读取一致性

### 回归防护
- 所有其他 wp_code 的 `derive_component_type` 返回值不变
- `a-program-console` 组件对 xlsx 底稿行为不变
- htmlRendererRegistry 现有 11 类组件测试通过
