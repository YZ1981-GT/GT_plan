/**
 * useLedgerNavigation - 账簿穿透导航域逻辑
 *
 * 从 LedgerPenetration.vue 拆分而来，包含：
 * - 穿透层级管理（balance → ledger → voucher / aux_balance → aux_ledger）
 * - 面包屑导航
 * - 层级间钻取
 * - 键盘快捷键导航
 *
 * @domain ledger-navigation
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

// ─── 类型 ───
export type PenetrationLevel = 'balance' | 'ledger' | 'voucher' | 'aux_balance' | 'aux_ledger'

export interface BreadcrumbItem {
  label: string
  level: PenetrationLevel
  params?: Record<string, any>
}

export function useLedgerNavigation() {
  const currentLevel = ref<PenetrationLevel>('balance')
  const breadcrumbs = ref<BreadcrumbItem[]>([{ label: '余额表', level: 'balance' }])

  // 当前钻取上下文
  const drillAccountCode = ref('')
  const drillAccountName = ref('')
  const drillVoucherNo = ref('')

  function navigateTo(index: number) {
    if (index < 0 || index >= breadcrumbs.value.length) return
    const target = breadcrumbs.value[index]
    currentLevel.value = target.level
    breadcrumbs.value = breadcrumbs.value.slice(0, index + 1)
  }

  function drillToLedger(row: any) {
    drillAccountCode.value = row.account_code
    drillAccountName.value = row.account_name || row.account_code
    currentLevel.value = 'ledger'
    breadcrumbs.value.push({
      label: `${row.account_code} ${row.account_name || ''}`.trim(),
      level: 'ledger',
      params: { account_code: row.account_code },
    })
  }

  function drillToVoucher(row: any) {
    drillVoucherNo.value = row.voucher_no || row.voucher_number || ''
    currentLevel.value = 'voucher'
    breadcrumbs.value.push({
      label: `凭证 ${drillVoucherNo.value}`,
      level: 'voucher',
      params: { voucher_no: drillVoucherNo.value },
    })
  }

  function drillToAuxBalance(auxType?: string) {
    currentLevel.value = 'aux_balance'
    const label = auxType ? `辅助余额(${auxType})` : '辅助余额表'
    // 切换到辅助余额时重置面包屑
    breadcrumbs.value = [
      { label: '余额表', level: 'balance' },
      { label, level: 'aux_balance', params: { aux_type: auxType } },
    ]
  }

  function drillToAuxLedger(row: any) {
    currentLevel.value = 'aux_ledger'
    const label = row.aux_name ? `${row.aux_code} ${row.aux_name}` : (row.aux_code || '辅助明细')
    breadcrumbs.value.push({
      label,
      level: 'aux_ledger',
      params: { aux_code: row.aux_code, aux_type: row.aux_type, account_code: row.account_code },
    })
  }

  function goBack() {
    if (breadcrumbs.value.length > 1) {
      navigateTo(breadcrumbs.value.length - 2)
    }
  }

  // ─── 键盘快捷键 ───
  function onKeydown(e: KeyboardEvent) {
    // Enter/Backspace 返回上级
    if ((e.key === 'Backspace' || e.key === 'Enter') && currentLevel.value !== 'balance') {
      e.preventDefault()
      goBack()
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', onKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', onKeydown)
  })

  return {
    currentLevel,
    breadcrumbs,
    drillAccountCode,
    drillAccountName,
    drillVoucherNo,
    navigateTo,
    drillToLedger,
    drillToVoucher,
    drillToAuxBalance,
    drillToAuxLedger,
    goBack,
  }
}
