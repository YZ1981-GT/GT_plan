/**
 * useLineageAutoFollow 单测 — deliverable-lineage-content-control Task 4.1
 *
 * 用可控 stub 连接器验证：
 * - Property 8：sec_ Tag 触发溯源
 * - Property 9：非 sec_ / 无 Tag 忽略
 * - Property 7：连接器不可用 fail-open（不抛、不触发）
 * - Property 10：dispose 解绑事件
 * 不依赖真实 OnlyOffice。
 */
import { describe, it, expect, vi } from 'vitest'
import {
  extractControlTag,
  isSectionTag,
  createLineageAutoFollow,
} from '../useLineageAutoFollow'

describe('extractControlTag', () => {
  it('提取多形态 Tag', () => {
    expect(extractControlTag({ Tag: 'sec_八_1' })).toBe('sec_八_1')
    expect(extractControlTag({ tag: 'x' })).toBe('x')
    expect(extractControlTag({ pr: { Tag: 'sec_五_1' } })).toBe('sec_五_1')
    expect(extractControlTag([{ Tag: 'sec_1' }])).toBe('sec_1')
  })
  it('无 Tag / 空 / null → null', () => {
    expect(extractControlTag(null)).toBeNull()
    expect(extractControlTag({})).toBeNull()
    expect(extractControlTag({ Tag: '' })).toBeNull()
    expect(extractControlTag({ Tag: 123 })).toBeNull()
  })
})

describe('isSectionTag', () => {
  it('sec_ 前缀为章节 Tag', () => {
    expect(isSectionTag('sec_八_1')).toBe(true)
    expect(isSectionTag('note_section_1')).toBe(false)
    expect(isSectionTag('')).toBe(false)
    expect(isSectionTag(null)).toBe(false)
  })
})

/** 构造可控 stub 连接器 + editorInstance。 */
function makeStubEditor() {
  let changeHandler: ((cc: any) => void) | null = null
  const connector = {
    attachEvent: vi.fn((name: string, cb: (cc: any) => void) => {
      if (name === 'onChangeContentControl') changeHandler = cb
    }),
    executeMethod: vi.fn((name: string, _args: any[], cb: (res: any) => void) => {
      if (name === 'GetCurrentContentControl') cb({ Tag: 'sec_五_1' })
    }),
    detachEvent: vi.fn(),
  }
  const editorInstance = { createConnector: vi.fn(() => connector) }
  return {
    editorInstance,
    connector,
    fireChange: (cc: any) => changeHandler?.(cc),
  }
}

describe('createLineageAutoFollow', () => {
  it('Property 8：sec_ Tag 变化触发溯源回调', () => {
    const { editorInstance, connector, fireChange } = makeStubEditor()
    const onSectionTag = vi.fn()
    const follow = createLineageAutoFollow(editorInstance, onSectionTag)

    expect(connector.attachEvent).toHaveBeenCalledWith(
      'onChangeContentControl',
      expect.any(Function),
    )
    fireChange({ Tag: 'sec_八_1' })
    expect(onSectionTag).toHaveBeenCalledWith('sec_八_1')
    follow.dispose()
  })

  it('Property 9：非 sec_ / 无 Tag 忽略', () => {
    const { editorInstance, fireChange } = makeStubEditor()
    const onSectionTag = vi.fn()
    createLineageAutoFollow(editorInstance, onSectionTag)

    fireChange({ Tag: 'note_section_1' })
    fireChange(null)
    fireChange({})
    expect(onSectionTag).not.toHaveBeenCalled()
  })

  it('queryCurrent：GetCurrentContentControl 命中 sec_ → 触发', () => {
    const { editorInstance, connector } = makeStubEditor()
    const onSectionTag = vi.fn()
    const follow = createLineageAutoFollow(editorInstance, onSectionTag)

    follow.queryCurrent()
    expect(connector.executeMethod).toHaveBeenCalledWith(
      'GetCurrentContentControl',
      [],
      expect.any(Function),
    )
    expect(onSectionTag).toHaveBeenCalledWith('sec_五_1')
  })

  it('Property 10：dispose 解绑事件', () => {
    const { editorInstance, connector } = makeStubEditor()
    const follow = createLineageAutoFollow(editorInstance, vi.fn())
    follow.dispose()
    expect(connector.detachEvent).toHaveBeenCalledWith('onChangeContentControl')
  })

  it('Property 7：无 createConnector → fail-open 空操作', () => {
    const onSectionTag = vi.fn()
    const follow = createLineageAutoFollow({}, onSectionTag)
    expect(() => follow.queryCurrent()).not.toThrow()
    expect(() => follow.dispose()).not.toThrow()
    expect(onSectionTag).not.toHaveBeenCalled()
  })

  it('Property 7：createConnector 抛错 → fail-open 空操作', () => {
    const editorInstance = {
      createConnector: vi.fn(() => {
        throw new Error('connector unavailable')
      }),
    }
    const onSectionTag = vi.fn()
    const follow = createLineageAutoFollow(editorInstance, onSectionTag)
    expect(() => follow.queryCurrent()).not.toThrow()
    expect(() => follow.dispose()).not.toThrow()
    expect(onSectionTag).not.toHaveBeenCalled()
  })
})
