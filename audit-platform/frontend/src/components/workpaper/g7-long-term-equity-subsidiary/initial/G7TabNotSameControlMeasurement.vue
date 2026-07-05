<template>
  <div class="g7-tab-not-same-control">
    <!-- 方法论上下文: CAS20非同控合并规则 -->
    <div class="methodology-context">
      <div class="methodology-content">
        <strong>CAS20 非同一控制下企业合并：</strong>
        <ul>
          <li>购买方按<b>公允价值</b>计量合并对价</li>
          <li>初始投资成本 = 支付对价 + 直接相关费用（审计、法律等）</li>
          <li>商誉 = 初始投资成本 − 享有被购买方可辨认净资产公允价值份额</li>
          <li>成本 &gt; 份额 → <b>商誉</b>（资产）；成本 &lt; 份额 → <b>营业外收入</b>（廉价购买利得）</li>
        </ul>
      </div>
    </div>

    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-no">①</span> 录入购买日、合并方式及对价</div>
        <div class="guide-step"><span class="step-no">②</span> 填写直接费用，系统自动计算初始成本</div>
        <div class="guide-step"><span class="step-no">③</span> 录入被购买方净资产FV，自动计算商誉</div>
        <div class="guide-step"><span class="step-no">④</span> AI辅助生成审计结论</div>
      </div>
    </div>

    <!-- 工具栏: 新增行 + 导入导出 + AI + 复核 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-9 子公司初始计量测试（非同一控制下企业合并）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增被投资单位
        </el-button>
        <el-dropdown :disabled="isReadonly" trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI">🤖 AI</el-button>
        <el-button size="small" @click="openReviewDialog('G7-9-not-same-control')">💬 复核</el-button>
      </div>
    </div>

    <!-- 53行×9列数据表格 -->
    <el-table :data="rows" border size="small" max-height="600" style="font-size: 13px">
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <el-table-column label="被投资单位" min-width="140" fixed>
        <template #default="{ row }">
          <el-input v-model="row.investeeName" size="small" :disabled="isReadonly"
            @change="handleCellChange(row)" />
        </template>
      </el-table-column>

      <el-table-column label="购买日" min-width="130">
        <template #default="{ row }">
          <el-date-picker v-model="row.acquisitionDate" type="date" size="small"
            value-format="YYYY-MM-DD" :disabled="isReadonly" style="width: 100%"
            @change="handleCellChange(row)" />
        </template>
      </el-table-column>

      <el-table-column label="合并方式" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.mergerType" size="small" :disabled="isReadonly"
            placeholder="请选择" @change="handleCellChange(row)">
            <el-option value="吸收合并" label="吸收合并" />
            <el-option value="控股合并" label="控股合并" />
            <el-option value="新设合并" label="新设合并" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="支付对价" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.consideration" size="small" :controls="false"
            :disabled="isReadonly" style="width: 100%" :precision="2"
            @change="recalcRow(row)" />
        </template>
      </el-table-column>

      <el-table-column label="直接费用" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.directFees" size="small" :controls="false"
            :disabled="isReadonly" style="width: 100%" :precision="2"
            @change="recalcRow(row)" />
        </template>
      </el-table-column>

      <el-table-column label="初始投资成本" min-width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="初始投资成本 = 支付对价 + 直接费用 (calcNotSameControlCost)">
            {{ fmtNum(row.initialCost) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="被购买方净资产FV" min-width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.acquireeNetAssetsFV" size="small" :controls="false"
            :disabled="isReadonly" style="width: 100%" :precision="2"
            @change="recalcRow(row)" />
        </template>
      </el-table-column>

      <el-table-column label="持股比例" min-width="100" align="right">
        <template #header>
          <span title="小数形式，如60%填0.6">持股比例</span>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.shareholdingRatio" size="small" :controls="false"
            :disabled="isReadonly" style="width: 100%" :precision="4" :min="0" :max="1"
            @change="recalcRow(row)" />
        </template>
      </el-table-column>

      <el-table-column label="享有份额" min-width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="享有份额 = 被购买方净资产FV × 持股比例">
            {{ fmtNum(row.shareOfFV) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="商誉" min-width="140" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="商誉 = 初始投资成本 - 享有份额 (calcGoodwill)">
            <el-tag v-if="row.goodwill > 0" type="success" size="small" effect="plain">
              商誉 {{ fmtNum(row.goodwill) }}
            </el-tag>
            <el-tag v-else-if="row.goodwill < 0" type="primary" size="small" effect="plain">
              廉价购买利得 {{ fmtNum(Math.abs(row.goodwill)) }}
            </el-tag>
            <span v-else>—</span>
          </span>
        </template>
      </el-table-column>

      <el-table-column label="审计结论" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.auditConclusion" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
            size="small" :disabled="isReadonly" @change="handleCellChange(row)" />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="handleRemoveRow(row)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计区域 -->
    <div class="totals">
      <span class="subtotal-label">合计：</span>
      支付对价 {{ fmtNum(totals.consideration) }} ·
      直接费用 {{ fmtNum(totals.directFees) }} ·
      初始投资成本 {{ fmtNum(totals.initialCost) }} ·
      商誉 {{ fmtNum(totals.goodwill) }}
    </div>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
        <el-button size="small" style="float: right" @click="handleAI">🤖 AI辅助</el-button>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" placeholder="请填写非同控合并初始计量审计结论..."
        @change="handleConclusionChange" />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>初始投资成本 = 支付对价 + 直接相关费用（审计费、律师费、资产评估费等）</li>
        <li>享有份额 = 被购买方可辨认净资产公允价值 × 持股比例</li>
        <li>商誉 = 初始投资成本 − 享有份额：正值确认为商誉（资产），负值确认为营业外收入</li>
        <li>需关注：被购买方净资产FV是否经评估、对价支付方式（现金/股权/混合）</li>
        <li>直接费用不含发行权益性证券/债务性证券的发行费用（冲减资本公积/溢折价）</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传 input -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display: none"
      @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabNotSameControlMeasurement — G7-9 非同一控制下企业合并初始计量测试
 *
 * 53行×9列: 被投资单位|购买日|合并方式|支付对价|直接费用|初始投资成本(公式)|被购买方净资产FV|享有份额(公式)|商誉(公式)
 *
 * 核心公式:
 *   初始投资成本 = calcNotSameControlCost(consideration, directFees)
 *   享有份额 = acquireeNetAssetsFV × shareholdingRatio
 *   商誉 = calcGoodwill(initialCost, shareOfFV)
 *
 * 商誉正值=商誉(绿色tag)，负值="廉价购买利得"(蓝色tag)
 * 动态行增删(ElMessageBox.prompt命名) + 导入导出(sheet='G7-9')
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Requirements: 3.2, 3.4, 3.5
 */
import { ref, computed, watch, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { calcNotSameControlCost, calcGoodwill, parseNum } from '../../composables/useG7SubFormulaEngine'
import { useG7SubImportExport, type G7SubImportableSheet } from '../../composables/useG7SubImportExport'
import type { G7NotSameControlRow } from '../../composables/useG7SubFormData'

// ─── Props ───────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => !!props.readonly)

// ─── 导入导出 composable ─────────────────────────────────────────────────────
const wpIdRef = toRef(props, 'wpId')
const importExport = useG7SubImportExport({ wpId: computed(() => wpIdRef.value) })
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 数据模型 ────────────────────────────────────────────────────────────────
const rows = ref<G7NotSameControlRow[]>([])
const conclusion = ref('')

/** 从htmlData初始化数据 */
function initFromHtmlData(): void {
  if (!props.htmlData) return
  const content = props.htmlData?.notSameControl ?? props.htmlData?.content?.notSameControl ?? props.htmlData
  if (content?.rows && Array.isArray(content.rows)) {
    rows.value = content.rows.map((r: any, idx: number) => normalizeRow(r, idx))
  }
  if (content?.conclusion) {
    conclusion.value = content.conclusion
  }
}

function normalizeRow(r: any, idx: number): G7NotSameControlRow {
  const consideration = parseNum(r.consideration)
  const directFees = parseNum(r.directFees)
  const acquireeNetAssetsFV = parseNum(r.acquireeNetAssetsFV)
  const shareholdingRatio = parseNum(r.shareholdingRatio)
  const initialCost = calcNotSameControlCost(consideration, directFees)
  const shareOfFV = Math.round(acquireeNetAssetsFV * shareholdingRatio * 100) / 100
  const goodwill = calcGoodwill(initialCost, shareOfFV)

  return {
    id: r.id || `nsc-${Date.now()}-${idx}`,
    seq: idx + 1,
    investeeName: r.investeeName || '',
    acquisitionDate: r.acquisitionDate || '',
    mergerType: r.mergerType || '',
    consideration,
    directFees,
    initialCost,
    acquireeNetAssetsFV,
    shareholdingRatio,
    shareOfFV,
    goodwill,
    auditConclusion: r.auditConclusion || '',
  }
}

function createEmptyRow(name: string): G7NotSameControlRow {
  return {
    id: `nsc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq: rows.value.length + 1,
    investeeName: name,
    acquisitionDate: '',
    mergerType: '',
    consideration: 0,
    directFees: 0,
    initialCost: 0,
    acquireeNetAssetsFV: 0,
    shareholdingRatio: 0,
    shareOfFV: 0,
    goodwill: 0,
    auditConclusion: '',
  }
}

// ─── 公式重计算 ──────────────────────────────────────────────────────────────
function recalcRow(row: G7NotSameControlRow): void {
  row.initialCost = calcNotSameControlCost(row.consideration, row.directFees)
  row.shareOfFV = Math.round(parseNum(row.acquireeNetAssetsFV) * parseNum(row.shareholdingRatio) * 100) / 100
  row.goodwill = calcGoodwill(row.initialCost, row.shareOfFV)
  handleCellChange(row)
}

// ─── 合计 ────────────────────────────────────────────────────────────────────
const totals = computed(() => {
  let consideration = 0
  let directFees = 0
  let initialCost = 0
  let goodwill = 0
  for (const r of rows.value) {
    consideration += parseNum(r.consideration)
    directFees += parseNum(r.directFees)
    initialCost += parseNum(r.initialCost)
    goodwill += parseNum(r.goodwill)
  }
  return {
    consideration: Math.round(consideration * 100) / 100,
    directFees: Math.round(directFees * 100) / 100,
    initialCost: Math.round(initialCost * 100) / 100,
    goodwill: Math.round(goodwill * 100) / 100,
  }
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '名称不能为空'
        if (rows.value.some((r) => r.investeeName === val.trim())) return '该被投资单位已存在'
        return true
      },
    })
    if (value?.trim()) {
      rows.value.push(createEmptyRow(value.trim()))
      reindex()
      emitSave()
    }
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(row: G7NotSameControlRow): void {
  const idx = rows.value.findIndex((r) => r.id === row.id)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    reindex()
    emitSave()
  }
}

function reindex(): void {
  rows.value.forEach((r, i) => { r.seq = i + 1 })
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
function handleImportExportCmd(cmd: string): void {
  const sheet: G7SubImportableSheet = 'G7-9'
  switch (cmd) {
    case 'export-template':
      importExport.exportTemplate(sheet)
      break
    case 'export-data':
      importExport.exportData(sheet)
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // 重置以支持重复选择

  const result = await importExport.importData('G7-9', file)
  if (result && result.rowCount > 0) {
    // 导入成功后重新加载数据（此处简化：实际应从后端获取最新数据）
    ElMessage.success(`已导入 ${result.rowCount} 行数据`)
  }
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────
async function handleAI(): Promise<void> {
  try {
    const res = await import('@/utils/http').then((m) => m.default.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/initial-measurement-conclusion`,
      { sheet: 'G7-9', rows: rows.value },
    ))
    const generated = res?.data?.data?.conclusion ?? res?.data?.conclusion ?? ''
    if (generated) {
      conclusion.value = generated
      emitSave()
      ElMessage.success('AI结论已生成')
    }
  } catch {
    ElMessage.warning('AI生成失败，请手动填写')
  }
}

// ─── 保存事件 ────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'save', data: { rows: G7NotSameControlRow[]; conclusion: string }): void
}>()

function handleCellChange(_row: G7NotSameControlRow): void {
  emitSave()
}

function handleConclusionChange(): void {
  emitSave()
}

function emitSave(): void {
  emit('save', { rows: rows.value, conclusion: conclusion.value })
}

// ─── 格式化工具 ──────────────────────────────────────────────────────────────
function fmtNum(v: number | null | undefined): string {
  const n = parseNum(v)
  if (n === 0) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 初始化 ──────────────────────────────────────────────────────────────────
watch(() => props.htmlData, () => {
  initFromHtmlData()
}, { immediate: true })
</script>

<style scoped>
.g7-tab-not-same-control {
  padding: 12px;
  font-size: 13px;
}

/* 方法论上下文: 琥珀色左边线+浅黄背景 */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 4px;
}
.methodology-content {
  font-size: 13px;
  line-height: 1.6;
  color: #92400e;
}
.methodology-content ul {
  margin: 4px 0 0 16px;
  padding: 0;
}
.methodology-content li {
  margin-bottom: 2px;
}

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.guide-step {
  font-size: 13px;
  color: #1e40af;
}
.step-no {
  font-weight: 700;
  margin-right: 4px;
}

/* section标题 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 公式列样式 */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 合计区域 */
.totals {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  color: #303133;
}
.subtotal-label {
  font-weight: 600;
  margin-right: 8px;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 12px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #606266;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.prep-hint ul {
  margin: 4px 0 0 16px;
  line-height: 1.8;
}
</style>
