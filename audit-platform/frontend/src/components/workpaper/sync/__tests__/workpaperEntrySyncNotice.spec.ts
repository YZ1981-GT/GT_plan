// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 46 收口
//
// AC 1.4 的 UI 义务判据：**未注册 adapter 的入口必须显示可操作原因**。
//
// Validates: Requirements 1.4
//
// ═══ 两侧都要有真分母 ═══
//
// `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 当前是空集合（registry 里四条 pilot 全部
// `adapter_registered: False`）。如果只断言「D 循环 entry 拿到通知」，那么把函数改成
// `return NOTICE` 恒返回也照样绿 —— 那就是空分母重言式。所以 `entrySyncNotice` 留了
// 第二个参数，测试在**已注册**分支上也给真输入，两个方向都锁：
//   未注册 ⇒ 必须有通知（否则审计师看不到两侧不互通）
//   已注册 ⇒ 必须没有通知（否则真接上双向后还在挂假警告）
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import GtEntrySyncCapabilityNotice from '../GtEntrySyncCapabilityNotice.vue'
import { WORKPAPER_SYNC_MANIFEST } from '../workpaperSyncManifest.generated'
import {
  ENTRY_SYNC_NOTICE_LABEL,
  ENTRY_SYNC_NOTICE_REASON,
  ENTRY_SYNC_NOTICE_SUMMARY,
  SYNC_ADAPTER_REGISTERED_ENTRY_IDS,
  entrySyncNotice,
} from '../workpaperEntrySyncNotice'

/**
 * D 循环**尚未接通**双向回写的 entry —— 从 manifest **现算**，不再手写清单。
 *
 * 🔴 2026-09-22：原来这是个手写数组，里面钉着 `'xlsx/gt-d4-operating-revenue'`。
 * 而 D4 早已在 manifest 里 `capability=bidirectional`，于是这条守卫**把缺陷写进了判据**
 * —— 它断言「D4 必须显示两侧数据未互通」，反过来保护了生产侧那个硬编码登记表漏登记
 * D4/G7/H1 的 bug。用户在 D4-2 上实测撞到红字后才暴露。
 *
 * 教训：**判据里的成员清单只要是手写的，就会在事实变化时变成「保护缺陷的判据」**。
 * 现在两侧分母都从同一真源（generated manifest）现算：
 *   未接通（capability ≠ bidirectional）⇒ 必须有通知
 *   已接通（capability === bidirectional）⇒ 必须没有通知
 * 两侧都非空由下方 `toBeGreaterThan(0)` 锁死，避免退化成空分母重言式。
 */
const D_CYCLE_ENTRY_PREFIXES = [
  'xlsx/gt-d1-',
  'xlsx/gt-d3-',
  'xlsx/gt-d4-',
  'xlsx/gt-d5-',
  'xlsx/gt-d6-',
  'xlsx/gt-d7-',
] as const

const D_CYCLE_NOT_WIRED_ENTRY_IDS: readonly string[] = WORKPAPER_SYNC_MANIFEST.filter(
  (e) =>
    e.capability !== 'bidirectional'
    && D_CYCLE_ENTRY_PREFIXES.some((p) => e.entryId.startsWith(p)),
).map((e) => e.entryId)

describe('entrySyncNotice — 未注册 adapter 的入口必须给可操作原因（AC 1.4）', () => {
  it('尚未接通的 D 循环 entry 全部拿到非空通知', () => {
    expect(D_CYCLE_NOT_WIRED_ENTRY_IDS.length, '未接通侧分母不得为空').toBeGreaterThan(0)
    for (const entryId of D_CYCLE_NOT_WIRED_ENTRY_IDS) {
      const notice = entrySyncNotice(entryId)
      expect(notice, entryId).not.toBeNull()
      expect(notice!.level, entryId).toBe('not_synchronized')
      expect(notice!.label, entryId).toBe(ENTRY_SYNC_NOTICE_LABEL)
      expect(notice!.summary, entryId).toBe(ENTRY_SYNC_NOTICE_SUMMARY)
      expect(notice!.reason, entryId).toBe(ENTRY_SYNC_NOTICE_REASON)
    }
  })

  it('已接通的 entry 不再显示该警告（读生产常量，不自造分母）', () => {
    // 分母取**生产常量本身** —— 若有人把 D2 从常量里删掉，这条会红。
    expect(SYNC_ADAPTER_REGISTERED_ENTRY_IDS.length).toBeGreaterThan(0)
    for (const entryId of SYNC_ADAPTER_REGISTERED_ENTRY_IDS) {
      expect(entrySyncNotice(entryId), entryId).toBeNull()
    }
    // 逐 entry 判定而非全局开关：同一次调用里未接通的仍要有通知
    expect(entrySyncNotice('xlsx/gt-d1-notes-receivable')).not.toBeNull()
  })

  it('D2 已接通 —— 它必须在已注册集合里且不出警告', () => {
    expect([...SYNC_ADAPTER_REGISTERED_ENTRY_IDS]).toContain(
      'xlsx/gt-d2-accounts-receivable',
    )
    expect(entrySyncNotice('xlsx/gt-d2-accounts-receivable')).toBeNull()
  })

  it('登记表与 manifest 的 bidirectional 集合逐项一致（禁止第二个真源）', () => {
    // 🔴 2026-09-22 新增。修的缺陷是「生产侧手写数组只有 D2，漏了 manifest 里同为
    //    bidirectional 的 D4/G7/H1，于是三个真双向底稿常显『两侧数据未互通』」。
    //    这条判据直接锁死「登记表 === manifest 现算」，任何一侧再漂移都打红。
    //    变异反证：把生产侧改回 `['xlsx/gt-d2-accounts-receivable']` 立刻红。
    const fromManifest = WORKPAPER_SYNC_MANIFEST.filter(
      (e) => e.capability === 'bidirectional',
    ).map((e) => e.entryId)
    expect(fromManifest.length, 'manifest 里必须有 bidirectional entry').toBeGreaterThan(0)
    expect([...SYNC_ADAPTER_REGISTERED_ENTRY_IDS].sort()).toEqual([...fromManifest].sort())
  })

  it('D4/G7/H1 这三个真双向 entry 不得再出「两侧数据未互通」', () => {
    // 用户真栈实测撞到的正是 D4-2（entry xlsx/gt-d4-operating-revenue）。
    // 这条按 entry_id 逐个点名，即使上面那条一致性判据被人放宽，这三个也不许回退。
    for (const entryId of [
      'xlsx/gt-d4-operating-revenue',
      'xlsx/gt-g7-long-term-equity-main',
      'xlsx/gt-h1-fixed-assets',
    ]) {
      expect(entrySyncNotice(entryId), entryId).toBeNull()
    }
  })

  it('空 entryId 不产生通知（宿主没传 entry 时不挂无主警告）', () => {
    expect(entrySyncNotice('')).toBeNull()
  })

  // 🔴 这里曾有一条 `expect([...SYNC_ADAPTER_REGISTERED_ENTRY_IDS]).toEqual([])`。
  // 它把「空集合」锁成了基线 ⇒ 一旦真接通某个 entry（把它加进常量），测试反而打红，
  // 于是这条断言实际在**阻止**能力上线，同时让「恒显未互通」看起来是通过状态。
  // 这是假绿第③源（守卫把错值当基线锁死）的标准形态，已随 D2 接通一并删除。
  // 现在的判据是逐 entry 的行为等值（见上面两条），不锁集合的具体长度。
})

describe('可操作原因的内容判据', () => {
  it('两侧都点名、并说清互不同步与该怎么做', () => {
    // 现状：两个存储各自是什么
    expect(ENTRY_SYNC_NOTICE_REASON).toContain('结构化视图')
    expect(ENTRY_SYNC_NOTICE_REASON).toContain('在线编辑')
    expect(ENTRY_SYNC_NOTICE_REASON).toContain('checklist_responses')
    // 后果：不同步
    expect(ENTRY_SYNC_NOTICE_REASON).toContain('互不同步')
    // 动作：现在该怎么做
    expect(ENTRY_SYNC_NOTICE_REASON).toContain('只在该侧录入')
  })

  it('常显摘要一行说清「各自独立、互不同步」', () => {
    expect(ENTRY_SYNC_NOTICE_SUMMARY).toContain('结构化视图')
    expect(ENTRY_SYNC_NOTICE_SUMMARY).toContain('在线编辑')
    expect(ENTRY_SYNC_NOTICE_SUMMARY).toContain('互不同步')
    // 常显位不能太长，否则挤爆工具栏 ⇒ 作者会退回「只放 tooltip」
    expect(ENTRY_SYNC_NOTICE_SUMMARY.length).toBeLessThanOrEqual(40)
  })

  it('不得出现笼统成功态文案', () => {
    for (const forbidden of ['同步成功', '已同步', '可双向回写', '双向同步']) {
      expect(ENTRY_SYNC_NOTICE_REASON).not.toContain(forbidden)
      expect(ENTRY_SYNC_NOTICE_SUMMARY).not.toContain(forbidden)
      expect(ENTRY_SYNC_NOTICE_LABEL).not.toContain(forbidden)
    }
  })
})

describe('GtEntrySyncCapabilityNotice — DOM 侧判据', () => {
  /**
   * DOM 判据的样本 entry 必须**真的未接通**，从 manifest 现算取第一条。
   *
   * 🔴 2026-09-22：原来这里写死 `'xlsx/gt-d4-operating-revenue'`，而 D4 已是
   * `bidirectional` ⇒ 该判据同样在保护缺陷（断言真双向 entry 要渲染「未互通」标签）。
   */
  const sampleNotWiredEntryId = D_CYCLE_NOT_WIRED_ENTRY_IDS[0]

  it('挂载后真渲染标签、原因与 entry 绑定', () => {
    expect(sampleNotWiredEntryId, '需要一个真未接通的样本 entry').toBeTruthy()
    const wrapper = mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: sampleNotWiredEntryId },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })

    // 标签文案真出现在 DOM 里（不是只在 computed 里算了一遍）
    expect(wrapper.text()).toContain(ENTRY_SYNC_NOTICE_LABEL)
    // 🔴 常显摘要必须**不 hover 就在 DOM 里** —— tooltip 内容是 teleport + 仅 hover 后
    //    才挂载，只放 tooltip 等于「默认看不见的原因」，AC 1.4 不算兑现。
    expect(wrapper.text()).toContain(ENTRY_SYNC_NOTICE_SUMMARY)
    // entry 绑定真落到属性上 —— 模板漏掉 :data-entry-sync-notice 即红
    const tagged = wrapper.find('[data-entry-sync-notice]')
    expect(tagged.exists()).toBe(true)
    expect(tagged.attributes('data-entry-sync-notice')).toBe(sampleNotWiredEntryId)
    // 完整原因挂在 tooltip 触发器上（hover 后展开），触发器本身必须存在
    expect(wrapper.find('.entry-sync-notice__summary').exists()).toBe(true)

    wrapper.unmount()
  })

  it('已注册 entry（假想）不渲染任何标签 —— 组件不是恒显', () => {
    // 组件读的是模块默认登记表，故用「不在 D 集合里的空 id」验证 v-if 真起作用
    const wrapper = mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: '' },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    expect(wrapper.find('[data-entry-sync-notice]').exists()).toBe(false)
    expect(wrapper.text().trim()).toBe('')
    wrapper.unmount()
  })
})
