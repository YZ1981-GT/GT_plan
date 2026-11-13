import { describe, expect, it, vi } from 'vitest'
import { useAdjustmentHallResource } from '../useAdjustmentHallResource'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

describe('useAdjustmentHallResource', () => {
  it('旧项目响应晚到时不能覆盖新上下文', async () => {
    let context = 'p1:2024:1'
    const resource = useAdjustmentHallResource(() => [] as string[], () => context)
    const oldRequest = deferred<string[]>()
    const nextRequest = deferred<string[]>()
    const oldLoad = resource.load(() => oldRequest.promise, '读取列表失败')

    context = 'p2:2025:2'
    const nextLoad = resource.load(() => nextRequest.promise, '读取列表失败')
    nextRequest.resolve(['new'])
    await nextLoad
    oldRequest.resolve(['old'])
    await oldLoad

    expect(resource.data.value).toEqual(['new'])
    expect(resource.status.value).toBe('success')
  })

  it('同一上下文较早请求晚到时也不能覆盖重试结果', async () => {
    const resource = useAdjustmentHallResource(() => '', () => 'p1:2025:1')
    const first = deferred<string>()
    const retry = deferred<string>()
    const firstLoad = resource.load(() => first.promise, '读取失败')
    const retryLoad = resource.load(() => retry.promise, '读取失败')
    retry.resolve('retry')
    await retryLoad
    first.resolve('first')
    await firstLoad
    expect(resource.data.value).toBe('retry')
  })

  it('失败保留最后成功数据并暴露独立错误和最后成功时间', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-02T03:04:05Z'))
    const resource = useAdjustmentHallResource(() => [] as string[], () => 'ctx')
    await resource.load(async () => ['saved'], '读取科目失败')
    const lastSuccess = resource.lastSuccessAt.value
    expect(lastSuccess).toBe(Date.now())

    await resource.load(async () => { throw new Error('network') }, '读取科目失败')
    expect(resource.data.value).toEqual(['saved'])
    expect(resource.status.value).toBe('error')
    expect(resource.error.value).toBe('读取科目失败')
    expect(resource.lastSuccessAt.value).toBe(lastSuccess)
    vi.useRealTimers()
  })

  it('数据库结构未升级（503 MIGRATION_PENDING）时错误文案用后端说明', async () => {
    const resource = useAdjustmentHallResource(() => [] as string[], () => 'ctx')
    const text = '数据库结构未升级：程序需要 V251，库里最高 V234，还有 17 个迁移未执行。请联系管理员重启后端（启动时会自动执行迁移）'
    await resource.load(async () => {
      throw { response: { status: 503, data: { message: { error_code: 'MIGRATION_PENDING', message: text } } } }
    }, '读取客户已入账建议失败，请重试')
    expect(resource.status.value).toBe('error')
    expect(resource.error.value).toBe(text)
    // 其他 503 仍用调用方给的文案
    await resource.load(async () => { throw { response: { status: 503, data: { message: '维护中' } } } }, '读取失败')
    expect(resource.error.value).toBe('读取失败')
  })

  it('取消请求不伪装成读取失败；reset 使在途响应失效', async () => {
    const resource = useAdjustmentHallResource(() => ['initial'], () => 'ctx')
    await resource.load(async () => { throw { code: 'ERR_CANCELED' } }, '读取协作失败')
    expect(resource.status.value).toBe('idle')
    expect(resource.error.value).toBe('')

    const request = deferred<string[]>()
    const loading = resource.load(() => request.promise, '读取失败')
    resource.reset()
    request.resolve(['late'])
    await loading
    expect(resource.data.value).toEqual(['initial'])
    expect(resource.status.value).toBe('idle')
  })
})
