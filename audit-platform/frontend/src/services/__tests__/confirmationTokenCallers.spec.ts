/**
 * 后端要求二次确认令牌的接口，前端每个调用方都先确认再带令牌（spec attachment-archive-and-a-class-evidence 需求 4.3）。
 *
 * 改造前前端没有一处带 `X-Confirmation-Token`：启动归档与签字恒 403。类型上令牌参数已必填，这里再钉两件类型管不到的事：
 * ① 调用这些接口的文件都从 `utils/passwordConfirm` 取令牌（不是传个空串糊过去）；② 接口确实把令牌放进请求头。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

vi.mock('@/utils/http', () => ({ default: { post: vi.fn(() => Promise.resolve({ data: { ok: 1 } })), get: vi.fn() } }))

import http from '@/utils/http'
import { signDocument } from '@/services/signatureApi'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const GUARDED_CALLS = /\b(signDocument|startArchiveOrchestrate|retryArchiveJob)\s*\(/

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (name === 'node_modules' || name === '__tests__') continue
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(vue|ts)$/.test(name)) out.push(p)
  }
  return out
}

describe('二次确认令牌调用方', () => {
  beforeEach(() => vi.clearAllMocks())

  it('调用方文件都从 passwordConfirm 取令牌', () => {
    const callers = walk(SRC).filter((f) => {
      const src = readFileSync(f, 'utf-8')
      return GUARDED_CALLS.test(src.replace(/export async function \w+/g, ''))
    }).map((f) => relative(SRC, f).replace(/\\/g, '/'))
    expect(callers.sort()).toEqual(['views/ArchiveWizard.vue', 'views/PartnerDashboard.vue', 'views/PartnerSignDecision.vue'])
    for (const f of callers) {
      const src = readFileSync(join(SRC, f), 'utf-8')
      expect(src, f).toContain("from '@/utils/passwordConfirm'")
      expect(src, f).toMatch(/requestConfirmationToken\(/)
    }
  })

  it('signDocument 把令牌放进 X-Confirmation-Token', async () => {
    await signDocument({ object_type: 'audit_report', object_id: 'r', signer_id: 'u', signature_level: 'l1' }, 'tok')
    expect(http.post).toHaveBeenCalledWith('/api/signatures/sign', expect.any(Object), {
      headers: { 'X-Confirmation-Token': 'tok' },
    })
  })
})
