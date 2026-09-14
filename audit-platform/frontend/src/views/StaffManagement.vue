<template>
  <div class="gt-staff-page gt-fade-in" @animationend="relayoutTable">
    <!-- P2-6 统计卡顶部 -->
    <div class="gt-staff-stats">
      <div class="gt-staff-stats__item">
        <span class="gt-staff-stats__num">{{ total }}</span>
        <span class="gt-staff-stats__label">总人数</span>
      </div>
      <div class="gt-staff-stats__item">
        <span class="gt-staff-stats__num">{{ cpaCount }}</span>
        <span class="gt-staff-stats__label">注册会计师</span>
      </div>
      <div class="gt-staff-stats__item">
        <span class="gt-staff-stats__num">{{ partnerCount }}</span>
        <span class="gt-staff-stats__label">合伙人</span>
      </div>
      <div class="gt-staff-stats__item">
        <span class="gt-staff-stats__num">{{ activeProjectCount }}</span>
        <span class="gt-staff-stats__label">当前在项目</span>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="gt-staff-toolbar">
      <h2 class="gt-staff-toolbar__title">人员档案</h2>
      <div class="gt-staff-toolbar__actions">
        <el-input v-model="searchQuery" placeholder="搜索姓名/工号" clearable style="width: 200px"
          :prefix-icon="Search" @input="debouncedSearch" />
        <el-select v-model="filterDept" placeholder="部门" clearable style="width: 130px" @change="loadStaff">
          <el-option label="审计一部" value="审计一部" />
          <el-option label="审计二部" value="审计二部" />
          <el-option label="审计三部" value="审计三部" />
        </el-select>
        <el-select v-model="filterRole" placeholder="职级" clearable style="width: 120px" @change="loadStaff">
          <el-option v-for="t in titles" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 100px" @change="loadStaff">
          <el-option label="在职" value="active" />
          <el-option label="休假" value="on_leave" />
          <el-option label="离职" value="resigned" />
        </el-select>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增人员</el-button>
        <el-dropdown @command="onImportCommand">
          <el-button>Excel导入 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">下载导入模板</el-dropdown-item>
              <el-dropdown-item command="import">导入 Excel</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- P2-6 表格（去border stripe，外包el-card） -->
    <el-card shadow="never" class="gt-staff-card">
      <!-- #3 批量操作工具栏 -->
      <div v-if="selectedRows.length" class="gt-staff-batch-bar">
        <span>已选 {{ selectedRows.length }} 人</span>
        <el-button size="small" @click="batchSetDept">批量设置部门</el-button>
        <el-button size="small" @click="batchSetPartner">批量设置合伙人</el-button>
        <el-button size="small" type="danger" plain @click="batchDeactivate">批量停用</el-button>
      </div>
      <el-table ref="staffTableRef" :data="staffList" v-loading="loading" style="width: 100%" border :row-class-name="rowClassName" @selection-change="onSelectionChange">
        <!-- #3 批量选择列 -->
        <el-table-column type="selection" width="36" />
        <!-- 头像列 -->
        <el-table-column width="44" align="center">
          <template #default="{ row }">
            <div class="gt-staff-avatar" :style="{ backgroundColor: avatarColor(row.name) }">
              {{ row.name?.charAt(0) || '?' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="employee_no" label="工号" width="75" sortable show-overflow-tooltip />
        <el-table-column prop="name" label="姓名" width="80" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tooltip :content="row.name" placement="top" :disabled="!row.name || row.name.length <= 4">
              <span v-html="highlightSearch(row.name)"></span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" width="85" show-overflow-tooltip />
        <el-table-column prop="title" label="职级" width="90" show-overflow-tooltip />
        <el-table-column prop="partner_name" label="所属合伙人" min-width="100" show-overflow-tooltip />
        <el-table-column prop="specialty" label="专业领域" min-width="100" show-overflow-tooltip />
        <el-table-column label="CPA" width="50" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_cpa" color="var(--el-color-success)"><Check /></el-icon>
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="年限" width="50" align="center">
          <template #default="{ row }">
            <span v-if="row.audit_years">{{ row.audit_years }}年</span>
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="55" align="center">
          <template #default="{ row }">
            <el-tag :type="row.source === 'seed' ? 'info' : 'success'" size="small" round>
              {{ row.source === 'seed' ? '系统' : '手工' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="联系电话" width="115" show-overflow-tooltip />
        <!-- 操作列 -->
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editStaff(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="viewResume(row)">档案</el-button>
            <el-dropdown trigger="click" @command="(cmd: string) => onRowAction(cmd, row)">
              <el-button link type="info" size="small">更多<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="handover">交接</el-dropdown-item>
                  <el-dropdown-item v-if="row.source === 'custom'" command="delete" divided>
                    <span style="color: var(--el-color-danger)">删除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-pagination v-if="total > pageSize" :current-page="currentPage" :page-size="pageSize"
      :total="total" layout="total, prev, pager, next" style="margin-top: 16px; justify-content: flex-end"
      @current-change="onPageChange" />

    <!-- P0-1 创建/编辑弹窗（三步分组） -->
    <el-dialog append-to-body v-model="showCreateDialog" :title="editingStaff ? '编辑人员' : '新增人员'" width="600px">
      <el-form ref="staffFormRef" :model="formData" :rules="staffRules" label-width="100px">
        <el-divider content-position="left">基本信息</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="姓名" prop="name" required><el-input v-model="formData.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="工号"><el-input v-model="formData.employee_no" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="部门"><el-input v-model="formData.department" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职级">
              <el-select v-model="formData.title" style="width: 100%">
                <el-option v-for="t in titles" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所属合伙人"><el-input v-model="formData.partner_name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入职日期">
              <el-date-picker v-model="formData.join_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="联系电话"><el-input v-model="formData.phone" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱"><el-input v-model="formData.email" /></el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">执业资质</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="注册会计师">
              <el-switch v-model="formData.is_cpa" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="CPA证书号">
              <el-input v-model="formData.cpa_cert_no" :disabled="!formData.is_cpa" placeholder="执业证书编号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="审计年限">
              <el-input-number v-model="formData.audit_years" :min="0" :max="50" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色等级">
              <el-select v-model="formData.role_level" placeholder="选择" style="width: 100%">
                <el-option label="合伙人" value="partner" />
                <el-option label="经理" value="manager" />
                <el-option label="高级" value="senior" />
                <el-option label="审计员" value="auditor" />
                <el-option label="实习" value="intern" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="专业资质">
          <el-select v-model="formData.qualifications" multiple allow-create filterable style="width: 100%"
            placeholder="选择或输入资质（如CPA/CIA/CISA/评估师）">
            <el-option v-for="q in qualificationOptions" :key="q" :label="q" :value="q" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">专业领域</el-divider>
        <el-form-item label="专业领域"><el-input v-model="formData.specialty" placeholder="如：审计/税务/咨询" /></el-form-item>
        <el-form-item label="行业经验">
          <el-select v-model="formData.industry_experience" multiple allow-create filterable style="width: 100%"
            placeholder="选择或输入行业">
            <el-option v-for="ind in industryOptions" :key="ind" :label="ind" :value="ind" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveStaff" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- P1-3 简历/档案弹窗（增强为项目参与面板） -->
    <el-dialog append-to-body v-model="showResumeDialog" title="人员档案" width="700px">
      <div v-if="resumeData">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="姓名">{{ resumeData.name }}</el-descriptions-item>
          <el-descriptions-item label="职级">{{ resumeData.title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ resumeData.department || '—' }}</el-descriptions-item>
          <el-descriptions-item label="CPA">{{ resumeData.is_cpa ? '✓ ' + (resumeData.cpa_cert_no || '') : '否' }}</el-descriptions-item>
          <el-descriptions-item label="审计年限">{{ resumeData.audit_years ? resumeData.audit_years + '年' : '—' }}</el-descriptions-item>
          <el-descriptions-item label="参与项目数">{{ resumeData.total_projects }}</el-descriptions-item>
        </el-descriptions>

        <!-- P3-8 能力矩阵展示 -->
        <div v-if="resumeData.qualifications?.length || resumeData.industry_experience?.length" style="margin-top: 12px">
          <el-tag v-for="q in (resumeData.qualifications || [])" :key="q" type="warning" size="small" round style="margin: 2px">{{ q }}</el-tag>
          <el-tag v-for="ind in (resumeData.industry_experience || [])" :key="ind" size="small" round style="margin: 2px">{{ ind }}</el-tag>
        </div>

        <h4 style="margin: 16px 0 8px">当前参与项目</h4>
        <el-table :data="resumeData.recent_projects" size="small" max-height="300">
          <el-table-column prop="project_name" label="项目名称" show-overflow-tooltip />
          <el-table-column prop="client_name" label="客户" width="120" />
          <el-table-column prop="role" label="角色" width="100">
            <template #default="{ row }">
              <el-tag :type="roleTagType(row.role)" size="small">{{ row.role }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assigned_at" label="委派时间" width="110" />
        </el-table>

        <!-- P1-5 轮换提示 -->
        <el-alert
          v-if="resumeData.title === '合伙人' && resumeData.total_projects > 0"
          type="info"
          :closable="false"
          style="margin-top: 12px"
          description="提示：签字合伙人连续审计同一客户不得超过5年（上市7年），请关注轮换要求。"
        />
      </div>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog v-model="showStaffImport" import-type="staff" @imported="onStaffImported" />

    <!-- 交接弹窗（保留原有完整实现） -->
    <el-dialog
      v-model="showHandoverDialog"
      title="人员工作交接"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @close="resetHandoverForm"
    >
      <el-form ref="handoverFormRef" :model="handoverForm" :rules="handoverRules" label-width="100px">
        <el-form-item label="交接人">
          <span style="font-weight: 600">{{ handoverTarget?.name }}（{{ handoverTarget?.title || '—' }}）</span>
        </el-form-item>
        <el-form-item label="目标人" prop="target_staff_id" required>
          <el-select v-model="handoverForm.target_staff_id" filterable placeholder="请选择接收人" style="width: 100%">
            <el-option v-for="s in handoverCandidates" :key="s.id" :label="`${s.name}（${s.title || '—'}）`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="原因" prop="reason_code" required>
          <el-select v-model="handoverForm.reason_code" placeholder="请选择原因" style="width: 100%">
            <el-option label="离职" value="resignation" />
            <el-option label="长期休假" value="long_leave" />
            <el-option label="岗位轮换" value="rotation" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="补充说明">
          <el-input v-model="handoverForm.reason_detail" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
        <el-form-item label="生效日期" prop="effective_date" required>
          <el-date-picker v-model="handoverForm.effective_date" type="date" placeholder="选择" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
      </el-form>
      <div v-if="handoverPreview" class="gt-handover-preview">
        <el-divider content-position="left">交接预览</el-divider>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="底稿">{{ handoverPreview.workpapers }} 张</el-descriptions-item>
          <el-descriptions-item label="工单">{{ handoverPreview.issues }} 张</el-descriptions-item>
          <el-descriptions-item label="项目委派">{{ handoverPreview.assignments }} 个</el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-if="handoverPreviewLoading" style="text-align: center; padding: 16px">
        <el-icon class="is-loading"><Loading /></el-icon> 加载预览中...
      </div>
      <template #footer>
        <el-button @click="showHandoverDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!canSubmitHandover" :loading="handoverSubmitting" @click="executeHandover">确认交接</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import * as P from '@/services/apiPaths'
import { ref, computed, onMounted, nextTick } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmDelete, confirmDangerous } from '@/utils/confirm'
import { Search, Plus, ArrowDown, Check, Loading } from '@element-plus/icons-vue'
import { listStaff, createStaff, updateStaff, getStaffResume, deleteStaff, type StaffMember } from '@/services/staffApi'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { rules } from '@/utils/formRules'

const titles = ['合伙人', '总监', '高级经理', '经理', '高级审计员', '审计员', '实习生']
const qualificationOptions = ['CPA', 'CIA', 'CISA', '资产评估师', '税务师', '法律职业资格', 'ACCA', 'CFA']
const industryOptions = ['制造业', '金融业', '房地产', '医药', '科技', '零售', '能源', '交通运输', '建筑', '教育']

const staffList = ref<StaffMember[]>([])
const staffTableRef = ref<any>(null)
// el-table 在 gt-fade-in（transform 动画）中挂载会算错列宽（列被压窄/头像裁切/表头截断），
// 动画结束及每次数据加载后强制重新布局。
function relayoutTable() {
  nextTick(() => staffTableRef.value?.doLayout?.())
}
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
const searchQuery = ref('')
const filterDept = ref('')
const filterRole = ref('')
const showCreateDialog = ref(false)
const showStaffImport = ref(false)
const showResumeDialog = ref(false)
const editingStaff = ref<StaffMember | null>(null)
const saving = ref(false)
const resumeData = ref<any>(null)

// P2 统计卡真实数据
const statsData = ref({ total: 0, cpa_count: 0, partner_count: 0, active_project_count: 0 })
const cpaCount = computed(() => statsData.value.cpa_count)
const partnerCount = computed(() => statsData.value.partner_count)
const activeProjectCount = computed(() => statsData.value.active_project_count)

// #4 人员状态筛选
const filterStatus = ref('')

// #3 批量操作
const selectedRows = ref<StaffMember[]>([])
function onSelectionChange(rows: StaffMember[]) { selectedRows.value = rows }

// #8 仪表盘联动入口
import { useRoute } from 'vue-router'
const route = useRoute()
const routeProjectId = computed(() => (route.query.project_id as string) || '')

const formData = ref({
  name: '', employee_no: '', department: '', title: '', partner_name: '',
  specialty: '', phone: '', email: '', join_date: '',
  is_cpa: false, cpa_cert_no: '', audit_years: null as number | null,
  role_level: '', qualifications: [] as string[], industry_experience: [] as string[],
})
const staffFormRef = ref<FormInstance>()
const staffRules: FormRules = { name: [rules.required('姓名')] }

// P2-6 头像颜色
const AVATAR_COLORS = ['#4b2d77', '#2d6b4b', '#6b2d2d', '#2d4b6b', '#6b5a2d', '#3d6b6b', '#5a2d6b']
function avatarColor(name: string) {
  if (!name) return AVATAR_COLORS[0]
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}

// P2-6 职级tag类型
function titleTagType(title: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (title === '合伙人') return 'danger'
  if (title === '总监' || title === '高级经理') return 'warning'
  if (title === '经理') return ''
  if (title === '高级审计员') return 'success'
  return 'info'
}

function roleTagType(role: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (role === 'signing_partner' || role === '签字合伙人') return 'danger'
  if (role === 'manager' || role === '项目经理') return 'warning'
  if (role === 'qc') return 'info'
  return 'success'
}

function rowClassName({ row }: { row: StaffMember }) {
  const r = row as any
  if (r.status === 'resigned') return 'gt-resigned-row'
  if (r.is_cpa) return 'gt-cpa-row'
  return ''
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { currentPage.value = 1; loadStaff() }, 400)
}

async function loadStaff() {
  loading.value = true
  try {
    const res = await listStaff({
      search: searchQuery.value || undefined,
      department: filterDept.value || undefined,
      partner_name: undefined,
      offset: (currentPage.value - 1) * pageSize,
      limit: pageSize,
      // #1 职级筛选
      ...(filterRole.value ? { title: filterRole.value } : {}),
      // #4 状态筛选
      ...(filterStatus.value ? { status: filterStatus.value } : {}),
      // #8 项目联动
      ...(routeProjectId.value ? { project_id: routeProjectId.value } : {}),
    } as any)
    staffList.value = res.items
    total.value = res.total
    relayoutTable()
  } finally { loading.value = false }
}

async function loadStats() {
  try {
    const { data } = await http.get(P.staff.stats)
    statsData.value = data as any
  } catch { /* fail-open */ }
}

// #6 搜索高亮
function highlightSearch(text: string): string {
  if (!text || !searchQuery.value) return text || ''
  const escaped = searchQuery.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${escaped})`, 'gi')
  return text.replace(re, '<mark style="background:#ffe58f;padding:0 1px;border-radius:2px">$1</mark>')
}

// #3 批量操作
async function batchSetDept() {
  const { value } = await ElMessageBox.prompt('请输入部门名称', '批量设置部门', { inputPlaceholder: '如：审计一部' }) as any
  if (!value) return
  for (const row of selectedRows.value) {
    await updateStaff(row.id, { department: value } as any)
  }
  ElMessage.success(`已为 ${selectedRows.value.length} 人设置部门`)
  await loadStaff()
}

async function batchSetPartner() {
  const { value } = await ElMessageBox.prompt('请输入合伙人姓名', '批量设置所属合伙人', { inputPlaceholder: '如：李合伙人' }) as any
  if (!value) return
  for (const row of selectedRows.value) {
    await updateStaff(row.id, { partner_name: value } as any)
  }
  ElMessage.success(`已为 ${selectedRows.value.length} 人设置合伙人`)
  await loadStaff()
}

async function batchDeactivate() {
  await confirmDangerous(`确认将 ${selectedRows.value.length} 人标记为离职？`, '批量停用')
  for (const row of selectedRows.value) {
    await updateStaff(row.id, { status: 'resigned' } as any)
  }
  ElMessage.success(`已停用 ${selectedRows.value.length} 人`)
  await loadStaff()
  await loadStats()
}

function onPageChange(page: number) { currentPage.value = page; loadStaff() }

function openCreateDialog() {
  editingStaff.value = null
  formData.value = {
    name: '', employee_no: '', department: '', title: '', partner_name: '',
    specialty: '', phone: '', email: '', join_date: '',
    is_cpa: false, cpa_cert_no: '', audit_years: null,
    role_level: '', qualifications: [], industry_experience: [],
  }
  showCreateDialog.value = true
}

function editStaff(row: StaffMember) {
  editingStaff.value = row
  const r = row as any
  formData.value = {
    name: row.name, employee_no: row.employee_no || '', department: row.department || '',
    title: row.title || '', partner_name: row.partner_name || '',
    specialty: row.specialty || '', phone: row.phone || '', email: row.email || '',
    join_date: (row as any).join_date || '',
    is_cpa: r.is_cpa || false, cpa_cert_no: r.cpa_cert_no || '',
    audit_years: r.audit_years || null, role_level: r.role_level || '',
    qualifications: r.qualifications || [], industry_experience: r.industry_experience || [],
  }
  showCreateDialog.value = true
}

async function viewResume(row: StaffMember) {
  try {
    resumeData.value = await getStaffResume(row.id)
    // 合并当前行数据供展示
    const r = row as any
    resumeData.value.is_cpa = r.is_cpa
    resumeData.value.cpa_cert_no = r.cpa_cert_no
    resumeData.value.audit_years = r.audit_years
    resumeData.value.qualifications = r.qualifications
    resumeData.value.industry_experience = r.industry_experience
    showResumeDialog.value = true
  } catch (e: any) { handleApiError(e, '获取档案') }
}

async function saveStaff() {
  if (!formData.value.name) { ElMessage.warning('请输入姓名'); return }
  saving.value = true
  try {
    const payload: any = { ...formData.value }
    if (!payload.join_date) delete payload.join_date
    if (!payload.audit_years) delete payload.audit_years
    if (editingStaff.value) {
      await updateStaff(editingStaff.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createStaff({ ...payload, source: 'custom' })
      ElMessage.success('创建成功')
    }
    showCreateDialog.value = false
    editingStaff.value = null
    await loadStaff()
  } finally { saving.value = false }
}

// P2-6 操作列更多菜单
function onRowAction(cmd: string, row: StaffMember) {
  if (cmd === 'handover') openHandover(row)
  else if (cmd === 'delete') onDeleteStaff(row)
}

async function onDeleteStaff(row: StaffMember) {
  await confirmDelete(`「${row.name}」`)
  try {
    await deleteStaff(row.id)
    ElMessage.success('已删除')
    await loadStaff()
  } catch (e: any) { handleApiError(e, '删除') }
}

// P2-7 导入增强
function onImportCommand(cmd: string) {
  if (cmd === 'template') downloadTemplate()
  else if (cmd === 'import') showStaffImport.value = true
}

function downloadTemplate() {
  // 使用平台 downloadFile 工具（已处理 blob+错误解析+文件名）
  import('@/utils/http').then(({ downloadFile }) => {
    downloadFile(P.staff.exportTemplate, {
      fileName: '人员档案导入模板.xlsx',
      silent: true,
    }).catch(() => {
      ElMessage.warning('模板下载失败，请稍后重试')
    })
  })
}

function onStaffImported() {
  showStaffImport.value = false
  loadStaff()
}

// ── 交接功能（保留原有完整实现） ──

const showHandoverDialog = ref(false)
const handoverTarget = ref<StaffMember | null>(null)
const handoverCandidates = ref<StaffMember[]>([])
const handoverPreview = ref<{ workpapers: number; issues: number; assignments: number } | null>(null)
const handoverPreviewLoading = ref(false)
const handoverSubmitting = ref(false)

const handoverForm = ref({ target_staff_id: '', reason_code: '', reason_detail: '', effective_date: '' })
const handoverFormRef = ref<FormInstance>()
const handoverRules: FormRules = {
  target_staff_id: [rules.required('目标人', 'change')],
  reason_code: [rules.required('原因', 'change')],
  effective_date: [{ required: true, message: '请选择生效日期', trigger: 'change' }],
}

const canSubmitHandover = computed(() => {
  return handoverForm.value.target_staff_id && handoverForm.value.reason_code &&
    handoverForm.value.effective_date && handoverPreview.value !== null && !handoverSubmitting.value
})

function resetHandoverForm() {
  handoverTarget.value = null
  handoverPreview.value = null
  handoverPreviewLoading.value = false
  handoverSubmitting.value = false
  handoverForm.value = { target_staff_id: '', reason_code: '', reason_detail: '', effective_date: '' }
}

async function openHandover(row: StaffMember) {
  handoverTarget.value = row
  showHandoverDialog.value = true
  try {
    const res = await listStaff({ limit: 500 })
    handoverCandidates.value = res.items.filter(s => s.id !== row.id)
  } catch { handoverCandidates.value = [] }
  await loadHandoverPreview(row.id)
}

async function loadHandoverPreview(staffId: string) {
  handoverPreviewLoading.value = true
  handoverPreview.value = null
  try {
    const { data } = await http.get(P.staff.handoverPreview(staffId), { params: { scope: 'all' } })
    handoverPreview.value = data as { workpapers: number; issues: number; assignments: number }
  } catch {
    handoverPreview.value = null
    ElMessage.warning('获取交接预览失败')
  } finally { handoverPreviewLoading.value = false }
}

async function executeHandover() {
  if (!handoverTarget.value) return
  const totalItems = (handoverPreview.value?.workpapers || 0) + (handoverPreview.value?.issues || 0) + (handoverPreview.value?.assignments || 0)
  if (totalItems === 0) { ElMessage.info('该人员名下无需交接的工作项'); showHandoverDialog.value = false; return }
  try {
    await confirmDangerous(
      `确认将 ${handoverPreview.value?.workpapers} 张底稿、${handoverPreview.value?.issues} 张工单、${handoverPreview.value?.assignments} 个项目委派交接给目标人？`,
      '交接确认',
    )
  } catch { return }
  handoverSubmitting.value = true
  try {
    await http.post(P.staff.handover(handoverTarget.value.id), {
      scope: 'all', target_staff_id: handoverForm.value.target_staff_id,
      reason_code: handoverForm.value.reason_code, reason_detail: handoverForm.value.reason_detail || undefined,
      effective_date: handoverForm.value.effective_date,
    })
    ElMessage.success('交接完成')
    showHandoverDialog.value = false
    await loadStaff()
  } catch {} finally { handoverSubmitting.value = false }
}

onMounted(() => { loadStaff(); loadStats() })
</script>

<style scoped>
.gt-staff-page {
  padding: 16px 20px;
  font-size: 13px;
}

/* 统计卡 */
.gt-staff-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 14px 20px;
  background: linear-gradient(135deg, rgba(75, 45, 119, 0.04), rgba(75, 45, 119, 0.01));
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.gt-staff-stats__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.gt-staff-stats__num {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.gt-staff-stats__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 工具栏 */
.gt-staff-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.gt-staff-toolbar__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-staff-toolbar__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格卡片 */
.gt-staff-card {
  border-radius: 8px;
}

.gt-staff-card :deep(.el-card__body) {
  padding: 0;
}

.gt-staff-card :deep(.el-table) {
  font-size: 12px;
}

.gt-staff-card :deep(.el-table th) {
  background-color: var(--el-fill-color-lighter);
  font-weight: 600;
  font-size: 12px;
}

.gt-staff-card :deep(.el-table td) {
  font-size: 12px;
}

.gt-staff-card :deep(.el-table .cell) {
  font-size: 12px;
}

/* 头像 */
.gt-staff-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.gt-text-muted {
  color: var(--el-text-color-placeholder);
}

/* 表格行高紧凑 */
.gt-staff-card :deep(.el-table td .cell) {
  padding-top: 4px;
  padding-bottom: 4px;
}

.gt-staff-card :deep(.el-table th .cell) {
  padding-top: 6px;
  padding-bottom: 6px;
}

.gt-handover-preview {
  margin-top: 16px;
}

/* #4 离职人员灰化 */
:deep(.gt-resigned-row) {
  opacity: 0.5;
  background-color: var(--el-fill-color-lighter) !important;
}

/* #3 批量操作工具栏 */
.gt-staff-batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
  color: var(--el-color-primary);
}

/* #8 项目联动入口提示 */
.gt-project-filter-hint {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
