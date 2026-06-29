# 设计文档：A16 管理层声明书聚合组件

## 概述

将 A16 及其 7 个 word-template 子底稿聚合为单一 `a16-bundle` 组件。纯 Tab 分发 + WorkpaperWordEditor 渲染，无 composable，无业务联动。遵循 GtA11Bundle 极简模式。

## 架构

```
GtWpRenderer → componentType='a16-bundle' → GtA16Bundle.vue
  └─ el-tabs
       ├─ A16-1: WorkpaperWordEditor (会计审核版)
       ├─ A16-2: WorkpaperWordEditor (整合审核版)
       ├─ A16-3: WorkpaperWordEditor (IPO补贴)
       ├─ A16-4: WorkpaperWordEditor (IPO券商审阅)
       ├─ A16-5: WorkpaperWordEditor (新三板申报)
       ├─ A16-6: WorkpaperWordEditor (合营协议)
       └─ A16-7: WorkpaperWordEditor (关联交易合规说明)
```

## 组件设计

### GtA16Bundle.vue（单文件，~80行）

```typescript
// Props
interface Props {
  wpId: string
  sheetName?: string
  readonly?: boolean
}

// Tab 配置（静态数组）
const TABS = [
  { id: 'A16-1', label: '会计审核版', wpCode: 'A16-1' },
  { id: 'A16-2', label: '整合审核版', wpCode: 'A16-2' },
  { id: 'A16-3', label: 'IPO补贴', wpCode: 'A16-3' },
  { id: 'A16-4', label: 'IPO券商审阅', wpCode: 'A16-4' },
  { id: 'A16-5', label: '新三板申报', wpCode: 'A16-5' },
  { id: 'A16-6', label: '合营协议', wpCode: 'A16-6' },
  { id: 'A16-7', label: '关联交易合规说明', wpCode: 'A16-7' },
]
```

### wp_id 解析逻辑

```typescript
// onMounted 调用 getWpIndex(projectId) 获取项目底稿索引
// 过滤 A16-* 条目生成 wpIdMap
const wpIdMap = computed(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith('A16-')) {
      map[item.wp_code] = item.wp_id
    }
  }
  return map
})

// 仅显示 wpIdMap 中存在的 Tab
const visibleTabs = computed(() =>
  TABS.filter(t => wpIdMap.value[t.wpCode])
)
```

### sheetName 路由

```typescript
const active = ref('')

// 初始化：props.sheetName > route.query.sheet > 第一个可见 Tab
onMounted(() => {
  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = visibleTabs.value[0]?.id || ''
  }
})

watch(() => props.sheetName, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) active.value = v
})
```

### Template

```html
<el-tabs v-model="active">
  <el-tab-pane v-for="t in visibleTabs" :key="t.id" :label="t.label" :name="t.id">
    <WorkpaperWordEditor
      :wp-id="wpIdMap[t.wpCode]"
      :readonly="readonly"
    />
  </el-tab-pane>
</el-tabs>
```

## 数据模型变更

### wp_code_overrides.json

```json
"A16": "a16-bundle",
"A16-1": "skip",
"A16-2": "skip",
"A16-3": "skip",
"A16-4": "skip",
"A16-5": "skip",
"A16-6": "skip",
"A16-7": "skip"
```

### htmlRendererRegistry.ts

- HtmlComponentType 联合新增 `'a16-bundle'`
- lazy import: `const GtA16Bundle = defineAsyncComponent(() => import('./GtA16Bundle.vue'))`
- REGISTRY_LIST 新增条目：componentType='a16-bundle', icon='📜', label='A16 管理层声明书', emits=[], contextProps='standard'

### wp_classification_service.py

- VALID_COMPONENT_TYPES 新增 `"a16-bundle"`

## 正确性属性

### Property 1: skip 映射完整性

*For any* wp_code_overrides.json，A16→a16-bundle，A16-1~A16-7→skip。

**Validates: Requirements 2.1, 2.2**

### Property 2: wp_id 解析正确性

*For any* wp_index 数据集（含若干 A16-* 条目 + 干扰条目），wpIdMap 仅含 A16-* 且映射正确。

**Validates: Requirements 5.1, 5.2**

### Property 3: Tab 可见性由 wp_index 存在性驱动

*For any* A16-* 子集存在于 wp_index，仅存在的子底稿显示为 Tab。

**Validates: Requirements 3.3, 5.3**

### Property 4: sheetName 路由正确性

*For any* 合法 sheetName → 激活对应 Tab；非法值 → 保持默认。

**Validates: Requirements 4.1, 4.2**

### Property 5: readonly 透传

*For any* readonly 值，所有 WorkpaperWordEditor 子组件接收一致的 readonly prop。

**Validates: Requirements 6.1**

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| wp_index API 失败 | 显示错误提示，无 Tab 可用 |
| 子底稿 wp_id 不存在 | 对应 Tab 隐藏 |
| sheetName 无效 | 默认激活第一个可见 Tab |
| WorkpaperWordEditor 加载失败 | defineAsyncComponent errorComponent 兜底 |
