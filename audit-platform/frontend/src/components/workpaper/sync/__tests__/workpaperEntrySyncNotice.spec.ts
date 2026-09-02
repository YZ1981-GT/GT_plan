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
import {
  ENTRY_SYNC_NOTICE_LABEL,
  ENTRY_SYNC_NOTICE_REASON,
  ENTRY_SYNC_NOTICE_SUMMARY,
  SYNC_ADAPTER_REGISTERED_ENTRY_IDS,
  entrySyncNotice,
} from '../workpaperEntrySyncNotice'

/** D 循环 7 个独立 entry —— 与 backend/data/workpaper_sync_d_cycle_manifest_slice.json 同集合。 */
const D_CYCLE_ENTRY_IDS = [
  'xlsx/gt-d1-notes-receivable',
  'xlsx/gt-d2-accounts-receivable',
  'xlsx/gt-d3-prepaid-accounts',
  'xlsx/gt-d4-operating-revenue',
  'xlsx/gt-d5-receivables-financing',
  'xlsx/gt-d6-contract-assets',
  'xlsx/gt-d7-contract-liabilities',
] as const

describe('entrySyncNotice — 未注册 adapter 的入口必须给可操作原因（AC 1.4）', () => {
  it('D 循环 7 个 entry 全部拿到非空通知', () => {
    for (const entryId of D_CYCLE_ENTRY_IDS) {
      const notice = entrySyncNotice(entryId)
      expect(notice, entryId).not.toBeNull()
      expect(notice!.level, entryId).toBe('not_synchronized')
      expect(notice!.label, entryId).toBe(ENTRY_SYNC_NOTICE_LABEL)
      expect(notice!.summary, entryId).toBe(ENTRY_SYNC_NOTICE_SUMMARY)
      expect(notice!.reason, entryId).toBe(ENTRY_SYNC_NOTICE_REASON)
    }
  })

  it('已注册 adapter 的 entry 不再显示该警告（另一侧真分母）', () => {
    const registered = ['xlsx/gt-d2-accounts-receivable']
    expect(entrySyncNotice('xlsx/gt-d2-accounts-receivable', registered)).toBeNull()
    // 同一次调用里未登记的那些仍要有通知 —— 证明判据是逐 entry 的，不是全局开关
    expect(entrySyncNotice('xlsx/gt-d1-notes-receivable', registered)).not.toBeNull()
  })

  it('空 entryId 不产生通知（宿主没传 entry 时不挂无主警告）', () => {
    expect(entrySyncNotice('')).toBeNull()
  })

  it('当前登记表为空 —— 与 registry 的 adapter_registered=False 一致', () => {
    expect([...SYNC_ADAPTER_REGISTERED_ENTRY_IDS]).toEqual([])
  })
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
  it('挂载后真渲染标签、原因与 entry 绑定', () => {
    const wrapper = mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: 'xlsx/gt-d4-operating-revenue' },
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
    expect(tagged.attributes('data-entry-sync-notice')).toBe('xlsx/gt-d4-operating-revenue')
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
