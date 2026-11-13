/**
 * spec wp-sync-conflict-adjudication-and-d4-32-modeling §2：room 侧 fence 的读取面。
 *
 * 缺陷原貌：后端 `get_operation` 自 Task 32 起就随 `app_facts` 返回
 * `room_latest_durable_application_id` / `room_latest_durable_sequence`，而前端
 * ①DTO 没解析它们 ②桥与面板的注释写着「这两项没有任何读取面」③缺口登记表把它们
 * 登记成永久缺口。三者叠加 ⇒ `buildResolveFence` 永远判「缺两项」⇒ **任何** entry
 * 的冲突都提交不了裁决。
 *
 * 判据分三层，缺一层都会留下假绿：
 *   1. 纯函数投影（齐备 / 各种不齐备）；
 *   2. DTO 解析（后端字段名 → 前端字段，漏解析则投影恒 null）；
 *   3. 面板（不传 prop 也能从桥的快照投影出齐备 fence 并真的提交）。
 */

import { describe, expect, it } from 'vitest'

import { parseOperationSnapshot } from '../workpaperSyncDto'
import {
  WP_SYNC_FENCE_MISSING_TEXT,
  buildResolveFence,
  roomDurableFenceFromOperation,
} from '../workpaperSyncPresentation'

const UUID_A = '11111111-1111-4111-8111-111111111111'

// ═══════════════════════════════════════════════════════════════════════════
// 1. 纯函数投影
// ═══════════════════════════════════════════════════════════════════════════

describe('roomDurableFenceFromOperation', () => {
  it('两项齐备 ⇒ 投影出 fence', () => {
    const fence = roomDurableFenceFromOperation({
      roomLatestDurableApplicationId: UUID_A,
      roomLatestDurableSequence: 7,
    })
    expect(fence).toEqual({ applicationId: UUID_A, sequence: 7 })
  })

  it('sequence 为 0 是合法的（room 刚耐久第一份）', () => {
    expect(
      roomDurableFenceFromOperation({
        roomLatestDurableApplicationId: UUID_A,
        roomLatestDurableSequence: 0,
      }),
    ).toEqual({ applicationId: UUID_A, sequence: 0 })
  })

  it.each([
    ['快照本身为 null', null],
    [
      'application 为 null（room 尚无耐久记录）',
      { roomLatestDurableApplicationId: null, roomLatestDurableSequence: 7 },
    ],
    [
      'sequence 为 null',
      { roomLatestDurableApplicationId: UUID_A, roomLatestDurableSequence: null },
    ],
    [
      'sequence 为负',
      { roomLatestDurableApplicationId: UUID_A, roomLatestDurableSequence: -1 },
    ],
    [
      'sequence 非整数',
      { roomLatestDurableApplicationId: UUID_A, roomLatestDurableSequence: 1.5 },
    ],
    [
      'application 不是 UUID 形态',
      { roomLatestDurableApplicationId: 'not-a-uuid', roomLatestDurableSequence: 7 },
    ],
  ])('%s ⇒ null（不编造，交给缺项路径可见地失败）', (_label, input) => {
    expect(
      roomDurableFenceFromOperation(
        input as Parameters<typeof roomDurableFenceFromOperation>[0],
      ),
    ).toBeNull()
  })

  it('投影结果是冻结对象（调用方改不动服务端事实）', () => {
    const fence = roomDurableFenceFromOperation({
      roomLatestDurableApplicationId: UUID_A,
      roomLatestDurableSequence: 7,
    })
    expect(Object.isFrozen(fence)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. DTO 解析（后端字段名 → 前端字段）
// ═══════════════════════════════════════════════════════════════════════════

describe('parseOperationSnapshot 解析 room 侧 fence', () => {
  const wire = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
    requested_operation_id: '22222222-2222-4222-8222-222222222222',
    canonical_operation_id: '22222222-2222-4222-8222-222222222222',
    followed_duplicate: false,
    state: 'conflict',
    application_id: '33333333-3333-4333-8333-333333333333',
    duplicate_of_operation_id: null,
    ...over,
  })

  it('两项有值 ⇒ 解析进快照，且能直接投影出 fence', () => {
    const snap = parseOperationSnapshot(
      wire({
        room_latest_durable_application_id: UUID_A,
        room_latest_durable_sequence: 9,
      }),
    )
    expect(snap.roomLatestDurableApplicationId).toBe(UUID_A)
    expect(snap.roomLatestDurableSequence).toBe(9)
    expect(roomDurableFenceFromOperation(snap)).toEqual({
      applicationId: UUID_A,
      sequence: 9,
    })
  })

  it('缺键 / null ⇒ 都归 null（「room 尚无耐久记录」与「后端没投影」同一条可见路径）', () => {
    const absent = parseOperationSnapshot(wire())
    expect(absent.roomLatestDurableApplicationId).toBeNull()
    expect(absent.roomLatestDurableSequence).toBeNull()

    const nulled = parseOperationSnapshot(
      wire({
        room_latest_durable_application_id: null,
        room_latest_durable_sequence: null,
      }),
    )
    expect(nulled.roomLatestDurableApplicationId).toBeNull()
    expect(nulled.roomLatestDurableSequence).toBeNull()
  })

  it('解析出的两项喂给 buildResolveFence 能凑齐八项', () => {
    const snap = parseOperationSnapshot(
      wire({
        room_latest_durable_application_id: UUID_A,
        room_latest_durable_sequence: 4,
      }),
    )
    const { fence, missing } = buildResolveFence({
      preview: {
        conflictSetDigest: 'a'.repeat(64),
        canonicalApplicationId: '33333333-3333-4333-8333-333333333333',
        incomingSequence: 4,
        currentRevision: 12,
        roomGeneration: 2,
        clientEditEpoch: 5,
      } as Parameters<typeof buildResolveFence>[0]['preview'],
      roomDurable: roomDurableFenceFromOperation(snap),
    })
    expect(missing).toEqual([])
    expect(fence).not.toBeNull()
    expect(fence?.roomLatestDurableApplicationId).toBe(UUID_A)
    expect(fence?.roomLatestDurableSequence).toBe(4)
  })

  it('两项缺失时 buildResolveFence 逐项列出且有中文文案（不合并成一句）', () => {
    const snap = parseOperationSnapshot(wire())
    const { fence, missing } = buildResolveFence({
      preview: {
        conflictSetDigest: 'a'.repeat(64),
        canonicalApplicationId: '33333333-3333-4333-8333-333333333333',
        incomingSequence: 4,
        currentRevision: 12,
        roomGeneration: 2,
        clientEditEpoch: 5,
      } as Parameters<typeof buildResolveFence>[0]['preview'],
      roomDurable: roomDurableFenceFromOperation(snap),
    })
    expect(fence).toBeNull()
    expect(missing).toEqual([
      'room_latest_durable_application_id',
      'room_latest_durable_sequence',
    ])
    for (const key of missing) {
      expect(WP_SYNC_FENCE_MISSING_TEXT[key]).toBeTruthy()
      // 措辞不得再说「无读取面」——读取面已经有了，那样写会把用户引向错误结论
      expect(WP_SYNC_FENCE_MISSING_TEXT[key]).not.toContain('无读取面')
    }
  })
})

// 面板层判据（不传 prop 也能从桥的快照投影）在 `WorkpaperSyncConflictDialog.spec.ts`
// 的「resolve fence」一节 —— 那里已有 driveTo('conflict') / dialogApi / panel 夹具，
// 在这里重建一套替身只会多出一处会漂的夹具。
