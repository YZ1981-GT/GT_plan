/**
 * publication 管理页路由接线守卫。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure Task 16/20
 *
 * 🔴 判据是「真实 router 实例的解析结果」—— 与 ingest 页同一教训：Task 12 曾
 * 勾了 [x] 而 `grep CustomIngestionWizard src/router` 为 0 命中，页面永远打不开。
 * 本守卫因此解析真 router 并真实 import 组件模块。
 *
 * 另防：新增的静态段 `publications` 不得夺走 `:id/edit` 的正常匹配。
 */
import { describe, expect, it } from 'vitest'

import router from '@/router/index'

const PUBS_PATH = '/extension/custom-templates/publications'

describe('custom template publications route', () => {
  it('resolves the publications path to the publications page', () => {
    const resolved = router.resolve(PUBS_PATH)

    expect(resolved.name).toBe('CustomTemplatePublications')
    // 反向断言：本守卫真正要防的故障形态是指到别的页面
    expect(resolved.name).not.toBe('CustomTemplateEdit')
    expect(resolved.name).not.toBe('CustomIngestionWizard')
    expect(resolved.matched.length).toBeGreaterThan(0)
  })

  it('lazily loads a real component module', async () => {
    const resolved = router.resolve(PUBS_PATH)
    const leaf = resolved.matched[resolved.matched.length - 1]
    const loader = leaf.components?.default

    expect(typeof loader).toBe('function')
    const mod = await (loader as () => Promise<{ default: unknown }>)()
    expect(mod?.default).toBeTruthy()
  })

  it('does not steal the dynamic :id/edit route', () => {
    expect(router.resolve('/extension/custom-templates/abc123/edit').name).toBe(
      'CustomTemplateEdit',
    )
    // ingest 页也仍在
    expect(router.resolve('/extension/custom-templates/ingest').name).toBe(
      'CustomIngestionWizard',
    )
  })
})
