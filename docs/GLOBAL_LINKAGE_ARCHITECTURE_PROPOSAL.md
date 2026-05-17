# 全局联动架构改进方案

> 目标：彻底双向联动、完整性、企业级、可扩展
> 日期：2026-05-17
> 基于：代码考古实测（非推测）

---

## 一、现状诊断（基于 grep + 代码阅读）

### 1.1 底稿模板了解程度

| 维度 | 状态 | 数据量 |
|------|------|--------|
| 477 文件名称 | ✅ 全部清楚 | 179 主编码 |
| 2737 sheet 名称 | ✅ 全部扫描 | template_content_map.json |
| 行/列表头语义 | ✅ 启发式抓取 | 239,693 锚点 |
| 关键单元格物理坐标 | ✅ 已入库 | 374,826 个 |
| 跨 sheet 公式依赖 | ✅ 自动提取 | 42,163 条 |
| 109 个 docx 内容 | ❌ 完全未扫描 | 0 |
| 单元格业务语义核对 | ⚠️ 机器抓取未人工校对 | 误差率未知 |

### 1.2 现有联动机制（两套并存，互不通信）

```
机制 A：EventBus 事件驱动（后端，已跑通）
─────────────────────────────────────────
ADJUSTMENT_CREATED/UPDATED/DELETED
  → TrialBalanceService.on_adjustment_changed → TB 重算
  → mark_stale(project_id, account_codes) → WorkingPaper.prefill_stale=True
  → _invalidate_formula_cache → Redis 清缓存

DATA_IMPORTED / LEDGER_DATASET_ACTIVATED
  → TrialBalanceService.on_data_imported → TB 全量重算
  → mark_stale(project_id) → 全部底稿 prefill_stale=True
  → _invalidate_formula_cache_all

TRIAL_BALANCE_UPDATED
  → ReportEngine.on_trial_balance_updated → 报表增量更新
  → 发布 REPORTS_UPDATED

REPORTS_UPDATED
  → DisclosureEngine.on_reports_updated → 附注增量更新
  → AuditReportService.on_reports_updated → 审计报告刷新

WORKPAPER_SAVED
  → consistency_check → 一致性校验
  → 前端 eventBus 'workpaper:saved' → 附注同步

LEDGER_DATASET_ROLLED_BACK
  → AuditReport.is_stale=True + DisclosureNote.is_stale=True

机制 B：Address Registry V2（前端+后端，刚做）
─────────────────────────────────────────
WorkpaperEditor.onSave
  → useStaleImpact.notify({sheet})
  → POST /v2/notify-cell-change
  → 后端 BFS resolved_refs + L3 公式依赖
  → 返回 stale_targets[] 给前端展示
```

### 1.3 两套机制的断裂点

| 场景 | 机制 A | 机制 B | 结果 |
|------|--------|--------|------|
| 调整分录改 → 底稿 stale | ✅ mark_stale | ❌ 不触发 | 底稿标 stale 但前端无即时反馈 |
| 底稿保存 → 下游底稿 stale | ❌ 不触发 | ✅ BFS 计算 | 前端看到但后端不标 prefill_stale |
| 报表改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 公式管理改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 附注改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 底稿保存 → 附注 stale | ✅ eventBus | ❌ 不触发 | 只走 A 不走 B |

### 1.4 预填充双路径并存

```
路径 1：生成时（wp_template_init_service.py）
  读 prefill_formula_mapping.json → 按语义名称（"期初余额"）找行 → openpyxl 写值
  119 条映射 / 9 种公式类型 / 语义行匹配

路径 2：编辑时（prefill_engine.py:prefill_workpaper_real）
  直接扫 xlsx 内嵌 =TB()/=WP() 公式 → FormulaEngine 执行 → 写 structure.json
  不读 mapping json / 物理坐标匹配

两条路径数据源不同、匹配方式不同、写入目标不同。
```

### 1.5 公式引擎现状

```
report_engine.py:ReportFormulaParser
  → 解析 report_config.formula 字段
  → TB()/SUM_TB()/ROW()/SUM_ROW()/PREV()
  → 从 trial_balance 表取数
  → 写入 financial_report 表

prefill_engine.py:FormulaEngine
  → 解析底稿 xlsx 内嵌公式
  → TB/SUM_TB/WP/AUX/PREV/ADJ/LEDGER/NOTE/TB_AUX
  → 从 trial_balance/tb_ledger/tb_aux_balance/adjustments/disclosure_notes 取数
  → 写入 structure.json

formula_unified.py
  → 统一公式引擎（兼容旧 API）
  → safe_eval + FormulaResult

三套公式引擎并存，各管一段。
```

---

## 二、核心问题总结

1. **单向链路**：数据只从上游流向下游（TB→报表→附注），反向无感知
2. **两套 stale 机制不互通**：后端 prefill_stale 字段 vs 前端 Address Registry BFS
3. **公式管理改动无联动**：report_config.formula 改了，不通知任何底稿
4. **三套公式引擎各管一段**：report_engine / prefill_engine / formula_unified 不共享依赖图
5. **docx 类底稿完全脱离**：109 个 Word 底稿不在任何联动链路中
6. **语义→物理翻译不可靠**：L2 锚点启发式抓取，"审定数"在不同 sheet 可能落在不同列

---

## 三、改进方案：统一联动总线（Unified Linkage Bus）

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Linkage Bus                            │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 底稿模块  │  │ 报表模块  │  │ 附注模块  │  │ 调整分录  │        │
│  │ Workpaper │  │ Report   │  │ Note     │  │ Adjustment│        │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘        │
│        │              │              │              │              │
│        ▼              ▼              ▼              ▼              │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Dependency Graph（统一依赖图）                   │     │
│  │                                                          │     │
│  │  节点 = 任何可寻址对象：                                    │     │
│  │    WP:D2:审定表D2-1:未审数  （底稿单元格）                  │     │
│  │    REPORT:BS-005::当期金额  （报表行次）                   │     │
│  │    NOTE:5.7:应收账款:期末余额 （附注表格单元格）           │     │
│  │    ADJ:1122::aje_net        （调整分录科目净额）           │     │
│  │    TB:1122::期末余额        （试算表科目余额）             │     │
│  │    FORMULA:BS-005::公式定义  （公式配置行）                │     │
│  │                                                          │     │
│  │  边 = 数据依赖关系：                                       │     │
│  │    TB:1122::期末余额 → WP:D2:审定表D2-1:未审数            │     │
│  │    WP:D2:审定表D2-1:审定数 → REPORT:BS-005::当期金额      │     │
│  │    WP:D2:审定表D2-1:审定数 → NOTE:5.7:应收账款:期末余额   │     │
│  │    ADJ:1122::aje_net → WP:D2:审定表D2-1:AJE调整           │     │
│  │    FORMULA:BS-005::公式定义 → REPORT:BS-005::当期金额      │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Stale Propagation Engine                        │     │
│  │                                                          │     │
│  │  任何节点变更 → BFS 遍历出边 → 标记下游 stale             │     │
│  │  支持双向：                                               │     │
│  │    正向：源改 → 下游 stale                                │     │
│  │    反向：公式/配置改 → 所有引用该公式的节点 stale          │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Notification Layer                              │     │
│  │                                                          │     │
│  │  后端：写 DB stale 字段 + 发 EventBus 事件                │     │
│  │  前端：SSE 推送 + 编辑器黄条 + 模块级 badge               │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 统一寻址格式（URI）

```
格式：{module}:{code}:{sheet_name}:{label}

规则：
  module     = 模块标识（WP/REPORT/NOTE/ADJ/TB/FORMULA）
  code       = 模块内编码（D2/BS-005/5.7/1122）
  sheet_name = Excel sheet 精确标签名（如"折旧分配分析表H1-13"），非 Excel 模块留空
  label      = 语义标签（"销售费用折旧"/"期初余额"/"审定数"）

关键设计决策：
  ✓ label 用语义描述（稳定，不受插入行影响）
  ✗ 不用物理坐标（D13/C10 会因插入行而漂移）
  ✓ sheet_name 用 Excel 精确标签名（天然唯一，每个文件内不重复）
  ✓ 物理坐标只在运行时动态解析（打开 xlsx 搜索行列表头定位）

示例：
  WP:H1:折旧分配分析表H1-13:销售费用折旧     底稿 H1 折旧分配表中的销售费用折旧金额
  WP:H1:折旧分配分析表H1-13:管理费用折旧     底稿 H1 折旧分配表中的管理费用折旧金额
  WP:H1:折旧分配分析表H1-13:生产成本折旧     底稿 H1 折旧分配表中的生产成本折旧金额
  WP:D2:审定表D2-1:期初余额                  底稿 D2 审定表中的期初余额
  WP:D2:审定表D2-1:审定数                    底稿 D2 审定表中的审定数
  WP:D2:审定表D2-1:AJE调整                   底稿 D2 审定表中的 AJE 调整金额
  WP:K8:审定表K8-1:折旧费                    底稿 K8 管理费用审定表中的折旧费行
  REPORT:BS-005::当期金额                     报表资产负债表第 5 行当期金额
  REPORT:IS-001::当期金额                     利润表第 1 行
  NOTE:5.7:应收账款:期末余额                  附注 5.7 节应收账款期末余额
  ADJ:1122::aje_net                           科目 1122 的 AJE 净额
  TB:1122::期末余额                           试算表 1122 期末余额
  FORMULA:BS-005::公式定义                    报表公式配置（改公式本身触发）
  FORMULA:prefill:D2:期初余额                 预填充公式配置

运行时解析流程（label → 物理坐标）：
  1. 根据 wp_code + sheet_name 打开对应 xlsx 文件
  2. 扫描 sheet 全部行列（不限前 3 行），找到 label 文本所在的行或列
  3. 结合行列交叉点确定物理坐标（如"销售费用"在 D 列表头，"合计"在第 13 行 → D13）
  4. 缓存结果（同一模板结构不变，只需解析一次）
  5. 用户插入行后，下次打开重新解析（label 不变，坐标自动更新）
```

### 3.3 地址解析三层优先级 + 用户手动校正

系统自动识别表头位置不可能 100% 准确（审计底稿前 5-8 行是标题/公司名/日期装饰行，真正数据表头在更深处），必须支持用户手动校正，且校正结果持久化为全局规则。

```
解析优先级（高→低）：
┌─────────────────────────────────────────────────────────────────┐
│ 1. address_label_overrides.json → overrides                      │
│    用户手动指定 label → (row, col)，最高优先                      │
│    例：H1:折旧分配分析表H1-13:销售费用折旧 → {row:13, col:"D"}   │
│                                                                   │
│ 2. address_label_overrides.json → header_rules                   │
│    用户指定某 sheet 的数据起始行/列表头行/行表头列                 │
│    系统按此规则重新扫描（替代默认"前 3 行"启发式）                │
│    例：H1:折旧分配分析表H1-13 → {data_start_row:7, col_header:7} │
│                                                                   │
│ 3. 系统自动启发式识别（兜底）                                     │
│    改进后算法：找"数据区域首行"而非固定前 3 行                    │
│    特征：连续多非空短文本单元格，排除标题/公司名/日期装饰行       │
└─────────────────────────────────────────────────────────────────┘
```

**全局规则文件**：`backend/data/address_label_overrides.json`

```json
{
  "description": "用户手动校正的 label→物理坐标映射（覆盖自动识别结果）",
  "version": "2025-R1",
  "overrides": {
    "H1:折旧分配分析表H1-13:销售费用折旧": {
      "row": 13, "col": "D",
      "corrected_by": "admin",
      "corrected_at": "2026-05-17T10:00:00Z",
      "note": "合计行D列是销售费用折旧合计"
    },
    "H1:折旧分配分析表H1-13:管理费用折旧": {
      "row": 13, "col": "E",
      "corrected_by": "admin",
      "corrected_at": "2026-05-17T10:00:00Z"
    },
    "H1:折旧分配分析表H1-13:生产成本折旧": {
      "row": 13, "col": "F",
      "corrected_by": "admin",
      "corrected_at": "2026-05-17T10:00:00Z"
    }
  },
  "header_rules": {
    "_doc": "全局表头检测规则（覆盖默认启发式，指定数据区域起始位置）",
    "H1:折旧分配分析表H1-13": {
      "data_start_row": 7,
      "col_header_row": 7,
      "row_header_col": "A"
    },
    "D2:审定表D2-1": {
      "data_start_row": 5,
      "col_header_row": 5,
      "row_header_col": "A"
    }
  }
}
```

**前端入口**：
- 底稿编辑器右键菜单 → "标记此单元格为 [label]" → 弹窗输入语义标签 → 写入 overrides
- 模板管理页 → "表头规则" Tab → 指定每个 sheet 的数据起始行

**API**：
- `POST /api/address-registry/v2/override` — 用户手动校正（写入 overrides）
- `GET /api/address-registry/v2/overrides` — 查看全部校正规则
- `DELETE /api/address-registry/v2/override/{uri}` — 删除某条校正
- `POST /api/address-registry/v2/header-rule` — 设置某 sheet 的表头规则
- `GET /api/address-registry/v2/header-rules` — 查看全部表头规则

**设计原则**：
- 用户改一次，全局生效（同一模板的所有项目共享）
- 校正结果优先于自动识别（永远不会被覆盖）
- 支持导出/导入（团队间共享校正规则）
- 底稿保存时自动清除该 wp 的解析缓存（下次打开重新解析）

### 3.4 依赖图构建来源（6 个数据源合并）

| 数据源 | 产出边类型 | 数量级 |
|--------|-----------|--------|
| `prefill_formula_mapping.json` | TB/ADJ → WP | ~500 边 |
| `cross_wp_references.json` | WP → WP / WP → NOTE / WP → REPORT | 107 边 |
| `report_config.formula` 字段 | TB → REPORT / REPORT → REPORT (ROW) | ~300 边 |
| `address_registry_l3_dependencies.json` | WP:sheet → WP:sheet（同文件跨 sheet） | 42,163 边 |
| `note_account_mapping` 表 | WP → NOTE（底稿→附注章节） | ~50 边 |
| `account_mapping` 表 | MAPPING → TB / MAPPING → WP / MAPPING → REPORT | ~200 边 |

**合并后总边数**：~43,300 条（去重后）

### 3.5 变更触发点（7 个入口）

| 触发点 | 当前实现 | 改进后 |
|--------|---------|--------|
| 底稿保存 | eventBus WORKPAPER_SAVED + useStaleImpact | 统一走 Linkage Bus |
| 调整分录增删改 | eventBus ADJUSTMENT_* → mark_stale | 统一走 Linkage Bus |
| 账表导入/激活 | eventBus DATA_IMPORTED → 全量 stale | 统一走 Linkage Bus |
| 报表重新生成 | eventBus REPORTS_UPDATED | 统一走 Linkage Bus |
| 公式管理改配置 | ❌ 无 | **新增**：FORMULA_CHANGED → Linkage Bus |
| 附注编辑保存 | ❌ 无 | **新增**：NOTE_SAVED → Linkage Bus |
| 试算表手动编辑 | ❌ 无 | **新增**：TB_MANUAL_EDIT → Linkage Bus |

### 3.6 公式管理全局穿透设计（三向可达）

公式管理前端**已有完善基础**（FormulaManagerDialog.vue 1500+ 行），当前已实现：
- ✅ 左侧树形导航（试算平衡表/报表/附注/底稿/合并报表/表间审核 6 大类）
- ✅ 右侧公式表格（可编辑/新增/删除/导入/导出/应用自动运算）
- ✅ 表间审核（报表↔附注/报表↔底稿/附注↔底稿/合并↔报表 4 组交叉校验）
- ✅ 公式看板（按报表类型/公式分类/数据源分组统计）
- ✅ 全局入口（ThreeColumnLayout 侧栏 ƒx 按钮 → FormulaManagerDialog）
- ✅ 各模块入口（TrialBalance/ReportView/DisclosureEditor/StructureEditor/ConsolNoteTab 都有 ƒx 按钮）
- ✅ FormulaDependencyGraph.vue（有向图 + stale 高亮 + 编制顺序建议）

**需要增强的 3 个方向**（在现有组件上追加，不新建）：

#### 方向 1：全局公式中心 → 具体文档（从公式找使用方）

```
入口：公式管理页面（/formula-management）
展示：全部公式列表（按类型分组：TB/WP/ADJ/NOTE/PREV/SUM_TB）
操作：点击某条公式 → 展开"引用方"面板 → 列出所有使用该公式的文档

示例：
  公式 TB('1122','期末余额') 被以下对象引用：
  ┌─────────────────────────────────────────────────────┐
  │ 📄 WP:D2:审定表D2-1:未审数        [跳转底稿编辑器]   │
  │ 📊 REPORT:BS-005:当期金额          [跳转报表页面]     │
  │ 📝 NOTE:5.7:应收账款:期末余额      [跳转附注编辑器]   │
  └─────────────────────────────────────────────────────┘

API：
  GET /api/linkage/formula-usage?formula=TB('1122','期末余额')
  → 返回 [{uri, module, label, route}]

前端组件：
  FormulaUsagePanel.vue — 公式引用方列表（可点击跳转）
```

#### 方向 2：具体文档 → 当前页面所用公式（从文档找公式）

```
入口：底稿编辑器 / 报表页面 / 附注编辑器 的侧栏或工具栏
展示：当前打开的文档使用了哪些公式（按 sheet 分组）
操作：点击某条公式 → 高亮对应单元格 / 跳转公式管理页面编辑

示例（打开 D2 应收账款底稿时）：
  当前底稿使用的公式：
  ┌─────────────────────────────────────────────────────┐
  │ 审定表D2-1                                           │
  │   期初余额  ← =TB('1122','期初余额')     [定位]      │
  │   未审数    ← =TB('1122','期末余额')     [定位]      │
  │   AJE调整   ← =ADJ('1122','aje_net')    [定位]      │
  │   RJE调整   ← =ADJ('1122','rje_net')    [定位]      │
  │   上年审定数 ← =PREV('D2','审定表D2-1','审定数') [定位]│
  ├─────────────────────────────────────────────────────┤
  │ 坏账准备明细表D2-3                                    │
  │   （无预填充公式）                                    │
  └─────────────────────────────────────────────────────┘

API：
  GET /api/linkage/formulas-for?uri=WP:D2
  → 返回 [{sheet, label, formula, formula_type, cell_ref}]

前端组件：
  DocumentFormulaList.vue — 当前文档公式清单（WorkpaperSidePanel 新 Tab）
  
接入点：
  - WorkpaperEditor: WorkpaperSidePanel 新增"公式"Tab
  - ReportView: 工具栏"查看公式"按钮 → 弹出当前报表行的公式列表
  - DisclosureEditor: 侧栏"公式来源"面板
  - TrialBalance: 右键"查看取数公式"
  - Adjustments: 右键"查看影响的底稿公式"
```

#### 方向 3：单元格右键 → 该单元格的公式详情（从单元格找全部关联）

```
入口：底稿编辑器 / 报表 / 附注 中右键某个单元格
展示：该单元格的完整公式信息（来源 + 去向 + 依赖链）
操作：点击来源/去向可跳转到对应模块

示例（右键 D2 审定表 "未审数" 单元格）：
  ┌─────────────────────────────────────────────────────┐
  │ 📍 WP:D2:审定表D2-1:未审数                           │
  │                                                      │
  │ 📥 数据来源（我从哪取数）：                            │
  │   ← TB:1122::期末余额 (试算表)        [跳转试算表]    │
  │                                                      │
  │ 📤 数据去向（谁引用我）：                              │
  │   → REPORT:BS-005::当期金额 (报表)    [跳转报表]      │
  │   → NOTE:5.7:应收账款:期末余额 (附注) [跳转附注]      │
  │   → WP:D0:函证汇总表D0-2:应收账款审定数 [跳转底稿]   │
  │                                                      │
  │ 🔗 公式定义：                                         │
  │   =TB('1122','期末余额')                              │
  │   类型：TB（从试算表取数）                             │
  │   最后计算值：¥20,283,811.52                          │
  │   最后计算时间：2026-05-17 10:30                      │
  │                                                      │
  │ ⚠️ 状态：                                             │
  │   试算表 1122 已于 2h 前变更，当前值可能过期           │
  │   [重新计算] [查看变更历史]                            │
  └─────────────────────────────────────────────────────┘

API：
  GET /api/linkage/cell-detail?uri=WP:D2:审定表D2-1:未审数
  → 返回 {
      uri, label, formula, formula_type,
      sources: [{uri, module, label, route}],      // 数据来源
      consumers: [{uri, module, label, route}],    // 数据去向
      last_value, last_computed_at,
      is_stale, stale_reason
    }

前端组件：
  CellFormulaDetail.vue — 单元格公式详情弹窗
  
触发方式：
  - WorkpaperEditor: Univer 右键菜单追加"查看公式详情"
  - ReportView: 行右键菜单追加"查看公式来源"
  - DisclosureEditor: 单元格右键追加"查看数据来源"
  - TrialBalance: 科目行右键追加"查看引用方"
  - Adjustments: 分录行右键追加"查看影响范围"
```

#### 3.7 公式管理中心页面增强（在现有 FormulaManagerDialog 基础上）

```
现有（已实现）：
  ✅ 左侧树（试算平衡表/报表/附注/底稿/合并报表/表间审核）
  ✅ 右侧公式表格（编辑/新增/删除/导入/导出/应用）
  ✅ 公式看板（按类型/分类/数据源分组）
  ✅ 全局入口（侧栏 ƒx）+ 各模块入口（工具栏 ƒx）
  ✅ 表间审核（4 组交叉校验规则）
  ✅ FormulaDependencyGraph（有向图 + stale 高亮 + 编制顺序）

需增强（追加到现有组件）：
  1. FormulaManagerDialog 左侧树增加"按引用方分组"视图切换按钮
  2. FormulaManagerDialog 右侧表格增加"引用方"列（点击展开引用方列表）
  3. FormulaManagerDialog 顶部增加"公式健康度"统计卡片：
     - 失效公式数（引用的科目在当前项目 TB 中不存在）
     - 覆盖率：有公式的底稿数 / 总底稿数
  4. 搜索框增强：支持按 URI 格式搜索（如输入"1122"找到所有引用该科目的公式）
  5. 批量操作增强：选中多条公式 → "查看全部引用方" / "批量重新计算"
  6. 与 Linkage Bus 集成：保存公式时自动调用 stale_engine.on_change()
```

---

## 四、实施方案（4 个 Sprint）

### Sprint 1：统一依赖图构建 + 运行时解析器（3 天）

**目标**：把 5 个数据源合并为统一依赖图 + 实现 label→物理坐标的运行时解析器

```python
# 新建 backend/app/services/linkage_graph_builder.py
class LinkageGraphBuilder:
    """从 5 个数据源构建统一依赖图（边用语义 URI，不含物理坐标）"""
    
    def build(self) -> dict:
        edges = []
        edges += self._from_prefill_mapping()      # TB:1122::期末余额 → WP:D2:审定表D2-1:未审数
        edges += self._from_cross_wp_references()   # WP:H1:折旧分配分析表H1-13:销售费用折旧 → WP:K8:审定表K8-1:折旧费
        edges += self._from_report_config()         # TB:1122::期末余额 → REPORT:BS-005::当期金额
        edges += self._from_l3_dependencies()       # WP:H1:审定表H1-1:* → WP:H1:折旧分配分析表H1-13:*（同文件跨sheet）
        edges += self._from_note_account_mapping()  # WP:D2:审定表D2-1:审定数 → NOTE:5.7:应收账款:期末余额
        
        # 反向边（公式配置→引用方）
        edges += self._build_formula_reverse_index()
        
        return {
            "nodes": self._collect_nodes(edges),
            "edges": self._deduplicate(edges),
        }

# 新建 backend/app/services/linkage_label_resolver.py
class LinkageLabelResolver:
    """运行时解析器：语义 label → 物理坐标
    
    设计原则：
    - label 是稳定标识（"销售费用折旧"），物理坐标是易变实现（D13）
    - 解析结果缓存到 Redis（key = wp_code:sheet_name:label，TTL = 24h）
    - 用户插入行后缓存自动失效（底稿保存时清除该 wp 的全部缓存）
    """
    
    async def resolve(self, wp_code: str, sheet_name: str, label: str) -> tuple[int, int] | None:
        """返回 (row, col) 或 None
        
        搜索策略（不限前 3 行）：
        1. 全 sheet 扫描所有单元格文本，精确匹配 label
        2. 如果 label 是"行表头.列表头"格式（如"合计.销售费用"），分别匹配行和列
        3. 如果 label 是单一词（如"销售费用折旧"），搜索包含该词的单元格
        4. 返回匹配到的单元格坐标（优先数据区域，排除标题行）
        """
        
    async def resolve_batch(self, uris: list[str]) -> dict[str, tuple[int, int] | None]:
        """批量解析（减少重复打开文件）"""
        
    def invalidate_cache(self, wp_code: str):
        """底稿保存后清除该 wp 的全部解析缓存"""
```

**产出**：
- `backend/app/services/linkage_graph_builder.py`
- `backend/app/services/linkage_label_resolver.py`
- `backend/data/unified_dependency_graph.json`（语义 URI 边，~5000 条去重后）
- `GET /api/linkage/graph` 端点
- `GET /api/linkage/resolve?uri=WP:H1:折旧分配分析表H1-13:销售费用折旧` 端点（返回物理坐标）
- `GET /api/linkage/impact?uri=...&max_depth=3` 端点（BFS 下游影响）

### Sprint 2：Stale Propagation Engine 统一化（2 天）

**目标**：用统一依赖图替代现有两套 stale 机制

```python
# 新建 backend/app/services/stale_propagation_engine.py
class StalePropagationEngine:
    """统一 stale 传播引擎"""
    
    async def propagate(self, changed_uri: str, max_depth: int = 5) -> list[str]:
        """BFS 遍历依赖图，返回所有受影响的 URI 列表"""
        
    async def mark_stale_by_uri(self, uris: list[str]):
        """按 URI 类型分发标记：
        WP:* → WorkingPaper.prefill_stale = True
        REPORT:* → FinancialReport.is_stale = True
        NOTE:* → DisclosureNote.is_stale = True
        """
        
    async def on_change(self, source_uri: str, project_id: UUID, year: int):
        """统一入口：任何变更 → 传播 → 标记 → 通知"""
        affected = await self.propagate(source_uri)
        await self.mark_stale_by_uri(affected)
        await self._notify_frontend(project_id, affected)  # SSE 推送
```

**迁移策略**：
- 保留 event_handlers.py 现有逻辑（向后兼容）
- 在每个 handler 末尾追加 `await stale_engine.on_change(uri, ...)`
- 前端 useStaleImpact 改调统一端点 `/api/linkage/impact`（替代 `/v2/notify-cell-change`）
- `/v2/notify-cell-change` 保留但标记 deprecated（过渡期 30 天后删除）
- 统一引擎 `on_change` 一次调用同时完成：BFS 传播 + 写 DB stale + SSE 推送前端

**合并后效果**：
- 机制 A 的持久化能力（写 DB）✓
- 机制 B 的即时可视化能力（返回前端 tag 列表）✓
- 一个入口、一次 BFS、两个输出
- 不再有"后端标了 stale 但前端不知道"或"前端算了影响但后端不标"的断裂

### Sprint 3：反向联动 + 公式管理联动（2 天）

**目标**：实现"报表改→底稿 stale"和"公式管理改→底稿 stale"

#### 3.1 公式管理与底稿的联动现状

当前系统有 3 种公式引用格式，**已天然符合统一 URI 规则**：

| 公式来源 | 格式 | 对应 URI |
|---------|------|---------|
| `report_config.formula` | `TB('1122','期末余额')` | `TB:1122::期末余额` |
| `prefill_formula_mapping` | `=WP('H1','折旧分配分析表H1-13','销售费用折旧')` | `WP:H1:折旧分配分析表H1-13:销售费用折旧` |
| `prefill_formula_mapping` | `=TB('1122','期初余额')` | `TB:1122::期初余额` |
| `prefill_formula_mapping` | `=ADJ('1122','aje_net')` | `ADJ:1122::aje_net` |
| `prefill_formula_mapping` | `=PREV('D1','审定表D1-1','审定数')` | `WP:D1:审定表D1-1:审定数`（上年） |
| `cross_wp_references` | `=WP('H1','折旧分配分析表H1-13','销售费用折旧')` | `WP:H1:折旧分配分析表H1-13:销售费用折旧` |

**关键发现**：`=WP('wp_code','sheet_name','label')` 公式的三个参数**恰好就是 URI 的后三段**。无需额外转换。

#### 3.2 需要修改的联动点

**A. report_config.formula 改动 → 底稿 stale**

```
触发：管理员在公式管理页面修改 report_config 某行的 formula 字段
影响：所有引用该 report_config 行的底稿需要 stale

实现：
1. report_config UPDATE 时发布 FORMULA_CONFIG_CHANGED 事件
2. 事件 payload 含 {row_code, old_formula, new_formula}
3. 从 old_formula 解析出引用的 TB 科目列表
4. 从 prefill_formula_mapping 反查哪些底稿引用了这些科目
5. 标记这些底稿 prefill_stale=True

代码改动：
- backend/app/routers/report_config.py: PUT 端点追加事件发布
- backend/app/services/event_handlers.py: 新增 FORMULA_CONFIG_CHANGED handler
- backend/app/services/linkage_graph_builder.py: 构建 FORMULA:row_code → REPORT:row_code 边
```

**B. prefill_formula_mapping 改动 → 底稿 stale**

```
触发：管理员修改 prefill_formula_mapping.json（通过 reseed 或手动编辑）
影响：被修改公式对应的底稿需要重新预填充

实现：
1. /api/template-library-mgmt/seed-all 端点执行后发布 PREFILL_MAPPING_CHANGED 事件
2. 对比新旧 mapping 差异，找出变更的 wp_code 列表
3. 标记这些底稿 prefill_stale=True

代码改动：
- backend/app/routers/template_library_mgmt.py: seed 端点追加事件发布
- backend/app/services/event_handlers.py: 新增 PREFILL_MAPPING_CHANGED handler
```

**C. 底稿保存 → 引用该底稿的其他底稿 stale（=WP() 公式反向）**

```
触发：用户保存底稿 H1（修改了折旧分配分析表H1-13 的数据）
影响：K8/K9/F5 等引用 =WP('H1',...) 的底稿需要 stale

实现（已有基础，需打通）：
1. WorkpaperEditor.onSave → staleImpact.notify({sheet: '折旧分配分析表H1-13'})
2. 后端从 prefill_formula_mapping 反查：谁的公式引用了 WP('H1','折旧分配分析表H1-13',*)
3. 找到 K8/K9/F5 → 标记 prefill_stale=True（当前只返回前端，不写 DB）
4. 【需修改】：notify-cell-change 端点同时写 DB stale 字段

代码改动：
- backend/app/routers/address_registry_v2.py: notify_cell_change 追加 mark_stale 调用
```

**D. 附注保存 → 引用该附注的底稿 stale（=NOTE() 公式反向）**

```
触发：用户编辑附注 5.7 节并保存
影响：引用 =NOTE('5.7',...) 的底稿需要 stale

实现：
1. 附注保存端点发布 NOTE_SECTION_SAVED 事件
2. 从 prefill_formula_mapping 反查：谁的公式引用了 NOTE('5.7',*)
3. 标记这些底稿 prefill_stale=True

代码改动：
- backend/app/routers/disclosure_notes.py: PUT 端点追加事件发布
- backend/app/services/event_handlers.py: 新增 NOTE_SECTION_SAVED handler
```

#### 3.3 反向索引构建

```python
# 新建 backend/app/services/formula_reverse_index.py
class FormulaReverseIndex:
    """从公式文本解析引用关系，建立"被引用方 → 引用方"反向索引
    
    数据源：
    1. prefill_formula_mapping.json 的 cells[].formula 字段
    2. report_config 表的 formula 字段
    3. cross_wp_references.json 的 targets[].formula 字段
    
    产出：
    {
      "TB:1122::期末余额": ["WP:D2:审定表D2-1:未审数", "REPORT:BS-005::当期金额"],
      "WP:H1:折旧分配分析表H1-13:销售费用折旧": ["WP:K8:审定表K8-1:折旧"],
      "NOTE:5.7:应收账款:期末余额": ["WP:D2:审定表D2-1:附注引用"],
    }
    
    用法：
    当 TB:1122 变了 → 查反向索引 → 得到 [WP:D2, REPORT:BS-005] → 标 stale
    当 WP:H1:折旧分配分析表H1-13 变了 → 查反向索引 → 得到 [WP:K8] → 标 stale
    """
    
    def build_from_prefill_mapping(self) -> dict[str, list[str]]:
        """解析 =TB()/=WP()/=ADJ()/=NOTE() 公式，提取被引用 URI"""
        
    def build_from_report_config(self) -> dict[str, list[str]]:
        """解析 report_config.formula 中的 TB()/SUM_TB()/ROW() 引用"""
        
    def query(self, changed_uri: str) -> list[str]:
        """查询：谁引用了 changed_uri → 返回引用方 URI 列表"""
```

**新增事件**：
- `FORMULA_CONFIG_CHANGED`：report_config 表 formula 字段被修改
- `PREFILL_MAPPING_CHANGED`：prefill_formula_mapping.json 被 reseed
- `NOTE_SECTION_SAVED`：附注章节保存
- `TB_MANUAL_EDITED`：试算表手动编辑（非公式计算）

### Sprint 4：docx 底稿 + 前端统一展示（2 天）

**目标**：109 个 Word 底稿纳入联动 + 前端统一 stale 展示

**docx 处理**：
```python
# 扫描 docx 占位符 → 注册为 L2 锚点
# 占位符格式：{{company_name}} / {{partner_name}} / {{materiality_level}}
# 来源：wp_prefill_context 端点的字段
# URI 格式：WP:B60:总体审计策略:{{partner_name}}
```

**前端统一展示**：
- 所有模块（底稿/报表/附注/调整分录）统一 stale badge 样式
- SSE 推送 `linkage:stale-changed` 事件
- 各模块订阅 → 自动刷新 badge

### Sprint 5：公式管理全局穿透 UI（3 天）

**目标**：实现三向穿透（全局→具体 / 具体→公式 / 单元格→公式详情）

**后端 API（3 个新端点）**：
- `GET /api/linkage/formula-usage?formula=...` — 查某条公式被谁引用
- `GET /api/linkage/formulas-for?uri=WP:D2` — 查某文档用了哪些公式
- `GET /api/linkage/cell-detail?uri=WP:D2:审定表D2-1:未审数` — 单元格完整公式详情

**前端组件（3 个新组件）**：
- `FormulaUsagePanel.vue` — 公式引用方列表（公式管理页面用）
- `DocumentFormulaList.vue` — 当前文档公式清单（WorkpaperSidePanel 新 Tab "公式"）
- `CellFormulaDetail.vue` — 单元格公式详情弹窗（右键菜单触发）

**接入点（5 个模块右键菜单）**：
- WorkpaperEditor: Univer 右键追加"查看公式详情"
- ReportView: 行右键追加"查看公式来源"
- DisclosureEditor: 单元格右键追加"查看数据来源"
- TrialBalance: 科目行右键追加"查看引用方"
- Adjustments: 分录行右键追加"查看影响范围"

**公式管理中心增强**：
- 左侧树增加"按引用方分组"视图
- 右侧详情增加"引用方列表"面板
- 顶部"公式健康度"统计卡片（总数/有效/失效/覆盖率）
- 搜索框支持按科目/底稿/类型搜索
- 批量操作："查看全部引用方" / "批量重新计算"

---

## 五、与现有代码的兼容策略

| 现有组件 | 处置 | 理由 |
|---------|------|------|
| event_handlers.py | **保留** + 追加 | 已跑通的联动不动，在末尾追加统一引擎调用 |
| prefill_engine.py | **保留** | 底稿内嵌公式执行逻辑不变 |
| prefill_formula_mapping.json | **保留** | 作为依赖图的数据源之一 |
| cross_wp_references.json | **保留** | 作为依赖图的数据源之一 |
| address_registry_v2 | **升级** | 从独立 BFS 改为调用统一引擎 |
| useStaleImpact.ts | **升级** | 改调统一端点 `/api/linkage/impact` |
| WorkingPaper.prefill_stale | **保留** | 统一引擎写入此字段 |
| AuditReport.is_stale | **保留** | 统一引擎写入此字段 |
| DisclosureNote.is_stale | **保留** | 统一引擎写入此字段 |

---

## 六、可扩展性设计

### 6.1 新增模块接入（3 步）

```
1. 定义 URI 格式：NEW_MODULE:{code}:{field}
2. 在 linkage_graph_builder.py 添加数据源方法
3. 在 stale_propagation_engine.py 添加 mark_stale 分支
```

### 6.2 用户自定义联动规则

```json
// 用户在前端配置：
{
  "source": "WP:D2:审定表D2-1:审定数",
  "target": "NOTE:5.7:应收账款:期末余额",
  "type": "data_flow",
  "severity": "blocking"
}
// 写入 sheet_mapping_rules.json 的 custom_rules
// 统一引擎自动纳入依赖图
```

### 6.3 插件化公式类型

```python
# 新增公式类型只需：
# 1. 在 _FORMULA_RESOLVERS 字典注册
# 2. 实现 async def _resolve_xxx(db, project_id, year, args) → Decimal
# 3. 在 linkage_graph_builder 添加对应边提取逻辑
```

---

## 七、工时估算与优先级

| Sprint | 内容 | 工时 | 价值 |
|--------|------|------|------|
| 1 | 统一依赖图构建 + 运行时解析器 | 3 天 | 基础设施（后续全依赖） |
| 2 | Stale 传播引擎统一化 | 2 天 | 消除两套机制并存 |
| 3 | 反向联动 + 公式管理联动 | 2 天 | 解决最大断裂点 |
| 4 | docx + 前端统一展示 | 2 天 | 完整性收尾 |
| 5 | 公式管理全局穿透 UI | 3 天 | 三向可达（全局→具体/具体→公式/单元格→详情） |
| **合计** | | **12 天** | |

**推荐执行顺序**：Sprint 1 → 2 → 3 → 4 → 5（严格串行，每步依赖前步产出）

---

## 八、补充设计（复盘后 6 项改进）

### 8.1 科目表（AccountMapping）联动

**现状缺口**：科目映射改了（如 1122 从"应收账款"改映射到"其他应收款"），整个 TB→报表→底稿→附注链路全部错位，但当前方案没覆盖。

**补充设计**：
```
触发：account_mapping 表 INSERT/UPDATE/DELETE
事件：ACCOUNT_MAPPING_CHANGED
payload：{project_id, year, old_mapping, new_mapping, affected_account_codes}

影响范围（最大范围 stale 触发）：
  1. TB:affected_codes::* → 试算表该科目行 stale
  2. 所有 prefill_formula_mapping 中引用 affected_codes 的底稿 → prefill_stale=True
  3. 所有 report_config 中 formula 含 TB('affected_code',...) 的报表行 → is_stale=True
  4. 所有 note_account_mapping 中关联 affected_codes 的附注章节 → is_stale=True

URI 格式：MAPPING:1122::standard_account_code

代码改动：
  - backend/app/routers/account_chart.py: POST/PUT/DELETE 追加事件发布
  - backend/app/services/event_handlers.py: 新增 ACCOUNT_MAPPING_CHANGED handler
  - 统一引擎 FormulaReverseIndex 增加 MAPPING → TB/WP/REPORT/NOTE 边
```

### 8.2 报表行编辑反向触发

**现状缺口**：方案只说了"报表改→底稿 stale"，但没说具体哪个端点触发。

**补充设计**：
```
触发点：ReportEngine.on_trial_balance_updated 执行完后
逻辑：对比新旧 financial_report 行值，变化的 row_code 列表
事件：REPORT_ROW_CHANGED
payload：{project_id, year, changed_row_codes: ["BS-005", "IS-001"]}

影响范围：
  - 从 cross_wp_references 反查：哪些底稿的 target 是 REPORT:changed_row_code
  - 从 prefill_formula_mapping 反查：哪些底稿公式引用了 ROW('changed_row_code')
  - 标记这些底稿 prefill_stale=True

代码改动：
  - backend/app/services/report_engine.py: generate_all_reports 末尾对比新旧值
  - 新增 _detect_changed_rows(old_values, new_values) → list[str]
  - 发布 REPORT_ROW_CHANGED 事件
```

### 8.3 多项目隔离 + 权限

**设计原则**：
```
依赖图结构：全局共享（模板级，所有项目用同一套模板结构）
stale 传播：按项目隔离（project_id 参数强制过滤）
公式管理中心：按项目过滤引用方列表（同一模板在不同项目有不同实例）

权限矩阵：
  address_label_overrides.json 修改 → admin/partner only
  header_rules 修改 → admin/partner only
  公式管理中心查看 → all roles
  公式管理中心编辑 → admin/partner only
  单元格右键"查看公式详情" → all roles
  单元格右键"标记此单元格为[label]" → admin/partner/manager

API 层面：
  StalePropagationEngine.on_change(uri, project_id, year)
    → project_id 参数确保只标记当前项目的 WorkingPaper/FinancialReport/DisclosureNote
  GET /api/linkage/formula-usage?formula=...&project_id=...
    → 按 project_id 过滤引用方实例
  GET /api/linkage/cell-detail?uri=...&project_id=...
    → 按 project_id 过滤 last_value/last_computed_at
```

### 8.4 性能设计细节

```
依赖图加载：
  - 启动时一次性从 5 个 JSON 文件构建内存图（~5000 条有效边，<1MB）
  - 热加载：JSON 文件变更时自动重建（inotify/polling 30s）
  - 不存 DB（避免 N+1 查询），纯内存 dict

BFS 性能：
  - 5000 边 + max_depth=5，最坏情况 <10ms
  - 平均情况（单底稿变更）：3-5 个下游节点，<1ms
  - 全量 stale（账表导入）：遍历全图 ~50ms，可接受

label→物理坐标解析缓存：
  - Redis key：resolve:{project_id}:{wp_code}:{sheet_name}:{label}
  - TTL：24h（模板结构不频繁变化）
  - 清除时机：
    a. 底稿保存时：SCAN resolve:{project_id}:WP:{wp_code}:* → DEL
    b. 公式管理改配置时：清全部 resolve:* 缓存（低频操作）
    c. address_label_overrides 修改时：清对应 URI 的缓存

并发安全：
  - BFS 传播是只读操作（读内存图），无锁
  - mark_stale 写 DB 用 bulk UPDATE（单条 SQL），无并发冲突
  - Redis 缓存用 SET NX + TTL，无竞态
```

### 8.5 审计日志

```
目的：排查"为什么我的底稿突然变 stale 了"

数据模型：
  linkage_audit_log 表（或 JSONB 字段追加到 audit_log_entries）
  {
    id, timestamp, project_id, year,
    triggered_by_user_id,
    source_uri,           -- 变更源（如 "WP:H1:折旧分配分析表H1-13:销售费用折旧"）
    trigger_event,        -- 触发事件（如 "WORKPAPER_SAVED"）
    affected_count,       -- 影响对象数
    affected_uris,        -- 前 20 个受影响 URI（JSONB 数组）
    propagation_depth,    -- BFS 最大深度
    duration_ms,          -- 传播耗时
  }

前端展示：
  - 单元格公式详情弹窗（CellFormulaDetail.vue）增加"变更历史"Tab
  - 显示该 URI 最近 10 次被 stale 的记录：时间 + 触发源 + 触发人
  - 底稿详情卡片增加"stale 原因"提示：点击展开最近一次 stale 的完整传播链

API：
  GET /api/linkage/audit-log?uri=WP:D2:审定表D2-1:未审数&limit=10
  → 返回 [{timestamp, source_uri, trigger_event, triggered_by}]
```

### 8.6 降级策略

```
场景：统一引擎不可用（Redis 断连 / 依赖图加载失败 / 内存不足）

降级方案：
  后端：
    - StalePropagationEngine 初始化失败 → 设 _degraded=True
    - on_change() 在 _degraded 模式下：
      a. 不做 BFS（跳过精确传播）
      b. 回退到 event_handlers 的粗粒度 mark_stale（按 project_id 全量标）
      c. 日志 WARNING "linkage engine degraded, falling back to event_handlers"
    - /api/linkage/impact 返回 503 + {"degraded": true, "fallback": "event_handlers"}

  前端：
    - useStaleImpact 收到 503 → 静默降级（不显示黄条，不阻断保存）
    - 公式详情弹窗收到 503 → 显示"联动引擎暂不可用，数据可能不是最新"
    - 不影响核心编辑/保存流程（联动是增强功能，不是阻断功能）

  健康检查：
    GET /api/linkage/health
    → {
        status: "healthy" | "degraded" | "unavailable",
        graph_loaded: true/false,
        graph_edge_count: 5000,
        redis_connected: true/false,
        last_propagation_ts: "2026-05-17T10:30:00Z",
        last_error: null | "Redis connection refused"
      }

  恢复：
    - Redis 重连后自动恢复（下次 on_change 调用时检测）
    - 依赖图加载失败后每 60s 重试一次
    - 恢复后自动清除 _degraded 标记
```

---

## 九、验收标准

| # | 验收项 | 量化指标 |
|---|--------|---------|
| 1 | 调整分录改 → 底稿+报表+附注全部 stale | 3 模块同时标记 |
| 2 | 底稿保存 → 下游底稿+报表+附注 stale | BFS ≤ 3 层 |
| 3 | 公式管理改 → 引用该公式的报表行 stale | 反向索引命中 |
| 4 | 附注改 → 引用该附注的底稿 stale | 反向边 |
| 5 | 前端任何模块看到 stale badge | SSE ≤ 2s 延迟 |
| 6 | 109 个 docx 底稿纳入联动 | 占位符注册率 ≥ 90% |
| 7 | 统一 URI 格式覆盖全部 6 模块 | WP/REPORT/NOTE/ADJ/TB/FORMULA 0 遗漏 |
| 8 | 用户自定义联动规则可用 | 前端配置 → 即时生效 |
| 9 | 科目映射改 → 全链路 stale | TB+报表+底稿+附注同时标记 |
| 10 | 公式穿透三向可达 | 全局→具体 / 具体→公式 / 单元格→详情 全通 |
| 11 | 单元格右键"查看公式详情"可用 | 5 模块全部接入 |
| 12 | 降级模式不阻断核心流程 | 引擎 503 时保存/编辑正常 |

---

## 十、风险与缓解

| 风险 | 缓解 |
|------|------|
| 依赖图 43000 边 BFS 性能 | 内存图 <1MB + max_depth=5 截断 + 平均 <1ms |
| 循环依赖（A→B→A） | visited set 防环 + 检测告警 |
| 旧 event_handlers 与新引擎重复标记 | 幂等设计（已 stale 不重复标） |
| 语义 label 匹配不到物理坐标 | 三层优先级（override→header_rules→启发式）+ 用户手动校正 |
| docx 占位符格式不统一 | 定义标准格式 `{{field_name}}`，扫描时容错 |
| 科目映射改动影响范围过大 | 先计算影响数量，超过阈值（50+）弹窗确认再执行 |
| 统一引擎不可用 | 降级到 event_handlers 粗粒度标记（§8.6） |
