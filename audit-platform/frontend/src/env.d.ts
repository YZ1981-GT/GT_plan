/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEV_PORT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// ─── Route Meta 类型扩展 ───
// @see R7.1 路由守卫统一
import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 是否需要登录（默认由父路由 requireAuth 继承） */
    requireAuth?: boolean
    /** 路由级权限字符串，如 'admin' / 'project:edit'，不满足时跳转首页并提示 */
    permission?: string
    /** 标记为开发中页面，访问时提示并阻止导航 */
    developing?: boolean
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '@univerjs/preset-sheets-core/lib/locales/zh-CN' {
  const locale: Record<string, any>
  export default locale
}
