<template>
<div class="d7-disclosure">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 上市/国企版切换 -->
    <div class="variant-toolbar">
      <el-segmented v-model="activeVariant" :options="variantOptions" size="small" />
    </div>

    <!-- 上市公司版 -->
    <template v-if="activeVariant === 'listed'">
      <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="card-title">{{ section.label }}</h4>

        <el-table :data="getSectionDisplayData(section)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <span :class="{ 'label-bold': row.rowId.startsWith('__') }">
                {{ row.label }}
                <el-tooltip v-if="!section.isDynamic && !row.rowId.startsWith('__')" content="跨sheet取数（来源：D7-1审定表）" placement="top">
                  <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.prior" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'prior', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.prior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.current" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'current', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.current) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="section.isDynamic && !isReadonly" label="" width="60" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.rowId.startsWith('__')" type="danger" text size="small" @click="removeDynamicRow(section.sectionKey, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="section.isDynamic && !isReadonly" style="margin-top:8px">
          <el-button size="small" @click="addDynamicRow(section.sectionKey)">添加行</el-button>
        </div>

        <!-- 说明textarea -->
        <div class="note-textarea">
          <label>说明：</label>
          <el-input
            :model-value="noteTexts[getNoteKey(section.sectionKey)]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="补充披露说明..."
            @change="(v: string) => updateNoteText(getNoteKey(section.sectionKey), v)"
          />
        </div>

        <!-- 编制提示 -->
        <details class="editing-hints">
          <summary>📋 编制提示</summary>
          <div class="hints-content">
            <p v-if="section.sectionKey === 'listed-1'">从D7-1审定表自动取数，确认性质分类合计与审定数一致。<GtIndexChip wp-code="D7-1" label="→D7-1" /></p>
            <p v-else-if="section.sectionKey === 'listed-2'">列示账龄超过1年的重要合同负债，说明未转收原因。</p>
            <p v-else>列示本期账面价值发生重大变动的合同负债事项。</p>
          </div>
        </details>
      </div>
    </template>

    <!-- 国企版 -->
    <template v-if="activeVariant === 'soe'">
      <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="card-title">{{ section.label }}</h4>

        <el-table :data="getSectionDisplayData(section)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <span :class="{ 'label-bold': row.rowId.startsWith('__') }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.prior" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'prior', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.prior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.current" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'current', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.current) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="section.isDynamic && !isReadonly" label="" width="60" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.rowId.startsWith('__')" type="danger" text size="small" @click="removeDynamicRow(section.sectionKey, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="section.isDynamic && !isReadonly" style="margin-top:8px">
          <el-button size="small" @click="addDynamicRow(section.sectionKey)">添加行</el-button>
        </div>

        <div class="note-textarea">
          <label>说明：</label>
          <el-input
            :model-value="noteTexts[getNoteKey(section.sectionKey)]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="补充披露说明..."
            @change="(v: string) => updateNoteText(getNoteKey(section.sectionKey), v)"
          />
        </div>
      </div>
    </template>
  </template>

  <div v-else class="oo-mode-placeholder">
    <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabDisclosure.vue — 附注披露 (~350行)
 * el-segmented: 上市公司版(3子节) / 国企版(2子节)
 * Task: 23.1
 * Requirements: 13.1-13.8, 14.1-14.6, 15.1-15.6, 19.5, 20.1
 */
import { ref, computed, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { useD7Disclosure, type DisclosureSection, type DisclosureRow } from '../composables/useD7Disclosure'
import type { ChecklistResponse } from '../composables/useD7FormData'
import type useD7CrossSheet from '../composables/useD7CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD7CrossSheet>
  variant?: 'listed' | 'soe'
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

const variantOptions = [
  { label: '上市公司版', value: 'listed' },
  { label: '国企版', value: 'soe' },
]

const {
  listedSections, soeSections,
  activeVariant, addDynamicRow, removeDynamicRow, noteTexts,
} = useD7Disclosure({
  allResponses: props.allResponses,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: async () => {},
  debouncedSave: props.debouncedSave,
})

// Initialize variant from prop if provided
if (props.variant) {
  activeVariant.value = props.variant
}

function getSectionDisplayData(section: DisclosureSection): DisclosureRow[] {
  if (section.totalRow) {
    return [...section.rows, section.totalRow]
  }
  return section.rows
}

function updateDynamicRow(sectionKey: string, rowId: string, field: string, value: number) {
  // Find the section and update inline
  const sections = activeVariant.value === 'listed' ? listedSections.value : soeSections.value
  const section = sections.find(s => s.sectionKey === sectionKey)
  if (!section) return
  const row = section.rows.find(r => r.rowId === rowId)
  if (row) {
    ;(row as any)[field] = value
    // Trigger persist by re-adding (composable handles persistence)
  }
}

function getNoteKey(sectionKey: string): string {
  const map: Record<string, string> = {
    'listed-1': 'D7-note-listed-text-1',
    'listed-2': 'D7-note-listed-text-2',
    'listed-3': 'D7-note-listed-text-3',
    'soe-1': 'D7-note-soe-text-1',
    'soe-2': 'D7-note-soe-text-2',
  }
  return map[sectionKey] || ''
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
</script>

<style scoped>
.d7-disclosure { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.variant-toolbar { margin-bottom: 16px; }
.oo-mode-placeholder { padding: 40px 0; }

.disclosure-card {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.label-bold { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }

.note-textarea { margin-top: 12px; }
.note-textarea label { font-size: 13px; color: #606266; display: block; margin-bottom: 4px; }

.editing-hints {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}
.editing-hints summary { padding: 8px 12px; cursor: pointer; font-size: 12px; color: #409eff; }
.hints-content { padding: 0 12px 10px; font-size: 12px; color: #606266; line-height: 1.6; }
.hints-content p { margin: 0; }
</style>
