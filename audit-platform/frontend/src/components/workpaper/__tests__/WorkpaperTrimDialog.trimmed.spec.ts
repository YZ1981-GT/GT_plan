/**
 * WorkpaperTrimDialog — 已被程序裁剪的模板不预选、不可勾选（挂载测试）
 *
 * spec procedure-trim-generation-delegation-chain 需求 2：模板列表按保留范围标 `trimmed` / `trimmed_by`，
 * 生成前确认弹窗默认只勾「适用且未被裁剪」的，全选也跳过已裁剪的；列表读不到时弹窗内说明原因。
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.get } }))

import WorkpaperTrimDialog from '../WorkpaperTrimDialog.vue'

const LIVE: VueWrapper[] = []
afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
})
beforeEach(() => {
  mocks.get.mockReset()
})

const TEMPLATES = [
  { wp_code: 'H1', wp_name: '固定资产', cycle: 'H', applicable: true, trimmed: false, trimmed_by: null },
  { wp_code: 'H3', wp_name: '投资性房地产', cycle: 'H', applicable: true, trimmed: true, trimmed_by: 'H3' },
  { wp_code: 'H3-1', wp_name: '投资性房地产审定表', cycle: 'H', applicable: true, trimmed: true, trimmed_by: 'H3' },
  { wp_code: 'M4A', wp_name: '资本公积程序表', cycle: 'M', applicable: true, trimmed: true, trimmed_by: 'M4' },
  { wp_code: 'S1', wp_name: '专项', cycle: 'S', applicable: false, applicable_reason: '仅 A 类适用', trimmed: false },
]

async function mountDialog() {
  const w = mount(WorkpaperTrimDialog, {
    props: { modelValue: true, projectId: 'p1' },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(w)
  await flushPromises()
  await nextTick()
  // 循环分组默认折叠（子节点展开后才渲染）：逐个点开
  for (const group of Array.from(document.body.querySelectorAll('.el-tree > .el-tree-node > .el-tree-node__content'))) {
    ;(group as HTMLElement).click()
    await nextTick()
  }
  await flushPromises()
  return w
}

function confirmed(w: VueWrapper): string[] {
  const events = w.emitted('confirm') as unknown[][] | undefined
  return (events?.at(-1)?.[0] as string[]) ?? []
}

function confirmButton(): HTMLButtonElement {
  const btn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('确认生成'))
  if (!btn) throw new Error('未找到确认按钮')
  return btn as HTMLButtonElement
}

describe('WorkpaperTrimDialog 已裁剪模板', () => {
  it('默认只预选适用且未被裁剪的；已裁剪的标注跟随的程序行并禁用', async () => {
    mocks.get.mockResolvedValue(TEMPLATES)
    const w = await mountDialog()
    expect(mocks.get).toHaveBeenCalledWith(
      '/api/workpapers/template-list',
      expect.objectContaining({ params: { project_id: 'p1' }, _silent: true }),
    )
    const text = document.body.textContent || ''
    expect(text).toContain('H3 投资性房地产（已裁剪）')
    expect(text).toContain('H3-1 投资性房地产审定表（已裁剪：跟随 H3）')
    expect(text).toContain('M4A 资本公积程序表（已裁剪：跟随 M4）')
    expect(text).toContain('3 个底稿已在程序裁剪中标为不执行')
    const leaves = Array.from(document.body.querySelectorAll('.el-tree-node__content'))
      .filter((c) => c.querySelector('.el-tree-node__expand-icon.is-leaf'))
    const codeOf = (c: Element) => c.querySelector('.el-tree-node__label')?.textContent?.split(' ')[0]
    expect(leaves.map(codeOf)).toEqual(['H1', 'H3', 'H3-1', 'M4A', 'S1'])
    expect(leaves.filter((c) => c.querySelector('.el-checkbox.is-disabled')).map(codeOf)).toEqual(['H3', 'H3-1', 'M4A'])

    confirmButton().click()
    await flushPromises()
    expect(confirmed(w)).toEqual(['H1'])
  })

  it('全选跳过已裁剪的', async () => {
    mocks.get.mockResolvedValue(TEMPLATES)
    const w = await mountDialog()
    const selectAll = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.trim() === '全选')
    selectAll!.click()
    await flushPromises()
    confirmButton().click()
    await flushPromises()
    expect(confirmed(w).sort()).toEqual(['H1', 'S1'])
  })

  it('列表读不到（如裁剪结果不可用）⇒ 弹窗内说明原因、一个都不选', async () => {
    mocks.get.mockRejectedValue({
      response: { status: 503, data: { detail: { error: 'trim_scope_unavailable', message: '无法读取程序裁剪结果，已停止生成底稿，请稍后重试' } } },
    })
    const w = await mountDialog()
    expect(document.body.textContent).toContain('模板列表加载失败：无法读取程序裁剪结果，已停止生成底稿，请稍后重试')
    confirmButton().click()
    await flushPromises()
    expect(confirmed(w)).toEqual([])
  })
})
