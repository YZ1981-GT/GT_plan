import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
const warning = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ apiProxy: api }))
vi.mock('element-plus', () => ({ ElMessage: { warning } }))
vi.mock('@/utils/http', () => ({
  downloadFile: vi.fn(),
  isRequestCancelled: (error: unknown) => (error as { code?: string })?.code === 'ERR_CANCELED',
}))

import { useQueryRunEvidence } from '../useQueryRunEvidence'

function deferred<T = unknown>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

let wrappers: VueWrapper[] = []
function setup(entry: 'business' | 'builder' = 'business') {
  let evidence!: ReturnType<typeof useQueryRunEvidence>
  const wrapper = mount(defineComponent({
    setup() {
      evidence = useQueryRunEvidence(entry)
      return () => h('div')
    },
  }))
  wrappers.push(wrapper)
  return { evidence, wrapper }
}

const canceled = () => Object.assign(new Error('canceled'), { code: 'ERR_CANCELED' })
const signalAt = (call: number) => api.get.mock.calls[call][1].signal as AbortSignal

beforeEach(() => {
  api.get.mockReset()
  api.delete.mockReset().mockResolvedValue(undefined)
  api.post.mockReset().mockResolvedValue(undefined)
  warning.mockReset()
})
afterEach(() => {
  for (const wrapper of wrappers) wrapper.unmount()
  wrappers = []
})

describe('useQueryRunEvidence freshness', () => {
  it('new execution aborts the old check, frees single-flight immediately and ignores the old finally', async () => {
    const { evidence } = setup()
    const old = deferred()
    const next = deferred()
    api.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
    evidence.setFromExecuteResult({ run: { id: 'old', recorded: true }, version: { vector_hash: 'v1' } })
    const oldTask = evidence.checkFreshness()
    const oldSignal = signalAt(0)
    expect(evidence.checking.value).toBe(true)
    await evidence.checkFreshness()
    expect(api.get).toHaveBeenCalledTimes(1)
    evidence.setFromExecuteResult({ run: { id: 'new', recorded: true }, version: { vector_hash: 'v2' } })
    expect(oldSignal.aborted).toBe(true)
    expect(evidence.checking.value).toBe(false)
    expect(evidence.freshness.value).toBeNull()
    const nextTask = evidence.checkFreshness()
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/custom-query/runs/new/freshness',
      expect.objectContaining({ _silent: true, _dedupe: false, signal: expect.any(AbortSignal) }))
    old.resolve({ status: 'stale' })
    await oldTask
    expect(evidence.checking.value).toBe(true)
    expect(evidence.freshness.value).toBeNull()
    next.resolve({ status: 'current' })
    await nextTask
    expect(evidence.checking.value).toBe(false)
    expect(evidence.freshness.value?.status).toBe('current')
  })

  it('repeating the same run id uses a fresh producer after aborting the old check', async () => {
    const { evidence } = setup()
    const old = deferred()
    const next = deferred()
    api.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
    evidence.setFromExecuteResult({ run: { id: 'same', recorded: true } })
    const oldTask = evidence.checkFreshness()
    const oldSignal = signalAt(0)
    evidence.setFromExecuteResult({ run: { id: 'same', recorded: true } })
    const nextTask = evidence.checkFreshness()
    expect(oldSignal.aborted).toBe(true)
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/custom-query/runs/same/freshness',
      expect.objectContaining({ _dedupe: false, signal: expect.any(AbortSignal) }))
    old.resolve({ status: 'stale' })
    await oldTask
    expect(evidence.freshness.value).toBeNull()
    next.resolve({ status: 'current' })
    await nextTask
    expect(evidence.freshness.value?.status).toBe('current')
  })

  it('stale rejection and cancellation never overwrite the new run; real failure reports an error', async () => {
    const { evidence } = setup()
    const old = deferred()
    api.get.mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error('network'))
    evidence.setFromExecuteResult({ run: { id: 'a', recorded: true } })
    const task = evidence.checkFreshness()
    evidence.setFromExecuteResult({ run: { id: 'b', recorded: true } })
    old.reject(canceled())
    await task
    expect(evidence.checkError.value).toBeNull()
    await evidence.checkFreshness()
    expect(evidence.checkError.value).toContain('网络连接失败')
    evidence.setFromExecuteResult({ run: { id: 'c', recorded: true } })
    expect(evidence.checkError.value).toBeNull()
  })
})

describe('useQueryRunEvidence lists', () => {
  it('runs and artifacts load concurrently with entry/project params and independent signals', async () => {
    const { evidence } = setup()
    api.get.mockResolvedValueOnce({ runs: ['run'] }).mockResolvedValueOnce({ artifacts: ['artifact'] })
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    expect(api.get).toHaveBeenNthCalledWith(1, '/api/custom-query/runs', {
      params: { entry: 'business', limit: '20', project_id: 'p1' }, _silent: true, _dedupe: false, signal: expect.any(AbortSignal),
    })
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/custom-query/artifacts', {
      params: { entry: 'business', limit: '20', project_id: 'p1' }, _silent: true, _dedupe: false, signal: expect.any(AbortSignal),
    })
    expect(signalAt(0).aborted).toBe(false)
    expect(evidence.runs.value).toEqual(['run'])
    expect(evidence.artifacts.value).toEqual(['artifact'])
  })

  it('a second load in the same project bypasses the aborted list producer', async () => {
    const { evidence } = setup()
    const first = deferred()
    const second = deferred()
    api.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const oldTask = evidence.loadRuns('p1')
    const oldSignal = signalAt(0)
    const newTask = evidence.loadRuns('p1')
    expect(oldSignal.aborted).toBe(true)
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/custom-query/runs',
      expect.objectContaining({ _dedupe: false, params: expect.objectContaining({ project_id: 'p1' }) }))
    first.resolve({ runs: ['obsolete'] })
    await oldTask
    expect(evidence.runs.value).toEqual([])
    second.resolve({ runs: ['latest'] })
    await newTask
    expect(evidence.runs.value).toEqual(['latest'])
  })

  it('failure preserves existing rows, cancellation stays quiet, malformed success is not an empty list', async () => {
    const { evidence } = setup()
    api.get.mockResolvedValueOnce({ runs: ['old'] }).mockResolvedValueOnce({ artifacts: ['old-art'] })
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    api.get.mockRejectedValueOnce(new Error('network')).mockRejectedValueOnce(new Error('network'))
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    expect(evidence.runs.value).toEqual(['old'])
    expect(evidence.artifacts.value).toEqual(['old-art'])
    expect(evidence.runsError.value).toContain('网络连接失败')
    expect(evidence.artifactsError.value).toContain('网络连接失败')
    expect(warning).toHaveBeenCalledTimes(2)
    api.get.mockRejectedValueOnce(canceled()).mockResolvedValueOnce({})
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    expect(evidence.runsError.value).toBeNull()
    expect(evidence.artifactsError.value).toContain('返回格式异常')
    expect(evidence.artifacts.value).toEqual(['old-art'])
    expect(warning).toHaveBeenCalledTimes(3)
  })

  it('switching project clears both lists/errors and rejects late results from the old project', async () => {
    const { evidence } = setup()
    api.get.mockResolvedValueOnce({ runs: ['old-run'] }).mockResolvedValueOnce({ artifacts: ['old-art'] })
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    const old = deferred()
    const newer = deferred()
    api.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(newer.promise)
      .mockResolvedValueOnce({ runs: ['new-run'] })
    const oldTask = evidence.loadRuns('p1')
    const oldSignal = signalAt(2)
    const otherTask = evidence.loadArtifacts('p1')
    const otherSignal = signalAt(3)
    const switchedTask = evidence.loadRuns('p2')
    expect(oldSignal.aborted).toBe(true)
    expect(otherSignal.aborted).toBe(true)
    expect(evidence.runs.value).toEqual([])
    expect(evidence.artifacts.value).toEqual([])
    old.resolve({ runs: ['old-result'] })
    newer.resolve({ artifacts: ['old-result'] })
    await Promise.all([oldTask, otherTask, switchedTask])
    expect(evidence.runs.value).toEqual(['new-run'])
    expect(evidence.artifacts.value).toEqual([])
    expect(evidence.runsError.value).toBeNull()
    expect(warning).not.toHaveBeenCalled()
  })
})

describe('useQueryRunEvidence mutations and disposal', () => {
  it('hide invalidates the old list, reloads in the same project only after success', async () => {
    const { evidence } = setup()
    api.get.mockResolvedValueOnce({ runs: ['old'] })
    await evidence.loadRuns('p1')
    const old = deferred()
    const hide = deferred()
    api.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ runs: ['remaining'] })
    api.delete.mockReturnValueOnce(hide.promise)
    const oldTask = evidence.loadRuns('p1')
    const oldSignal = signalAt(1)
    const hideTask = evidence.hideRun('id1')
    expect(oldSignal.aborted).toBe(true)
    expect(api.get).toHaveBeenCalledTimes(2)
    old.resolve({ runs: ['stale'] })
    await oldTask
    expect(evidence.runs.value).toEqual(['old'])
    hide.resolve(undefined)
    await hideTask
    expect(api.delete).toHaveBeenCalledWith('/api/custom-query/runs/id1', { _silent: true })
    expect(api.get).toHaveBeenNthCalledWith(3, '/api/custom-query/runs',
      expect.objectContaining({ params: { entry: 'business', limit: '20', project_id: 'p1' } }))
    expect(evidence.runs.value).toEqual(['remaining'])
  })

  it('a load started during hide is replaced by a post-hide reload', async () => {
    const { evidence } = setup()
    const hide = deferred()
    const inflight = deferred()
    api.get.mockResolvedValueOnce({ runs: ['before'] }).mockReturnValueOnce(inflight.promise)
      .mockResolvedValueOnce({ runs: ['after'] })
    await evidence.loadRuns('p1')
    api.delete.mockReturnValueOnce(hide.promise)
    const mutation = evidence.hideRun('id1')
    const load = evidence.loadRuns('p1')
    const signal = signalAt(1)
    expect(evidence.runs.value).toEqual(['before'])
    hide.resolve(undefined)
    await mutation
    expect(signal.aborted).toBe(true)
    expect(evidence.runs.value).toEqual(['after'])
    inflight.resolve({ runs: ['obsolete'] })
    await load
    expect(evidence.runs.value).toEqual(['after'])
  })

  it('hide finishing after a project switch must not reload the old project', async () => {
    const { evidence } = setup()
    const hide = deferred()
    api.get.mockResolvedValueOnce({ runs: ['p1'] }).mockResolvedValueOnce({ artifacts: [] })
      .mockResolvedValueOnce({ artifacts: ['p2'] })
    await Promise.all([evidence.loadRuns('p1'), evidence.loadArtifacts('p1')])
    api.delete.mockReturnValueOnce(hide.promise)
    const task = evidence.hideRun('id1')
    await evidence.loadArtifacts('p2')
    hide.resolve(undefined)
    await task
    expect(api.get).toHaveBeenCalledTimes(3)
    expect(evidence.runs.value).toEqual([])
    expect(evidence.artifacts.value).toEqual(['p2'])
  })

  it('clear invalidates inflight list; success clears only after response and sends entry', async () => {
    const { evidence } = setup('builder')
    const old = deferred()
    const clear = deferred()
    api.get.mockResolvedValueOnce({ runs: ['old'] }).mockReturnValueOnce(old.promise)
    api.post.mockReturnValueOnce(clear.promise)
    await evidence.loadRuns('p1')
    const oldTask = evidence.loadRuns('p1')
    const oldSignal = signalAt(1)
    const task = evidence.clearRuns()
    expect(api.post).toHaveBeenCalledWith('/api/custom-query/runs/clear', {}, {
      params: { entry: 'builder' }, _silent: true,
    })
    expect(evidence.runs.value).toEqual(['old'])
    expect(oldSignal.aborted).toBe(true)
    old.resolve({ runs: ['stale'] })
    await oldTask
    expect(evidence.runs.value).toEqual(['old'])
    clear.resolve(undefined)
    await task
    expect(evidence.runs.value).toEqual([])
    expect(evidence.runsError.value).toBeNull()
  })

  it('clear completion invalidates a load started while the mutation was pending', async () => {
    const { evidence } = setup()
    const clear = deferred()
    const inflight = deferred()
    api.get.mockResolvedValueOnce({ runs: ['before'] }).mockReturnValueOnce(inflight.promise)
    await evidence.loadRuns('p1')
    api.post.mockReturnValueOnce(clear.promise)
    const mutation = evidence.clearRuns()
    const load = evidence.loadRuns('p1')
    const signal = signalAt(1)
    clear.resolve(undefined)
    await mutation
    expect(signal.aborted).toBe(true)
    inflight.resolve({ runs: ['stale'] })
    await load
    expect(evidence.runs.value).toEqual([])
  })

  it('clear failure keeps existing list, and a late success does not clear a newly selected project', async () => {
    const { evidence } = setup()
    api.get.mockResolvedValueOnce({ runs: ['old'] })
    await evidence.loadRuns('p1')
    api.post.mockRejectedValueOnce(new Error('network'))
    await evidence.clearRuns()
    expect(evidence.runs.value).toEqual(['old'])
    expect(evidence.runsError.value).toContain('网络连接失败')
    const clear = deferred()
    api.post.mockReturnValueOnce(clear.promise)
    const task = evidence.clearRuns()
    api.get.mockResolvedValueOnce({ runs: ['p2'] })
    await evidence.loadRuns('p2')
    clear.resolve(undefined)
    await task
    expect(evidence.runs.value).toEqual(['p2'])
  })

  describe.each(['hide', 'clear'] as const)('%s late failure', (operation) => {
    it.each(['success', 'failure', 'pending'] as const)('preserves a newer list load in %s state', async (loadState) => {
      const { evidence } = setup()
      api.get.mockResolvedValueOnce({ runs: ['before'] })
      await evidence.loadRuns('p1')
      const mutation = deferred()
      const newer = deferred()
      const mutationApi = operation === 'hide' ? api.delete : api.post
      mutationApi.mockReturnValueOnce(mutation.promise)
      const mutationTask = operation === 'hide' ? evidence.hideRun('id1') : evidence.clearRuns()
      api.get.mockReturnValueOnce(newer.promise)
      const loadTask = evidence.loadRuns('p1')
      if (loadState === 'success') {
        newer.resolve({ runs: ['latest'] })
        await loadTask
      } else if (loadState === 'failure') {
        newer.reject(new Error('network'))
        await loadTask
      }
      const rowsBefore = [...evidence.runs.value]
      const errorBefore = evidence.runsError.value
      const warningsBefore = warning.mock.calls.length
      if (loadState === 'failure') {
        expect(errorBefore).toContain('加载查询历史')
        expect(warningsBefore).toBe(1)
      } else {
        expect(errorBefore).toBeNull()
        expect(warningsBefore).toBe(0)
      }
      mutation.reject(new Error('network'))
      await mutationTask
      expect(evidence.runs.value).toEqual(rowsBefore)
      expect(evidence.runsError.value).toBe(errorBefore)
      expect(warning).toHaveBeenCalledTimes(warningsBefore)
      expect(api.get).toHaveBeenCalledTimes(2)
      if (loadState === 'pending') {
        newer.resolve({ runs: ['latest'] })
        await loadTask
        expect(evidence.runs.value).toEqual(['latest'])
        expect(evidence.runsError.value).toBeNull()
        expect(warning).not.toHaveBeenCalled()
      }
    })
  })

  it('unmount aborts all active requests, removes visibility listener and ignores late results', async () => {
    const { evidence, wrapper } = setup()
    const pending = [deferred(), deferred(), deferred()]
    api.get.mockReturnValueOnce(pending[0].promise).mockReturnValueOnce(pending[1].promise)
      .mockReturnValueOnce(pending[2].promise)
    evidence.setFromExecuteResult({ run: { id: 'r', recorded: true } })
    const tasks = [evidence.checkFreshness(), evidence.loadRuns('p1'), evidence.loadArtifacts('p1')]
    const signals = [signalAt(0), signalAt(1), signalAt(2)]
    wrapper.unmount()
    expect(signals.every(signal => signal.aborted)).toBe(true)
    for (const item of pending) item.resolve({ status: 'stale', runs: ['bad'], artifacts: ['bad'] })
    await Promise.all(tasks)
    expect(evidence.runs.value).toEqual([])
    expect(evidence.artifacts.value).toEqual([])
    expect(evidence.freshness.value).toBeNull()
    document.dispatchEvent(new Event('visibilitychange'))
    expect(api.get).toHaveBeenCalledTimes(3)
  })
})
