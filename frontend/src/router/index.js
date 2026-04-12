/**
 * 前端路由配置
 * 包含 AI 功能页面路由
 */

import { createRouter, createWebHistory } from 'vue-router'

// AI 页面组件（延迟导入）
const AIChatView = () => import('@/views/ai/AIChatView.vue')
const AIDocumentView = () => import('@/views/ai/AIDocumentView.vue')
const AIModelView = () => import('@/views/ai/AIModelView.vue')
const AIContractView = () => import('@/views/ai/AIContractView.vue')
const AIEvidenceView = () => import('@/views/ai/AIEvidenceView.vue')
const AIWorkpaperView = () => import('@/views/ai/AIWorkpaperView.vue')

const routes = [
  {
    path: '/ai/chat',
    name: 'AIChat',
    component: AIChatView,
    meta: { title: 'AI 问答', requiresAuth: true },
  },
  {
    path: '/ai/document',
    name: 'AIDocument',
    component: AIDocumentView,
    meta: { title: '文档识别', requiresAuth: true },
  },
  {
    path: '/ai/models',
    name: 'AIModels',
    component: AIModelView,
    meta: { title: 'AI 模型管理', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/ai/contract',
    name: 'AIContract',
    component: AIContractView,
    meta: { title: '合同分析', requiresAuth: true },
  },
  {
    path: '/ai/evidence',
    name: 'AIEvidence',
    component: AIEvidenceView,
    meta: { title: '证据链分析', requiresAuth: true },
  },
  {
    path: '/ai/workpaper',
    name: 'AIWorkpaper',
    component: AIWorkpaperView,
    meta: { title: '底稿 AI 填充', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 更新页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 审计作业平台`
  }

  // 检查登录状态
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  next()
})

export default router
