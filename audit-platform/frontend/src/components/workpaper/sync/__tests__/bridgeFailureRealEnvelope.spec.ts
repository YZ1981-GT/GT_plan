/**
 * sync 失败必须按**平台真实响应信封**认出业务码 —— 而不是按 FastAPI 原生 `detail` 形状。
 *
 * ═══ 真实缺陷（e2e 抓到的原始响应体）═══
 *
 * 平台注册了全局 HTTPException 处理器（`backend/app/middleware/error_handler.py`）：
 *
 * ```python
 * return JSONResponse(status_code=exc.status_code,
 *                     content={"code": exc.status_code, "message": exc.detail})
 * ```
 *
 * ⇒ router 用 `HTTPException(detail={"error_code":…, "message":…})` 抛出的 domain error，
 * 到了前端是 **`data.message`** 里的对象，**没有 `data.detail` 键**。真栈实测原文：
 *
 * ```
 * {"code":500,"message":{"error_code":"excel_extract_identity_carrier_missing",
 *                        "message":"entry xlsx/gt-d4-operating-revenue: …"}}
 * ```
 *
 * 而 `readWireError` 只从 `response.data.detail` 取码 ⇒ `errorCode` 恒为空 ⇒ 所有 sync
 * domain error 都落第三桶（`WP_BRIDGE_LOCAL_FAILURE_CODE` + `unregistered: true`），于是：
 *
 * * `classifySyncFailure` 的全部分派（stale identity 三门 / 可重试 / 409·422·403 区分）
 *   **在生产上从未生效**；
 * * 后端写的中文根因**整段丢失**，用户只看到 axios 的 `Request failed with status code 500`；
 * * 500 被判「可重试」⇒ 对这类确定性失败无意义地重试 3 次（真栈实测 materialize 500 ×3）。
 *
 * 🔴 **既有 22+ 条 bridge 判据全绿**，因为它们一律 mock 成 `data: { detail: {…} }` ——
 * 一个生产上不存在的形状。这是本仓库反复登记的「假绿第①源」：判据喂了自己造的形状。
 * 本文件按**真实信封**喂，修复前必红。
 */
import { describe, it, expect } from 'vitest'
import {
  describeBridgeFailure,
  WP_BRIDGE_LOCAL_FAILURE_CODE,
  WP_BRIDGE_NON_DISCLOSURE_CODE,
} from '../useWorkpaperSyncBridge'

/** 平台真实信封：全局 handler 把 `exc.detail` 放进 `message`，无 `detail` 键。 */
function realEnvelope(status: number, detail: unknown) {
  return { response: { status, data: { code: status, message: detail } } }
}

/** FastAPI 原生形状（绕过全局 handler 的场景 / 既有判据用的形状）。 */
function nativeEnvelope(status: number, detail: unknown) {
  return { response: { status, data: { detail } } }
}

const DOMAIN_ERROR = {
  error_code: 'excel_extract_identity_carrier_missing',
  message: 'entry xlsx/gt-d4-operating-revenue: 受管区 sheet=\'营业收入审定表D4-1\' …',
}

describe('平台真实信封（data.message）里的 domain error 必须被认出来', () => {
  it('500 + message 里带 error_code ⇒ 认出业务码，不落「本地/传输」桶', () => {
    const described = describeBridgeFailure('materialize', realEnvelope(500, DOMAIN_ERROR))
    expect(
      described.errorCode,
      '认不出业务码 ⇒ 落 WP_BRIDGE_LOCAL_FAILURE_CODE ⇒ classifySyncFailure 全部分派失效',
    ).toBe(DOMAIN_ERROR.error_code)
    expect(described.errorCode).not.toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
  })

  it('后端的中文根因必须保留（不得被 axios 的英文 message 顶掉）', () => {
    const described = describeBridgeFailure('materialize', {
      ...realEnvelope(500, DOMAIN_ERROR),
      message: 'Request failed with status code 500',
    })
    expect(described.message).toBe(DOMAIN_ERROR.message)
    expect(described.message).not.toContain('Request failed with status code')
  })

  it('409 stale identity 在真实信封下也要被认出（否则编辑器会被错误放行）', () => {
    const described = describeBridgeFailure(
      'materialize',
      realEnvelope(409, { error_code: 'launch_descriptor_stale_identity', message: '陈旧' }),
    )
    expect(described.errorCode).toBe('launch_descriptor_stale_identity')
    expect(described.staleIdentity, 'staleIdentity 未置位 ⇒ 三门放行，编辑器会打开').toBe(true)
  })

  it('403 workflow_locked 在真实信封下保留业务码（不塌成「不可区分」）', () => {
    const described = describeBridgeFailure(
      'forcesave',
      realEnvelope(403, { error_code: 'workflow_locked', message: '流程已锁定' }),
    )
    expect(described.errorCode).toBe('workflow_locked')
    expect(described.errorCode).not.toBe(WP_BRIDGE_NON_DISCLOSURE_CODE)
  })

  it('真实信封的纯字符串 message（统一 404/403）仍按脱敏桶处理，不当 error_code', () => {
    const described = describeBridgeFailure('probe', realEnvelope(404, '资源不存在或不可访问'))
    expect(described.errorCode).toBe(WP_BRIDGE_NON_DISCLOSURE_CODE)
  })

  it('真实信封下 5xx 纯字符串仍是本地/传输桶（不凭空造码）', () => {
    const described = describeBridgeFailure('probe', realEnvelope(500, '内部错误'))
    expect(described.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
    expect(described.message).toBe('内部错误')
  })
})

describe('FastAPI 原生 detail 形状必须继续工作（零回归）', () => {
  it('detail 里带 error_code ⇒ 照旧认出', () => {
    const described = describeBridgeFailure('materialize', nativeEnvelope(409, DOMAIN_ERROR))
    expect(described.errorCode).toBe(DOMAIN_ERROR.error_code)
    expect(described.message).toBe(DOMAIN_ERROR.message)
  })

  it('detail 与 message 同时存在时 detail 优先（它更贴近 FastAPI 语义）', () => {
    const described = describeBridgeFailure('materialize', {
      response: {
        status: 409,
        data: {
          detail: { error_code: 'from_detail', message: '来自 detail' },
          message: { error_code: 'from_message', message: '来自 message' },
        },
      },
    })
    expect(described.errorCode).toBe('from_detail')
    expect(described.message).toBe('来自 detail')
  })

  it('两者都没有 ⇒ 仍落本地/传输桶（不因新增分支而误判）', () => {
    const described = describeBridgeFailure('probe', { response: { status: 500, data: {} } })
    expect(described.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
  })
})
