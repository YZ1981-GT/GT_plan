# Sprint 1（P0）设计文档

## D1：apiPaths 新增路径

```ts
// services/apiPaths.ts 新增
export const my = {
  pendingIndependence: '/api/my/pending-independence',
  reminders: '/api/my/reminders',
  unreadAnnotations: '/api/my/unread-annotations/count',
} as const

// qcDashboard 对象追加
export const qcDashboard = {
  // ... 已有
  reviewerMetrics: '/api/qc/reviewer-metrics',
} as const
```

## D2：登录角色跳转

修改文件：`stores/auth.ts`

```ts
// login() 方法末尾，token 写入后
const ROLE_HOME: Record<string, string> = {
  auditor: '/my/dashboard',
  manager: '/dashboard/manager',
  partner: '/dashboard/partner',
  qc: '/qc/inspections',
  eqcr: '/eqcr/workbench',
  admin: '/',
}
const redirect = router.currentRoute.value.query.redirect as string | undefined
const target = redirect || ROLE_HOME[user.role] || '/'
router.replace(target)
```

## D3：isEqcrEligible 修改

文件：`layouts/DefaultLayout.vue:131-134`

```ts
const isEqcrEligible = computed(() => {
  const role = roleStore.effectiveRole
  return ['partner', 'admin', 'eqcr'].includes(role) || roleStore.isPartner
})
```

文件：`router/index.ts:465`
```ts
meta: { requiresAnnualDeclaration: true, roles: ['admin', 'partner', 'eqcr'] },
```

## D4：/confirmation 路由

文件：`router/index.ts`，在 QC 路由块后追加：

```ts
{
  path: 'confirmation',
  name: 'ConfirmationHub',
  component: () => import('@/views/DevelopingPage.vue'),
  meta: { developing: true },
},
```

## D5：confirm.ts 新增函数

文件：`utils/confirm.ts`

```ts
export async function confirmSubmitReview(wpCode: string, wpName: string) {
  return ElMessageBox.confirm(
    `提交后底稿 ${wpCode}「${wpName}」将进入复核流程，复核通过前您将无法编辑。确认提交？`,
    '提交复核',
    { confirmButtonText: '确认提交', cancelButtonText: '取消', type: 'info' }
  )
}

export async function confirmVersionConflict(serverVer: number, localVer: number) {
  return ElMessageBox.confirm(
    `底稿已被他人修改（服务器版本 v${serverVer}，您的版本 v${localVer}）。刷新将放弃本地修改。`,
    '版本冲突',
    { confirmButtonText: '刷新', cancelButtonText: '取消', type: 'warning', distinguishCancelAndClose: true }
  )
}

export async function confirmLeave(moduleLabel: string) {
  return ElMessageBox.confirm(
    `当前${moduleLabel}有未保存的变更，离开将丢失这些变更。`,
    '确认离开',
    { confirmButtonText: '离开', cancelButtonText: '留下', type: 'warning' }
  )
}

export async function confirmConvert(fromLabel: string, toLabel: string) {
  return ElMessageBox.confirm(
    `将${fromLabel}转为${toLabel}？转换后将出现在对应汇总表中。`,
    '确认转换',
    { confirmButtonText: '确认转换', cancelButtonText: '取消', type: 'info' }
  )
}

export async function confirmEscalate(targetRole: string) {
  return ElMessageBox.confirm(
    `确认将此事项升级通知${targetRole}？`,
    '升级确认',
    { confirmButtonText: '确认升级', cancelButtonText: '取消', type: 'warning' }
  )
}
```

## D6：GtEmpty.vue

文件：`components/common/GtEmpty.vue`

```vue
<template>
  <div class="gt-empty">
    <el-empty :image-size="80">
      <template #image v-if="icon">
        <span style="font-size: 48px">{{ icon }}</span>
      </template>
      <template #description>
        <h4 class="gt-empty__title">{{ title }}</h4>
        <p class="gt-empty__desc">{{ description }}</p>
      </template>
      <el-button v-if="actionText" type="primary" @click="$emit('action')">
        {{ actionText }}
      </el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  actionText?: string
  icon?: string
}>()
defineEmits<{ (e: 'action'): void }>()
</script>
```
