/**
 * API 服务层统一入口
 *
 * 所有 API 调用应通过此模块导入，不要在组件中直接使用 http.get/post
 *
 * 用法：
 *   import { auditApi, workpaperApi, staffApi } from '@/services'
 *   const data = await auditApi.getTrialBalance(projectId, year)
 */

export * as auditApi from './auditPlatformApi'
export * as workpaperApi from './workpaperApi'
export * as staffApi from './staffApi'
export * as consolidationApi from './consolidationApi'
export * as extensionApi from './extensionApi'
export * as phase10Api from './phase10Api'
export * as aiApi from './aiApi'
export * as aiModelApi from './aiModelApi'
export * as collaborationApi from './collaborationApi'
