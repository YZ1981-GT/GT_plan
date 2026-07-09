<template>
  <div class="i1-tab-title-check">
    <!-- 蓝色引导区 -->
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 逐项核查无形资产权属证书（专利/商标/著作权等）</div>
        <div class="guidance-step"><span class="step-num">②</span> 核对权利人与企业名称是否一致</div>
        <div class="guidance-step"><span class="step-num">③</span> 比较账面值与权证记载金额，计算差异</div>
        <div class="guidance-step"><span class="step-num">④</span> 检查有效期、登记状态，确认法律效力</div>
      </div>
    </div>

    <!-- 琥珀色方法论 -->
    <div class="methodology-context">
      <p><b>CAS6 无形资产权属核验要求</b>：逐项检查无形资产权属证书原件，核对权利人是否为被审计单位；
      对已到期或即将到期的权属证书，关注续展/续费情况；对存在权属纠纷的资产，评估其可收回性；
      比较账面记录金额与权证记载金额的一致性，分析差异原因（评估增值/减值/入账错误）。
      注意：土地使用权需单独检查出让/划拨性质及剩余年限。</p>
    </div>

    <!-- 表头操作区 -->
    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="section-title">
          <span>权属检查表（{{ rows.length }} 项）</span>
          <div class="title-actions">
            <!-- 分组筛选 -->
            <el-select v-model="filterType" size="small" placeholder="按类型筛选" clearable style="width:130px">
              <el-option label="全部" value="" />
              <el-option v-for="t in TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-dropdown size="small" trigger="click" :disabled="isReadonly">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                  <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                  <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="default" link @click="handleReview('I1-8')">💬 复核</el-button>
            <el-button size="small" link @click="handleAiConclusion" :disabled="isReadonly">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>

      <!-- 94行大表，max-height实现虚拟滚动 -->
      <el-table
        :data="filteredRows"
        border
        stripe
        size="small"
        :max-height="500"
        class="title-check-table"
        row-key="rowId"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="序号" width="50" align="center" fixed />
        <el-table-column prop="name" label="名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" placeholder="资产名称" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.type" size="small" placeholder="选择类型" style="width:105px">
              <el-option v-for="t in TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
            <el-tag v-else size="small" :type="typeTagColor(row.type)">{{ row.type || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="certNo" label="证书编号" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.certNo" size="small" placeholder="证书编号" />
            <span v-else>{{ row.certNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="registrationDate" label="登记日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.registrationDate" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:110px" />
            <span v-else>{{ row.registrationDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="validUntil" label="有效期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.validUntil" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:110px" />
            <span v-else :class="{ 'expired-date': isExpired(row.validUntil) }">{{ row.validUntil || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rightHolder" label="权利人" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.rightHolder" size="small" placeholder="权利人名称" />
            <span v-else>{{ row.rightHolder }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="registrationAuthority" label="登记机关" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.registrationAuthority" size="small" placeholder="如：国家知识产权局" />
            <span v-else>{{ row.registrationAuthority }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="registrationStatus" label="登记状态" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.registrationStatus" size="small" style="width:78px">
              <el-option label="有效" value="有效" />
              <el-option label="到期" value="到期" />
              <el-option label="续展中" value="续展中" />
              <el-option label="注销" value="注销" />
              <el-option label="待办" value="待办" />
            </el-select>
            <span v-else>{{ row.registrationStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" :precision="2" style="width:100px" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="certValue" label="权证价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.certValue" :controls="false" size="small" :precision="2" style="width:100px" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.certValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="120" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'diff-nonzero': getDiff(row) !== 0 }"
              :title="`差异金额 = 账面值(${fmtAmt(row.bookValue)}) - 权证值(${fmtAmt(row.certValue)})`"
            >{{ fmtAmt(getDiff(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isConsistent" label="是否与账面一致" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isConsistent" size="small" style="width:100px">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="部分一致" value="部分一致" />
            </el-select>
            <el-tag v-else :type="consistentTagType(row.isConsistent)" size="small">{{ row.isConsistent || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="diffDescription" label="差异说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.diffDescription" size="small" placeholder="差异原因说明" />
            <span v-else>{{ row.diffDescription }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeStatus" label="质押/限制" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.pledgeStatus" size="small" style="width:78px">
              <el-option label="无" value="无" />
              <el-option label="质押" value="质押" />
              <el-option label="冻结" value="冻结" />
              <el-option label="查封" value="查封" />
            </el-select>
            <span v-else>{{ row.pledgeStatus || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="renewalStatus" label="续展情况" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.renewalStatus" size="small" style="width:78px">
              <el-option label="无需" value="无需" />
              <el-option label="已续" value="已续" />
              <el-option label="待续" value="待续" />
              <el-option label="逾期" value="逾期" />
            </el-select>
            <span v-else>{{ row.renewalStatus || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="verifyMethod" label="核验方式" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.verifyMethod" size="small" style="width:85px">
              <el-option label="原件核对" value="原件核对" />
              <el-option label="网查" value="网查" />
              <el-option label="函证" value="函证" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.verifyMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="verifyDate" label="核验日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.verifyDate" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:110px" />
            <span v-else>{{ row.verifyDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" style="width:88px">
              <el-option label="无异常" value="无异常" />
              <el-option label="有差异" value="有差异" />
              <el-option label="需补办" value="需补办" />
            </el-select>
            <el-tag v-else :type="conclusionTagType(row.conclusion)" size="small">{{ row.conclusion || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 汇总统计栏 -->
      <div class="summary-bar">
        <span>检查总数: <b>{{ rows.length }}</b> 项</span>
        <span>账面合计: <b class="amount-cell">{{ fmtAmt(totalBookValue) }}</b></span>
        <span>差异合计: <b class="amount-cell" :class="{ 'diff-nonzero': totalDiff !== 0 }">{{ fmtAmt(totalDiff) }}</b></span>
        <span>不一致: <b :class="{ 'error-amount': inconsistentCount > 0 }">{{ inconsistentCount }}</b> 项</span>
        <span>需补办: <b :class="{ 'error-amount': needRenewalCount > 0 }">{{ needRenewalCount }}</b> 项</span>
      </div>

      <!-- 分组统计 -->
      <div class="group-stats" v-if="rows.length > 0">
        <span v-for="g in groupStats" :key="g.type" class="group-chip">
          <el-tag size="small" :type="typeTagColor(g.type)">{{ g.type }}</el-tag>
          <span class="group-count">{{ g.count }}项 / {{ fmtAmt(g.bookTotal) }}</span>
        </span>
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" link @click="handleAiConclusion" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="经逐项核查，无形资产权属情况…" @blur="persist" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>权属检查应逐项取得原件或通过国家知识产权局/工商局网站查询确认</li>
        <li>差异金额 = 账面值 - 权证值，由公式自动计算（虚线下划线列）</li>
        <li>按类型分组查看：专利权/商标权/著作权/土地使用权/软件著作权/特许经营权</li>
        <li>有效期已过需关注续展状态，标注"需补办"结论的项需跟踪落实</li>
        <li>权利人不一致可能涉及关联方占用或历史遗留问题，需在差异说明中详述</li>
        <li>本表支持94行大规模数据，表格max-height=500自带滚动条</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { calcTitleDiff } from '../../composables/useI1FormulaEngine'
import http from '@/utils/http'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': []
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const TYPE_OPTIONS = [
  '专利权',
  '商标权',
  '著作权',
  '土地使用权',
  '软件著作权',
  '特许经营权',
  '其他',
] as const

const ITEM_PREFIX = 'I1-8'

// ─── Types ───────────────────────────────────────────────────────────────────

interface TitleRow {
  rowId: string
  name: string
  type: string
  certNo: string
  registrationDate: string
  validUntil: string
  rightHolder: string
  registrationAuthority: string
  registrationStatus: string
  bookValue: number
  certValue: number
  isConsistent: string
  diffDescription: string
  pledgeStatus: string
  renewalStatus: string
  verifyMethod: string
  verifyDate: string
  conclusion: string
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<TitleRow[]>([])
const auditConclusion = ref('')
const filterType = ref('')

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadData() {
  const rowItem = props.allResponses.get(`${ITEM_PREFIX}-rows`)
  if (rowItem?.remark) {
    try {
      const parsed = JSON.parse(rowItem.remark)
      rows.value = Array.isArray(parsed) ? parsed.map(normalizeRow) : []
    } catch { rows.value = [] }
  } else { rows.value = [] }

  const conclusionItem = props.allResponses.get(`${ITEM_PREFIX}-conclusion`)
  auditConclusion.value = (conclusionItem?.remark ?? conclusionItem?.conclusion ?? '') as string
}

function normalizeRow(raw: any): TitleRow {
  return {
    rowId: raw.rowId ?? `i1t8-${Math.random().toString(36).slice(2, 10)}`,
    name: raw.name ?? '',
    type: raw.type ?? '',
    certNo: raw.certNo ?? '',
    registrationDate: raw.registrationDate ?? '',
    validUntil: raw.validUntil ?? '',
    rightHolder: raw.rightHolder ?? '',
    registrationAuthority: raw.registrationAuthority ?? '',
    registrationStatus: raw.registrationStatus ?? '',
    bookValue: Number(raw.bookValue) || 0,
    certValue: Number(raw.certValue) || 0,
    isConsistent: raw.isConsistent ?? '',
    diffDescription: raw.diffDescription ?? '',
    pledgeStatus: raw.pledgeStatus ?? '',
    renewalStatus: raw.renewalStatus ?? '',
    verifyMethod: raw.verifyMethod ?? '',
    verifyDate: raw.verifyDate ?? '',
    conclusion: raw.conclusion ?? '',
    remark: raw.remark ?? '',
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

// ─── Computed ────────────────────────────────────────────────────────────────

/** 按类型筛选 */
const filteredRows = computed(() => {
  if (!filterType.value) return rows.value
  return rows.value.filter((r) => r.type === filterType.value)
})

/** 差异金额使用公式引擎 */
function getDiff(row: TitleRow): number {
  return calcTitleDiff(row.bookValue || 0, row.certValue || 0)
}

const totalBookValue = computed(() =>
  rows.value.reduce((sum, r) => sum + (r.bookValue || 0), 0),
)

const totalDiff = computed(() =>
  rows.value.reduce((sum, r) => sum + getDiff(r), 0),
)

const inconsistentCount = computed(() =>
  rows.value.filter((r) => r.isConsistent === '否').length,
)

const needRenewalCount = computed(() =>
  rows.value.filter((r) => r.conclusion === '需补办').length,
)

/** 按类型分组统计 */
const groupStats = computed(() => {
  const map = new Map<string, { count: number; bookTotal: number }>()
  for (const r of rows.value) {
    const t = r.type || '未分类'
    const existing = map.get(t) || { count: 0, bookTotal: 0 }
    existing.count++
    existing.bookTotal += r.bookValue || 0
    map.set(t, existing)
  }
  return [...map.entries()].map(([type, stats]) => ({ type, ...stats }))
})

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入无形资产名称',
      '新增权属检查项',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：XX发明专利' },
    )
    if (!name?.trim()) return
    const newRow: TitleRow = {
      rowId: `i1t8-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim(),
      type: '',
      certNo: '',
      registrationDate: '',
      validUntil: '',
      rightHolder: '',
      registrationAuthority: '',
      registrationStatus: '',
      bookValue: 0,
      certValue: 0,
      isConsistent: '',
      diffDescription: '',
      pledgeStatus: '',
      renewalStatus: '',
      verifyMethod: '',
      verifyDate: '',
      conclusion: '',
      remark: '',
    }
    rows.value.push(newRow)
    persist()
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    persist()
  }
}

// ─── Import / Export ─────────────────────────────────────────────────────────

async function handleExportTemplate() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/i1/export-template?sheet=I1-8`, { responseType: 'blob' })
    downloadBlob(res.data, 'I1-8_权属检查表_模板.xlsx')
  } catch { ElMessage.warning('导出模板失败') }
}

async function handleExportData() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/i1/export-data`,
      { sheet: 'I1-8', rows: rows.value },
      { responseType: 'blob' },
    )
    downloadBlob(res.data, 'I1-8_权属检查表_数据.xlsx')
  } catch { ElMessage.warning('导出数据失败') }
}

async function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('sheet', 'I1-8')
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/i1/import-data`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const imported = res.data?.data?.rows ?? res.data?.rows ?? []
      if (imported.length) {
        await ElMessageBox.confirm(`识别到 ${imported.length} 行数据，是否导入？`, '导入确认')
        rows.value = imported.map(normalizeRow)
        persist()
        ElMessage.success(`已导入 ${imported.length} 行`)
      } else {
        ElMessage.warning('未识别到有效数据')
      }
    } catch { /* cancelled */ }
  }
  input.click()
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── AI Conclusion ───────────────────────────────────────────────────────────

async function handleAiConclusion() {
  try {
    const types = [...new Set(rows.value.map((r) => r.type).filter(Boolean))].join('、')
    const context = `权属检查共${rows.value.length}项，类型包括：${types || '未分类'}。` +
      `账面价值合计${fmtAmt(totalBookValue.value)}元，差异合计${fmtAmt(totalDiff.value)}元。` +
      `不一致${inconsistentCount.value}项，需补办${needRenewalCount.value}项。`
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'title-check-conclusion',
      prompt: '请根据以下无形资产权属检查结果，生成审计结论（简洁专业，关注权属完整性和差异说明）',
      context,
      existingContent: auditConclusion.value,
    })
    const generated = res.data?.data?.content ?? res.data?.content ?? ''
    if (generated) {
      await ElMessageBox.confirm(generated, 'AI生成结论预览', { confirmButtonText: '采用', cancelButtonText: '取消', type: 'info' })
      auditConclusion.value = generated
      persist()
    }
  } catch { /* cancelled */ }
}

// ─── Review / Navigation ─────────────────────────────────────────────────────

function handleReview(id: string) { openReviewDialog(id) }

// ─── Persist ─────────────────────────────────────────────────────────────────

function persist() {
  emit('save')
}

// ─── Summary Method ──────────────────────────────────────────────────────────

function getSummary({ columns }: any) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (col.property === 'bookValue') {
      sums[idx] = fmtAmt(totalBookValue.value)
      return
    }
    if (col.property === 'certValue') {
      const total = rows.value.reduce((s, r) => s + (r.certValue || 0), 0)
      sums[idx] = fmtAmt(total)
      return
    }
    // 差异金额列（无prop，按label判断）
    if (col.label === '差异金额') {
      sums[idx] = fmtAmt(totalDiff.value)
      return
    }
    sums[idx] = ''
  })
  return sums
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isExpired(dateStr: string): boolean {
  if (!dateStr) return false
  return new Date(dateStr) < new Date()
}

function typeTagColor(type: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (type) {
    case '专利权': return ''
    case '商标权': return 'success'
    case '著作权': return 'warning'
    case '土地使用权': return 'danger'
    case '软件著作权': return 'info'
    case '特许经营权': return 'success'
    default: return 'info'
  }
}

function consistentTagType(val: string): '' | 'success' | 'danger' | 'warning' {
  if (val === '是') return 'success'
  if (val === '否') return 'danger'
  if (val === '部分一致') return 'warning'
  return ''
}

function conclusionTagType(val: string): '' | 'success' | 'danger' | 'warning' {
  if (val === '无异常') return 'success'
  if (val === '有差异') return 'warning'
  if (val === '需补办') return 'danger'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-title-check { padding: 16px; font-size: 13px; }

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 12px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guidance-step {
  font-size: 12px;
  color: #1a5276;
  display: flex;
  align-items: center;
  gap: 6px;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #7d6608;
  line-height: 1.6;
}
.methodology-context b { color: #5a4e04; }

.main-card { margin-bottom: 12px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.title-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.title-check-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }

.formula-cell {
  text-decoration: underline dashed;
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.diff-nonzero {
  color: var(--el-color-danger);
  font-weight: 600;
}
.expired-date {
  color: var(--el-color-danger);
  font-weight: 500;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }

.summary-bar {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  flex-wrap: wrap;
}

.group-stats {
  display: flex;
  gap: 12px;
  padding: 8px 12px;
  margin-top: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.group-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.group-count { font-size: 12px; color: var(--el-text-color-secondary); }

.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
