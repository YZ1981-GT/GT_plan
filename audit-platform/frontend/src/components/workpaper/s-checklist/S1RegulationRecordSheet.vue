<template>
  <div class="s1-regulation-record">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：记录对被审计单位遵守法律法规情况的考虑，识别违反法律法规行为对财务报表的潜在影响及所需的审计应对。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ S1-1 对法律法规的考虑记录表 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S1-1 对法律法规的考虑记录表</span>
          <div class="header-actions">
            <!-- 导入导出（动态行表格 Req 11.3） -->
            <el-dropdown v-if="!isReadonly" trigger="click" size="small">
              <el-button size="small" :loading="isExporting || isImporting">
                导入导出 ▾
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                  <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                  <el-dropdown-item>
                    <el-upload
                      :show-file-list="false"
                      accept=".xlsx"
                      :auto-upload="false"
                      :disabled="isImporting"
                      @change="handleImportChange"
                    >
                      <span>导入数据</span>
                    </el-upload>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s1-regulation', 'S1-1法律法规记录表')">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示 -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本记录表用于记录审计人员对被审计单位所适用法律法规的识别与考虑。</p>
          <p>应关注对财务报表有直接影响的法律法规（如税法、会计准则），以及对经营有重大影响但违反可能对财务报表产生重大影响的法律法规。</p>
          <p>结构：95×10，包含法规名称/适用性/影响评估/不合规后果/审计程序/索引。</p>
        </div>
      </details>

      <!-- 法规记录表 -->
      <el-table
        :data="regulationRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        row-key="id"
        :cell-class-name="cellClassName"
      >
        <el-table-column type="index" label="序号" width="55" align="center" />

        <el-table-column prop="category" label="法规类别" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              placeholder="选择"
              @change="markDirty"
            >
              <el-option label="直接影响" value="direct" />
              <el-option label="间接影响" value="indirect" />
              <el-option label="行业特有" value="industry" />
            </el-select>
            <el-tag v-else :type="categoryTagType(row.category)" size="small">
              {{ categoryLabel(row.category) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="lawName" label="法律法规名称" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.lawName"
              size="small"
              placeholder="法规名称"
              @change="markDirty"
            />
            <span v-else>{{ row.lawName || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="applicable" label="是否适用" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.applicable"
              size="small"
              placeholder="—"
              @change="markDirty"
            >
              <el-option label="适用" value="yes" />
              <el-option label="不适用" value="no" />
              <el-option label="待确认" value="pending" />
            </el-select>
            <el-tag v-else :type="row.applicable === 'yes' ? 'success' : row.applicable === 'no' ? 'info' : 'warning'" size="small">
              {{ row.applicable === 'yes' ? '适用' : row.applicable === 'no' ? '不适用' : '待确认' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="impactAssessment" label="对财务报表的影响" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.impactAssessment"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="评估不合规对财务报表的潜在影响"
              @change="markDirty"
            />
            <span v-else>{{ row.impactAssessment || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="consequence" label="不合规后果" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.consequence"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="罚款/吊销/刑事等"
              @change="markDirty"
            />
            <span v-else>{{ row.consequence || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="auditProcedure" label="已执行审计程序" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.auditProcedure"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="询问/检查/观察等"
              @change="markDirty"
            />
            <span v-else>{{ row.auditProcedure || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="conclusion" label="结论" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.conclusion"
              size="small"
              placeholder="—"
              @change="markDirty"
            >
              <el-option label="合规" value="compliant" />
              <el-option label="不合规" value="non-compliant" />
              <el-option label="未发现" value="not-found" />
            </el-select>
            <el-tag v-else :type="row.conclusion === 'compliant' ? 'success' : row.conclusion === 'non-compliant' ? 'danger' : 'info'" size="small">
              {{ row.conclusion === 'compliant' ? '合规' : row.conclusion === 'non-compliant' ? '不合规' : '未发现' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="indexRef" label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <span v-else class="text-placeholder">—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 动态行操作 -->
      <div v-if="!isReadonly" class="row-actions">
        <el-button size="small" type="primary" plain @click="addRow">+ 新增法规</el-button>
      </div>
    </el-card>

    <!-- ═══ 总体评价 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>总体评价</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对被审计单位遵守适用法律法规情况的总体评价..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S1RegulationRecordSheet.vue — S1-1 对法律法规的考虑记录表
 *
 * 功能：
 * - 95×10 法规考虑记录结构
 * - 法规类别（直接影响/间接影响/行业特有）下拉选择
 * - 适用性判断 + 影响评估 + 不合规后果 + 已执行程序 + 结论
 * - 动态行：可新增法规记录
 * - GtIndexChip 索引跳转
 * - readonly 禁止编辑
 * - 13px 字体 + AI 辅助
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.3
 * Requirements: 8.2
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useSSpecialImportExport } from '../composables/useSSpecialImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 导入导出（Req 11.3） ────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const { isExporting, isImporting, exportTemplate, exportData, importData } =
  useSSpecialImportExport({ wpId: wpIdRef })

function handleExportTemplate() {
  exportTemplate('S1-1')
}

function handleExportData() {
  exportData('S1-1')
}

async function handleImportChange(f: { raw?: File } | File) {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  const result = await importData('S1-1', file)
  if (result?.success) {
    loadData()
  }
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface RegulationRow {
  id: string
  category: string
  lawName: string
  applicable: string
  impactAssessment: string
  consequence: string
  auditProcedure: string
  conclusion: string
  indexRef: string
}

const regulationRows = ref<RegulationRow[]>([])
const overallConclusion = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── 默认检查项 ─────────────────────────────────────────────────────────────

const DEFAULT_ROWS: Partial<RegulationRow>[] = [
  { category: 'direct', lawName: '《企业会计准则》及其应用指南', applicable: 'yes' },
  { category: 'direct', lawName: '《中华人民共和国税收征收管理法》', applicable: 'yes' },
  { category: 'direct', lawName: '《中华人民共和国企业所得税法》', applicable: 'yes' },
  { category: 'direct', lawName: '《中华人民共和国增值税暂行条例》', applicable: 'yes' },
  { category: 'direct', lawName: '《中华人民共和国公司法》', applicable: 'yes' },
  { category: 'direct', lawName: '《中华人民共和国证券法》（上市公司适用）', applicable: 'pending' },
  { category: 'indirect', lawName: '《中华人民共和国劳动合同法》', applicable: 'yes' },
  { category: 'indirect', lawName: '《中华人民共和国环境保护法》', applicable: 'pending' },
  { category: 'indirect', lawName: '《中华人民共和国安全生产法》', applicable: 'pending' },
  { category: 'industry', lawName: '（根据被审计单位所属行业补充）', applicable: 'pending' },
]

// ─── 辅助函数 ────────────────────────────────────────────────────────────────

function categoryLabel(cat: string): string {
  return cat === 'direct' ? '直接影响' : cat === 'indirect' ? '间接影响' : cat === 'industry' ? '行业特有' : '—'
}

function categoryTagType(cat: string): '' | 'success' | 'warning' | 'info' {
  return cat === 'direct' ? '' : cat === 'indirect' ? 'warning' : 'info'
}

function markDirty() {
  isDirty.value = true
}

function cellClassName({ column }: any) {
  if (column.label === '结论') return 'conclusion-cell'
  return ''
}

function addRow() {
  const idx = regulationRows.value.length
  regulationRows.value.push({
    id: `s1-1-${idx}`,
    category: '',
    lawName: '',
    applicable: 'pending',
    impactAssessment: '',
    consequence: '',
    auditProcedure: '',
    conclusion: '',
    indexRef: '',
  })
  markDirty()
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将根据被审计单位行业自动推荐适用法规清单')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据法规考虑记录自动生成总体评价')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (saving.value) return
  saving.value = true
  try {
    const payload = {
      regulation_rows: regulationRows.value.map(r => ({
        id: r.id,
        category: r.category,
        law_name: r.lawName,
        applicable: r.applicable,
        impact_assessment: r.impactAssessment,
        consequence: r.consequence,
        audit_procedure: r.auditProcedure,
        conclusion: r.conclusion,
        index_ref: r.indexRef,
      })),
      overall_conclusion: overallConclusion.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { sheet_name: 'S1-1对法律法规的考虑记录表', data: payload }
    )
    isDirty.value = false
    ElMessage.success('法律法规记录表已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 加载 ────────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { _silent: true } as any
    )
    const sheets = res?.data?.sheets || res?.sheets || []
    const sheet = sheets.find((s: any) =>
      s.sheet_name?.includes('S1-1') || s.sheet_name?.includes('法律法规的考虑记录')
    )
    const htmlData = sheet?.html_data

    if (htmlData?.regulation_rows?.length) {
      regulationRows.value = htmlData.regulation_rows.map((r: any, idx: number) => ({
        id: r.id || `s1-1-${idx}`,
        category: r.category || '',
        lawName: r.law_name || r.lawName || '',
        applicable: r.applicable || 'pending',
        impactAssessment: r.impact_assessment || r.impactAssessment || '',
        consequence: r.consequence || '',
        auditProcedure: r.audit_procedure || r.auditProcedure || '',
        conclusion: r.conclusion || '',
        indexRef: r.index_ref || r.indexRef || '',
      }))
    } else {
      regulationRows.value = DEFAULT_ROWS.map((r, idx) => ({
        id: `s1-1-${idx}`,
        category: r.category || '',
        lawName: r.lawName || '',
        applicable: r.applicable || 'pending',
        impactAssessment: '',
        consequence: '',
        auditProcedure: '',
        conclusion: '',
        indexRef: '',
      }))
    }

    if (htmlData?.overall_conclusion) {
      overallConclusion.value = htmlData.overall_conclusion
    }
  } catch {
    regulationRows.value = DEFAULT_ROWS.map((r, idx) => ({
      id: `s1-1-${idx}`,
      category: r.category || '',
      lawName: r.lawName || '',
      applicable: r.applicable || 'pending',
      impactAssessment: '',
      consequence: '',
      auditProcedure: '',
      conclusion: '',
      indexRef: '',
    }))
  }
}

onMounted(() => { loadData() })
</script>

<style scoped>
.s1-regulation-record { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.compile-hint { margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.compile-hint summary { cursor: pointer; color: #909399; font-size: 12px; margin-bottom: 8px; }
.methodology-context { padding: 10px 14px; border-left: 4px solid #e6a23c; background-color: #fdf6ec; font-size: var(--wp-font-size, 13px); line-height: 1.7; color: #606266; }
.methodology-context p { margin: 4px 0; }
.row-actions { margin-top: 12px; }
.text-placeholder { color: #c0c4cc; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.conclusion-cell) { text-align: center; }
</style>
