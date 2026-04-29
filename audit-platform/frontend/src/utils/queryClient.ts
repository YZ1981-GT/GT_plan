/**
 * Vue Query 全局配置
 *
 * 统一管理服务端状态（缓存/重试/乐观更新），
 * Pinia 只管客户端 UI 状态（表单草稿/折叠状态等）。
 *
 * 用法：在 main.ts 中注册 VueQueryPlugin
 */

import { QueryClient } from '@tanstack/vue-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 窗口重新聚焦时不自动重新请求（审计场景数据变化不频繁）
      refetchOnWindowFocus: false,
      // 默认缓存 5 分钟
      staleTime: 5 * 60 * 1000,
      // 失败重试 1 次
      retry: 1,
      // 重试延迟
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    },
    mutations: {
      // mutation 失败不自动重试
      retry: false,
    },
  },
})
