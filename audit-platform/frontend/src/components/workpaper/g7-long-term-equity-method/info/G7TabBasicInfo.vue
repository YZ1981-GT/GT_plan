<!--
  G7TabBasicInfo.vue — G7-4 被投资单位基本信息（25列→2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 工商信息(12列): 被投资单位|统一社会信用代码|成立日期|注册资本|实缴资本|注册地|行业|主营业务|法定代表人|控制类型(下拉:合营/联营)|持股比例|投票权比例
  - Tab2: 股权结构+管理层(13列): 被投资单位|其他股东名称|其他股东持股|董事会席位|派出董事|是否有否决权|是否参与决策|重大影响判断依据(textarea)|管理层组成|最新审计报告日|审计意见类型|关联关系|备注

  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  动态行增删：ElMessageBox.prompt输入被投资单位名称（名称唯一性校验）
  导入导出：el-dropdown复用useG7EquityMethodImportExport

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 4.1
  Requirements: 2.1, 2.2
-->
<template>
  <div class="g7-tab-basic-info">
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-4 被投资单位基本信息</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-4-basic-info')">💬复核</el-button>
      </div>
    </div>

    <!-- 2区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 表格（单一实例，列按Tab切换） -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      class="basic-info-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 被投资单位列（始终显示作为锚定列） -->
      <el-table-column label="被投资单位" width="160" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 工商信息(12列，含被投资单位共12) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="统一社会信用代码" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.creditCode" size="small"
              @change="(v: string) => updateField(row.id, 'creditCode', v)" />
            <span v-else>{{ row.creditCode }}</span>
          </template>
        </el-table-column>

        <el-table-column label="成立日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.establishDate" size="small"
              type="date" value-format="YYYY-MM-DD" style="width:100%"
              @update:model-value="(v: string) => updateField(row.id, 'establishDate', v)" />
            <span v-else>{{ row.establishDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="注册资本(万元)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.registeredCapital" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateField(row.id, 'registeredCapital', v)" />
            <span v-else>{{ fmtNum(row.registeredCapital) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="实缴资本(万元)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.paidInCapital" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateField(row.id, 'paidInCapital', v)" />
            <span v-else>{{ fmtNum(row.paidInCapital) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="注册地" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.registeredAddress" size="small"
              @change="(v: string) => updateField(row.id, 'registeredAddress', v)" />
            <span v-else>{{ row.registeredAddress }}</span>
          </template>
        </el-table-column>

        <el-table-column label="行业" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.industry" size="small"
              @change="(v: string) => updateField(row.id, 'industry', v)" />
            <span v-else>{{ row.industry }}</span>
          </template>
        </el-table-column>

        <el-table-column label="主营业务" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.mainBusiness" size="small"
              @change="(v: string) => updateField(row.id, 'mainBusiness', v)" />
            <span v-else>{{ row.mainBusiness }}</span>
          </template>
        </el-table-column>

        <el-table-column label="法定代表人" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.legalRepresentative" size="small"
              @change="(v: string) => updateField(row.id, 'legalRepresentative', v)" />
            <span v-else>{{ row.legalRepresentative }}</span>
          </template>
        </el-table-column>

        <el-table-column label="控制类型" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.controlType" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'controlType', v)">
              <el-option value="合营" label="合营" />
              <el-option value="联营" label="联营" />
            </el-select>
            <span v-else>{{ row.controlType }}</span>
          </template>
        </el-table-column>

        <el-table-column label="持股比例" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.investmentRatio" size="small"
              :controls="false" :precision="4" :step="0.01" :min="0" :max="1" class="compact-num"
              @change="(v: number) => updateField(row.id, 'investmentRatio', v)" />
            <span v-else>{{ fmtPercent(row.investmentRatio) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="投票权比例" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.votingRatio" size="small"
              :controls="false" :precision="4" :step="0.01" :min="0" :max="1" class="compact-num"
              @change="(v: number) => updateField(row.id, 'votingRatio', v)" />
            <span v-else>{{ fmtPercent(row.votingRatio) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 股权结构+管理层(13列，含被投资单位共13) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="其他股东名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.otherShareholderName" size="small"
              @change="(v: string) => updateField(row.id, 'otherShareholderName', v)" />
            <span v-else>{{ row.otherShareholderName }}</span>
          </template>
        </el-table-column>

        <el-table-column label="其他股东持股" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.otherShareholderRatio" size="small"
              :controls="false" :precision="4" :step="0.01" :min="0" :max="1" class="compact-num"
              @change="(v: number) => updateField(row.id, 'otherShareholderRatio', v)" />
            <span v-else>{{ fmtPercent(row.otherShareholderRatio) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="董事会席位" min-width="100" align="center">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.boardSeats" size="small"
              :controls="false" :min="0" class="compact-num"
              @change="(v: number) => updateField(row.id, 'boardSeats', v)" />
            <span v-else>{{ row.boardSeats }}</span>
          </template>
        </el-table-column>

        <el-table-column label="派出董事" min-width="100" align="center">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.appointedDirectors" size="small"
              :controls="false" :min="0" class="compact-num"
              @change="(v: number) => updateField(row.id, 'appointedDirectors', v)" />
            <span v-else>{{ row.appointedDirectors }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否有否决权" min-width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.hasVeto" size="small" style="width:100%"
              @change="(v: boolean) => updateField(row.id, 'hasVeto', v)">
              <el-option :value="true" label="是" />
              <el-option :value="false" label="否" />
            </el-select>
            <span v-else>{{ row.hasVeto ? '是' : '否' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否参与决策" min-width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.participatesInDecision" size="small" style="width:100%"
              @change="(v: boolean) => updateField(row.id, 'participatesInDecision', v)">
              <el-option :value="true" label="是" />
              <el-option :value="false" label="否" />
            </el-select>
            <span v-else>{{ row.participatesInDecision ? '是' : '否' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="重大影响判断依据" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" type="textarea" :model-value="row.significantInfluenceBasis"
              :autosize="{ minRows: 1, maxRows: 3 }" size="small"
              @change="(v: string) => updateField(row.id, 'significantInfluenceBasis', v)" />
            <span v-else class="multiline-cell">{{ row.significantInfluenceBasis }}</span>
          </template>
        </el-table-column>

        <el-table-column label="管理层组成" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.managementComposition" size="small"
              @change="(v: string) => updateField(row.id, 'managementComposition', v)" />
            <span v-else>{{ row.managementComposition }}</span>
          </template>
        </el-table-column>

        <el-table-column label="最新审计报告日" min-width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.latestAuditReportDate" size="small"
              type="date" value-format="YYYY-MM-DD" style="width:100%"
              @update:model-value="(v: string) => updateField(row.id, 'latestAuditReportDate', v)" />
            <span v-else>{{ row.latestAuditReportDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审计意见类型" min-width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.auditOpinionType" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'auditOpinionType', v)">
              <el-option value="无保留意见" label="无保留意见" />
              <el-option value="保留意见" label="保留意见" />
              <el-option value="否定意见" label="否定意见" />
              <el-option value="无法表示意见" label="无法表示意见" />
            </el-select>
            <span v-else>{{ row.auditOpinionType }}</span>
          </template>
        </el-table-column>

        <el-table-column label="关联关系" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.relatedPartyRelation" size="small"
              @change="(v: string) => updateField(row.id, 'relatedPartyRelation', v)" />
            <span v-else>{{ row.relatedPartyRelation }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => updateField(row.id, 'remark', v)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」?`" @confirm="removeRow(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>控制类型仅限"合营"或"联营"（权益法核算范围）</li>
        <li>持股比例和投票权比例填写小数（如0.30代表30%）</li>
        <li>重大影响判断依据应说明持股比例、派出董事、参与决策等情况</li>
        <li>有否决权时需特别关注是否仍构成重大影响</li>
        <li>审计意见类型参照被投资方最近一期审计报告</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabBasicInfo — G7-4 被投资单位基本信息
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 4.1
 *
 * 25列→2区段Tab：
 * - Tab1 工商信息(12列): 含控制类型下拉、持股/投票权比例输入
 * - Tab2 股权结构+管理层(13列): 含textarea重大影响判断依据
 * - 行同步：Tab切换保持当前行索引
 * - 动态行增删：ElMessageBox.prompt 输入被投资单位名称（名称唯一性校验）
 *
 * Requirements: 2.1, 2.2
 */
import { ref, reactive, inject, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { BasicInfoRow } from '../../composables/useG7EquityMethodFormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 2区段Tab ────────────────────────────────────────────────────────────────

type TabKey = 'tab1' | 'tab2'
const activeTab = ref<TabKey>('tab1')

const segmentOptions = [
  { label: '工商信息(12)', value: 'tab1' },
  { label: '股权结构+管理层(13)', value: 'tab2' },
]

// ─── 行同步: selectedRowIndex ────────────────────────────────────────────────

const selectedRowIndex = ref<number>(-1)

function onCurrentChange(row: BasicInfoRow | null) {
  if (row) {
    const idx = rows.findIndex(r => r.id === row.id)
    selectedRowIndex.value = idx
  }
}

// ─── 行数据 ──────────────────────────────────────────────────────────────────

const rows = reactive<BasicInfoRow[]>([])

function createEmptyRow(seq: number, investeeName: string): BasicInfoRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    creditCode: '',
    establishDate: '',
    registeredCapital: 0,
    paidInCapital: 0,
    registeredAddress: '',
    industry: '',
    mainBusiness: '',
    legalRepresentative: '',
    controlType: '联营',
    investmentRatio: 0,
    votingRatio: 0,
    otherShareholderName: '',
    otherShareholderRatio: 0,
    boardSeats: 0,
    appointedDirectors: 0,
    hasVeto: false,
    participatesInDecision: false,
    significantInfluenceBasis: '',
    managementComposition: '',
    latestAuditReportDate: '',
    auditOpinionType: '',
    relatedPartyRelation: '',
    remark: '',
  }
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateField(id: string, field: keyof BasicInfoRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
  }
}

// ─── 动态行增删（ElMessageBox.prompt + 名称唯一性校验） ──────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '被投资单位名称不能为空'
        const exists = rows.some(r => r.investeeName === val.trim())
        if (exists) return `「${val.trim()}」已存在，请勿重复添加`
        return true
      },
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim())
      rows.push(newRow)
      ElMessage.success(`已添加「${value.trim()}」`)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    // 重新排序
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleDropdownCommand(command: string) {
  // 导入导出功能由 useG7EquityMethodImportExport composable 提供
  // 在 Task 9.2 中实现，此处仅提供骨架
  if (command === 'template') {
    ElMessage.info('导出模板功能将在后续集成')
  } else if (command === 'export') {
    ElMessage.info('导出数据功能将在后续集成')
  } else if (command === 'import') {
    ElMessage.info('导入数据功能将在后续集成')
  }
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  rows.length = 0

  const basicData = data.basicInfo || data
  const rawRows = basicData?.rows || []

  if (Array.isArray(rawRows) && rawRows.length > 0) {
    for (let i = 0; i < rawRows.length; i++) {
      const raw = rawRows[i]
      const row: BasicInfoRow = {
        ...createEmptyRow(i + 1, raw.investeeName || raw.investee_name || ''),
        ...raw,
        seq: i + 1,
        id: raw.id || crypto.randomUUID(),
      }
      rows.push(row)
    }
  }
}

/**
 * 导出当前数据（供父组件保存调用）
 */
function getData(): { rows: BasicInfoRow[] } {
  return { rows: [...rows] }
}

defineExpose({ getData, loadFromHtmlData })

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})
</script>

<style scoped>
.g7-tab-basic-info { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.segment-bar { margin-bottom: 12px; }
.basic-info-table { font-size: 13px; }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }
.multiline-cell { white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.4; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
