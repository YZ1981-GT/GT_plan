// `workpaperSyncPresentation.ts` 的**纯函数判据**。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
// Validates: Requirements 5.8, 8.1, 8.2, 8.3, 11.2, 11.3, 11.11
// Properties: P35（冲突双侧可追溯）/ P46（状态域穷尽且逐一可辨）
//
// ═══ 判据设计 ═══
//
// 1. **三张表对 26 个状态穷尽**，且相互一致（progress 无提示 / settled 有提示 /
//    只有 applied 是 success / 三个终态必须 settled）。表自证函数无条件被调用。
// 2. **解析器 fail visible**：每一处缺项都断言**具体码**，不是「抛了就算过」。
// 3. **金额走 store**：期望值是字面量 `1,234,567.50`，同时断言它 ≠ `String(v)` ——
//    既不拿被测函数算期望值，也不拿被测常量当期望值。
// 4. **fence 缺项逐项列出**：断言缺项名集合，而不是「missing 非空」。
import { describe, expect, it } from 'vitest'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

import {
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_TEXT,
  WP_BRIDGE_TERMINAL_STATES,
} from '../workpaperSyncBridgeMachine'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'
import {
  WP_SYNC_ACTION_HINT,
  WP_SYNC_BULK_SCOPES,
  WP_SYNC_BULK_SCOPE_LABEL,
  WP_SYNC_FENCE_MISSING_TEXT,
  WP_SYNC_RECOVERY_REASON_TEXT,
  WP_SYNC_RECOVERY_STATE_TEXT,
  WP_SYNC_STATE_TONE,
  WP_SYNC_SUCCESS_STATES,
  WP_SYNC_TRACE_GAPS,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
  WP_SYNC_VALUE_ABSENT_TEXT,
  WP_SYNC_VALUE_NULL_TEXT,
  WP_SYNC_VALUE_UNPROJECTED_TEXT,
  WP_SYNC_WAIT_KIND,
  assertPresentationTextDisjoint,
  buildResolveFence,
  bulkScopeTargets,
  deriveRecoveryBlocking,
  describeBulkScope,
  describeCloseArbitration,
  describeRecoveryEntities,
  formatConflictValue,
  isCloseArbitrationVisible,
  parseConflictPreview,
  projectOperationTimeline,
  projectRecoveryTimeline,
  shortDigest,
  type WorkpaperSyncCloseOutcome,
} from '../workpaperSyncPresentation'
import {
  DIGEST,
  UUID,
  conflictItemWire,
  conflictPreviewWire,
  recoveryCaseFixture,
  threeGroupPreview,
} from './workpaperSyncUiHarness'

function expectRefusal(fn: () => unknown, code: string): void {
  let caught: unknown
  try {
    fn()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望拒绝 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 三张表穷尽且自洽
// ═══════════════════════════════════════════════════════════════════════════

describe('投影表对桥状态域穷尽且自洽', () => {
  it('基调 / 等待语义 / 动作提示三张表逐个状态都有裁决，没有多余键', () => {
    const declared = [...WP_BRIDGE_STATES].sort()
    expect(Object.keys(WP_SYNC_STATE_TONE).sort()).toEqual(declared)
    expect(Object.keys(WP_SYNC_WAIT_KIND).sort()).toEqual(declared)
    expect(Object.keys(WP_SYNC_ACTION_HINT).sort()).toEqual(declared)
  })

  it('表自证通过：progress 无提示、settled 有具体提示、只有 applied 是 success', () => {
    expect(() => assertPresentationTextDisjoint()).not.toThrow()
    expect(WP_SYNC_SUCCESS_STATES).toEqual(['applied'])
    const successStates = WP_BRIDGE_STATES.filter(
      (state) => WP_SYNC_STATE_TONE[state] === 'success',
    )
    expect(successStates).toEqual(['applied'])
  })

  it('三个终态一律 settled —— 它们永不再动，转圈就是无限等待', () => {
    expect([...WP_BRIDGE_TERMINAL_STATES].sort()).toEqual(
      ['close_recovery_required', 'duplicate', 'recovery_download_only'].sort(),
    )
    for (const state of WP_BRIDGE_TERMINAL_STATES) {
      expect(WP_SYNC_WAIT_KIND[state], state).toBe('settled')
    }
  })

  it('close_recovery_required 与 recovery_download_only 的文案与提示都不含成功字样', () => {
    for (const state of ['close_recovery_required', 'recovery_download_only'] as const) {
      const text = `${WP_BRIDGE_STATE_TEXT[state]}｜${WP_SYNC_ACTION_HINT[state]}`
      expect(text).not.toContain('保存成功')
      expect(text).not.toContain('同步成功')
      expect(text).not.toContain('回写完成')
      expect(WP_SYNC_STATE_TONE[state]).not.toBe('success')
    }
  })

  it('26 条状态文案两两不同（同一状态两种含义会让状态条不可辨）', () => {
    const texts = WP_BRIDGE_STATES.map((state) => WP_BRIDGE_STATE_TEXT[state])
    expect(new Set(texts).size).toBe(WP_BRIDGE_STATES.length)
  })

  it('每条动作提示都点得出一个具体动作（含动词且不是「请稍候」类）', () => {
    for (const state of WP_BRIDGE_STATES) {
      const hint = WP_SYNC_ACTION_HINT[state]
      if (WP_SYNC_WAIT_KIND[state] === 'progress') {
        expect(hint, state).toBe('')
        continue
      }
      expect(hint.length, state).toBeGreaterThan(6)
      expect(hint, state).toMatch(/请|可/)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. close 仲裁
// ═══════════════════════════════════════════════════════════════════════════

describe('close 仲裁三种结局逐一可辨', () => {
  it('失权且未定接任者 ⇒ awaiting_successor，文案说明仍在仲裁', () => {
    const result = describeCloseArbitration('close_authorization_stale', [
      'close_authorization_lost',
    ])
    expect(result.outcome).toBe('awaiting_successor')
    expect(result.successorIntentId).toBeNull()
    expect(result.label).toContain('尚未确定接任者')
    expect(result.label).not.toContain('保存成功')
  })

  it('失权且已知接任者 ⇒ 文案逐字带 intent id', () => {
    const result = describeCloseArbitration(
      'close_authorization_stale',
      ['close_authorization_lost'],
      UUID(77),
    )
    expect(result.outcome).toBe('awaiting_successor')
    expect(result.successorIntentId).toBe(UUID(77))
    expect(result.label).toContain(UUID(77))
  })

  it('接任者已完成（结局 applied）仍可辨：outcome=successor_applied 且归因于接任者', () => {
    const result = describeCloseArbitration(
      'applied',
      ['close_authorization_lost', 'close_successor_applied'],
      UUID(78),
    )
    expect(result.outcome).toBe('successor_applied')
    expect(result.label).toContain('接任者')
    expect(result.label).toContain(UUID(78))
    // 不得只说一句「保存成功」——那与「我自己保存成功」不可区分
    expect(result.label).not.toBe(WP_BRIDGE_STATE_TEXT.applied)
  })

  it('宿主没回传 intent id 时显式说明「未回传」，而不是编一个 id', () => {
    const result = describeCloseArbitration('applied', [
      'close_authorization_lost',
      'close_successor_applied',
    ])
    expect(result.successorIntentId).toBeNull()
    expect(result.label).toContain('未由宿主回传')
    expect(result.label).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/)
  })

  it('无接任者 ⇒ no_successor，且清空 successor id', () => {
    const result = describeCloseArbitration(
      'close_recovery_required',
      ['close_authorization_lost', 'close_no_successor'],
      UUID(79),
    )
    expect(result.outcome).toBe('no_successor')
    expect(result.successorIntentId).toBeNull()
    expect(result.label).toContain('无合法接任者')
  })

  it('从未发生 close 仲裁 ⇒ not_applicable 且文案为空（不占版面）', () => {
    const result = describeCloseArbitration('applied', ['forcesave_started', 'operation_observed'])
    expect(result.outcome).toBe('not_applicable')
    expect(result.label).toBe('')
    expect(isCloseArbitrationVisible(result)).toBe(false)
  })

  it('仲裁行可见性：三种真实结局都要显示，只有 not_applicable 不显示', () => {
    const visible: WorkpaperSyncCloseOutcome[] = [
      'awaiting_successor',
      'successor_applied',
      'no_successor',
    ]
    for (const outcome of visible) {
      expect(
        isCloseArbitrationVisible({ outcome, label: 'x', successorIntentId: null }),
        outcome,
      ).toBe(true)
    }
    expect(
      isCloseArbitrationVisible({
        outcome: 'not_applicable',
        label: '',
        successorIntentId: null,
      }),
    ).toBe(false)
  })

  it('同一会话内反复失权时取**最近**一次结局', () => {
    const result = describeCloseArbitration('applied', [
      'close_authorization_lost',
      'close_no_successor',
      'close_authorization_lost',
      'close_successor_applied',
    ])
    expect(result.outcome).toBe('successor_applied')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 追溯缺口登记
// ═══════════════════════════════════════════════════════════════════════════

describe('追溯缺口登记表', () => {
  it('五项已登记缺口都有 id/label/reason，且 id 唯一', () => {
    expect(WP_SYNC_TRACE_GAPS.length).toBe(5)
    const ids = WP_SYNC_TRACE_GAPS.map((gap) => gap.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const gap of WP_SYNC_TRACE_GAPS) {
      expect(gap.label.length, gap.id).toBeGreaterThan(1)
      expect(gap.reason.length, gap.id).toBeGreaterThan(8)
    }
  })

  it('两个 room durable fence 字段与 origin sequence 都在登记表里', () => {
    const ids = WP_SYNC_TRACE_GAPS.map((gap) => gap.id)
    expect(ids).toContain('room_latest_durable_application_id')
    expect(ids).toContain('room_latest_durable_sequence')
    expect(ids).toContain('application_origin_request_sequence')
    expect(ids).toContain('incoming_artifact_sha256')
  })

  it('占位符不是空串也不是 0/—（空白会被读成「值就是空」）', () => {
    expect(WP_SYNC_TRACE_GAP_PLACEHOLDER).toBe('未投影（无读取面）')
    expect(shortDigest(null)).toBe(WP_SYNC_TRACE_GAP_PLACEHOLDER)
    expect(shortDigest('')).toBe(WP_SYNC_TRACE_GAP_PLACEHOLDER)
  })

  it('digest 紧凑展示保留首尾，且不改变原值长度判断', () => {
    const digest = DIGEST(3)
    const short = shortDigest(digest)
    expect(short.startsWith(digest.slice(0, 12))).toBe(true)
    expect(short.endsWith(digest.slice(-4))).toBe(true)
    expect(short).not.toBe(digest)
    // 短串原样返回（不足 16 位时截断只会丢信息）
    expect(shortDigest('abcd')).toBe('abcd')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 冲突预览解析
// ═══════════════════════════════════════════════════════════════════════════

describe('冲突预览解析：分组、双侧定位与 fail visible', () => {
  it('三组预览解析出 sheet/table/row 三级分组与稳定 groupKey', () => {
    const preview = parseConflictPreview(threeGroupPreview())
    expect(preview.groups.map((group) => group.groupKey)).toEqual([
      '明细表/tbl_detail/row-1',
      '明细表/tbl_detail/row-2',
      '汇总表/tbl_summary/row-9',
    ])
    expect(preview.conflictCount).toBe(4)
    expect(preview.groups[0].items.length).toBe(2)
  })

  it('每条冲突都带 JSON Pointer 与 OO 地址（Property 35 的双侧可追溯）', () => {
    const preview = parseConflictPreview(threeGroupPreview())
    for (const item of preview.groups.flatMap((group) => group.items)) {
      expect(item.jsonPointer, item.conflictId).toMatch(/^\//)
      expect(item.ooLocation, item.conflictId).toContain('!')
      expect(item.base).not.toBeNull()
      expect(item.current).not.toBeNull()
      expect(item.incoming).not.toBeNull()
      expect(item.kind.length).toBeGreaterThan(0)
    }
  })

  it('缺 json_pointer ⇒ 具体码 conflict_preview_field_missing，不渲染空串', () => {
    const wire = conflictPreviewWire([
      {
        sheet_key: 's',
        table_key: 't',
        row_key: 'r',
        items: [conflictItemWire({ json_pointer: '' })],
      },
    ])
    expectRefusal(() => parseConflictPreview(wire), 'conflict_preview_field_missing')
  })

  it('缺 adjudicable_by_value_choice ⇒ 拒绝，不默认成「可选边」', () => {
    const item = conflictItemWire()
    delete (item as Record<string, unknown>).adjudicable_by_value_choice
    const wire = conflictPreviewWire([
      { sheet_key: 's', table_key: 't', row_key: 'r', items: [item] },
    ])
    expectRefusal(() => parseConflictPreview(wire), 'conflict_item_adjudicability_missing')
  })

  it('值信封缺 present 布尔 ⇒ 拒绝（「字段缺失」与「显式空值」不得合并）', () => {
    const wire = conflictPreviewWire([
      {
        sheet_key: 's',
        table_key: 't',
        row_key: 'r',
        items: [conflictItemWire({ incoming: { value: 1 } })],
      },
    ])
    expectRefusal(() => parseConflictPreview(wire), 'conflict_value_envelope_invalid')
  })

  it('groups 不是数组 / 载荷不是对象都各有自己的码', () => {
    expectRefusal(
      () => parseConflictPreview(conflictPreviewWire([], { groups: null })),
      'conflict_preview_groups_missing',
    )
    expectRefusal(() => parseConflictPreview([1, 2, 3]), 'conflict_preview_shape_invalid')
  })

  it('conflict_set_digest 为空串时归一成 null（不得当成一个合法摘要）', () => {
    const preview = parseConflictPreview(
      conflictPreviewWire([], { conflict_set_digest: '   ' }),
    )
    expect(preview.conflictSetDigest).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 值渲染：金额必须经 displayPrefs
// ═══════════════════════════════════════════════════════════════════════════

describe('冲突值渲染', () => {
  it('amount 经注入的 fmtAmount 得到千分符 + 2 位小数，且与裸 String 不同', () => {
    const store = useDisplayPrefsStore()
    const rendered = formatConflictValue(
      { present: true, value: 1234567.5 },
      'amount',
      (value) => store.fmtAmount(value),
    )
    expect(rendered).toBe('1,234,567.50')
    expect(rendered).not.toBe(String(1234567.5))
  })

  it('切换单位后同一函数给出不同结果（证明读的是活 store 而非本地副本）', () => {
    const store = useDisplayPrefsStore()
    const yuan = formatConflictValue({ present: true, value: 1234567.5 }, 'amount', (v) =>
      store.fmtAmount(v),
    )
    store.setUnit('wan')
    const wan = formatConflictValue({ present: true, value: 1234567.5 }, 'amount', (v) =>
      store.fmtAmount(v),
    )
    store.setUnit('yuan')
    expect(yuan).toBe('1,234,567.50')
    expect(wan).not.toBe(yuan)
  })

  it('三种「没有值」互不相同：未投影 / 无此字段 / 空值', () => {
    const fmt = (value: unknown): string => String(value)
    expect(formatConflictValue(null, 'text', fmt)).toBe(WP_SYNC_VALUE_UNPROJECTED_TEXT)
    expect(formatConflictValue({ present: false, value: undefined }, 'text', fmt)).toBe(
      WP_SYNC_VALUE_ABSENT_TEXT,
    )
    expect(formatConflictValue({ present: true, value: null }, 'text', fmt)).toBe(
      WP_SYNC_VALUE_NULL_TEXT,
    )
    expect(
      new Set([
        WP_SYNC_VALUE_UNPROJECTED_TEXT,
        WP_SYNC_VALUE_ABSENT_TEXT,
        WP_SYNC_VALUE_NULL_TEXT,
      ]).size,
    ).toBe(3)
  })

  it('非金额类型不经 fmtAmount（布尔中文化、对象 JSON 化）', () => {
    const store = useDisplayPrefsStore()
    const fmt = (value: unknown): string => store.fmtAmount(value)
    expect(formatConflictValue({ present: true, value: true }, 'boolean', fmt)).toBe('是')
    expect(formatConflictValue({ present: true, value: false }, 'boolean', fmt)).toBe('否')
    expect(formatConflictValue({ present: true, value: { a: 1 } }, 'json', fmt)).toBe('{"a":1}')
    expect(formatConflictValue({ present: true, value: 3 }, 'integer', fmt)).toBe('3')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 批量范围
// ═══════════════════════════════════════════════════════════════════════════

describe('批量裁决的显式范围', () => {
  const preview = parseConflictPreview(threeGroupPreview())
  const rowAnchor = preview.groups[0]

  it('四个范围各自取到不同的目标集（行 ⊂ 表 ⊂ 工作表 ⊆ 全部）', () => {
    const row = bulkScopeTargets(preview.groups, 'row', rowAnchor)
    const table = bulkScopeTargets(preview.groups, 'table', rowAnchor)
    const sheet = bulkScopeTargets(preview.groups, 'sheet', rowAnchor)
    const all = bulkScopeTargets(preview.groups, 'all_unresolved', null)
    expect(row.map((item) => item.conflictId)).toEqual([UUID(61), UUID(62)])
    expect(table.length).toBe(3)
    expect(sheet.length).toBe(3)
    // 汇总表那条是 schema 冲突 ⇒ 不可选边收敛，全部范围里也不出现
    expect(all.length).toBe(3)
    expect(all.map((item) => item.conflictId)).not.toContain(UUID(64))
  })

  it('已裁决的项不进任何范围（重复写一遍就是静默覆盖）', () => {
    const withResolved = parseConflictPreview(
      conflictPreviewWire([
        {
          sheet_key: 's',
          table_key: 't',
          row_key: 'r',
          items: [
            conflictItemWire({ conflict_id: UUID(65), resolved: true }),
            conflictItemWire({ conflict_id: UUID(66) }),
          ],
        },
      ]),
    )
    const targets = bulkScopeTargets(withResolved.groups, 'all_unresolved', null)
    expect(targets.map((item) => item.conflictId)).toEqual([UUID(66)])
  })

  it('没有锚点的「本行/本表/本工作表」被拒绝（范围不明确）', () => {
    for (const scope of ['row', 'table', 'sheet'] as const) {
      expectRefusal(
        () => bulkScopeTargets(preview.groups, scope, null),
        'bulk_scope_anchor_required',
      )
    }
  })

  it('未登记范围被拒绝', () => {
    expectRefusal(
      () =>
        bulkScopeTargets(
          preview.groups,
          'everything' as unknown as (typeof WP_SYNC_BULK_SCOPES)[number],
          null,
        ),
      'bulk_scope_unknown',
    )
  })

  it('二次确认文案逐字点出范围名、条数与裁决动作', () => {
    const text = describeBulkScope('table', rowAnchor, 3, '采用回传')
    expect(text).toContain(WP_SYNC_BULK_SCOPE_LABEL.table)
    expect(text).toContain('3 条')
    expect(text).toContain('采用回传')
    expect(text).toContain('明细表')
    expect(text).toContain('tbl_detail')
  })

  it('四个范围都有中文标签且两两不同', () => {
    const labels = WP_SYNC_BULK_SCOPES.map((scope) => WP_SYNC_BULK_SCOPE_LABEL[scope])
    expect(new Set(labels).size).toBe(WP_SYNC_BULK_SCOPES.length)
    for (const label of labels) expect(label).toMatch(/[\u4e00-\u9fa5]/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. resolve fence
// ═══════════════════════════════════════════════════════════════════════════

describe('resolve fence 八项齐备或逐项报缺', () => {
  it('宿主给了 room durable fence ⇒ 八项齐备且逐项来自预览/入参', () => {
    const preview = parseConflictPreview(threeGroupPreview())
    const { fence, missing } = buildResolveFence({
      preview,
      roomDurable: { applicationId: UUID(51), sequence: 9 },
    })
    expect(missing).toEqual([])
    expect(fence).toEqual({
      canonicalApplicationId: UUID(50),
      applicationEffectiveRequestSequence: 7,
      roomLatestDurableApplicationId: UUID(51),
      roomLatestDurableSequence: 9,
      conflictSetDigest: DIGEST(9),
      expectedCurrentRevision: 11,
      roomGeneration: 3,
      clientEditEpoch: 4,
    })
  })

  it('宿主没给 ⇒ 两项 room fence 都进 missing，fence 为 null（不拿 canonical 顶替）', () => {
    const preview = parseConflictPreview(threeGroupPreview())
    const { fence, missing } = buildResolveFence({ preview, roomDurable: null })
    expect(fence).toBeNull()
    expect([...missing].sort()).toEqual([
      'room_latest_durable_application_id',
      'room_latest_durable_sequence',
    ])
  })

  it('room fence 用了 numeric revision 冒充 UUID ⇒ 仍然报缺', () => {
    const preview = parseConflictPreview(threeGroupPreview())
    const { missing } = buildResolveFence({
      preview,
      roomDurable: { applicationId: '12', sequence: 9 },
    })
    expect(missing).toContain('room_latest_durable_application_id')
  })

  it('conflict_set_digest 缺失 ⇒ 单独一项 missing', () => {
    const preview = parseConflictPreview(
      conflictPreviewWire([], { conflict_set_digest: null }),
    )
    const { missing } = buildResolveFence({
      preview,
      roomDurable: { applicationId: UUID(51), sequence: 9 },
    })
    expect(missing).toEqual(['conflict_set_digest'])
  })

  it('每个缺项名都有中文阻断文案（不合并成一句「参数不全」）', () => {
    const keys = [
      'conflict_set_digest',
      'room_latest_durable_application_id',
      'room_latest_durable_sequence',
      'canonical_application_id',
    ]
    for (const key of keys) {
      expect(WP_SYNC_FENCE_MISSING_TEXT[key], key).toBeTruthy()
    }
    expect(new Set(Object.values(WP_SYNC_FENCE_MISSING_TEXT)).size).toBe(keys.length)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 8. recovery 推导
// ═══════════════════════════════════════════════════════════════════════════

describe('recovery 阻断原因与三实体投影', () => {
  const fence = {
    participantId: UUID(22),
    expectedGeneration: 3,
    expectedWriteFence: 5,
    expectedDefinitionBundleSha256: DIGEST(3),
    expectedCurrentRevision: 11,
  }

  it('合法 case + 合法冻结身份 ⇒ 零阻断原因', () => {
    expect(deriveRecoveryBlocking(recoveryCaseFixture(), fence)).toEqual([])
  })

  it('宿主没给冻结身份 ⇒ 一条明确原因（bundle 摘要与写栅栏）', () => {
    const blocking = deriveRecoveryBlocking(recoveryCaseFixture(), null)
    expect(blocking.length).toBe(1)
    expect(blocking[0]).toContain('definition bundle')
    expect(blocking[0]).toContain('写栅栏')
  })

  it('服务端关掉 claim ⇒ 原因里带中文状态名', () => {
    const blocking = deriveRecoveryBlocking(
      recoveryCaseFixture({ state: 'download_only', actions: { claim: false, downloadOnly: false } }),
      fence,
    )
    expect(blocking.some((reason) => reason.includes(WP_SYNC_RECOVERY_STATE_TEXT.download_only))).toBe(
      true,
    )
  })

  it('没有候选确认 ⇒ 单独一条原因（claim 只能引用同 room/代际的既有确认）', () => {
    const blocking = deriveRecoveryBlocking(
      recoveryCaseFixture({ candidatePriorConfirmations: [] }),
      fence,
    )
    expect(blocking.some((reason) => reason.includes('合法基线'))).toBe(true)
  })

  it('摘要形态非法 / 代际非法 / 写栅栏非法 / participant 非 UUID 各自一条', () => {
    expect(
      deriveRecoveryBlocking(recoveryCaseFixture(), {
        ...fence,
        expectedDefinitionBundleSha256: 'not-a-digest',
      }).some((reason) => reason.includes('摘要形态非法')),
    ).toBe(true)
    expect(
      deriveRecoveryBlocking(recoveryCaseFixture(), {
        ...fence,
        expectedGeneration: 0,
      }).some((reason) => reason.includes('代际号形态非法')),
    ).toBe(true)
    expect(
      deriveRecoveryBlocking(recoveryCaseFixture(), {
        ...fence,
        expectedWriteFence: -1,
      }).some((reason) => reason.includes('写栅栏形态非法')),
    ).toBe(true)
    expect(
      deriveRecoveryBlocking(recoveryCaseFixture(), {
        ...fence,
        participantId: '22',
      }).some((reason) => reason.includes('不透明 UUID')),
    ).toBe(true)
  })

  it('claim 前三实体逐项「尚未创建」，presentCount=0', () => {
    const projected = describeRecoveryEntities(recoveryCaseFixture())
    expect(projected.presentCount).toBe(0)
    expect(projected.rows.map((row) => row.value)).toEqual([
      '尚未创建',
      '尚未创建',
      '尚未创建',
    ])
    expect(projected.rows.map((row) => row.id)).toEqual([
      'forcesave_request_id',
      'application_id',
      'operation_id',
    ])
  })

  it('claim 后三实体逐项给出真实 id，presentCount=3', () => {
    const projected = describeRecoveryEntities(
      recoveryCaseFixture({
        state: 'application_created',
        forcesaveRequestId: UUID(42),
        applicationId: UUID(44),
        operationId: UUID(43),
      }),
    )
    expect(projected.presentCount).toBe(3)
    expect(projected.rows.map((row) => row.value)).toEqual([UUID(42), UUID(44), UUID(43)])
  })

  it('四种 recovery 原因都有中文文案且两两不同', () => {
    const texts = Object.values(WP_SYNC_RECOVERY_REASON_TEXT)
    expect(texts.length).toBe(4)
    expect(new Set(texts).size).toBe(4)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 9. timeline 投影
// ═══════════════════════════════════════════════════════════════════════════

describe('两条 timeline 各自投影', () => {
  it('operation timeline 合并 operation/application 两流并按流+序号排', () => {
    const projected = projectOperationTimeline({
      application_id: UUID(50),
      followed_duplicate: true,
      operation_events: [
        { stream: 'operation', sequence_no: 2, to_state: 'b', correlation_id: UUID(71) },
        { stream: 'operation', sequence_no: 1, to_state: 'a', correlation_id: UUID(70) },
      ],
      application_events: [{ stream: 'application', sequence_no: 1, to_state: 'created' }],
    })
    expect(projected.rows.map((row) => `${row.stream}#${row.sequenceNo}`)).toEqual([
      'application#1',
      'operation#1',
      'operation#2',
    ])
    expect(projected.applicationId).toBe(UUID(50))
    expect(projected.followedDuplicate).toBe(true)
  })

  it('缺 sequence_no 的事件被丢掉而不是编一个序号', () => {
    const projected = projectOperationTimeline({
      operation_events: [{ stream: 'operation', to_state: 'x' }, { stream: 'operation', sequence_no: 1 }],
    })
    expect(projected.rows.length).toBe(1)
    expect(projected.rows[0].sequenceNo).toBe(1)
  })

  it('recovery timeline 结构里没有 operation 事件流，只给 claim 后的三实体', () => {
    const projected = projectRecoveryTimeline({
      case_id: UUID(40),
      state: 'application_created',
      claimed_operation_id: UUID(43),
      claimed_application_id: UUID(44),
      recovery_request_id: UUID(42),
      has_three_entities: true,
      events: [{ stream: 'recovery_case', sequence_no: 1, to_state: 'unclaimed' }],
    })
    expect(projected.claimedOperationId).toBe(UUID(43))
    expect(projected.claimedApplicationId).toBe(UUID(44))
    expect(projected.recoveryRequestId).toBe(UUID(42))
    expect(projected.hasThreeEntities).toBe(true)
    expect(Object.keys(projected)).not.toContain('operationEvents')
  })

  it('claim 之前三实体为 null 且 hasThreeEntities=false（不得投影成 0/空串）', () => {
    const projected = projectRecoveryTimeline({
      case_id: UUID(40),
      state: 'unclaimed',
      claimed_operation_id: null,
      claimed_application_id: null,
      recovery_request_id: null,
      has_three_entities: false,
      events: [],
    })
    expect(projected.claimedOperationId).toBeNull()
    expect(projected.claimedApplicationId).toBeNull()
    expect(projected.recoveryRequestId).toBeNull()
    expect(projected.hasThreeEntities).toBe(false)
  })
})
