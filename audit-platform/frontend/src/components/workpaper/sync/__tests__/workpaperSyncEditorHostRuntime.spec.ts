/**
 * `workpaperSyncEditorHostRuntime` 的宿主侧判据。
 *
 * 本文件在 spec `onlyoffice-sheet-open-via-published-artifact` 的 task 3.2 建立：
 * 该模块此前**没有专属 spec**（`buildDocEditorConfig` 只在
 * `WorkpaperSyncEditorHost.spec.ts` / `task69IndependentRegression.spec.ts` 被间接用到），
 * 所以「descriptor 的视图身份有没有真的变成 actionLink」这条判据无处可放。
 */
import { describe, expect, it } from 'vitest'

import { buildDocEditorConfig, hostRefusal } from '../workpaperSyncEditorHostRuntime'

/** 最小可用 descriptor：只带 `buildDocEditorConfig` 真正读的字段。 */
function descriptor(over: Record<string, unknown> = {}): any {
  return {
    roomId: 'room-1',
    docKey: 'doc-key-1',
    generation: 1,
    representationId: 'rep-1',
    representationGeneration: 1,
    documentType: 'xlsx',
    documentScope: 'single_sheet',
    targetSheet: null,
    onlyofficeConfig: {
      document: { key: 'doc-key-1', fileType: 'xlsx' },
      editorConfig: { mode: 'edit', customization: { forcesave: false } },
    },
    ...over,
  }
}

const events = {} as any

describe('task 3.2：actionLink 注入（Requirement 3.3 / 3.4）', () => {
  it('single_sheet + targetSheet ⇒ 注入 actionLink（bookmark 指向该 sheet）', () => {
    const cfg = buildDocEditorConfig(
      descriptor({ targetSheet: '境外销售收入检查D4-26' }),
      events,
    ) as any
    expect(cfg.editorConfig.actionLink).toEqual({
      action: { type: 'bookmark', data: '境外销售收入检查D4-26' },
    })
  })

  it('single_sheet + targetSheet=null ⇒ 不注入（契约没声明 = 不定位）', () => {
    const cfg = buildDocEditorConfig(descriptor({ targetSheet: null }), events) as any
    expect('actionLink' in cfg.editorConfig).toBe(false)
  })

  it('whole_workbook ⇒ **必须不**注入 actionLink（整册要显示全部 sheet tab）', () => {
    // 🔴 即便 targetSheet 有值也不注入：整册视图带定位会把其它 sheet 藏起来，
    // 而那正是 Requirement 3.4 禁止的形态。
    const cfg = buildDocEditorConfig(
      descriptor({ documentScope: 'whole_workbook', targetSheet: '随便一张' }),
      events,
    ) as any
    expect('actionLink' in cfg.editorConfig).toBe(false)
  })

  it('服务端已给 actionLink 时不覆盖（两份定位不一致时以服务端为准）', () => {
    const cfg = buildDocEditorConfig(
      descriptor({
        targetSheet: '前端想定位的',
        onlyofficeConfig: {
          document: { key: 'doc-key-1' },
          editorConfig: {
            mode: 'edit',
            customization: { forcesave: false },
            actionLink: { action: { type: 'bookmark', data: '服务端给的' } },
          },
        },
      }),
      events,
    ) as any
    expect(cfg.editorConfig.actionLink.action.data).toBe('服务端给的')
  })

  it('缺 editorConfig 段时拒绝，且失败码已登记（不是裸 code_unregistered）', () => {
    let caught: any = null
    try {
      buildDocEditorConfig(
        descriptor({
          targetSheet: '某张表',
          onlyofficeConfig: { document: { key: 'doc-key-1' } },
        }),
        events,
      )
    } catch (e) {
      caught = e
    }
    expect(caught).not.toBeNull()
    expect(caught.code).toBe('editor_host_config_editor_missing')
    // 文案必须是人话（AC 11.x 禁止把裸英文标识符显示给用户）。
    expect(String(caught.message)).toContain('editorConfig')
  })

  it('注入不改变其它 config 段（document / customization 逐字节保留）', () => {
    const cfg = buildDocEditorConfig(
      descriptor({ targetSheet: '某张表' }),
      events,
    ) as any
    expect(cfg.document).toEqual({ key: 'doc-key-1', fileType: 'xlsx' })
    expect(cfg.editorConfig.mode).toBe('edit')
    expect(cfg.editorConfig.customization).toEqual({ forcesave: false })
    expect(cfg.width).toBe('100%')
    expect(cfg.height).toBe('100%')
  })

  it('返回的是纯对象（不含 Vue Proxy）—— 注入后仍是', () => {
    // 🔴 OO 会往 `document.token` 赋值，Proxy 会让它 -20（见 g4-* 证据）。
    const cfg = buildDocEditorConfig(descriptor({ targetSheet: '某张表' }), events) as any
    cfg.document.token = 'assigned-by-oo'
    expect(cfg.document.token).toBe('assigned-by-oo')
  })
})

describe('task 3.2：hostRefusal 码表登记', () => {
  it('editor_host_config_editor_missing 已登记（不是 unregistered 兜底）', () => {
    const err = hostRefusal('editor_host_config_editor_missing')
    expect(err.code).toBe('editor_host_config_editor_missing')
    expect(String(err.message)).not.toContain('未登记的失败码')
  })
})
