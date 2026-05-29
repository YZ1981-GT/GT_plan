/**
 * confirm.ts 单测 — V3 Req 4.1
 *
 * 验证 confirmDelete / confirmDangerous 扩展：
 * - 向后兼容（string 参数）
 * - 新签名（options 对象 + impact + recoverable + requireInputMatch）
 * - HTML 转义防注入
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ElMessageBox } from 'element-plus'
import {
  confirmDelete,
  confirmDangerous,
  type ConfirmDeleteOptions,
} from '../confirm'

describe('confirmDelete', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('向后兼容：传 string itemName 走简单消息分支', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDelete('该分录')

    expect(spy).toHaveBeenCalledTimes(1)
    const [msg, title, opts] = spy.mock.calls[0] as [string, string, any]
    expect(msg).toBe('确定删除该分录？')
    expect(title).toBe('删除确认')
    expect(opts.dangerouslyUseHTMLString).toBe(false)
    expect(opts.confirmButtonClass).toBe('el-button--danger')
  })

  it('无参数时使用默认提示', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDelete()

    expect(spy.mock.calls[0][0]).toBe('确定删除该记录？')
  })

  it('options.impact 启用 HTML 渲染并展示影响范围', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDelete({ name: '分录 RJE-001', impact: '影响 3 张底稿' })

    expect(spy).toHaveBeenCalled()
    const [html, title, opts] = spy.mock.calls[0] as [string, string, any]
    expect(opts.dangerouslyUseHTMLString).toBe(true)
    expect(html).toContain('分录 RJE-001')
    expect(html).toContain('影响 3 张底稿')
    expect(html).toContain('影响范围')
  })

  it('options.recoverable=true 显示回收站提示', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDelete({ name: '底稿 D2', recoverable: true })

    const [html] = spy.mock.calls[0] as unknown as [string]
    expect(html).toContain('删除后可在回收站恢复')
  })

  it('options.recoverable=false 显示不可恢复警告', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDelete({ name: '永久档案', recoverable: false })

    const [html] = spy.mock.calls[0] as unknown as [string]
    expect(html).toContain('此操作不可恢复')
  })

  it('HTML 特殊字符自动转义防注入', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    const opts: ConfirmDeleteOptions = {
      name: '<script>alert(1)</script>',
      impact: '影响 & 关联',
    }
    await confirmDelete(opts)

    const [html] = spy.mock.calls[0] as unknown as [string]
    expect(html).not.toContain('<script>alert(1)</script>')
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain('影响 &amp; 关联')
  })

  it('用户取消时 reject', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel')
    await expect(confirmDelete('该分录')).rejects.toBe('cancel')
  })
})

describe('confirmDangerous', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('向后兼容：(message, title) 两参形式', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDangerous('确定要操作？', '自定义标题')

    expect(spy).toHaveBeenCalledTimes(1)
    const [msg, title, opts] = spy.mock.calls[0] as [string, string, any]
    expect(msg).toBe('确定要操作？')
    expect(title).toBe('自定义标题')
    expect(opts.confirmButtonText).toBe('确定执行')
  })

  it('options 对象形式支持自定义按钮文字', async () => {
    const spy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)

    await confirmDangerous({
      message: '强制覆盖文件？',
      title: '覆盖确认',
      confirmText: '强制覆盖',
      cancelText: '保留',
    })

    const [, title, opts] = spy.mock.calls[0] as [string, string, any]
    expect(title).toBe('覆盖确认')
    expect(opts.confirmButtonText).toBe('强制覆盖')
    expect(opts.cancelButtonText).toBe('保留')
  })

  it('requireInputMatch 触发 prompt 校验对象名', async () => {
    const promptSpy = vi
      .spyOn(ElMessageBox, 'prompt')
      .mockResolvedValueOnce({ value: 'YG2101', action: 'confirm' } as any)

    await confirmDangerous({
      message: '确定要解除归档吗？',
      title: '解除归档',
      requireInputMatch: 'YG2101',
    })

    expect(promptSpy).toHaveBeenCalledTimes(1)
    const [, title, opts] = promptSpy.mock.calls[0] as [string, string, any]
    expect(title).toBe('解除归档')
    expect(opts.inputPattern).toBeInstanceOf(RegExp)
    // 校验正则正确转义特殊字符（这里没特殊字符，但匹配 YG2101 而非 YG2101X）
    expect(opts.inputPattern.test('YG2101')).toBe(true)
    expect(opts.inputPattern.test('YG2101X')).toBe(false)
  })

  it('requireInputMatch 含正则特殊字符时正确转义', async () => {
    const promptSpy = vi
      .spyOn(ElMessageBox, 'prompt')
      .mockResolvedValueOnce({ value: 'A.B(C)', action: 'confirm' } as any)

    await confirmDangerous({
      message: '危险',
      requireInputMatch: 'A.B(C)',
    })

    const [, , opts] = promptSpy.mock.calls[0] as [string, string, any]
    expect(opts.inputPattern.test('A.B(C)')).toBe(true)
    // ".".特殊字符不应匹配任何字符
    expect(opts.inputPattern.test('AXB(C)')).toBe(false)
  })

  it('用户取消 prompt 时向上抛出', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockRejectedValueOnce('cancel')

    await expect(
      confirmDangerous({ message: 'm', requireInputMatch: 'X' }),
    ).rejects.toBe('cancel')
  })
})
