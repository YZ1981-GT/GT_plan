# Design Document — Phase 1 体验断层修复

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始设计 |

---

## Overview

本设计实现 Phase 1 五项体验断层修复：全局搜索 Ctrl+K、表格字号统一、穿透面包屑导航、工具栏 compact 模式、并发编辑版本锁。五项功能相互独立，可并行开发，共享的基础设施为 displayPrefs store 和 useNavigationStack composable。

---

## F1 全局搜索 — 架构设计

### 系统分层

```
┌─────────────────────────────────────────────────┐
│ DefaultLayout.vue                                │
│   └─ GlobalSearchDialog.vue (Ctrl+K 触发)       │
│       ├─ 搜索输入框 (el-input, autofocus)       │
│       ├─ 最近访问列表 (localStorage)            │
│       └─ 搜索结果列表 (keyboard navigable)      │
│           └─ SearchResultItem.vue               │
└─────────────────────────────────────────────────┘
         │ debounce 300ms
         ▼
┌─────────────────────────────────────────────────┐
│ GET /api/search/global?q={keyword}&project_id=  │
│   → global_search_service.py                    │
│     ├─ search_workpapers(q) → WpIndex ILIKE     │
│     ├─ search_accounts(q) → account_chart ILIKE │
│     ├─ search_reports(q) → report_lines ILIKE   │
│     └─ search_projects(q) → projects ILIKE      │
│   → 合并 + 排序(relevance) + limit 50          │
└─────────────────────────────────────────────────┘
```

### ADR-F1: 搜索方案选型

**决策**：使用 PostgreSQL `ILIKE` + GIN trigram 索引，不引入 Elasticsearch。

**理由**：
1. 当前数据规模（363 底稿索引 + ~500 科目 + ~200 报表行 + ~50 项目）总计 < 2000 条，PG 完全胜任
2. 拼音首字母匹配通过后端 `pypinyin` 库生成拼音首字母字段（预计算存储），搜索时同时匹配原文和拼音
3. 避免引入新基础设施依赖（ES 需要独立部署+维护）
4. 未来数据量增长到 10000+ 时再考虑迁移到 MeiliSearch

**替代方案**：MeiliSearch（轻量级全文搜索），暂不采用（当前规模不需要）。

### 数据模型

```python
# 搜索结果统一结构
class SearchResult(BaseModel):
    type: Literal['workpaper', 'account', 'report_line', 'project']
    id: str
    title: str           # 显示名称
    subtitle: str        # 辅助信息（如所属项目/科目编号）
    route: dict          # { name: str, params: dict } 用于前端跳转
    relevance: float     # 相关度评分（0~1）
```

### 前端组件设计

```typescript
// GlobalSearchDialog.vue props
interface Props {
  visible: boolean  // v-model 控制显隐
}

// 内部状态
const keyword = ref('')
const results = ref<SearchResult[]>([])
const recentItems = ref<SearchResult[]>([])  // localStorage
const activeIndex = ref(0)  // 键盘导航当前选中项
const loading = ref(false)
```

### 快捷键注册

在 `DefaultLayout.vue` 的 `onMounted` 中注册：
```typescript
// 复用 shortcuts.ts 的 registerShortcut
registerShortcut('ctrl+k', () => { showSearch.value = true })
```

不拦截输入框/textarea/contentEditable 内的 Ctrl+K（与 useNavigationStack 的 Backspace 拦截逻辑一致）。

---

## F2 表格字号统一 — 架构设计

### ADR-F2: 字号控制方案

**决策**：使用动态 class + scoped `:deep()` + `!important`，废弃 `:style="{ fontSize }"`。

**理由**：
1. Element Plus el-table 内部 DOM 结构为 `table > thead > tr > th > .cell`，inline style 在 `.cell` 层被 EP 默认 `font-size: 14px` 覆盖
2. `:deep(.gt-tb-font-sm) .cell { font-size: 12px !important }` 可穿透 scoped 样式边界
3. 动态 class 绑定 `:class="'gt-tb-font-' + displayPrefs.fontSize"` 响应式自动更新

### CSS 定义位置

在 `audit-platform/frontend/src/assets/gt-design-tokens.css` 中新增：

```css
/* 表格字号 4 档 — 全局生效 */
.gt-tb-font-xs :deep(th .cell),
.gt-tb-font-xs :deep(td .cell) { font-size: 11px !important; }
.gt-tb-font-sm :deep(th .cell),
.gt-tb-font-sm :deep(td .cell) { font-size: 12px !important; }
.gt-tb-font-md :deep(th .cell),
.gt-tb-font-md :deep(td .cell) { font-size: 13px !important; }
.gt-tb-font-lg :deep(th .cell),
.gt-tb-font-lg :deep(td .cell) { font-size: 14px !important; }
```

注意：由于 `:deep()` 仅在 scoped style 中生效，全局 CSS 需使用非 scoped 写法（直接 `.gt-tb-font-sm th .cell`）。

### 迁移策略

1. grep 全仓库 `fontSize.*displayPrefs\|fontConfig.*tableFont` 找到所有使用点
2. 逐个替换为 `:class` 绑定
3. 替换后在 el-table 的 `updated` hook 中调用 `tableRef.value?.doLayout()` 确保列宽重算

---

## F3 穿透面包屑 — 架构设计

### 组件设计

```
┌─────────────────────────────────────────────────┐
│ DrilldownBreadcrumb.vue                          │
│   props: { stack: NavigationItem[] }             │
│   ┌─────────────────────────────────────────┐   │
│   │ 试算表 > 辅助余额 > 明细账 > 底稿D2-1  │   │
│   └─────────────────────────────────────────┘   │
│   emit: jump(index: number)                      │
└─────────────────────────────────────────────────┘
```

### 与 useNavigationStack 联动

```typescript
// useNavigationStack 已有结构（代码锚定 2026-05-21 确认）
interface NavigationEntry {
  source_view: string       // 来源路由 path
  row_index?: number        // 可选：表格行索引
  query?: Record<string, string>  // 可选：查询参数
  scroll_position?: number  // 可选：滚动位置
}

// 已有 API：push / pop / goBack / canGoBack / stack
// 缺失：jumpTo(index) 方法 + label 字段 → 需扩展
```

**需扩展**：
1. NavigationEntry 新增 `label: string` 字段（面包屑显示文本）
2. 新增 `jumpTo(index: number)` 方法：截断 stack 到 index 位置 + router.push(stack[index])

```typescript
// 扩展后的 useNavigationStack
function jumpTo(index: number) {
  if (index < 0 || index >= stack.value.length) return
  const entry = stack.value[index]
  stack.value = stack.value.slice(0, index)  // 截断到目标位置
  _router!.push({ path: entry.source_view, query: entry.query })
}
```

### 放置位置

在 `DefaultLayout.vue` 的 `<router-view>` 上方，仅在 `stack.length > 1` 时显示：

```html
<DrilldownBreadcrumb
  v-if="navigationStack.length > 1"
  :stack="navigationStack"
  @jump="onBreadcrumbJump"
/>
```

### 折叠逻辑

- stack.length ≤ 5：全部显示
- stack.length > 5：显示 `[0] > ... > [n-2] > [n-1] > [n]`（首项 + 省略号 + 最后 3 项）
- hover 省略号时 el-popover 展开完整路径

---

## F4 工具栏 compact 模式 — 架构设计

### GtToolbar 改造

```typescript
// 新增 prop
interface GtToolbarProps {
  variant?: 'default' | 'compact'  // 新增 compact
}
```

### compact 模式布局

```
┌──────────────────────────────────────────────────────────┐
│ [标题/信息]                    [刷新] [导出] [保存] [全屏] │  ← 单行 36px
└──────────────────────────────────────────────────────────┘
```

vs 当前 default 模式：
```
┌──────────────────────────────────────────────────────────┐
│ [Tab1] [Tab2] [Tab3]                                      │  ← Tab 栏
├──────────────────────────────────────────────────────────┤
│ [+ 新增] [删除]              [刷新] [导出] [保存] [全屏]  │  ← 工具栏
├──────────────────────────────────────────────────────────┤
│ 单位：万元 | 年度：2025 | 模板：国企合并                  │  ← 信息栏
└──────────────────────────────────────────────────────────┘
```

compact 模式将信息栏内容移到 Tab 栏左侧，操作按钮移到 Tab 栏右侧，消除独立工具栏行。

### 适用页面清单

| 页面 | 当前行数 | compact 后行数 | 节省 |
|------|---------|---------------|------|
| TrialBalance | 3 | 2 | 1 行 |
| WorkpaperList | 2 | 1 | 1 行 |
| Adjustments | 3 | 2 | 1 行 |
| Misstatements | 2 | 1 | 1 行 |
| StaffManagement | 2 | 1 | 1 行 |

---

## F5 并发编辑版本锁 — 架构设计（前端补全）

### 现状确认（Sprint 0 代码锚定 2026-05-21）

后端已完整实现：
- `working_paper` 表（单数）有 `file_version` 字段（Integer, server_default=1）
- `POST /working-papers/{wp_id}/univer-save` 端点已实现 `expected_version` 参数
- 版本不一致时返回 409 + `{ error_code: "VERSION_CONFLICT", server_version, expected_version }`

### 前端需补全

```typescript
// WorkpaperEditor.vue — 验证 onSave 是否已处理 409
// 当前 univer-save 调用可能未 catch 409，需确认并补全：
try {
  const res = await http.post(P_wp.univerSave(projectId, wpId), {
    snapshot,
    expected_version: localFileVersion.value,
  })
  localFileVersion.value = res.file_version  // 更新本地版本号
} catch (err) {
  if (err.response?.status === 409) {
    showConflictDialog(err.response.data)
  }
}
```

### ConflictDialog 设计（不变）

```
┌─────────────────────────────────────────────┐
│ ⚠️ 保存冲突                                 │
│                                              │
│ 底稿已被他人修改，请刷新后重试               │
│ 服务器版本：v5                               │
│ 您的版本：v4                                 │
│                                              │
│ [刷新查看最新版]  [强制覆盖(仅管理层)]        │
└─────────────────────────────────────────────┘
```

---

## Error Handling

| 场景 | 处理方式 |
|------|---------|
| F1 搜索 API 超时 | 前端显示"搜索超时，请重试"，不阻塞弹窗 |
| F1 搜索 API 500 | 前端显示"搜索服务暂不可用"，保留最近访问列表可用 |
| F2 doLayout 失败 | 静默忽略（不影响功能，仅列宽可能不完美） |
| F3 stack 为空 | 不显示面包屑（v-if 守卫） |
| F5 409 冲突 | 弹出 ConflictDialog，用户选择后续操作 |
| F5 强制覆盖 | 请求携带 `force: true`，后端跳过版本检查直接保存 |

---

## 测试策略

### 后端测试

| 文件 | 覆盖 |
|------|------|
| `test_global_search_endpoint.py` | F1 搜索 API：happy path / 空结果 / 拼音匹配 / 权限过滤 / 超时 |
| `test_workpaper_version_lock.py` | F5 版本锁：正常保存 version+1 / 409 冲突 / 强制覆盖 / 并发模拟 |

### 前端测试

| 文件 | 覆盖 |
|------|------|
| `GlobalSearchDialog.spec.ts` | F1：Ctrl+K 打开 / 输入搜索 / 键盘导航 / 点击跳转 / 最近访问 |
| `DrilldownBreadcrumb.spec.ts` | F3：正常显示 / 折叠逻辑 / 点击跳转 / stack 联动 |
| `GtToolbar.spec.ts` | F4：compact 模式渲染 / 按钮位置 / 高度约束 |
| `ConflictDialog.spec.ts` | F5：409 触发显示 / 刷新按钮 / 强制覆盖权限控制 |

### PBT

| 编号 | Property | 策略 |
|------|----------|------|
| PBT-P1 | 版本号单调递增 | `st.integers(1, 1000)` 生成初始版本，模拟 N 次保存后 version == initial + N |
