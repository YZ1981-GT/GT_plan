/**
 * K6 附注录入区块接线契约（批 3 Task 13）
 *
 * 背景：改造前两个 K6 披露 Tab **只喂主表** —— 附注要求的另外 3~4 张表
 * （减值准备变动 / 持有待售非流动资产 / 处置组 / 持有待售负债）在底稿里
 * 完全没有录入位置，模板补了 columns/guidance 也只有 seed 路径能看到，
 * 同步路径永远推不出这些表。
 *
 * 本守卫读组件源码 + 跑 composable，锁死：
 * - 两个 Tab 都挂了 `K6NoteBlockTables` 并把 4 个区块喂进 `buildK6SyncPayload`
 * - 国企侧**单独 POST §八、43**（`sync_from_workpaper` 定位键只含 note_section）
 * - 金额控件是 `WpAmountInput`（`el-input-number` 归零）、只读金额走 `fmtAmount`
 * - composable 的增删改 / 反序列化补齐 / 派生列读时推导
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  k6BlockItemId,
  useK6NoteBlocks,
  type K6BlockKey,
} from '../useK6NoteBlocks'
import { buildK6SoeLiabilityPayload, buildK6SyncPayload, K6_SOE_SUBTABLE } from '../k6NoteSectionMap'

const WP_ROOT = resolve(__dirname, '../..')

const TABS = {
  listed: 'k6/core/K6TabDisclosureListed.vue',
  soe: 'k6/core/K6TabDisclosureSoe.vue',
} as const

/** 去注释：守卫注释里会写反例，不剥离会误报（J1 接线守卫首版即因此） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
}

function readTab(variant: keyof typeof TABS): string {
  return stripComments(readFileSync(resolve(WP_ROOT, TABS[variant]), 'utf-8'))
}

describe('K6 披露 Tab 接线：附注 4 张表已有录入位置', () => {
  it.each(Object.keys(TABS) as Array<keyof typeof TABS>)(
    '%s Tab 挂载 K6NoteBlockTables 并初始化 useK6NoteBlocks',
    (variant) => {
      const src = readTab(variant)
      expect(/<K6NoteBlockTables\b/.test(src), '未挂载附注录入区块组件').toBe(true)
      expect(/useK6NoteBlocks\(\s*\{/.test(src), '未初始化 useK6NoteBlocks').toBe(true)
      // load 必须在 loadSavedData 里调用，否则切回本页数据不回显
      expect(/noteBlocks\.load\(\)/.test(src), '未调用 noteBlocks.load()').toBe(true)
    },
  )

  it.each(Object.keys(TABS) as Array<keyof typeof TABS>)(
    '%s Tab 把 4 个区块喂进 buildK6SyncPayload（不再只推主表）',
    (variant) => {
      const src = readTab(variant)
      for (const key of ['impairment', 'nonCurrent', 'disposalGroup']) {
        expect(
          new RegExp(`${key}:\\s*noteBlocks\\.${key}\\.value`).test(src),
          `载荷缺 ${key} 区块`,
        ).toBe(true)
      }
      const liabField = variant === 'listed' ? 'listedLiabilities' : 'liabilities'
      expect(
        src.includes(`noteBlocks.${liabField}.value`),
        `载荷缺 ${liabField} 区块`,
      ).toBe(true)
    },
  )

  it('国企 Tab 单独 POST §八、43（一个 payload 只能写一节）', () => {
    const src = readTab('soe')
    expect(/buildK6SoeLiabilityPayload\(/.test(src), '未构建负债章节载荷').toBe(true)
    expect(/K6_SOE_LIABILITY_NOTE_SECTION/.test(src), '未登记负债章节号').toBe(true)
    // 两次 POST（主表章节 + 负债章节）
    expect((src.match(/http\.post\(url/g) ?? []).length).toBeGreaterThanOrEqual(2)
  })

  it('上市 Tab 不发第二次请求（负债并入 五、11）', () => {
    const src = readTab('listed')
    expect(/buildK6SoeLiabilityPayload/.test(src)).toBe(false)
  })

  it.each([
    ...Object.values(TABS),
    'k6/core/K6NoteBlockTables.vue',
    'k6/core/K6FairValueBlock.vue',
  ])('%s 金额控件用 WpAmountInput，el-input-number 归零', (rel) => {
    const src = stripComments(readFileSync(resolve(WP_ROOT, rel), 'utf-8'))
    expect(
      (src.match(/el-input-number/g) ?? []).length,
      '残留 el-input-number（EP 2.13.6 的 :formatter 是空操作，千分符不生效）',
    ).toBe(0)
    expect(/WpAmountInput/.test(src), '未使用 WpAmountInput').toBe(true)
  })

  it.each(Object.values(TABS))('%s 只读金额委托平台 fmtAmount 单一真源', (rel) => {
    const src = stripComments(readFileSync(resolve(WP_ROOT, rel), 'utf-8'))
    expect(/import \{ fmtAmount \} from '@\/utils\/formatters'/.test(src)).toBe(true)
    expect(
      /toLocaleString\('zh-CN'/.test(src),
      '仍在自造千分符格式化（应委托 fmtAmount）',
    ).toBe(false)
  })

  it('守卫自检：stripComments 不把注释里的反例当代码', () => {
    const sample = '/* 原来用 el-input-number */\n// toLocaleString(\'zh-CN\')\nconst x = 1'
    const cleaned = stripComments(sample)
    expect(/el-input-number/.test(cleaned)).toBe(false)
    expect(/toLocaleString\('zh-CN'/.test(cleaned)).toBe(false)
    expect(/el-input-number/.test('<el-input-number v-model="x" />')).toBe(true)
  })
})

// ─── composable 行为 ────────────────────────────────────────────────────────

let harnessSeq = 0

function harness(
  variant: 'listed' | 'soe',
  seed: Partial<Record<K6BlockKey, unknown>> = {},
  wpId = `wp-${(harnessSeq += 1)}`,
) {
  const store = new Map<string, any>()
  for (const [block, rows] of Object.entries(seed)) {
    store.set(k6BlockItemId(variant, block as K6BlockKey), { remark: JSON.stringify(rows) })
  }
  const saved: Array<[string, string]> = []
  let changed = 0
  const blocks = useK6NoteBlocks({
    variant,
    wpId: () => wpId,
    responses: () => store,
    save: (itemId, remark) => {
      saved.push([itemId, remark])
      store.set(itemId, { remark })
    },
    onChanged: () => { changed += 1 },
  })
  blocks.load()
  return { blocks, saved, store, wpId, changedCount: () => changed }
}

describe('useK6NoteBlocks', () => {
  it('item_id 命名稳定（改了会丢既有项目的录入数据）', () => {
    expect(k6BlockItemId('soe', 'impairment')).toBe('K6-disclosure-soe-impairment-rows')
    expect(k6BlockItemId('listed', 'liabilities')).toBe('K6-disclosure-listed-liabilities-rows')
  })

  it('反序列化补齐缺字段（旧载荷缺列时不得让 undefined 进公式变 NaN）', () => {
    const { blocks } = harness('soe', {
      impairment: [{ project: '固定资产', priorAmount: 1000 }],
      nonCurrent: [{ project: '厂房' }],
    })
    const imp = blocks.impairment.value[0]
    expect(imp).toMatchObject({ project: '固定资产', priorAmount: 1000, increase: 0, reverse: 0, disposal: 0 })
    expect(Number.isFinite(blocks.endOf(imp))).toBe(true)
    expect(blocks.endOf(imp)).toBe(1000)
    expect(blocks.nonCurrent.value[0]).toMatchObject({ endBook: 0, endFairValue: 0, disposalFee: 0, timetable: '' })
  })

  it('增删改都落持久化并触发 onChanged（否则自动同步不会跑）', () => {
    const { blocks, saved, changedCount } = harness('soe')
    blocks.addRow('impairment')
    expect(blocks.impairment.value).toHaveLength(1)
    expect(saved[0][0]).toBe('K6-disclosure-soe-impairment-rows')
    const id = blocks.impairment.value[0].id
    blocks.updateField('impairment', id, 'increase', 500)
    expect(blocks.impairment.value[0].increase).toBe(500)
    blocks.removeRow('impairment', id)
    expect(blocks.impairment.value).toHaveLength(0)
    expect(changedCount()).toBe(3)
  })

  it('派生列读时推导：期末 = 期初 + 增加 − 转回 − 出售', () => {
    const { blocks } = harness('listed', {
      impairment: [
        { project: 'A', priorAmount: 1000, increase: 500, reverse: 200, disposal: 100 },
        { project: 'B', priorAmount: 300, increase: 0, reverse: 0, disposal: 300 },
      ],
    })
    expect(blocks.endOf(blocks.impairment.value[0])).toBe(1200)
    expect(blocks.endOf(blocks.impairment.value[1])).toBe(0)
    expect(blocks.impairmentTotalEnd.value).toBe(1200)
    // 派生值不落持久化（行对象里没有 end_amount 字段）
    expect('endAmount' in blocks.impairment.value[0]).toBe(false)
  })

  it('国企负债走 5 列公允价值口径，上市负债走 2 列余额口径（源模板不同）', () => {
    const soe = harness('soe', {
      liabilities: [{ project: '应付账款', endBook: 300, endFairValue: 320, disposalFee: 10 }],
    })
    expect(soe.blocks.liabilities.value[0]).toMatchObject({ endBook: 300, disposalFee: 10 })
    expect(soe.blocks.listedLiabilities.value).toHaveLength(0)

    const listed = harness('listed', {
      liabilities: [{ project: '应付账款', endAmount: 300, priorAmount: 200 }],
    })
    expect(listed.blocks.listedLiabilities.value[0]).toMatchObject({ endAmount: 300, priorAmount: 200 })
    expect(listed.blocks.liabilities.value).toHaveLength(0)
  })

  it('wasTouched 区分「从未填过」与「填过再清空」（决定是否发清理载荷）', () => {
    const fresh = harness('soe')
    expect(fresh.blocks.wasTouched('liabilities')).toBe(false)
    fresh.blocks.addRow('liabilities')
    expect(fresh.blocks.wasTouched('liabilities')).toBe(true)
    fresh.blocks.removeRow('liabilities', fresh.blocks.liabilities.value[0].id)
    // 清空后仍算「填过」→ 必须发清理载荷，否则附注残留过时明细
    expect(fresh.blocks.wasTouched('liabilities')).toBe(true)

    // 既有项目：checklist item 存在（即使是空数组）也算填过
    const existing = harness('soe', { liabilities: [] })
    expect(existing.blocks.wasTouched('liabilities')).toBe(true)
    expect(existing.blocks.wasTouched('impairment')).toBe(false)
  })

  it('🔴 标记跨组件重挂存活（宿主重建 allResponses / 重挂 Tab 时不得归零）', () => {
    const wp = 'wp-remount-case'
    const first = harness('soe', {}, wp)
    first.blocks.addRow('liabilities')
    first.blocks.removeRow('liabilities', first.blocks.liabilities.value[0].id)
    expect(first.blocks.wasTouched('liabilities')).toBe(true)

    // 模拟宿主重挂：新实例 + 宿主的 responses 里**没有**该 item（本地保存未回灌）
    const remounted = harness('soe', {}, wp)
    expect(
      remounted.blocks.wasTouched('liabilities'),
      '重挂后标记丢失 → 清理载荷不发 → 附注永久残留过时明细（实测踩中）',
    ).toBe(true)
    // 其他底稿不受影响（标记按 wpId 归集）
    expect(harness('soe', {}, 'wp-other').blocks.wasTouched('liabilities')).toBe(false)
  })

  it('responses() 异常/缺失时 wasTouched 不抛（否则整个同步在 POST 前就崩）', () => {
    const blocks = useK6NoteBlocks({
      variant: 'soe',
      wpId: () => 'wp-null-resp',
      responses: () => (null as unknown as Map<string, any>),
      save: () => {},
      onChanged: () => {},
    })
    expect(() => blocks.wasTouched('liabilities')).not.toThrow()
    expect(blocks.wasTouched('liabilities')).toBe(false)
  })

  it('清空负债后载荷带 _removed_table_keys（实测缺这条 §八、43 永久残留）', () => {
    const { blocks } = harness('soe', {
      liabilities: [{ project: '应付账款', endBook: 300, endFairValue: 320, disposalFee: 10 }],
    })
    blocks.removeRow('liabilities', blocks.liabilities.value[0].id)
    // 组件不传 opts → 默认 clearWhenEmpty=true（无条件清理，不依赖任何"是否改动过"启发式）
    const p = buildK6SoeLiabilityPayload('wp-1', blocks.liabilities.value)
    expect(p).not.toBeNull()
    expect(p!.sub_table_data._removed_table_keys).toEqual(['持有待售负债'])
  })

  it('组件不得再用 wasTouched 门控负债清理（启发式在真实宿主里不可靠）', () => {
    const src = readTab('soe')
    expect(
      /clearWhenEmpty:\s*noteBlocks\.wasTouched/.test(src),
      '用 wasTouched 门控 → 宿主重挂后「填过再清空」识别不到，附注残留过时明细',
    ).toBe(false)
  })

  it('端到端：区块数据经载荷落到正确的附注表名 / 章节', () => {
    const { blocks } = harness('soe', {
      impairment: [{ project: '固定资产', priorAmount: 1000, increase: 500, reverse: 200, disposal: 100 }],
      nonCurrent: [{ project: '厂房', endBook: 900, endFairValue: 1000, disposalFee: 20, timetable: '2026Q2' }],
      disposalGroup: [{ project: '子公司甲', endBook: 500, endFairValue: 600, disposalFee: 10 }],
      liabilities: [{ project: '应付账款', endBook: 300, endFairValue: 320, disposalFee: 10 }],
    })
    const p = buildK6SyncPayload('soe', 'wp-1', {
      assets: [{ project: '固定资产', bookValue: 900, impairment: 100, openingBalance: 1000 }],
      impairment: blocks.impairment.value,
      nonCurrent: blocks.nonCurrent.value,
      disposalGroup: blocks.disposalGroup.value,
    })
    const keys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(keys).toEqual([
      K6_SOE_SUBTABLE.main,
      K6_SOE_SUBTABLE.impairment,
      K6_SOE_SUBTABLE.nonCurrent,
      K6_SOE_SUBTABLE.disposalGroup,
    ])
    // 负债不在这一节 → 单独载荷
    expect(keys).not.toContain('持有待售负债')
    const liab = buildK6SoeLiabilityPayload('wp-1', blocks.liabilities.value)
    expect(liab!.section_id).toBe('八、43')
    expect((liab!.sub_table_data['持有待售负债'] as unknown[])).toHaveLength(2)
  })
})
