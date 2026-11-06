// @vitest-environment node
import { EventEmitter } from 'node:events'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const execFileSync = vi.hoisted(() => vi.fn())
vi.mock('node:child_process', () => ({ execFileSync }))

import { candidatePortGuard, resolveCandidateFrontendIdentity } from '../../../vite.config'

const OID = '0123456789abcdef0123456789abcdef01234567'
function env(overrides: Record<string, string | undefined> = {}) {
  return {
    GT_EXPECTED_CANDIDATE_TREE_OID: OID,
    VITE_DEV_PORT: '3093',
    VITE_API_BASE_URL: 'http://127.0.0.1:9993',
    ...overrides,
  }
}

beforeEach(() => {
  execFileSync.mockReset()
    .mockReturnValueOnce(`${OID}\n`)
    .mockReturnValueOnce('')
})

describe('候选前端代码身份与端口隔离', () => {
  it('普通模式不调用 git、不产生 marker 身份', () => {
    expect(resolveCandidateFrontendIdentity({}, [], 'D:/repo/frontend')).toBeNull()
    expect(execFileSync).not.toHaveBeenCalled()
  })

  it('以 frontend cwd 解析 HEAD tree，忽略未跟踪文件但拒绝受跟踪改动', () => {
    expect(resolveCandidateFrontendIdentity(env(), [], 'D:/repo/frontend')).toEqual({ expected: OID, actual: OID })
    expect(execFileSync.mock.calls).toEqual([
      ['git', ['rev-parse', 'HEAD^{tree}'], expect.objectContaining({ cwd: 'D:/repo/frontend' })],
      ['git', ['status', '--porcelain', '--untracked-files=no'], expect.objectContaining({ cwd: 'D:/repo/frontend' })],
    ])
  })

  it.each([
    [{ GT_EXPECTED_CANDIDATE_TREE_OID: 'ABC' }, [], '40 位'],
    [{ VITE_DEV_PORT: '3030' }, [], '非 3030'],
    [{ VITE_DEV_PORT: undefined }, [], 'VITE_DEV_PORT'],
    [{ VITE_API_BASE_URL: undefined }, [], 'VITE_API_BASE_URL'],
    [{ VITE_API_BASE_URL: 'http://127.0.0.1:9980' }, [], '9980'],
    [{}, ['--port', '3030'], '--port'],
    [{}, ['--host=0.0.0.0'], '--host'],
  ] as const)('非法候选启动输入拒绝：%j', (overrides, argv, message) => {
    expect(() => resolveCandidateFrontendIdentity(env({ ...overrides }), [...argv], 'D:/repo/frontend')).toThrow(message)
  })

  it('树不一致或工作树有受跟踪改动时拒绝', () => {
    execFileSync.mockReset().mockReturnValueOnce(`${'f'.repeat(40)}\n`).mockReturnValueOnce('')
    expect(() => resolveCandidateFrontendIdentity(env(), [], 'D:/repo/frontend')).toThrow('身份不符')
    execFileSync.mockReset().mockReturnValueOnce(`${OID}\n`).mockReturnValueOnce(' M src/main.ts')
    expect(() => resolveCandidateFrontendIdentity(env(), [], 'D:/repo/frontend')).toThrow('受跟踪改动')
  })

  it('监听后的实际端口不符会退出；相符不退出', () => {
    const emitter = new EventEmitter() as EventEmitter & { address: () => { port: number } }
    let port = 3093
    emitter.address = () => ({ port })
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never)
    const plugin = candidatePortGuard(3093)
    ;(plugin.configureServer as Function)({ httpServer: emitter })
    emitter.emit('listening')
    expect(exit).not.toHaveBeenCalled()
    port = 3030
    ;(plugin.configureServer as Function)({ httpServer: emitter })
    emitter.emit('listening')
    expect(exit).toHaveBeenCalledWith(1)
    exit.mockRestore()
  })
})
