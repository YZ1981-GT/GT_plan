<template>
  <!--
    ReportMappingDialog — 转换规则（映射）弹窗
    从 ReportDialogs.vue 拆分（report-view-slimdown tech debt #3）
  -->

  <!-- 转换规则弹窗 -->
  <el-dialog append-to-body :model-value="showMappingDialog" title="国企版 ↔ 上市版 转换规则" width="950px" top="3vh" @update:model-value="$emit('update:showMappingDialog', $event)">
    <div class="gt-rv-mapping-dialog">
      <p style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); margin: 0 0 10px;">
        配置国企版与上市版各报表项目的映射关系。确认后系统将按规则自动转换，转换结果缓存到数据库。
      </p>
      <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap;">
        <el-button size="small" @click="$emit('mapping-load-preset')" :loading="mappingLoading">一键加载全部预设</el-button>
        <el-button size="small" type="primary" @click="$emit('mapping-save')" :loading="mappingLoading">保存全部规则</el-button>
        <SharedTemplatePicker
          config-type="report_mapping"
          :project-id="projectId"
          :get-config-data="getMappingConfigData"
          @applied="(data: Record<string, any>) => $emit('mapping-template-applied', data)"
        />
        <span style="flex:1" />
        <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); line-height: 28px;">
          总计已映射 {{ totalMappedCount }} / {{ totalRuleCount }} 项
        </span>
      </div>
      <el-tabs :model-value="mappingTab" type="card" size="small" @update:model-value="$emit('update:mappingTab', $event as string)">
        <el-tab-pane v-for="rt in mappingReportTypes" :key="rt.key" :label="rt.label" :name="rt.key" />
      </el-tabs>
      <el-table :data="currentMappingRules" border size="small" max-height="420" style="width: 100%">
        <el-table-column label="国企版项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.soe_row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="编码" width="110" align="center">
          <template #default="{ row }">
            <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">{{ row.soe_row_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="→" width="30" align="center">
          <template #default><span style="color: var(--gt-color-text-placeholder);">→</span></template>
        </el-table-column>
        <el-table-column label="上市版项目" min-width="220">
          <template #default="{ row }">
            <el-select v-model="row.listed_row_code" size="small" filterable clearable placeholder="选择" style="width: 100%;">
              <el-option v-for="opt in currentListedOptions" :key="opt.code" :label="opt.name" :value="opt.code">
                <span style="font-size: var(--gt-font-size-xs);">{{ opt.code }} {{ opt.name }}</span>
              </el-option>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.listed_row_code" style="color: var(--gt-color-success); font-size: var(--gt-font-size-xs);">✓</span>
            <span v-else style="color: var(--gt-color-coral); font-size: var(--gt-font-size-xs);">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 8px; text-align: right; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">
        {{ mappingTabLabel }} 已映射 {{ currentMappingRules.filter((r: any) => r.listed_row_code).length }} / {{ currentMappingRules.length }} 项
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'

// ─── Props ──────────────────────────────────────────────────────────────────
defineProps<{
  showMappingDialog: boolean
  mappingLoading: boolean
  mappingTab: string
  mappingReportTypes: { key: string; label: string }[]
  currentMappingRules: any[]
  currentListedOptions: any[]
  totalMappedCount: number
  totalRuleCount: number
  mappingTabLabel: string
  getMappingConfigData: () => Record<string, any>
  projectId: string
}>()

// ─── Emits ──────────────────────────────────────────────────────────────────
defineEmits<{
  (e: 'update:showMappingDialog', val: boolean): void
  (e: 'update:mappingTab', val: string): void
  (e: 'mapping-load-preset'): void
  (e: 'mapping-save'): void
  (e: 'mapping-template-applied', data: Record<string, any>): void
}>()
</script>
