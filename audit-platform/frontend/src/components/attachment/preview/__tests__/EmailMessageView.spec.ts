import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EmailMessageView from '../email/EmailMessageView.vue'
import type { ParsedEmail } from '../email/emailParser'
import { PreviewResourceScope } from '../previewResourceScope'

function email(overrides: Partial<ParsedEmail> = {}): ParsedEmail {
  return {
    from: 'sender@example.com',
    to: ['recipient@example.com'],
    cc: [],
    subject: '审计证据',
    date: null,
    html: null,
    text: 'plain body',
    attachments: [],
    inlineParts: [],
    ambiguousCids: [],
    ...overrides,
  }
}

const png = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0,
])

function cidEmail(subject: string, cid: string): ParsedEmail {
  return email({
    subject,
    html: `<p>${subject}</p><img src="cid:${cid}">`,
    inlineParts: [{
      canonicalCid: cid,
      declaredMime: 'image/png',
      bytes: png.buffer,
    }],
  })
}

describe('EmailMessageView resource ownership', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('CID URL 纳入 PreviewResourceScope，换邮件与卸载时成对释放', async () => {
    if (typeof URL.revokeObjectURL !== 'function') {
      ;(URL as any).revokeObjectURL = () => undefined
    }
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const scope = new PreviewResourceScope()
    let sequence = 0
    const wrapper = mount(EmailMessageView, {
      props: {
        email: cidEmail('first', 'first@x'),
        createObjectUrl: () => scope.trackObjectUrl(`blob:cid-${++sequence}`),
        releaseObjectUrl: (url: string) => scope.releaseObjectUrl(url),
      },
    })
    await nextTick()
    expect(scope.snapshot().objectUrls).toBe(1)
    expect(wrapper.find('iframe').attributes('srcdoc')).toContain('blob:cid-1')

    await wrapper.setProps({ email: cidEmail('second', 'second@x') })
    await nextTick()
    expect(scope.snapshot().objectUrls).toBe(1)
    expect(revoke).toHaveBeenCalledWith('blob:cid-1')
    expect(wrapper.find('iframe').attributes('srcdoc')).toContain('blob:cid-2')

    wrapper.unmount()
    expect(scope.snapshot().objectUrls).toBe(0)
    expect(revoke).toHaveBeenCalledWith('blob:cid-2')
  })

  it('跨邮件按当前安全正文复位 HTML/text mode，空 HTML 时禁用按钮', async () => {
    const wrapper = mount(EmailMessageView, { props: { email: email() } })
    await nextTick()
    expect(wrapper.find('[data-testid="email-text-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-toggle-html"]').attributes('disabled')).toBeDefined()

    await wrapper.setProps({ email: email({ subject: 'html-1', html: '<p>html one</p>' }) })
    await nextTick()
    expect(wrapper.find('[data-testid="email-html-frame"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-toggle-html"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-testid="email-toggle-text"]').trigger('click')
    expect(wrapper.find('[data-testid="email-text-body"]').exists()).toBe(true)
    await wrapper.setProps({ email: email({ subject: 'html-2', html: '<p>html two</p>' }) })
    await nextTick()
    expect(wrapper.find('[data-testid="email-html-frame"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
