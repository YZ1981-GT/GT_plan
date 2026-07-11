<script setup lang="ts">
/**
 * D2TabBadDebt — 坏账准备明细表 D2-3
 *
 * 三分类（单项/账龄组合/客户类型组合），固定汇总行 + 可增删子行。
 * 打磨基准：D1 检查型底稿（审计目标 / 金额列可编辑 / 计算列只读+tooltip /
 *           ECL 差异联动 / 审计说明+结论 / 编制提示）
 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import { useD2BadDebt, type BadDebtRow } from '../composables/useD2BadDebt'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-3',
)

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const eclTestTotal = ref(0)

const {
  individualRows,
  agingRows,
  customerTypeRows,
  totalRow,
  eclWarning,
  addSubRow,
  removeSubRow,
  updateCell,
} = useD2BadDebt({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  eclTestTotal,
})

type Category = 'individual' | 'aging' | 'customer-type'

const sections: Array<{ category: Category; title: string; rows: Ref<BadDebtRow[]> }> = [
  { category: 'individual', title: '按单项计提', rows: individualRows },
  { category: 'aging', title: '按账龄组合', rows: agingRows },
  { category: 'customer-type', title: '按客户类型组合', rows: customerTypeRows },
]

/** 汇总固定行：若该分类存在子行，则汇总行为自动合计（只读）；无子行时可直接录入 */
function isRowEditable(rows: BadDebtRow[], row: BadDebtRow): boolean {
  if (props.isReadonly) return false
  if (row.isSubRow) return true
  // fixed row: editable only when no sub rows
  return !rows.some(r => r.isSubRow)
}

// ─── 审计结论（inline 存储）────────────────────────────────────────────────
const CONCLUSION_KEY = 'D2-baddebt-conclusion'
const auditConclusion = ref('')
onMounted(() => { auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || '' })

function saveConclusion(v: string): void {
  if (props.isReadonly) return
  auditConclusion.value = v
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: v }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
}

const { aiAvailable, generateAndConfirm } = useD2AiGenerate(toRef(props, 'wpId'))
const aiLoadingConclusion = ref(false)

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm('baddebt-note', auditConclusion.value, {
      sheet: 'D2-3',
      priorAudited: totalRow.value.priorAudited,
      currentAudited: totalRow.value.currentAudited,
    }, 'AI · 坏账准备说明')
    if (text) saveConclusion(text)
  } finally { aiLoadingConclusion.value = false }
}

const GUIDANCE_TEXTS = [
  '坏账准备按单项和组合两种方式计提：对存在客观减值证据的应收款单项评估；对信用风险特征相似的组合按账龄或客户类型评估预期信用损失（CAS 22）。',
  '本表期末审定 = 期初审定 + 计提 + 转入 − 收回 − 转回 − 核销 + AJE + RJE（灰色列为自动计算）。',
  '期末审定合计应与 D2-9/D2-10 ECL 测算结果勾稽，差异需查明（下方警告联动 D2-9）。',
  '关注计提比例的一致性与合理性，避免通过多提/少提坏账调节利润。',
]
</script>

<template>
  <div class="d2-tab-bad-debt">
    <div class="tab-header">
      <h4>坏账准备明细表 D2-3</h4>
      <GtReviewTrigger section-id="D2-baddebt-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>核实坏账准备计提的完整性、准确性与充分性，评价计提方法与比例的合理性，并与 ECL 测算勾稽（CAS 22）。</p>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <el-button-group>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" style="display:inline-block">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <!-- ECL差异警告 -->
    <el-alert v-if="eclWarning" type="warning" :closable="false" show-icon class="ecl-alert">
      <span>{{ eclWarning }}</span>
      <GtIndexChip v-if="jumpToSection" label="D2-9" class="ecl-chip" @click="jumpToSection('应收坏账准备测算D2-9')" />
    </el-alert>

    <!-- 三分类区块 -->
    <div v-for="section in sections" :key="section.category" class="section-block">
      <div class="section-header">
        <span class="section-title">{{ section.title }}</span>
        <el-button v-if="!isReadonly" size="small" type="primary" link @click="addSubRow(section.category)">+ 添加子行</el-button>
      </div>

      <el-table :data="section.rows.value" border size="small" max-height="420" style="width: 100%">
        <el-table-column prop="label" label="项目" width="170" fixed="left">
          <template #default="{ row }">
            <el-input
              v-if="row.isSubRow && !isReadonly"
              :model-value="row.label"
              size="small"
              placeholder="债务人/组合名称"
              @change="(v: string) => updateCell(row.rowId, 'label', v as any)"
            />
            <span v-else :style="{ fontWeight: row.isFixed ? '600' : 'normal' }">{{ row.label }}</span>
            <GtReviewDot row-prefix="D2-baddebt" :row-key="row.rowId" />
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初未审" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.priorUnadjusted" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.priorAje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAje', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.priorRje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorRje', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="= 期初未审 + AJE + RJE（自动计算）" placement="top">
              <span class="calc-cell">{{ displayPrefs.fmtAmount(row.priorAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 本期增加 -->
        <el-table-column label="计提" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentProvision" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentProvision', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentTransferIn" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentTransferIn', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentTransferIn) }}</span>
          </template>
        </el-table-column>

        <!-- 本期减少 -->
        <el-table-column label="收回" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentRecovery" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentRecovery', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentRecovery) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentReversal" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentReversal', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentWriteOff" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentWriteOff', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentWriteOff) }}</span>
          </template>
        </el-table-column>

        <!-- 期末 -->
        <el-table-column label="期末未审" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="= 期初审定 + 计提 + 转入 − 收回 − 转回 − 核销（自动计算）" placement="top">
              <span class="calc-cell">{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentAje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentAje', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="isRowEditable(section.rows.value, row)" :model-value="row.currentRje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentRje', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="= 期末未审 + AJE + RJE（自动计算）" placement="top">
              <span class="calc-cell" style="font-weight:600">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-popconfirm v-if="row.isSubRow" title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeSubRow(row.rowId)">
              <template #reference><el-button type="danger" link size="small">✕</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 合计行 -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <span>期初审定 {{ displayPrefs.fmtAmount(totalRow.priorAudited) }}</span>
      <span>期末审定 {{ displayPrefs.fmtAmount(totalRow.currentAudited) }}</span>
    </div>

    <!-- 审计说明/结论 -->
    <div class="section-subtitle">
      审计说明与结论
      <GtReviewTrigger section-id="D2-baddebt-conclusion" />
      <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
        <el-button size="small" text type="primary" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusionAI">🤖 AI 生成</el-button>
      </el-tooltip>
      <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D2-baddebt-conclusion')">💬 复核</el-button>
    </div>
    <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditConclusion" placeholder="评价坏账准备计提的充分性、方法一致性及与 ECL 测算的勾稽..." :disabled="isReadonly" @change="saveConclusion" />

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-bad-debt { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.ecl-alert { margin-bottom: 12px; }
.ecl-chip { margin-left: 8px; vertical-align: middle; }
.section-block { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.section-title { font-weight: 600; font-size: 14px; }
.calc-cell { color: #909399; font-variant-numeric: tabular-nums; }
.total-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; }
.section-subtitle { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
</style>
