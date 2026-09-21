/**
 * useD4CustomerDetail — D4-29 客户信息检查表 composable
 *
 * 转置表：每个客户一张信息卡片（31个检查字段）
 * 三模式：卡片视图 / 矩阵视图 / 在线编辑
 * 持久化：D4-29-customers / D4-29-note / D4-29-conclusion
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'

// ─── 检查字段定义（对齐源模板31个维度） ─────────────────────────────────

export interface FieldDef {
  key: string
  label: string
  group: string  // basic / shareholder / management / risk
  type: 'text' | 'textarea' | 'select'
  options?: string[]
}

export const CUSTOMER_FIELDS: FieldDef[] = [
  // 基本信息
  { key: 'creditCode', label: '统一社会信用代码', group: 'basic', type: 'text' },
  { key: 'regAddress', label: '注册地址', group: 'basic', type: 'text' },
  { key: 'officeAddress', label: '办公地址', group: 'basic', type: 'text' },
  { key: 'website', label: '网站地址', group: 'basic', type: 'text' },
  { key: 'websiteIp', label: '网站IP地址', group: 'basic', type: 'text' },
  { key: 'email', label: '企业邮箱', group: 'basic', type: 'text' },
  { key: 'establishDate', label: '成立时间', group: 'basic', type: 'text' },
  { key: 'registeredCapital', label: '注册资本/实缴资本', group: 'basic', type: 'text' },
  { key: 'bizScope', label: '经营范围', group: 'basic', type: 'textarea' },
  { key: 'headcount', label: '人员规模/社保缴纳人数', group: 'basic', type: 'text' },
  { key: 'legalRep', label: '法定代表人', group: 'basic', type: 'text' },
  // 股东
  { key: 'shareholder1', label: '股东1及持股比例', group: 'shareholder', type: 'text' },
  { key: 'shareholder2', label: '股东2及持股比例', group: 'shareholder', type: 'text' },
  { key: 'shareholder3', label: '股东3及持股比例', group: 'shareholder', type: 'text' },
  { key: 'shareholder4', label: '股东4及持股比例', group: 'shareholder', type: 'text' },
  { key: 'shareholder5', label: '股东5及持股比例', group: 'shareholder', type: 'text' },
  // 管理层
  { key: 'chairman', label: '董事长', group: 'management', type: 'text' },
  { key: 'gm', label: '总经理', group: 'management', type: 'text' },
  { key: 'otherMgmt', label: '其他关键管理人员', group: 'management', type: 'text' },
  { key: 'keyHandler', label: '关键经办人员', group: 'management', type: 'text' },
  // 风险判断
  { key: 'actualController', label: '实际控制人', group: 'risk', type: 'text' },
  { key: 'isRelated', label: '是否为关联方', group: 'risk', type: 'select', options: ['是', '否', '待确认'] },
  { key: 'isAlsoSupplier', label: '是否同时为供应商', group: 'risk', type: 'select', options: ['是', '否'] },
  { key: 'cooperationStart', label: '开始合作时间', group: 'risk', type: 'text' },
  { key: 'hasOverdue', label: '是否长期拖欠款项', group: 'risk', type: 'select', options: ['是', '否'] },
  { key: 'bizStatus', label: '经营状态', group: 'risk', type: 'text' },
  { key: 'isBlacklisted', label: '是否列入失信人', group: 'risk', type: 'select', options: ['是', '否'] },
  { key: 'infoSource', label: '信息来源', group: 'risk', type: 'text' },
]

export const FIELD_GROUPS = [
  { key: 'basic', label: '基本信息', color: '#f0faf0' },
  { key: 'shareholder', label: '股东信息', color: '#f0f5ff' },
  { key: 'management', label: '管理层及经办人', color: '#faf5ff' },
  { key: 'risk', label: '风险判断', color: '#fef0f0' },
]

// ─── Types ───────────────────────────────────────────────────────────

export interface CustomerItem {
  id: string
  name: string
  fields: Record<string, string>  // key → value
}

// 🔴 后端 store 里一条客户行可能只有 {id,name}（尚未填 fields 子对象，合法半成品，与后端
//    phase5_d4_ipo_interview_sheets 的「缺 fields 段 → None」容差同源）。卡片视图
//    `activeCustomer.fields[field.key]` / 矩阵视图 `cust.fields[row.key]` / relatedCount /
//    completionRate 若 fields 为 undefined 会抛 `Cannot read properties of undefined` 打挂整个
//    组件渲染（ErrorBoundary 捕获后子组件不挂载 → 在线编辑切换器不可达）。载入时统一归一
//    fields 为对象，单源杜绝（与 D4TabInterviewSummary 同型修复）。
function normalizeCustomers(raw: unknown): CustomerItem[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
    .map((c) => ({
      id: String(c.id ?? ''),
      name: String(c.name ?? ''),
      fields: (c.fields && typeof c.fields === 'object' && !Array.isArray(c.fields))
        ? (c.fields as Record<string, string>)
        : {},
    }))
}

export interface UseD4CustomerDetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  saveItems?: (items: any[]) => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────

export function useD4CustomerDetail(options: UseD4CustomerDetailOptions) {
  const { wpId, projectId, allResponses, isReadonly, saveItems } = options

  const customers = ref<CustomerItem[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let saveInFlight: Promise<void> = Promise.resolve()
  const lastError = ref<string | null>(null)

  // Load
  function loadData() {
    const r = allResponses.value.get('D4-29-customers')
    if (r?.remark) {
      try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { customers.value = normalizeCustomers(p); return } } catch {}
    }
    customers.value = []
  }
  function loadNote() {
    auditNote.value = allResponses.value.get('D4-29-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-29-conclusion')?.remark || ''
  }
  watch(() => allResponses.value.get('D4-29-customers')?.remark, loadData, { immediate: true })
  watch(() => [allResponses.value.get('D4-29-note')?.remark, allResponses.value.get('D4-29-conclusion')?.remark], loadNote, { immediate: true })

  // CRUD
  function addCustomer(name: string): CustomerItem {
    const item: CustomerItem = {
      id: `cust-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      fields: {},
    }
    customers.value.push(item)
    persistAll()
    return item
  }

  function removeCustomer(id: string) {
    if (isReadonly.value) return
    customers.value = customers.value.filter(c => c.id !== id)
    persistAll()
  }

  function updateField(customerId: string, fieldKey: string, value: string) {
    if (isReadonly.value) return
    const cust = customers.value.find(c => c.id === customerId)
    if (!cust) return
    cust.fields[fieldKey] = value
    persistAll()
  }

  function updateCustomerName(id: string, name: string) {
    if (isReadonly.value) return
    const cust = customers.value.find(c => c.id === id)
    if (cust) { cust.name = name; persistAll() }
  }

  // Stats
  const customerCount = computed(() => customers.value.length)
  const relatedCount = computed(() => customers.value.filter(c => c.fields.isRelated === '是').length)
  const completionRate = computed(() => {
    if (!customers.value.length) return 0
    const totalFields = customers.value.length * CUSTOMER_FIELDS.length
    let filled = 0
    for (const c of customers.value) {
      for (const f of CUSTOMER_FIELDS) {
        if (c.fields[f.key]?.trim()) filled++
      }
    }
    return Math.round((filled / totalFields) * 100)
  })

  // Persistence
  function persistAll() {
    allResponses.value.set('D4-29-customers', { item_id: 'D4-29-customers', conclusion: null, remark: JSON.stringify(customers.value) })
    allResponses.value.set('D4-29-note', { item_id: 'D4-29-note', conclusion: null, remark: auditNote.value })
    allResponses.value.set('D4-29-conclusion', { item_id: 'D4-29-conclusion', conclusion: null, remark: auditConclusion.value })
    debounceSave()
  }
  function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave().catch((error) => { lastError.value = error?.message || '保存失败，请重试' }) }, 2000) }
  function flushSave(): Promise<void> {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    if (!saveItems) return Promise.reject(new Error('D4-29 未提供保存宿主'))
    const keys = ['D4-29-customers', 'D4-29-note', 'D4-29-conclusion']
    const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    const operation = saveInFlight.catch(() => {}).then(() => saveItems(items)).catch((error) => { lastError.value = error?.message || '保存失败，请重试'; throw error })
    saveInFlight = operation.catch(() => {})
    return operation
  }
  function updateAuditNote(v: string) { if (isReadonly.value) return; auditNote.value = v; persistAll() }
  function updateAuditConclusion(v: string) { if (isReadonly.value) return; auditConclusion.value = v; persistAll() }
  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; void flushSave().catch(() => {}) } })

  return {
    customers, auditNote, auditConclusion, lastError,
    customerCount, relatedCount, completionRate,
    addCustomer, removeCustomer, updateField, updateCustomerName,
    updateAuditNote, updateAuditConclusion, loadData, flushPendingSave: flushSave,
  }
}

export default useD4CustomerDetail
