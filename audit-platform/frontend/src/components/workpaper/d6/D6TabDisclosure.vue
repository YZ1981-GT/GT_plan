<template>
<div class="d6-disclosure">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 合同资产（科目1402）附注依 CAS14 收入准则及 CAS22 减值准则披露，按上市公司版（5子节）/ 国企版（3子节）分别列报。</p>
      <p>2. 表内浅蓝背景单元格为跨sheet自动取数（来源 D6-1 审定表 / D6-3 减值明细 / D6-8 测算），不可手工编辑。</p>
      <p>3. 上市公司版需披露分类构成、减值计提情况、单项与组合明细及计提转回核销变动；国企版仅需披露分类及减值变动。</p>
      <p>4. 各子节说明文本将双向回写至附注模块，请与审定表、减值明细及测算保持勾稽一致。</p>
    </div>
  </details>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-segmented v-if="showListed && showSoe" v-model="activeVariant" :options="variantOptions" size="small" />
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
    </div>
  </div>

  <!-- 上市公司版 -->
  <template v-if="displayVariant === 'listed' && showListed">
    <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <!-- Section 1: 分类 -->
      <template v-if="section.sectionKey === 'listed-1'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" width="200" />
          <el-table-column label="期末账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="期末减值准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endImpairment) }}</span></template>
          </el-table-column>
          <el-table-column label="期末账面价值" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookValue) }}</span></template>
          </el-table-column>
          <el-table-column label="上年账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="上年减值准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorImpairment) }}</span></template>
          </el-table-column>
          <el-table-column label="上年账面价值" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookValue) }}</span></template>
          </el-table-column>
        </el-table>
      </template>

      <!-- Section 2: 减值计提情况 -->
      <template v-else-if="section.sectionKey === 'listed-2'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="类别" width="180" />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="比例%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct(row.endPercentage) }}</template>
          </el-table-column>
          <el-table-column label="减值金额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="损失率%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct100(row.endLossRate) }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- Section 3: 单项明细 -->
      <template v-else-if="section.sectionKey === 'listed-3'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="名称" min-width="160" />
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.balance) }}</span></template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="损失率%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct100(row.lossRate) }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="计提理由" min-width="160" />
        </el-table>
      </template>

      <!-- Section 4: 按组合明细 -->
      <template v-else-if="section.sectionKey === 'listed-4'">
        <div v-for="(group, gIdx) in groupedDetails" :key="gIdx" class="group-block">
          <div class="group-header">
            <el-input
              v-if="!isReadonly"
              :model-value="group.groupName"
              size="small"
              placeholder="组合名称"
              style="width:200px"
              @change="(v: string) => updateGroupName(gIdx, v)"
            />
            <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
            <el-button v-if="!isReadonly" size="small" @click="addGroupedDetailRow(group.groupName)">添加行</el-button>
          </div>
          <el-table :data="group.rows" size="small" border>
            <el-table-column label="账龄" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.label" size="small" @change="(v: string) => updateGroupedCell(gIdx, row.rowId, 'label', v)" />
                <span v-else>{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合同资产" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.balance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'balance', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.balance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.provision" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'provision', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.provision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="损失率%" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'lossRate', v ?? 0)" />
                <span v-else>{{ fmtPct100(row.lossRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="50" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" @click="removeGroupedRow(gIdx, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addGroup">添加组合</el-button>
      </template>

      <!-- Section 5: 计提转回核销 -->
      <template v-else-if="section.sectionKey === 'listed-5'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" width="180" />
          <el-table-column label="本期计提" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="本期转回" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
          </el-table-column>
          <el-table-column label="本期核销" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160" />
        </el-table>
      </template>

      <div class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getListedNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getListedNoteKey(section.sectionKey), v)"
        />
      </div>
    </div>
  </template>

  <!-- 国企版 -->
  <template v-if="displayVariant === 'soe' && showSoe">
    <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <template v-if="section.sectionKey === 'soe-1'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" width="200" />
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorAmount) }}</span></template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="section.sectionKey === 'soe-2'">
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" width="160" />
          <el-table-column label="期初数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="本期计提" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="本期转回" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
          </el-table-column>
          <el-table-column label="本期核销" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
          </el-table-column>
          <el-table-column label="期末数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else>
        <el-empty v-if="!section.rows.length" description="暂无重大变动事项" :image-size="60" />
        <el-table v-else :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" />
        </el-table>
      </template>

      <div class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getSoeNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getSoeNoteKey(section.sectionKey), v)"
        />
      </div>
    </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabDisclosure.vue — 附注披露（上市5子节 / 国企3子节）
 */
import { computed, toRef, type Ref } from 'vue'
import { useD6Disclosure } from '../composables/useD6Disclosure'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
  variant: 'listed' | 'soe'
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const {
  listedSections, soeSections, showListed, showSoe, activeVariant,
  groupedDetails, addGroup, addGroupedDetailRow, updateGroupName, updateGroupedCell, removeGroupedRow,
  noteTexts,
} = useD6Disclosure({
  allResponses: allResponsesRef,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: async () => {},
  debouncedSave: props.debouncedSave,
})

if (props.variant) {
  activeVariant.value = props.variant
}

const displayVariant = computed(() => {
  if (props.variant) return props.variant
  if (showListed.value && !showSoe.value) return 'listed'
  if (showSoe.value && !showListed.value) return 'soe'
  return activeVariant.value
})

const variantOptions = computed(() => {
  const opts = []
  if (showListed.value) opts.push({ label: '上市公司版', value: 'listed' })
  if (showSoe.value) opts.push({ label: '国企版', value: 'soe' })
  return opts
})

const LISTED_NOTE_MAP: Record<string, string> = {
  'listed-1': 'D6-note-listed-text-1',
  'listed-2': 'D6-note-listed-text-2',
  'listed-3': 'D6-note-listed-text-3',
  'listed-4': 'D6-note-listed-text-4',
  'listed-5': 'D6-note-listed-text-5',
}

const SOE_NOTE_MAP: Record<string, string> = {
  'soe-1': 'D6-note-soe-text-1',
  'soe-2': 'D6-note-soe-text-2',
  'soe-3': 'D6-note-soe-text-3',
}

function getListedNoteKey(sectionKey: string): string {
  return LISTED_NOTE_MAP[sectionKey] || ''
}

function getSoeNoteKey(sectionKey: string): string {
  return SOE_NOTE_MAP[sectionKey] || ''
}

function updateNoteText(key: string, value: string) {
  if (!key) return
  noteTexts.value = { ...noteTexts.value, [key]: value }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(rate: number): string {
  if (!rate) return '-'
  return `${(rate * 100).toFixed(1)}%`
}

function fmtPct100(rate: number): string {
  if (!rate) return '-'
  return `${rate.toFixed(2)}%`
}
</script>

<style scoped>
.d6-disclosure { padding: 16px; }
.d6-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.disclosure-card {
  margin-bottom: 24px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; cursor: help; }
.group-block { margin-bottom: 12px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.note-block { margin-top: 12px; }
.note-label { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 6px; }
</style>
