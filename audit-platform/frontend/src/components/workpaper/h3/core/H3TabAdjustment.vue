<template>
  <div class="h3-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表登记投资性房地产相关的调整分录（AJE 审计调整 / RJE 重分类调整），每笔借贷必须平衡。</p>
        <p>2. 成本模式常见调整涉及科目 1503 投资性房地产、1504 累计折旧、1505 减值准备；公允价值模式涉及 1503 及公允价值变动损益。</p>
        <p>3. 每笔分录需选定资产类别（房屋及建筑物 / 土地使用权 / 其他）；未选时按摘要/科目名称推断。</p>
        <p>4. 借贷平衡后方可「发布至 H3-1」：按资产类别分摊写入各分类行的 AJE/RJE，并可「推送 A13」。</p>
        <p>5. 索引列填写支持性底稿索引号，便于交叉引用与复核追溯。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：完整、准确地记录投资性房地产的审计调整与重分类分录，确保借贷平衡并恰当反映至审定表与错报汇总。"
    />

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
      <el-button size="small" type="success" :disabled="!isBalanced || isReadonly" @click="publishAdjustment">发布至H3-1</el-button>
      <el-button size="small" :disabled="isReadonly" @click="pushToA13()">推送A13</el-button>
    </div>

    <!-- H3-3 → H3-1 同步预览 -->
    <el-card shadow="never" class="sync-card">
      <template #header>
        <div class="section-title">
          <span>同步预览（发布至 H3-1）</span>
          <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-1')">打开 H3-1</el-tag>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="AJE合计">{{ fmtNum(syncSummary.totalAje) }}</el-descriptions-item>
        <el-descriptions-item label="RJE合计">{{ fmtNum(syncSummary.totalRje) }}</el-descriptions-item>
        <el-descriptions-item label="借贷状态">
          <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">{{ isBalanced ? '平衡' : '不平衡' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="1503 AJE">{{ fmtNum(syncSummary.aje1503) }}</el-descriptions-item>
        <el-descriptions-item label="1503 RJE">{{ fmtNum(syncSummary.rje1503) }}</el-descriptions-item>
        <el-descriptions-item label="1504 AJE/RJE">{{ fmtNum(syncSummary.aje1504) }} / {{ fmtNum(syncSummary.rje1504) }}</el-descriptions-item>
        <el-descriptions-item label="1505 AJE/RJE" :span="3">{{ fmtNum(syncSummary.aje1505) }} / {{ fmtNum(syncSummary.rje1505) }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="categoryPreviewRows" border size="small" class="cat-preview-table">
        <el-table-column prop="category" label="资产类别" min-width="120" />
        <el-table-column prop="aje1503" label="1503 AJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.aje1503) }}</template>
        </el-table-column>
        <el-table-column prop="rje1503" label="1503 RJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.rje1503) }}</template>
        </el-table-column>
        <el-table-column prop="aje1504" label="1504 AJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.aje1504) }}</template>
        </el-table-column>
        <el-table-column prop="rje1504" label="1504 RJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.rje1504) }}</template>
        </el-table-column>
        <el-table-column prop="aje1505" label="1505 AJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.aje1505) }}</template>
        </el-table-column>
        <el-table-column prop="rje1505" label="1505 RJE" min-width="90" align="right">
          <template #default="{ row }">{{ fmtNum(row.rje1505) }}</template>
        </el-table-column>
      </el-table>
      <el-table :data="writeTargets" border size="small" class="cat-preview-table">
        <el-table-column prop="label" label="写入目标" min-width="200" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.exists ? 'success' : 'info'" size="small">{{ row.exists ? '可写入' : '无行' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="将写 AJE" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.aje) }}</template>
        </el-table-column>
        <el-table-column prop="rje" label="将写 RJE" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.rje) }}</template>
        </el-table-column>
      </el-table>
      <p class="sync-note">发布后按资产类别分摊：1503→原值/公允行，1504→折旧行，1505→减值行；无对应分类行时并入「其他」。</p>
    </el-card>

    <!-- 分录表 -->
    <el-table :data="rows" border size="small" class="audit-table">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column prop="description" label="调整事项说明" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-model="row.description" size="small" :disabled="isReadonly" @change="updateCell($index, 'description', row.description)" />
        </template>
      </el-table-column>
      <el-table-column prop="entryType" label="调整类型" width="90" align="center">
        <template #default="{ row, $index }">
          <el-select v-model="row.entryType" size="small" :disabled="isReadonly" @change="updateCell($index, 'entryType', row.entryType)">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="资产类别" width="130" align="center">
        <template #default="{ row, $index }">
          <el-select v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell($index, 'category', row.category)">
            <el-option v-for="cat in H3_ASSET_CATEGORIES" :key="cat" :label="cat" :value="cat" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目代码" width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.accountCode" size="small" :disabled="isReadonly" @change="updateCell($index, 'accountCode', row.accountCode)" />
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.accountName" size="small" :disabled="isReadonly" @change="updateCell($index, 'accountName', row.accountName)" />
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.summary" size="small" :disabled="isReadonly" @change="updateCell($index, 'summary', row.summary)" />
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly" @change="updateCell($index, 'debitAmount', row.debitAmount)" />
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly" @change="updateCell($index, 'creditAmount', row.creditAmount)" />
        </template>
      </el-table-column>
      <el-table-column prop="indexRef" label="索引" width="80">
        <template #default="{ row, $index }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell($index, 'indexRef', row.indexRef)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text :disabled="isReadonly" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷合计+平衡校验 -->
    <div class="balance-row">
      <span>借方合计：<b>{{ fmtNum(debitTotal) }}</b></span>
      <span>贷方合计：<b>{{ fmtNum(creditTotal) }}</b></span>
      <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
        {{ isBalanced ? '借贷平衡 ✓' : '借贷不平衡 ✗' }}
      </el-tag>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：各笔调整/重分类的事由、依据、涉及科目及影响金额。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：调整分录借贷平衡、依据充分、已发布至审定表并推送错报汇总。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjustment.vue — H3-3 调整分录
 * el-table 10列+借贷平衡+推送A13
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3Adjustment } from '../../composables/useH3Adjustment'
import { useH3FormData } from '../../composables/useH3FormData'
import { H3_ASSET_CATEGORIES } from '../../composables/h3CategoryMap'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: computed(() => 'cost') as any,
})

const {
  rows, debitTotal, creditTotal, isBalanced, syncSummary, writeTargets,
  addRow, removeRow, updateCell, publishAdjustment, pushToA13,
} = useH3Adjustment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

function fmtNum(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const categoryPreviewRows = computed(() => {
  const b = syncSummary.value.byCategory
  return H3_ASSET_CATEGORIES.map((category) => ({
    category,
    aje1503: b.aje1503[category] || 0,
    rje1503: b.rje1503[category] || 0,
    aje1504: b.aje1504[category] || 0,
    rje1504: b.rje1504[category] || 0,
    aje1505: b.aje1505[category] || 0,
    rje1505: b.rje1505[category] || 0,
  }))
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-3-audit-note'
const CONCLUSION_KEY = 'H3-3-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}
</script>

<style scoped>
.h3-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.balance-row { display: flex; align-items: center; gap: 16px; margin-top: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.sync-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.sync-note { margin: 8px 0 0; font-size: 12px; color: #909399; line-height: 1.5; }
.nav-chip { cursor: pointer; }
.cat-preview-table { margin-top: 10px; }
</style>
