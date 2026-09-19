import type { RouteRecordRaw } from 'vue-router'

/**
 * Router domain: standalone top-level routes (outside DefaultLayout)
 */
export const standaloneRoutes: RouteRecordRaw[] = [
  {
    // AI 审计助手独立窗口（DshPanel 头部「在新窗口打开」的目标）
    // 顶层路由而非 DefaultLayout 子路由：1200x800 弹窗里主布局侧栏/顶栏只会挤占对话区。
    // 宿主上下文经 query 传入（project_id / wp_id），由 AIChatView 用
    // buildAmbientHost 自行推导，无参数时为显式全局知识模式。
    path: '/ai-chat',
    name: 'AIChatWindow',
    component: () => import('@/views/ai/AIChatView.vue'),
    meta: { requireAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
  },
  {
    path: '/developing',
    name: 'DevelopingPage',
    component: () => import('@/views/DevelopingPage.vue'),
  },
]
