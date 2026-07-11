<template>
  <div class="l5-tab-lt-payable-check">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-7 长期应付款检查表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('check')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>综合检查长期应付款合同条款、偿付安排、折现率适当性、摊销准确性、分类与披露完整性，形成审计结论。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>长期应付款检查要点：</strong>
        ①合同条款完整性（金额/利率/期限/担保） ②偿付安排合理性 ③折现率适当性（市场利率参照）
        ④未确认融资费用摊销准确性 ⑤分类准确性（一年内到期→短期） ⑥附注披露完整性。
      </div>
    </div>

    <!-- ═══ 核对清单 ═══ -->
    <el-card shadow="never" class="checklist-card">
      <template #header>
        <div class="card-header">
          <span>核对检查项</span>
          <el-tag size="small" :type="completionRate === 100 ? 'success' : 'warning'">
            {{ completedCount }}/{{ checkItems.length }} 已完成
          </el-tag>
        </div>
      </template>

      <el-table :data="checkItems" size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="检查项" min-width="300">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="160" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.result"
              size="small"
              style="width:100%"
              placeholder="请选择"
              @change="(val: string) => handleCheckUpdate($index, 'result', val)"
            >
              <el-option label="符合" value="符合" />
              <el-option label="基本符合" value="基本符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getResultTagType(row.result)" size="small">
              {{ row.result || '待检查' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              size="small"
              placeholder="补充说明"
              @change="(val: string) => handleCheckUpdate($index, 'note', val)"
            />
            <span v-else>{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成结论
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据上述检查结果，得出审计结论..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项完成核对清单，确保覆盖合同条款/偿付/折现/摊销/分类/披露</li>
        <li>不符合项应详细说明原因及影响</li>
        <li>审计结论可使用AI辅助生成，但需复核确认</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabLtPayableCheck — L5-7 长期应付款检查表
 * Requirements: 5.2
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL5FormData } from '../../composables/useL5FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 检查项数据 ──────────────────────────────────────────────────────────────

interface CheckItem {
  question: string
  result: string
  note: string
}

const checkItems = ref<CheckItem[]>([
  { question: '长期应付款合同条款是否完整（金额、利率、期限、担保条款）', result: '', note: '' },
  { question: '偿付安排是否合理（分期金额/频率与经营现金流匹配）', result: '', note: '' },
  { question: '折现率（EIR）选取是否适当（参照同期同类市场利率）', result: '', note: '' },
  { question: '未确认融资费用本期摊销计算是否准确（实际利率法复核）', result: '', note: '' },
  { question: '长期应付款中一年内到期部分是否正确重分类至流动负债', result: '', note: '' },
  { question: '关联方长期应付款定价条件是否公允', result: '', note: '' },
  { question: '附注披露是否完整（款项性质/到期时间/担保情况/关联方交易）', result: '', note: '' },
  { question: '期初余额与上年审定数是否一致', result: '', note: '' },
])

const auditConclusion = ref('')

// ─── 计算属性 ────────────────────────────────────────────────────────────────

const completedCount = computed(() => checkItems.value.filter(i => i.result).length)
const completionRate = computed(() =>
  checkItems.value.length > 0 ? Math.round((completedCount.value / checkItems.value.length) * 100) : 0
)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCheckUpdate(index: number, field: 'result' | 'note', value: string) {
  if (index < 0 || index >= checkItems.value.length) return
  checkItems.value[index][field] = value
  formData.debouncedSave(`L5-L5-7-check-${index + 1}-${field}`, { remark: value || null })
}

function handleConclusionChange() {
  formData.debouncedSave('L5-L5-7-conclusion', { remark: auditConclusion.value || null })
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function getResultTagType(result: string): string {
  switch (result) {
    case '符合': return 'success'
    case '基本符合': return 'info'
    case '不符合': return 'danger'
    case '不适用': return 'warning'
    default: return 'info'
  }
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l5-tab-lt-payable-check { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.checklist-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.conclusion-card { margin-bottom: 16px; }
:deep(.el-table) { font-size: 13px; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
