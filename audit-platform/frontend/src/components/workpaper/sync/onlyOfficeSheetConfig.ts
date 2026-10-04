/**
 * OnlyOffice sheet 文档配置预拉 —— 与 `onlyOfficeHealth.ts` 同级的平台能力层。
 *
 * spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption` Task 6
 *
 * 「拉取成功才可切」：切到在线编辑前先确认该 sheet 的 OO 配置真能拿到，拿不到就留在
 * 结构化视图 —— 避免切过去才看到一块空白编辑器。原实现直接写在 `useN1DualMode.ts` 里
 * （N 域唯一一处 `onlyoffice-config` 直调），收敛到这里后任何循环平行 import，
 * 端点与信封解包口径只有这一份。
 *
 * 🔴 只做「可达性预检」，不缓存配置本身：真正渲染时 `GtOnlyOfficeSheet` 会自己拉最新配置
 *    （配置里含一次性 token，缓存旧值会让编辑器打不开）。
 */
import http from '@/utils/http'

/** 端点（唯一一处） */
export function onlyOfficeSheetConfigUrl(wpId: string, sheetName: string): string {
  return `/api/workpapers/${wpId}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`
}

/**
 * 预拉该 sheet 的 OO 配置；拿得到返回 true。
 *
 * `http`（utils/http）返回完整响应体 ⇒ 业务数据在 `res.data.data`（ResponseWrapperMiddleware
 * 信封），`res.data` 一层留给未包装形态。任何异常都视为「不可切」，不抛。
 */
export async function prefetchOnlyOfficeSheetConfig(wpId: string, sheetName: string): Promise<boolean> {
  if (!wpId || !sheetName) return false
  try {
    const res: any = await http.get(onlyOfficeSheetConfigUrl(wpId, sheetName), { _silent: true } as any)
    return !!(res?.data?.data ?? res?.data)
  } catch {
    return false
  }
}
