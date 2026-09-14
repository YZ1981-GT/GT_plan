/**
 * procedureConsoleOverlay.spec.ts — 程序控制台 task overlay 纯逻辑单测 + PBT
 *
 * Feature: procedure-delegation-notification / Task 14
 * 覆盖：
 * - hasTaskOverlay / isUnmaterialized（overlay 检测，需求 2.7）
 * - resolveDeepLink（需求 9.6 / P28：仅按 definition_key 精确定位，缺失即“模板已变化”，绝不按 program_no 猜测）
 * - memberActions（需求 6 / 9.7：与 MyProcedureTasks transition 契约一致）
 * - workflowLabel / workflowTagType（术语一致）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  hasTaskOverlay,
  isUnmaterialized,
  resolveDeepLink,
  memberActions,
  workflowLabel,
  workflowTagType,
  newRequestId,
  WORKFLOW_LABELS,
  ROLE_TERMS,
  type OverlayRow,
} from '../procedureConsoleOverlay'

describe('hasTaskOverlay', () => {
  it('无 overlay 字段 → false（expand 阶段回退既有展示）', () => {
    expect(hasTaskOverlay([{ program_no: 1 }, { program_no: 2 }])).toBe(false)
    expect(hasTaskOverlay([])).toBe(false)
    expect(hasTaskOverlay(null)).toBe(false)
    expect(hasTaskOverlay(undefined)).toBe(false)
  })

  it('任一行带 task_id 或 materialization_required → true', () => {
    expect(hasTaskOverlay([{ program_no: 1 }, { program_no: 2, task_id: 't1' }])).toBe(true)
    expect(hasTaskOverlay([{ program_no: 1, materialization_required: true }])).toBe(true)
  })
})

describe('isUnmaterialized', () => {
  it('materialization_required=true 或 无 task_id 且带标记 → 未物化', () => {
    expect(isUnmaterialized({ materialization_required: true })).toBe(true)
    expect(isUnmaterialized({ task_id: null, materialization_required: false })).toBe(false)
    expect(isUnmaterialized({ task_id: 't1', materialization_required: false })).toBe(false)
  })
  it('无 overlay 标记（普通行）→ false', () => {
    expect(isUnmaterialized({ program_no: 1 })).toBe(false)
    expect(isUnmaterialized(null)).toBe(false)
  })
})

describe('resolveDeepLink — 需求 9.6 / P28', () => {
  const rows: OverlayRow[] = [
    { program_no: 1, definition_key: 'D2A::D2A::aaa', task_id: 't1' },
    { program_no: 2, definition_key: 'D2A::D2A::bbb', task_id: 't2' },
  ]

  it('无 definition_key → 不定位，不报模板变化', () => {
    const r = resolveDeepLink(rows, null, null)
    expect(r.matched).toBe(false)
    expect(r.templateChanged).toBe(false)
  })

  it('命中 definition_key → matched，返回对应行', () => {
    const r = resolveDeepLink(rows, null, 'D2A::D2A::bbb')
    expect(r.matched).toBe(true)
    expect(r.row?.program_no).toBe(2)
    expect(r.templateChanged).toBe(false)
  })

  it('definition_key 匹配不到 → templateChanged=true（绝不按 program_no 猜测）', () => {
    const r = resolveDeepLink(rows, null, 'D2A::D2A::zzz')
    expect(r.matched).toBe(false)
    expect(r.templateChanged).toBe(true)
    expect(r.row).toBeNull()
  })

  it('空行集但给了 definition_key → 模板变化', () => {
    const r = resolveDeepLink([], null, 'D2A::D2A::aaa')
    expect(r.templateChanged).toBe(true)
  })

  it('PBT：给定 definition_key 只会命中同 key 的行，或报模板变化；绝不返回 program_no 相同但 key 不同的行', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            program_no: fc.integer({ min: 1, max: 50 }),
            definition_key: fc.string({ minLength: 1, maxLength: 12 }),
          }),
          { maxLength: 30 },
        ),
        fc.string({ minLength: 1, maxLength: 12 }),
        (arr, target) => {
          const overlayRows: OverlayRow[] = arr.map((a) => ({
            program_no: a.program_no,
            definition_key: a.definition_key,
          }))
          const r = resolveDeepLink(overlayRows, null, target)
          if (r.matched) {
            // 命中行的 definition_key 必须严格等于 target
            expect(r.row?.definition_key).toBe(target)
          } else {
            // 未命中：要么没有任何行等于 target，要么行集为空
            expect(overlayRows.some((x) => x.definition_key === target)).toBe(false)
            expect(r.templateChanged).toBe(true)
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})

describe('memberActions — 需求 6 / 9.7', () => {
  const base = (over: Partial<OverlayRow> & { my_role?: 'assignee' | 'reviewer' | null }) =>
    memberActions({
      task_id: 't1', applicability_status: 'execute', ...over,
    } as any)

  it('未物化 / 无 task_id → 无动作', () => {
    expect(memberActions({ materialization_required: true, my_role: 'assignee' } as any)).toEqual([])
    expect(memberActions({ workflow_status: 'assigned', my_role: 'assignee' } as any)).toEqual([])
  })

  it('applicability != execute → 无动作（细裁不适用）', () => {
    expect(base({ applicability_status: 'not_applicable', workflow_status: 'assigned', my_role: 'assignee' })).toEqual([])
  })

  it('assignee 状态动作链：assigned→ack, acknowledged→start, in_progress→submit, changes_requested→继续修改', () => {
    expect(base({ workflow_status: 'assigned', my_role: 'assignee' }).map(a => a.key)).toEqual(['acknowledge'])
    expect(base({ workflow_status: 'acknowledged', my_role: 'assignee' }).map(a => a.key)).toEqual(['start'])
    expect(base({ workflow_status: 'in_progress', my_role: 'assignee' }).map(a => a.key)).toEqual(['submit'])
    expect(base({ workflow_status: 'changes_requested', my_role: 'assignee' }).map(a => a.key)).toEqual(['start'])
  })

  it('reviewer 在 submitted 有 review + request_changes；其他状态无', () => {
    expect(base({ workflow_status: 'submitted', my_role: 'reviewer' }).map(a => a.key)).toEqual(['review', 'request_changes'])
    expect(base({ workflow_status: 'in_progress', my_role: 'reviewer' })).toEqual([])
  })

  it('reviewed / cancelled 终态无动作', () => {
    expect(base({ workflow_status: 'reviewed', my_role: 'assignee' })).toEqual([])
    expect(base({ workflow_status: 'cancelled', my_role: 'reviewer' })).toEqual([])
  })
})

describe('术语与标签', () => {
  it('workflowLabel 已知值中文化，未知原样，空 → —', () => {
    expect(workflowLabel('submitted')).toBe('待复核')
    expect(workflowLabel('reviewed')).toBe('已复核')
    expect(workflowLabel('weird')).toBe('weird')
    expect(workflowLabel(null)).toBe('—')
  })

  it('workflowTagType 关键状态映射', () => {
    expect(workflowTagType('reviewed')).toBe('success')
    expect(workflowTagType('changes_requested')).toBe('danger')
    expect(workflowTagType('submitted')).toBe('warning')
    expect(workflowTagType(undefined)).toBe('')
  })

  it('ROLE_TERMS 区分五类角色，不混淆高阶复核与程序行 reviewer（需求 14.1）', () => {
    expect(ROLE_TERMS.procedureAssignee).toBe('程序执行人')
    expect(ROLE_TERMS.operationReviewer).toBe('操作复核人')
    expect(ROLE_TERMS.highOrderReviewer).toContain('EQCR')
    expect(ROLE_TERMS.operationReviewer).not.toBe(ROLE_TERMS.highOrderReviewer)
  })

  it('WORKFLOW_LABELS 覆盖状态机全部状态', () => {
    for (const s of ['unassigned', 'assigned', 'acknowledged', 'in_progress', 'submitted', 'changes_requested', 'reviewed', 'cancelled']) {
      expect(WORKFLOW_LABELS[s]).toBeTruthy()
    }
  })
})

describe('newRequestId', () => {
  it('生成非空唯一字符串', () => {
    const a = newRequestId()
    const b = newRequestId()
    expect(a).toBeTruthy()
    expect(a).not.toBe(b)
  })
})
