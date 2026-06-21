# 设计：多 Sheet 底稿 OnlyOffice 渲染

## 架构概览

```
GtWpRenderer
  ├── GtWpToolbar (统一工具栏)
  ├── [HTML 白名单 sheet] → 原有组件 (b-index / a-program / audit-sheet / c-note / d-form)
  └── [OnlyOffice sheet] → GtOnlyOfficeSheet (新组件，iframe 嵌入)
```

## §1 后端改动

### 1.1 componentType 白名单判定

在 `wp_render_config.py` dispatch 循环中，当 `renderer=None`（无后端策略）且 `_is_multi_sheet=True` 时：

```python
# HTML 白名单 componentType — 走 grid 兜底
_HTML_WHITELIST = {"b-index", "a-program-console", "audit-sheet", "c-note-table", "d-form-table"}

if component_type not in _HTML_WHITELIST:
    # 非白名单 → 走 OnlyOffice
    component_type = "onlyoffice-sheet"
    sheet_html_data = {"onlyoffice": True, "sheet_name": cls.sheet_name}
```

### 1.2 OnlyOffice WOPI 端点（底稿级）

新增 `wp_onlyoffice_router.py`：

- `GET /api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-config`
  - 返回 OnlyOffice editor config（doc_key / url / callback / JWT）
  - 文件路径：项目存储优先 → 回退模板文件
  
- `GET /api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents`
  - WOPI GetFile：返回 xlsx 文件内容（单 sheet 提取或全文件）
  
- `POST /api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback`
  - 回调：status=2 时下载编辑后文件并存储到项目目录

### 1.3 文件管理

- 首次打开 sheet：从模板复制到 `storage/projects/{pid}/workpapers/onlyoffice/{wp_code}_{sheet_name}.xlsx`
- 后续打开：直接用已有文件
- 保存回调：覆盖写入

## §2 前端改动

### 2.1 GtOnlyOfficeSheet.vue（新组件）

```vue
<template>
  <div class="gt-onlyoffice-sheet">
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">OnlyOffice 不可用，已降级为只读</div>
    <div ref="editorContainer" class="editor-container" />
  </div>
</template>
```

- Props: `wpId`, `sheetName`, `readonly`
- 调用 `/onlyoffice-config` 获取配置
- 动态加载 OnlyOffice JS API（`/web-apps/apps/api/documents/api.js`）
- 创建 `new DocsAPI.DocEditor(container, config)`

### 2.2 GtWpRenderer 路由分发

在 `noRendererGridFallback` 之前加 OnlyOffice 判断：

```typescript
const isOnlyOfficeSheet = computed(() => {
  const hd = activeSheetHtmlData.value as any
  return hd?.onlyoffice === true
})
```

模板中：
```html
<GtOnlyOfficeSheet v-else-if="isOnlyOfficeSheet" ... />
<GtGridSheet v-else-if="noRendererGridFallback" ... />  <!-- 降级 -->
```

### 2.3 降级逻辑

- 前端先 fetch `/onlyoffice-config`，如果 404 或超时 → 回退 GtGridSheet
- OnlyOffice iframe 加载失败（onerror）→ 切换到 grid 兜底

## §3 数据流

```
用户点击非白名单 Tab
  → GtWpRenderer 检测 componentType="onlyoffice-sheet"
  → GtOnlyOfficeSheet mounted
  → GET /api/workpapers/{wpId}/sheets/{sheetName}/onlyoffice-config
  → 后端：检查项目存储有无文件 → 无则从模板复制 → 生成 WOPI config + JWT
  → 前端：new DocsAPI.DocEditor(config)
  → OnlyOffice iframe 加载 xlsx
  → 用户编辑 → Ctrl+S / 自动保存
  → OnlyOffice POST callback (status=2, url)
  → 后端下载编辑后文件 → 覆盖存储
```

## §4 测试策略

- 单元测试：WOPI config 生成 + JWT 签名
- 集成测试：OnlyOffice 容器不可用时降级到 grid
- 冒烟测试：render-config 返回 `onlyoffice-sheet` componentType
- Playwright：D0 底稿 tab 切换到函证检查表 → OnlyOffice iframe 可见

## §5 风险

- OnlyOffice 容器内存占用（~500MB），并发打开多文件时需关注
- JWT secret 三处一致性（已有铁律守卫）
- 单 sheet 提取（从多 sheet xlsx 中只提取一个 sheet 给 OnlyOffice）的可行性待验证
