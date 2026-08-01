<template>
  <div class="n2-tab-detail">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
    >
      <ul class="ao-list">
        <li><strong>完整性</strong>：应交税费按税种逐项列示，未审→审定的期初/应交/已交/期末勾稽完整。</li>
        <li><strong>准确性</strong>：审定期末 = 审定期初 + 审定应交 − 审定已交，各税种测算与本表一致。</li>
        <li><strong>计价</strong>：期初调整、账项调整、重分类调整正确反映至审定列。</li>
      </ul>
    </el-alert>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税费明细表 N2-2</span>
        <el-tag type="danger" size="small" class="liability-tag">负债类·贷方</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleSeedFromN21">从 N2-1 带入</el-button>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="noteAiLoading" :disabled="isReadonly" @click="handleNoteAi">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>明细表规则（源模板 16 列）：</strong>
        未审期末 F = 期初 C + 应交 D − 已交 E；审定期初 M = C + 期初调整 G；
        审定应交 N = D + 账项调整应交 I + 重分类应交 K；审定已交 O = E + 账项调整已交 J + 重分类已交 L；
        审定期末 P = M + N − O。灰底列为公式自动计算。
      </div>
    </div>

    <!-- ═══ 统计摘要区 ═══ -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-label">税种数</span>
        <span class="summary-value">{{ summary.taxTypeCount }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">计提合计（审定应交）</span>
        <span class="summary-value">{{ fmtAmount(summary.accrualTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">缴纳合计（审定已交）</span>
        <span class="summary-value">{{ fmtAmount(summary.paymentTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">期末合计（审定期末）</span>
        <span class="summary-value">{{ fmtAmount(summary.endBalanceTotal) }}</span>
      </div>
    </div>

    <!-- ═══ 16列明细表（嵌套分组表头） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      show-summary
      :summary-method="getSummaries"
      style="width: 100%"
      empty-text="暂无明细行"
    >
      <el-table-column prop="taxType" label="项目" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.taxType"
            size="small"
            placeholder="项目"
            @input="(val: string) => handleUpdate(row.id, 'taxType', val)"
          />
          <span v-else>{{ row.taxType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="税率(%)" width="96" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.taxRate"
            :controls="false"
            :precision="4"
            :min="0"
            :max="1"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => handleUpdate(row.id, 'taxRate', val ?? 0)"
          />
          <span v-else>{{ (row.taxRate * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>

      <!-- 未审 分组 -->
      <el-table-column label="未审" align="center">
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjBegin"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'unadjBegin', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.unadjBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjPayable"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'unadjPayable', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.unadjPayable) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjPaid"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'unadjPaid', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.unadjPaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="未审期末 F = 期初 C + 应交 D − 已交 E">期末</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.unadjEnd) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 期初调整 G（单列） -->
      <el-table-column label="期初调整" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.beginAdjust"
            :controls="false"
            :precision="2"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => handleUpdate(row.id, 'beginAdjust', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.beginAdjust) }}</span>
        </template>
      </el-table-column>

      <!-- 账项调整 分组 -->
      <el-table-column label="账项调整" align="center">
        <el-table-column label="应交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ajePayable"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'ajePayable', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ajePayable) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ajePaid"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'ajePaid', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ajePaid) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 重分类 分组 -->
      <el-table-column label="重分类" align="center">
        <el-table-column label="应交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.rjePayable"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'rjePayable', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.rjePayable) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已交" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.rjePaid"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate(row.id, 'rjePaid', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.rjePaid) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 审定 分组 -->
      <el-table-column label="审定" align="center">
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="审定期初 M = 未审期初 C + 期初调整 G">期初</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.audBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="审定应交 N = 未审应交 D + 账项调整应交 I + 重分类应交 K">应交</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.audPayable) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="审定已交 O = 未审已交 E + 账项调整已交 J + 重分类已交 L">已交</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.audPaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="审定期末 P = 期初 M + 应交 N − 已交 O">期末</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell strong-cell">{{ fmtAmount(row.audEnd) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @input="(val: string) => handleUpdate(row.id, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增行 ═══ -->
    <div v-if="!isReadonly" class="add-row-bar">
      <el-button size="small" @click="handleAddRow">+ 新增税种明细行</el-button>
      <el-button v-if="rows.length === 0" size="small" @click="handleSeedDefaults">预置源模板常见税种（13项）</el-button>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
        </div>
      </template>
      <div class="notes-field">
        <div class="field-label-row">
          <label class="field-label">审计说明</label>
          <el-button size="small" text type="primary" :loading="noteAiLoading" :disabled="isReadonly" @click="handleNoteAi">
            <el-icon><MagicStick /></el-icon> AI辅助说明
          </el-button>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="saveNote"
        />
      </div>
      <div class="notes-field">
        <div class="field-label-row">
          <label class="field-label">审计结论</label>
          <el-button size="small" text type="primary" :loading="conclusionAiLoading" :disabled="isReadonly" @click="handleConclusionAi">
            <el-icon><MagicStick /></el-icon> AI辅助结论
          </el-button>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="saveConclusion"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本表按源模板 16 列结构：项目 / 税率 / 未审(期初·应交·已交·期末) / 期初调整 / 账项调整(应交·已交) / 重分类(应交·已交) / 审定(期初·应交·已交·期末) / 备注。</li>
        <li>灰底虚线列为公式自动计算：F=C+D−E、M=C+G、N=D+I+K、O=E+J+L、P=M+N−O。</li>
        <li>13 个固定税种（增值税/消费税/城建税/教育费附加/房产税/印花税/所得税等）可新增/删除。</li>
        <li>"从 N2-1 带入"：无数据时按 13 固定税种从审定表带入未审期初。</li>
        <li>支持导入导出（模板/数据/xlsx）。</li>
      </ul>
    </details>

    <!-- ═══ 隐藏文件上传 ═══ -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabDetail — N2-2 应交税费明细表（16 列源模板对齐版）
 *
 * 源结构：项目 / 税率 / 未审(期初C/应交D/已交E/期末F=C+D-E) / 期初调整G /
 *   账项调整(应交I/已交J) / 重分类(应交K/已交L) /
 *   审定(期初M=C+G/应交N=D+I+K/已交O=E+J+L/期末P=M+N-O) / 备注
 *
 * - 嵌套分组表头；公式列灰底自动
 * - 13 固定税种 + 可新增/删（ElMessageBox.prompt 输入名称）
 * - 统计摘要（税种数/计提合计/缴纳合计/期末合计）
 * - seedFromN21(): 无数据时从 N2-1 审定表带入未审期初
 * - item_id: N2-2-detail-rows + N2-2-note + N2-2-conclusion
 *
 * 科目：2221 应交税费（贷方/负债类！）
 */
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ArrowDown } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2Detail16 } from '../../composables/useN2Detail'
import { useN2ImportExport } from '../../composables/useN2ImportExport'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  year?: string
}>()

// ─── FormData ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useN2FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── useN2Detail16 ───────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  summary,
  total,
  addRow,
  seedDefaultRows,
  removeRow,
  updateRow,
  seedFromN21,
} = useN2Detail16({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
})

// ─── useN2ImportExport ───────────────────────────────────────────────────────

const {
  exportTemplate,
  exportData,
  importData,
} = useN2ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── State ───────────────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)
const isReadonly = computed(() => props.isReadonly ?? false)
const noteAiLoading = ref(false)
const conclusionAiLoading = ref(false)

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────

function _readResponseText(itemId: string): string {
  const r = props.allResponses?.get?.(itemId) as any
  const v = r?.conclusion ?? r?.remark
  return typeof v === 'string' ? v : ''
}

const auditNote = ref<string>(_readResponseText('N2-2-note'))
const auditConclusion = ref<string>(_readResponseText('N2-2-conclusion'))

watch(
  () => props.allResponses,
  () => {
    if (!auditNote.value) auditNote.value = _readResponseText('N2-2-note')
    if (!auditConclusion.value) auditConclusion.value = _readResponseText('N2-2-conclusion')
  },
  { deep: true },
)

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 更新行字段 ──────────────────────────────────────────────────────────────

async function handleUpdate(rowId: string, field: any, value: any) {
  await updateRow(rowId, field, value)
}

// ─── 新增行 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value: taxType } = await ElMessageBox.prompt(
      '请输入税种名称（如：增值税、城建税、房产税）',
      '新增税种明细行',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '税种名称不能为空',
        inputPlaceholder: '税种名称',
      },
    )
    await addRow(taxType)
    ElMessage.success(`已新增税种：${taxType}`)
  } catch {
    // 用户取消
  }
}

// ─── 预置源模板常见税种 ──────────────────────────────────────────────────────

async function handleSeedDefaults() {
  try {
    await ElMessageBox.confirm(
      '将预置致同源模板 N2-2 的 13 类标准税种（金额为0，可按被审计单位税收情况增减）。仅在当前明细为空时生效。',
      '预置常见税种',
      { type: 'info', confirmButtonText: '预置', cancelButtonText: '取消' },
    )
    // 合计/摘要均为 computed 派生（派生列不持久化），无需额外同步保存
    await seedDefaultRows()
    ElMessage.success('已预置源模板常见税种')
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

async function handleRemoveRow(rowId: string) {
  try {
    await ElMessageBox.confirm('确认删除该明细行？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await removeRow(rowId)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// ─── 从 N2-1 带入 ────────────────────────────────────────────────────────────

async function handleSeedFromN21() {
  try {
    await ElMessageBox.confirm(
      '将按 13 个固定税种从 N2-1 审定表带入未审期初，覆盖当前明细行。是否继续？',
      '从 N2-1 带入',
      { type: 'warning', confirmButtonText: '带入', cancelButtonText: '取消' },
    )
    await seedFromN21()
    ElMessage.success('已从 N2-1 带入未审期初')
  } catch {
    // 用户取消
  }
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = total.value
  // leaf 列顺序: 项目(0) 税率(1) C(2) D(3) E(4) F(5) G(6) I(7) J(8) K(9) L(10) M(11) N(12) O(13) P(14) 备注(15) 操作(16)
  const map: Record<number, string> = {
    2: fmtAmount(t.unadjBegin),
    3: fmtAmount(t.unadjPayable),
    4: fmtAmount(t.unadjPaid),
    5: fmtAmount(t.unadjEnd),
    6: fmtAmount(t.beginAdjust),
    7: fmtAmount(t.ajePayable),
    8: fmtAmount(t.ajePaid),
    9: fmtAmount(t.rjePayable),
    10: fmtAmount(t.rjePaid),
    11: fmtAmount(t.audBegin),
    12: fmtAmount(t.audPayable),
    13: fmtAmount(t.audPaid),
    14: fmtAmount(t.audEnd),
  }
  columns.forEach((_col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    sums[idx] = map[idx] ?? ''
  })
  return sums
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate': exportTemplate('N2-2'); break
    case 'exportData': exportData('N2-2'); break
    case 'importData': fileInputRef.value?.click(); break
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importData(file, 'N2-2')
  input.value = ''
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

async function saveNote() {
  await formData.setField('2', 'note', auditNote.value)
}

async function saveConclusion() {
  await formData.setField('2', 'conclusion', auditConclusion.value)
}

// ─── AI 真回填（context 值全部转 String） ────────────────────────────────────

function _buildAiContext(): Record<string, string> {
  const s = summary.value
  return {
    科目: '2221 应交税费（负债类）',
    税种数: String(s.taxTypeCount),
    审定应交合计: String(s.accrualTotal.toFixed(2)),
    审定已交合计: String(s.paymentTotal.toFixed(2)),
    审定期末合计: String(s.endBalanceTotal.toFixed(2)),
  }
}

async function _aiGenerate(section: string, prompt: string, existing: string): Promise<string> {
  const h = (await import('@/utils/http')).default
  const res: any = await h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    section,
    prompt,
    existingContent: existing || '',
    context: _buildAiContext(),
  })
  return res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
}

async function handleNoteAi() {
  noteAiLoading.value = true
  try {
    const text = await _aiGenerate(
      'n2-detail-note',
      '请基于应交税费明细表各税种未审→审定的计提/缴纳/期末数据，撰写审计说明。',
      auditNote.value,
    )
    if (text) {
      auditNote.value = text
      await saveNote()
      ElMessage.success('AI 已生成审计说明')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败')
  } finally {
    noteAiLoading.value = false
  }
}

async function handleConclusionAi() {
  conclusionAiLoading.value = true
  try {
    const text = await _aiGenerate(
      'n2-detail-conclusion',
      '请基于应交税费明细表数据，给出审计结论。',
      auditConclusion.value,
    )
    if (text) {
      auditConclusion.value = text
      await saveConclusion()
      ElMessage.success('AI 已生成审计结论')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败')
  } finally {
    conclusionAiLoading.value = false
  }
}
</script>

<style scoped>
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 0; }

.n2-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.liability-tag { font-size: 11px; }

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong { color: #b88230; }

/* ─── 统计摘要区 ─── */
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.summary-label { font-size: 12px; color: #909399; }
.summary-value { font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 公式列样式 ─── */
.formula-header {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

.strong-cell { font-weight: 700; }

/* ─── 表格统一 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 新增行按钮 ─── */
.add-row-bar { text-align: center; margin: 12px 0; }

/* ─── 审计说明卡片 ─── */
.audit-notes-card { margin: 16px 0; }

.notes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.field-label {
  display: block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
}

/* ─── 编制提示折叠 ─── */
.n2-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
