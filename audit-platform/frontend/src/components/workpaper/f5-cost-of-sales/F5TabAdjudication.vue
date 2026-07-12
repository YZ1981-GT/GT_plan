<template>
  <div class="f5-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表反映营业成本（科目6401）审定过程，损益类只有"本期/上期"发生额对比，无期初期末概念。</p>
        <p>2. "未审数"取自试算平衡表，AJE(账项调整)/RJE(重分类)取自 F5-4 调整分录；审定 = 未审 + AJE + RJE。</p>
        <p>3. 主营业务成本与其他业务成本分区列示并自动生成小计，全表合计应与试算平衡表 6401 发生额核对一致。</p>
        <p>4. 审定完成后点击"发布审定数"回写试算表，同时供 F5-7 成本倒轧表校验区消费（与收入配比、毛利分析）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实营业成本各成本项目本期发生额的完整与准确，确认成本结转口径恰当，为利润表营业成本列报及毛利分析提供审定依据。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-hint">损益类 6401 · 本期/上期对比</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-4" :context-project-id="projectIdStr" /></span>
        <el-tag size="small" type="info">共 {{ dataRowCount }} 行</el-tag>
      </div>
    </div>

    <el-table :data="tableData" size="small" border stripe :row-class-name="rowClass" max-height="560">
      <el-table-column label="项目" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'group'">
            <span class="f5-adj-group">{{ row.label }}</span>
            <el-button v-if="!isReadonly && row.group" size="small" type="primary" link
              @click="promptAddRow(row.group)">+ 品种</el-button>
          </template>
          <template v-else-if="row.__type === 'data'">
            <el-input v-if="!row.isFixed && !isReadonly" v-model="row.label" size="small"
              @change="(v: string) => adj.updateCell(row.group, row.rowKey, 'label', v)" />
            <span v-else>{{ row.label }}</span>
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
          </template>
          <span v-else class="f5-adj-subtotal">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 本期 -->
      <el-table-column label="本期" align="center">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentUnadjusted" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentUnadjusted', v)" />
            <span v-else-if="row.currentUnadjusted != null">{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整(AJE)" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentAje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentAje', v)" />
            <span v-else-if="row.currentAje != null">{{ fmt(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类(RJE)" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentRje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentRje', v)" />
            <span v-else-if="row.currentRje != null">{{ fmt(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.currentAdjusted != null" class="f5-formula" title="审定 = 未审 + AJE + RJE">
              {{ fmt(row.currentAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 上期 -->
      <el-table-column label="上期" align="center">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorUnadjusted" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorUnadjusted', v)" />
            <span v-else-if="row.priorUnadjusted != null">{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="90" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorAje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorAje', v)" />
            <span v-else-if="row.priorAje != null">{{ fmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="90" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorRje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorRje', v)" />
            <span v-else-if="row.priorRje != null">{{ fmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.priorAdjusted != null" class="f5-formula" title="审定 = 未审 + AJE + RJE">
              {{ fmt(row.priorAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.changeAmount != null" class="f5-formula" title="变动额 = 本期审定 - 上期审定">
            {{ fmt(row.changeAmount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm v-if="row.__type === 'data' && !row.isFixed" title="确认删除？"
            @confirm="adj.removeRow(row.group, row.rowKey)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 核对行：与试算平衡表核对（科目6401） -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目6401发生额）：</span>
      <el-input v-if="!isReadonly" v-model.number="tbInput" size="small" style="width: 160px"
        @change="onTbChange" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <el-tag v-if="Math.abs(adj.variance.value) > 0.01" type="danger" size="small">
        差异（审定-试算）{{ fmt(adj.variance.value) }}
      </el-tag>
      <el-tag v-else type="success" size="small">核对一致</el-tag>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">
        发布审定数（回写TB）
      </el-button>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" />
            <GtIndexChip value="wp:F5-7" :context-project-id="projectIdStr" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <el-button size="small" @click="openReview">💬</el-button>
        </div>
        <el-input v-model="adj.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly" placeholder="营业成本审定说明（如成本结转口径、量本核对、与收入配比、月度波动原因等）..." />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
        </div>
        <el-input v-model="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly" placeholder="审计结论..." />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabAdjudication.vue — F5-1 审定表（损益类 6401 营业成本）
 * 主营品种行+小计 + 其他品种行+小计 + 总计+TB数+差异
 * 动态品种行增删(ElMessageBox.prompt) + GtIndexChip + EventBus发布
 */
import { ref, computed, inject, toRef, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useF5Adjudication } from '../composables/useF5Adjudication'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯值；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const adj = useF5Adjudication({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const tbInput = ref(adj.trialBalanceAmount.value)
watch(adj.trialBalanceAmount, (v) => { tbInput.value = v })

/** GtIndexChip 上下文项目 id */
const projectIdStr = computed(() => props.projectId)
/** 工具栏"共 N 行"统计（主营 + 其他品种行） */
const dataRowCount = computed(() => adj.mainBusinessRows.value.length + adj.otherBusinessRows.value.length)

function onTbChange() {
  adj.updateTrialBalance(tbInput.value)
}

/** 组装表格行（分组标题 + 数据行 + 小计 + 总计） */
const tableData = computed(() => {
  const rows: any[] = []
  rows.push({ __type: 'group', label: '主营业务成本', group: 'main' })
  for (const r of adj.mainBusinessRows.value) rows.push({ __type: 'data', group: 'main', ...r })
  rows.push({ __type: 'subtotal', ...adj.mainSubtotal.value })
  rows.push({ __type: 'group', label: '其他业务成本', group: 'other' })
  for (const r of adj.otherBusinessRows.value) rows.push({ __type: 'data', group: 'other', ...r })
  rows.push({ __type: 'subtotal', ...adj.otherSubtotal.value })
  rows.push({ __type: 'subtotal', ...adj.grandTotal.value })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'group') return 'f5-row-group'
  if (row.__type === 'subtotal') return 'f5-row-subtotal'
  return ''
}

async function promptAddRow(group: 'main' | 'other') {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '品种名称不能为空',
    })
    if (value) adj.addRow(group, value.trim())
  } catch { /* 用户取消 */ }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function openReview() {
  openReviewDialog('F5-1-conclusion')
}
</script>

<style scoped>
.f5-adjudication { padding: 12px; }
.f5-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.toolbar-hint { font-size: var(--wp-font-size, 13px); color: #909399; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 表格 */
.f5-adj-group { font-weight: 600; color: #409eff; margin-right: 8px; }
.f5-adj-subtotal { font-weight: 700; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.f5-row-group) { background: #ecf5ff; }
:deep(.f5-row-subtotal) { background: #f5f7fa; font-weight: 700; }

/* 核对行 */
.tb-check-row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin: 12px 0; font-size: var(--wp-font-size, 13px); flex-wrap: wrap; }
.tb-label { color: #909399; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
</style>
