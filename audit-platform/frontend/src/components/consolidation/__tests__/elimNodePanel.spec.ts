/**
 * 差额分录面板纯逻辑（spec consol-tree-three-code-autobuild 任务 10.7 / 需求 6.1 / 9.3）
 *
 * - 状态机按钮与后端 change_review_status 一致；
 * - 表单校验与后端 _serialize_lines 一致（借贷平衡、有金额必有科目、至少一行金额）；
 * - 归属由节点决定：合并差额 ⇒ branch_entity_code=null，母分差额 ⇒ 该企业代码；
 * - 节点金额按科目自然方向归一（贷方性质科目取贷减借）。
 */
import { describe, it, expect } from 'vitest'
import {
  buildEntryPayload,
  canApprove,
  canEdit,
  canRevoke,
  canSubmit,
  elimTargetOf,
  emptyLine,
  findTarget,
  linesToForm,
  normalizeDrillRow,
  signedNet,
  statusLabel,
  typeLabel,
  validateLines,
  type FormLine,
} from '../composables/elimNodePanel'

const line = (code: string, dr = '', cr = '', name = ''): FormLine => ({
  account_code: code, account_name: name, debit_amount: dr, credit_amount: cr,
})

describe('elimNodePanel 状态机', () => {
  it.each([
    ['draft', true, true, true, false],
    ['rejected', true, true, false, false],
    ['pending_review', false, false, true, false],
    ['approved', false, false, false, true],
  ])('%s：可修改=%s 可提交=%s 可审批=%s 可撤销审批=%s', (status, edit, submit, approve, revoke) => {
    const e = { review_status: status }
    expect([canEdit(e), canSubmit(e), canApprove(e), canRevoke(e)]).toEqual([edit, submit, approve, revoke])
  })

  it('状态与类型为中文', () => {
    expect(['draft', 'pending_review', 'approved', 'rejected'].map(statusLabel)).toEqual(['草稿', '待审批', '已审批', '已驳回'])
    expect(typeLabel('other')).toBe('其他调整')
    expect(typeLabel('internal_ar_ap')).toBe('内部往来')
  })
})

describe('elimNodePanel 表单校验', () => {
  it('借贷平衡且有金额 ⇒ 可保存；合计按两位小数', () => {
    const c = validateLines([line('1122', '100.5'), line('2202', '', '1,00.50')])
    expect(c.error).toBe('')
    expect([c.debit.toString(), c.credit.toString()]).toEqual(['100.5', '100.5'])
  })

  it.each([
    [[line('1122', '100'), line('2202', '', '90')], '借贷不平衡'],
    [[line('1122', '100'), line('', '', '100')], '第 2 行有金额但没有科目'],
    [[line('1122', '1.234'), line('2202', '', '1.234')], '第 1 行金额格式不正确（最多两位小数）'],
    [[line('1122', 'abc'), line('2202')], '第 1 行金额格式不正确（最多两位小数）'],
    [[emptyLine(), emptyLine()], '请至少填写一行金额'],
  ])('拦下：%#', (lines, message) => {
    expect(validateLines(lines as FormLine[]).error).toBe(message)
  })
})

describe('elimNodePanel 请求体', () => {
  const form = {
    entry_type: 'internal_ar_ap' as const,
    description: '  抵销内部往来 ',
    lines: [line('1122', '60', '', '应收账款'), line('2202', '', '60'), emptyLine()],
  }

  it('母分差额节点 ⇒ 归属该企业；只提交有科目的行；金额两位小数', () => {
    const target = elimTargetOf({ node_key: 'G:branch_elim', role: 'branch_elim', company_code: 'G' })
    const payload = buildEntryPayload(target, form, { projectId: 'p-g', year: 2025 })
    expect(payload).toEqual({
      project_id: 'p-g', year: 2025, entry_type: 'internal_ar_ap', description: '抵销内部往来',
      branch_entity_code: 'G',
      lines: [
        { account_code: '1122', account_name: '应收账款', debit_amount: '60.00', credit_amount: '0.00' },
        { account_code: '2202', account_name: null, debit_amount: '0.00', credit_amount: '60.00' },
      ],
    })
  })

  it('合并差额节点 ⇒ 归属为空（显式 null）；修改时不带项目与年度', () => {
    const target = elimTargetOf({ node_key: 'G:consol_elim', role: 'consol_elim', company_code: 'G' })
    const payload = buildEntryPayload(target, form, {
      projectId: 'p-g', year: 2025, forUpdate: true,
    })
    expect(payload.branch_entity_code).toBeNull()
    expect('branch_entity_code' in payload).toBe(true)
    expect(payload.project_id).toBeUndefined()
    expect(payload.year).toBeUndefined()
  })

  it('归属选项：明细表 hosted_nodes 与企业树节点同形；已有分录按 branch_entity_code 找回选项', () => {
    expect(elimTargetOf({
      node_key: 'G:branch_elim', role: 'branch_elim', company_code: 'G', display_name: '某集团（母分差额）',
    })).toEqual({ node_key: 'G:branch_elim', label: '某集团（母分差额）', branch_entity_code: 'G' })
    const targets = [
      { node_key: 'G:consol_elim', label: '合并差额', branch_entity_code: null },
      { node_key: 'G:branch_elim', label: '母分差额', branch_entity_code: 'G' },
    ]
    expect(findTarget(targets, 'G')?.node_key).toBe('G:branch_elim')
    expect(findTarget(targets, null)?.node_key).toBe('G:consol_elim')
    expect(findTarget(targets, ' ')?.node_key).toBe('G:consol_elim')
    expect(findTarget(targets, 'X')).toBeNull()
    // 请求体按选项取归属，空白企业代码按合并差额提交
    expect(buildEntryPayload({ branch_entity_code: ' ' }, form, { projectId: 'p-g', year: 2025 }).branch_entity_code)
      .toBeNull()
  })

  it('回填：已保存明细行转表单行且至少两行；穿透行归一为列表行', () => {
    expect(linesToForm({ lines: [{ account_code: '1122', account_name: null, debit_amount: '5', credit_amount: '0' }] }))
      .toEqual([line('1122', '5.00', '', ''), emptyLine()])
    const row = normalizeDrillRow({
      entry_id: 'e1', entry_no: 'CE-001', entry_type: 'other', review_status: 'approved',
      host_project_id: 'p-a', debit_amount: '5.00', credit_amount: '5.00', lines: [], related_company_codes: ['A'],
    })
    expect([row.id, row.project_id, row.entry_no, row.review_status]).toEqual(['e1', 'p-a', 'CE-001', 'approved'])
  })
})

describe('elimNodePanel 节点金额归一', () => {
  const base = {
    account_code: '2202', account_name: '应付账款', children_amount_sum: '0', net_difference: '0', consolidated_amount: '0',
    adjustment_debit: '0', adjustment_credit: '0', elimination_debit: '30', elimination_credit: '100',
  }

  it('贷方性质科目：贷减借；借方性质科目：借减贷', () => {
    expect(signedNet({ ...base, direction: 'credit' }, 'elimination')).toBe('70.00')
    expect(signedNet({ ...base, direction: 'debit' }, 'elimination')).toBe('-70.00')
    expect(signedNet({ ...base, direction: 'debit' }, 'adjustment')).toBe('0.00')
  })
})
