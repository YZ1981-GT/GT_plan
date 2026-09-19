<script setup lang="ts">
/**
 * D1TabEclCalc.vue — D1-15 应收票据坏账准备测算表
 *
 * Spec: .kiro/specs/d1-ecl-provision/
 * Task: 7.1
 *
 * 8列测算表×2 section（组合+单项）+ 差异分析卡片 + 审计说明/结论
 * 公式：D=B×C / F=E-D / SUM合计
 *
 * Requirements: 6.1-9.5, 11.1-11.5, 13.1-13.7, 15.1-15.7, 16.1-16.4
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useD1EclCalc, formatAmountDisplay } from '../composables/useD1EclCalc'
import type { ChecklistResponse } from '../composables/useD1FormData'
import type { Ref } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isReadonly: false,
})

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Format Helper ───────────────────────────────────────────────────────────

const fmtAmount = computed(() => displayPrefs.fmtAmount)

// ─── Save helpers ────────────────────────────────────────────────────────────

async function saveImmediate(items: any[]): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
  } catch {
    ElMessage.warning('保存失败，请重试')
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
async function debouncedSave(items: any[]): Promise<void> {
  if (props.isReadonly) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch {
      ElMessage.warning('保存失败，请重试')
    }
  }, 2000)
}

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  portfolioRows,
  individualRows,
  addPortfolioRow,
  removePortfolioRow,
  addIndividualRow,
  removeIndividualRow,
  updateRow,
  lossRateWarningRow,
  portfolioSumRow,
  individualSumRow,
  grandTotalRow,
  materialityThreshold,
  exceedsMateriality,
  auditProcedures,
  auditNote,
  auditConclusion,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
  isLoading,
  hydrate,
  exportTemplate,
  exportData,
  importData,
  pullFromD1_4,
  d1_4DataAvailable,
} = useD1EclCalc({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  saveImmediate,
  debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
})

// ─── Import File Input ───────────────────────────────────────────────────────

async function handleImport(file: File) {
  if (!file) return
  try {
    await importData(file)
    ElMessage.success('导入成功')
    hydrate()
  } catch {
    ElMessage.error('导入失败，请检查文件格式')
  }
  return false
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)
const aiLoadingProcedures = ref(false)

const AUDIT_OBJECTIVES = [
  '应收票据坏账准备金额已恰当计提并反映于财务报表；',
  '组合计提与单项计提分类清晰且不存在重复计提；',
  '计提依据、索引及差异分析能够支撑审计判断。',
]

function buildEclContext(): string {
  // 收集差异汇总+重要性+各行最大差异
  const lines: string[] = []
  lines.push(`【组合差异合计】${portfolioSumRow.value.difference}`)
  lines.push(`【单项差异合计】${individualSumRow.value.difference}`)
  lines.push(`【差异总额】${grandTotalRow.value.difference}`)
  lines.push(`【重要性水平】${materialityThreshold.value > 0 ? materialityThreshold.value : '未设置'}`)
  lines.push(`【是否超重要性】${exceedsMateriality.value ? '是' : '否'}`)

  // 各行最大差异 Top 3
  const allRows = [...portfolioRows.value, ...individualRows.value]
  const sorted = allRows
    .filter(r => r.difference !== 0)
    .sort((a, b) => Math.abs(b.difference) - Math.abs(a.difference))
    .slice(0, 3)
  if (sorted.length > 0) {
    lines.push(`【差异最大的债务人】`)
    sorted.forEach(r => {
      lines.push(`  - ${r.debtor || '未命名'}：差异${r.difference}，余额${r.balance}，损失率${(r.lossRate * 100).toFixed(2)}%`)
    })
  }

  return lines.join('\n')
}

async function generateAuditNoteWithAI() {
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'ecl-audit-note',
      buildEclContext(),
      { guidance: guidanceContent },
      'AI · 审计说明',
    )
    if (text) {
      auditNote.value = text
      saveAuditNote()
    }
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateAuditProceduresWithAI() {
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'ecl-audit-note',
      `【审计过程】${auditProcedures.value || '（未填写）'}\n${buildEclContext()}`,
      { guidance: guidanceContent, section: 'D1-15-audit-procedures' },
      'AI · 审计过程',
    )
    if (text) {
      auditProcedures.value = text
      saveAuditProcedures()
    }
  } finally {
    aiLoadingProcedures.value = false
  }
}

async function generateAuditConclusionWithAI() {
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'ecl-audit-conclusion',
      buildEclContext() + `\n【审计说明】${auditNote.value || '（未填写）'}`,
      { guidance: guidanceContent },
      'AI · 审计结论',
    )
    if (text) {
      auditConclusion.value = text
      saveAuditConclusion()
    }
  } finally {
    aiLoadingConclusion.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  hydrate()
})

// ─── Review Dialog ───────────────────────────────────────────────────────────

function handleOpenNoteReview() {
  openReviewDialog?.('D1-ecl-audit-note')
}

function handleOpenConclusionReview() {
  openReviewDialog?.('D1-ecl-audit-conclusion')
}

// ─── Guidance Content ────────────────────────────────────────────────────────

const guidanceContent = `1. D=B×C 含义：应计提坏账准备 = 审定应收票据余额 × 预期信用损失率
   按组合section用账龄迁徙率或同类损失率，按单项section用个别评估损失率

2. F=E-D 差异追查：差异 = 期末坏账准备账面余额 - 应计提金额
   正值表示多提（公司计提>应计提），负值表示少提（公司计提<应计提）
   差异≠0时需分析原因，判断是否需要审计调整

3. 组合与单项不重复：同一债务人不能同时出现在组合和单项section
   已做单项评估的应从组合评估中剔除

4. 超重要性水平建议：当差异总额绝对值超过重要性水平时
   应与管理层沟通调整，或考虑出具非无保留意见审计报告`

</script>

<template>
  <div class="ecl-calc-table">
    <!-- Dual Mode Switch + Toolbar -->
    <div class="toolbar">
      <div style="flex:1" />
      <el-button-group size="small">
        <el-button @click="exportTemplate">导出模板</el-button>
        <el-button @click="exportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="handleImport"
          style="display:inline-block"
        >
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button size="small" type="primary" @click="pullFromD1_4" :disabled="!d1_4DataAvailable">
        从D1-4取数
      </el-button>
      <span v-if="!d1_4DataAvailable" class="d1-4-hint">⚠️ D1-4坏账准备明细表尚未填写</span>
    </div>

    <div>
      <!-- Loading Skeleton -->
      <el-skeleton v-if="isLoading" :rows="12" animated />

      <template v-else>
        <div class="tab-header">
          <h4>坏账准备测算 D1-15</h4>
          <GtReviewTrigger section-id="D1-ecl-header" />
        </div>
        <details class="methodology-collapse" open>
          <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
          <div class="methodology-body">
            <p class="method-title"><strong>一、审计目标：</strong></p>
            <ol class="method-objectives">
              <li v-for="(item, i) in AUDIT_OBJECTIVES" :key="'obj-' + i">{{ item }}</li>
            </ol>
            <div class="method-title-row">
              <p class="method-title"><strong>二、审计过程：</strong></p>
              <el-tooltip :content="aiAvailable ? 'AI辅助生成审计过程' : 'AI服务暂不可用'" placement="top">
                <el-button size="small" :loading="aiLoadingProcedures" :disabled="isReadonly || !aiAvailable" @click="generateAuditProceduresWithAI">🤖 AI</el-button>
              </el-tooltip>
            </div>
            <el-input
              v-model="auditProcedures"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="请填写审计过程..."
              @input="saveAuditProcedures"
            />
          </div>
        </details>
        <!-- Section 1: 按组合计提 -->
        <el-divider content-position="left">一、按组合计提坏账准备测算</el-divider>
        <el-table :data="portfolioRows" border size="small" class="ecl-table">
          <el-table-column label="A 债务人名称" min-width="140" align="left">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.debtor"
                :disabled="isReadonly"
                placeholder="债务人"
                @input="(val: string) => updateRow('portfolio', $index, 'debtor', val)"
              />
              <GtReviewDot row-prefix="D1-ecl" :row-key="String(row.id)" />
            </template>
          </el-table-column>
          <el-table-column label="B 审定余额" min-width="130" align="right">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.balance === 0 ? '' : String(row.balance)"
                :disabled="isReadonly"
                placeholder="0.00"
                @input="(val: string) => updateRow('portfolio', $index, 'balance', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="C 预期信用损失率" min-width="130" align="center">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.lossRate === 0 ? '' : (row.lossRate * 100).toFixed(2)"
                :disabled="isReadonly"
                placeholder="0.00%"
                :class="{ 'loss-rate-warning': lossRateWarningRow === row.id }"
                @input="(val: string) => updateRow('portfolio', $index, 'lossRate', (Number(val) || 0) / 100)"
              >
                <template #suffix>%</template>
              </el-input>
            </template>
          </el-table-column>
          <el-table-column label="D 应计提" min-width="120" align="right">
            <template #default="{ row }">
              <span class="cell-readonly" :class="{ 'cell-diff-nonzero': row.shouldProvision < 0 }">
                {{ formatAmountDisplay(row.shouldProvision, fmtAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="E 账面余额" min-width="130" align="right">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.actualProvision === 0 ? '' : String(row.actualProvision)"
                :disabled="isReadonly"
                :class="{ 'auto-pulled': row.autoPulled }"
                placeholder="0.00"
                @input="(val: string) => updateRow('portfolio', $index, 'actualProvision', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="F 差异" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-readonly" :class="{ 'cell-diff-nonzero': row.difference !== 0 }">
                {{ formatAmountDisplay(row.difference, fmtAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="G 计提依据" min-width="160" align="left">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.basis"
                type="textarea"
                :rows="1"
                :disabled="isReadonly"
                placeholder="依据"
                @input="(val: string) => updateRow('portfolio', $index, 'basis', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="H 索引号" min-width="100" align="center">
            <template #default="{ row, $index }">
              <GtIndexChip
                :value="row.indexRef"
                :readonly="isReadonly"
                @update="(val: string) => updateRow('portfolio', $index, 'indexRef', val)"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removePortfolioRow($index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Portfolio Sum Row -->
        <div class="sum-row">
          <span class="sum-label">组合合计：</span>
          <span class="sum-cell">B {{ formatAmountDisplay(portfolioSumRow.balance, fmtAmount) }}</span>
          <span class="sum-cell">D {{ formatAmountDisplay(portfolioSumRow.shouldProvision, fmtAmount) }}</span>
          <span class="sum-cell">E {{ formatAmountDisplay(portfolioSumRow.actualProvision, fmtAmount) }}</span>
          <span class="sum-cell" :class="{ 'cell-diff-nonzero': portfolioSumRow.difference !== 0 }">F {{ formatAmountDisplay(portfolioSumRow.difference, fmtAmount) }}</span>
        </div>
        <el-button v-if="!isReadonly" type="primary" link @click="addPortfolioRow" style="margin-top:8px">
          + 添加组合
        </el-button>

        <!-- Section 2: 按单项计提 -->
        <el-divider content-position="left">二、按单项计提坏账准备测算</el-divider>
        <el-table :data="individualRows" border size="small" class="ecl-table">
          <el-table-column label="A 债务人名称" min-width="140" align="left">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.debtor"
                :disabled="isReadonly"
                placeholder="债务人"
                @input="(val: string) => updateRow('individual', $index, 'debtor', val)"
              />
              <GtReviewDot row-prefix="D1-ecl" :row-key="String(row.id)" />
            </template>
          </el-table-column>
          <el-table-column label="B 审定余额" min-width="130" align="right">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.balance === 0 ? '' : String(row.balance)"
                :disabled="isReadonly"
                placeholder="0.00"
                @input="(val: string) => updateRow('individual', $index, 'balance', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="C 预期信用损失率" min-width="130" align="center">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.lossRate === 0 ? '' : (row.lossRate * 100).toFixed(2)"
                :disabled="isReadonly"
                placeholder="0.00%"
                :class="{ 'loss-rate-warning': lossRateWarningRow === row.id }"
                @input="(val: string) => updateRow('individual', $index, 'lossRate', (Number(val) || 0) / 100)"
              >
                <template #suffix>%</template>
              </el-input>
            </template>
          </el-table-column>
          <el-table-column label="D 应计提" min-width="120" align="right">
            <template #default="{ row }">
              <span class="cell-readonly" :class="{ 'cell-diff-nonzero': row.shouldProvision < 0 }">
                {{ formatAmountDisplay(row.shouldProvision, fmtAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="E 账面余额" min-width="130" align="right">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.actualProvision === 0 ? '' : String(row.actualProvision)"
                :disabled="isReadonly"
                :class="{ 'auto-pulled': row.autoPulled }"
                placeholder="0.00"
                @input="(val: string) => updateRow('individual', $index, 'actualProvision', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="F 差异" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-readonly" :class="{ 'cell-diff-nonzero': row.difference !== 0 }">
                {{ formatAmountDisplay(row.difference, fmtAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="G 计提依据" min-width="160" align="left">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.basis"
                type="textarea"
                :rows="1"
                :disabled="isReadonly"
                placeholder="依据"
                @input="(val: string) => updateRow('individual', $index, 'basis', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="H 索引号" min-width="100" align="center">
            <template #default="{ row, $index }">
              <GtIndexChip
                :value="row.indexRef"
                :readonly="isReadonly"
                @update="(val: string) => updateRow('individual', $index, 'indexRef', val)"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeIndividualRow($index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Individual Sum Row -->
        <div class="sum-row">
          <span class="sum-label">单项合计：</span>
          <span class="sum-cell">B {{ formatAmountDisplay(individualSumRow.balance, fmtAmount) }}</span>
          <span class="sum-cell">D {{ formatAmountDisplay(individualSumRow.shouldProvision, fmtAmount) }}</span>
          <span class="sum-cell">E {{ formatAmountDisplay(individualSumRow.actualProvision, fmtAmount) }}</span>
          <span class="sum-cell" :class="{ 'cell-diff-nonzero': individualSumRow.difference !== 0 }">F {{ formatAmountDisplay(individualSumRow.difference, fmtAmount) }}</span>
        </div>
        <el-button v-if="!isReadonly" type="primary" link @click="addIndividualRow" style="margin-top:8px">
          + 添加单项
        </el-button>

        <!-- Grand Total Row -->
        <div class="grand-total-row">
          <span class="sum-label">总合计：</span>
          <span class="sum-cell">B {{ formatAmountDisplay(grandTotalRow.balance, fmtAmount) }}</span>
          <span class="sum-cell">D {{ formatAmountDisplay(grandTotalRow.shouldProvision, fmtAmount) }}</span>
          <span class="sum-cell">E {{ formatAmountDisplay(grandTotalRow.actualProvision, fmtAmount) }}</span>
          <span class="sum-cell" :class="{ 'cell-diff-nonzero': grandTotalRow.difference !== 0 }">F {{ formatAmountDisplay(grandTotalRow.difference, fmtAmount) }}</span>
        </div>

        <!-- 差异分析卡片 -->
        <el-card class="diff-card" shadow="never">
          <template #header>
            <span style="font-weight:600">差异分析</span>
          </template>
          <div class="diff-grid">
            <div class="diff-item">
              <span class="diff-label">组合差异合计</span>
              <span class="diff-value" :class="{ 'cell-diff-nonzero': portfolioSumRow.difference !== 0 }">
                {{ formatAmountDisplay(portfolioSumRow.difference, fmtAmount) }}
              </span>
            </div>
            <div class="diff-item">
              <span class="diff-label">单项差异合计</span>
              <span class="diff-value" :class="{ 'cell-diff-nonzero': individualSumRow.difference !== 0 }">
                {{ formatAmountDisplay(individualSumRow.difference, fmtAmount) }}
              </span>
            </div>
            <div class="diff-item">
              <span class="diff-label">差异总额</span>
              <span class="diff-value" :class="{ 'cell-diff-nonzero': grandTotalRow.difference !== 0 }">
                {{ formatAmountDisplay(grandTotalRow.difference, fmtAmount) }}
              </span>
            </div>
            <div class="diff-item">
              <span class="diff-label">重要性水平</span>
              <span class="diff-value">
                <template v-if="materialityThreshold > 0">
                  {{ fmtAmount(materialityThreshold) }}
                </template>
                <template v-else>
                  <span style="color:#e6a23c">⚠️ -</span>
                </template>
              </span>
            </div>
            <div class="diff-item diff-item-wide">
              <span class="diff-label">是否超重要性</span>
              <div v-if="materialityThreshold <= 0" style="color:#e6a23c;font-size: var(--wp-font-size, 13px)">
                ⚠️ 重要性水平尚未设置
              </div>
              <div v-else-if="exceedsMateriality" class="exceed-warning">
                ⚠️ 超重要性水平，建议调整
              </div>
              <div v-else class="within-ok">
                ✓ 未超重要性水平
              </div>
            </div>
          </div>
        </el-card>

        <!-- 审计说明 -->
        <div class="audit-section">
          <div class="section-label">审计说明</div>
          <el-input
            v-model="auditNote"
            type="textarea"
            :rows="4"
            :disabled="isReadonly"
            placeholder="请填写审计说明"
            @input="saveAuditNote"
          />
          <div class="section-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成' : 'AI服务暂不可用'" placement="top">
              <el-button size="small" :disabled="!aiAvailable || aiLoadingNote" :loading="aiLoadingNote" @click="generateAuditNoteWithAI">🤖 AI生成</el-button>
            </el-tooltip>
            <el-tooltip content="发起复核对话" placement="top">
              <el-button size="small" @click="handleOpenNoteReview">💬 复核</el-button>
            </el-tooltip>
          </div>
        </div>

        <!-- 审计结论 -->
        <div class="audit-section">
          <div class="section-label">审计结论</div>
          <el-input
            v-model="auditConclusion"
            type="textarea"
            :rows="4"
            :disabled="isReadonly"
            placeholder="请填写审计结论"
            @input="saveAuditConclusion"
          />
          <div class="section-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成' : 'AI服务暂不可用'" placement="top">
              <el-button size="small" :disabled="!aiAvailable || aiLoadingConclusion" :loading="aiLoadingConclusion" @click="generateAuditConclusionWithAI">🤖 AI生成</el-button>
            </el-tooltip>
            <el-tooltip content="发起复核对话" placement="top">
              <el-button size="small" @click="handleOpenConclusionReview">💬 复核</el-button>
            </el-tooltip>
          </div>
        </div>

        <!-- 编制提示折叠区 -->
        <details class="guidance-details">
          <summary>📋 编制提示</summary>
          <pre class="guidance-content">{{ guidanceContent }}</pre>
        </details>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ecl-calc-table {
  padding: 16px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

.methodology-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.8;
}

.method-title {
  margin: 8px 0 4px;
  font-size: var(--wp-font-size, 13px);
}

.method-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
}

.method-title-row .method-title {
  margin: 0;
}

.method-objectives {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.ecl-table {
  margin-top: 8px;
}

.ecl-table :deep(.el-table__header th),
.ecl-table :deep(.el-table__body td),
.ecl-table :deep(.el-input__inner),
.ecl-table :deep(.el-textarea__inner),
.ecl-table :deep(.el-input__wrapper),
.ecl-table :deep(.el-textarea__wrapper) {
  font-size: var(--wp-font-size, 13px);
}

.sum-row {
  background: #fafafa;
  font-weight: bold;
  padding: 8px 12px;
  margin-top: 8px;
  border-radius: 4px;
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
}

.grand-total-row {
  background: #f0f7ff;
  font-weight: bold;
  border-top: 2px solid #409eff;
  padding: 10px 12px;
  margin-top: 16px;
  border-radius: 4px;
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
}

.sum-label {
  min-width: 80px;
  color: #303133;
}

.sum-cell {
  min-width: 100px;
  text-align: right;
}

.diff-card {
  margin: 16px 0;
}

.diff-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.diff-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-item-wide {
  grid-column: span 3;
}

.diff-label {
  font-size: 12px;
  color: #909399;
}

.diff-value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.exceed-warning {
  background: #fef0f0;
  color: #f56c6c;
  padding: 8px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}

.within-ok {
  background: #f0f9eb;
  color: #67c23a;
  padding: 8px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}

.cell-readonly {
  background: #f5f7fa;
  padding: 4px 8px;
  border-radius: 2px;
  display: inline-block;
  min-width: 60px;
  text-align: right;
}

.cell-diff-nonzero {
  color: #f56c6c;
  font-weight: 500;
}

.loss-rate-warning :deep(.el-input__wrapper) {
  border-color: #e6a23c !important;
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.auto-pulled :deep(.el-input__wrapper) {
  background: #ecf5ff;
}

.d1-4-hint {
  font-size: 12px;
  color: #e6a23c;
  white-space: nowrap;
}

.audit-section {
  margin-top: 16px;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.section-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.guidance-details {
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 12px;
  margin-top: 16px;
  border-radius: 4px;
}

.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 14px;
}

.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: pre-wrap;
  line-height: 1.6;
}
</style>
