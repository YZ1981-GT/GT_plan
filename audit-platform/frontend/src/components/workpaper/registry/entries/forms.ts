import { defineAsyncComponent } from 'vue'
import type { HtmlRendererEntry } from '../types'

/**
 * Explicit HtmlRendererEntry[] for domain: forms
 * Membership is the array itself — no startsWith classifier.
 *
 * All five D subtypes share one lazy GtDForm (form-type prop routes behavior).
 * Capability manifest generator requires componentType string literals (no .map).
 */
const GtDForm = defineAsyncComponent(() => import('../../GtDForm/GtDForm.vue'))

export const formsEntries: HtmlRendererEntry[] = [
  {
    componentType: 'd-form-table',
    component: GtDForm,
    icon: '📑',
    label: 'D 检查表 (table)',
    emits: ['save'],
    contextProps: 'form-type',
  },
  {
    componentType: 'd-form-paragraph',
    component: GtDForm,
    icon: '📄',
    label: 'D 检查表 (paragraph)',
    emits: ['save'],
    contextProps: 'form-type',
  },
  {
    componentType: 'd-form-qa',
    component: GtDForm,
    icon: '❓',
    label: 'D 检查表 (qa)',
    emits: ['save'],
    contextProps: 'form-type',
  },
  {
    componentType: 'd-form-confirmation',
    component: GtDForm,
    icon: '✉️',
    label: 'D 检查表 (confirmation)',
    emits: ['save'],
    contextProps: 'form-type',
  },
  {
    componentType: 'd-form-review',
    component: GtDForm,
    icon: '✍️',
    label: 'D 检查表 (review)',
    emits: ['save'],
    contextProps: 'form-type',
  },
  {
    componentType: 'd1-notes-receivable',
    component: defineAsyncComponent(() => import('../../GtD1NotesReceivable.vue')),
    icon: '📄',
    label: 'D1 应收票据',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd2-accounts-receivable',
    component: defineAsyncComponent(() => import('../../GtD2AccountsReceivable.vue')),
    icon: '💰',
    label: 'D2 应收账款',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd3-prepaid-accounts',
    component: defineAsyncComponent(() => import('../../GtD3PrepaidAccounts.vue')),
    icon: '💰',
    label: 'D3 预收账款',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd4-operating-revenue',
    component: defineAsyncComponent(() => import('../../GtD4OperatingRevenue.vue')),
    icon: '💹',
    label: 'D4 营业收入',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd5-receivables-financing',
    component: defineAsyncComponent(() => import('../../GtD5ReceivablesFinancing.vue')),
    icon: '📈',
    label: 'D5 应收款项融资',
    emits: ['save', 'completed', 'jump-to-section'],
    contextProps: 'standard',
  },
  {
    componentType: 'd6-contract-assets',
    component: defineAsyncComponent(() => import('../../GtD6ContractAssets.vue')),
    icon: '📋',
    label: 'D6 合同资产',
    emits: ['save', 'completed', 'jump-to-section'],
    contextProps: 'standard',
  },
  {
    componentType: 'd7-contract-liabilities',
    component: defineAsyncComponent(() => import('../../GtD7ContractLiabilities.vue')),
    icon: '📋',
    label: 'D7 合同负债',
    emits: ['save', 'completed', 'jump-to-section'],
    contextProps: 'standard',
  },
]
