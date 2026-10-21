# 公式管理体验优化 — 设计文档

> spec: `formula-management-ux-improvements`

## §1 总体方案

6 批独立交付（A/B/D/E/G/C），各批改动文件不交叉。每批前端为主、后端按需。

## §2 A 批：公式编辑器实时语法校验 + 地址选择增强

### §2.1 公式语法解析器（前端纯函数）

新建 `frontend/src/composables/formula/formulaSyntaxParser.ts`：

```typescript
// 解析 TB('code','field') / WP('wp','sheet','coord') / NOTE('section','field') / ROW('code') / REPORT('code','field')
// + 数学运算符 + SUM_ROW('start','end')
interface ParseToken {
  type: 'function' | 'string' | 'operator' | 'number' | 'paren' | 'unknown'
  value: string
  start: number
  end: number
  error?: string  // 语法错误描述
}

export function tokenize(expr: string): ParseToken[]
export function validate(expr: string): ValidationResult
export interface ValidationResult {
  valid: boolean
  errors: Array<{ start: number; end: number; message: string }>
  functions: Array<{ name: string; args: string[]; start: number; end: number }>
}
```

### §2.2 语法高亮渲染

在 FormulaManagerDialog 的公式输入列，编辑态替换 `<el-input>` 为自定义 `<FormulaInput>`：
- 底层用 `<div contenteditable>` + 覆盖层着色（函数名蓝、参数绿、错误红色下划线）
- 输入 debounce 500ms 后调 `validate()`，错误 inline 提示
- `v-model` 绑定保持与原 `editFormula` 兼容

### §2.3 快捷按钮参数选择器

改造 FormulaManagerDialog 的 TB/WP/NOTE/ROW 快捷按钮：

| 按钮 | 点击行为 | 数据源 |
|------|----------|--------|
| TB | 弹出科目选择 popover（试算表科目树） | `useAddressRegistry().tbAddresses` (ACNR) |
| WP | 弹出底稿选择 popover（底稿编码+sheet） | `useAcnr().listSheets(wpCode)` |
| NOTE | 弹出章节选择 popover（附注章节树） | `loadNoteTree()` (已有) |
| ROW | 弹出行次选择 popover（当前报表行） | `currentRows` (已有) |

选中后自动填入完整参数到光标位置，如 `TB('1001','期末余额')`。

### §2.4 自动补全

在 FormulaInput 中，输入 `TB(` 或 `'` 后触发补全下拉：
- 补全候选按数据源分类（科目/底稿/章节/行次）
- 上下箭头选择，Enter/Tab 确认
- 补全后自动补右括号

### §2.5 改动文件清单（A 批）

| 文件 | 改动 |
|------|------|
| 新建 `frontend/src/composables/formula/formulaSyntaxParser.ts` | 解析器纯函数 |
| 新建 `frontend/src/components/formula/FormulaInput.vue` | 语法高亮输入组件 |
| 新建 `frontend/src/components/formula/FormulaParamPicker.vue` | 参数选择弹出组件 |
| 改 `frontend/src/components/formula/FormulaManagerDialog.vue` | 接入 FormulaInput + ParamPicker |
| 新建 `frontend/src/composables/formula/__tests__/formulaSyntaxParser.spec.ts` | 解析器测试 |

## §3 D 批：待确认智能分组

### §3.1 分组逻辑

改造 FormulaPendingSyncDialog：

```typescript
// 按域分组
const grouped = computed(() => {
  const groups = new Map<string, PendingItem[]>()
  for (const item of items.value) {
    const key = item.domain
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  return [...groups.entries()].map(([domain, items]) => ({
    domain,
    label: domainLabel(domain),
    items,
    count: items.length,
    // 来源统计
    sources: [...new Set(items.map(i => i.upstream_origin_label))],
  }))
})
```

### §3.2 组级批量操作

每组头部增加按钮行：
```html
<div class="gt-fps-group-header" @click="toggleGroup(group.domain)">
  <span>{{ group.expanded ? '▼' : '▶' }} {{ group.label }}（{{ group.count }}）</span>
  <el-tag size="small">来自{{ group.sources.join('、') }}</el-tag>
  <el-button size="small" @click.stop="setGroupAll(group.domain, 'adopt')">全部采用</el-button>
  <el-button size="small" @click.stop="setGroupAll(group.domain, 'keep')">全部保留</el-button>
</div>
```

### §3.3 改动文件清单（D 批）

| 文件 | 改动 |
|------|------|
| 改 `frontend/src/components/formula/settings/FormulaPendingSyncDialog.vue` | 分组 + 折叠 + 组级批量 |

## §4 B 批：推送覆盖率仪表盘

### §4.1 覆盖率数据

后端已有 `formula_push_coverage.json`（80 码），增加按循环分组的接口：

```python
# backend/app/routers/formula_push.py 新增端点
@router.get("/coverage")
async def get_push_coverage():
    """返回推送覆盖率概览（静态数据，无需鉴权）"""
    # 读 formula_push_coverage.json + 按首字母分循环
```

### §4.2 前端覆盖率卡片

在 FormulaManagerDialog 的公式看板（📊）增加覆盖率区域：

```html
<div class="gt-fp-coverage">
  <div class="gt-fp-coverage-header">
    <span>推送覆盖率</span>
    <span class="gt-fp-coverage-pct">{{ coveragePct }}%</span>
  </div>
  <el-progress :percentage="coveragePct" :stroke-width="8" />
  <div v-for="cycle in cycles" class="gt-fp-cycle-row">
    <span>{{ cycle.label }}</span>
    <el-progress :percentage="cycle.pct" :stroke-width="6" :status="cycle.pct === 100 ? 'success' : ''" />
    <span v-if="cycle.reason" class="gt-fp-muted">{{ cycle.reason }}</span>
  </div>
</div>
```

### §4.3 未接入空状态文案

替换 FormulaPushPanel 的笼统空状态：

```typescript
const NOT_NEEDED_REASONS: Record<string, string> = {
  A: '报表/调整类底稿不涉及数值回写试算表',
  B: '控制了解/计划类底稿，审计程序不产出数值',
  C: '控制测试底稿只记录测试结论，不涉及科目金额',
  S: '专项底稿按项目自定义，不走统一推送通道',
}
```

### §4.4 改动文件清单（B 批）

| 文件 | 改动 |
|------|------|
| 新增 `backend/app/routers/formula_push.py` 端点 `GET /coverage` | 覆盖率按循环分组 |
| 改 `frontend/src/components/formula/FormulaManagerDialog.vue` | 看板增加覆盖率区域 |
| 改 `frontend/src/components/formula/FormulaPushPanel.vue` | 改进空状态文案 |

## §5 E 批：表间审核历史查看

### §5.1 历史查询端点

复用已有的 `draft_refresh_audit` + `cross_check_results` 表：

```python
# backend/app/routers/formula_management.py（已有）
@router.get("/{project_id}/formula/cross-check-history")
async def cross_check_history(project_id: UUID, year: int, limit: int = 20):
    """返回表间审核执行历史（recent runs + per-run results）"""
```

### §5.2 前端历史视图

在 FormulaManagerDialog 的表间审核模式增加折叠区：

```html
<el-collapse v-model="crossCheckHistoryOpen" class="gt-fm-cc-history">
  <el-collapse-item title="执行历史" name="history">
    <el-table :data="crossCheckHistory" size="small" ...>
      <el-table-column label="时间" />
      <el-table-column label="通过/失败" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button size="small" @click="showRunDetail(row)">查看明细</el-button>
          <el-button v-if="previousRun" size="small" @click="compareRuns(previousRun, row)">对比上次</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-collapse-item>
</el-collapse>
```

### §5.3 改动文件清单（E 批）

| 文件 | 改动 |
|------|------|
| 新增后端端点 `GET /cross-check-history` | 查询 draft_refresh_audit + cross_check_results |
| 改 `frontend/src/components/formula/FormulaManagerDialog.vue` | 表间审核增加历史折叠区 |

## §6 G 批：公式依赖关系可视化

### §6.1 后端依赖查询端点

利用已有的 `formula_reverse_index` + `note_formula_dependency_service`：

```python
# backend/app/routers/formula_settings.py 新增
@project_router.get("/dependencies")
async def formula_dependencies(project_id: UUID, addr_id: str, depth: int = 2):
    """查询公式的上下游依赖链"""
    # upstream: parse_formula_dependencies(formula_text) → 解析 TB/WP/NOTE/ROW 引用
    # downstream: formula_reverse_index.get_dependents(addr_id)
    # 递归到 depth 层
```

### §6.2 前端依赖面板

在 FormulaManagerDialog 中，选中公式行后右侧显示依赖面板：

```html
<div v-if="selectedRow && showDependencyPanel" class="gt-fm-dep-panel">
  <div class="gt-fm-dep-title">📊 依赖关系</div>
  <!-- 引用了谁 -->
  <div class="gt-fm-dep-section">
    <div class="gt-fm-dep-section-title">⬆ 引用了（{{ upstream.length }}）</div>
    <div v-for="dep in upstream" class="gt-fm-dep-item" @click="jumpToDep(dep)">
      <el-tag size="small" :type="depTypeTag(dep.type)">{{ dep.type }}</el-tag>
      <span>{{ dep.label }}</span>
      <span class="gt-fm-dep-value">{{ dep.value }}</span>
    </div>
  </div>
  <!-- 被谁引用 -->
  <div class="gt-fm-dep-section">
    <div class="gt-fm-dep-section-title">⬇ 被引用（{{ downstream.length }}）</div>
    <div v-for="dep in downstream" class="gt-fm-dep-item" @click="jumpToDep(dep)">
      <el-tag size="small" :type="depTypeTag(dep.type)">{{ dep.type }}</el-tag>
      <span>{{ dep.label }}</span>
    </div>
  </div>
</div>
```

### §6.3 改动文件清单（G 批）

| 文件 | 改动 |
|------|------|
| 新增后端端点 `GET /dependencies` | 依赖查询（reverse_index + parse_formula_dependencies） |
| 改 `frontend/src/components/formula/FormulaManagerDialog.vue` | 增加依赖面板 |

## §7 C 批：模板发现性（最后，需产品拍板）

### §7.1 方案

1. 项目创建成功后 `ElMessageBox.confirm` 提示订阅模板
2. `FormulaTemplateManager` 列表增加「推荐」tag（匹配 `applicable_scope`）
3. 订阅确认前复用 `FormulaPublishPreviewDialog` 展示差异

### §7.2 改动文件清单（C 批）

| 文件 | 改动 |
|------|------|
| 改 `frontend/src/views/ProjectWizard.vue` | 创建成功后提示 |
| 改 `frontend/src/components/formula/settings/FormulaTemplateManager.vue` | 推荐标签 |
| 改 `frontend/src/components/formula/settings/FormulaTemplateSubscribeDialog.vue` | 订阅前差异预览 |

## §8 偏离记录

（交付过程中如有设计偏离在此登记）
