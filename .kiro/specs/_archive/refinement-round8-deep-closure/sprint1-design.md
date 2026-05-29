# Sprint 1（P0）设计文档

## D1：/confirmation 路由修复

### 文件变更

| 文件 | 操作 |
|------|------|
| `views/ConfirmationHub.vue` | 新建（stub） |
| `router/index.ts` | 添加路由 |
| `layouts/ThreeColumnLayout.vue` | 无需改（侧栏已有 confirmation 条目） |

### ConfirmationHub.vue

```vue
<template>
  <div class="gt-confirmation-hub gt-fade-in">
    <GtPageHeader title="函证管理" :show-back="false" />
    <GtEmpty icon="📮" title="函证管理" description="该模块正在开发中，敬请期待" />
  </div>
</template>

<script setup lang="ts">
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtEmpty from '@/components/common/GtEmpty.vue'
</script>
```

### router 添加

```ts
{
  path: '/confirmation',
  name: 'ConfirmationHub',
  component: () => import('@/views/ConfirmationHub.vue'),
  meta: { requireAuth: true, developing: true },
}
```

router beforeEach 已有 `meta.developing` 守卫逻辑，会自动跳转 DevelopingPage。

---

## D2：confirm.ts 补齐 + 全局替换

### 新增函数签名

```ts
// utils/confirm.ts 新增

/** 版本冲突：刷新 / 强制覆盖 / 取消 */
export async function confirmVersionConflict(
  serverVersion: number,
  localVersion: number
): Promise<'refresh' | 'override' | 'cancel'>

/** 签字确认：必须输入客户名 */
export async function confirmSignature(
  clientName: string,
  reportType: string
): Promise<boolean>

/** 强制重置（导入锁等） */
export async function confirmForceReset(context: string): Promise<boolean>

/** 回滚版本 */
export async function confirmRollback(version: number): Promise<boolean>

/** 分享给项目组 */
export async function confirmShare(target: string, audience: string): Promise<boolean>

/** 重复数据处理 */
export async function confirmDuplicateAction(message: string): Promise<'overwrite' | 'skip' | 'cancel'>

/** 强制通过（复核有未解决意见时） */
export async function confirmForcePass(reason: string): Promise<{ confirmed: boolean; note: string }>
```

### 替换策略

按文件分类替换：

| 类别 | 文件 | 替换为 |
|------|------|--------|
| 合并工作表删除 | 8 个 *Sheet.vue | `confirmBatch('删除', count)` |
| 导入冲突 | AccountImportStep / DataImportPanel | `confirmForceReset` / `confirmDuplicateAction` |
| 项目删除 | MiddleProjectList / DetailProjectPanel | `confirmDelete` / `confirmForceReset` |
| EQCR 笔记 | EqcrReviewNotesPanel / EqcrRelatedParties | `confirmDelete` / `confirmShare` |
| 底稿版本冲突 | WorkpaperEditor | `confirmVersionConflict` |
| 底稿复核 | WorkpaperList | `confirmForcePass` |
| 独立性声明 | IndependenceDeclarationForm | `confirmSignature`（语义接近） |
| 公式回滚 | StructureEditor | `confirmRollback` |
| 还原默认 | NetAssetSheet / EquitySimSheet / CapitalReserveSheet | `confirmDangerous('还原默认行结构', ...)` |
| 合并汇总 | ConsolNoteTab | `confirmBatch('汇总', ...)` |

### CI 卡点

`.github/workflows/ci.yml` frontend-build job 新增步骤：

```yaml
- name: Check ElMessageBox.confirm usage
  run: |
    count=$(grep -r "ElMessageBox\.confirm" audit-platform/frontend/src --include="*.vue" -l | wc -l)
    echo "ElMessageBox.confirm direct usage: $count files"
    if [ "$count" -gt 5 ]; then
      echo "::error::ElMessageBox.confirm direct usage exceeds baseline (5). Found: $count"
      exit 1
    fi
```

---

## D3：Adjustments "转错报"按钮

### 前端改动

文件：`views/Adjustments.vue`

在行操作区（el-table-column label="操作"）对 `row.review_status === 'rejected'` 的行增加按钮：

```vue
<el-button
  v-if="row.review_status === 'rejected'"
  v-permission="'adjustment:convert_to_misstatement'"
  size="small"
  type="warning"
  @click="onConvertToMisstatement(row)"
>
  转为错报
</el-button>
```

### 处理函数

```ts
async function onConvertToMisstatement(row: AdjustmentRow) {
  try {
    const res = await api.post(
      apiPaths.adjustments.convertToMisstatement(projectId.value, row.id)
    )
    feedback.success(`已转为错报（净额 ${displayPrefs.fmt(res.net_amount)}）`)
    // 跳转确认（非批量操作，用简单 confirm）
    try {
      await confirmDangerous('查看未更正错报表', '跳转后当前页面数据将刷新')
      router.push({ name: 'Misstatements', params: { projectId: projectId.value }, query: { year: String(year.value) } })
    } catch { await loadAdjustments() }
  } catch (e: any) {
    const parsed = e?.response?.data?.detail || e?.response?.data
    if (parsed?.code === 'ALREADY_CONVERTED') {
      try {
        await confirmDangerous('跳转查看', '该分录已转为未更正错报')
        router.push({ name: 'Misstatements', params: { projectId: projectId.value }, query: { year: String(year.value) } })
      } catch { /* 用户取消 */ }
    } else {
      handleApiError(e, '转为错报')
    }
  }
}
```

### apiPaths 补充

```ts
// services/apiPaths.ts adjustments 对象新增
convertToMisstatement: (pid: string, adjId: string) =>
  `/api/projects/${pid}/adjustments/${adjId}/convert-to-misstatement`,
```

### 权限补充

`composables/usePermission.ts` ROLE_PERMISSIONS：
- auditor 增加 `'adjustment:convert_to_misstatement'`
- manager/partner/admin 同样增加

---

## D4：全局年度上下文 store

### 新建 stores/projectYear.ts

```ts
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { eventBus } from '@/utils/eventBus'

export const useProjectYearStore = defineStore('projectYear', () => {
  const currentProjectId = ref('')
  const currentYear = ref(new Date().getFullYear() - 1)

  function setProject(pid: string) {
    currentProjectId.value = pid
  }

  function setYear(y: number) {
    const prev = currentYear.value
    currentYear.value = y
    if (prev !== y) {
      eventBus.emit('year:changed', { projectId: currentProjectId.value, year: y })
    }
  }

  return { currentProjectId, currentYear, setProject, setYear }
})
```

### GtInfoBar 绑定

`components/common/GtInfoBar.vue` 的年度 select `@change` 改为调 `projectYearStore.setYear(val)`。

### 视图接入

TrialBalance / ReportView / DisclosureEditor / Materiality / Adjustments / Misstatements：
- `const year = computed(() => projectYearStore.currentYear)`
- 删除各自的 `year = Number(route.query.year) || ...` 本地计算
- `onMounted` 时从 `route.query.year` 初始化 store（如果 store 未设置）

### router guard 注入

```ts
router.afterEach((to) => {
  const store = useProjectYearStore()
  if (store.currentYear && !to.query.year) {
    // 静默追加 year query（不触发导航）
    router.replace({ ...to, query: { ...to.query, year: String(store.currentYear) } })
  }
})
```

---

## D5：http interceptor 5xx/超时/断网

### utils/feedback.ts（新建）

```ts
import { ElMessage, ElNotification } from 'element-plus'

export const feedback = {
  success: (msg: string) => ElMessage.success(msg),
  info: (msg: string) => ElMessage.info(msg),
  warning: (msg: string) => ElMessage.warning(msg),
  error: (msg: string, detail?: string) => {
    ElMessage.error({ message: msg, duration: 4000, showClose: true })
    if (detail) console.warn('[feedback.error]', detail)
  },
  notify: (opts: {
    title: string; message: string;
    type?: 'success' | 'warning' | 'info' | 'error';
    duration?: number; onClick?: () => void
  }) => ElNotification({ duration: 5000, ...opts }),
}
```

### utils/http.ts interceptor 改动

```ts
// response error interceptor 新增
if (error.response?.status >= 500) {
  const errorId = error.response?.headers?.['x-request-id'] || Date.now().toString(36)
  feedback.notify({
    type: 'error',
    title: '服务器错误',
    message: `系统暂时无法响应，请稍后重试。(${errorId})`,
    duration: 8000,
  })
}

if (error.code === 'ECONNABORTED') {
  feedback.notify({
    type: 'warning',
    title: '请求超时',
    message: '网络连接缓慢，已停止等待。建议检查网络或稍后重试。',
  })
}

if (!navigator.onLine) {
  feedback.notify({
    type: 'warning',
    title: '网络已断开',
    message: '当前离线，部分操作可能无法完成。',
  })
}
```

---

## D6：AI mask_context 全路径审计

### 需要检查的文件

| 文件 | 预期 |
|------|------|
| `services/wp_chat_service.py` | ✅ 已集成 mask_context |
| `routers/wp_ai.py` | 需确认 |
| `routers/note_ai.py` | 需确认 |
| `routers/ai_unified.py` | 需确认 |
| `routers/role_ai_features.py` | 需确认 |

### 修复模式

每个 AI 端点在构建 prompt 前：

```python
from app.services.export_mask_service import ExportMaskService

mask_svc = ExportMaskService()
masked_context = mask_svc.mask_context(raw_context)
# 用 masked_context 构建 prompt
```

### 测试

新建 `backend/tests/test_ai_masking.py`：
- 构造含客户名/金额的 context
- 调用各 AI service 函数
- 断言 prompt 中不含原始客户名/金额
