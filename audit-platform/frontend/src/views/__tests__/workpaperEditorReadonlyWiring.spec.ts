/**
 * 底稿编辑页把只读传给 HTML 渲染器（spec attachment-confirmation-evidence-loop 浏览器走查实测）
 *
 * 同一张底稿在第二个标签页打开：编辑锁冲突，横幅写「当前为只读模式（所有保存已禁用）」，但 GtWpRenderer 没有收到
 * readonly ⇒ 页面照样能改能存，函证附件抽屉照样能上传 / 解绑（两个标签页互相覆盖）。已归档项目同理。
 * Spec F FEAT-003 F6.2 追加 !canEdit：QC / EQCR 只有 review 级项目权限（canEdit=false），传只读。
 * 编辑页挂载代价过高（十几个 composable + 渲染配置），这里按源码核对接线（先剥注释），行为由浏览器走查覆盖。
 * 绑定式直接写在模板里（编辑页行数在棘轮上，见 workpaper-editor/__tests__/line-budget.spec.ts）。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { stripHtmlComments, stripJsComments } from '@/__tests__/_helpers/frontendSourceScan'

const SRC = readFileSync(resolve(__dirname, '../WorkpaperEditor.vue'), 'utf-8')
const template = stripHtmlComments(/<template>([\s\S]*)<\/template>/.exec(SRC)?.[1] ?? '')
const script = stripJsComments([...SRC.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join('\n'))
const rendererTag = /<GtWpRenderer\b[^>]*>/.exec(template)?.[0] ?? ''
const readonlyExpr = /\s:readonly="([^"]*)"/.exec(rendererTag)?.[1] ?? ''

describe('WorkpaperEditor → GtWpRenderer 只读接线', () => {
  it('GtWpRenderer 绑定 readonly', () => {
    expect(rendererTag, '找不到 GtWpRenderer 起始标签').not.toBe('')
    expect(readonlyExpr, 'GtWpRenderer 没有绑定 :readonly').not.toBe('')
  })

  it('只读统一来自 effectiveCanEdit，且包含权限、编辑锁、项目归档与底稿终态', () => {
    expect(readonlyExpr).toBe('!effectiveCanEdit')
    expect(script).toMatch(/const effectiveCanEdit = computed\([\s\S]*canEdit\.value[\s\S]*!editLock\.forcedReadonly\.value[\s\S]*!isArchived\.value[\s\S]*review_passed[\s\S]*archived/)
    expect(script).toMatch(/const \{[^}]*\bisArchived\b[^}]*\} = useAuditContext\(\)/)
    expect(script).toMatch(/const \{[^}]*\bcanEdit\b[^}]*\} = useAuditContext\(\)/)
  })
})
