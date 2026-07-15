import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as fc from 'fast-check'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: mocks.get } }))

import { useDisclosureCapabilities } from '../useDisclosureCapabilities'

describe('Feature: advanced-query-disclosure-integration-hardening, Property P12', () => {
  beforeEach(() => mocks.get.mockReset())

  it('historical_upload=false 时统一禁用并始终给出中文理由', async () => {
    await fc.assert(fc.asyncProperty(
      fc.option(fc.string(), { nil: undefined }),
      async (reason) => {
        mocks.get.mockResolvedValueOnce({ data: {
          advanced_query: true,
          disclosure_writeback: true,
          historical_upload: false,
          historical_upload_reason: reason,
        } })
        const capability = useDisclosureCapabilities({ autoLoad: false })
        await capability.loadCapabilities()
        expect(mocks.get).toHaveBeenCalledWith(
          '/api/disclosure-notes/capabilities',
          { _silent: true },
        )
        expect(capability.historicalUploadDisabled.value).toBe(true)
        expect(capability.historicalUploadReason.value).toMatch(/[\u4e00-\u9fff]/)
      },
    ), { numRuns: 20 })
  })

  it('能力发现失败时 fail-closed，不伪造可用入口', async () => {
    mocks.get.mockRejectedValueOnce(new Error('offline'))
    const capability = useDisclosureCapabilities({ autoLoad: false })
    await capability.loadCapabilities()
    expect(capability.capabilities.value.historical_upload).toBe(false)
    expect(capability.historicalUploadDisabled.value).toBe(true)
    expect(capability.historicalUploadReason.value).toContain('禁用')
  })
})
