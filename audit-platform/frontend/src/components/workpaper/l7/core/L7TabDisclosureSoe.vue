<template>
  <div class="l7-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="success" size="small">国企</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-soe')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露要求：</strong>
        除通用披露外，需按年初余额和期末余额列示其他非流动负债。
        国企格式重点关注国有资本相关融资安排和政府补贴明细。
        数据自动从审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ 附注表：项目 | 年初余额 | 期末余额 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他非流动负债披露明细</span>
          <el-button size="small" @click="handleAI('section1')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="年初余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateRow($index, 'beginBalance', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateRow($index, 'endBalance', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 国资专项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国资体系专项说明</span>
          <el-button size="small" @click="handleAI('section2')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeSpecialNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="国资体系内融资安排、政府贴息/补贴明细、国有股东相关安排等专项说明..."
        @change="handleSoeNoteChange"
      />
    </el-card>

    <!-- ═══ 核对结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">核对结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写附注核对结论..." :disabled="isReadonly" @change="saveConclusion" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企需额外披露国资体系内融资安排</li>
        <li>列报顺序为：项目 | 年初余额 | 期末余额（与上市公司不同）</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabDisclosureSoe — 附注披露信息（国有企业）
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 4.5
 * Requirements: 4.4-4.5
 *
 * Table: 项目 | 年初余额 | 期末余额 (same data different order from Listed)
 * Auto-fill from EventBus 'substantive:adjudicated'
 */
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useL7FormData } from '../../composables/useL7FormData'
import { L7_NOTE_SECTION, buildL7SyncPayload } from '../../composables/l7NoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref([
  { item: '递延收益', beginBalance: 0, endBalance: 0 },
  { item: '长期保证金/押金', beginBalance: 0, endBalance: 0 },
  { item: '政府补助（非流动）', beginBalance: 0, endBalance: 0 },
  { item: '预收款项（非流动）', beginBalance: 0, endBalance: 0 },
  { item: '其他', beginBalance: 0, endBalance: 0 },
  { item: '合计', beginBalance: 0, endBalance: 0 },
])

const soeSpecialNote = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'beginBalance' | 'endBalance', val: number) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value[index][field] = val
    formData.debouncedSave(`L7-disclosure-soe-${index}-${field}`, { remark: String(val) })
  }
}

function handleSoeNoteChange() {
  formData.debouncedSave('L7-disclosure-soe-special', { remark: soeSpecialNote.value || null })
}

// ─── Conclusion ──────────────────────────────────────────────────────────────

const conclusion = ref('')

function saveConclusion() {
  formData.debouncedSave('L7-disc-soe-conclusion', { remark: conclusion.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l7-disclosure-soe-${section}`,
      prompt: `请基于其他非流动负债底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.('L7-disclosure-soe', '附注披露（国企）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData()
}

onMounted(async () => {
  await formData.loadData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.l7-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
