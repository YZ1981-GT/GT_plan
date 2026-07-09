/**
 * useH1TitleCheck — H1-16~17 权属检查 composable
 *
 * BuildingRow 22列 + VehicleRow 18列
 * 权属异常判定 + 抵押统计 + 差异计算
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.15
 * Requirements: 14.1-14.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 房屋建筑物权属行 (H1-16, 22列) */
export interface BuildingRow {
  rowId: string
  seq: number                    // 序号
  name: string                   // 资产名称
  address: string                // 坐落地址
  buildingArea: number           // 建筑面积(m²)
  landArea: number               // 土地面积(m²)
  titleCertNo: string            // 产权证号
  issueDate: string              // 发证日期
  owner: string                  // 权利人
  isOwnerEntity: string          // 权利人是否为被审计单位(Y/N)
  usage: string                  // 用途
  isMortgaged: string            // 是否抵押(Y/N)
  mortgagee: string              // 抵押权人
  mortgageAmount: number         // 抵押金额
  mortgageExpiry: string         // 抵押到期日
  completionDate: string         // 在建转固日期
  bookValue: number              // 账面原值
  certValue: number              // 产权证载原值
  difference: number             // 差异（公式）
  diffReason: string             // 差异原因
  isRestricted: string           // 是否限制(Y/N)
  conclusion: string             // 结论
  remark: string                 // 备注
}

/** 运输设备权属行 (H1-17, 18列) */
export interface VehicleRow {
  rowId: string
  seq: number                    // 序号
  name: string                   // 车辆名称
  plateNo: string                // 车牌号
  vinNo: string                  // 车架号
  engineNo: string               // 发动机号
  drivingLicenseNo: string       // 行驶证号
  regCertNo: string              // 登记证号
  regDate: string                // 登记日期
  owner: string                  // 所有人
  isOwnerEntity: string          // 所有人是否为被审计单位(Y/N)
  useNature: string              // 使用性质
  isMortgaged: string            // 是否抵押(Y/N)
  bookValue: number              // 账面原值
  regValue: number               // 登记载明价值
  difference: number             // 差异（公式）
  inspectionStatus: string       // 年检状态(已通过/未通过/已过期)
  conclusion: string             // 结论
  remark: string                 // 备注
}

/** 权属汇总统计 */
export interface TitleStatistics {
  totalChecked: number           // 已检查资产数
  ownerAnomalyCount: number      // 权属异常数
  mortgagedCount: number         // 抵押资产数
  mortgageAmountTotal: number    // 抵押金额合计
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_16 = 'H1-16'
const ITEM_PREFIX_17 = 'H1-17'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1TitleCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const buildingRows = ref<BuildingRow[]>([])
  const vehicleRows = ref<VehicleRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const bItem = allResponses.value.get(`${ITEM_PREFIX_16}-rows`)
    if (bItem?.remark) {
      try {
        const parsed = JSON.parse(bItem.remark)
        buildingRows.value = Array.isArray(parsed) ? parsed.map(_normalizeBuildingRow) : []
      } catch { buildingRows.value = [] }
    } else { buildingRows.value = [] }

    const vItem = allResponses.value.get(`${ITEM_PREFIX_17}-rows`)
    if (vItem?.remark) {
      try {
        const parsed = JSON.parse(vItem.remark)
        vehicleRows.value = Array.isArray(parsed) ? parsed.map(_normalizeVehicleRow) : []
      } catch { vehicleRows.value = [] }
    } else { vehicleRows.value = [] }

    auditNote.value = _getString(`${ITEM_PREFIX_16}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX_16}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeBuildingRow(raw: any, idx: number): BuildingRow {
    const bookVal = Number(raw.bookValue) || 0
    const certVal = Number(raw.certValue) || 0
    return {
      rowId: raw.rowId ?? `bld-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      address: raw.address ?? '',
      buildingArea: Number(raw.buildingArea) || 0,
      landArea: Number(raw.landArea) || 0,
      titleCertNo: raw.titleCertNo ?? '',
      issueDate: raw.issueDate ?? '',
      owner: raw.owner ?? '',
      isOwnerEntity: raw.isOwnerEntity ?? 'Y',
      usage: raw.usage ?? '',
      isMortgaged: raw.isMortgaged ?? 'N',
      mortgagee: raw.mortgagee ?? '',
      mortgageAmount: Number(raw.mortgageAmount) || 0,
      mortgageExpiry: raw.mortgageExpiry ?? '',
      completionDate: raw.completionDate ?? '',
      bookValue: bookVal,
      certValue: certVal,
      difference: bookVal - certVal,
      diffReason: raw.diffReason ?? '',
      isRestricted: raw.isRestricted ?? 'N',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeVehicleRow(raw: any, idx: number): VehicleRow {
    const bookVal = Number(raw.bookValue) || 0
    const regVal = Number(raw.regValue) || 0
    return {
      rowId: raw.rowId ?? `veh-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      plateNo: raw.plateNo ?? '',
      vinNo: raw.vinNo ?? '',
      engineNo: raw.engineNo ?? '',
      drivingLicenseNo: raw.drivingLicenseNo ?? '',
      regCertNo: raw.regCertNo ?? '',
      regDate: raw.regDate ?? '',
      owner: raw.owner ?? '',
      isOwnerEntity: raw.isOwnerEntity ?? 'Y',
      useNature: raw.useNature ?? '',
      isMortgaged: raw.isMortgaged ?? 'N',
      bookValue: bookVal,
      regValue: regVal,
      difference: bookVal - regVal,
      inspectionStatus: raw.inspectionStatus ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 统计 ────────────────────────────────────────────────────────

  const buildingStats = computed<TitleStatistics>(() => {
    const totalChecked = buildingRows.value.length
    const ownerAnomalyCount = buildingRows.value.filter((r) => r.isOwnerEntity === 'N').length
    const mortgagedList = buildingRows.value.filter((r) => r.isMortgaged === 'Y')
    return {
      totalChecked,
      ownerAnomalyCount,
      mortgagedCount: mortgagedList.length,
      mortgageAmountTotal: calcSubtotal(mortgagedList.map((r) => r.mortgageAmount)),
    }
  })

  const vehicleStats = computed<TitleStatistics>(() => {
    const totalChecked = vehicleRows.value.length
    const ownerAnomalyCount = vehicleRows.value.filter((r) => r.isOwnerEntity === 'N').length
    const mortgagedList = vehicleRows.value.filter((r) => r.isMortgaged === 'Y')
    return {
      totalChecked,
      ownerAnomalyCount,
      mortgagedCount: mortgagedList.length,
      mortgageAmountTotal: calcSubtotal(mortgagedList.map((r) => r.bookValue)), // 车辆以账面值估算
    }
  })

  // ─── CRUD: Buildings ───────────────────────────────────────────────────────

  function addBuildingRow(name: string): void {
    const newRow: BuildingRow = {
      rowId: `bld-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: buildingRows.value.length + 1,
      name, address: '', buildingArea: 0, landArea: 0,
      titleCertNo: '', issueDate: '', owner: '', isOwnerEntity: 'Y',
      usage: '', isMortgaged: 'N', mortgagee: '', mortgageAmount: 0,
      mortgageExpiry: '', completionDate: '',
      bookValue: 0, certValue: 0, difference: 0, diffReason: '',
      isRestricted: 'N', conclusion: '', remark: '',
    }
    buildingRows.value.push(newRow)
    _persistBuildings()
  }

  function removeBuildingRow(rowId: string): void {
    const idx = buildingRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      buildingRows.value.splice(idx, 1)
      buildingRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistBuildings()
    }
  }

  function updateBuildingCell(rowId: string, field: keyof BuildingRow, value: any): void {
    const row = buildingRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算差异
    row.difference = row.bookValue - row.certValue
    _persistBuildings()
  }

  // ─── CRUD: Vehicles ────────────────────────────────────────────────────────

  function addVehicleRow(name: string): void {
    const newRow: VehicleRow = {
      rowId: `veh-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: vehicleRows.value.length + 1,
      name, plateNo: '', vinNo: '', engineNo: '',
      drivingLicenseNo: '', regCertNo: '', regDate: '',
      owner: '', isOwnerEntity: 'Y', useNature: '', isMortgaged: 'N',
      bookValue: 0, regValue: 0, difference: 0,
      inspectionStatus: '', conclusion: '', remark: '',
    }
    vehicleRows.value.push(newRow)
    _persistVehicles()
  }

  function removeVehicleRow(rowId: string): void {
    const idx = vehicleRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      vehicleRows.value.splice(idx, 1)
      vehicleRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistVehicles()
    }
  }

  function updateVehicleCell(rowId: string, field: keyof VehicleRow, value: any): void {
    const row = vehicleRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.difference = row.bookValue - row.regValue
    _persistVehicles()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistBuildings(): void {
    options?.onSave?.(`${ITEM_PREFIX_16}-rows`, buildingRows.value)
  }

  function _persistVehicles(): void {
    options?.onSave?.(`${ITEM_PREFIX_17}-rows`, vehicleRows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_16}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX_16}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    buildingRows,
    vehicleRows,
    auditNote,
    auditConclusion,
    buildingStats,
    vehicleStats,
    addBuildingRow,
    removeBuildingRow,
    updateBuildingCell,
    addVehicleRow,
    removeVehicleRow,
    updateVehicleCell,
    saveNote,
    saveConclusion,
  }
}

export default useH1TitleCheck
