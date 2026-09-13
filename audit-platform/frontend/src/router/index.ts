import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { ROLE_PERMISSIONS } from '@/composables/usePermission'

import { authRoutes } from './domains/auth'
import { dashboardRoutes } from './domains/dashboard'
import { projectsRoutes } from './domains/projects'
import { workpapersRoutes } from './domains/workpapers'
import { reportsRoutes } from './domains/reports'
import { notesRoutes } from './domains/notes'
import { confirmationsRoutes } from './domains/confirmations'
import { qcRoutes } from './domains/qc'
import { extensionRoutes } from './domains/extension'
import { systemRoutes } from './domains/system'
import { standaloneRoutes } from './domains/standalone'

// NProgress 配置：不显示旋转图标，与 GT 紫色主题一致
NProgress.configure({ showSpinner: false })

// ─── 路由装配：domains/*.ts 为唯一真源 ───
// 每个域文件显式导出一个 RouteRecordRaw[]，本文件只做装配，不再内联路由块。
// routeDomainProjection.spec.ts 断言：每个域导出在 layoutChildren /
// top-level routes 中各展开恰好一次，域内 path 全部进入声明集合，跨域 name 不重复。

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...authRoutes,
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      meta: { requireAuth: true },
      children: [
        ...dashboardRoutes,     // 首页与仪表盘
        ...projectsRoutes,      // 项目与项目内工作台
        ...workpapersRoutes,    // 底稿
        ...reportsRoutes,       // 报表
        ...notesRoutes,         // 附注
        ...confirmationsRoutes, // 函证
        ...qcRoutes,            // 质量复核
        ...extensionRoutes,     // 扩展与模板
        ...systemRoutes,        // 系统管理与运维
      ],
    },
    ...standaloneRoutes,
  ],
})

// ─── 统一路由守卫 [R7.1] ───
// 职责：① 开发中页面拦截 ② 认证守卫 ③ 权限守卫 ④ 项目上下文自动加载
// 注意：未保存变更拦截由 useEditMode 的 onBeforeRouteLeave 在组件级处理，
//       router 级 beforeEach 不重复拦截，也不会干扰组件级守卫。
router.beforeEach(async (to) => {
  NProgress.start()
  const authStore = useAuthStore()

  // ① 开发中页面 → 跳转到专门的"开发中"页面
  if (to.meta.developing) {
    NProgress.done()
    return { name: 'DevelopingPage' }
  }

  // ② 已登录用户访问 /login → 重定向到首页
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }

  // ③ 认证守卫：需要登录但未认证 → 重定向到登录页
  if (to.matched.some((r) => r.meta.requireAuth) && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // ④ 权限守卫：检查路由级 meta.permission
  // 修复 P1.2：不再调用 usePermission()（在 beforeEach 里调用会创建游离 computed）
  // 改为直接访问 authStore.user?.role，使用 ROLE_PERMISSIONS 常量做权限判断
  const permissionRequired = to.meta.permission
  if (permissionRequired && authStore.isAuthenticated) {
    const role = authStore.user?.role ?? ''
    const hasPermission =
      role === 'admin' ||
      (role !== '' &&
        permissionRequired !== 'admin' &&
        (ROLE_PERMISSIONS[role]?.includes(permissionRequired as string) ?? false))
    if (!hasPermission) {
      import('element-plus').then(({ ElMessage }) => {
        ElMessage.warning('您没有访问该页面的权限')
      })
      NProgress.done()
      return { path: '/' }
    }
  }

  // ④b 角色守卫：检查路由级 meta.roles（R-1 安全加固）
  const allowedRoles = to.meta.roles as string[] | undefined
  if (allowedRoles && authStore.isAuthenticated && !to.matched.some((r) => r.meta.requiresAnnualDeclaration)) {
    const role = authStore.user?.role ?? ''
    if (!allowedRoles.includes(role)) {
      import('element-plus').then(({ ElMessage }) => {
        ElMessage.warning('您没有访问该页面的权限')
      })
      NProgress.done()
      return { path: '/' }
    }
  }

    // ⑤ EQCR 路由：角色粗筛 + 年度独立性声明阻断（R5 需求 12）
  if (to.matched.some((r) => r.meta.requiresAnnualDeclaration)) {
    // 5a 角色粗筛（仅 EqcrMetrics 有 roles 限制；EqcrWorkbench/ProjectView 不限角色，非 EQCR 用户看空态）
    const allowedRoles = to.meta.roles as string[] | undefined
    if (allowedRoles && !allowedRoles.includes(authStore.user?.role ?? '')) {
      import('element-plus').then(({ ElMessage }) => {
        ElMessage.warning('您没有访问该页面的权限')
      })
      NProgress.done()
      return { path: '/' }
    }

    // 5b 年度独立性声明阻断
    try {
      const http = (await import('@/utils/http')).default
      const resp = await http.get('/api/eqcr/independence/annual/check', {
        validateStatus: (s: number) => s < 600,
      })
      if (resp?.data && resp.data.has_declaration === false) {
        // 未提交：重定向到工作台（工作台会弹出声明对话框并阻止加载数据）
        if (to.name !== 'EqcrWorkbench') {
          NProgress.done()
          return { name: 'EqcrWorkbench' }
        }
      }
    } catch {
      // 端点异常时放行到工作台（工作台内二次检查会阻断数据加载）
      if (to.name !== 'EqcrWorkbench') {
        NProgress.done()
        return { name: 'EqcrWorkbench' }
      }
    }
  }

    // ⑥ 项目上下文自动加载：路由含 :projectId 时同步到 projectStore
  //    DefaultLayout 的 watch 仍保留作为备份，此处提前触发确保数据就绪
  if (to.params.projectId && authStore.isAuthenticated) {
    const projectStore = useProjectStore()
    // 非阻塞：先渲染页面，数据异步更新，避免路由切换等待 API
    projectStore.syncFromRoute(to as any)
  }
})

// ─── afterEach：结束进度条 ───
router.afterEach(() => {
  NProgress.done()
})

export default router
