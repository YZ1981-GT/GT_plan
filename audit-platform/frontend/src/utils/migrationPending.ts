/**
 * 后端 503 `MIGRATION_PENDING`：数据库结构比程序旧（迁移未执行），spec voucher-workflow-linkage-lineage-closure R2。
 *
 * 后端统一异常处理在「表 / 列不存在」且确有未执行迁移时回这个错误，说明里写了两边版本与个数。
 * 这类错误重试没有用，提示也要用后端的说明（通用的「服务暂时不可用」看不出原因）。
 * 信封里业务详情在 `message`，http 拦截器会补成 `detail`，两处都认。
 */
export function migrationPendingMessage(err: unknown): string | null {
  const res = (err as { response?: { status?: number; data?: Record<string, unknown> } } | null)?.response
  if (res?.status !== 503) return null
  const body = (res.data?.detail ?? res.data?.message) as Record<string, unknown> | undefined
  if (!body || typeof body !== 'object' || body.error_code !== 'MIGRATION_PENDING') return null
  return typeof body.message === 'string' && body.message ? body.message : '数据库结构未升级，请联系管理员'
}
