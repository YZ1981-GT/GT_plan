<template>
  <div class="g7-tab-disposal-single">
    <!-- Section标题栏 + AI + 复核 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-11 处置检查（非一揽子交易）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('disposal-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-11-disposal-single')">💬 复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：确认非一揽子交易下处置子公司股权的处置损益计算准确（个别报表=对价−账面−应收股利+可转损益OCI；合并层面另加合并调整与净资产份额影响），会计处理符合 CAS2/CAS33，处置时点及对价确认恰当。
    </el-alert>

    <el-skeleton v-if="!props.htmlData" :rows="6" animated />
    <div v-else class="disposal-single-content">
      <!-- 47行×14列单表（横向可滚动，固定前2列，max-height虚拟滚动） -->
      <el-table
        :data="rows"
        border
        size="small"
        max-height="580"
        highlight-current-row
        row-key="id"
        style="font-size: 13px"
      >
        <el-table-column prop="investeeName" label="被投资单位" width="140" fixed />
        <el-table-column prop="disposalDate" label="处置日" width="100" fixed />
        <el-table-column prop="disposalRatio" label="处置比例" width="90" align="right" />
        <el-table-column prop="disposalPrice" label="处置对价" width="110" align="right" />
        <el-table-column prop="disposalDateBookValue" label="处置日账面" width="110" align="right" />
        <el-table-column prop="disposalDateDividend" label="应收股利" width="100" align="right" />
        <el-table-column prop="priorOCICumulative" label="OCI累计" width="100" align="right" />
        <el-table-column prop="transferableOCI" label="可转OCI" width="100" align="right" />
        <el-table-column label="个别处置损益" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 对价 - 账面 - 应收股利 + 可转OCI">
              {{ calcIndividualGain(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="consolidationAdjustment" label="合并调整" width="110" align="right" />
        <el-table-column prop="consolidatedNetAssetShare" label="净资产份额" width="110" align="right" />
        <el-table-column prop="consolidatedGain" label="合并处置损益" width="120" align="right" />
        <el-table-column prop="auditConclusion" label="审计结论" min-width="150" />
        <el-table-column prop="indexRef" label="索引" width="80" />
      </el-table>
    </div>

    <!-- 审计结论（AI辅助） -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('disposal-conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对非一揽子处置的审计结论..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>个别处置损益 = 处置对价 − 处置日账面价值 − 应收股利 + 结转的可转损益OCI（CAS2）</li>
        <li>合并处置损益 = 处置对价 − 享有子公司自购买日持续计算的净资产份额 ± 合并层面商誉/调整</li>
        <li>处置部分股权但未丧失控制权：不确认损益，差额调整资本公积（合并层面）</li>
        <li>丧失控制权：剩余股权按丧失控制权日公允价值重新计量，差额计入投资收益</li>
        <li>与被投资方相关的其他综合收益，按处置比例结转（可结转部分转投资收益/留存收益）</li>
        <li>公式列显示虚线下划线，鼠标悬停可查看公式来源</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDisposalSingle — G7-11 处置（非一揽子）47行×14列
 *
 * 虚拟滚动：el-table max-height="580"（47行，标准el-table原生滚动即可）
 * 横向：固定前2列(被投资单位+处置日)，其余列可横滚
 *
 * Requirements: 5.1, 5.3, 5.5, 7.5
 */
import { ref, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { calcDisposalGain, parseNum } from '../../composables/useG7SubFormulaEngine'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const conclusion = ref('')
const aiLoading = ref(false)

const rows = computed(() => {
  return props.htmlData?.disposalSingle?.rows ?? []
})

function calcIndividualGain(row: any): string {
  const gain = calcDisposalGain(
    parseNum(row.disposalPrice),
    parseNum(row.disposalDateBookValue),
    parseNum(row.disposalDateDividend),
    parseNum(row.transferableOCI)
  )
  return gain.toFixed(2)
}

async function handleAi(section: string): Promise<void> {
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/${section}`,
      { existingContent: conclusion.value, relatedContext: { sheet: 'G7-11' } },
    )
    const text = res?.data?.data?.conclusion ?? res?.data?.conclusion ?? res?.data?.text ?? ''
    if (text) {
      conclusion.value = text
      ElMessage.success('AI结论已生成')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.g7-tab-disposal-single { padding: 12px; font-size: 13px; }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 4px 0 0 16px; line-height: 1.8; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
</style>
