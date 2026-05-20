/**
 * useIIntangibleAssetSheetGroups vitest
 *
 * spec workpaper-i-intangible-assets-cycle ADR-I5b（Task 2.5）
 *
 * 覆盖：
 * - 10 类分组规则代表性 sheet 名分类正确性 + fallback 其他程序
 * - priority 优先级顺序（首个命中即停止）
 * - defaultHidden / readonly 标志位
 * - composable 基本行为（refresh / 默认过滤索引/历史遗留 / groups 按 priority 排序）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyISheet,
  I_SHEET_PATTERNS,
  FALLBACK_GROUP,
  useIIntangibleAssetSheetGroups,
} from '../useIIntangibleAssetSheetGroups'

// ===== 10 类分组规则测试 =====

describe('classifyISheet - 10 类分组规则全覆盖', () => {
  it('1. 索引（priority 0, defaultHidden=true）: 底稿目录 / GT_Custom / 修订说明', () => {
    expect(classifyISheet('底稿目录')).toMatchObject({
      category: '索引',
      priority: 0,
      defaultHidden: true,
    })
    expect(classifyISheet('GT_Custom')).toMatchObject({
      category: '索引',
      priority: 0,
      defaultHidden: true,
    })
    expect(classifyISheet('修订说明')).toMatchObject({
      category: '索引',
      priority: 0,
      defaultHidden: true,
    })
  })

  it('2. 历史遗留（priority 1, defaultHidden=true）: 参考－商誉减值测试示例 等', () => {
    expect(classifyISheet('参考－商誉减值测试示例')).toMatchObject({
      category: '历史遗留',
      priority: 1,
      defaultHidden: true,
    })
    expect(classifyISheet('参考-减值测试示例')).toMatchObject({
      category: '历史遗留',
      defaultHidden: true,
    })
    expect(classifyISheet('修订前-审定表')).toMatchObject({
      category: '历史遗留',
      defaultHidden: true,
    })
  })

  it('3. 总控台（priority 2）: I1A / 实质性程序表I1A', () => {
    expect(classifyISheet('I1A')).toMatchObject({ category: '总控台', priority: 2 })
    expect(classifyISheet('实质性程序表I1A')).toMatchObject({
      category: '总控台',
      priority: 2,
    })
    expect(classifyISheet('无形资产实质性程序表')).toMatchObject({ category: '总控台' })
  })

  it('4. 审定表（priority 3）: 审定表I1-1', () => {
    expect(classifyISheet('审定表I1-1')).toMatchObject({ category: '审定表', priority: 3 })
    expect(classifyISheet('审定表I3-1')).toMatchObject({ category: '审定表' })
    expect(classifyISheet('审定表I6-1')).toMatchObject({ category: '审定表' })
  })

  it('5. 附注披露（priority 4, readonly=true）', () => {
    expect(classifyISheet('附注披露信息（上市公司）')).toMatchObject({
      category: '附注披露',
      priority: 4,
      readonly: true,
    })
    expect(classifyISheet('附注披露信息（国有企业）')).toMatchObject({
      category: '附注披露',
      readonly: true,
    })
  })

  it('6. 明细表（priority 5）: 明细表I1-2', () => {
    expect(classifyISheet('明细表I1-2')).toMatchObject({ category: '明细表', priority: 5 })
    expect(classifyISheet('明细表I2-2')).toMatchObject({ category: '明细表' })
    expect(classifyISheet('明细表I3-2')).toMatchObject({ category: '明细表' })
    expect(classifyISheet('明细表I4-2')).toMatchObject({ category: '明细表' })
    expect(classifyISheet('明细表I6-2')).toMatchObject({ category: '明细表' })
  })

  it('7. 摊销测算（priority 6）: 摊销测算表（不含减值）I1-10（剩余年限法）', () => {
    expect(classifyISheet('摊销测算表（不含减值）I1-10（剩余年限法）')).toMatchObject({
      category: '摊销测算',
      priority: 6,
    })
    expect(classifyISheet('摊销测算表（含减值）I1-11')).toMatchObject({ category: '摊销测算' })
    expect(classifyISheet('摊销测算I4-6')).toMatchObject({ category: '摊销测算' })
    expect(classifyISheet('摊销测算表I4-7（工作量法）')).toMatchObject({ category: '摊销测算' })
    expect(classifyISheet('摊销分配分析表')).toMatchObject({ category: '摊销测算' })
  })

  it('8. 减值测试（priority 7）: 商誉减值测试I3-6 / 可收回金额测试', () => {
    expect(classifyISheet('商誉减值测试I3-6')).toMatchObject({
      category: '减值测试',
      priority: 7,
    })
    expect(classifyISheet('可收回金额测试I3-7')).toMatchObject({ category: '减值测试' })
    expect(classifyISheet('减值测试I3-6')).toMatchObject({ category: '减值测试' })
  })

  it('9. 针对性检查（priority 8）: 资本化时点判断I2-6 等', () => {
    expect(classifyISheet('资本化时点判断I2-6')).toMatchObject({
      category: '针对性检查',
      priority: 8,
    })
    expect(classifyISheet('研发项目清单I6-3')).toMatchObject({ category: '针对性检查' })
    expect(classifyISheet('加计扣除测算表I6-5')).toMatchObject({ category: '针对性检查' })
    expect(classifyISheet('项目成立条件检查I2-5')).toMatchObject({ category: '针对性检查' })
  })

  it('10. 调整分录（priority 9）: 调整分录', () => {
    expect(classifyISheet('调整分录')).toMatchObject({ category: '调整分录', priority: 9 })
    expect(classifyISheet('调整分录汇总I1-16')).toMatchObject({ category: '调整分录' })
  })

  it('Fallback: 其他程序（priority 10）— 不匹配任何 pattern', () => {
    expect(classifyISheet('利息资本化测算表')).toEqual(FALLBACK_GROUP)
    expect(classifyISheet('完全不相干的随机名字 XYZ123')).toEqual(FALLBACK_GROUP)
    expect(FALLBACK_GROUP).toMatchObject({ category: '其他程序', priority: 10 })
  })
})

// ===== priority 优先级顺序（首个命中即停止） =====

describe('classifyISheet - priority 优先级顺序', () => {
  it('I_SHEET_PATTERNS priority 严格升序排列', () => {
    const priorities = I_SHEET_PATTERNS.map((p) => p.priority)
    expect(priorities).toEqual([...priorities].sort((a, b) => a - b))
  })

  it('I_SHEET_PATTERNS 包含 10 条规则 + FALLBACK 11 类', () => {
    expect(I_SHEET_PATTERNS).toHaveLength(10)
    expect(FALLBACK_GROUP.priority).toBe(10)
  })

  it('多 pattern 命中时取首个（priority 最低）— 索引 > 历史遗留 > 总控台...', () => {
    // 假设某 sheet 名既含"明细表"又含"减值测试"，应归"明细表"（priority 5 < 7）
    expect(classifyISheet('明细表减值测试备注')).toMatchObject({
      category: '明细表',
      priority: 5,
    })
    // 含"审定表"的 sheet 优先于含"明细表"的（priority 3 < 5）
    expect(classifyISheet('审定表明细表合并')).toMatchObject({
      category: '审定表',
      priority: 3,
    })
  })

  it('索引/历史遗留 default hidden flag 仅标在前 2 类', () => {
    const hiddenCats = I_SHEET_PATTERNS.filter((p) => p.defaultHidden === true).map(
      (p) => p.category,
    )
    expect(hiddenCats).toEqual(['索引', '历史遗留'])
  })

  it('readonly flag 仅标在附注披露', () => {
    const readonlyCats = I_SHEET_PATTERNS.filter((p) => p.readonly === true).map(
      (p) => p.category,
    )
    expect(readonlyCats).toEqual(['附注披露'])
  })
})

// ===== composable 行为测试 =====

describe('useIIntangibleAssetSheetGroups - composable behavior', () => {
  function createMockUniverAPI(sheetNames: string[]) {
    const sheetObjects = sheetNames.map((name, idx) => ({
      getSheetId: () => `sid-${idx}`,
      getSheetName: () => name,
      isSheetHidden: () => false,
      activate: () => undefined,
    }))
    const wb = {
      getSheets: () => sheetObjects,
      getActiveSheet: () => sheetObjects[0],
      getId: () => 'unit1',
    }
    return {
      getActiveWorkbook: () => wb,
      executeCommand: async () => undefined,
    }
  }

  it('默认过滤索引类 sheet（底稿目录 / GT_Custom 默认隐藏）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI(['底稿目录', 'GT_Custom', '审定表I1-1', '明细表I1-2']),
    )
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(2)
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('审定表I1-1')
    expect(names).toContain('明细表I1-2')
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
  })

  it('默认过滤历史遗留 sheet（参考－商誉减值测试示例）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI(['参考－商誉减值测试示例', '商誉减值测试I3-6', '审定表I3-1']),
    )
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(2)
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('参考－商誉减值测试示例')
    expect(names).toContain('商誉减值测试I3-6')
    expect(names).toContain('审定表I3-1')
  })

  it('附注披露 readonly 标志正确传递到 sheet item', () => {
    const apiRef = ref<any>(
      createMockUniverAPI(['附注披露信息（上市公司）', '审定表I1-1']),
    )
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    nav.refresh()

    const note = nav.sheets.value.find((s) => s.name === '附注披露信息（上市公司）')
    const audit = nav.sheets.value.find((s) => s.name === '审定表I1-1')
    expect(note?.readonly).toBe(true)
    expect(audit?.readonly).toBe(false)
  })

  it('univerAPI 为 null 时 sheets 列表为空，无异常抛出', () => {
    const apiRef = ref<any>(null)
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
  })

  it('groups 按 priority 升序排列（覆盖 10 类）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '实质性程序表I1A', // 总控台 (2)
        '审定表I1-1', // 审定表 (3)
        '附注披露信息（上市公司）', // 附注披露 (4)
        '明细表I1-2', // 明细表 (5)
        '摊销测算表（不含减值）I1-10（剩余年限法）', // 摊销测算 (6)
        '商誉减值测试I3-6', // 减值测试 (7)
        '资本化时点判断I2-6', // 针对性检查 (8)
        '调整分录', // 调整分录 (9)
        '利息资本化测算表', // 其他程序 (10, fallback)
      ]),
    )
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    expect(priorities).toEqual([...priorities].sort((a, b) => a - b))
    // 确认所有 9 个可见 group 都呈现（索引/历史遗留默认隐藏不计）
    const cats = nav.groups.value.map((g) => g.category)
    expect(cats).toEqual([
      '总控台',
      '审定表',
      '附注披露',
      '明细表',
      '摊销测算',
      '减值测试',
      '针对性检查',
      '调整分录',
      '其他程序',
    ])
  })

  it('classifyISheet 由 composable 暴露，可直接调用', () => {
    const apiRef = ref<any>(null)
    const nav = useIIntangibleAssetSheetGroups(apiRef)
    expect(nav.classifyISheet('审定表I1-1')).toMatchObject({ category: '审定表' })
  })
})
