import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import LedgerAppendResultPanel from '../LedgerAppendResultPanel.vue'
import {
  appendFormFields,
  buildIncrementalDetectBody,
  normalizeIncrementalRequest,
  voucherDiffEntries,
} from '../ledgerAppendResult'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (path: string) => readFileSync(resolve(ROOT, path), 'utf-8')

const stubs = {
  'el-alert': {
    template: '<div class="alert"><span>{{ title }}</span><slot name="title"/><slot/></div>',
    props: ['title', 'type', 'closable', 'showIcon'],
  },
}

describe('增量追加请求契约', () => {
  it('月份去重排序并生成后端预检字段', () => {
    const request = normalizeIncrementalRequest({
      year: 2025,
      strategy: 'overwrite',
      filePeriods: [12, 3, 12, 0, 13],
    })
    expect(request.filePeriods).toEqual([3, 12])
    expect(buildIncrementalDetectBody(request)).toEqual({
      year: 2025,
      file_periods: [3, 12],
      overlap_strategy: 'overwrite',
    })
  })

  it('旧智能导入 Form 只在追加模式携带策略与余额确认', () => {
    expect(appendFormFields(null, true)).toEqual({})
    expect(appendFormFields({ year: 2025, strategy: 'skip', filePeriods: [12] }, true)).toEqual({
      append_strategy: 'skip',
      balance_carry_confirmed: 'true',
    })
  })
})


describe('增量合并与凭证差异展示', () => {
  it('展示策略、继承月份、余额沿用与三类凭证差异', () => {
    const wrapper = mount(LedgerAppendResultPanel, {
      props: {
        appendReport: {
          strategy: 'skip',
          base_dataset_id: 'base',
          file_months: [11, 12],
          inherited_months: [1, 2, 11],
          skipped_months: [11],
          balance_confirmation_required: true,
          tables: { tb_balance: { carried: true, copied_rows: 10 } },
        },
        voucherDiff: {
          status: 'ok',
          summary: {
            added: { count: 2, amount: '30.00', net_amount_change: '30.00' },
            deleted: { count: 1, amount: '10.00', net_amount_change: '-10.00' },
            modified: { count: 3, amount: '40.00', net_amount_change: '5.00' },
          },
        },
      },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('重叠月份保留上一版本')
    expect(wrapper.text()).toContain('继承月份：1 月、2 月、11 月')
    expect(wrapper.text()).toContain('沿用上一版本：科目余额表')
    expect(wrapper.text()).toContain('余额表未随新增月份更新')
    expect(wrapper.text()).toContain('新增凭证2 张')
    expect(wrapper.text()).toContain('分录变化3 张')
  })

  it('差异报告失败时显示原因而不假装无差异', () => {
    const wrapper = mount(LedgerAppendResultPanel, {
      props: { voucherDiff: { status: 'failed', reason: 'query timeout' } },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('差异报告未生成：query timeout')
    expect(voucherDiffEntries(null).every(item => item.count === 0)).toBe(true)
  })
})


describe('生产入口接线', () => {
  it('数据管理不再调用预删端点，并把完整请求交给上传入口', () => {
    const source = read('components/ledger-import/LedgerDataManager.vue')
    expect(source).not.toContain('incrementalApply')
    expect(source).not.toContain('执行清理')
    expect(source).toContain("emit('request-incremental-upload', request)")
    expect(source).toContain('buildIncrementalDetectBody')
  })

  it('旧导入与 v2 两入口都携带追加策略和独立余额确认', () => {
    const penetration = read('views/LedgerPenetration.vue')
    const page = read('views/LedgerImportPage.vue')
    const dialog = read('components/ledger-import/LedgerImportDialog.vue')
    expect(penetration).toContain('appendFormFields(incrementalUploadRequest.value')
    expect(penetration).toContain('result: payload,')
    expect(penetration).not.toContain('{ imported: payload.imported }')
    expect(penetration).toContain('回滚到上一版本')
    expect(penetration).toContain('rollbackLedgerDataset(')
    for (const source of [page, dialog]) {
      expect(source).toContain('incremental: !!')
      expect(source).toContain('overlap_strategy:')
      expect(source).toContain('balance_carry_confirmed:')
    }
  })

  it('两个完成界面都挂合并与差异面板', () => {
    const summary = read('components/ImportCompletionSummary.vue')
    const progress = read('components/ledger-import/ImportProgress.vue')
    expect(summary).toContain('<LedgerAppendResultPanel')
    expect(progress).toContain('<LedgerAppendResultPanel')
    expect(progress).toContain('resultPayload.value = (data.result || null)')
  })
})
