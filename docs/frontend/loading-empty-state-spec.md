# 加载、空态与异步任务规范

> P1-3 产出物：统一首屏加载、空态预设、异步任务进度的使用规范。

## 1. 首屏 Skeleton 规范

### 1.1 适用场景

| 场景 | 方案 | 说明 |
|------|------|------|
| 页面首次加载（数据量大） | Skeleton + 渐显 | 试算表、报表等表格页 |
| 局部区域刷新 | `v-loading` 指令 | 表格内刷新、弹窗内加载 |
| 异步长任务 | `AsyncJobProgress` | 导入/导出/生成/归档 |
| 路由切换 | NProgress 顶部进度条 | 已全局配置 |

### 1.2 Skeleton 布局规则

```vue
<!-- 表格页面 skeleton 示例 -->
<template>
  <div v-if="loading" class="gt-skeleton-table">
    <div class="gt-skeleton-header">
      <div class="gt-skeleton-bar" style="width: 200px; height: 24px;" />
      <div class="gt-skeleton-bar" style="width: 300px; height: 32px;" />
    </div>
    <div class="gt-skeleton-rows">
      <div v-for="i in 8" :key="i" class="gt-skeleton-row">
        <div class="gt-skeleton-bar" style="width: 80px;" />
        <div class="gt-skeleton-bar" style="width: 160px;" />
        <div class="gt-skeleton-bar" style="width: 120px;" />
        <div class="gt-skeleton-bar" style="width: 120px;" />
      </div>
    </div>
  </div>
  <div v-else>
    <!-- 实际内容 -->
  </div>
</template>
```

### 1.3 Skeleton CSS 令牌

```css
.gt-skeleton-bar {
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(90deg,
    var(--gt-color-skeleton-base, #f0f0f0) 25%,
    var(--gt-color-skeleton-shine, #e0e0e0) 50%,
    var(--gt-color-skeleton-base, #f0f0f0) 75%
  );
  background-size: 200% 100%;
  animation: gt-skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes gt-skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### 1.4 使用原则

1. **首屏 > 1s 必须有视觉反馈**：skeleton 或 v-loading
2. **skeleton 不超过 3s**：超过 3s 仍未加载完成应显示错误提示
3. **skeleton 形状应匹配实际内容**：表格页用行形 skeleton，卡片页用块形
4. **避免 skeleton 闪烁**：加载 < 300ms 时不显示 skeleton（使用 `setTimeout` 延迟显示）

---

## 2. GtEmpty 四类预设

### 2.1 预设类型

| 预设 | 图标 | 标题 | 描述 | 操作按钮 |
|------|------|------|------|---------|
| `no-data` | 📭 | 暂无数据 | — | 刷新 |
| `no-permission` | 🔒 | 无权限访问 | 请联系项目经理或管理员 | — |
| `developing` | 🚧 | 功能开发中 | 该模块正在开发中，敬请期待 | — |
| `no-search-result` | 🔍 | 无匹配结果 | 请调整筛选条件后重试 | — |
| `load-failed` | ⚠️ | 加载失败 | 请检查网络后重试 | 重试 |

### 2.2 试点页面接入

| 页面 | 当前实现 | 改为 |
|------|---------|------|
| TrialBalance | `el-empty` | `<GtEmpty preset="no-data" @action="refetch" />` |
| ReportView | 条件渲染空白 | `<GtEmpty preset="no-data" @action="fetchReport" />` |
| DisclosureEditor | 条件渲染 el-empty | `<GtEmpty preset="no-data" />` |
| ConsolidationIndex | `GtEmpty developing` | ✅ 已对齐 |
| WorkpaperEditor | 无（始终有内容） | N/A |

### 2.3 使用规则

1. **数据为空**：`preset="no-data"` + `@action="reload"`
2. **无权限**：`preset="no-permission"`（由 router guard 或 API 403 触发）
3. **功能开发中**：`preset="developing"`（空壳页面统一使用）
4. **搜索无结果**：`preset="no-search-result"`
5. **加载失败**：`preset="load-failed"` + `@action="retry"`

---

## 3. AsyncJobProgress 使用规范

### 3.1 适用场景

| 操作 | 触发方式 | 预期时长 | 使用方案 |
|------|---------|---------|---------|
| 数据导入 | 用户上传文件 | 5-30s | AsyncJobProgress |
| Excel 导出 | 用户点击导出 | 3-15s | AsyncJobProgress |
| 报表生成 | 用户点击刷新 | 2-10s | AsyncJobProgress |
| 项目归档 | 用户确认归档 | 5-20s | AsyncJobProgress |
| AI 生成内容 | 用户发起 | 10-60s | AsyncJobProgress |

### 3.2 标准用法

```vue
<AsyncJobProgress
  v-if="jobVisible"
  :title="jobTitle"
  :percentage="jobPercent"
  :status="jobStatus"
  :message="jobMessage"
  :cancelable="true"
  :retryable="true"
  @cancel="onJobCancel"
  @retry="onJobRetry"
  @close="jobVisible = false"
/>
```

### 3.3 状态流转

```
pending → running → completed
                  → failed → (retry) → running
                  → cancelled
```

### 3.4 后端轮询约定

- 前端每 2s 轮询一次 `/api/jobs/{jobId}/status`
- 返回结构：`{ status, percentage, message, result? }`
- 完成后停止轮询，展示结果

---

## 4. UAT 检查清单

| # | 场景 | 预期表现 | 验证方法 |
|---|------|---------|---------|
| 1 | 断网后访问试算表 | `GtEmpty preset="load-failed"` + 重试按钮 | 断开网络 → 刷新 |
| 2 | 无权限访问报表 | `GtEmpty preset="no-permission"` | 用无权限账号访问 |
| 3 | 空项目进入试算表 | `GtEmpty preset="no-data"` + 刷新按钮 | 新建空项目 → 进入 |
| 4 | 空壳页面（工时等） | `GtEmpty preset="developing"` | 直接访问 |
| 5 | 导入文件进度 | AsyncJobProgress running → completed | 上传 Excel |
| 6 | 导出超时 | AsyncJobProgress running → failed + 重试 | mock 超时 |
