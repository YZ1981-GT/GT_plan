/**
 * useH5TitleCheck — H5-16 权属 composable
 *
 * 21列, 采矿权到期预警(<1年黄色)
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 8.3, 8.7
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TitleCheckRow {
  rowId: string
  seq: number
  assetName: string
  oilField: string
  block: string
  miningLicenseNo: string       // 采矿权证号
  licenseType: string           // 证照类型(采矿权/探矿权)
  validFrom: string             // 有效期起
  validTo: string               // 有效期止
  area: number                  // 面积(km²)
  registrar: string             // 登记机关
  ownerEntity: string           // 权属主体
  pledgeStatus: string          // 抵押状态(无/已抵押)
  pledgeAmount: number          // 抵押金额
  annualFee: number             // 年度费用
  renewalStatus: string         // 续期状态(已续期/待续期/无需续期)
  expiryWarning: boolean        // 到期预警(<1年) - computed
  verificationDoc: string       // 核验文件
  conclusion: string            // 检查结论
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-16'
const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5TitleCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<TitleCheckRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw = allResponses.value.get(`${ITEM_PREFIX}-rows`)?.remark
    if (raw) {
      try { rows.value = (JSON.parse(raw) ?? []).map(_normalize) } catch { rows.value = [] }
    } else { rows.value = [] }
    auditNote.value = (allResponses.value.get(`${ITEM_PREFIX}-audit-note`)?.remark ?? '') as string
    auditConclusion.value = (allResponses.value.get(`${ITEM_PREFIX}-audit-conclusion`)?.remark ?? '') as string
  }

  function _normalize(raw: any): TitleCheckRow {
    const validTo = raw.validTo ?? ''
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      block: raw.block ?? '',
      miningLicenseNo: raw.miningLicenseNo ?? '',
      licenseType: raw.licenseType ?? '采矿权',
      validFrom: raw.validFrom ?? '',
      validTo,
      area: Number(raw.area) || 0,
      registrar: raw.registrar ?? '',
      ownerEntity: raw.ownerEntity ?? '',
      pledgeStatus: raw.pledgeStatus ?? '无',
      pledgeAmount: Number(raw.pledgeAmount) || 0,
      annualFee: Number(raw.annualFee) || 0,
      renewalStatus: raw.renewalStatus ?? '',
      expiryWarning: _isExpiringSoon(validTo),
      verificationDoc: raw.verificationDoc ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 采矿权到期日<1年 → 黄色高亮预警 */
  function _isExpiringSoon(validTo: string): boolean {
    if (!validTo) return false
    const expiryDate = new Date(validTo).getTime()
    if (isNaN(expiryDate)) return false
    const now = Date.now()
    return expiryDate > now && (expiryDate - now) < ONE_YEAR_MS
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const expiringCount = computed(() => rows.value.filter((r) => r.expiryWarning).length)
  const pledgedCount = computed(() => rows.value.filter((r) => r.pledgeStatus === '已抵押').length)
  const totalPledgeAmount = computed(() => rows.value.reduce((sum, r) => sum + r.pledgeAmount, 0))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    rows.value.push({
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', block: '', miningLicenseNo: '', licenseType: '采矿权',
      validFrom: '', validTo: '', area: 0, registrar: '', ownerEntity: '',
      pledgeStatus: '无', pledgeAmount: 0, annualFee: 0, renewalStatus: '',
      expiryWarning: false, verificationDoc: '', conclusion: '', remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof TitleCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'validTo') {
      row.expiryWarning = _isExpiringSoon(value as string)
    }
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    expiringCount, pledgedCount, totalPledgeAmount,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
  }
}
