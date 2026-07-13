<template>
  <div class="g1-classification">
    <div class="section-head">
      <h3 class="sheet-title">G1-9 分类适当性检查（SPPI + 业务模式）</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="cls.addRow()">新增投资项目</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ cls.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-9-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价金融资产分类（AC/FVOCI/FVTPL）适当性，核实 SPPI 测试与业务模式判定的合理性，确认分类结论符合 CAS22 要求。"
      class="objective-alert"
    />

    <div class="stats-bar">
      SPPI通过：<b>{{ cls.stats.value.pass }}</b> ·
      不通过：<b class="warn">{{ cls.stats.value.fail }}</b> ·
      分类 FVTPL：{{ cls.stats.value.fvtpl }} / FVOCI：{{ cls.stats.value.fvoci }} / AC：{{ cls.stats.value.ac }}
    </div>

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- SPPI 测试区段 -->
    <el-table v-if="segment === 'sppi'" :data="cls.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in cls.sppiColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :fixed="col.prop === 'investItem' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <el-select
            v-if="col.type === 'sppi-select'"
            v-model="row.sppiResult"
            size="small"
            :disabled="isReadonly"
            @change="cls.updateRow(row.id, { sppiResult: row.sppiResult })"
          >
            <el-option v-for="o in cls.sppiResultOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-input
            v-else
            v-model="row[col.prop]"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            size="small"
            :disabled="isReadonly"
            @change="cls.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="cls.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 业务模式判定区段 -->
    <el-table v-else :data="cls.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in cls.bizModelColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :fixed="col.prop === 'investItem' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <el-select
            v-if="col.type === 'class-select'"
            v-model="row.finalClassification"
            size="small"
            :disabled="isReadonly"
            @change="cls.updateRow(row.id, { finalClassification: row.finalClassification })"
          >
            <el-option v-for="o in cls.finalClassOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-input
            v-else
            v-model="row[col.prop]"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            size="small"
            :disabled="isReadonly"
            @change="cls.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="cls.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）执行的分类适当性程序及结果；（2）SPPI 测试与业务模式判定的关键判断、拟调整/未调整事项及其影响。" />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="cls.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对金融工具分类适当性的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>SPPI 测试判断合同现金流量是否仅为本金和利息，未通过则强制分类为 FVTPL。</li>
        <li>最终分类需结合 SPPI 结果与业务模式共同判定：AC / FVOCI / FVTPL。</li>
        <li>两区段共用投资项目，切换 Tab 时行保持同步。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject, watch } from 'vue'
import { useG1Classification } from '../../composables/useG1Classification'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const cls = useG1Classification({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-9-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const segment = ref<'sppi' | 'bizmodel'>('sppi')
const segmentOptions = [
  { label: 'SPPI测试', value: 'sppi' },
  { label: '业务模式判定', value: 'bizmodel' },
]
</script>

<style scoped>
.g1-classification { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-classification :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-classification :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #f56c6c; }
.segment-bar { margin-bottom: 12px; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
