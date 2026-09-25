/**
 * 后端错误信封适配判据 —— 守住「下游读得到后端真实错误详情」这条线。
 *
 * ## 被修复的缺陷（真栈实测 2026-09-23，后端 9980）
 *
 * ```
 * GET /api/projects/00000000-0000-0000-0000-000000000000
 *   => 404 {"code":404,"message":"项目不存在"}          ← 业务 HTTPException，无 detail
 * GET /api/projects/{id}/workpapers/{id}/render-config
 *   => 404 {"detail":"Not Found"}                        ← starlette 原生，有 detail
 * ```
 *
 * `backend/app/main.py:654` 注册的是 `fastapi.HTTPException` → 平台全局
 * `http_exception_handler`，它把 `exc.detail` 放进 **`message`** 字段而不输出 `detail`
 * （`{code, message}` 是平台统一信封，见 `backend/app/middleware/error_handler.py`）。
 *
 * 而前端下游普遍只读 `detail`：
 * - `utils/errorHandler.ts::handleApiError`（平台统一错误处理器，全仓大量视图在用）
 * - 几十个视图里的 `e?.response?.data?.detail`
 * - `components/workpaper/sync/useWorkpaperSyncBridge.ts::readWireError`
 *
 * 于是生产上对**所有业务 HTTPException** 恒取不到值，后果全是静默降级：
 * - 400/409/503 的后端中文根因退化成「请求参数错误」这类兜底文案；
 * - 422 的 `AI_CONTENT_NOT_CONFIRMED` / `CROSS_MODULE_CONFLICT_UNRESOLVED` 特化分派从未生效；
 * - sync 桥 `classifySyncFailure` 的 error_code 分派从未生效，domain error 被当可重试而重试 3 次。
 *
 * 注意 `http.ts` 内部的 `extractErrorDetail` 早就写对了（`detail ?? message`），所以拦截器
 * 自己弹的全局 toast 一直是好的 —— 这恰好说明该知识在全仓被重复实现了 N 次而只有 1 处正确。
 * 修法是把它收敛到拦截器一处 normalize，而不是逐个调用点打补丁。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const elMessageError = vi.fn()
const elMessageWarning = vi.fn()
const elNotification = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...a: unknown[]) => elMessageError(...a),
    warning: (...a: unknown[]) => elMessageWarning(...a),
    success: vi.fn(),
    info: vi.fn(),
  },
  ElNotification: (...a: unknown[]) => elNotification(...a),
}))

import http, { normaliseErrorEnvelope } from '../http'
import { handleApiError } from '../errorHandler'

/** 业务 HTTPException 的真实生产形状：detail 被放进 message，没有 detail 键。 */
function wireHttpException(status: number, detail: unknown): { data: unknown } {
  return { data: { code: status, message: detail } }
}

describe('normaliseErrorEnvelope — 按后端真实形状回填 detail', () => {
  it('业务 HTTPException 的字符串 detail：从 message 回填', () => {
    const resp = wireHttpException(404, '项目不存在')
    normaliseErrorEnvelope(resp)
    expect((resp.data as any).detail).toBe('项目不存在')
  })

  it('业务 HTTPException 的 dict detail：恢复成对象而非字符串', () => {
    // 后端 raise HTTPException(409, detail={...}) 时 exc.detail 是原样透出的 dict，
    // 所以下游 `detail?.error` / `detail?.error_code` 这类读法必须能拿到对象。
    const resp = wireHttpException(409, { error: 'data_version_conflict', server_version: 5 })
    normaliseErrorEnvelope(resp)
    const d = (resp.data as any).detail
    expect(typeof d, 'dict detail 被 String() 化就等于丢了 error_code').toBe('object')
    expect(d.error).toBe('data_version_conflict')
    expect(d.server_version).toBe(5)
  })

  it('starlette 原生 404 已有 detail：一个字节都不动', () => {
    const resp = { data: { detail: 'Not Found' } }
    normaliseErrorEnvelope(resp)
    expect((resp.data as any).detail).toBe('Not Found')
    expect((resp.data as any).message).toBeUndefined()
  })

  it('422 校验错误的字段级 detail 数组不被 message 覆盖', () => {
    // validation_exception_handler 同时输出 message 与 detail，
    // 若无条件覆盖就会把字段级错误数组换成「请求参数校验失败」这句废话。
    const resp = {
      data: { code: 422, message: '请求参数校验失败', detail: [{ loc: ['body', 'x'], msg: '字段必填' }] },
    }
    normaliseErrorEnvelope(resp)
    expect(Array.isArray((resp.data as any).detail)).toBe(true)
    expect((resp.data as any).detail[0].msg).toBe('字段必填')
  })

  it('detail 为 null 时视为已有值，不回填（区别于 undefined）', () => {
    const resp = { data: { code: 400, message: '坏请求', detail: null } }
    normaliseErrorEnvelope(resp)
    expect((resp.data as any).detail).toBeNull()
  })

  it('非对象载荷不崩：undefined / 字符串 / 数组 / Blob', () => {
    expect(() => normaliseErrorEnvelope(undefined)).not.toThrow()
    expect(() => normaliseErrorEnvelope({ data: undefined })).not.toThrow()
    expect(() => normaliseErrorEnvelope({ data: 'plain text 502' })).not.toThrow()
    const arr = { data: [1, 2, 3] }
    normaliseErrorEnvelope(arr)
    expect(arr.data).toEqual([1, 2, 3])
    const blob = { data: new Blob(['{"message":"x"}']) }
    expect(() => normaliseErrorEnvelope(blob)).not.toThrow()
    expect((blob.data as any).detail).toBeUndefined()
  })
})

describe('响应拦截器确实调用了信封适配（守接线，不只守函数）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('错误出口的 error.response.data 已带 detail', async () => {
    // 取拦截器的 rejected handler 真实跑一遍。用 _silent 让它在弹 toast / 重试之前就
    // reject，这样断言的是「拦截器入口处已 normalize」而非某个分支的顺手处理。
    // status 选 409：不触发 401 刷新，也不触发 5xx 自动重试。
    const handlers = (http.interceptors.response as any).handlers
    const rejected = handlers?.[0]?.rejected
    expect(typeof rejected, '拦截器 rejected handler 必须存在，否则这条判据是空转').toBe('function')

    const error: any = {
      isAxiosError: true,
      message: 'Request failed with status code 409',
      config: { url: '/api/x', method: 'post', _silent: true },
      response: {
        status: 409,
        headers: {},
        data: { code: 409, message: { error: 'data_version_conflict', server_version: 5 } },
      },
    }

    await expect(rejected(error)).rejects.toBe(error)
    expect(error.response.data.detail, '拦截器没接线 ⇒ 下游拿不到 error_code').toBeDefined()
    expect(error.response.data.detail.error).toBe('data_version_conflict')
    // 原字段不得被破坏：extractErrorDetail 与既有 `data.message` 消费者仍要能读到
    expect(error.response.data.code).toBe(409)
    expect(error.response.data.message.error).toBe('data_version_conflict')
  })
})

describe('handleApiError 端到端：后端根因真的到了用户眼前', () => {
  beforeEach(() => {
    elMessageError.mockClear()
    elMessageWarning.mockClear()
    elNotification.mockClear()
  })

  /** 造一个「已过拦截器」的错误对象。 */
  function axiosErrorAfterInterceptor(status: number, detail: unknown) {
    const error: any = { response: { status, headers: {}, data: { code: status, message: detail } } }
    normaliseErrorEnvelope(error.response)
    return error
  }

  it('400：弹后端中文根因，不是「请求参数错误」兜底', () => {
    handleApiError(axiosErrorAfterInterceptor(400, '项目编码校验失败：与归档时不一致'), '反归档')
    expect(elMessageWarning).toHaveBeenCalledTimes(1)
    const msg = String(elMessageWarning.mock.calls[0][0])
    expect(msg).toContain('项目编码校验失败')
    expect(msg, '退化成兜底文案 ⇒ 用户看不出到底哪里错了').not.toContain('请求参数错误')
  })

  it('409：弹后端冲突原因，不是「数据冲突，请刷新后重试」兜底', () => {
    handleApiError(
      axiosErrorAfterInterceptor(409, { message: '该底稿已绑定在线编辑，请切换到「在线编辑」模式保存' }),
      '保存底稿',
    )
    expect(elNotification).toHaveBeenCalledTimes(1)
    const msg = String((elNotification.mock.calls[0][0] as any).message)
    expect(msg).toContain('已绑定在线编辑')
    expect(msg).not.toContain('数据冲突，请刷新后重试')
  })

  it('422：error_code 特化分派命中（修前从未生效）', () => {
    handleApiError(
      axiosErrorAfterInterceptor(422, { error_code: 'AI_CONTENT_NOT_CONFIRMED', message: 'x' }),
      '提交',
    )
    expect(elMessageWarning).toHaveBeenCalledTimes(1)
    expect(String(elMessageWarning.mock.calls[0][0])).toContain('未确认的 AI 内容')
  })

  it('422：跨模块冲突特化分派命中', () => {
    handleApiError(
      axiosErrorAfterInterceptor(422, { error_code: 'CROSS_MODULE_CONFLICT_UNRESOLVED', message: 'x' }),
      '提交',
    )
    expect(String(elMessageWarning.mock.calls[0][0])).toContain('未调解的跨模块冲突')
  })

  it('503：弹后端降级原因，不是通用「服务暂时不可用」', () => {
    handleApiError(axiosErrorAfterInterceptor(503, { message: 'CWR 图谱服务未就绪' }), '加载联动全景')
    expect(elNotification).toHaveBeenCalledTimes(1)
    expect(String((elNotification.mock.calls[0][0] as any).message)).toContain('CWR 图谱服务未就绪')
  })
})
