/**
 * useH1TitleCheck — H1-16~17 权属检查 composable
 *
 * H1-16 BuildingRow：财务账面 | 权证记载 | 抵押情况（对齐 Excel 三区）
 * H1-17 VehicleRow：登记证/行驶证 + 年检 + 抵押
 * 权属异常判定 + 抵押统计 + 净值/差异计算
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.15
 * Requirements: 14.1-14.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 房屋建筑物权属行 (H1-16，对齐 Excel 财务账面/权证/抵押三区) */
export interface BuildingRow {
  rowId: string
  seq: number
  // —— 财务账面记录 ——
  assetCode: string              // 资产编号（勾稽 H1-2）
  name: string                   // 资产名称
  bookValue: number              // 原值
  accumDep: number               // 累计折旧
  impairment: number             // 减值准备
  netValue: number               // 净值（公式）= 原值 - 累计折旧 - 减值
  // —— 权证记载 ——
  titleCertNo: string            // 权证编号
  owner: string                  // 房屋所有权人/权利人
  coOwnership: string            // 共有情况
  address: string                // 房屋坐落
  issueDate: string              // 登记时间
  propertyNature: string         // 房屋性质/权利类型
  usage: string                  // 规划用途
  buildingArea: number           // 建筑面积(m²)
  landArea: number               // 土地面积(m²)
  usefulLife: string             // 使用年限/使用期限
  issuingAuthority: string       // 颁发单位
  otherRights: string            // 他项权利
  certCopyIndex: string          // 权证复印件索引
  isOwnerEntity: string          // 权利人是否为被审计单位(Y/N)
  // —— 抵押情况 ——
  isMortgaged: string            // 是否抵押受限(Y/N)
  mortgageArea: number           // 抵押面积
  mortgageAmount: number         // 抵押价值
  mortgageNature: string         // 抵押性质
  mortgagee: string              // 抵押权人
  mortgageExpiry: string         // 抵押到期日
  isRestricted: string           // 是否其他限制(Y/N)（查封等）
  // —— 未办证 / 在建转固 ——
  fromCip: string                // 是否在建转固(Y/N)
  completionDate: string         // 在建转固日期
  expectedCertDate: string       // 预计办证日期
  cipNote: string                // 办证进度说明
  // —— 核对与结论 ——
  certValue: number              // 产权证载价值（可选；房地产权证通常无此字段）
  difference: number             // 差异（公式）= 账面原值 - 证载价值
  diffReason: string             // 差异原因
  checkConclusion: string        // 核对结论(相符/不符/未取得权证)
  conclusion: string             // 结论（兼容旧字段）
  remark: string                 // 备注
  ocrResult: string              // OCR原始识别JSON（审计轨迹）
}

/** 运输设备权属行 (H1-17) */
export interface VehicleRow {
  rowId: string
  seq: number                    // 序号
  assetCode: string              // 资产编号（勾稽 H1-2）
  name: string                   // 车辆名称
  plateNo: string                // 车牌号/机动车登记编号
  vinNo: string                  // 车架号/VIN
  engineNo: string               // 发动机号
  drivingLicenseNo: string       // 行驶证号
  regCertNo: string              // 登记证号
  regDate: string                // 登记/发证日期
  regRemarks: string             // 登记栏（变更/抵押/查封）
  owner: string                  // 所有人
  isOwnerEntity: string          // 所有人是否为被审计单位(Y/N)
  useNature: string              // 使用性质
  isMortgaged: string            // 是否抵押(Y/N)
  mortgageAmount: number         // 抵押价值
  mortgageNature: string         // 抵押性质
  bookValue: number              // 账面原值
  regValue: number               // 登记载明价值
  difference: number             // 差异（公式）
  inspectionExpiry: string       // 年检截止日
  inspectionStatus: string       // 年检状态(已通过/未通过/已过期)
  checkConclusion: string        // 核对结论(相符/不符/未取得权证)
  conclusion: string             // 结论（兼容旧字段）
  remark: string                 // 备注/索引
}

/** 权属汇总统计 */
export interface TitleStatistics {
  totalChecked: number           // 已检查资产数
  ownerAnomalyCount: number      // 权属异常数
  mortgagedCount: number         // 抵押资产数
  mortgageAmountTotal: number    // 抵押金额合计
  mismatchCount: number          // 不符/未取得权证数
  restrictedCount: number        // 其他限制数
  bookNetTotal: number           // 账面净值合计
  uncertifiedCipCount: number    // 未办证在建转固数
  uncertifiedCipNetTotal: number // 未办证在建转固净值合计
}

/** 判定是否为「未办证在建转固」：在建转固且尚无有效权证 */
export function isUncertifiedCipBuilding(row: BuildingRow): boolean {
  const fromCip = row.fromCip === 'Y' || !!(row.completionDate || '').trim()
  if (!fromCip) return false
  if (row.checkConclusion === '未取得权证') return true
  return !(row.titleCertNo || '').trim()
}

/** 运输设备权证 OCR 可回填字段标签（H1-17 确认弹窗用） */
export const H1_VEHICLE_OCR_FIELD_LABELS: Record<string, string> = {
  plateNo: '号牌号码',
  vinNo: '车架号/VIN',
  engineNo: '发动机号',
  drivingLicenseNo: '行驶证号',
  regCertNo: '登记证书编号',
  regDate: '登记日期',
  owner: '所有人',
  useNature: '使用性质',
  inspectionExpiry: '年检截止日',
  regRemarks: '登记栏备注',
}

/** 权证 OCR 可回填字段标签（确认弹窗用） */
export const H1_PROPERTY_OCR_FIELD_LABELS: Record<string, string> = {
  titleCertNo: '权证编号',
  owner: '权利人',
  coOwnership: '共有情况',
  address: '房屋坐落',
  issueDate: '登记时间',
  propertyNature: '权利类型',
  usage: '规划用途',
  buildingArea: '建筑面积',
  landArea: '土地面积',
  usefulLife: '使用期限',
  issuingAuthority: '颁发单位',
  otherRights: '他项权利',
  mortgagee: '抵押权人',
  mortgageNature: '抵押性质',
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_16 = 'H1-16'
const ITEM_PREFIX_17 = 'H1-17'

/** H1-2 明细中视为「运输设备」的分类关键词 */
const TRANSPORT_CATEGORY_KEYS = ['运输设备', '运输工具', '交通运输设备', '车辆', '汽车']
/** H1-2 明细中视为「房屋建筑物」的分类关键词 */
const BUILDING_CATEGORY_KEYS = ['房屋建筑物', '房屋及建筑物', '房屋', '建筑物', '房产', '不动产']

function _calcNet(book: number, dep: number, impair: number): number {
  return book - dep - impair
}

function _safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 判断资产分类是否为运输设备 */
export function isTransportCategory(category: string | null | undefined): boolean {
  const c = (category || '').trim()
  if (!c) return false
  return TRANSPORT_CATEGORY_KEYS.some((k) => c.includes(k))
}

/** 判断资产分类是否为房屋建筑物 */
export function isBuildingCategory(category: string | null | undefined): boolean {
  const c = (category || '').trim()
  if (!c) return false
  return BUILDING_CATEGORY_KEYS.some((k) => c.includes(k))
}

/** 年检截止日是否早于（不含等于）资产负债表日 → 视为过期 */
export function isInspectionExpiredBeforePeriodEnd(
  inspectionExpiry: string | null | undefined,
  periodEnd: string | null | undefined,
): boolean {
  if (!inspectionExpiry || !periodEnd) return false
  const exp = Date.parse(String(inspectionExpiry).slice(0, 10))
  const end = Date.parse(String(periodEnd).slice(0, 10))
  if (!Number.isFinite(exp) || !Number.isFinite(end)) return false
  return exp < end
}

/** H1-2 明细行（导入用最小字段） */
export interface H12DetailSeed {
  rowId?: string
  category?: string
  name?: string
  assetNo?: string
  originalCostEnd?: number
  accDepEnd?: number
  impairmentEnd?: number
  netValue?: number
  spec?: string
}

/** 从 allResponses 读取 H1-2 运输设备明细 */
export function getTransportDetailSeeds(allResponses: Map<string, any>): H12DetailSeed[] {
  const item = allResponses.get('H1-2-rows')
  const rows = _safeParseRows<H12DetailSeed>(item?.remark)
  return rows.filter((r) => isTransportCategory(r.category))
}

/** 从 allResponses 读取 H1-2 房屋建筑物明细 */
export function getBuildingDetailSeeds(allResponses: Map<string, any>): H12DetailSeed[] {
  const item = allResponses.get('H1-2-rows')
  const rows = _safeParseRows<H12DetailSeed>(item?.remark)
  return rows.filter((r) => isBuildingCategory(r.category))
}

/** H1-2 行 → H1-17 VehicleRow */
export function mapDetailSeedToVehicleRow(seed: H12DetailSeed, seq: number): VehicleRow {
  const bookVal = Number(seed.originalCostEnd) || 0
  return {
    rowId: `veh-h12-${seed.rowId || Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    assetCode: seed.assetNo ?? '',
    name: seed.name || seed.spec || '未命名车辆',
    plateNo: '',
    vinNo: '',
    engineNo: '',
    drivingLicenseNo: '',
    regCertNo: '',
    regDate: '',
    regRemarks: '',
    owner: '',
    isOwnerEntity: 'Y',
    useNature: '',
    isMortgaged: 'N',
    mortgageAmount: 0,
    mortgageNature: '',
    bookValue: bookVal,
    regValue: 0,
    difference: bookVal,
    inspectionExpiry: '',
    inspectionStatus: '',
    checkConclusion: '',
    conclusion: '',
    remark: '来源:H1-2',
  }
}

/** H1-2 行 → H1-16 BuildingRow */
export function mapDetailSeedToBuildingRow(seed: H12DetailSeed, seq: number): BuildingRow {
  const bookVal = Number(seed.originalCostEnd) || 0
  const accumDep = Number(seed.accDepEnd) || 0
  const impairment = Number(seed.impairmentEnd) || 0
  const netValue = seed.netValue != null
    ? Number(seed.netValue) || 0
    : _calcNet(bookVal, accumDep, impairment)
  return {
    rowId: `bld-h12-${seed.rowId || Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    assetCode: seed.assetNo ?? '',
    name: seed.name || seed.spec || '未命名建筑物',
    bookValue: bookVal,
    accumDep,
    impairment,
    netValue,
    titleCertNo: '',
    owner: '',
    coOwnership: '',
    address: '',
    issueDate: '',
    propertyNature: '',
    usage: '',
    buildingArea: 0,
    landArea: 0,
    usefulLife: '',
    issuingAuthority: '',
    otherRights: '',
    certCopyIndex: '',
    isOwnerEntity: 'Y',
    isMortgaged: 'N',
    mortgageArea: 0,
    mortgageAmount: 0,
    mortgageNature: '',
    mortgagee: '',
    mortgageExpiry: '',
    isRestricted: 'N',
    fromCip: 'N',
    completionDate: '',
    expectedCertDate: '',
    cipNote: '',
    certValue: 0,
    difference: bookVal,
    diffReason: '',
    checkConclusion: '',
    conclusion: '',
    remark: '来源:H1-2',
    ocrResult: '',
  }
}

type DisclosureRestrictedRow = {
  rowId?: string
  remark?: string
  name?: string
  amount?: number
  description?: string
}

/** 抵押车辆 → 附注「受限资产」动态行 */
export function mapMortgagedVehiclesToDisclosureRows(rows: VehicleRow[]): DisclosureRestrictedRow[] {
  return rows
    .filter((r) => r.isMortgaged === 'Y')
    .map((r, i) => {
      const amount = r.mortgageAmount > 0 ? r.mortgageAmount : (r.bookValue || 0)
      return {
        rowId: `disc-h117-${r.rowId || i}`,
        name: [r.assetCode, r.name, r.plateNo].filter(Boolean).join(' ') || `抵押运输设备-${i + 1}`,
        amount,
        description: [
          '权利限制:抵押',
          r.mortgageNature ? `性质:${r.mortgageNature}` : '',
          r.plateNo ? `登记编号:${r.plateNo}` : '',
          r.vinNo ? `VIN:${r.vinNo}` : '',
          amount ? `抵押/账面金额:${amount.toLocaleString('zh-CN')}` : '',
        ].filter(Boolean).join('；'),
        remark: '来源:H1-17',
      }
    })
}

/** 抵押房屋 → 附注「受限资产」动态行 */
export function mapMortgagedBuildingsToDisclosureRows(rows: BuildingRow[]): DisclosureRestrictedRow[] {
  return rows
    .filter((r) => r.isMortgaged === 'Y')
    .map((r, i) => {
      const amount = r.mortgageAmount > 0 ? r.mortgageAmount : (r.netValue || r.bookValue || 0)
      return {
        rowId: `disc-h116-${r.rowId || i}`,
        name: [r.assetCode, r.name, r.address].filter(Boolean).join(' ') || `抵押房屋-${i + 1}`,
        amount,
        description: [
          '权利限制:抵押',
          r.mortgageNature ? `性质:${r.mortgageNature}` : '',
          r.mortgagee ? `抵押权人:${r.mortgagee}` : '',
          r.mortgageArea ? `抵押面积:${r.mortgageArea}㎡` : '',
          r.titleCertNo ? `权证:${r.titleCertNo}` : '',
          amount ? `抵押/账面金额:${amount.toLocaleString('zh-CN')}` : '',
        ].filter(Boolean).join('；'),
        remark: '来源:H1-16',
      }
    })
}

/**
 * 将权属底稿抵押行合并进附注受限子节：按来源标记替换，保留其他来源行。
 */
export function mergeRestrictedDisclosureRows(
  existing: DisclosureRestrictedRow[],
  fromSource: DisclosureRestrictedRow[],
  sourceTag: string,
) {
  const kept = (existing || []).filter((r) => !(r.remark || '').includes(sourceTag))
  return [...kept, ...fromSource]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1TitleCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    /** 资产负债表日 YYYY-MM-DD，用于年检过期判定 */
    periodEnd?: Ref<string>
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
    const accumDep = Number(raw.accumDep) || 0
    const impairment = Number(raw.impairment) || 0
    const certVal = Number(raw.certValue) || 0
    const netValue = raw.netValue != null
      ? Number(raw.netValue) || 0
      : _calcNet(bookVal, accumDep, impairment)
    return {
      rowId: raw.rowId ?? `bld-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      assetCode: raw.assetCode ?? '',
      name: raw.name ?? '',
      bookValue: bookVal,
      accumDep,
      impairment,
      netValue,
      titleCertNo: raw.titleCertNo ?? '',
      owner: raw.owner ?? '',
      coOwnership: raw.coOwnership ?? '',
      address: raw.address ?? '',
      issueDate: raw.issueDate ?? '',
      propertyNature: raw.propertyNature ?? '',
      usage: raw.usage ?? '',
      buildingArea: Number(raw.buildingArea) || 0,
      landArea: Number(raw.landArea) || 0,
      usefulLife: raw.usefulLife ?? '',
      issuingAuthority: raw.issuingAuthority ?? '',
      otherRights: raw.otherRights ?? '',
      certCopyIndex: raw.certCopyIndex ?? '',
      isOwnerEntity: raw.isOwnerEntity ?? 'Y',
      isMortgaged: raw.isMortgaged ?? 'N',
      mortgageArea: Number(raw.mortgageArea) || 0,
      mortgageAmount: Number(raw.mortgageAmount) || 0,
      mortgageNature: raw.mortgageNature ?? '',
      mortgagee: raw.mortgagee ?? '',
      mortgageExpiry: raw.mortgageExpiry ?? '',
      isRestricted: raw.isRestricted ?? 'N',
      fromCip: raw.fromCip ?? (raw.completionDate ? 'Y' : 'N'),
      completionDate: raw.completionDate ?? '',
      expectedCertDate: raw.expectedCertDate ?? '',
      cipNote: raw.cipNote ?? '',
      certValue: certVal,
      difference: bookVal - certVal,
      diffReason: raw.diffReason ?? '',
      checkConclusion: raw.checkConclusion ?? raw.conclusion ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      ocrResult: raw.ocrResult ?? '',
    }
  }

  function _normalizeVehicleRow(raw: any, idx: number): VehicleRow {
    const bookVal = Number(raw.bookValue) || 0
    const regVal = Number(raw.regValue) || 0
    return {
      rowId: raw.rowId ?? `veh-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      assetCode: raw.assetCode ?? '',
      name: raw.name ?? '',
      plateNo: raw.plateNo ?? '',
      vinNo: raw.vinNo ?? '',
      engineNo: raw.engineNo ?? '',
      drivingLicenseNo: raw.drivingLicenseNo ?? '',
      regCertNo: raw.regCertNo ?? '',
      regDate: raw.regDate ?? '',
      regRemarks: raw.regRemarks ?? '',
      owner: raw.owner ?? '',
      isOwnerEntity: raw.isOwnerEntity ?? 'Y',
      useNature: raw.useNature ?? '',
      isMortgaged: raw.isMortgaged ?? 'N',
      mortgageAmount: Number(raw.mortgageAmount) || 0,
      mortgageNature: raw.mortgageNature ?? '',
      bookValue: bookVal,
      regValue: regVal,
      difference: bookVal - regVal,
      inspectionExpiry: raw.inspectionExpiry ?? '',
      inspectionStatus: raw.inspectionStatus ?? '',
      checkConclusion: raw.checkConclusion ?? raw.conclusion ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 统计 ────────────────────────────────────────────────────────

  const buildingStats = computed<TitleStatistics>(() => {
    const rows = buildingRows.value
    const mortgagedList = rows.filter((r) => r.isMortgaged === 'Y')
    const uncertified = rows.filter(isUncertifiedCipBuilding)
    return {
      totalChecked: rows.length,
      ownerAnomalyCount: rows.filter((r) => r.isOwnerEntity === 'N').length,
      mortgagedCount: mortgagedList.length,
      mortgageAmountTotal: calcSubtotal(mortgagedList.map((r) => r.mortgageAmount)),
      mismatchCount: rows.filter((r) => r.checkConclusion === '不符' || r.checkConclusion === '未取得权证').length,
      restrictedCount: rows.filter((r) => r.isRestricted === 'Y').length,
      bookNetTotal: calcSubtotal(rows.map((r) => r.netValue)),
      uncertifiedCipCount: uncertified.length,
      uncertifiedCipNetTotal: calcSubtotal(uncertified.map((r) => r.netValue)),
    }
  })

  const vehicleStats = computed<TitleStatistics>(() => {
    const rows = vehicleRows.value
    const mortgagedList = rows.filter((r) => r.isMortgaged === 'Y')
    return {
      totalChecked: rows.length,
      ownerAnomalyCount: rows.filter((r) => r.isOwnerEntity === 'N').length,
      mortgagedCount: mortgagedList.length,
      mortgageAmountTotal: calcSubtotal(
        mortgagedList.map((r) => (r.mortgageAmount > 0 ? r.mortgageAmount : r.bookValue)),
      ),
      mismatchCount: rows.filter((r) => r.checkConclusion === '不符' || r.checkConclusion === '未取得权证').length,
      restrictedCount: 0,
      bookNetTotal: calcSubtotal(rows.map((r) => r.bookValue)),
      uncertifiedCipCount: 0,
      uncertifiedCipNetTotal: 0,
    }
  })

  /** 未办证在建转固清单（单独提示用） */
  const uncertifiedCipRows = computed(() => buildingRows.value.filter(isUncertifiedCipBuilding))

  // ─── CRUD: Buildings ───────────────────────────────────────────────────────

  function addBuildingRow(name: string): void {
    const newRow: BuildingRow = {
      rowId: `bld-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: buildingRows.value.length + 1,
      assetCode: '',
      name,
      bookValue: 0, accumDep: 0, impairment: 0, netValue: 0,
      titleCertNo: '', owner: '', coOwnership: '', address: '',
      issueDate: '', propertyNature: '', usage: '',
      buildingArea: 0, landArea: 0, usefulLife: '',
      issuingAuthority: '', otherRights: '', certCopyIndex: '',
      isOwnerEntity: 'Y',
      isMortgaged: 'N', mortgageArea: 0, mortgageAmount: 0,
      mortgageNature: '', mortgagee: '', mortgageExpiry: '',
      isRestricted: 'N',
      fromCip: 'N', completionDate: '', expectedCertDate: '', cipNote: '',
      certValue: 0, difference: 0, diffReason: '',
      checkConclusion: '', conclusion: '', remark: '', ocrResult: '',
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
    row.netValue = _calcNet(row.bookValue, row.accumDep, row.impairment)
    row.difference = row.bookValue - row.certValue
    // 勾选在建转固且无证号时，自动提示核对结论
    if (field === 'fromCip' || field === 'titleCertNo' || field === 'completionDate') {
      if (isUncertifiedCipBuilding(row) && !row.checkConclusion) {
        row.checkConclusion = '未取得权证'
      }
    }
    _persistBuildings()
  }

  /**
   * 权证 OCR 结果回填（仅填空字段；他项权利含抵押时同步勾选）。
   * @returns 实际填入的字段名列表
   */
  function mergeBuildingOcrResult(
    rowId: string,
    ocrData: Record<string, any>,
    options?: { overwrite?: boolean },
  ): string[] {
    const row = buildingRows.value.find((r) => r.rowId === rowId)
    if (!row) return []
    const overwrite = options?.overwrite === true
    const filled: string[] = []

    const strFields: (keyof BuildingRow)[] = [
      'titleCertNo', 'owner', 'coOwnership', 'address', 'issueDate',
      'propertyNature', 'usage', 'usefulLife', 'issuingAuthority', 'otherRights',
      'mortgagee', 'mortgageNature',
    ]
    for (const f of strFields) {
      const v = ocrData[f]
      if (v == null || String(v).trim() === '') continue
      if (!overwrite && String((row as any)[f] || '').trim()) continue
      ;(row as any)[f] = String(v).trim()
      filled.push(f)
    }

    for (const f of ['buildingArea', 'landArea'] as const) {
      const n = Number(ocrData[f])
      if (!Number.isFinite(n) || n <= 0) continue
      if (!overwrite && row[f] > 0) continue
      row[f] = n
      filled.push(f)
    }

    // 他项权利/抵押权人暗示抵押
    const other = String(row.otherRights || '')
    if (
      (other.includes('抵押') || other.includes('查封') || filled.includes('mortgagee') || filled.includes('mortgageNature'))
      && row.isMortgaged !== 'Y'
    ) {
      row.isMortgaged = 'Y'
      filled.push('isMortgaged')
    }

    if (filled.includes('titleCertNo') && row.checkConclusion === '未取得权证') {
      row.checkConclusion = ''
      filled.push('checkConclusion')
    }
    if (filled.includes('owner') && row.isOwnerEntity !== 'N') {
      // 不自动判定是否被审计单位，留给人工勾选
    }

    row.ocrResult = JSON.stringify(ocrData)
    if (ocrData.attachment_id || ocrData.attachmentId) {
      const idx = String(ocrData.attachment_id || ocrData.attachmentId)
      if (!row.certCopyIndex) {
        row.certCopyIndex = `OCR:${idx.slice(0, 8)}`
        filled.push('certCopyIndex')
      }
    }

    _persistBuildings()
    return filled
  }

  // ─── CRUD: Vehicles ────────────────────────────────────────────────────────

  function addVehicleRow(name: string): void {
    const newRow: VehicleRow = {
      rowId: `veh-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: vehicleRows.value.length + 1,
      assetCode: '',
      name, plateNo: '', vinNo: '', engineNo: '',
      drivingLicenseNo: '', regCertNo: '', regDate: '', regRemarks: '',
      owner: '', isOwnerEntity: 'Y', useNature: '', isMortgaged: 'N',
      mortgageAmount: 0, mortgageNature: '',
      bookValue: 0, regValue: 0, difference: 0,
      inspectionExpiry: '', inspectionStatus: '',
      checkConclusion: '', conclusion: '', remark: '',
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
    // 年检截止日相对资产负债表日：自动标「已过期」
    if (field === 'inspectionExpiry' || field === 'inspectionStatus') {
      const periodEnd = options?.periodEnd?.value || ''
      if (isInspectionExpiredBeforePeriodEnd(row.inspectionExpiry, periodEnd)) {
        if (row.inspectionStatus !== '未通过') {
          row.inspectionStatus = '已过期'
        }
      }
    }
    _persistVehicles()
  }

  /**
   * 行驶证/登记证书 OCR 结果回填（仅填空字段；登记栏含抵押/查封时同步勾选抵押受限）。
   * @returns 实际填入的字段名列表
   */
  function mergeVehicleOcrResult(
    rowId: string,
    ocrData: Record<string, any>,
    opts?: { overwrite?: boolean },
  ): string[] {
    const row = vehicleRows.value.find((r) => r.rowId === rowId)
    if (!row) return []
    const overwrite = opts?.overwrite === true
    const filled: string[] = []

    const strFields: (keyof VehicleRow)[] = [
      'plateNo', 'vinNo', 'engineNo', 'drivingLicenseNo', 'regCertNo',
      'regDate', 'owner', 'useNature', 'inspectionExpiry', 'regRemarks',
    ]
    for (const f of strFields) {
      const v = ocrData[f]
      if (v == null || String(v).trim() === '') continue
      if (!overwrite && String((row as any)[f] || '').trim()) continue
      ;(row as any)[f] = String(v).trim()
      filled.push(f)
    }

    // 登记栏备注含抵押/查封 → 暗示抵押受限
    const remarks = String(row.regRemarks || '')
    if ((remarks.includes('抵押') || remarks.includes('质押') || remarks.includes('查封')) && row.isMortgaged !== 'Y') {
      row.isMortgaged = 'Y'
      filled.push('isMortgaged')
    }

    // 年检截止日 OCR 后按资产负债表日重判年检状态
    if (filled.includes('inspectionExpiry')) {
      const periodEnd = options?.periodEnd?.value || ''
      if (isInspectionExpiredBeforePeriodEnd(row.inspectionExpiry, periodEnd) && row.inspectionStatus !== '未通过') {
        row.inspectionStatus = '已过期'
        filled.push('inspectionStatus')
      }
    }

    if (ocrData.attachment_id || ocrData.attachmentId) {
      const idx = String(ocrData.attachment_id || ocrData.attachmentId)
      if (!(row.remark || '').includes('OCR:')) {
        row.remark = [row.remark, `OCR:${idx.slice(0, 8)}`].filter(Boolean).join('；')
        filled.push('remark')
      }
    }

    _persistVehicles()
    return filled
  }

  /** H1-2 中可带入的运输设备台数 */
  const h12TransportCount = computed(() => getTransportDetailSeeds(allResponses.value as Map<string, any>).length)

  /** H1-2 中可带入的房屋建筑物栋数 */
  const h12BuildingCount = computed(() => getBuildingDetailSeeds(allResponses.value as Map<string, any>).length)

  /**
   * 从 H1-2 带入运输设备行。
   * - 已存在相同资产编号（或无编号时同名）则跳过
   * - 返回 { added, skipped, total }
   */
  function importVehiclesFromH12(): { added: number; skipped: number; total: number } {
    const seeds = getTransportDetailSeeds(allResponses.value as Map<string, any>)
    const existingCodes = new Set(
      vehicleRows.value.map((r) => (r.assetCode || '').trim()).filter(Boolean),
    )
    const existingNames = new Set(
      vehicleRows.value.filter((r) => !(r.assetCode || '').trim()).map((r) => (r.name || '').trim()).filter(Boolean),
    )
    let added = 0
    let skipped = 0
    for (const seed of seeds) {
      const code = (seed.assetNo || '').trim()
      const name = (seed.name || seed.spec || '').trim()
      if (code && existingCodes.has(code)) { skipped++; continue }
      if (!code && name && existingNames.has(name)) { skipped++; continue }
      const row = mapDetailSeedToVehicleRow(seed, vehicleRows.value.length + 1)
      vehicleRows.value.push(row)
      if (code) existingCodes.add(code)
      else if (name) existingNames.add(name)
      added++
    }
    if (added) {
      vehicleRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistVehicles()
    }
    return { added, skipped, total: seeds.length }
  }

  /**
   * 从 H1-2 带入房屋建筑物行。
   * - 已存在相同资产编号（或无编号时同名）则跳过
   */
  function importBuildingsFromH12(): { added: number; skipped: number; total: number } {
    const seeds = getBuildingDetailSeeds(allResponses.value as Map<string, any>)
    const existingCodes = new Set(
      buildingRows.value.map((r) => (r.assetCode || '').trim()).filter(Boolean),
    )
    const existingNames = new Set(
      buildingRows.value.filter((r) => !(r.assetCode || '').trim()).map((r) => (r.name || '').trim()).filter(Boolean),
    )
    let added = 0
    let skipped = 0
    for (const seed of seeds) {
      const code = (seed.assetNo || '').trim()
      const name = (seed.name || seed.spec || '').trim()
      if (code && existingCodes.has(code)) { skipped++; continue }
      if (!code && name && existingNames.has(name)) { skipped++; continue }
      const row = mapDetailSeedToBuildingRow(seed, buildingRows.value.length + 1)
      buildingRows.value.push(row)
      if (code) existingCodes.add(code)
      else if (name) existingNames.add(name)
      added++
    }
    if (added) {
      buildingRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistBuildings()
    }
    return { added, skipped, total: seeds.length }
  }

  /** 将抵押车辆同步至上市/国企附注「抵押担保」子节 */
  function syncMortgagedToDisclosure(): number {
    const fromH117 = mapMortgagedVehiclesToDisclosureRows(vehicleRows.value)
    for (const key of [
      'H1-soe-restricted-rows',
      'H1-listed-mortgage-rows',
    ] as const) {
      const existingItem = allResponses.value.get(key)
      const existing = _safeParseRows<DisclosureRestrictedRow>(existingItem?.remark)
      const merged = mergeRestrictedDisclosureRows(existing, fromH117, '来源:H1-17')
      options?.onSave?.(key, merged)
    }
    return fromH117.length
  }

  /** 将抵押房屋同步至上市/国企附注「抵押担保」子节 */
  function syncMortgagedBuildingsToDisclosure(): number {
    const fromH116 = mapMortgagedBuildingsToDisclosureRows(buildingRows.value)
    for (const key of [
      'H1-soe-restricted-rows',
      'H1-listed-mortgage-rows',
    ] as const) {
      const existingItem = allResponses.value.get(key)
      const existing = _safeParseRows<DisclosureRestrictedRow>(existingItem?.remark)
      const merged = mergeRestrictedDisclosureRows(existing, fromH116, '来源:H1-16')
      options?.onSave?.(key, merged)
    }
    return fromH116.length
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
    uncertifiedCipRows,
    h12TransportCount,
    h12BuildingCount,
    addBuildingRow,
    removeBuildingRow,
    updateBuildingCell,
    mergeBuildingOcrResult,
    addVehicleRow,
    removeVehicleRow,
    updateVehicleCell,
    mergeVehicleOcrResult,
    importVehiclesFromH12,
    importBuildingsFromH12,
    syncMortgagedToDisclosure,
    syncMortgagedBuildingsToDisclosure,
    saveNote,
    saveConclusion,
  }
}

export default useH1TitleCheck
