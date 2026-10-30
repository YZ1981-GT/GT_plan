/**
 * WorkpaperEditor 壳的接线（spec procedure-chain-hardening-and-java-contracts R1 / R2 / R9 / R10）。
 * 行为由各组合式函数的用例覆盖；这里只钉住壳把它们接上了：模板按 SFC AST 查，脚本先去掉注释再查。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'

const SRC = readFileSync(resolve(__dirname, '../../WorkpaperEditor.vue'), 'utf-8')
const { descriptor } = parse(SRC)
const SCRIPT = (descriptor.scriptSetup?.content ?? '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
  .replace(/\s+/g, ' ')

function findElement(node: any, tag: string): any {
  if (node?.type === 1 && node.tag === tag) return node
  for (const child of node?.children ?? []) {
    const hit = findElement(child, tag)
    if (hit) return hit
  }
  return null
}

describe('WorkpaperEditor 接线', () => {
  it('Univer 核心在归类加载完才挂，取到的详情交回壳（R1）', () => {
    const core = findElement(descriptor.template!.ast, 'UniverEditorCore')
    expect(core).toBeTruthy()
    const vIf = core.props.find((p: any) => p.type === 7 && p.name === 'if')
    expect(vIf?.exp?.content).toBe('modeResolved')
    const onDetail = core.props.find((p: any) => p.type === 7 && p.name === 'on' && p.arg?.content === 'update:wp-detail')
    expect(onDetail?.exp?.content).toBe('onCoreWpDetail')
    expect(SCRIPT).toContain('const onCoreWpDetail = (d: WorkpaperDetail) => { wpDetail.value = d }')
    // 置真在归类加载之后
    const load = SCRIPT.indexOf('await wpClassification.load()')
    expect(load).toBeGreaterThan(0)
    expect(SCRIPT.indexOf('modeResolved.value = true', load)).toBeGreaterThan(load)
  })

  it('可编辑时才取锁（R2）', () => {
    expect(SCRIPT).toMatch(/useEditingLock\(\{ resourceId: computed\(\(\) => wpId\.value \|\| ''\), enabled: canEdit, \}\)/)
  })

  it('前置横幅按当前底稿编码 getter 请求（R9）', () => {
    expect(SCRIPT).toContain('usePrerequisiteStatus(() => projectId.value, () => prerequisiteWpCode(wpDetail.value?.wp_code))')
  })

  it('能力快照走 useShellCapability（R10）', () => {
    expect(SCRIPT).toContain('useShellCapability({ wpId, projectId, activeSheetContext })')
    expect(SCRIPT).not.toContain('fetchWorkpaperCapabilitySnapshot')
  })

  it('壳的辅助请求失败不弹全局提示：Univer 目录（R10）', () => {
    expect(SCRIPT).toContain('`/api/workpapers/${requestedWpId}/render-config`, { _silent: true, _dedupe: false } as any,')
  })

  it('壳不再自带一份 render-config：侧栏 decision_trace 读 GtWpRenderer / Univer 目录（spec platform-perf-hotspots R4）', () => {
    expect(SCRIPT).not.toContain('useWpRenderer(')
    // 两项事实的取法在 useEditorRendererFacts（行为用例见 useEditorRendererFacts.spec.ts），壳只负责接线
    expect(SCRIPT).toContain('const { sidePanelDecisionTrace, guidanceContextReady } = useEditorRendererFacts({ useHtmlRenderer, wpRendererRef, univerCatalog, univerSheetIdentityReady, activeSheetContext })')
    // Univer 目录请求顺带记下 decision_trace（原先壳为此单独再取一份 render-config）
    expect(SCRIPT).toContain('univerCatalog.value = { wpCode: config?.wp_code ?? null, decisionTrace: config?.decision_trace ?? null }')
    const sidePanel = findElement(descriptor.template!.ast, 'WorkpaperSidePanel')
    const trace = sidePanel.props.find((p: any) => p.type === 7 && p.name === 'bind' && p.arg?.content === 'decision-trace')
    expect(trace?.exp?.content).toBe('sidePanelDecisionTrace')
  })

  it('编制说明面板等页签上下文就绪再挂（R4：原先按空上下文先请求一次）', () => {
    const panel = findElement(descriptor.template!.ast, 'WpGuidancePanel')
    const vIf = panel.props.find((p: any) => p.type === 7 && p.name === 'if')
    expect(vIf?.exp?.content).toBe('wpDetail && projectYear != null && guidanceContextReady')
  })
})
