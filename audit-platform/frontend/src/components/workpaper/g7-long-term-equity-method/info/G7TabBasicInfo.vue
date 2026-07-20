<template>
  <div class="g7-tab-basic-info">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-4 被投资单位基本信息</h3>
        <div class="sheet-subtitle">按控制关系分类编制，核对持股、表决权与会计处理结论</div>
      </div>
      <div class="head-actions">
        <el-dropdown trigger="click" :disabled="importExport.importing.value" @command="handleDropdownCommand">
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-4-basic-info')">💬复核</el-button>
        <GtIndexChip value="wp:G7-4" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <div>审计目标：了解被审计单位投资公司的基本情况。</div>
      <div class="audit-process">
        取得投资单位备查明细簿，结合以前年度审计情况及“子公司初始计量测试”，判断核算方法、控制关系和特殊表决权安排。
      </div>
    </el-alert>

    <div class="summary-bar">
      <div class="summary-left">
        <el-tag type="info">共 {{ rows.length }} 家</el-tag>
        <el-tag v-if="errorCount" type="danger">{{ errorCount }} 项错误</el-tag>
        <el-tag v-if="warningCount" type="warning">{{ warningCount }} 项待补全</el-tag>
        <span>比例统一按百分数填写，例如30表示30%。</span>
      </div>
      <div v-if="!isReadonly" class="summary-actions">
        <el-button size="small" :loading="syncing" @click="syncFromG72">从 G7-2 同步名单</el-button>
      </div>
    </div>

    <el-alert
      v-if="validationIssues.length"
      :type="errorCount ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <div v-for="(issue, index) in validationIssues.slice(0, 8)" :key="`${issue.rowId}-${index}`">
        {{ issue.message }}
      </div>
      <div v-if="validationIssues.length > 8">……另有 {{ validationIssues.length - 8 }} 项</div>
    </el-alert>

    <el-card
      v-for="group in G7_BASIC_INFO_GROUPS"
      :key="group.value"
      shadow="never"
      class="group-card"
    >
      <template #header>
        <div class="group-head">
          <div>
            <strong>{{ group.label }}</strong>
            <el-tag size="small" effect="plain" class="method-tag">{{ group.accountingMethod }}</el-tag>
          </div>
          <div class="group-actions">
            <span>{{ rowsForGroup(group.value).length }} 家</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              @click="addRow(group.value)"
            >
              新增
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rowsForGroup(group.value)"
        border
        size="small"
        row-key="id"
        empty-text="暂无被投资单位"
        class="basic-info-table"
      >
        <el-table-column label="序号" width="52" align="center" fixed="left">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>

        <el-table-column label="公司名称" min-width="180" fixed="left">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.investeeName"
              size="small"
              @change="value => updateText(row, 'investeeName', value)"
            />
            <span v-else>{{ display(row.investeeName) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="级次（国企适用）" min-width="120">
          <template #default="{ row }">
            <template v-if="isSubsidiary(row)">
              <el-input
                v-if="!isReadonly"
                :model-value="row.level"
                size="small"
                @change="value => updateText(row, 'level', value)"
              />
              <span v-else>{{ display(row.level) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="企业类型（国企适用）" min-width="190">
          <template #default="{ row }">
            <template v-if="isSubsidiary(row)">
              <el-select
                v-if="!isReadonly"
                :model-value="row.enterpriseType"
                clearable
                size="small"
                placeholder="请选择"
                @change="value => updateText(row, 'enterpriseType', value)"
              >
                <el-option
                  v-for="option in G7_ENTERPRISE_TYPE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <span v-else>{{ enterpriseTypeLabel(row.enterpriseType) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="本期新纳入合并范围（国企适用）" min-width="170">
          <template #default="{ row }">
            <template v-if="isSubsidiary(row)">
              <el-select
                v-if="!isReadonly"
                :model-value="row.newlyConsolidated"
                clearable
                size="small"
                placeholder="请选择"
                @change="value => updateText(row, 'newlyConsolidated', value)"
              >
                <el-option v-for="option in G7_YES_NO_OPTIONS" :key="option" :label="option" :value="option" />
              </el-select>
              <span v-else>{{ display(row.newlyConsolidated) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="主要经营地" min-width="130">
          <template #default="{ row }">
            <EditableText :row="row" field="principalPlace" :readonly="isReadonly" @change="updateText" />
          </template>
        </el-table-column>
        <el-table-column label="注册地" min-width="130">
          <template #default="{ row }">
            <EditableText :row="row" field="registeredPlace" :readonly="isReadonly" @change="updateText" />
          </template>
        </el-table-column>
        <el-table-column label="业务性质" min-width="150">
          <template #default="{ row }">
            <EditableText :row="row" field="businessNature" :readonly="isReadonly" @change="updateText" />
          </template>
        </el-table-column>

        <el-table-column label="注册资本" min-width="125" align="right">
          <template #default="{ row }">
            <EditableNumber :row="row" field="registeredCapital" :readonly="isReadonly" @change="updateNumber" />
          </template>
        </el-table-column>
        <el-table-column label="投资额" min-width="125" align="right">
          <template #default="{ row }">
            <EditableNumber :row="row" field="investmentAmount" :readonly="isReadonly" @change="updateNumber" />
          </template>
        </el-table-column>
        <el-table-column label="期末净资产" min-width="125" align="right">
          <template #default="{ row }">
            <EditableNumber :row="row" field="endingNetAssets" :readonly="isReadonly" @change="updateNumber" />
          </template>
        </el-table-column>
        <el-table-column label="本期净利润" min-width="125" align="right">
          <template #default="{ row }">
            <EditableNumber :row="row" field="currentNetProfit" :readonly="isReadonly" @change="updateNumber" />
          </template>
        </el-table-column>

        <el-table-column label="持股比例/享有的份额%" align="center">
          <el-table-column label="直接" min-width="105" align="right">
            <template #default="{ row }">
              <EditablePercent :row="row" field="directHoldingRatio" :readonly="isReadonly" @change="updateNumber" />
            </template>
          </el-table-column>
          <el-table-column label="间接" min-width="105" align="right">
            <template #default="{ row }">
              <EditablePercent :row="row" field="indirectHoldingRatio" :readonly="isReadonly" @change="updateNumber" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="表决权比例%" min-width="115" align="right">
          <template #default="{ row }">
            <EditablePercent
              v-if="row.groupType !== 'joint_operation'"
              :row="row"
              field="votingRatio"
              :readonly="isReadonly"
              @change="updateNumber"
            />
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="持股与表决权比例不一致的原因" min-width="230">
          <template #default="{ row }">
            <template v-if="row.groupType !== 'joint_operation'">
              <el-input
                v-if="!isReadonly"
                :model-value="row.holdingVotingDifferenceReason"
                type="textarea"
                :rows="2"
                :class="{ 'required-input': needsHoldingVotingReason(row) }"
                :placeholder="needsHoldingVotingReason(row) ? '持股比例与表决权比例不一致，请说明' : '如不一致请说明'"
                @change="value => updateText(row, 'holdingVotingDifferenceReason', value)"
              />
              <span v-else>{{ display(row.holdingVotingDifferenceReason) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="不足半数但形成控制的原因" min-width="230">
          <template #default="{ row }">
            <template v-if="isSubsidiary(row)">
              <el-input
                v-if="!isReadonly"
                :model-value="row.lessThanHalfControlReason"
                type="textarea"
                :rows="2"
                :class="{ 'required-input': needsLessThanHalfControlReason(row) }"
                :placeholder="needsLessThanHalfControlReason(row) ? '表决权不足半数，请填写控制依据' : '如适用请说明'"
                @change="value => updateText(row, 'lessThanHalfControlReason', value)"
              />
              <span v-else>{{ display(row.lessThanHalfControlReason) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="超过半数但未形成控制的原因" min-width="250">
          <template #default="{ row }">
            <template v-if="row.groupType !== 'joint_operation'">
              <el-input
                v-if="!isReadonly"
                :model-value="row.majorityNoControlReason"
                type="textarea"
                :rows="2"
                :class="{ 'required-input': needsMajorityNoControlReason(row) }"
                :placeholder="needsMajorityNoControlReason(row) ? '表决权达到半数，请说明未形成控制的依据' : '如适用请说明'"
                @change="value => updateText(row, 'majorityNoControlReason', value)"
              />
              <span v-else>{{ display(row.majorityNoControlReason) }}</span>
            </template>
            <span v-else class="not-applicable">--</span>
          </template>
        </el-table-column>

        <el-table-column label="取得方式" min-width="170">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.acquisitionMethod"
              filterable
              allow-create
              clearable
              size="small"
              placeholder="请选择或输入"
              @change="value => updateText(row, 'acquisitionMethod', value)"
            >
              <el-option v-for="option in ACQUISITION_METHOD_OPTIONS" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ display(row.acquisitionMethod) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="会计处理方法" min-width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.accountingMethod }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="62" fixed="right" align="center">
          <template #default="{ row }">
            <el-popconfirm :title="`确认删除「${row.investeeName || '该行'}」？`" @confirm="removeRow(row.id)">
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="说明资料来源、核对过程、控制判断依据及例外事项。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>企业类型和“是否本期新纳入合并范围”沿用原底稿下拉选项，仅对子公司适用。</li>
        <li>会计处理方法由投资关系自动确定：子公司成本法、合营/联营权益法、共同经营各项单独确认。</li>
        <li>持股与表决权比例不一致、未过半但控制、过半但不控制时，系统会提示补充判断依据。</li>
        <li>可从 G7-2 明细表同步子公司/合营/联营名单；共同经营需手工维护。</li>
        <li>历史小数比例（如0.30）打开时会自动换算为百分数（30）。</li>
      </ul>
    </details>

    <input ref="fileInput" class="hidden-file-input" type="file" accept=".xlsx" @change="onFileSelected">
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, inject, onMounted, reactive, ref } from 'vue'
import { ElInput, ElInputNumber, ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import {
  G7_BASIC_INFO_GROUPS,
  G7_ENTERPRISE_TYPE_OPTIONS,
  G7_YES_NO_OPTIONS,
  createG7BasicInfoRow,
  hasG7BasicInfoBlockingErrors,
  needsHoldingVotingReason,
  needsLessThanHalfControlReason,
  needsMajorityNoControlReason,
  normalizeG7BasicInfoRow,
  resequenceG7BasicInfoRows,
  serializeG7BasicInfoRows,
  sourcesFromG7DetailPayload,
  syncG7BasicInfoFromSources,
  validateG7BasicInfoRows,
  type G7BasicInfoGroup,
  type G7BasicInfoRow,
} from './g7BasicInfoModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)
const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const importExport = useG7EquityMethodImportExport({ wpId: computed(() => props.wpId) })

const ROWS_KEY = 'G7-4-rows'
const AUDIT_NOTE_KEY = 'G7-4-audit-note'
const AUDIT_CONCLUSION_KEY = 'G7-4-audit-conclusion'
const ACQUISITION_METHOD_OPTIONS = [
  '投资设立',
  '同一控制下企业合并',
  '非同一控制下企业合并',
  '股权受让',
  '增资取得',
  '其他',
]

const rows = reactive<G7BasicInfoRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const syncing = ref(false)

const validationIssues = computed(() => validateG7BasicInfoRows(rows))
const errorCount = computed(() => validationIssues.value.filter(issue => issue.severity === 'error').length)
const warningCount = computed(() => validationIssues.value.filter(issue => issue.severity === 'warning').length)

function display(value: unknown): string {
  return value === '' || value == null ? '—' : String(value)
}

function formatNumber(value: unknown): string {
  if (value === '' || value == null) return '—'
  const parsed = Number(value)
  return Number.isFinite(parsed)
    ? parsed.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    : String(value)
}

function enterpriseTypeLabel(value: string): string {
  return G7_ENTERPRISE_TYPE_OPTIONS.find(option => option.value === value)?.label ?? display(value)
}

function isSubsidiary(row: G7BasicInfoRow): boolean {
  return row.groupType === 'subsidiary'
}

function rowsForGroup(groupType: G7BasicInfoGroup): G7BasicInfoRow[] {
  return rows.filter(row => row.groupType === groupType)
}

function persistRows(options: { force?: boolean } = {}): void {
  if (isReadonly.value) return
  if (!options.force && hasG7BasicInfoBlockingErrors(rows)) {
    ElMessage.warning('存在阻断性校验错误（空名称/重复/比例越界等），已暂不写入，请先修正')
    return
  }
  formData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify(serializeG7BasicInfoRows(rows)),
    remark: null,
  })
}

function updateText(row: G7BasicInfoRow, field: keyof G7BasicInfoRow, value: unknown): void {
  ;(row as any)[field] = value == null ? '' : String(value)
  persistRows()
}

function updateNumber(row: G7BasicInfoRow, field: keyof G7BasicInfoRow, value: unknown): void {
  ;(row as any)[field] = value === '' || value == null ? null : Number(value)
  persistRows()
}

async function addRow(groupType: G7BasicInfoGroup): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入公司名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '公司名称不能为空',
      inputValidator: (name: string) => {
        const normalized = name?.trim()
        if (!normalized) return '公司名称不能为空'
        if (rows.some(row => row.investeeName === normalized)) return '该公司已存在'
        return true
      },
    })
    rows.push(createG7BasicInfoRow(groupType, rowsForGroup(groupType).length + 1, value.trim()))
    persistRows()
  } catch {
    // 用户取消
  }
}

function removeRow(id: string): void {
  const index = rows.findIndex(row => row.id === id)
  if (index < 0) return
  rows.splice(index, 1)
  resequenceG7BasicInfoRows(rows)
  persistRows()
}

function parseStoredRows(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value as Record<string, unknown>[]
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
  } catch {
    return []
  }
  return []
}

function hydrateRows(rawRows: Record<string, unknown>[]): void {
  rows.splice(0, rows.length, ...rawRows.map(normalizeG7BasicInfoRow))
  resequenceG7BasicInfoRows(rows)
}

function rowsFromHtmlData(): Record<string, unknown>[] {
  const basicInfo = props.htmlData?.basicInfo ?? props.htmlData?.basic_info ?? props.htmlData
  return Array.isArray(basicInfo?.rows) ? basicInfo.rows : []
}

function saveAuditNote(value: string): void {
  if (isReadonly.value) return
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: value, conclusion: null })
}

function saveAuditConclusion(value: string): void {
  if (isReadonly.value) return
  formData.debouncedSave(AUDIT_CONCLUSION_KEY, { remark: value, conclusion: null })
}

async function handleDropdownCommand(command: string): Promise<void> {
  if (command === 'template') await importExport.exportTemplate('G7-4')
  if (command === 'export') await importExport.exportData('G7-4')
  if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-4', file)
  if (!result) return
  await formData.loadResponses()
  hydrateRows(parseStoredRows(formData.data.value.get(ROWS_KEY)?.conclusion))
}

async function syncFromG72(): Promise<void> {
  if (isReadonly.value || !props.wpId || syncing.value) return
  syncing.value = true
  try {
    const response = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(response) ? response : (response?.data ?? [])
    const stored = items.find((item: any) => item.item_id === 'G7-2-rows')
    if (!stored?.conclusion) {
      ElMessage.warning('未找到 G7-2 明细数据，请先在明细表维护被投资单位')
      return
    }
    let payload: unknown = stored.conclusion
    if (typeof payload === 'string') {
      try { payload = JSON.parse(payload) } catch { payload = [] }
    }
    const sources = sourcesFromG7DetailPayload(payload)
    if (!sources.length) {
      ElMessage.warning('G7-2 中没有可同步的子公司/合营/联营单位')
      return
    }
    const result = syncG7BasicInfoFromSources(rows, sources)
    rows.splice(0, rows.length, ...result.rows)
    persistRows()
    ElMessage.success(`已同步：新增 ${result.added} 家，回填 ${result.filled} 项空字段`)
  } catch {
    ElMessage.error('从 G7-2 同步失败')
  } finally {
    syncing.value = false
  }
}

const EditableText = defineComponent({
  props: {
    row: { type: Object, required: true },
    field: { type: String, required: true },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', display((componentProps.row as any)[componentProps.field]))
      : h(ElInput, {
          modelValue: (componentProps.row as any)[componentProps.field],
          size: 'small',
          onChange: (value: string) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})

const EditableNumber = defineComponent({
  props: {
    row: { type: Object, required: true },
    field: { type: String, required: true },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', formatNumber((componentProps.row as any)[componentProps.field]))
      : h(ElInputNumber, {
          modelValue: (componentProps.row as any)[componentProps.field],
          controls: false,
          precision: 2,
          size: 'small',
          class: 'cell-number',
          onChange: (value: number | undefined) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})

const EditablePercent = defineComponent({
  props: {
    row: { type: Object, required: true },
    field: { type: String, required: true },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', (componentProps.row as any)[componentProps.field] == null
          ? '—'
          : `${formatNumber((componentProps.row as any)[componentProps.field])}%`)
      : h(ElInputNumber, {
          modelValue: (componentProps.row as any)[componentProps.field],
          controls: false,
          precision: 4,
          min: 0,
          max: 100,
          size: 'small',
          class: 'cell-number',
          onChange: (value: number | undefined) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})

onMounted(async () => {
  await formData.load()
  const htmlRows = rowsFromHtmlData()
  const savedRows = parseStoredRows(formData.data.value.get(ROWS_KEY)?.conclusion)
  hydrateRows(savedRows.length ? savedRows : htmlRows)
  // 迁移后的百分数立刻落盘，避免下次再次按小数解释
  if (savedRows.length) persistRows({ force: true })
  auditNote.value = formData.data.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
  auditConclusion.value = formData.data.value.get(AUDIT_CONCLUSION_KEY)?.remark ?? ''
})
</script>

<style scoped>
.g7-tab-basic-info { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head, .group-head, .summary-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-head { margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 16px; }
.sheet-subtitle { margin-top: 4px; color: #909399; font-size: 12px; }
.head-actions, .group-actions { display: flex; align-items: center; gap: 8px; }
.audit-objective { margin-bottom: 10px; }
.audit-process { margin-top: 4px; color: #606266; }
.summary-bar { margin-bottom: 10px; color: #606266; font-size: 12px; }
.summary-left, .summary-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.validation-alert { margin-bottom: 12px; }
.group-card { margin-bottom: 12px; }
.method-tag { margin-left: 8px; }
.basic-info-table { width: 100%; }
.not-applicable { display: block; text-align: center; color: #a8abb2; }
.required-input :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px #e6a23c inset; }
.cell-number { width: 100%; }
.conclusion-card { margin-top: 14px; }
.prep-hint { margin-top: 14px; color: #606266; font-size: 12px; }
.prep-hint summary { cursor: pointer; font-weight: 600; }
.prep-hint ul { margin: 8px 0 0; padding-left: 20px; line-height: 1.8; }
.hidden-file-input { display: none; }
</style>
