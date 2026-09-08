import { describe, expect, it } from 'vitest'
import {
  isAmbientFailedResponse,
  isExemptFailedResponse,
  partitionConsoleErrors,
  unexplainedResourceFailures,
} from './_helpers/pacNetworkGate'

describe('PAC network console gate', () => {
  it('allows OnlyOffice / favicon ambient failures only', () => {
    expect(
      isAmbientFailedResponse({
        status: 404,
        url: 'https://documentserver.example/web-apps/apps/api/documents/api.js',
      }),
    ).toBe(true)
    expect(isAmbientFailedResponse({ status: 404, url: 'http://localhost:3030/favicon.ico' })).toBe(
      true,
    )
    expect(
      isAmbientFailedResponse({
        status: 500,
        url: 'http://127.0.0.1:9980/api/workpapers/x/render-config',
      }),
    ).toBe(false)
    expect(
      isAmbientFailedResponse({
        status: 404,
        url: 'http://localhost:3030/assets/missing-chunk.js',
      }),
    ).toBe(false)
  })

  it('names concurrent guidance WIP as the only first-party exemption', () => {
    expect(
      isExemptFailedResponse({
        status: 500,
        url: 'http://localhost:3030/api/workpapers/abc/guidance',
      }),
    ).toBe(true)
    expect(
      isExemptFailedResponse({
        status: 404,
        url: 'http://localhost:3030/api/workpapers/abc/guidance?sheet_name=x',
      }),
    ).toBe(true)
    expect(
      isExemptFailedResponse({
        status: 500,
        url: 'http://localhost:3030/api/workpapers/abc/render-config',
      }),
    ).toBe(false)
  })

  it('partitions console messages and never treats first-party failures as ambient', () => {
    const parts = partitionConsoleErrors([
      'ResizeObserver loop limit exceeded',
      'Failed to load resource: the server responded with a status of 500 (Internal Server Error)',
      'TypeError: x is not a function\n    at foo',
      'Random console error from app',
    ])
    expect(parts.resourceErrors).toHaveLength(1)
    expect(parts.pageErrors).toHaveLength(1)
    expect(parts.other).toEqual(['Random console error from app'])
  })

  it('RED when failed response is first-party even if console is vague', () => {
    const bad = unexplainedResourceFailures(4, [
      { status: 500, url: 'http://127.0.0.1:9980/api/health' },
      { status: 404, url: 'https://oo.example/web-apps/apps/api/documents/api.js' },
    ])
    expect(bad).toEqual([{ status: 500, url: 'http://127.0.0.1:9980/api/health' }])
  })

  it('GREEN when only ambient / named guidance WIP accompany resource console noise', () => {
    expect(
      unexplainedResourceFailures(2, [
        { status: 404, url: 'https://documentserver/web-apps/apps/api/documents/api.js' },
        { status: 500, url: 'http://localhost:3030/api/workpapers/x/guidance' },
      ]),
    ).toEqual([])
  })

  it('RED when resource console fires with zero attributed responses', () => {
    expect(unexplainedResourceFailures(1, [])).toEqual([
      { status: 0, url: '<unattributed-resource-console-error>' },
    ])
  })
})
