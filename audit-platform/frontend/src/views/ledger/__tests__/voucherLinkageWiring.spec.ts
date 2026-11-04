/**
 * 凭证联动的页面级接线（spec voucher-workflow-linkage-lineage-closure；源码判据，大页面守卫的惯例）
 *
 * 序时账穿透（5 千多行）、底稿渲染器、底稿编辑器、试算表、合并页太大，不整页挂载；它们用到的组件另有行为用例，
 * 这里只钉「页面把组件接上了、传对了值」（注释先剥掉，写在注释里的旧代码不算）：
 * - 序时账：「抽中本凭证」按钮与处理函数已删（R3.1）；凭证层标签接查询状态、重试、打开底稿（R3.3）；
 *   打开底稿走统一地址、带返回地址（R3.2 / R3.5）；
 * - 底稿渲染器挂待导入提示（R3.6）；
 * - 底稿编辑器返回按钮按返回地址显示文案、回原穿透现场，未保存只确认一次（R3.7）；
 * - 试算表 / 合并页行数据溯源带年度，子源失败如实提示（R8.1 / R8.3）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { stripHtmlComments, stripJsComments } from '@/__tests__/_helpers/frontendSourceScan'

const SRC_ROOT = resolve(__dirname, '../../..')

function sfc(rel: string) {
  const text = readFileSync(resolve(SRC_ROOT, rel), 'utf-8')
  const template = stripHtmlComments(text.slice(text.indexOf('<template>'), text.lastIndexOf('</template>')))
  const script = stripJsComments([...text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join('\n'))
  return { template, script }
}

/** 模板里某组件的全部开始标签（属性值里的 `>` / `=>` 不截断） */
function openTags(template: string, name: string): string[] {
  const tags = template.match(/<[A-Za-z][\w-]*(?:[^>"]|"[^"]*")*>/g) || []
  return tags.filter((t) => new RegExp(`^<${name}[\\s/>]`).test(t))
}

/** 脚本里某函数的函数体：参数表按圆括号配平（参数类型里可能有花括号），函数体按花括号配平 */
function functionBody(script: string, name: string): string {
  const at = script.search(new RegExp(`function ${name}\\s*\\(`))
  if (at < 0) return ''
  let i = script.indexOf('(', at)
  for (let depth = 0; i < script.length; i++) {
    if (script[i] === '(') depth++
    else if (script[i] === ')' && --depth === 0) break
  }
  const open = script.indexOf('{', i)
  for (let j = open, depth = 0; j < script.length; j++) {
    if (script[j] === '{') depth++
    else if (script[j] === '}' && --depth === 0) return script.slice(open, j + 1)
  }
  return ''
}

describe('序时账穿透（LedgerPenetration.vue）', () => {
  const { template, script } = sfc('views/LedgerPenetration.vue')

  it('「抽中本凭证」按钮与处理函数已删：挂凭只经「挂凭到底稿」', () => {
    expect(template).not.toContain('抽中本凭证')
    expect(script).not.toMatch(/\bsampleCurrentVoucher\b/)
    expect(script).not.toMatch(/\battachVoucher\s*\(/)
    expect(template).toContain('@click="attachCurrentVoucher"')
  })

  it('凭证层标签接查询状态、重试与打开底稿（不经挂凭结果，不带来源标记）', () => {
    const tags = openTags(template, 'VoucherLinkTags')
    expect(tags).toHaveLength(1)
    expect(tags[0]).toContain(':link-status="voucherLinks.linkStatusOf(currentVoucherEvidenceKey)"')
    expect(tags[0]).toContain('@retry-links="voucherLinks.refresh([currentVoucherEvidenceKey])"')
    expect(tags[0]).toContain('@open-wp="(id: string) => onNavigateToWp({ workpaperId: id }, false)"')
  })

  it('挂凭结果「打开底稿」与标签都走统一地址并带返回地址', () => {
    const dialogs = openTags(template, 'AttachVoucherToWpDialog')
    expect(dialogs).toHaveLength(1)
    expect(dialogs[0]).toContain('@navigate-to-wp="onNavigateToWp"')
    const body = functionBody(script, 'onNavigateToWp')
    expect(body).toContain('workpaperRouteFromLedger(projectId.value, payload.workpaperId, { returnTo: route.fullPath, fromAttach })')
    expect(script).toMatch(/function onNavigateToWp\(payload: \{ workpaperId: string \}, fromAttach = true\)/)
  })
})

describe('底稿渲染器（GtWpRenderer.vue）', () => {
  it('挂待导入提示，传项目、底稿与编制年度', () => {
    const tags = openTags(sfc('components/workpaper/GtWpRenderer.vue').template, 'VoucherAttachPendingBanner')
    expect(tags).toHaveLength(1)
    for (const attr of [':project-id="runtimeProjectId"', ':workpaper-id="wpId"', ':year="preparationYear"']) {
      expect(tags[0]).toContain(attr)
    }
  })
})

describe('底稿编辑器（WorkpaperEditor.vue）', () => {
  const { template, script } = sfc('views/WorkpaperEditor.vue')

  it('两个工具栏的返回按钮都按返回地址显示文案', () => {
    const backs = template.match(/<el-button[^>]*@click="goBack"[^>]*>([^<]*)<\/el-button>/g) || []
    expect(backs).toHaveLength(2)
    for (const b of backs) expect(b).toContain('{{ returnLabelOf(route.query.returnTo) }}')
  })

  it('返回回原穿透现场；未保存确认只走离开守卫（不再先弹一次原生确认）', () => {
    const body = functionBody(script, 'goBack')
    expect(body).toContain("router.push(safeReturnTo(route.query.returnTo) ?? { name: 'WorkpaperList', params: { projectId: projectId.value } })")
    expect(body).not.toMatch(/\bconfirm\s*\(/)
    expect(script).toMatch(/onBeforeRouteLeave\(/)
  })
})

describe('行数据溯源（TrialBalance.vue / ConsolidationIndex.vue）', () => {
  it('试算表：带审计年度；查无结果时有子源失败就说失败原因', () => {
    const body = functionBody(sfc('views/TrialBalance.vue').script, 'onTbCtxCellTrace')
    expect(body).toMatch(/object_type: 'tb_row'[^}]*\.\.\.\(year\.value != null \? \{ year: year\.value \} : \{\}\)/)
    expect(body).toContain("ElMessage[data?.errors?.length ? 'warning' : 'info'](data?.errors?.[0]?.message || '该数字暂无溯源信息')")
  })

  it('合并页：试算表行带页面年度；子源失败同样如实提示', () => {
    const body = functionBody(sfc('views/ConsolidationIndex.vue').script, 'onConsolCtxCellTrace')
    expect(body).toContain("...(objectType === 'tb_row' && year.value != null ? { year: year.value } : {})")
    expect(body).toContain("ElMessage[data?.errors?.length ? 'warning' : 'info'](data?.errors?.[0]?.message || '该数字暂无溯源信息')")
  })

  it('判据自检：函数体按配平截取，取不到即为空（不会误用整段脚本）', () => {
    expect(functionBody('function a(x: { y: number }) { if (x) { return 1 } }\nfunction b() {}', 'a')).toBe('{ if (x) { return 1 } }')
    expect(functionBody('const z = 1', 'missing')).toBe('')
  })
})
