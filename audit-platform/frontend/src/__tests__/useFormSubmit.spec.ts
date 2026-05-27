/**
 * useFormSubmit 单元测试（V3 Req 3.3）
 *
 * 覆盖 useFormSubmit 的核心契约：
 *  1. validate() 失败时 short-circuit（返回 false，不调用 action）
 *  2. validate() 通过时 action 被执行（返回 true）
 *  3. submitting 屏蔽重复点击
 *  4. action 抛异常时 submitting 重置后向上抛
 *  5. formRef 为空时安全失败
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import type { FormInstance } from 'element-plus'
import { useFormSubmit } from '@/composables/useFormSubmit'

function makeFormRef(behavior: 'pass' | 'fail') {
  const fakeForm = {
    validate: vi.fn(() =>
      behavior === 'pass'
        ? Promise.resolve(true)
        : Promise.reject({ name: [{ message: '校验失败' }] }),
    ),
  }
  return ref(fakeForm as unknown as FormInstance)
}

describe('useFormSubmit', () => {
  it('校验失败时 short-circuit，不调用 action（V3 Req 3.3 空提交拦截）', async () => {
    const formRef = makeFormRef('fail')
    const { submit, submitting } = useFormSubmit(formRef)
    const action = vi.fn(async () => 'done')

    const result = await submit(action)

    expect(result).toBe(false)
    expect(action).not.toHaveBeenCalled()
    expect(submitting.value).toBe(false)
  })

  it('校验通过时执行 action，返回 true', async () => {
    const formRef = makeFormRef('pass')
    const { submit } = useFormSubmit(formRef)
    const action = vi.fn(async () => 'done')

    const result = await submit(action)

    expect(result).toBe(true)
    expect(action).toHaveBeenCalledTimes(1)
  })

  it('submitting 在 action 期间为 true，结束后回到 false', async () => {
    const formRef = makeFormRef('pass')
    const { submit, submitting } = useFormSubmit(formRef)

    let resolveAction!: () => void
    const action = vi.fn(() => new Promise<void>(r => { resolveAction = r }))

    expect(submitting.value).toBe(false)
    const pending = submit(action)
    // 等微任务把 validate 走完
    await nextTick()
    await Promise.resolve()
    await Promise.resolve()
    expect(submitting.value).toBe(true)

    resolveAction()
    await pending
    expect(submitting.value).toBe(false)
  })

  it('submitting=true 时再次调用直接返回 false（防重复点击）', async () => {
    const formRef = makeFormRef('pass')
    const { submit, submitting } = useFormSubmit(formRef)

    let resolveAction!: () => void
    const action = vi.fn(() => new Promise<void>(r => { resolveAction = r }))

    const first = submit(action)
    await nextTick()
    await Promise.resolve()
    await Promise.resolve()
    expect(submitting.value).toBe(true)

    const second = await submit(action)   // 立即返回 false
    expect(second).toBe(false)
    expect(action).toHaveBeenCalledTimes(1)   // 第二次没真正调用

    resolveAction()
    await first
  })

  it('action 抛异常时，submitting 已重置且异常向上抛出', async () => {
    const formRef = makeFormRef('pass')
    const { submit, submitting } = useFormSubmit(formRef)
    const action = vi.fn(async () => {
      throw new Error('业务失败')
    })

    await expect(submit(action)).rejects.toThrow('业务失败')
    expect(submitting.value).toBe(false)
  })

  it('formRef 为空时安全失败（不抛异常，不调用 action）', async () => {
    const formRef = ref<FormInstance | null>(null)
    const { submit, submitting } = useFormSubmit(formRef)
    const action = vi.fn(async () => 'done')

    const result = await submit(action)

    expect(result).toBe(false)
    expect(action).not.toHaveBeenCalled()
    expect(submitting.value).toBe(false)
  })
})
