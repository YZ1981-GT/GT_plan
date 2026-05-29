/**
 * useFormSubmit 单测 — V3 Req 3.2
 *
 * 验证：
 * - validate() 失败时 short-circuit 不调用 action
 * - validate() 通过时调用 action 并切换 submitting
 * - 重复点击被屏蔽
 * - action 抛异常时 submitting 仍重置
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useFormSubmit } from '../useFormSubmit'

function makeFormRef(validateImpl: () => Promise<unknown>) {
  return ref({
    validate: vi.fn(validateImpl),
  } as any)
}

describe('useFormSubmit', () => {
  it('validate 通过 → 调用 action 并返回 true', async () => {
    const formRef = makeFormRef(async () => true)
    const { submit, submitting } = useFormSubmit(formRef)
    const action = vi.fn(async () => {})

    expect(submitting.value).toBe(false)
    const ok = await submit(action)
    expect(ok).toBe(true)
    expect(action).toHaveBeenCalledTimes(1)
    expect(submitting.value).toBe(false)
  })

  it('validate 失败 → short-circuit，不调用 action，返回 false', async () => {
    const formRef = makeFormRef(async () => Promise.reject({ field: 'invalid' }))
    const { submit } = useFormSubmit(formRef)
    const action = vi.fn(async () => {})

    const ok = await submit(action)
    expect(ok).toBe(false)
    expect(action).not.toHaveBeenCalled()
  })

  it('formRef 为 null → short-circuit，返回 false', async () => {
    const formRef = ref(null) as any
    const { submit } = useFormSubmit(formRef)
    const action = vi.fn(async () => {})

    const ok = await submit(action)
    expect(ok).toBe(false)
    expect(action).not.toHaveBeenCalled()
  })

  it('submitting=true 时重复点击被屏蔽', async () => {
    let resolveAction!: () => void
    const formRef = makeFormRef(async () => true)
    const { submit, submitting } = useFormSubmit(formRef)
    const action = vi.fn(
      () => new Promise<void>((resolve) => { resolveAction = resolve }),
    )

    const p1 = submit(action)
    // 等 validate().then() 链 + submitting=true 同步赋值穿过事件循环
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(submitting.value).toBe(true)
    expect(action).toHaveBeenCalledTimes(1)

    const p2 = await submit(action)
    expect(p2).toBe(false)
    expect(action).toHaveBeenCalledTimes(1)

    resolveAction()
    await p1
    expect(submitting.value).toBe(false)
  })

  it('action 抛异常 → submitting 重置且异常向上抛出', async () => {
    const formRef = makeFormRef(async () => true)
    const { submit, submitting } = useFormSubmit(formRef)
    const error = new Error('API 错误')
    const action = vi.fn(async () => { throw error })

    await expect(submit(action)).rejects.toThrow('API 错误')
    expect(submitting.value).toBe(false)
  })
})
