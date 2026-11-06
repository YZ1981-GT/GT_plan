import { nextTick, type Ref } from 'vue'
import { usePreferredFixedColumns } from '@/composables/usePreferredFixedColumns'

export const TRIAL_BALANCE_FIXED_COLUMNS = [
  { key: 'standard_account_code', label: '科目编码' },
  { key: 'account_name', label: '科目名称' },
  { key: 'direction', label: '方向' },
  { key: 'unadjusted_amount', label: '未审数' },
  { key: 'rje_adjustment', label: 'RJE调整' },
  { key: 'aje_adjustment', label: 'AJE调整' },
  { key: 'wp_adjustment', label: '底稿调整' },
  { key: 'audited_amount', label: '审定数' },
  { key: 'wp_status', label: '底稿状态' },
] as const

export function useTrialBalanceFixedColumns(tableRef: Ref<any>) {
  const fixed = usePreferredFixedColumns({
    pageKey: 'trial-balance',
    allowedColumns: TRIAL_BALANCE_FIXED_COLUMNS.map((column) => column.key),
    mandatoryColumns: ['standard_account_code', 'account_name'],
  })
  const onChange = (): void => { nextTick(() => tableRef.value?.doLayout?.()) }
  return { columns: TRIAL_BALANCE_FIXED_COLUMNS, fixed, onChange }
}
