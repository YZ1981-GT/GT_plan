<template>
  <div class="g7-tab-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G7-18 凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine
          v-if="!isReadonly && wpId && projectId"
          :project-id="projectId"
          :workpaper-id="wpId"
          account-code="1511"
          phase="final"
          :year="auditYear"
          @filled="onSampleFilled"
        />
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow">+ 新增</el-button>
        <el-dropdown @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('voucher-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-18-voucher-check')">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：抽取长期股权投资（科目1511）相关记账凭证，核对原始凭证完整性、授权审批、账务处理、金额准确性、科目分类及投资收益确认的正确性，确认凭证真实、合规且借贷平衡。
    </el-alert>

    <el-skeleton v-if="loading" :rows="6" animated />
    <div v-else class="voucher-check-content">
      <!-- 二、样本选取标准与检查比例 -->
      <el-card shadow="never" class="criteria-card">
        <template #header>
          <div class="card-header-row">
            <span>二、样本选取标准与结果</span>
            <el-button size="small" link type="primary" @click="showMethodGuide = !showMethodGuide">
              {{ showMethodGuide ? '收起方法说明' : '选取方法说明' }}
            </el-button>
          </div>
        </template>
        <div class="criteria-grid">
          <div class="cg-item cg-full">
            <label>测试范围</label>
            <el-input
              v-model="criteria.testScope"
              size="small"
              :disabled="isReadonly"
              placeholder="长期股权投资（1511）借方、贷方发生额检查（含取得/追加/处置/股利/减值）"
              @change="persistCriteria"
            />
          </div>
          <div class="cg-item">
            <label>抽样总体（笔数 / 金额）</label>
            <div class="cg-inline">
              <el-input-number
                v-model="criteria.populationCount"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                class="num-sm"
                @change="persistCriteria"
              />
              <span class="cg-unit">笔</span>
              <el-input-number
                v-model="criteria.populationAmount"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                class="num-md"
                @change="persistCriteria"
              />
              <span class="cg-unit">元</span>
            </div>
          </div>
          <div class="cg-item">
            <label>抽样方法</label>
            <el-select v-model="criteria.samplingMethod" size="small" :disabled="isReadonly" @change="persistCriteria">
              <el-option label="随机选样" value="随机选样" />
              <el-option label="系统选样" value="系统选样" />
              <el-option label="货币单元抽样(MUS)" value="MUS" />
              <el-option label="选取特定项目" value="特定项目" />
              <el-option label="选取全部项目" value="全部项目" />
            </el-select>
          </div>
          <div class="cg-item cg-full">
            <label>特定样本</label>
            <el-input
              v-model="criteria.specificSample"
              size="small"
              :disabled="isReadonly"
              placeholder="超过重要性水平、关联方股权交易、异常处置/减值等全部测试，共XX笔"
              @change="persistCriteria"
            />
          </div>
          <div class="cg-item">
            <label>代表性样本量</label>
            <el-input-number
              v-model="criteria.representativeSize"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="persistCriteria"
            />
          </div>
          <div class="cg-item">
            <label>账面期末余额（检查比例用）</label>
            <el-input-number
              v-model="criteria.endBalance"
              :controls="false"
              size="small"
              :disabled="isReadonly"
              @change="persistCriteria"
            />
          </div>
        </div>
        <div v-if="showMethodGuide" class="method-guide">
          <p><b>（1）选取全部项目：</b>总体较小或存在重大股权交易、关联方投资、重大估计变更时适用。</p>
          <p><b>（2）选取特定项目：</b>大额取得/处置、超过阈值、异常或高风险项目；不能推断至总体。</p>
          <p><b>（3）审计抽样：</b>可分层后随机/系统/MUS；样本量结合置信水平与错报风险判断。</p>
        </div>
        <el-table :data="checkRatios" border size="small" class="ratio-table" style="font-size: 13px">
          <el-table-column label="方向" prop="direction" width="120" />
          <el-table-column label="账面金额" align="right" width="140">
            <template #default="{ row }">{{ Number(row.bookAmount || 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="已检查金额" align="right" width="140">
            <template #default="{ row }">{{ Number(row.checkedAmount || 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="检查比例" width="120" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="row.ratio != null"
                size="small"
                :type="row.ratio >= 0.3 ? 'success' : (row.bookAmount > 0 ? 'warning' : 'info')"
              >
                {{ (row.ratio * 100).toFixed(1) }}%
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table>
        <el-alert
          v-if="lowRatioWarnings.length"
          type="warning"
          :closable="false"
          show-icon
          class="ratio-warn"
          :title="`检查比例偏低：${lowRatioWarnings.map(r => r.direction).join('、')}，请评估是否扩样或补充说明`"
        />
      </el-card>

      <div class="tab-toolbar">
        <div class="toolbar-left"><span class="section-label">三、测试 · 凭证检查明细</span></div>
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:G7-18" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
          <el-tag v-if="abnormalCount" size="small" type="danger">异常 {{ abnormalCount }}</el-tag>
        </div>
      </div>

      <div class="balance-summary" :class="{ 'is-unbalanced': !isBalanced }">
        <span>借方合计: {{ debitTotal.toFixed(2) }}</span>
        <span>贷方合计: {{ creditTotal.toFixed(2) }}</span>
        <span v-if="!isBalanced" class="diff-warning">差额: {{ (debitTotal - creditTotal).toFixed(2) }}</span>
        <el-tag v-else type="success" size="small">借贷平衡</el-tag>
      </div>

      <el-tabs v-model="activeTab" type="border-card" class="voucher-tabs">
        <el-tab-pane label="凭证基础(7列)" name="voucher">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column label="日期" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.voucherDate" size="small" @change="persistRows" />
                <span v-else>{{ row.voucherDate }}</span>
              </template>
            </el-table-column>
            <el-table-column label="凭证号" width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
                <span v-else>{{ row.voucherNo }}</span>
              </template>
            </el-table-column>
            <el-table-column label="业务内容" min-width="150">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persistRows" />
                <span v-else>{{ row.businessContent }}</span>
              </template>
            </el-table-column>
            <el-table-column label="对方科目" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" @change="persistRows" />
                <span v-else>{{ row.counterAccount }}</span>
              </template>
            </el-table-column>
            <el-table-column label="借方" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.debitAmount"
                  :controls="false"
                  :precision="2"
                  size="small"
                  style="width: 100%"
                  @change="persistRows"
                />
                <span v-else>{{ Number(row.debitAmount || 0).toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="贷方" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.creditAmount"
                  :controls="false"
                  :precision="2"
                  size="small"
                  style="width: 100%"
                  @change="persistRows"
                />
                <span v-else>{{ Number(row.creditAmount || 0).toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="📎" width="50" align="center">
              <template #default="{ row }">
                <el-button v-if="!isReadonly" link size="small" @click="handleOCR(row)">📎</el-button>
                <span v-else-if="row.attachment">✓</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="70">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="handleRemoveRow(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="核对内容(7列)" name="check">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column label="支持性文件" min-width="150">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" @change="persistRows" />
                <span v-else>{{ row.supportingDoc }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原始凭证" width="80" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check1Original" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
            <el-table-column label="授权" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check2Authorization" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
            <el-table-column label="账务" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check3Accounting" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
            <el-table-column label="金额" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check4Amount" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
            <el-table-column label="分类" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check5Classification" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
            <el-table-column label="投资收益" width="85" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check6InvestmentIncome" :disabled="isReadonly" @change="persistRows" />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="结论(5列)" name="conclusion">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column label="索引" width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="persistRows" />
                <span v-else>{{ row.indexRef }}</span>
              </template>
            </el-table-column>
            <el-table-column label="是否异常" width="85" align="center">
              <template #default="{ row }">
                <el-tag :type="isRowAbnormal(row) ? 'danger' : 'success'" size="small">
                  {{ isRowAbnormal(row) ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="异常说明" min-width="150">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.abnormalNote" size="small" @change="persistRows" />
                <span v-else>{{ row.abnormalNote }}</span>
              </template>
            </el-table-column>
            <el-table-column label="风险等级" width="110" align="center">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" v-model="row.riskLevel" size="small" clearable @change="persistRows">
                  <el-option label="低" value="低" />
                  <el-option label="中" value="中" />
                  <el-option label="高" value="高" />
                </el-select>
                <span v-else>{{ row.riskLevel }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persistRows" />
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="PAGE_SIZE"
          :total="rows.length"
          layout="prev, pager, next, total"
          small
        />
      </div>
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="conclusion-header"><span>审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述抽样范围、凭证核对情况及结果，发现的异常及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('voucher-conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对凭证检查的审计结论..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>先填写样本选取标准与总体金额，检查比例 = 已检查金额 ÷ 账面/总体金额</li>
        <li>核对6要素：原始凭证完整、授权审批、账务处理正确、金额准确、科目分类恰当、投资收益确认无误</li>
        <li>任一核对项未通过 → 该行「是否异常」自动标记为「是」，须填写异常说明</li>
        <li>借贷合计应平衡；可用抽凭引擎按科目 1511 抽样回填</li>
        <li>字段与导入导出/后端一致：check1Original / supportingDoc / check4Amount / indexRef / abnormalNote</li>
      </ul>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx" class="hidden-input" @change="handleFileChange">
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabVoucherCheck — G7-18 凭证检查表
 * 持久化 G7-18-rows / G7-18-criteria；字段对齐后端 IE；抽凭引擎科目 1511。
 * Runtime Boundary：保存后 scheduleAutoSnapshot。
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import { isDebitCreditBalanced, parseNum } from '../../composables/useG7SubFormulaEngine'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
/** 审计年度：从 htmlData.project_context 派生（audit_year → bs_date 年份 → 当前年），供抽凭引擎按年度查询序时账 */
const auditYear = computed<number>(() => {
  const ctx = (props.htmlData?.project_context ?? {}) as Record<string, any>
  const y = ctx.audit_year ?? ctx.auditYear
  if (y) return Number(y)
  const bs = ctx.bs_date ?? ctx.bsDate
  if (typeof bs === 'string' && bs.length >= 4) return Number(bs.slice(0, 4))
  return new Date().getFullYear()
})
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)

const PAGE_SIZE = 30
const ROWS_KEY = 'G7-18-rows'
const CRITERIA_KEY = 'G7-18-criteria'
const NOTE_KEY = 'G7-18-voucher-audit-note'
const CONCLUSION_KEY = 'G7-18-voucher-audit-conclusion'

interface G7SampleCriteria {
  testScope: string
  populationCount: number
  populationAmount: number
  samplingMethod: string
  specificSample: string
  representativeSize: number
  endBalance: number
  populationDebitAmount: number
  populationCreditAmount: number
}

interface G7CheckRatioRow {
  direction: string
  bookAmount: number
  checkedAmount: number
  ratio: number | null
}

function emptyCriteria(): G7SampleCriteria {
  return {
    testScope: '长期股权投资（1511）借方、贷方发生额检查（含取得/追加/处置/股利/减值）',
    populationCount: 0,
    populationAmount: 0,
    samplingMethod: '随机选样',
    specificSample: '',
    representativeSize: 0,
    endBalance: 0,
    populationDebitAmount: 0,
    populationCreditAmount: 0,
  }
}

const activeTab = ref<'voucher' | 'check' | 'conclusion'>('voucher')
const activeRowIndex = ref(0)
const currentPage = ref(1)
const conclusionText = ref('')
const aiLoading = ref(false)
const loading = ref(true)
const rows = ref<Record<string, any>[]>([])
const criteria = ref<G7SampleCriteria>(emptyCriteria())
const showMethodGuide = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const auditNote = ref('')

const rowCount = computed(() => rows.value.length)
const abnormalCount = computed(() => rows.value.filter(isRowAbnormal).length)

const auditFormData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const importExport = useG7SubImportExport({
  wpId: computed(() => props.wpId),
})

function createEmptyRow(seq: number): Record<string, any> {
  return {
    id: `g18-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    attachment: '',
    supportingDoc: '',
    check1Original: false,
    check2Authorization: false,
    check3Accounting: false,
    check4Amount: false,
    check5Classification: false,
    check6InvestmentIncome: false,
    indexRef: '',
    isAbnormal: false,
    abnormalNote: '',
    riskLevel: '',
    remark: '',
  }
}

/** 兼容旧前端字段名 → 后端 IE 字段 */
function normalizeRow(raw: Record<string, any>, index: number): Record<string, any> {
  const row = {
    ...createEmptyRow(index + 1),
    ...raw,
    id: raw.id || `g18-${Date.now()}-${index}`,
    seq: index + 1,
  }
  if (raw.check1OriginalComplete != null && raw.check1Original == null) {
    row.check1Original = !!raw.check1OriginalComplete
  }
  if (raw.check4AmountCorrect != null && raw.check4Amount == null) {
    row.check4Amount = !!raw.check4AmountCorrect
  }
  if (raw.supportingDocDesc != null && !raw.supportingDoc) {
    row.supportingDoc = raw.supportingDocDesc
  }
  if (raw.abnormalDesc != null && !raw.abnormalNote) {
    row.abnormalNote = raw.abnormalDesc
  }
  if (raw.indexNo != null && !raw.indexRef) {
    row.indexRef = raw.indexNo
  }
  row.debitAmount = parseNum(row.debitAmount)
  row.creditAmount = parseNum(row.creditAmount)
  row.isAbnormal = isRowAbnormal(row)
  return row
}

function parseRows(raw: unknown): Record<string, any>[] {
  const source = Array.isArray(raw)
    ? raw
    : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows) ? (raw as any).rows : [])
  return source.map((r: any, i: number) => normalizeRow(r || {}, i))
}

function parseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function persistRows(): void {
  if (isReadonly.value) return
  for (const r of rows.value) r.isAbnormal = isRowAbnormal(r)
  auditFormData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify(rows.value),
    remark: null,
  })
}

function persistCriteria(): void {
  if (isReadonly.value) return
  // 未单独填借贷总体时，用抽样总体金额兜底借方账面
  if (!criteria.value.populationDebitAmount && criteria.value.populationAmount) {
    criteria.value.populationDebitAmount = criteria.value.populationAmount
  }
  auditFormData.debouncedSave(CRITERIA_KEY, {
    remark: JSON.stringify(criteria.value),
    conclusion: null,
  })
}

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (isReadonly.value) return
  conclusionText.value = val
  auditFormData.debouncedSave(CONCLUSION_KEY, { remark: val, conclusion: null })
}

const pageRows = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return rows.value.slice(start, start + PAGE_SIZE)
})

const debitTotal = computed(() =>
  rows.value.reduce((sum, r) => sum + parseNum(r.debitAmount), 0),
)
const creditTotal = computed(() =>
  rows.value.reduce((sum, r) => sum + parseNum(r.creditAmount), 0),
)
const isBalanced = computed(() =>
  isDebitCreditBalanced(
    rows.value.map(r => parseNum(r.debitAmount)),
    rows.value.map(r => parseNum(r.creditAmount)),
  ),
)

const checkRatios = computed<G7CheckRatioRow[]>(() => {
  const mk = (direction: string, book: number, checked: number): G7CheckRatioRow => ({
    direction,
    bookAmount: book,
    checkedAmount: checked,
    ratio: book > 0 ? checked / book : null,
  })
  const debitBook = criteria.value.populationDebitAmount || criteria.value.populationAmount || 0
  const creditBook = criteria.value.populationCreditAmount || 0
  const endBook = criteria.value.endBalance || 0
  return [
    mk('本期借方', debitBook, debitTotal.value),
    mk('本期贷方', creditBook, creditTotal.value),
    mk('期末余额', endBook, Math.abs(debitTotal.value - creditTotal.value) || debitTotal.value),
  ]
})

const lowRatioWarnings = computed(() =>
  checkRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0),
)

function isRowAbnormal(row: any): boolean {
  if (!row.voucherNo && !parseNum(row.debitAmount) && !parseNum(row.creditAmount)) return false
  return !(
    row.check1Original
    && row.check2Authorization
    && row.check3Accounting
    && row.check4Amount
    && row.check5Classification
    && row.check6InvestmentIncome
  )
}

function handleRowChange(row: any) {
  if (row) {
    const idx = rows.value.findIndex(r => r.id === row.id)
    if (idx >= 0) activeRowIndex.value = idx
  }
}

function getAbsoluteIndex(pageIndex: number): number {
  return (currentPage.value - 1) * PAGE_SIZE + pageIndex + 1
}

function handleAddRow(): void {
  if (isReadonly.value) return
  rows.value.push(createEmptyRow(rows.value.length + 1))
  persistRows()
}

function handleRemoveRow(id: string): void {
  const idx = rows.value.findIndex(r => r.id === id)
  if (idx < 0) return
  rows.value.splice(idx, 1)
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

function onSampleFilled(payload: {
  samples?: Array<{
    summary?: string
    amount?: number
    debitAmount?: number
    creditAmount?: number
    voucherDate?: string
    voucherNo?: string
    counterAccount?: string
  }>
}): void {
  if (isReadonly.value) return
  const samples = payload.samples ?? []
  if (!samples.length) {
    ElMessage.info('未收到抽凭样本')
    return
  }
  for (const s of samples) {
    const row = createEmptyRow(rows.value.length + 1)
    row.voucherDate = s.voucherDate || ''
    row.voucherNo = s.voucherNo || ''
    row.businessContent = s.summary || ''
    row.counterAccount = s.counterAccount || ''
    const amt = parseNum(s.debitAmount ?? s.amount)
    const credit = parseNum(s.creditAmount)
    if (credit) {
      row.creditAmount = credit
      row.debitAmount = amt
    } else {
      row.debitAmount = amt
      row.creditAmount = 0
    }
    row.source = '抽凭'
    rows.value.push(row)
  }
  if (!criteria.value.representativeSize) {
    criteria.value.representativeSize = samples.length
    persistCriteria()
  }
  persistRows()
  ElMessage.success(`已回填 ${samples.length} 笔抽凭样本`)
}

async function handleOCR(row: Record<string, any>): Promise<void> {
  if (isReadonly.value) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, fd)
      const data = res?.data?.data ?? res?.data ?? {}
      const preview = [
        data.voucherDate || data.date || '',
        data.voucherNo || data.voucher_no || '',
        data.businessContent || data.summary || data.content || '',
      ].filter(Boolean).join(' / ') || '（未识别到结构化字段）'
      await ElMessageBox.confirm(`OCR 识别结果：${preview}\n是否填入当前行？`, '确认 OCR 回填', {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
      })
      if (data.voucherDate || data.date) row.voucherDate = data.voucherDate || data.date
      if (data.voucherNo || data.voucher_no) row.voucherNo = data.voucherNo || data.voucher_no
      if (data.businessContent || data.summary || data.content) {
        row.businessContent = data.businessContent || data.summary || data.content
      }
      if (data.counterAccount) row.counterAccount = data.counterAccount
      if (data.debitAmount != null) row.debitAmount = parseNum(data.debitAmount)
      if (data.creditAmount != null) row.creditAmount = parseNum(data.creditAmount)
      row.attachment = file.name
      persistRows()
      ElMessage.success('OCR 已回填')
    } catch (e: any) {
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.warning('OCR 暂不可用，请手工填写')
      }
    }
  }
  input.click()
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void importExport.exportTemplate('G7-18')
  else if (command === 'export') void importExport.exportData('G7-18')
  else if (command === 'import') fileInputRef.value?.click()
}

async function handleFileChange(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    await importExport.importData('G7-18', file)
    await auditFormData.load()
    const saved = auditFormData.data.value.get(ROWS_KEY)
    const loaded = parseRows(parseJson(saved?.conclusion as string | undefined))
    rows.value = loaded.length ? loaded : rows.value
    ElMessage.success(loaded.length ? '导入完成' : '导入完成，请核对行数据')
  } catch {
    ElMessage.error('导入失败')
  }
}

function hydrateCriteria(raw: unknown): void {
  if (!raw || typeof raw !== 'object') return
  criteria.value = { ...emptyCriteria(), ...(raw as Record<string, any>) }
}

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.remark) conclusionText.value = c.remark

  const critSaved = auditFormData.data.value.get(CRITERIA_KEY)
  let critRaw = parseJson(critSaved?.remark as string | undefined)
  if (!critRaw) {
    const snap = props.htmlData?.responses_snapshot?.[CRITERIA_KEY]
    critRaw = parseJson(snap?.remark) ?? snap
  }
  hydrateCriteria(critRaw)

  const saved = auditFormData.data.value.get(ROWS_KEY)
  let loaded = parseRows(parseJson(saved?.conclusion as string | undefined)
    ?? parseJson(saved?.remark as string | undefined))
  if (!loaded.length) {
    const snapshot = props.htmlData?.responses_snapshot?.[ROWS_KEY]
    loaded = parseRows(parseJson(snapshot?.conclusion) ?? parseJson(snapshot?.remark))
  }
  if (!loaded.length) {
    loaded = parseRows(props.htmlData?.voucherCheck?.rows ?? props.htmlData?.voucherCheck)
  }
  rows.value = loaded
  loading.value = false
})

async function handleAi(section: string): Promise<void> {
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/${section}`,
      {
        existingContent: conclusionText.value,
        relatedContext: {
          sheet: 'G7-18',
          accountCode: '1511',
          rowCount: rows.value.length,
          abnormalCount: abnormalCount.value,
          debitTotal: debitTotal.value,
          creditTotal: creditTotal.value,
          isBalanced: isBalanced.value,
          samplingMethod: criteria.value.samplingMethod,
          populationAmount: criteria.value.populationAmount,
          representativeSize: criteria.value.representativeSize || rows.value.length,
          checkRatios: checkRatios.value,
          lowRatioDirections: lowRatioWarnings.value.map(r => r.direction),
        },
      },
    )
    const text = extractG7AiText(res?.data)
    if (text) {
      conclusionText.value = text
      saveAuditConclusion(text)
      ElMessage.success('AI结论已生成')
    } else {
      ElMessage.warning('AI辅助暂未连接，请手动填写')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.g7-tab-voucher-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 4px 0 0 16px; line-height: 1.8; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.criteria-card { margin-bottom: 12px; }
.card-header-row { display: flex; justify-content: space-between; align-items: center; }
.criteria-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
  margin-bottom: 12px;
}
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item label { font-size: 12px; color: #606266; }
.cg-full { grid-column: 1 / -1; }
.cg-inline { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cg-unit { font-size: 12px; color: #909399; }
.num-sm { width: 80px; }
.num-md { width: 140px; }
.method-guide {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}
.method-guide p { margin: 0 0 4px; }
.ratio-table { margin-top: 4px; }
.ratio-warn { margin-top: 8px; }
.section-label { font-size: 13px; font-weight: 600; color: #303133; }

.balance-summary {
  display: flex;
  gap: 24px;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.balance-summary.is-unbalanced { background: #fef0f0; }
.diff-warning { color: #f56c6c; font-weight: 600; }

.voucher-tabs { margin-bottom: 8px; overflow: hidden; }
.voucher-tabs :deep(.el-tabs__content) { overflow: hidden; }
.voucher-tabs :deep(.el-table) { width: 100% !important; }
.pagination-wrapper { display: flex; justify-content: center; padding: 8px 0; }
.conclusion-card, .audit-note-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; }
.hidden-input { display: none; }
</style>
