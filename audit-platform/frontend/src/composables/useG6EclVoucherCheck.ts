/**
 * useG6EclVoucherCheck — G6-15 凭证检查表 composable
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/
 * Task: 9.2
 *
 * 职责：
 * - OCR识别逻辑（POST /d4/contract-ocr → ElMessageBox确认 → 字段填入）
 * - 异常自动判定（7项核对任一✗ → isAbnormal = true）
 * - 借贷平衡校验（调用 isDebitCreditBalanced）
 * - 抽凭引擎样本填入（fillVoucherSamples）
 * - 行CRUD（addRow / removeRow 含 ElMessageBox.prompt）
 * - 数据持久化（loadRows / toJSON）
 *
 * Requirements: 5.2, 5.3
 */
import { ref, computed, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isDebitCreditBalanced, parseNum } from '@/composables/useG6EclFormulaEngine'
import http from '@/utils/http'
import type { VoucherCheckRow } from '@/components/workpaper/composables/useG6EclFormData'

// ─── OCR字段映射 ─────────────────────────────────────────────────────────────

/** OCR识别字段名 → VoucherCheckRow字段名 */
const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  date: 'date',
  凭证日期: 'date',
  voucherNo: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  businessContent: 'businessContent',
  业务内容: 'businessContent',
  摘要: 'businessContent',
  counterAccount: 'counterAccount',
  对方科目: 'counterAccount',
  detailAccount: 'detailAccount',
  明细科目: 'detailAccount',
  明细: 'detailAccount',
  debitAmount: 'debitAmount',
  借方金额: 'debitAmount',
  借方: 'debitAmount',
  creditAmount: 'creditAmount',
  贷方金额: 'creditAmount',
  贷方: 'creditAmount',
}

/** 字段中文标签（ElMessageBox预览用） */
const FIELD_LABELS: Record<string, string> = {
  date: '日期',
  voucherNo: '凭证号',
  businessContent: '业务内容',
  counterAccount: '对方科目',
  detailAccount: '明细',
  debitAmount: '借方金额',
  creditAmount: '贷方金额',
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6EclVoucherCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  htmlData?: Ref<Record<string, any> | null>,
) {
  const rows = ref<VoucherCheckRow[]>([])
  const activeTab = ref<'tab1' | 'tab2' | 'tab3'>('tab1')
  const activeRowIndex = ref(0)
  const ocrLoadingRowId = ref<string | null>(null)

  // ─── 借贷平衡校验（Requirements: 5.3） ────────────────────────────────────

  /** 借方金额合计 */
  const debitTotal = computed(() =>
    rows.value.reduce((sum, r) => sum + parseNum(r.debitAmount), 0),
  )

  /** 贷方金额合计 */
  const creditTotal = computed(() =>
    rows.value.reduce((sum, r) => sum + parseNum(r.creditAmount), 0),
  )

  /** 借贷差额 */
  const difference = computed(() =>
    Math.round(Math.abs(debitTotal.value - creditTotal.value) * 100) / 100,
  )

  /** 是否平衡 */
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      rows.value.map(r => r.debitAmount),
      rows.value.map(r => r.creditAmount),
    ),
  )

  // ─── 异常自动判定（Requirements: 5.2, 5.3） ───────────────────────────────

  /**
   * 7项核对字段：
   * checkOriginal / checkAuthorized / checkAccounting /
   * checkAmount / checkClassification / checkImpairment / checkInterest
   * 任一 false → isAbnormal = true
   */
  function recalcAbnormal(row: VoucherCheckRow): void {
    const checks = [
      row.checkOriginal,
      row.checkAuthorized,
      row.checkAccounting,
      row.checkAmount,
      row.checkClassification,
      row.checkImpairment,
      row.checkInterest,
    ]
    // 任一 false → 异常
    row.isAbnormal = checks.some(c => c === false)
  }

  /**
   * 判断某行是否全部7项核对通过
   */
  function isAllChecked(row: VoucherCheckRow): boolean {
    return [
      row.checkOriginal,
      row.checkAuthorized,
      row.checkAccounting,
      row.checkAmount,
      row.checkClassification,
      row.checkImpairment,
      row.checkInterest,
    ].every(c => c === true)
  }

  // ─── OCR识别逻辑（Requirements: 5.2） ─────────────────────────────────────

  /**
   * 将OCR识别结果映射为VoucherCheckRow可merge的字段对象
   */
  function mapOcrToVoucherFields(fields: Record<string, any>): Partial<VoucherCheckRow> {
    const patch: Partial<VoucherCheckRow> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = OCR_FIELD_MAP[ocrKey]
      if (target && val != null && String(val).trim() !== '') {
        if (target === 'debitAmount' || target === 'creditAmount') {
          const num = parseNum(val)
          if (num !== 0) (patch as any)[target] = num
        } else {
          (patch as any)[target] = String(val).trim()
        }
      }
    }
    return patch
  }

  /**
   * 渲染OCR识别结果预览HTML（dangerouslyUseHTMLString）
   */
  function renderOcrPreview(fields: Record<string, any>, confidence: number): string {
    const patch = mapOcrToVoucherFields(fields)
    const lines = Object.entries(patch)
      .map(([key, val]) => {
        const label = FIELD_LABELS[key] || key
        return `<div style="margin:4px 0"><strong>${label}：</strong>${val}</div>`
      })
    const confPct = (confidence * 100).toFixed(0)
    const confColor = confidence >= 0.8 ? '#67c23a' : '#e6a23c'
    return `
      <div style="font-size:13px">
        <div style="margin-bottom:8px;color:${confColor}">
          置信度：${confPct}%${confidence < 0.8 ? '（建议人工核对）' : ''}
        </div>
        ${lines.length ? lines.join('') : '<div style="color:#909399">未提取到有效字段</div>'}
      </div>
    `.trim()
  }

  /**
   * 行级OCR处理：上传 → POST /d4/contract-ocr → ElMessageBox确认 → 字段填入
   */
  async function handleRowOcr(row: VoucherCheckRow, file: File): Promise<boolean> {
    if (!wpId.value) return false
    ocrLoadingRowId.value = row.id
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields: Record<string, any> = data?.extracted_fields || {}
      const confidence: number = data?.confidence ?? 0

      if (!Object.keys(fields).length) {
        ElMessage.info('OCR完成，未识别到可填充字段')
        return false
      }

      const patch = mapOcrToVoucherFields(fields)
      if (Object.keys(patch).length === 0) {
        ElMessage.info('OCR完成，识别字段无法匹配当前行')
        return false
      }

      // 确认弹窗（dangerouslyUseHTMLString）
      await ElMessageBox.confirm(
        renderOcrPreview(fields, confidence),
        'OCR识别结果',
        {
          confirmButtonText: '填入',
          cancelButtonText: '取消',
          dangerouslyUseHTMLString: true,
          type: confidence < 0.8 ? 'warning' : 'info',
        },
      )

      // 确认后填入
      Object.assign(row, patch)
      row.attachment = file.name
      ElMessage.success('已填入OCR识别结果')
    } catch (e: any) {
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.warning('OCR识别失败或已取消')
      }
    } finally {
      ocrLoadingRowId.value = null
    }
    return false // 阻止el-upload默认上传行为
  }

  // ─── 抽凭引擎样本填入（Requirements: 5.2） ────────────────────────────────

  /**
   * 从 GtVoucherSamplingEngine 抽凭引擎结果批量填入行
   * samples: 抽样引擎返回的样本列表
   */
  function fillVoucherSamples(samples: Array<{
    voucherNo: string
    date?: string
    businessContent?: string
    counterAccount?: string
    detailAccount?: string
    debitAmount?: number
    creditAmount?: number
  }>): void {
    for (const sample of samples) {
      const newRow: VoucherCheckRow = {
        id: crypto.randomUUID(),
        seq: rows.value.length + 1,
        date: sample.date ?? '',
        voucherNo: sample.voucherNo,
        businessContent: sample.businessContent ?? '',
        counterAccount: sample.counterAccount ?? '',
        detailAccount: sample.detailAccount ?? '',
        debitAmount: sample.debitAmount ?? 0,
        creditAmount: sample.creditAmount ?? 0,
        attachment: null,
        supportingDoc: '',
        checkOriginal: false,
        checkAuthorized: false,
        checkAccounting: false,
        checkAmount: false,
        checkClassification: false,
        checkImpairment: false,
        checkInterest: false,
        indexRef: '',
        isAbnormal: true, // 未核对前默认异常
        abnormalNote: '',
        riskLevel: '',
        suggestion: '',
        remark: '',
      }
      rows.value.push(newRow)
    }
    _resequence()
  }

  // ─── 行 CRUD ──────────────────────────────────────────────────────────────

  /**
   * 新增行（ElMessageBox.prompt输入凭证编号）
   */
  async function addRow(defaultVoucherNo?: string): Promise<void> {
    let voucherNo = defaultVoucherNo
    if (!voucherNo) {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '凭证编号不能为空'),
      })
      if (!value?.trim()) return
      voucherNo = value.trim()
    }

    const newRow: VoucherCheckRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      date: '',
      voucherNo: voucherNo!,
      businessContent: '',
      counterAccount: '',
      detailAccount: '',
      debitAmount: 0,
      creditAmount: 0,
      attachment: null,
      supportingDoc: '',
      checkOriginal: false,
      checkAuthorized: false,
      checkAccounting: false,
      checkAmount: false,
      checkClassification: false,
      checkImpairment: false,
      checkInterest: false,
      indexRef: '',
      isAbnormal: true, // 未核对前默认异常
      abnormalNote: '',
      riskLevel: '',
      suggestion: '',
      remark: '',
    }
    rows.value.push(newRow)
    _resequence()
  }

  /**
   * 删除行
   */
  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    _resequence()
  }

  /** 内部：重新编号 */
  function _resequence(): void {
    rows.value.forEach((row, i) => {
      row.seq = i + 1
    })
  }

  // ─── 数据持久化 ───────────────────────────────────────────────────────────

  /**
   * 加载行数据
   */
  function loadRows(data: VoucherCheckRow[]): void {
    rows.value = (data || []).map((r) => ({
      ...r,
      id: r.id || crypto.randomUUID(),
    }))
    _resequence()
  }

  /**
   * 导出为 JSON（VoucherCheckData结构）
   */
  function toJSON() {
    return {
      rows: rows.value.map(r => ({ ...r })),
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      difference: difference.value,
      isBalanced: isBalanced.value,
    }
  }

  return {
    // State
    rows,
    activeTab,
    activeRowIndex,
    ocrLoadingRowId,
    // Computed - 借贷平衡
    debitTotal,
    creditTotal,
    difference,
    isBalanced,
    // Validation - 异常判定
    recalcAbnormal,
    isAllChecked,
    // OCR
    handleRowOcr,
    mapOcrToVoucherFields,
    // Sampling - 抽凭引擎
    fillVoucherSamples,
    // CRUD
    addRow,
    removeRow,
    // Data
    loadRows,
    toJSON,
  }
}

export default useG6EclVoucherCheck
