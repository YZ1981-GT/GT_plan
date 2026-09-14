/**
 * OcrAttachmentPicker.vue — 附件 OCR 部分失败容错 组件测试 (fast-check + @vue/test-utils)
 *
 * Spec: .kiro/specs/c-control-test-popup-enhance/  Task 8.2
 *
 * 覆盖：
 * - Property 6: OCR 部分失败容错
 *     对任意 N 个选中附件、其中 K 个 OCR 失败 (0 ≤ K < N)，系统 SHALL：
 *       1) 将 (N-K) 个成功附件的 OCR 文本纳入 AI 上下文（emit confirm.ocrText）
 *       2) 返回 K 个失败附件 ID 供告警展示（emit confirm.failedIds）
 *       3) 不因部分 OCR 失败阻塞 AI 生成（confirm 事件仍被 emit，流程完成）
 *   **Validates: Requirements 4.6**
 *
 * - Property 5 交叉引用（不重复 ocrContext.spec.ts 的完整套件）：
 *     验证真实组件 confirm 出的 ocrText 与 truncateOcrText 的拼接结果一致。
 *   **Validates: Requirements 4.4, 5.3**
 *
 * 被测真实组件（非替身）：OcrAttachmentPicker.vue + useOcrAttachmentCache。
 * 仅 mock 真实 HTTP 端点（@/utils/http）与 ElMessage：
 *   - GET /api/working-papers/{wpId}/attachments  → 可控附件列表
 *   - GET /api/attachments/{id}/download           → 返回携带 id 的 blob
 *   - POST /api/workpapers/{wpId}/d4/contract-ocr  → good id resolve / bad id REJECT
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import * as fc from 'fast-check'

// ── mock 必须 hoist 到 import 组件之前 ──
const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import OcrAttachmentPicker from '@/components/workpaper/cControlTest/OcrAttachmentPicker.vue'
import { truncateOcrText } from '@/composables/useOcrAttachmentCache'

// ─── 类型 ──────────────────────────────────────────────────────────────────────

interface Att {
  id: string
  file_name: string
  file_type: string
  file_size: number
  created_at: string
}

// ─── el-* 组件 stub（仅供渲染，不参与交互；交互直接走 vm） ────────────────────────

const stubs = {
  'el-dialog': {
    template: '<div class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue'],
  },
  'el-checkbox-group': {
    template: '<div class="el-checkbox-group"><slot /></div>',
    props: ['modelValue'],
  },
  'el-checkbox': {
    template: '<label class="el-checkbox"><slot /></label>',
    props: ['value', 'disabled', 'modelValue'],
  },
  'el-tooltip': { template: '<span class="el-tooltip"><slot /></span>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-empty': { template: '<div class="el-empty"><slot /></div>' },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['loading', 'disabled', 'type'],
  },
}

// ─── HTTP mock 装配：按 URL 路由 list / download / OCR ─────────────────────────────

/**
 * 配置 http mock：
 * - 列表端点返回 atts
 * - 下载端点返回内容为附件 id 的 blob，并记录 lastDownloadedId
 * - OCR 端点对 goodIds 内的 id resolve `OCR_{id}`，否则 REJECT（模拟单附件 OCR 失败）
 *
 * 下载→OCR 在组件 confirm 循环中严格顺序执行（await），故用 lastDownloadedId 关联
 * 当前 OCR 调用对应的附件，无交叉污染。
 */
function configureHttp(atts: Att[], goodIds: Set<string>): void {
  let lastDownloadedId = ''
  httpMock.get.mockReset()
  httpMock.post.mockReset()

  httpMock.get.mockImplementation(async (url: string) => {
    // 附件列表：/api/working-papers/{wpId}/attachments
    if (/\/attachments$/.test(url)) {
      return { data: atts }
    }
    // 附件下载：/api/attachments/{id}/download
    const m = url.match(/\/api\/attachments\/([^/]+)\/download/)
    if (m) {
      lastDownloadedId = m[1]
      return { data: new Blob([m[1]]) }
    }
    return { data: null }
  })

  httpMock.post.mockImplementation(async (_url: string) => {
    const id = lastDownloadedId
    if (goodIds.has(id)) {
      return { data: { extracted_fields: { full_text: `OCR_${id}` } } }
    }
    throw new Error(`OCR failed for ${id}`)
  })
}

/**
 * 挂载 picker、加载附件、全选后触发 confirm，返回 wrapper。
 * 直接调用暴露的 setup 绑定（handleOpen / selectedIds / handleConfirm），
 * 不依赖 el-dialog @open 事件（已 stub）。
 */
async function mountAndConfirm(atts: Att[], goodIds: Set<string>) {
  configureHttp(atts, goodIds)
  const ocrCache = new Map<string, string>()
  const wrapper = mount(OcrAttachmentPicker, {
    props: { wpId: 'wp-1', projectId: 'proj-1', visible: true, ocrCache },
    global: { stubs },
  })
  const vm = wrapper.vm as any
  await vm.handleOpen()
  await flushPromises()
  vm.selectedIds = atts.map((a) => a.id)
  await nextTick()
  await vm.handleConfirm()
  await flushPromises()
  return wrapper
}

function lastConfirmPayload(wrapper: any): { ocrText: string; failedIds: string[] } {
  const emitted = wrapper.emitted('confirm')
  expect(emitted).toBeTruthy()
  return emitted[emitted.length - 1][0]
}

/** 构造 N 个可 OCR 识别（.pdf）的附件，id = att-0 … att-{N-1} */
function makeAtts(n: number): Att[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `att-${i}`,
    file_name: `evidence-${i}.pdf`,
    file_type: 'application/pdf',
    file_size: 1024,
    created_at: '2026-01-01T00:00:00',
  }))
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: OCR 部分失败容错
// ═══════════════════════════════════════════════════════════════════════════════

describe('OcrAttachmentPicker — Property 6: OCR 部分失败容错', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── 代表性用例 ──

  it('N=3,K=1：成功附件文本入 context，失败 id 返回，流程不阻塞', async () => {
    const atts = makeAtts(3)
    // att-1 失败
    const goodIds = new Set(['att-0', 'att-2'])
    const wrapper = await mountAndConfirm(atts, goodIds)

    const payload = lastConfirmPayload(wrapper)
    expect(payload.ocrText).toBe(truncateOcrText(['OCR_att-0', 'OCR_att-2']))
    expect([...payload.failedIds].sort()).toEqual(['att-1'])
    wrapper.unmount()
  })

  it('K=0（全部成功）：无失败 id，全部文本入 context', async () => {
    const atts = makeAtts(4)
    const goodIds = new Set(atts.map((a) => a.id))
    const wrapper = await mountAndConfirm(atts, goodIds)

    const payload = lastConfirmPayload(wrapper)
    expect(payload.ocrText).toBe(
      truncateOcrText(['OCR_att-0', 'OCR_att-1', 'OCR_att-2', 'OCR_att-3']),
    )
    expect(payload.failedIds).toEqual([])
    wrapper.unmount()
  })

  it('首个附件失败也不阻塞：confirm 仍 emit，后续成功文本保留', async () => {
    const atts = makeAtts(3)
    // 第一个 att-0 失败
    const goodIds = new Set(['att-1', 'att-2'])
    const wrapper = await mountAndConfirm(atts, goodIds)

    const payload = lastConfirmPayload(wrapper)
    // confirm 被 emit → 未阻塞
    expect(wrapper.emitted('confirm')).toBeTruthy()
    expect(payload.ocrText).toBe(truncateOcrText(['OCR_att-1', 'OCR_att-2']))
    expect([...payload.failedIds].sort()).toEqual(['att-0'])
    wrapper.unmount()
  })

  // ── fast-check：对任意 N 与失败子集 (0 ≤ K < N) 容错契约恒成立 ──

  it('对任意 N 与失败子集满足部分失败容错契约', async () => {
    /** 生成 N∈[1,6] 的成功/失败标志数组，保证至少一个成功（K < N） */
    const arbPartition = fc.integer({ min: 1, max: 6 }).chain((n) =>
      fc.array(fc.boolean(), { minLength: n, maxLength: n }).map((flags) => {
        if (!flags.some((f) => f)) flags[0] = true // 至少一个成功 → 0 ≤ K < N
        return flags
      }),
    )

    await fc.assert(
      fc.asyncProperty(arbPartition, async (flags) => {
        const atts = makeAtts(flags.length)
        const goodIds = new Set(atts.filter((_, i) => flags[i]).map((a) => a.id))

        const wrapper = await mountAndConfirm(atts, goodIds)
        try {
          // 3) 不阻塞：confirm 事件必被 emit
          const payload = lastConfirmPayload(wrapper)

          // 1) 成功附件（按列表顺序）文本全部纳入
          const expectedTexts = atts
            .filter((_, i) => flags[i])
            .map((a) => `OCR_${a.id}`)
          expect(payload.ocrText).toBe(truncateOcrText(expectedTexts))

          // 2) 失败 id 恰为失败子集
          const expectedFailed = atts.filter((_, i) => !flags[i]).map((a) => a.id).sort()
          expect([...payload.failedIds].sort()).toEqual(expectedFailed)
        } finally {
          wrapper.unmount()
        }
      }),
      { numRuns: 24 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5 交叉引用（组件链路层，不重复 ocrContext.spec.ts 完整套件）
// ═══════════════════════════════════════════════════════════════════════════════

describe('OcrAttachmentPicker — Property 5 交叉引用：confirm.ocrText 与截断规则一致', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('多个成功附件：confirm.ocrText === truncateOcrText(成功文本, 顺序)', async () => {
    const atts = makeAtts(2)
    const goodIds = new Set(atts.map((a) => a.id))
    const wrapper = await mountAndConfirm(atts, goodIds)

    const payload = lastConfirmPayload(wrapper)
    expect(payload.ocrText).toBe(truncateOcrText(['OCR_att-0', 'OCR_att-1']))
    // 拼接分隔符契约（与 truncateOcrText 一致）
    expect(payload.ocrText).toBe('OCR_att-0\n---\nOCR_att-1')
    wrapper.unmount()
  })
})
