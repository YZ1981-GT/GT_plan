<template>
  <div class="f2-undisclosed">
    <header class="sheet-header">
      <div>
        <h3>识别未披露的关联方</h3>
        <span class="code">F2-67</span>
      </div>
      <div class="stat-row">
        <el-tag>共 {{ up.riskSummary.value.total }} 家</el-tag>
        <el-tag v-if="up.riskSummary.value.high" type="danger">高风险 {{ up.riskSummary.value.high }}</el-tag>
        <el-tag v-if="up.riskSummary.value.undisclosed" type="warning">未披露 {{ up.riskSummary.value.undisclosed }}</el-tag>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="up.addRow()">+ 新增</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-67"
        :disabled="isReadonly"
        ai-section="related-party-conclusion"
        :existing-content="up.auditNote.value"
        review-section="F2-67-undisclosed"
        @ai-filled="(t: string) => { up.auditNote.value = t }"
      />
      <el-input v-model="up.searchQuery.value" size="small" placeholder="搜索供应商/信用代码" clearable class="search" />
      <el-segmented v-model="up.activeSegment.value" :options="segments" size="small" />
    </div>

    <el-table
      :data="up.filteredRows.value"
      border size="small" max-height="460"
      :row-class-name="rowClass"
    >
      <el-table-column type="index" width="50" fixed />
      <el-table-column label="供应商名称" width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supplierName" size="small"
            @change="(v: string) => up.updateRow(row.id, { supplierName: v })" />
          <span v-else>{{ row.supplierName }}</span>
        </template>
      </el-table-column>

      <template v-if="up.activeSegment.value === 'basic'">
        <el-table-column label="统一社会信用代码" width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.creditCode" size="small"
              @change="(v: string) => up.updateRow(row.id, { creditCode: v })" />
            <span v-else>{{ row.creditCode }}</span>
          </template>
        </el-table-column>
        <el-table-column label="法定代表人" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.legalRep" size="small"
              @change="(v: string) => up.updateRow(row.id, { legalRep: v })" />
            <span v-else>{{ row.legalRep }}</span>
          </template>
        </el-table-column>
        <el-table-column label="股东信息" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.shareholderInfo" size="small"
              @change="(v: string) => up.updateRow(row.id, { shareholderInfo: v })" />
            <span v-else>{{ row.shareholderInfo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="注册地址" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.registeredAddress" size="small"
              @change="(v: string) => up.updateRow(row.id, { registeredAddress: v })" />
            <span v-else>{{ row.registeredAddress }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成立日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.regDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width: 100%"
              @update:model-value="(v: string) => up.updateRow(row.id, { regDate: v ?? '' })" />
            <span v-else>{{ row.regDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="注册资本" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.registeredCapital" size="small"
              @change="(v: string) => up.updateRow(row.id, { registeredCapital: v })" />
            <span v-else>{{ row.registeredCapital }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="up.activeSegment.value === 'relation'">
        <el-table-column label="实际控制人" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.actualController" size="small"
              @change="(v: string) => up.updateRow(row.id, { actualController: v })" />
            <span v-else>{{ row.actualController }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与客户关联关系" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.relationToClient" size="small"
              @change="(v: string) => up.updateRow(row.id, { relationToClient: v })" />
            <span v-else>{{ row.relationToClient }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联类型" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.relationType || undefined" size="small" clearable
              @change="(v: string) => up.updateRow(row.id, { relationType: v })">
              <el-option v-for="t in up.RELATION_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.relationType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否已披露" width="105">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isDisclosed || undefined" size="small" clearable
              @change="(v: '是'|'否') => up.updateRow(row.id, { isDisclosed: v })">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isDisclosed }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="核查来源" min-width="180">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.checkSources" size="small" multiple collapse-tags
              @change="(v: string[]) => up.updateRow(row.id, { checkSources: v })">
              <el-option v-for="s in up.CHECK_SOURCE_OPTIONS" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-else>{{ row.checkSources.join('、') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核查日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.checkDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width: 100%"
              @update:model-value="(v: string) => up.updateRow(row.id, { checkDate: v ?? '' })" />
            <span v-else>{{ row.checkDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核查人员" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.checker" size="small"
              @change="(v: string) => up.updateRow(row.id, { checker: v })" />
            <span v-else>{{ row.checker }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核查结论" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.checkConclusion" size="small"
              @change="(v: string) => up.updateRow(row.id, { checkConclusion: v })" />
            <span v-else>{{ row.checkConclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel || undefined" size="small" clearable
              @change="(v: string) => up.updateRow(row.id, { riskLevel: v })">
              <el-option v-for="l in up.RISK_LEVELS" :key="l" :label="l" :value="l" />
            </el-select>
            <el-tag v-else :type="row.riskLevel === '高' ? 'danger' : 'info'" size="small">{{ row.riskLevel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="跟进措施" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.followUp" size="small"
              @change="(v: string) => up.updateRow(row.id, { followUp: v })" />
            <span v-else>{{ row.followUp }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small"
              @change="(v: string) => up.updateRow(row.id, { indexNo: v })" />
            <span v-else>{{ row.indexNo }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="" width="52" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="up.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>关联方核查结论</h4>
      <el-input v-model="up.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2UndisclosedParty, type EnrichedUndisclosedRow } from '../../composables/useF2UndisclosedParty'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{ wpId?: string; allResponses: Map<string, ChecklistResponse>; isReadonly: boolean }>()

const segments = [
  { label: '工商基础', value: 'basic' },
  { label: '关联关系', value: 'relation' },
  { label: '核查审计', value: 'audit' },
]

const up = useF2UndisclosedParty({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function rowClass({ row }: { row: EnrichedUndisclosedRow }): string {
  if (row.highlightLevel === 'red') return 'row-red'
  if (row.highlightLevel === 'orange') return 'row-orange'
  return ''
}
</script>

<style scoped>
.f2-undisclosed { padding: 12px 16px; font-size: 13px; background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.stat-row { display: flex; gap: 6px; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.search { width: 200px; }
:deep(.row-red) { background: #fef0f0 !important; }
:deep(.row-orange) { background: #fdf6ec !important; }
.footer { margin-top: 14px; }
.footer h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
</style>
