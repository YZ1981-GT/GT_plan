<template>
  <div class="g10-derivative" data-testid="g10-derivative-check">
    <div class="methodology">
      衍生金融工具五要素(CAS22)：价值随特定变量变动 · 不要求/极少初始净投资 · 未来日期结算 · 固定或可确定金额交换 · 可净额结算
    </div>
    <div class="toolbar">
      <h3>G10-8 衍生金融工具核查（{{ dc.rows.value.length }} 行 · 5 区段）</h3>
      <el-tag v-if="dc.missingCompliance.value.length" type="danger" size="small">
        待填合规 {{ dc.missingCompliance.value.length }} 行
      </el-tag>
      <GtReviewTrigger section-id="G10-8-derivative" />
    </div>

    <div v-if="dc.useVirtualScroll.value" class="virtual-toolbar">
      <el-alert type="info" :closable="false">行数较多（{{ dc.rows.value.length }} 行）· 虚拟滚动速览模式</el-alert>
    </div>

    <el-table-v2
      v-if="dc.useVirtualScroll.value && browseMode"
      :columns="virtualColumns"
      :data="dc.rows.value"
      :width="tableWidth"
      :height="480"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
      data-testid="g10-derivative-virtual-table"
    />

    <el-collapse v-else v-model="expandedSections" class="sections">
      <el-collapse-item v-for="sec in dc.sections.value" :key="sec.title" :name="sec.title">
        <template #title>
          <span class="sec-title">{{ sec.title }}</span>
          <el-tag size="small" type="info" style="margin-left:8px">{{ sec.rows.length }} 项</el-tag>
          <el-button size="small" link :loading="dc.aiLoading.value" :disabled="isReadonly"
            @click.stop="dc.generateAiConclusion()">🤖 AI</el-button>
        </template>
        <el-table :data="sec.rows" border size="small" style="font-size:13px">
          <el-table-column label="#" prop="seq" width="44" />
          <el-table-column label="检查区域" prop="checkArea" width="100" show-overflow-tooltip />
          <el-table-column label="检查项目" prop="checkItem" min-width="130" show-overflow-tooltip />
          <el-table-column label="审计要求" prop="auditRequirement" min-width="110" show-overflow-tooltip />
          <el-table-column label="检查结果" min-width="110">
            <template #default="{ row }">
              <el-input v-model="row.checkResult" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'checkResult', row.checkResult)" />
            </template>
          </el-table-column>
          <el-table-column label="是否合规" width="110">
            <template #default="{ row }">
              <el-select v-model="row.compliance" size="small" :disabled="isReadonly"
                @change="(v: string) => dc.updateCell(row.rowId, 'compliance', v)">
                <el-option v-for="o in G10_COMPLIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="风险等级" width="100">
            <template #default="{ row }">
              <el-select v-model="row.riskLevel" size="small" :disabled="isReadonly"
                @change="(v: string) => dc.updateCell(row.rowId, 'riskLevel', v)">
                <el-option v-for="o in G10_RISK_LEVEL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="审计结论" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.auditConclusion" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'auditConclusion', row.auditConclusion)" />
            </template>
          </el-table-column>
          <el-table-column label="索引" width="72">
            <template #default="{ row }">
              <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'indexRef', row.indexRef)" />
            </template>
          </el-table-column>
          <el-table-column label="备注" width="80">
            <template #default="{ row }">
              <el-input v-model="row.remark" size="small" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'remark', row.remark)" />
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <div v-if="dc.useVirtualScroll.value" class="mode-toggle">
      <el-button size="small" @click="browseMode = !browseMode">{{ browseMode ? '切换分区编辑' : '切换虚拟速览' }}</el-button>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>综合审计结论</span>
          <el-button size="small" :loading="dc.aiLoading.value" :disabled="isReadonly" @click="dc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="dc.overallConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dc.updateOverallConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <p>五区段问卷覆盖衍生工具定义、嵌入衍生、公允价值、套期关系及披露完整性。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, h } from 'vue'
import type { Column } from 'element-plus'
import { useG10DerivativeCheck } from '../../composables/useG10DerivativeCheck'
import { G10_COMPLIANCE_OPTIONS, G10_RISK_LEVEL_OPTIONS } from '../../composables/g10Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dc = useG10DerivativeCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
})

const expandedSections = ref<string[]>([])
const browseMode = ref(true)
const tableWidth = 1100

const virtualColumns = computed<Column<any>[]>(() => [
  { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
  { key: 'sectionTitle', title: '区段', dataKey: 'sectionTitle', width: 140 },
  { key: 'checkItem', title: '检查项目', dataKey: 'checkItem', width: 200 },
  { key: 'checkResult', title: '检查结果', dataKey: 'checkResult', width: 160 },
  { key: 'compliance', title: '合规', dataKey: 'compliance', width: 88 },
  { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 72 },
])
</script>

<style scoped>
.g10-derivative { font-size: var(--wp-font-size, 13px); padding: 4px; }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.sec-title { font-weight: 600; }
.virtual-toolbar { margin-bottom: 8px; }
.mode-toggle { margin: 8px 0; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
</style>
