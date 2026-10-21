# 设计：公式输入参数值智能补全

## §1 现有基础设施

| 组件 | 状态 | 用途 |
|------|------|------|
| `FormulaInput.vue` | ✅ 已有 | 公式输入框，已有函数名补全 + 语法高亮 |
| `cursorContext(expr, cursor)` | ✅ 已有 | 返回 `{ funcName, argIndex }` 或 null |
| `knownFunctions()` | ✅ 已有 | 21 个函数 + minArgs/maxArgs |
| `GET /trial-balance` | ✅ 已有 | 返回科目代码 + 名称 |
| `GET /report-config` | ✅ 已有 | 返回行次 + 名称 |

## §2 补全数据源

### 2.1 参数补全映射表（新增文件 `formulaParamCandidates.ts`）

```typescript
// 每个函数每个参数位的候选来源
interface ParamCandidateConfig {
  source: 'account_codes' | 'tb_fields' | 'report_rows' | 'report_fields' | 'wp_codes' | 'static'
  staticItems?: Array<{ value: string; label: string }>
}

const PARAM_CANDIDATES: Record<string, ParamCandidateConfig[]> = {
  TB:    [{ source: 'account_codes' }, { source: 'tb_fields' }],
  SUM_TB:[{ source: 'account_codes' }, { source: 'tb_fields' }],
  ROW:   [{ source: 'report_rows' }],
  SUM_ROW:[{ source: 'report_rows' }, { source: 'report_rows' }],
  REPORT:[{ source: 'report_rows' }, { source: 'report_fields' }],
  WP:    [{ source: 'wp_codes' }],
  ADJ:   [{ source: 'account_codes' }],
  AUX:   [{ source: 'account_codes' }],
  PREV:  [{ source: 'account_codes' }, { source: 'tb_fields' }],
  PRIOR: [{ source: 'account_codes' }, { source: 'tb_fields' }],
  // 数学函数无参数补全
}
```

### 2.2 静态字段候选

```typescript
const TB_FIELDS = [
  { value: '期末余额', label: '期末余额（audited_amount）' },
  { value: '期初余额', label: '期初余额（opening_balance）' },
  { value: '发生额', label: '本期发生额' },
  { value: '变动额', label: '变动额（期末-期初）' },
  { value: 'AJE调整', label: '审计调整净额' },
  { value: 'RJE调整', label: '重分类调整净额' },
]

const REPORT_FIELDS = [
  { value: '期末', label: '本期金额' },
  { value: '期初', label: '上期金额' },
]
```

### 2.3 动态数据缓存（`useFormulaParamCache` composable）

```typescript
const cache = new Map<string, { accounts: Item[]; rows: Item[]; wpCodes: Item[] }>()

async function loadAccountCodes(projectId: string): Promise<Item[]>
// → GET /api/projects/{id}/trial-balance → map to { value: code, label: `${code} - ${name}` }
// 缓存 key = projectId，同会话不重复请求
```

## §3 FormulaInput 改动

### 3.1 新增 props

```typescript
props: {
  projectId?: string    // 提供项目上下文才启用参数补全
  reportRows?: Array<{ row_code: string; row_name: string }>  // 当前报表行（父组件传入）
  wpCodes?: string[]    // 底稿编码列表
}
```

### 3.2 updateSuggestions 改造

现有逻辑：只在函数名输入阶段补全。改造后：

```
if cursorContext 返回非 null:
  → 查 PARAM_CANDIDATES[funcName][argIndex]
  → 按 source 获取候选列表
  → 如果光标前有 `'` 开头的前缀，按前缀过滤
  → 展示候选
else:
  → 走原有函数名补全逻辑
```

### 3.3 acceptSuggestion 改造

参数值补全时，需要处理引号：
- 如果光标前已有 `'`，插入 `值'`（闭合引号）
- 如果光标前无引号，插入 `'值'`（完整引号对）

## §4 文件改动清单

| 文件 | 动作 |
|------|------|
| `formulaParamCandidates.ts` | 新建：参数补全映射表 + 静态字段候选 |
| `useFormulaParamCache.ts` | 新建：科目列表缓存 composable |
| `FormulaInput.vue` | 改动：增加 props + updateSuggestions 参数补全分支 + acceptSuggestion 引号处理 |
| `FormulaManagerDialog.vue` | 改动：给 FormulaInput 传 projectId / reportRows / wpCodes |
| `formulaParamCandidates.spec.ts` | 新建：映射表和过滤逻辑的单测 |
