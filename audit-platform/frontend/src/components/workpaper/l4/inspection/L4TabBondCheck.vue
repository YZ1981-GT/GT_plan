<template>
  <div class="l4-tab-bond-check">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-9 应付债券检查表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('bondCheck')">
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
        <strong>应付债券检查表：</strong>
        综合检查应付债券的完整性、存在性、准确性、列报和披露。
        逐项核对后形成审计结论。结论区使用el-card包裹，支持AI辅助填写。
      </div>
    </div>

    <!-- ═══ 检查清单 ═══ -->
    <el-table
      :data="checkItems"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="category" label="类别" width="100" />
      <el-table-column prop="content" label="检查内容" min-width="300" />
      <el-table-column label="结论" width="120" align="center">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" v-model="row.result" size="small" style="width:100%" @change="saveCheckItem($index)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag v-else :type="getResultTagType(row.result)" size="small">{{ row.result || '待检' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="补充说明" @change="saveCheckItem($index)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 检查进度 ═══ -->
    <div class="check-progress">
      <span>检查进度：{{ completedCount }} / {{ checkItems.length }}</span>
      <el-progress :percentage="progressPct" :stroke-width="6" :show-text="false" style="width:200px;display:inline-block;margin-left:8px" />
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="请填写应付债券审计结论（AI可辅助生成）..."
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>检查表按五大认定分组：完整性/存在性/准确性/列报/披露</li>
        <li>结论应综合前述各sheet的核对结果出具</li>
        <li>重点关注：后续计量是否准确（L4-7/L4-8）、披露是否充分（附注）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabBondCheck — L4-9 应付债券检查表
 *
 * Requirements: 8.2
 * - 核对清单 + 审计结论区(el-card包裹)
 * - AI辅助
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

interface CheckItem {
  seq: number
  category: string
  content: string
  result: string
  remark: string
}

const checkItems = ref<CheckItem[]>([
  { seq: 1, category: '完整性', content: '是否已获取所有已发行应付债券的完整清单', result: '', remark: '' },
  { seq: 2, category: '完整性', content: '是否核对了债券登记机构的确认函', result: '', remark: '' },
  { seq: 3, category: '存在性', content: '发行文件（募集说明书/发行批文）是否齐全', result: '', remark: '' },
  { seq: 4, category: '存在性', content: '已兑付债券是否有银行划款凭证', result: '', remark: '' },
  { seq: 5, category: '准确性', content: '初始计量（发行价−交易费用）是否正确', result: '', remark: '' },
  { seq: 6, category: '准确性', content: '后续计量实际利率法是否正确（L4-7验证）', result: '', remark: '' },
  { seq: 7, category: '准确性', content: '账面核对差异是否在可接受范围（L4-8验证）', result: '', remark: '' },
  { seq: 8, category: '准确性', content: '权益负债划分是否正确（L4-5验证）', result: '', remark: '' },
  { seq: 9, category: '列报', content: '一年内到期的应付债券是否正确重分类', result: '', remark: '' },
  { seq: 10, category: '列报', content: '面值/利息调整/应计利息是否分项列示', result: '', remark: '' },
  { seq: 11, category: '披露', content: '附注是否充分披露债券条款和利率信息', result: '', remark: '' },
  { seq: 12, category: '披露', content: '附注是否披露信用评级和担保情况', result: '', remark: '' },
])

const conclusion = ref('')

const completedCount = computed(() => checkItems.value.filter(i => i.result).length)
const progressPct = computed(() => Math.round((completedCount.value / checkItems.value.length) * 100))

function saveCheckItem(index: number) {
  const item = checkItems.value[index]
  formData.debouncedSave(`L4-9-check-${item.seq}`, {
    conclusion: item.result || null,
    remark: item.remark || null,
  })
}

function saveConclusion() {
  formData.debouncedSave('L4-9-conclusion', { remark: conclusion.value || null })
}

function getResultTagType(result: string): 'success' | 'danger' | 'info' | 'warning' {
  if (result === '是') return 'success'
  if (result === '否') return 'danger'
  if (result === '不适用') return 'info'
  return 'warning'
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-bond-check { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

:deep(.el-table) { font-size: 13px; }

.check-progress {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; font-size: 13px; color: #606266;
}

.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
