# 加载状态规范文档

> 日期：2026-05-12
> 对应需求：R9 F23

## 统一规范

| 场景 | 加载组件 | 说明 |
|------|----------|------|
| 表格数据加载 | `v-loading` | 覆盖表格区域，显示旋转图标 |
| 页面首屏加载 | `el-skeleton` | 骨架屏，模拟内容布局 |
| 弹窗内容加载 | `v-loading` | 覆盖弹窗 body 区域 |
| 按钮操作中 | `:loading="true"` | 按钮自带 loading 状态 |
| 全局路由切换 | NProgress | 顶部进度条 |

## 规范细则

### 表格加载（v-loading）

```vue
<el-table :data="tableData" v-loading="loading" style="width: 100%">
  ...
</el-table>
```

- 适用：所有 el-table 数据加载
- 触发：API 请求开始时 `loading = true`，结束时 `loading = false`
- 样式：默认 Element Plus 遮罩 + 旋转图标

### 页面首屏（el-skeleton）

```vue
<template v-if="pageLoading">
  <el-skeleton :rows="5" animated />
</template>
<template v-else>
  <!-- 实际内容 -->
</template>
```

- 适用：Dashboard、详情页等首次加载
- 触发：页面 onMounted 数据加载完成前
- 行数：根据实际内容布局设置 rows

### 弹窗加载（v-loading）

```vue
<el-dialog v-model="dialogVisible">
  <div v-loading="dialogLoading">
    <!-- 弹窗内容 -->
  </div>
</el-dialog>
```

### 按钮操作

```vue
<el-button :loading="submitting" @click="onSubmit">提交</el-button>
```

## 审计发现

### 当前使用统计

| 模式 | 使用次数 | 合规 |
|------|----------|------|
| `v-loading` 在表格 | ~35 处 | ✅ |
| `el-skeleton` 在页面 | ~4 处 | ⚠️ 偏少 |
| `v-loading` 在弹窗 | ~8 处 | ✅ |
| 自定义 loading 组件 | ~3 处 | ❌ 应统一 |

### 需改进的视图

| 视图 | 当前模式 | 应改为 |
|------|----------|--------|
| PersonalDashboard.vue | 无加载态 | el-skeleton |
| ManagerDashboard.vue | v-loading 全页 | el-skeleton |
| ProjectDashboard.vue | 无加载态 | el-skeleton |
| PartnerDashboard.vue | 无加载态 | el-skeleton |
| QCDashboard.vue | 无加载态 | el-skeleton |

## 禁止模式

1. ❌ 自定义 `<div class="loading-spinner">` — 使用 v-loading
2. ❌ 表格用 el-skeleton — 表格统一用 v-loading
3. ❌ 页面首屏用 v-loading 全覆盖 — 用 el-skeleton 更友好
4. ❌ 无加载态直接显示空白 — 必须有加载反馈
