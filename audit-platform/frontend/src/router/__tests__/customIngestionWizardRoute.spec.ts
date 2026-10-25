/**
 * 自定义模板摄取向导路由接线守卫。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure Task 12
 * Requirements: 1.6, 9.1
 *
 * 🔴 判据是「真实 router 实例的解析结果」，不是「index.ts 里 grep 到字符串」。
 * 要防的真实故障是**路由压根没注册**：Task 12 曾勾 [x]，而
 * `grep CustomIngestionWizard src/router` = 0 命中，页面永远打不开。
 * 变异实测：删掉路由块 → 本文件 3 条全红；grep 式判据则挡不住。
 *
 * ⚠️ 顺序无关：vue-router 4 按路径**特异性打分**匹配，静态段优先于动态段，
 * 所以把 'ingest' 挪到 ':id/edit' 之后**不会**改变解析结果（已变异实测确认）。
 * 下面那条 `not.toBe('CustomTemplateEdit')` 因此不是在防顺序，而是防
 * 「name 写错 / 指到编辑器组件」这类接线错误。
 */
import { describe, expect, it } from 'vitest'

import router from '@/router/index'

const INGEST_PATH = '/extension/custom-templates/ingest'

describe('custom ingestion wizard route', () => {
  it('resolves the ingest path to the wizard, not to the :id/edit dynamic segment', () => {
    const resolved = router.resolve(INGEST_PATH)

    expect(resolved.name).toBe('CustomIngestionWizard')
    // 反向断言：这条是本守卫真正要防的故障形态
    expect(resolved.name).not.toBe('CustomTemplateEdit')
    expect(resolved.matched.length).toBeGreaterThan(0)
  })

  it('lazily loads a real component module for the wizard route', async () => {
    const resolved = router.resolve(INGEST_PATH)
    const leaf = resolved.matched[resolved.matched.length - 1]
    const loader = leaf.components?.default

    expect(typeof loader).toBe('function')
    const mod = await (loader as () => Promise<{ default: unknown }>)()
    expect(mod?.default).toBeTruthy()
  })

  it('keeps sibling static and dynamic custom-template routes intact', () => {
    expect(router.resolve('/extension/custom-templates').name).toBe('CustomTemplateList')
    expect(router.resolve('/extension/custom-templates/new').name).toBe('CustomTemplateNew')
    // 真实 id 仍走编辑器：证明插入静态段没有夺走动态段的正常匹配
    expect(router.resolve('/extension/custom-templates/abc123/edit').name).toBe(
      'CustomTemplateEdit',
    )
  })
})
