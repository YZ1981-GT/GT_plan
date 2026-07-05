<template>
  <div class="g7-tab-disposal-package">
    <!-- Section标题栏 + AI + 复核 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-12 处置检查（一揽子交易）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('disposal-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-12-disposal-package')">💬 复核</el-button>
      </div>
    </div>

    <el-skeleton v-if="!props.htmlData" :rows="6" animated />
    <div v-else class="disposal-package-content">
      <!-- 54行×14列单表（横向可滚动，固定前2列，max-height虚拟滚动） -->
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
        <el-table-column prop="transactionDate" label="交易日期" width="100" fixed />
        <el-table-column prop="transactionPrice" label="交易对价" width="110" align="right" />
        <el-table-column prop="shareholdingChange" label="持股变动" width="100" align="right" />
        <el-table-column label="累计对价" width="110" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="= SUM(前N次交易对价)">
              {{ calcCumulativePrice($index) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="累计变动" width="100" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="= SUM(前N次持股变动)">
              {{ calcCumulativeShareChange($index) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="lossOfControlDate" label="丧失控制权日" width="110" />
        <el-table-column prop="lossDateBookValue" label="丧失日账面" width="110" align="right" />
        <el-table-column prop="remainingInvestmentFV" label="剩余投资FV" width="110" align="right" />
        <el-table-column prop="retrospectiveAdjustment" label="追溯调整" width="110" align="right" />
        <el-table-column prop="consolidatedGain" label="合并处置损益" width="120" align="right" />
        <el-table-column prop="packageJudgmentBasis" label="一揽子判断依据" min-width="150" />
        <el-table-column prop="auditConclusion" label="审计结论" min-width="120" />
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
        placeholder="对一揽子交易处置的审计结论..."
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDisposalPackage — G7-12 处置（一揽子交易）54行×14列
 *
 * 虚拟滚动：el-table max-height="580"（54行，标准el-table原生滚动即可）
 * 横向：固定前2列(被投资单位+交易日期)，其余列可横滚
 *
 * Requirements: 5.2, 5.4, 5.5, 7.5
 */
import { ref, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { parseNum } from '../../../composables/useG7SubFormulaEngine'

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
  return props.htmlData?.disposalPackage?.rows ?? []
})

// ═══ 累计计算（一揽子交易 SUM of prior） ═══
function calcCumulativePrice(index: number): string {
  let sum = 0
  for (let i = 0; i <= index; i++) {
    sum += parseNum(rows.value[i]?.transactionPrice)
  }
  return sum.toFixed(2)
}

function calcCumulativeShareChange(index: number): string {
  let sum = 0
  for (let i = 0; i <= index; i++) {
    sum += parseNum(rows.value[i]?.shareholdingChange)
  }
  return sum.toFixed(4)
}

async function handleAi(section: string): Promise<void> {
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/${section}`,
      { existingContent: conclusion.value, relatedContext: { sheet: 'G7-12' } },
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
.g7-tab-disposal-package { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
</style>
