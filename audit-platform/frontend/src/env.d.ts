/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEV_PORT?: string
  readonly VITE_ONLYOFFICE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// ─── 候选验证实例（spec platform-global-display-settings-closure 13A / AC-25）───
// 由 `vite.config.ts` 的 `define` 只在候选模式注入；普通模式不注入，运行时必须容忍缺失
// （消费方用 `typeof x === 'undefined'` 判存，见 utils/candidateTreeMarker.ts）。
declare const __GT_CANDIDATE_TREE_EXPECTED__: string | undefined
declare const __GT_CANDIDATE_TREE_ACTUAL__: string | undefined

// ─── Route Meta 类型扩展 ───
// @see R7.1 路由守卫统一
import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 是否需要登录（默认由父路由 requireAuth 继承） */
    requireAuth?: boolean
    /** 路由级权限字符串，如 'admin' / 'project:edit'，不满足时跳转首页并提示 */
    permission?: string
    /** 路由级角色白名单（兼容旧路由，新路由应使用 permission） */
    roles?: string[]
    /** 标记为开发中页面，访问时提示并阻止导航 */
    developing?: boolean
    /**
     * 只改 query（`?year=` 除外）时复用页面实例、不重挂（见 utils/routeViewKey）。
     * 只给自己监听了会变 query 的页面开；默认按 fullPath 重挂。
     */
    reuseOnQueryChange?: boolean
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '*.md?raw' {
  const content: string
  export default content
}

declare module '*.md' {
  const content: string
  export default content
}

declare module '@univerjs/preset-sheets-core/lib/locales/zh-CN' {
  const locale: Record<string, any>
  export default locale
}
