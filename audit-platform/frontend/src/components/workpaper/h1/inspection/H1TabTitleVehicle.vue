<template>
  <div class="h1-tab-title-vehicle">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：记录的运输设备由被审计单位拥有或控制；年检有效；抵押/查封等受限情形已识别并支持附注披露。
      </template>
    </el-alert>

    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-17" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ vehicleRows.length }} 项</el-tag>
    </div>

    <div class="methodology-context">
      <p>
        从 H1-2 运输设备明细确定检查总体 → 核对登记证书（所有人/车架号/登记栏）与行驶证年检 →
        账面原值勾稽 → 抵押/查封索引至附注受限资产。每次审计须重新取得权证原件并与复印件核对。
      </p>
    </div>

    <el-card shadow="never" class="coverage-card">
      <template #header><span>检查范围</span></template>
      <div class="coverage-grid">
        <div class="coverage-item">
          <span class="coverage-label">账面台数</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="coverage.bookCount"
            :controls="false"
            size="small"
            :min="0"
            @change="saveCoverage"
          />
          <span v-else>{{ coverage.bookCount ?? '-' }}</span>
          <el-tag v-if="h12TransportCount > 0" size="small" type="info">H1-2运输设备 {{ h12TransportCount }}</el-tag>
        </div>
        <div class="coverage-item">
          <span class="coverage-label">本次检查</span>
          <el-tag size="small">{{ vehicleRows.length }}</el-tag>
        </div>
        <div class="coverage-item">
          <span class="coverage-label">检查方式</span>
          <el-select
            v-if="!isReadonly"
            v-model="coverage.method"
            size="small"
            style="width:100px"
            @change="saveCoverage"
          >
            <el-option label="全查" value="全查" />
            <el-option label="抽样" value="抽样" />
          </el-select>
          <span v-else>{{ coverage.method || '-' }}</span>
        </div>
        <div class="coverage-item coverage-wide">
          <span class="coverage-label">抽样说明</span>
          <el-input
            v-if="!isReadonly"
            v-model="coverage.sampleNote"
            size="small"
            placeholder="抽样方法、样本量及代表结论"
            @change="saveCoverage"
          />
          <span v-else>{{ coverage.sampleNote || '-' }}</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-17 运输设备权属检查 <el-tag size="small" type="info">共 {{ vehicleRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || h12TransportCount === 0"
              @click="handleImportH12"
            >从 H1-2 带入</el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isReadonly || vehicleStats.mortgagedCount === 0"
              @click="handleSyncDisclosure"
            >同步抵押至附注</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-17')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="vehicleRows"
        border
        stripe
        size="small"
        max-height="480"
        class="title-table"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetCode" label="资产编号" width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCode" size="small" @change="onCell(row, 'assetCode')" />
            <span v-else>{{ row.assetCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plateNo" label="登记编号/车牌" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.plateNo" size="small" @change="onCell(row, 'plateNo')" />
            <span v-else>{{ row.plateNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="vinNo" label="车架号/VIN" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.vinNo" size="small" @change="onCell(row, 'vinNo')" />
            <span v-else>{{ row.vinNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="engineNo" label="发动机号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.engineNo" size="small" @change="onCell(row, 'engineNo')" />
            <span v-else>{{ row.engineNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="证载所有人" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.owner" size="small" @change="onCell(row, 'owner')" />
            <span v-else>{{ row.owner }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所有人为被审计单位" width="130" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isOwnerEntity" size="small" style="width:70px" @change="onCell(row, 'isOwnerEntity')">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.isOwnerEntity === 'Y' ? 'success' : 'danger'" size="small">
              {{ row.isOwnerEntity === 'Y' ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="regRemarks" label="登记栏" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.regRemarks" size="small" placeholder="抵押/查封等" @change="onCell(row, 'regRemarks')" />
            <span v-else>{{ row.regRemarks }}</span>
          </template>
        </el-table-column>
        <el-table-column label="抵押受限" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isMortgaged" size="small" style="width:56px" @change="onCell(row, 'isMortgaged')">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else-if="row.isMortgaged === 'Y'" type="warning" size="small">有</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="mortgageAmount" label="抵押价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.isMortgaged === 'Y'"
              v-model="row.mortgageAmount"
              :controls="false"
              size="small"
              @change="onCell(row, 'mortgageAmount')"
            />
            <span v-else class="amount-cell">{{ row.isMortgaged === 'Y' ? fmtAmt(row.mortgageAmount) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="inspectionExpiry" label="年检截止日" width="130">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.inspectionExpiry"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width:118px"
              :class="{ 'expiry-expired': isExpiryExpired(row) }"
              @change="onCell(row, 'inspectionExpiry')"
            />
            <span v-else :class="{ 'error-amount': isExpiryExpired(row) }">{{ row.inspectionExpiry || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="inspectionStatus" label="年检状态" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.inspectionStatus" size="small" style="width:88px" @change="onCell(row, 'inspectionStatus')">
              <el-option label="已通过" value="已通过" />
              <el-option label="未通过" value="未通过" />
              <el-option label="已过期" value="已过期" />
            </el-select>
            <el-tag
              v-else
              :type="row.inspectionStatus === '已通过' ? 'success' : 'warning'"
              size="small"
            >{{ row.inspectionStatus || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="checkConclusion" label="核对结论" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkConclusion" size="small" style="width:100px" @change="onCell(row, 'checkConclusion')">
              <el-option label="相符" value="相符" />
              <el-option label="不符" value="不符" />
              <el-option label="未取得权证" value="未取得权证" />
            </el-select>
            <el-tag
              v-else
              :type="checkTagType(row.checkConclusion)"
              size="small"
            >{{ row.checkConclusion || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注/索引" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              size="small"
              :loading="ocrLoadingId === row.rowId"
              title="上传行驶证/登记证书扫描件 OCR 预填"
              @click="handleOcr(row)"
            >📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeVehicleRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>总计: {{ vehicleStats.totalChecked }} 项</span>
        <span>所有人异常: <b :class="{ 'error-amount': vehicleStats.ownerAnomalyCount > 0 }">{{ vehicleStats.ownerAnomalyCount }}</b></span>
        <span>年检过期/未通过: <b :class="{ 'error-amount': expiredCount > 0 }">{{ expiredCount }}</b></span>
        <span>有抵押: <b :class="{ 'warn-amount': vehicleStats.mortgagedCount > 0 }">{{ vehicleStats.mortgagedCount }}</b>，合计 {{ fmtAmt(vehicleStats.mortgageAmountTotal) }}</span>
        <span>不符/未取得: <b :class="{ 'error-amount': mismatchCount > 0 }">{{ mismatchCount }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 6 }"
        :disabled="isReadonly"
        :placeholder="notePlaceholder"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        :placeholder="conclusionPlaceholder"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>可用「从 H1-2 带入」按分类自动引入运输设备；同资产编号不重复</li>
        <li>年检截止日早于资产负债表日（{{ periodEndDisplay || '未取到截止日' }}）时单元格标红，并自动置为「已过期」</li>
        <li>「同步抵押至附注」写入上市/国企附注受限资产子节（保留非 H1-17 来源行）</li>
        <li>登记证书是权属核心证据；行驶证用于号牌/VIN/年检，不能替代登记证书</li>
        <li>所有人非被审计单位标红；须补充代持/控制权证据并评估确认条件</li>
        <li>车架号（VIN）优先与登记证书、行驶证交叉核对</li>
        <li>行末 📎 上传行驶证/登记证书扫描件 → OCR 预填号牌/VIN/所有人/年检等字段（仅填空，不覆盖已有值）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH1TitleCheck,
  isInspectionExpiredBeforePeriodEnd,
  H1_VEHICLE_OCR_FIELD_LABELS,
  type VehicleRow,
} from '../../composables/useH1TitleCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** 资产负债表日 YYYY-MM-DD / YYYY年MM月DD日 */
  periodEnd?: string
  htmlData?: any
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const conclusion = ref('')
const auditNoteText = ref('')
const ocrLoadingId = ref('')
const coverage = ref<{ bookCount: number | null; method: string; sampleNote: string }>({
  bookCount: null,
  method: '全查',
  sampleNote: '',
})

const NOTE_KEY = 'H1-17-audit-note'
const CONCLUSION_KEY = 'H1-17-audit-conclusion'
const COVERAGE_KEY = 'H1-17-coverage'

const notePlaceholder = [
  '1. 权证是否齐全；登记证书所有人是否为被审计单位（代持需说明控制依据）；车架号/发动机号与账面是否一致',
  '2. 登记栏抵押/质押/查封限制；抵押价值及合同索引；是否已纳入附注受限资产披露',
  '3. 年检截止日是否覆盖资产负债表日；过期车辆及对持续使用/减值的影响',
  '4. 例外事项及进一步程序/调整建议',
].join('\n')

const conclusionPlaceholder =
  '经检查，除上述例外外，检查的运输设备权属证明齐全，所有人与被审计单位一致，年检有效，抵押受限已充分识别并与附注披露相符。 / 存在下列重大例外：……'

/** 规范化为 YYYY-MM-DD */
function normalizePeriodEnd(raw: string | null | undefined): string {
  if (!raw) return ''
  const s = String(raw).trim()
  const iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/)
  if (iso) return `${iso[1]}-${iso[2].padStart(2, '0')}-${iso[3].padStart(2, '0')}`
  const cn = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})/)
  if (cn) return `${cn[1]}-${cn[2].padStart(2, '0')}-${cn[3].padStart(2, '0')}`
  return s.slice(0, 10)
}

const periodEndRef = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  return normalizePeriodEnd(
    props.periodEnd
      || ctx.period_end
      || ctx.audit_period_end
      || ctx.bs_date
      || '',
  )
})
const periodEndDisplay = computed(() => periodEndRef.value || '（未配置）')

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
function saveCoverage() { saveResponse(COVERAGE_KEY, JSON.stringify(coverage.value)) }

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
  const cov = props.allResponses.get(COVERAGE_KEY)
  if (cov?.remark) {
    try {
      const parsed = JSON.parse(cov.remark)
      if (parsed && typeof parsed === 'object') coverage.value = { ...coverage.value, ...parsed }
    } catch { /* ignore */ }
  }
})

const {
  vehicleRows,
  vehicleStats,
  h12TransportCount,
  addVehicleRow,
  removeVehicleRow,
  updateVehicleCell,
  mergeVehicleOcrResult,
  importVehiclesFromH12,
  syncMortgagedToDisclosure,
} = useH1TitleCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    onSave: (itemId, value) => saveResponse(itemId, value),
    periodEnd: periodEndRef as any,
  },
)

const expiredCount = computed(() =>
  vehicleRows.value.filter((r) =>
    r.inspectionStatus === '已过期'
    || r.inspectionStatus === '未通过'
    || isInspectionExpiredBeforePeriodEnd(r.inspectionExpiry, periodEndRef.value),
  ).length,
)
const mismatchCount = computed(() =>
  vehicleRows.value.filter((r) => r.checkConclusion === '不符' || r.checkConclusion === '未取得权证').length,
)

function isExpiryExpired(row: VehicleRow): boolean {
  return isInspectionExpiredBeforePeriodEnd(row.inspectionExpiry, periodEndRef.value)
    || row.inspectionStatus === '已过期'
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('车辆名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) addVehicleRow(name)
}

function handleImportH12() {
  const { added, skipped, total } = importVehiclesFromH12()
  if (total === 0) {
    ElMessage.warning('H1-2 中暂无「运输设备」分类明细可带入')
    return
  }
  if (coverage.value.bookCount == null || coverage.value.bookCount < total) {
    coverage.value.bookCount = total
    saveCoverage()
  }
  ElMessage.success(
    added > 0
      ? `已从 H1-2 带入 ${added} 项（跳过已存在 ${skipped}，总体 ${total}）`
      : `无可新增项（H1-2 运输设备 ${total} 项均已在表中）`,
  )
}

function handleSyncDisclosure() {
  const n = syncMortgagedToDisclosure()
  ElMessage.success(
    n > 0
      ? `已同步 ${n} 项抵押运输设备至附注「受限资产」子节（上市/国企）`
      : '暂无抵押车辆可同步',
  )
}

function onCell(row: VehicleRow, field: keyof VehicleRow) {
  updateVehicleCell(row.rowId, field, (row as any)[field])
}

/** 行级权证 OCR：📎 → POST /h1/vehicle-title-ocr → 确认 → 仅填空预填 */
async function handleOcr(row: VehicleRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    ocrLoadingId.value = row.rowId
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h1/vehicle-title-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = { ...(data?.extracted_fields || {}) }
      if (data?.attachment_id) fields.attachment_id = data.attachment_id
      const previewEntries = Object.entries(fields)
        .filter(([k, v]) => k !== 'attachment_id' && v !== '' && v != null && v !== 0)
        .map(([k, v]) => `${H1_VEHICLE_OCR_FIELD_LABELS[k] || k}: ${v}`)
      if (!previewEntries.length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段，请核对扫描件清晰度后重试', '提示')
        return
      }
      const confPct = Math.round(Number(data?.confidence || 0) * 100)
      await ElMessageBox.confirm(
        `置信度 ${confPct}%\n\n${previewEntries.join('\n')}\n\n确认填入空白字段？`,
        '行驶证/登记证书 OCR 识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: confPct < 50 ? 'warning' : 'info' },
      )
      const filled = mergeVehicleOcrResult(row.rowId, fields)
      ElMessage.success(filled.length ? `已预填 ${filled.length} 个字段` : '无可填空字段（已有值未覆盖）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') {
        ElMessage.warning('权证 OCR 失败，请稍后重试或手工录入')
      }
    } finally {
      ocrLoadingId.value = ''
    }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function checkTagType(v: string): 'success' | 'danger' | 'warning' | 'info' {
  if (v === '相符') return 'success'
  if (v === '不符') return 'danger'
  if (v === '未取得权证') return 'warning'
  return 'info'
}
function rowClassName({ row }: { row: VehicleRow }) {
  if (row.isOwnerEntity === 'N' || row.checkConclusion === '不符' || row.checkConclusion === '未取得权证') {
    return 'row-anomaly'
  }
  if (isExpiryExpired(row) || row.inspectionStatus === '未通过') {
    return 'row-expiry'
  }
  if (row.isMortgaged === 'Y') {
    return 'row-warn'
  }
  return ''
}
</script>

<style scoped>
.h1-tab-title-vehicle { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
}
.coverage-card { margin-bottom: 12px; }
.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  align-items: center;
}
.coverage-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.coverage-wide { grid-column: 1 / -1; }
.coverage-label { color: var(--el-text-color-secondary); white-space: nowrap; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.title-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.title-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-warn) { background: #fdf6ec !important; }
:deep(.row-expiry) { background: #fde2e2 !important; }
:deep(.expiry-expired .el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-danger) inset;
  background: #fef0f0;
}
</style>
