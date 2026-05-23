<!--
  DashboardViewSwitcher — 仪表盘多维视图切换器（共享组件）

  4 个视图按 effectiveRole 过滤可见：
    me      → '/'（Dashboard.vue 默认页）
    team    → '/dashboard/manager'
    project → '/dashboard/partner'
    eqcr    → '/eqcr/metrics'

  路由变化时自动同步 activeView，避免「点进去回不来」。

  用法：放在每个 dashboard 页面顶部 banner #actions slot 即可。
-->
<template>
  <div v-if="availableViews.length > 1" class="dashboard-view-switcher">
    <el-radio-group v-model="activeView" size="small" @change="onChange">
      <el-radio-button v-for="v in availableViews" :key="v.key" :value="v.key">
        {{ v.label }}
      </el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useRoleContextStore } from '@/stores/roleContext'

type ViewKey = 'me' | 'team' | 'project' | 'eqcr'

interface ViewDef {
  key: ViewKey
  label: string
  roles: string[]
  route: string
}

const ALL_VIEWS: ViewDef[] = [
  { key: 'me',      label: '我的视图',  roles: ['auditor', 'reviewer', 'manager', 'partner', 'eqcr', 'admin'], route: '/' },
  { key: 'team',    label: '团队视图',  roles: ['manager', 'partner', 'admin'],                                route: '/dashboard/manager' },
  { key: 'project', label: '项目视图',  roles: ['partner', 'admin'],                                           route: '/dashboard/partner' },
  { key: 'eqcr',    label: 'EQCR 视图', roles: ['eqcr', 'partner', 'admin'],                                   route: '/eqcr/metrics' },
]

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const roleStore = useRoleContextStore()

const availableViews = computed(() => {
  const role = roleStore.effectiveRole || authStore.user?.role || 'auditor'
  return ALL_VIEWS.filter(v => v.roles.includes(role))
})

// 当前路由 → activeView 推断
function deriveActive(path: string): ViewKey {
  if (path.startsWith('/dashboard/manager')) return 'team'
  if (path.startsWith('/dashboard/partner')) return 'project'
  if (path.startsWith('/eqcr/metrics')) return 'eqcr'
  return 'me'
}

const activeView = ref<ViewKey>(deriveActive(route.path))

// 路由变化时同步 activeView（防止跳转后 radio 状态不一致）
watch(
  () => route.path,
  (p) => { activeView.value = deriveActive(p) },
  { immediate: true },
)

function onChange(val: ViewKey) {
  const v = ALL_VIEWS.find(x => x.key === val)
  if (!v) return
  if (route.path === v.route) return
  router.push(v.route)
}
</script>

<style scoped>
.dashboard-view-switcher {
  margin-top: var(--gt-space-2);
  display: inline-flex;
}

/* 紫色 banner 上的视图切换：未选中 = 半透白底白字；选中 = 白底紫字（高 specificity 覆盖 element-plus 默认） */
.dashboard-view-switcher :deep(.el-radio-button .el-radio-button__inner) {
  background: rgba(255, 255, 255, 0.12);
  color: var(--gt-color-text-inverse);
  border-color: rgba(255, 255, 255, 0.32);
  box-shadow: none;
}
.dashboard-view-switcher :deep(.el-radio-button .el-radio-button__inner:hover) {
  color: var(--gt-color-text-inverse);
  background: rgba(255, 255, 255, 0.22);
}
.dashboard-view-switcher :deep(.el-radio-button.is-active .el-radio-button__inner),
.dashboard-view-switcher :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #ffffff !important;
  color: var(--gt-color-primary) !important;
  border-color: #ffffff !important;
  box-shadow: -1px 0 0 0 #ffffff !important;
}
</style>
