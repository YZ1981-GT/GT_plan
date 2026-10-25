/** F1 保存队列：真实生产 composable + 可控网络 Promise，禁止假 flush。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref, type EffectScope } from 'vue'
import { useF1FormData } from '../composables/useF1FormData'

const mocks = vi.hoisted(() => ({ put: vi.fn(), get: vi.fn(), error: vi.fn(), warning: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { put: mocks.put, get: mocks.get } }))
vi.mock('element-plus', () => ({ ElMessage: { error: mocks.error, warning: mocks.warning } }))

function deferred() {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function microtasks() { for (let n = 0; n < 12; n++) await Promise.resolve() }
let scope: EffectScope
let form: ReturnType<typeof useF1FormData>
beforeEach(() => {
  vi.useFakeTimers()
  mocks.put.mockReset()
  mocks.get.mockReset()
  mocks.error.mockReset()
  mocks.warning.mockReset()
  mocks.put.mockResolvedValue(undefined)
  scope = effectScope()
  form = scope.run(() => useF1FormData({ wpId: ref('wp-f1'), projectId: ref('project-f1') }))!
})
afterEach(async () => {
  scope.stop()
  await microtasks()
  vi.useRealTimers()
})

function sent(index: number) { return mocks.put.mock.calls[index][1].items }

describe('F1 flush 是真实落库屏障', () => {
  it('取消 debounce，但必须等请求完成才 resolve（去掉 await 必红）', async () => {
    const net = deferred()
    mocks.put.mockReturnValueOnce(net.promise)
    form.debouncedSave('F1-rp-rows', { remark: '最新值' })
    let done = false
    const flush = form.flushPendingSave().then(() => { done = true })
    await microtasks()
    expect(mocks.put).toHaveBeenCalledTimes(1)
    expect(sent(0)[0].remark).toBe('最新值')
    expect(done).toBe(false)
    net.resolve()
    await flush
    expect(done).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(mocks.put).toHaveBeenCalledTimes(1)
  })

  it.each(['即时', '批量', '定时'] as const)('flush 等待%s已发出的请求，不重复提交同版本', async (kind) => {
    const net = deferred()
    mocks.put.mockReturnValueOnce(net.promise)
    if (kind === '即时') void form.saveImmediate('F1-rp-rows', { remark: '在途值' })
    if (kind === '批量') void form.saveBatch([{ itemId: 'F1-rp-rows', data: { remark: '在途值' } }])
    if (kind === '定时') {
      form.debouncedSave('F1-rp-rows', { remark: '在途值' })
      await vi.advanceTimersByTimeAsync(2000)
    }
    await microtasks()
    let done = false
    const flush = form.flushPendingSave().then(() => { done = true })
    await microtasks()
    expect(done).toBe(false)
    expect(mocks.put).toHaveBeenCalledTimes(1)
    net.resolve()
    await flush
    expect(done).toBe(true)
  })

  it('失败严格拒绝 flush，下一次仍可提交原 pending（先清 pending 必红）', async () => {
    const failure = new Error('网络断开')
    mocks.put.mockRejectedValueOnce(failure)
    form.debouncedSave('F1-rp-rows', { remark: '失败也保留' })
    await expect(form.flushPendingSave()).rejects.toBe(failure)
    expect(form.allResponses.value.get('F1-rp-rows')?.remark).toBe('失败也保留')
    expect(mocks.error).toHaveBeenCalledWith('保存失败，编辑已保留，请重试')
    await form.flushPendingSave()
    expect(mocks.put).toHaveBeenCalledTimes(2)
    expect(sent(1)[0].remark).toBe('失败也保留')
  })

  it.each(['即时', '批量'] as const)('%s兼容非抛错契约，失败留待 flush 重试而非遗失', async (kind) => {
    mocks.put.mockRejectedValueOnce(new Error('服务暂不可用'))
    const save = kind === '即时'
      ? form.saveImmediate('F1-rp-rows', { remark: '待重试' })
      : form.saveBatch([{ itemId: 'F1-rp-rows', data: { remark: '待重试' } }])
    await expect(save).resolves.toBeUndefined()
    expect(mocks.error).toHaveBeenCalledTimes(1)
    await form.flushPendingSave()
    expect(mocks.put).toHaveBeenCalledTimes(2)
    expect(sent(1)[0].remark).toBe('待重试')
  })

  it('定时失败不制造后台拒绝，重试仍携带该编辑', async () => {
    mocks.put.mockRejectedValueOnce(new Error('定时写入失败'))
    form.debouncedSave('F1-rp-rows', { remark: '后台编辑' })
    await vi.advanceTimersByTimeAsync(2000)
    await microtasks()
    expect(mocks.error).toHaveBeenCalledTimes(1)
    await form.flushPendingSave()
    expect(sent(1)[0].remark).toBe('后台编辑')
  })

  it('在途请求失败时 flush 必须拒绝，不因定时器已清理而报成功', async () => {
    const net = deferred()
    const failure = new Error('在途失败')
    mocks.put.mockReturnValueOnce(net.promise)
    void form.saveImmediate('F1-rp-rows', { remark: '在途编辑' })
    await microtasks()
    const flush = form.flushPendingSave()
    const rejected = expect(flush).rejects.toBe(failure)
    net.reject(failure)
    await rejected
    expect(mocks.put).toHaveBeenCalledTimes(1)
    await form.flushPendingSave()
    expect(sent(1)[0].remark).toBe('在途编辑')
  })

  it('空底稿编号不可被 flush 当作保存成功', async () => {
    scope.stop()
    scope = effectScope()
    form = scope.run(() => useF1FormData({ wpId: ref(''), projectId: ref('project-f1') }))!
    form.debouncedSave('F1-rp-rows', { remark: '未落库' })
    await expect(form.flushPendingSave()).rejects.toThrow('底稿编号缺失')
    expect(mocks.put).not.toHaveBeenCalled()
  })
})

describe('F1 最新版本顺序与批量去重', () => {
  it('即时→批量同键串行，旧请求冻结值，新值最后落库（取消队列必红）', async () => {
    const old = deferred()
    const latest = deferred()
    mocks.put.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
    const first = form.saveImmediate('F1-rp-rows', { remark: '旧值' })
    await microtasks()
    const second = form.saveBatch([{ itemId: 'F1-rp-rows', data: { remark: '新值' } }])
    await microtasks()
    expect(mocks.put).toHaveBeenCalledTimes(1)
    expect(sent(0)[0].remark).toBe('旧值')
    old.resolve()
    await first
    await microtasks()
    expect(sent(1)[0].remark).toBe('新值')
    let done = false
    const flush = form.flushPendingSave().then(() => { done = true })
    await microtasks()
    expect(done).toBe(false)
    latest.resolve()
    await second
    await flush
    expect(mocks.put).toHaveBeenCalledTimes(2)
  })

  it('旧请求成功不得清除等待 debounce 的新编辑', async () => {
    const old = deferred()
    mocks.put.mockReturnValueOnce(old.promise)
    const first = form.saveImmediate('F1-rp-rows', { remark: '旧编辑' })
    await microtasks()
    form.debouncedSave('F1-rp-rows', { remark: '较新编辑' })
    old.resolve()
    await first
    await form.flushPendingSave()
    expect(mocks.put).toHaveBeenCalledTimes(2)
    expect(sent(1)[0].remark).toBe('较新编辑')
  })

  it('flush 等待期间出现的编辑也须落库，不能读到早一拍快照', async () => {
    const firstNet = deferred()
    mocks.put.mockReturnValueOnce(firstNet.promise)
    form.debouncedSave('F1-rp-rows', { remark: '开始值' })
    const flush = form.flushPendingSave()
    await microtasks()
    form.debouncedSave('F1-rp-rows', { remark: '等待中追加' })
    firstNet.resolve()
    await flush
    expect(sent(1)[0].remark).toBe('等待中追加')
    await vi.advanceTimersByTimeAsync(2000)
    expect(mocks.put).toHaveBeenCalledTimes(2)
  })

  it('旧版本失败不能污染较新成功版本或阻塞串行队列', async () => {
    const old = deferred()
    mocks.put.mockReturnValueOnce(old.promise)
    const first = form.saveImmediate('F1-rp-rows', { remark: '旧值' })
    await microtasks()
    const second = form.saveImmediate('F1-rp-rows', { remark: '已修正' })
    old.reject(new Error('旧请求失败'))
    await first
    await second
    await expect(form.flushPendingSave()).resolves.toBeUndefined()
    expect(mocks.put).toHaveBeenCalledTimes(2)
    expect(sent(1)[0].remark).toBe('已修正')
  })

  it('批量重复 item_id 后值覆盖前值，保留已存在的另一列', async () => {
    form.allResponses.value.set('F1-rp-note', {
      item_id: 'F1-rp-note', conclusion: '通过', remark: '原备注',
    })
    await form.saveBatch([
      { itemId: 'F1-rp-note', data: { remark: '前值' } },
      { itemId: 'F1-rp-note', data: { remark: '后值' } },
      { itemId: 'F1-rp-conclusion', data: { conclusion: '已检查' } },
    ])
    expect(sent(0)).toEqual([
      { item_id: 'F1-rp-note', conclusion: '通过', remark: '后值' },
      { item_id: 'F1-rp-conclusion', conclusion: '已检查', remark: null },
    ])
    expect(mocks.put.mock.calls[0][0]).toBe('/api/workpapers/wp-f1/checklist-responses')
    expect(mocks.put.mock.calls[0][1].project_id).toBe('project-f1')
  })

  it('批量失败保留全部键供下次 flush 重试', async () => {
    mocks.put.mockRejectedValueOnce(new Error('整批失败'))
    await form.saveBatch([
      { itemId: 'F1-rp-note', data: { remark: '甲' } },
      { itemId: 'F1-rp-conclusion', data: { conclusion: '乙' } },
    ])
    await form.flushPendingSave()
    expect(sent(1)).toEqual(sent(0))
    expect(sent(1)).toHaveLength(2)
  })

  it('卸载时落库失败也不产生 unhandled rejection', async () => {
    mocks.put.mockRejectedValue(new Error('卸载时不可达'))
    form.debouncedSave('F1-rp-note', { remark: '卸载编辑' })
    scope.stop()
    await microtasks()
    expect(mocks.put).toHaveBeenCalledTimes(1)
    expect(mocks.error).toHaveBeenCalledTimes(1)
    expect(form.allResponses.value.get('F1-rp-note')?.remark).toBe('卸载编辑')
  })
})

describe('F1 flush 失败也等待其他已发请求', () => {
  it('某键失败不能让 flush 越过另一键尚未完成的请求', async () => {
    const firstNet = deferred()
    const secondNet = deferred()
    const failure = new Error('第一键失败')
    mocks.put.mockReturnValueOnce(firstNet.promise).mockReturnValueOnce(secondNet.promise)
    form.debouncedSave('F1-rp-note', { remark: '甲' })
    let done = false
    const flush = form.flushPendingSave().finally(() => { done = true })
    const rejected = expect(flush).rejects.toBe(failure)
    await microtasks()
    void form.saveImmediate('F1-rp-conclusion', { conclusion: '乙' })
    firstNet.reject(failure)
    await microtasks()
    expect(mocks.put).toHaveBeenCalledTimes(2)
    expect(done).toBe(false)
    secondNet.resolve()
    await rejected
    expect(done).toBe(true)
    await form.flushPendingSave()
    expect(sent(2).map((item: { item_id: string }) => item.item_id)).toEqual(['F1-rp-note'])
  })
})
