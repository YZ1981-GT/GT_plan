# Spec B (R10) — Linkage & Tokens · Design

**版本**：v1.0
**起草日期**：2026-05-16
**关联**：`requirements.md` v1.0

---

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-16 | 设计稿初稿 | requirements v1.0 完成 |
| v1.1 | 2026-05-16 | D6 baselines.json 字段命名统一为 `{property}-{format}-vue-files`，el-table-naked 改占位标注 | 复盘 B1 修复 |

---

## 1. 总体架构

```
显示治理三条线
├─ Sprint 1: 字号 1565 → 0（4 批迁移）
│  └─ 强制依赖：stylelint 卡点 + gt-tokens.css 7 级字号变量
├─ Sprint 2: 颜色 1611 → < 50（4 批） + 背景 712 → < 30（4 批）
│  └─ 依赖：gt-tokens.css 5 语义色 + 9 阶灰度 + 6 级背景
└─ Sprint 3: GtEditableTable 拆分 + 右键穿透补完 + CI baseline 卡点

Sprint 0（启动条件核验，0.5 天）必须先做：
├─ grep 实测 9 项 baseline
├─ 装 stylelint（warning 级别）
└─ gt-tokens.css 颜色变量补完
```

---

## 2. 架构决策

### D1 token 命名遵循已有约定不动用户视觉记忆

**问题**：是否重命名现有 token（如 `--gt-font-size-md`）让命名更通用？

**决策**：**不动**。`--gt-font-size-{xs,sm,md,lg,xl,2xl,3xl}` 7 级已经在 R8/R9 中定型，前端代码若干文件已使用。本 spec 只补完不重命名，避免增加无关 PR 噪声。

**影响**：颜色 / 背景命名同样遵循"扩充不重命名"原则。

### D2 stylelint 三阶启用避免 CI 红一周

**问题**：stylelint 规则一上来就 `error` 级别会让 CI 红到 Sprint 1 末尾，阻塞所有 PR。

**决策**：
- Sprint 0 第一天：装机 + 规则全 `warning`
- Sprint 1 期间：每批迁移完成后该批视图改为局部 `error`
- Sprint 1 末尾：全局规则转 `error`
- 实施期间允许 `// stylelint-disable-next-line` 临时豁免（迁移到 token 即移除）

### D3 GtEditableTable 兼容 wrapper 60 天观察期

**问题**：3 个使用方迁移到新组件后，能否立即删除旧组件？

**决策**：**不删，改 wrapper**。
- `GtEditableTable.vue` 内部根据 `mode` prop 路由：
  - `mode='display'` → 渲染 GtTableExtended
  - `mode='edit'` (默认) → 渲染 GtFormTable
- 加 `console.warn` 提示迁移路径
- 60 天观察期后无外部直接调用 → 删除 wrapper
- 实施期间任何新视图必须直接用 GtTableExtended/GtFormTable，不允许新增 GtEditableTable 调用

**理由**：避免 breaking 改动；3 个使用方测试覆盖如有遗漏，wrapper 提供安全网。

### D4 4 批迁移按"视觉影响域"切分

**问题**：1500+ 处字号迁移如何切批？按字母排序 / 按文件夹 / 按视觉影响？

**决策**：**按视觉影响域 4 批**：
- 批 1 编辑器 5 视图（视觉最关键，合伙人/审计助理日常使用）
- 批 2 表格类 6 视图（数据密集，金额对齐敏感）
- 批 3 Dashboard 6 视图（合伙人/项目经理首页）
- 批 4 剩余 ~30 视图（次要场景批量处理）

**理由**：每批结束后立即让对应角色试用 → 快速发现视觉问题；不会一次破坏所有视觉记忆。

### D5 Misstatements/Adjustments 关联底稿端点 SQL 模式复用

**问题**：要不要为 Misstatements/Adjustments 各自建独立端点？

**决策**：**不建独立端点，复用 `wp_account_mapping` 反查模式**。
- 后端共享 helper 函数 `find_workpapers_by_account_codes(db, project_id, year, account_codes: list[str])` 在 `app/services/workpaper_query.py`
- 三个端点（reports.relatedWorkpapers / disclosure.relatedWorkpapers / misstatements.relatedWorkpapers / adjustments.relatedWorkpapers）都调这个 helper
- SQL 模式：`SELECT wp_index.id, wp_code, wp_name FROM wp_index JOIN wp_account_mapping ON wp_account_mapping.wp_code = wp_index.wp_code WHERE account_code = ANY(:codes) AND project_id = :pid`

### D6 baseline 文件持久化到 git

**问题**：CI baseline 数字写在哪里？

**决策**：`.github/workflows/baselines.json` 持久化（字段命名统一为 `{property}-{format}-vue-files`）：
```json
{
  "font-size-px-vue-files": 0,
  "color-hex-vue-files": 50,
  "background-hex-vue-files": 30,
  "el-table-naked-vue-files": 0
}
```
每次降低后开 PR 同时更新 baseline，不允许悄悄放宽。`el-table-naked-vue-files` 字面量 `0` 是占位值，由 Sprint 0 grep 实测后写入真实数字（见 tasks 0.1）。

### D7 颜色透明度场景保留 RGBA 字面量

**问题**：是否所有 `rgba(0,0,0,0.5)` / `#rrggbb` 都要 token 化？

**决策**：**只迁移文字色 + 实色背景，透明度调节场景保留**。
- token 化：`color: #4b2d77` → `color: var(--gt-color-primary)`
- 保留：`background: rgba(75, 45, 119, 0.05)`（hover/选中等透明度叠加场景）
- 长期方案：用 `color-mix(in srgb, var(--gt-color-primary) 5%, transparent)`，但本期不做（CSS 兼容性问题）

### D8 visual diff 用人工截图不引入 Playwright

**问题**：Sprint 1-3 视觉回归是否需要自动化？

**决策**：**人工截图对比足够**。
- 30 个核心视图 × 3 个 Sprint = 90 次截图，1 个设计师/合伙人 1 小时可完成
- 引入 Playwright 视觉回归需 baseline 截图体系（约 5 天工时），ROI 不高
- 写入 NF5 不做清单 O5

---

## 3. token 体系扩展

### 3.1 字号（已就绪，不改）

```css
:root {
  --gt-font-size-xs: 11px;
  --gt-font-size-sm: 12px;
  --gt-font-size-md: 13px;   /* 默认正文 */
  --gt-font-size-lg: 14px;
  --gt-font-size-xl: 16px;
  --gt-font-size-2xl: 18px;
  --gt-font-size-3xl: 20px;
}
```

### 3.2 颜色（Sprint 0 补完）

```css
:root {
  /* 5 语义色（已就绪） */
  --gt-color-primary: #4b2d77;
  --gt-color-success: #67c23a;
  --gt-color-warning: #e6a23c;
  --gt-color-danger: #f56c6c;
  --gt-color-info: #909399;

  /* 灰度 9 阶（Sprint 0 补完） */
  --gt-color-text-primary: #303133;
  --gt-color-text-regular: #606266;
  --gt-color-text-secondary: #909399;
  --gt-color-text-tertiary: #c0c4cc;
  --gt-color-text-placeholder: #c0c4cc;
  --gt-color-text-disabled: #c0c4cc;
  --gt-color-border: #dcdfe6;
  --gt-color-border-light: #e4e7ed;
  --gt-color-border-lighter: #ebeef5;
}
```

### 3.3 背景（Sprint 0 补完，6 级）

```css
:root {
  --gt-bg-default: #ffffff;
  --gt-bg-subtle: #f5f7fa;
  --gt-bg-info: #ecf5ff;
  --gt-bg-warning: #fdf6ec;
  --gt-bg-success: #f0f9eb;
  --gt-bg-danger: #fef0f0;
}
```

---

## 4. 组件设计

### 4.1 GtTableExtended.vue（约 200 行）

```vue
<template>
  <div class="gt-table-extended">
    <el-table
      :data="data"
      :height="height"
      :border="border"
      :class="['gt-tb-purple-header', `gt-tb-font-${size}`]"
      v-bind="$attrs"
    >
      <slot />
    </el-table>
    <CellContextMenu
      v-if="enableContextMenu"
      :visible="ctx.contextMenu.visible"
      ...
    >
      <slot name="context-menu-extra" />
    </CellContextMenu>
  </div>
</template>

<script setup lang="ts">
interface Props {
  data: any[]
  size?: 'sm' | 'md' | 'lg'  // 字号 class
  height?: string | number
  border?: boolean
  enableContextMenu?: boolean
  enableCopy?: boolean   // 启用复制粘贴右键菜单
}
</script>

<style scoped>
/* 紫色表头 + 字号 class（移植自 gt-table.css） */
.gt-tb-purple-header :deep(th) { background: #f0edf5; color: #4b2d77; }
.gt-tb-font-sm :deep(.cell) { font-size: var(--gt-font-size-sm) !important; }
.gt-tb-font-md :deep(.cell) { font-size: var(--gt-font-size-md) !important; }
.gt-tb-font-lg :deep(.cell) { font-size: var(--gt-font-size-lg) !important; }
</style>
```

### 4.2 GtFormTable.vue（约 250 行）

```vue
<template>
  <GtTableExtended :data="rows" enable-context-menu>
    <slot />
    <!-- 行内编辑：通过 slot 传入可编辑列模板 -->
  </GtTableExtended>
  <div v-if="isDirty" class="gt-form-table-dirty-bar">
    <span>有 {{ dirtyCount }} 行未保存</span>
    <el-button @click="onUndo">撤销</el-button>
    <el-button type="primary" @click="onSave">保存</el-button>
  </div>
</template>

<script setup lang="ts">
const isDirty = ref(false)
const dirtyCount = ref(0)
// 校验规则 + 撤销栈 + dirty 标记的核心逻辑（从 GtEditableTable 移植）
</script>
```

### 4.3 GtEditableTable.vue（兼容 wrapper）

```vue
<template>
  <GtTableExtended v-if="mode === 'display'" v-bind="$attrs">
    <slot />
  </GtTableExtended>
  <GtFormTable v-else v-bind="$attrs">
    <slot />
  </GtFormTable>
</template>

<script setup lang="ts">
const props = defineProps<{ mode?: 'display' | 'edit' }>()
const _mode = computed(() => props.mode ?? 'edit')
onMounted(() => {
  console.warn('[GtEditableTable] 已迁移到 GtTableExtended/GtFormTable，请按场景选择')
})
</script>
```

---

## 5. 右键穿透补完

### 5.1 Misstatements 右键菜单

```vue
<!-- Misstatements.vue -->
<el-table @cell-contextmenu="onCellContextMenu" ref="tableRef">
  ...
</el-table>

<CellContextMenu :visible="ctx.contextMenu.visible" ...>
  <div class="gt-ucell-ctx-item" @click="onViewRelatedWp">
    <span class="gt-ucell-ctx-icon">📝</span> 查看关联底稿
  </div>
</CellContextMenu>

<script setup lang="ts">
const ctx = useCellSelection()
const penetrate = usePenetrate()

async function onViewRelatedWp() {
  const code = currentRow.value?.standard_account_code
  if (!code) return
  await penetrate.toWorkpapers(projectId.value, year.value, code)
}
</script>
```

### 5.2 Adjustments 右键菜单

类似模式，按 `line_items[].standard_account_code` 反查。

### 5.3 后端端点（按需新建）

`backend/app/services/workpaper_query.py`：
```python
async def find_workpapers_by_account_codes(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_codes: list[str],
) -> list[dict]:
    """共享 helper：按科目编码反查关联底稿"""
    sql = text("""
        SELECT DISTINCT w.id, w.wp_code, w.wp_name
        FROM wp_index w
        JOIN wp_account_mapping m ON m.wp_code = w.wp_code
        WHERE m.account_code = ANY(:codes)
          AND w.project_id = :pid
          AND w.year = :yr
          AND w.is_deleted = false
    """)
    result = await db.execute(sql, {"codes": account_codes, "pid": project_id, "yr": year})
    return [dict(r) for r in result.mappings()]
```

3 个 router 函数（misstatements / adjustments / 已有的 reports / disclosure_notes）调用同一 helper。

---

## 6. CI baseline 卡点设计

### 6.1 baselines.json 持久化

```json
{
  "font-size-px-vue-files": 0,
  "color-hex-vue-files": 50,
  "background-hex-vue-files": 30,
  "el-table-naked-vue-files": 0
}
```

### 6.2 CI step 模板

```yaml
- name: Display token guard
  run: |
    cd audit-platform/frontend
    FONT_COUNT=$(rg -c "font-size:\s*\d+px" src --type=vue | wc -l)
    BASELINE=$(jq -r '."font-size-px-vue-files"' .github/workflows/baselines.json)
    if [ $FONT_COUNT -gt $BASELINE ]; then
      echo "FAIL: font-size hardcode count $FONT_COUNT > baseline $BASELINE"
      exit 1
    fi
```

### 6.3 stylelint 配置

```json
// .stylelintrc.json
{
  "extends": ["stylelint-config-standard-vue"],
  "rules": {
    "declaration-property-value-disallowed-list": [
      {
        "font-size": ["/^\\d+px$/"],
        "color": ["/^#[0-9a-fA-F]{3,6}$/"],
        "background": ["/^#[0-9a-fA-F]{3,6}$/"],
        "background-color": ["/^#[0-9a-fA-F]{3,6}$/"]
      },
      { "severity": "warning" }   // Sprint 0/1 是 warning，末尾改 error
    ]
  }
}
```

---

## 7. 风险与缓解

参见 requirements §7。补充设计层面：

| 风险 | 概率 | 设计层面缓解 |
|------|------|--------------|
| 字号迁移破坏字体回退（Arial Narrow） | 中 | `gt-amt` class 保持原字体 stack；token 只控 size 不控 family |
| color-mix() 兼容性 | 低 | 本期不用 color-mix，透明度叠加保留 rgba 字面量 |
| baselines.json 多人 PR 冲突 | 中 | 加 git lock + PR review checklist：改动 baseline 必须解释为什么减少 |
| GtEditableTable wrapper 内部 slot 透传 bug | 中 | 单测覆盖 5 种 slot 场景（default / context-menu-extra / column / empty / pagination） |

---

## 8. 与 Spec C 协调

| 文件 | Spec B 改动 | Spec C 改动 | 协调策略 |
|------|------------|------------|---------|
| `Adjustments.vue` | F8 加右键菜单 + Sprint 1 字号 token 化 | confirmDangerous 删除分录组验证 | Spec C 先合（改动小），Spec B 基于此基线再改 |
| `DegradedBanner.vue` | Sprint 2 颜色 token 化 | Sprint 1 三档扩展 | Spec C Sprint 1 末尾 Spec B 同步刷颜色 |
| `gt-tokens.css` | Sprint 0 补完 | 不动 | Spec B 主导 |

---

## 9. 数据流图

```
[Sprint 0]
gt-tokens.css 补完 → stylelint warning 模式 → grep baseline 实测

[Sprint 1: 字号 4 批]
批 1 编辑器 5 视图 → 设计师截图对比 → 通过 → CI baseline -X
批 2 表格类 6 视图 → 设计师截图对比 → 通过 → CI baseline -Y
批 3 Dashboard 6 视图 → 通过 → CI baseline -Z
批 4 剩余 ~30 视图 → 通过 → CI baseline = 0
                                  ↓
                          stylelint 转 error

[Sprint 2: 颜色+背景]
颜色 4 批 → CI baseline < 50
背景 4 批 → CI baseline < 30

[Sprint 3: GtEditableTable + 穿透]
新建 GtTableExtended + GtFormTable
GtEditableTable 改 wrapper（保留 60 天观察）
Misstatements/Adjustments 加右键 + 后端端点（按需）
CI baseline 卡点 4 道全开
```

---

## 10. 关联文档

- `requirements.md` —— 本 spec 需求源
- `audit-platform/frontend/src/styles/gt-tokens.css` —— token 真源
- `audit-platform/frontend/src/components/common/GtEditableTable.vue` —— 现有组件待拆分
- `docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §8 §9 —— 治理战略源头
