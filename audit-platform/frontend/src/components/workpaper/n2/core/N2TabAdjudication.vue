<template>
  <div class="n2-adjudication">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
    >
      <ul class="ao-list">
        <li><strong>完整性（负债类重点）</strong>：应交税费（2221）各税种期末余额均已完整入账，无漏计提。</li>
        <li><strong>准确性</strong>：适用税率与计税依据正确，各税种测算（增值税/城建税及附加/房产税/土增税等）与明细表勾稽一致。</li>
        <li><strong>计价</strong>：期初/期末未审数经账项调整、重分类调整后得出审定数，变动合理并已回写试算表。</li>
      </ul>
    </el-alert>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税费审定表 N2-1</span>
        <el-tag type="danger" size="small" class="liability-tag">负债类·贷方</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" :loading="writebackLoading" type="primary" @click="handleWritebackTB">
          回写审定数
        </el-button>
      </div>
    </div>

    <!-- ═══ 负债类公式提示 ═══ -->
    <div class="liability-formula-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>负债类贷方科目：期初/期末审定 = 未审 + 账项调整 + 重分类；变动率 = 变动额 ÷ 期初（&gt;30% 黄字、&gt;50% 红字预警）</span>
    </div>

    <!-- ═══ 14列主数据表格（嵌套分组表头） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      show-summary
      :summary-method="getSummaries"
      class="adjudication-table"
    >
      <!-- 项目 -->
      <el-table-column prop="taxType" label="项目" min-width="120" fixed>
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.taxType"
            size="small"
            placeholder="项目"
            @input="(val: string) => handleUpdate($index, 'taxType', val)"
          />
          <span v-else class="tax-type-cell">{{ row.taxType }}</span>
        </template>
      </el-table-column>

      <!-- 期初数 分组 -->
      <el-table-column label="期初数" align="center">
        <el-table-column label="未审" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginUnadj"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'beginUnadj', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.beginUnadj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginAje"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'beginAje', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginRje"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'beginRje', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="期初审定 = 未审 + 账项调整 + 重分类">期初审定</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期初审定 = 未审 + 账项调整 + 重分类" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.beginAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 期末数 分组 -->
      <el-table-column label="期末数" align="center">
        <el-table-column label="未审" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endUnadj"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'endUnadj', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.endUnadj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endAje"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'endAje', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endRje"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(val: number | undefined) => handleUpdate($index, 'endRje', val ?? 0)"
            />
            <span v-else class="cell-value">{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="期末审定 = 未审 + 账项调整 + 重分类">期末审定</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末审定 = 未审 + 账项调整 + 重分类" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.endAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 变动 分组 -->
      <el-table-column label="变动" align="center">
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="未审变动额 = 期末未审 − 期初未审">未审变动额</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.unadjChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="未审变动率 = 未审变动额 ÷ 期初未审">未审变动率</span>
          </template>
          <template #default="{ row }">
            <span :class="['formula-cell', rateClass(row.unadjRate)]">{{ fmtRate(row.unadjRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="审定变动额 = 期末审定 − 期初审定">审定变动额</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.auditedChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="审定变动率 = 审定变动额 ÷ 期初审定">审定变动率</span>
          </template>
          <template #default="{ row }">
            <span :class="['formula-cell', rateClass(row.auditedRate)]">{{ fmtRate(row.auditedRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 原因分析 -->
      <el-table-column prop="reason" label="原因分析" min-width="170">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            size="small"
            placeholder="变动原因说明"
            @input="(val: string) => handleUpdate($index, 'reason', val)"
          />
          <span v-else class="cell-value">{{ row.reason || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增/删除项目行 ═══ -->
    <div v-if="!isReadonly" class="row-ops-bar">
      <el-button size="small" @click="handleAddRow">+ 新增项目行</el-button>
      <el-button size="small" @click="handleRemoveLast" :disabled="rows.length === 0">删除末行</el-button>
    </div>

    <!-- ═══ 试算平衡勾稽行（TB 2221期末 vs 审定合计） ═══ -->
    <div class="tb-recon-bar" :class="tbRecon.status">
      <div class="tb-recon-title">试算平衡勾稽</div>
      <div class="tb-recon-cells">
        <div class="tb-recon-cell">
          <span class="trc-label">试算表 2221 期末余额</span>
          <span class="trc-value">{{ tbClosing == null ? '（未取数）' : fmtAmount(tbClosing) }}</span>
        </div>
        <div class="tb-recon-cell">
          <span class="trc-label">审定期末合计</span>
          <span class="trc-value">{{ fmtAmount(total.endAudited) }}</span>
        </div>
        <div class="tb-recon-cell">
          <span class="trc-label">差异</span>
          <span class="trc-value">{{ tbClosing == null ? '—' : fmtAmount(tbRecon.diff) }}</span>
          <el-tag v-if="tbClosing == null" type="info" size="small" effect="plain">待取数</el-tag>
          <el-tag v-else-if="tbRecon.matched" type="success" size="small" effect="plain">✓ 勾稽一致</el-tag>
          <el-tag v-else type="danger" size="small" effect="plain">⚠ 存在差异</el-tag>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip）N4 联动 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 税金联动：</span>
      <GtIndexChip value="N4-1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">税金及附加审定表（计提核对）</span>
      <GtIndexChip value="N2-6" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">增值税测算</span>
      <GtIndexChip value="N2-8" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">其他税费测算</span>
      <GtIndexChip value="N2-9" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">房产税测算</span>
      <GtIndexChip value="N2-10" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">土地增值税测算</span>
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
        <li>应交税费（2221）为<strong>负债类贷方科目</strong>，本表按"期初数 / 期末数 / 变动 / 原因分析"四大块对齐源模板。</li>
        <li>期初审定 = 期初未审 + 期初账项调整 + 期初重分类；期末审定 = 期末未审 + 期末账项调整 + 期末重分类。</li>
        <li>变动额 = 期末 − 期初；变动率 = 变动额 ÷ 期初，超 30% 黄字提示、超 50% 红字预警，需在原因分析列说明。</li>
        <li>底部试算平衡勾稽：审定期末合计应与试算表科目 2221 期末余额一致。</li>
        <li>各测算表（N2-6 增值税 / N2-8 城建税及附加 / N2-9 房产税 / N2-10 土增税）测算结果应与本表对应行勾稽。</li>
        <li>"回写审定数"将审定期末合计回写至试算表（科目 2221 期末余额），并通知 N4 税金及附加联动。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabAdjudication — N2-1 应交税费审定表（14 列源模板对齐版）
 *
 * 源结构：项目 + 期初数(未审/账项调整/重分类/审定auto) + 期末数(同4列)
 *         + 变动(未审变动额/率 + 审定变动额/率) + 原因分析
 *
 * - beginAudited = beginUnadj + beginAje + beginRje；endAudited 同理
 * - 变动率 >30% 黄字、>50% 红字
 * - 底部试算平衡勾稽（TB 2221 期末 vs 审定合计）
 * - TB 回写 + GtIndexChip N4 联动
 * - 审计说明+结论（AI 真回填）
 * - item_id：N2-1-adjudication-rows / N2-1-note / N2-1-conclusion
 * - 向后兼容旧字段名（beginning/creditAmount/debitAmount/unadjusted/aje/rje）
 * - 消费 render htmlData.adjudication_prefill（无持久化时种子未审期初/期末）
 *
 * 科目：2221 应交税费（贷方/负债类！）
 */
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2Adjudication14 } from '../../composables/useN2Adjudication'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  year?: string
  htmlData?: any
}>()

// ─── FormData ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useN2FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── prefill / TB 取数 ───────────────────────────────────────────────────────

const prefill = computed<any[] | null>(() => {
  const pf = props.htmlData?.adjudication_prefill
  return Array.isArray(pf) ? pf : null
})

const tbClosing = computed<number | null>(() => {
  const hd = props.htmlData
  const raw =
    hd?.tb_closing_2221 ??
    hd?.tb_closing ??
    hd?.trial_balance?.closing_balance ??
    hd?.trial_balance?.['2221']?.closing_balance ??
    null
  if (raw == null) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
})

// ─── Composable（14列模型） ─────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  total,
  updateRow,
  addRow,
  removeRow,
  saveAndSync,
} = useN2Adjudication14({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
  writebackTB: (amt: number) => formData.writebackTB(amt, props.year),
  prefill,
})

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────

function _readResponseText(itemId: string): string {
  const r = props.allResponses?.get?.(itemId) as any
  const v = r?.conclusion ?? r?.remark
  return typeof v === 'string' ? v : ''
}

const auditNote = ref<string>(_readResponseText('N2-1-note'))
const auditConclusion = ref<string>(_readResponseText('N2-1-conclusion'))

watch(
  () => props.allResponses,
  () => {
    if (!auditNote.value) auditNote.value = _readResponseText('N2-1-note')
    if (!auditConclusion.value) auditConclusion.value = _readResponseText('N2-1-conclusion')
  },
  { deep: true },
)

const isReadonly = computed(() => props.isReadonly ?? false)
const writebackLoading = ref(false)
const noteAiLoading = ref(false)
const conclusionAiLoading = ref(false)

// ─── 试算平衡勾稽 ────────────────────────────────────────────────────────────

const tbRecon = computed(() => {
  if (tbClosing.value == null) {
    return { diff: 0, matched: false, status: 'trc-pending' }
  }
  const diff = total.value.endAudited - tbClosing.value
  const matched = Math.abs(diff) <= 0.01
  return { diff, matched, status: matched ? 'trc-ok' : 'trc-diff' }
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null | undefined): string {
  if (rate == null || rate === 0) return '—'
  return `${(rate * 100).toFixed(2)}%`
}

function rateClass(rate: number | null | undefined): string {
  const a = Math.abs(Number(rate) || 0)
  if (a > 0.5) return 'rate-red'
  if (a > 0.3) return 'rate-yellow'
  return ''
}

// ─── 单元格变更 ──────────────────────────────────────────────────────────────

async function handleUpdate(index: number, field: any, value: any) {
  await updateRow(index, field, value)
}

// ─── 新增/删除行 ─────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value: taxType } = await ElMessageBox.prompt(
      '请输入项目名称（如：增值税、城建税、房产税）',
      '新增项目行',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
        inputPlaceholder: '项目名称',
      },
    )
    await addRow(taxType)
    ElMessage.success(`已新增项目：${taxType}`)
  } catch {
    // 用户取消
  }
}

async function handleRemoveLast() {
  if (rows.value.length === 0) return
  try {
    await ElMessageBox.confirm('确认删除末行项目？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await removeRow(rows.value.length - 1)
    ElMessage.success('已删除末行')
  } catch {
    // 用户取消
  }
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = total.value
  const map: Record<number, string> = {
    1: fmtAmount(t.beginUnadj),
    2: fmtAmount(t.beginAje),
    3: fmtAmount(t.beginRje),
    4: fmtAmount(t.beginAudited),
    5: fmtAmount(t.endUnadj),
    6: fmtAmount(t.endAje),
    7: fmtAmount(t.endRje),
    8: fmtAmount(t.endAudited),
    9: fmtAmount(t.unadjChange),
    10: fmtRate(t.unadjRate),
    11: fmtAmount(t.auditedChange),
    12: fmtRate(t.auditedRate),
  }
  columns.forEach((_col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    sums[idx] = map[idx] ?? ''
  })
  return sums
}

// ─── TB 回写 ─────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  writebackLoading.value = true
  try {
    await saveAndSync()
    ElMessage.success('审定期末合计已回写试算表（科目 2221 期末余额）')
  } catch (err: any) {
    ElMessage.error(`回写失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

async function saveNote() {
  await formData.setField('1', 'note', auditNote.value)
}

async function saveConclusion() {
  await formData.setField('1', 'conclusion', auditConclusion.value)
}

// ─── AI 真回填（context 值全部转 String） ────────────────────────────────────

function _buildAiContext(): Record<string, string> {
  const t = total.value
  return {
    科目: '2221 应交税费（负债类）',
    期初审定合计: String(t.beginAudited.toFixed(2)),
    期末审定合计: String(t.endAudited.toFixed(2)),
    审定变动额: String(t.auditedChange.toFixed(2)),
    审定变动率: `${(t.auditedRate * 100).toFixed(2)}%`,
    试算表期末余额: tbClosing.value == null ? '未取数' : String(tbClosing.value.toFixed(2)),
    试算平衡勾稽: tbClosing.value == null ? '待取数' : (tbRecon.value.matched ? '一致' : '存在差异'),
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
      'n2-adjudication-note',
      '请基于应交税费审定表的期初/期末审定数、变动率及试算平衡勾稽情况，撰写审计说明。',
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
      'n2-adjudication-conclusion',
      '请基于应交税费审定表数据与勾稽结果，给出审计结论。',
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

.n2-adjudication {
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

/* ─── 负债类公式提示 ─── */
.liability-formula-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
  border: 1px solid #f48fb1;
  border-left: 4px solid #e91e63;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #880e4f;
}

.liability-formula-badge .el-icon {
  font-size: 16px;
  color: #e91e63;
  flex-shrink: 0;
}

/* ─── 表格 ─── */
.adjudication-table { margin-bottom: 12px; }

:deep(.adjudication-table .el-table) { font-size: var(--wp-font-size, 13px); }

.tax-type-cell { font-weight: 500; color: #303133; }

.cell-input { width: 100%; }

:deep(.cell-input .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }

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

/* ─── 变动率高亮 ─── */
.rate-yellow { color: #e6a23c !important; font-weight: 700; }
.rate-red { color: #f56c6c !important; font-weight: 700; }

/* ─── 新增/删除行 ─── */
.row-ops-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

/* ─── 试算平衡勾稽行 ─── */
.tb-recon-bar {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  background: #fafbfc;
}

.tb-recon-bar.trc-ok {
  background: #f0f9eb;
  border-color: #e1f3d8;
}

.tb-recon-bar.trc-diff {
  background: #fef0f0;
  border-color: #fde2e2;
}

.tb-recon-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.tb-recon-cells {
  display: flex;
  flex-wrap: wrap;
  gap: 28px;
  align-items: center;
}

.tb-recon-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trc-label { color: #606266; font-size: 12px; }
.trc-value { font-weight: 600; color: #303133; }

/* ─── 跨底稿联动 ─── */
.cross-wp-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 12px;
}

.cross-wp-label { color: #0369a1; font-weight: 500; margin-right: 4px; }
.cross-wp-desc { color: #64748b; margin-right: 8px; }

/* ─── 审计说明卡片 ─── */
.audit-notes-card { margin-bottom: 16px; }

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
