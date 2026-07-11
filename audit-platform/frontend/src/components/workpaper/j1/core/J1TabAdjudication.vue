<template>
  <div class="j1-tab-adjudication">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：确认应付职工薪酬各分类期初、期末审定数的准确性，分析本期变动率异常项（&gt;30% 标红），形成审定结论并回写试算平衡表（科目 2211）。
      </template>
    </el-alert>

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="['HTML', 'OnlyOffice']" size="small" />
      <span class="chip-wrap"><GtIndexChip value="wp:J1-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ groups.length }} 组分类</el-tag>
    </div>

    <template v-if="mode === 'HTML'">
      <!-- 各分类分组 -->
      <el-card v-for="group in groups" :key="group.category" shadow="never" class="group-card">
        <template #header>
          <span class="group-title">{{ group.label }}</span>
        </template>
        <el-table :data="[...group.rows, group.subtotal]" border size="small" style="font-size: 13px"
          :row-class-name="({ row }) => row.id?.startsWith('subtotal') ? 'subtotal-row' : ''">
          <el-table-column prop="label" label="项目名称" min-width="160" fixed />
          <el-table-column label="期初数" align="center">
            <el-table-column prop="beginUnadj" label="未审数" width="100" align="right" />
            <el-table-column prop="beginAje" label="调整" width="90" align="right" />
            <el-table-column prop="beginAudited" label="审定数" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="formula-cell" title="期初审定=未审+调整">{{ fmtAmount(row.beginAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column prop="endUnadj" label="未审数" width="100" align="right" />
            <el-table-column prop="endAje" label="调整" width="90" align="right" />
            <el-table-column prop="endAudited" label="审定数" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="formula-cell" title="期末审定=未审+调整">{{ fmtAmount(row.endAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="变动比较" align="center">
            <el-table-column prop="changeDiff" label="变动额" width="100" align="right" />
            <el-table-column label="变动率" width="80" align="right">
              <template #default="{ row }">
                <span :class="{ 'text-danger': Math.abs(row.changeRate) > 30 }">
                  {{ row.changeRate?.toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column prop="analysis" label="原因分析" min-width="120" />
        </el-table>
      </el-card>

      <!-- 合计行 -->
      <el-card shadow="never" class="total-card">
        <div class="total-row">
          <span>应付职工薪酬合计</span>
          <span>期初审定: {{ fmtAmount(grandTotal.beginAudited) }}</span>
          <span>期末审定: {{ fmtAmount(grandTotal.endAudited) }}</span>
          <span :class="{ 'text-danger': Math.abs(grandTotal.changeRate) > 30 }">
            变动率: {{ grandTotal.changeRate?.toFixed(1) }}%
          </span>
        </div>
      </el-card>
    </template>

    <!-- OnlyOffice降级 -->
    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式（审定表J1-1）" />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，审定表按短期薪酬/离职后福利/辞退福利/其他长期福利分组列示。</p>
        <p>2. 灰色底纹列为自动计算列（审定数=未审数+调整），不可手动编辑。</p>
        <p>3. 本期审定数与上期审定数变动率超过 30% 自动标红，须在原因分析栏说明。</p>
        <p>4. 审定合计应与明细表（J1-2）、试算平衡表科目 2211 期末余额勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1Adjudication } from '@/composables/workpaper/j1/useJ1Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const mode = ref('HTML')
const htmlDataRef = ref(props.htmlData || {})
const { groups, grandTotal, initFromHtmlData } = useJ1Adjudication(htmlDataRef)

onMounted(() => {
  if (props.htmlData) initFromHtmlData(props.htmlData)
})

function fmtAmount(val: number | null | undefined): string {
  if (val === null || val === undefined) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.j1-tab-adjudication { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.mode-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.group-card { margin-bottom: 16px; }
.group-title { font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.subtotal-row { background-color: #f5f7fa !important; font-weight: 600; }
.total-card { background: #ecf5ff; }
.total-row { display: flex; gap: 24px; align-items: center; font-weight: 600; }
.text-danger { color: #f56c6c; }
</style>
