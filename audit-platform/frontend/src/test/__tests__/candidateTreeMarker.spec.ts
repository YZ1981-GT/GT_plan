// @vitest-environment jsdom
/**
 * 候选前端树身份 marker（spec platform-global-display-settings-closure 13A / AC-25）。
 *
 * 守卫要点：
 * 1. 普通模式（Vite 未注入）**不抛 ReferenceError**、不改 DOM —— 这是「共享 dev server
 *    与 start-dev.bat 行为不变」的硬条件，用「直接引用未声明全局」的写法必红。
 * 2. 候选模式三个 data 属性都要写，且 `matched` 必须是真实比较结果，
 *    不能只写 expected/actual 就让验收脚本以为一致。
 * 3. 非法 OID 不产生 marker（避免把畸形值当身份证据）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const OID_A = '0123456789abcdef0123456789abcdef01234567'
const OID_B = 'fedcba9876543210fedcba9876543210fedcba98'

type GlobalWithMarker = typeof globalThis & {
  __GT_CANDIDATE_TREE_EXPECTED__?: string
  __GT_CANDIDATE_TREE_ACTUAL__?: string
}

function setInjected(expected?: string, actual?: string) {
  const g = globalThis as GlobalWithMarker
  if (expected === undefined) delete g.__GT_CANDIDATE_TREE_EXPECTED__
  else g.__GT_CANDIDATE_TREE_EXPECTED__ = expected
  if (actual === undefined) delete g.__GT_CANDIDATE_TREE_ACTUAL__
  else g.__GT_CANDIDATE_TREE_ACTUAL__ = actual
}

async function load() {
  vi.resetModules()
  return await import('../../utils/candidateTreeMarker')
}

beforeEach(() => {
  setInjected()
  delete document.documentElement.dataset.gtCandidateTreeExpected
  delete document.documentElement.dataset.gtCandidateTreeActual
  delete document.documentElement.dataset.gtCandidateTreeMatched
})

afterEach(() => {
  setInjected()
})

describe('候选前端树身份 marker', () => {
  it('普通模式：不抛错、返回 null、DOM 未改', async () => {
    const mod = await load()
    expect(mod.readCandidateTreeIdentity()).toBeNull()
    expect(mod.installCandidateTreeMarker()).toBeNull()
    expect(document.documentElement.dataset.gtCandidateTreeExpected).toBeUndefined()
    expect(document.documentElement.dataset.gtCandidateTreeActual).toBeUndefined()
    expect(document.documentElement.dataset.gtCandidateTreeMatched).toBeUndefined()
  })

  it('只注入一侧时视为非候选模式（不写半截身份）', async () => {
    setInjected(OID_A, undefined)
    const mod = await load()
    expect(mod.readCandidateTreeIdentity()).toBeNull()
    mod.installCandidateTreeMarker()
    expect(document.documentElement.dataset.gtCandidateTreeExpected).toBeUndefined()
  })

  it('候选模式一致：写三个属性且 matched=true', async () => {
    setInjected(OID_A, OID_A)
    const mod = await load()
    const identity = mod.installCandidateTreeMarker()
    expect(identity).toEqual({ expected: OID_A, actual: OID_A, matched: true })
    expect(document.documentElement.dataset.gtCandidateTreeExpected).toBe(OID_A)
    expect(document.documentElement.dataset.gtCandidateTreeActual).toBe(OID_A)
    expect(document.documentElement.dataset.gtCandidateTreeMatched).toBe('true')
  })

  it('候选模式不一致：matched=false（不把存在当一致）', async () => {
    setInjected(OID_A, OID_B)
    const mod = await load()
    const identity = mod.installCandidateTreeMarker()
    expect(identity).toEqual({ expected: OID_A, actual: OID_B, matched: false })
    expect(document.documentElement.dataset.gtCandidateTreeMatched).toBe('false')
  })

  it.each([
    ['短 OID', '0123456'],
    ['大写十六进制', OID_A.toUpperCase()],
    ['非十六进制', 'z'.repeat(40)],
    ['41 位', `${OID_A}0`],
  ])('非法 OID（%s）不产生 marker', async (_label, bad) => {
    setInjected(bad, bad)
    const mod = await load()
    expect(mod.readCandidateTreeIdentity()).toBeNull()
    mod.installCandidateTreeMarker()
    expect(document.documentElement.dataset.gtCandidateTreeExpected).toBeUndefined()
  })
})

describe('treeOid 工具', () => {
  it('只接受 40 位小写十六进制', async () => {
    const { isTreeOid, TREE_OID_RE } = await import('../../utils/treeOid')
    expect(isTreeOid(OID_A)).toBe(true)
    expect(isTreeOid(OID_A.toUpperCase())).toBe(false)
    expect(isTreeOid(null)).toBe(false)
    expect(isTreeOid(undefined)).toBe(false)
    expect(TREE_OID_RE.test(`${OID_A} `)).toBe(false)
  })
})
