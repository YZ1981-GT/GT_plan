<template>
  <div class="l4-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息核对（上市公司）</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure')">
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
        <strong>上市公司应付债券附注披露要求：</strong>
        按CAS 37/CAS 22要求披露：①债券名称、面值、发行日、期限、利率 ②摊余成本变动 ③利息费用
        ④信用评级 ⑤担保情况 ⑥提前赎回条款 ⑦转换条款（可转债）。核对审定表数据与附注数据一致性。
      </div>
    </div>

    <!-- ═══ 披露核对表 ═══ -->
    <el-table :data="disclosureItems" border size="small" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="item" label="披露项目" min-width="200" />
      <el-table-column label="附注金额/内容" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.noteContent" size="small" placeholder="附注披露内容" @change="saveItem($index)" />
          <span v-else>{{ row.noteContent || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定表数据" min-width="150">
        <template #default="{ row }">
          <span class="formula-value">{{ row.auditedData || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="一致" width="80" align="center">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" v-model="row.isConsistent" size="small" style="width:100%" @change="saveItem($index)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="N/A" value="N/A" />
          </el-select>
          <el-tag v-else :type="row.isConsistent === '是' ? 'success' : row.isConsistent === '否' ? 'danger' : 'info'" size="small">
            {{ row.isConsistent || '待核' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="差异说明" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.diffNote" size="small" @change="saveItem($index)" />
          <span v-else>{{ row.diffNote || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 附注文本核对区 ═══ -->
    <el-card shadow="never" class="note-text-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">附注文本内容</span>
          <el-button size="small" @click="handleAI('noteText')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 15 }"
        placeholder="粘贴或编写应付债券附注文本..."
        :disabled="isReadonly"
        @change="saveNoteText"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">核对结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写附注披露核对结论..."
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>核对附注数据与审定表L4-1一致</li>
        <li>上市公司需额外披露信用评级、担保、提前赎回/转换条款</li>
        <li>subscribe 'substantive:adjudicated' 自动刷新审定数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabDisclosureListed — 附注披露信息核对（上市公司）
 *
 * Requirements: 8.3, 8.4
 * - 附注上市公司模板
 * - subscribe 'substantive:adjudicated' 刷新
 */
import { inject, onMounted, onUnmounted, ref, computed } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { eventBus } from '@/utils/eventBus'

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

interface DisclosureItem {
  seq: number
  item: string
  noteContent: string
  auditedData: string
  isConsistent: string
  diffNote: string
}

const disclosureItems = ref<DisclosureItem[]>([
  { seq: 1, item: '债券名称及面值', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 2, item: '发行日期及期限', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 3, item: '票面利率/实际利率', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 4, item: '期初摊余成本', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 5, item: '本期利息费用', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 6, item: '本期兑付金额', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 7, item: '期末摊余成本', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 8, item: '信用评级', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 9, item: '担保情况', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
  { seq: 10, item: '提前赎回/转换条款', noteContent: '', auditedData: '', isConsistent: '', diffNote: '' },
])

const noteText = ref('')
const conclusion = ref('')

function saveItem(index: number) {
  const item = disclosureItems.value[index]
  formData.debouncedSave(`L4-disc-listed-${item.seq}`, {
    conclusion: item.isConsistent || null,
    remark: JSON.stringify({ noteContent: item.noteContent, diffNote: item.diffNote }),
  })
}

function saveNoteText() {
  formData.debouncedSave('L4-disc-listed-noteText', { remark: noteText.value || null })
}

function saveConclusion() {
  formData.debouncedSave('L4-disc-listed-conclusion', { remark: conclusion.value || null })
}

// subscribe EventBus
function onAdjudicated() {
  // 刷新审定表数据（实际集成时拉取最新审定数据填入auditedData列）
}

onMounted(async () => {
  await formData.loadData()
  eventBus.on('substantive:adjudicated', onAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicated)
})

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }
</script>

<style scoped>
.l4-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.formula-value { color: #409eff; font-weight: 500; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.note-text-card { margin-top: 16px; }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
