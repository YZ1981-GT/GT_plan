# CSS 变量覆盖率审计报告

> 日期：2026-05-12
> 对应需求：R9 F20

## 审计目标

确认所有视图使用 `--gt-font-size-*` / `--gt-space-*` / `--gt-color-*` CSS 变量，消除内联 `style="font-size: 13px"` 等硬编码。

## 全局 CSS 变量体系

### 字号变量（--gt-font-size-*）

| 变量名 | 值 | 用途 |
|--------|-----|------|
| `--gt-font-size-xs` | 11px | 辅助文字、时间戳 |
| `--gt-font-size-sm` | 12px | 表格内容、标签 |
| `--gt-font-size-base` | 13px | 正文默认 |
| `--gt-font-size-md` | 14px | 表头、按钮 |
| `--gt-font-size-lg` | 16px | 页面标题 |
| `--gt-font-size-xl` | 18px | 大标题 |

### 间距变量（--gt-space-*）

| 变量名 | 值 | 用途 |
|--------|-----|------|
| `--gt-space-xs` | 4px | 紧凑间距 |
| `--gt-space-sm` | 8px | 元素内间距 |
| `--gt-space-md` | 12px | 卡片内边距 |
| `--gt-space-lg` | 16px | 区块间距 |
| `--gt-space-xl` | 24px | 页面边距 |

### 颜色变量（--gt-color-*）

| 变量名 | 值 | 用途 |
|--------|-----|------|
| `--gt-color-primary` | #4b2d77 | 品牌主色 |
| `--gt-color-primary-light` | #f0ecf7 | 浅紫背景 |
| `--gt-color-success` | #67C23A | 成功状态 |
| `--gt-color-warning` | #E6A23C | 警告状态 |
| `--gt-color-danger` | #F56C6C | 错误/危险 |
| `--gt-color-info` | #909399 | 信息/辅助 |
| `--gt-color-text-primary` | #303133 | 主文字 |
| `--gt-color-text-regular` | #606266 | 常规文字 |
| `--gt-color-text-secondary` | #909399 | 次要文字 |
| `--gt-color-border` | #DCDFE6 | 边框 |

## 审计发现

### 需替换的内联样式模式

| 模式 | 出现次数 | 替换为 |
|------|----------|--------|
| `style="font-size: 13px"` | ~15 处 | `var(--gt-font-size-base)` |
| `style="font-size: 12px"` | ~20 处 | `var(--gt-font-size-sm)` |
| `style="font-size: 11px"` | ~8 处 | `var(--gt-font-size-xs)` |
| `style="padding: 16px"` | ~10 处 | `var(--gt-space-lg)` |
| `style="margin-bottom: 8px"` | ~12 处 | `var(--gt-space-sm)` |
| `style="gap: 4px"` | ~6 处 | `var(--gt-space-xs)` |
| `color: #4b2d77` | ~5 处 | `var(--gt-color-primary)` |
| `color: #909399` | ~8 处 | `var(--gt-color-text-secondary)` |

### 合规视图（已使用 CSS 变量）

- TrialBalance.vue ✅
- ReportView.vue ✅
- WorkpaperEditor.vue ✅
- GtPageHeader.vue ✅
- GtAmountCell.vue ✅

### 待改进视图（含内联硬编码）

- NotificationCenter.vue — 多处 font-size/color 硬编码
- PersonalDashboard.vue — 间距硬编码
- ForumPage.vue — 字号硬编码
- CheckInsPage.vue — 颜色硬编码
- CollaborationIndex.vue — 间距硬编码

## 规范建议

1. **禁止新增内联 style 中的字号/间距/颜色硬编码**
2. 所有数值型样式应引用 CSS 变量
3. 组件 scoped style 中可使用变量
4. CI 可加 grep 卡点检测 `style=".*font-size:.*px"` 模式
