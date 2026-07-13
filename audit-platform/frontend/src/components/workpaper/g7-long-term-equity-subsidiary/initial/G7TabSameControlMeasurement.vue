<!--
  G7TabSameControlMeasurement.vue — G7-8 同一控制下企业合并初始计量测试（52行×9列）

  方法论上下文区域（琥珀色左边线+浅黄背景：CAS20同控合并规则）
  蓝色渐变引导区（4步骤指引, 2列grid）

  9列单表：
  被投资单位|合并日|合并方式(下拉)|被合并方账面净资产|持股比例|享有份额(公式=calcSameControlCost)|
  初始投资成本(=享有份额)|支付对价|差额处理(textarea)|审计结论

  公式列：shareOfNetAssets = calcSameControlCost(acquireeNetAssets, shareholdingRatio)
  差额 = consideration - initialCost → 调整资本公积→留存收益
  差额过大(>初始成本50%)→橙色高亮+tooltip提示

  动态行增删(ElMessageBox.prompt命名)
  导入导出el-dropdown(useG7SubImportExport, sheet='G7-8')
  AI辅助(initial-measurement-conclusion)
  复核对话(inject openReviewDialog)

  Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 5.1
  Requirements: 3.1, 3.3, 3.5
-->
<template>
  <div class="g7-tab-same-control">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-8 同一控制下企业合并初始计量测试</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" link @click="handleAiConclusion">
          🤖 AI辅助
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-8-same-control')">💬复核</el-button>
      </div>
    </div>

    <!-- 蓝色渐变引导区（4步骤指引, 2列grid） -->
    <div class="guidance-steps">
      <div class="step-item">
        <span class="step-num">①</span>
        <span class="step-text">新增被投资单位并填写合并日与合并方式</span>
      </div>
      <div class="step-item">
        <span class="step-num">②</span>
        <span class="step-text">填入被合并方账面净资产和持股比例</span>
      </div>
      <div class="step-item">
        <span class="step-num">③</span>
        <span class="step-text">系统自动计算享有份额(=初始投资成本)</span>
      </div>
      <div class="step-item">
        <span class="step-num">④</span>
        <span class="step-text">填入支付对价，系统提示差额处理方式</span>
      </div>
    </div>

    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>同一控制下企业合并（CAS20）：</strong></p>
      <p>• 合并方以被合并方净资产的<strong>账面价值</strong>份额作为长期股权投资初始成本</p>
      <p>• 初始投资成本 = 被合并方所有者权益账面价值 × 持股比例</p>
      <p>• 差额处理：支付对价与初始成本的差额，先调整资本公积(股本溢价)，不足部分调整留存收益</p>
      <p>• 同控合并<strong>不确认商誉</strong></p>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：验证同一控制下企业合并的长期股权投资初始投资成本按被合并方净资产账面价值份额确定（CAS20），支付对价与初始成本的差额调整资本公积/留存收益处理恰当，未确认商誉。" />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-8" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <!-- 52行×9列数据表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      class="same-control-table"
      :max-height="600"
      highlight-current-row
      row-key="id"
    >
      <!-- #序号 -->
      <el-table-column type="index" label="#" width="45" align="center" fixed />

      <!-- 被投资单位 -->
      <el-table-column label="被投资单位" min-width="140" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <!-- 合并日 -->
      <el-table-column label="合并日" min-width="140" align="center">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            v-model="row.mergerDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="emitSave"
          />
          <span v-else>{{ row.mergerDate || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 合并方式(下拉) -->
      <el-table-column label="合并方式" min-width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.mergerType"
            size="small"
            placeholder="请选择"
            style="width: 100%"
            @change="emitSave"
          >
            <el-option value="吸收合并" label="吸收合并" />
            <el-option value="控股合并" label="控股合并" />
            <el-option value="新设合并" label="新设合并" />
          </el-select>
          <span v-else>{{ row.mergerType || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 被合并方账面净资产 -->
      <el-table-column label="被合并方账面净资产" min-width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.acquireeNetAssets"
            size="small"
            :controls="false"
            style="width: 100%"
            @update:model-value="(v: number) => updateField(row, 'acquireeNetAssets', v)"
          />
          <span v-else>{{ fmtAmount(row.acquireeNetAssets) }}</span>
        </template>
      </el-table-column>

      <!-- 持股比例 -->
      <el-table-column label="持股比例" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.shareholdingRatio"
            size="small"
            :controls="false"
            :precision="4"
            :step="0.01"
            :min="0"
            :max="1"
            style="width: 100%"
            @update:model-value="(v: number) => updateField(row, 'shareholdingRatio', v)"
          />
          <span v-else>{{ fmtPercent(row.shareholdingRatio) }}</span>
        </template>
      </el-table-column>

      <!-- 享有份额(公式列：calcSameControlCost) -->
      <el-table-column label="享有份额" min-width="140" align="right">
        <template #header>
          <el-tooltip content="公式: 被合并方账面净资产 × 持股比例" placement="top">
            <span class="formula-header">享有份额 <span class="formula-icon">ƒ</span></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="= 被合并方账面净资产 × 持股比例 (CAS20同控)" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.shareOfNetAssets) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 初始投资成本(=享有份额) -->
      <el-table-column label="初始投资成本" min-width="140" align="right">
        <template #header>
          <el-tooltip content="同控合并下初始成本 = 享有份额" placement="top">
            <span class="formula-header">初始投资成本 <span class="formula-icon">ƒ</span></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="= 享有份额（同控合并按账面价值入账）" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.initialCost) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 支付对价 -->
      <el-table-column label="支付对价" min-width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.consideration"
            size="small"
            :controls="false"
            style="width: 100%"
            @update:model-value="(v: number) => updateField(row, 'consideration', v)"
          />
          <span v-else>{{ fmtAmount(row.consideration) }}</span>
        </template>
      </el-table-column>

      <!-- 差额处理(textarea) -->
      <el-table-column label="差额处理" min-width="180">
        <template #default="{ row }">
          <div class="difference-cell">
            <el-tag
              v-if="getDifference(row) !== 0"
              size="small"
              :type="isDifferenceLarge(row) ? 'warning' : 'info'"
              class="diff-tag"
            >
              差额: {{ fmtAmount(getDifference(row)) }}
            </el-tag>
            <el-tooltip
              v-if="isDifferenceLarge(row)"
              content="差额较大，请核实对价与账面份额的合理性"
              placement="top"
            >
              <span class="diff-warning">⚠</span>
            </el-tooltip>
          </div>
          <el-input
            v-if="!isReadonly"
            v-model="row.differenceHandling"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            placeholder="差额调整：资本公积(股本溢价)→留存收益"
            @change="emitSave"
          />
          <span v-else class="text-cell">{{ row.differenceHandling || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 审计结论 -->
      <el-table-column label="审计结论" min-width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.auditConclusion"
            size="small"
            placeholder="请选择"
            style="width: 100%"
            @change="emitSave"
          >
            <el-option value="无差异" label="无差异" />
            <el-option value="差异可接受" label="差异可接受" />
            <el-option value="差异需调整" label="差异需调整" />
          </el-select>
          <el-tag v-else size="small" :type="conclusionTagType(row.auditConclusion)">
            {{ row.auditConclusion || '-' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」此行?`" @confirm="deleteRow(row)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <div v-if="rows.length === 0" class="empty-state">
      <p>暂无同控合并初始计量测试数据</p>
      <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">
        + 新增被投资单位
      </el-button>
    </div>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计说明</span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :readonly="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link @click="handleAiConclusion">
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据同控合并初始计量测试结果，总结各被投资单位入账金额是否准确..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 同一控制下企业合并，合并方以被合并方净资产<strong>账面价值</strong>的份额作为初始投资成本</p>
        <p>2. 初始投资成本 = 被合并方所有者权益账面价值 × 持股比例（公式自动计算）</p>
        <p>3. 差额 = 支付对价 - 初始投资成本：正差额先冲资本公积(股本溢价)，不足冲留存收益；负差额增加资本公积</p>
        <p>4. 同控合并不确认商誉，与非同控合并(G7-9)有本质区别</p>
        <p>5. 合并方式包括：吸收合并(目标注销)、控股合并(目标存续为子公司)、新设合并(双方合为新公司)</p>
        <p>6. 公式列显示虚线下划线，鼠标悬停可查看公式来源</p>
      </div>
    </details>

    <!-- 隐藏文件上传(导入) -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileChange" />
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabSameControlMeasurement — G7-8 同控初始计量测试（52行×9列）
 *
 * 公式引擎：calcSameControlCost(netAssets, ratio) → 享有份额 = 初始投资成本
 * 差额 = 支付对价 - 初始成本 → 调整资本公积→留存收益
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Requirements: 3.1, 3.3, 3.5
 */
import { ref, reactive, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { calcSameControlCost, parseNum } from '../../composables/useG7SubFormulaEngine'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import type { G7SameControlRow } from '../../composables/useG7SubFormData'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ═══ Props ═══

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', data: SameControlSavePayload): void
}>()

// ═══ Types ═══

interface SameControlSavePayload {
  rows: G7SameControlRow[]
  conclusion: string
}

// ═══ Injections ═══

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ Import/Export ═══

const wpIdRef = toRef(props, 'wpId')
const { exportTemplate, exportData, importData } = useG7SubImportExport({ wpId: wpIdRef })

// ═══ State ═══

const isReadonly = computed(() => !!props.readonly)
const rows = reactive<G7SameControlRow[]>([])
const conclusion = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const rowCount = computed(() => rows.length)

// ═══ 审计说明/结论持久化（checklist_responses，conclusion:null） ═══
const auditFormData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const NOTE_KEY = 'G7-8-same-control-audit-note'
const CONCLUSION_KEY = 'G7-8-same-control-audit-conclusion'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}
function saveAuditConclusion(val: string): void {
  if (isReadonly.value) return
  conclusion.value = val
  auditFormData.debouncedSave(CONCLUSION_KEY, { remark: val, conclusion: null })
  emitSave()
}

// ═══ 公式自动计算 ═══

/**
 * 重新计算单行公式列：
 * - shareOfNetAssets = calcSameControlCost(acquireeNetAssets, shareholdingRatio)
 * - initialCost = shareOfNetAssets（同控下初始成本=享有份额）
 */
function recalcRow(row: G7SameControlRow): void {
  row.shareOfNetAssets = calcSameControlCost(row.acquireeNetAssets, row.shareholdingRatio)
  row.initialCost = row.shareOfNetAssets
}

/** 差额 = 支付对价 - 初始投资成本 */
function getDifference(row: G7SameControlRow): number {
  return Math.round((parseNum(row.consideration) - parseNum(row.initialCost)) * 100) / 100
}

/** 差额是否过大(>初始成本50%且初始成本>0) → 橙色高亮告警 */
function isDifferenceLarge(row: G7SameControlRow): boolean {
  const cost = parseNum(row.initialCost)
  if (cost <= 0) return false
  return Math.abs(getDifference(row)) > cost * 0.5
}

// ═══ 字段更新 + 触发重算 ═══

function updateField(row: G7SameControlRow, field: keyof G7SameControlRow, value: any): void {
  ;(row as any)[field] = value ?? 0
  recalcRow(row)
  emitSave()
}

// ═══ 动态行增删 ═══

function createEmptyRow(investeeName: string, seq: number): G7SameControlRow {
  return {
    id: `sc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    mergerDate: '',
    mergerType: '',
    acquireeNetAssets: 0,
    shareholdingRatio: 0,
    shareOfNetAssets: 0,
    initialCost: 0,
    consideration: 0,
    differenceHandling: '',
    auditConclusion: '',
  }
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增被投资单位（同控合并）',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      },
    )
    const name = value.trim()
    // 校验唯一性
    if (rows.some(r => r.investeeName === name)) {
      ElMessage.warning(`「${name}」已存在，请勿重复添加`)
      return
    }
    const newRow = createEmptyRow(name, rows.length + 1)
    rows.push(newRow)
    emitSave()
    ElMessage.success(`已添加「${name}」`)
  } catch {
    // 用户取消
  }
}

function deleteRow(row: G7SameControlRow): void {
  const idx = rows.findIndex(r => r.id === row.id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
    emitSave()
  }
}

// ═══ 导入导出 ═══

function handleImportExportCommand(command: string): void {
  switch (command) {
    case 'template':
      void exportTemplate('G7-8')
      break
    case 'export':
      void exportData('G7-8')
      break
    case 'import':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const result = await importData('G7-8', file)
  if (result && result.rowCount > 0) {
    // 导入成功后重新加载数据（触发父组件刷新）
    ElMessage.info('数据已导入，请刷新查看')
  }
  // 重置 input
  target.value = ''
}

// ═══ AI辅助 ═══

async function handleAiConclusion(): Promise<void> {
  ElMessage.info('正在生成AI审计结论...')
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/initial-measurement-conclusion`,
      { existingContent: conclusion.value, relatedContext: { sheet: 'G7-8', rows } },
    )
    const text = res?.data?.data?.conclusion || res?.data?.conclusion || res?.data?.text || ''
    if (text) {
      conclusion.value = String(text)
      auditFormData.debouncedSave(CONCLUSION_KEY, { remark: String(text), conclusion: null })
      emitSave()
      ElMessage.success('AI结论生成完成')
    }
  } catch {
    ElMessage.warning('AI结论生成暂未连接，请手动填写')
  }
}

// ═══ 保存 ═══

function emitSave(): void {
  emit('save', {
    rows: [...rows],
    conclusion: conclusion.value,
  })
}

// ═══ 辅助格式化 ═══

function fmtPercent(v: unknown): string {
  if (typeof v === 'number' && v > 0) return `${(v * 100).toFixed(2)}%`
  return String(v ?? '-')
}

function conclusionTagType(c: string): '' | 'success' | 'warning' | 'danger' {
  switch (c) {
    case '无差异': return 'success'
    case '差异可接受': return 'warning'
    case '差异需调整': return 'danger'
    default: return ''
  }
}

// ═══ 数据水合 ═══

function hydrateData(): void {
  const data = props.htmlData
  if (!data) return

  const sameControlData = data?.sameControl ?? data?.same_control ?? data?.sameControlMeasurement ?? data
  conclusion.value = sameControlData?.conclusion ?? ''

  const rawRows = sameControlData?.rows ?? []
  rows.length = 0
  if (Array.isArray(rawRows)) {
    for (let i = 0; i < rawRows.length; i++) {
      const r = rawRows[i]
      const row: G7SameControlRow = {
        id: r.id ?? `sc-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 8)}`,
        seq: r.seq ?? i + 1,
        investeeName: r.investeeName ?? r.investee_name ?? '未命名',
        mergerDate: r.mergerDate ?? r.merger_date ?? '',
        mergerType: r.mergerType ?? r.merger_type ?? '',
        acquireeNetAssets: parseNum(r.acquireeNetAssets ?? r.acquiree_net_assets),
        shareholdingRatio: parseNum(r.shareholdingRatio ?? r.shareholding_ratio),
        shareOfNetAssets: 0,
        initialCost: 0,
        consideration: parseNum(r.consideration),
        differenceHandling: r.differenceHandling ?? r.difference_handling ?? '',
        auditConclusion: r.auditConclusion ?? r.audit_conclusion ?? '',
      }
      recalcRow(row)
      rows.push(row)
    }
  }
}

// ═══ 对外暴露 ═══

function getData(): SameControlSavePayload {
  return {
    rows: [...rows],
    conclusion: conclusion.value,
  }
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  rows.length = 0
  conclusion.value = ''
  if (data) {
    const prev = props.htmlData
    // 临时覆盖用于水合
    ;(props as any).htmlData = data
    hydrateData()
    ;(props as any).htmlData = prev
  }
}

defineExpose({ getData, loadFromHtmlData })

// ═══ Lifecycle ═══

onMounted(async () => {
  if (props.htmlData) {
    hydrateData()
  }
  await auditFormData.load()
  const n = auditFormData.data.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})
</script>

<style scoped>
.g7-tab-same-control {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ═══ Section标题栏 ═══ */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ═══ 蓝色渐变引导区 ═══ */
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #e8f4fd 0%, #dbeafe 100%);
  border-radius: 8px;
  border: 1px solid #bae6fd;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #1e40af;
}

/* ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ */
.methodology-context {
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 0 6px 6px 0;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #92400e;
}
.methodology-context p {
  margin: 2px 0;
}

/* ═══ 表格 ═══ */
.same-control-table {
  margin-bottom: 16px;
}
.same-control-table :deep(.el-table__header th) {
  background: #f8fafc;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.investee-name {
  font-weight: 500;
  color: #1d4ed8;
}

/* ═══ 公式列样式（虚线下划线+cursor:help） ═══ */
.formula-cell {
  border-bottom: 1px dashed #94a3b8;
  cursor: help;
  color: #1e40af;
  font-weight: 500;
  padding-bottom: 1px;
}
.formula-header {
  cursor: help;
}
.formula-icon {
  font-size: 11px;
  color: #6366f1;
  margin-left: 2px;
  font-style: italic;
}

/* ═══ 差额处理列 ═══ */
.difference-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
.diff-tag {
  font-size: 11px;
}
.diff-warning {
  color: #f59e0b;
  font-size: 14px;
  cursor: help;
}

/* ═══ 空状态 ═══ */
.empty-state {
  text-align: center;
  padding: 40px 0;
  color: #9ca3af;
}

/* ═══ 审计目标 / 工具栏 ═══ */
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; }

/* ═══ 审计说明/结论卡片 ═══ */
.audit-note-card {
  margin-top: 16px;
}
.conclusion-card {
  margin-top: 16px;
}
.conclusion-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.conclusion-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* ═══ 编制提示折叠 ═══ */
.guidance-details {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #6b7280;
  font-weight: 500;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.8;
  color: #4b5563;
}
.guidance-content p {
  margin: 2px 0;
}

/* ═══ 文本单元格 ═══ */
.text-cell {
  white-space: pre-wrap;
  font-size: 12px;
  color: #6b7280;
}
</style>
