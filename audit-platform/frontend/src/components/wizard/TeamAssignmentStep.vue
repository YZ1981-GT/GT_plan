<template>
  <div class="gt-team-step">
    <div class="gt-team-header">
      <span class="gt-team-title">团队委派</span>
      <div class="gt-team-header__actions">
        <el-button size="small" @click="showGuideDialog = true">
          <el-icon style="margin-right: 4px"><QuestionFilled /></el-icon>操作手册
        </el-button>
        <el-button size="small" @click="showRefProjectDialog = true">
          <el-icon style="margin-right: 4px"><CopyDocument /></el-icon>参照项目
        </el-button>
        <el-button type="primary" size="small" @click="showAddDialog = true">添加成员</el-button>
      </div>
    </div>

    <!-- 操作手册弹窗 -->
    <el-dialog v-model="showGuideDialog" title="人员委派 · 操作手册" width="680px" append-to-body>
      <div class="gt-guide-content">
        <div class="gt-guide-intro">
          <p>人员委派用于将项目组成员添加到本审计项目，并为每位成员分配<strong>项目角色</strong>与<strong>负责的审计循环</strong>。委派完成后，系统将根据分配结果控制底稿可见范围、复核权限与任务通知。</p>
        </div>

        <el-divider content-position="left">第一步：添加项目组成员</el-divider>
        <div class="gt-guide-step">
          <ol>
            <li>点击右上角 <el-tag size="small" type="primary" effect="dark">添加成员</el-tag> 按钮</li>
            <li>在弹出的「从人员库选择成员」窗口中：
              <ul>
                <li>通过<strong>姓名/工号</strong>搜索，或按<strong>部门</strong>筛选</li>
                <li>勾选需要加入本项目的成员（已添加的成员会显示「已添加」标签且不可重复勾选）</li>
              </ul>
            </li>
            <li>点击 <el-tag size="small" type="primary">添加 N 人</el-tag> 确认</li>
            <li>如果搜索不到目标人员，点击「搜不到？快速创建」可即时新建人员档案并自动加入</li>
          </ol>
        </div>

        <el-divider content-position="left">第二步：设置项目角色</el-divider>
        <div class="gt-guide-step">
          <p>在成员列表的「角色」列，为每位成员选择对应的项目角色：</p>
          <el-descriptions :column="1" border size="small" style="margin-top: 8px">
            <el-descriptions-item label="签字合伙人">对审计报告签字负责，拥有最高审计判断权限，可审批重大事项</el-descriptions-item>
            <el-descriptions-item label="项目经理">负责项目日常管理、底稿一级复核、任务分派与进度把控</el-descriptions-item>
            <el-descriptions-item label="审计员">现场执行人员，负责底稿编制、取数、调整分录录入等具体工作</el-descriptions-item>
            <el-descriptions-item label="质控人员">独立质量控制复核（QC），按 QC 28 条规则检查项目质量</el-descriptions-item>
            <el-descriptions-item label="独立复核合伙人">项目质量控制复核（EQCR），从技术层面独立复核审计结论</el-descriptions-item>
          </el-descriptions>
          <el-alert type="info" :closable="false" style="margin-top: 10px" show-icon>
            <template #title>
              每个项目建议至少配置 1 名签字合伙人 + 1 名项目经理 + 若干审计员
            </template>
          </el-alert>
        </div>

        <el-divider content-position="left">第三步：分配审计循环</el-divider>
        <div class="gt-guide-step">
          <p>在「审计循环」列勾选该成员负责的业务循环（B ~ N）：</p>
          <el-descriptions :column="2" border size="small" style="margin-top: 8px">
            <el-descriptions-item label="B">审计计划与风险评估</el-descriptions-item>
            <el-descriptions-item label="C">内部控制测试</el-descriptions-item>
            <el-descriptions-item label="D">销售与收款循环</el-descriptions-item>
            <el-descriptions-item label="E">货币资金</el-descriptions-item>
            <el-descriptions-item label="F">采购与付款循环</el-descriptions-item>
            <el-descriptions-item label="G">投资循环</el-descriptions-item>
            <el-descriptions-item label="H">固定/无形资产循环</el-descriptions-item>
            <el-descriptions-item label="I">无形/长期资产</el-descriptions-item>
            <el-descriptions-item label="J">薪酬循环</el-descriptions-item>
            <el-descriptions-item label="K">其他应收/应付/损益</el-descriptions-item>
            <el-descriptions-item label="L">债务循环</el-descriptions-item>
            <el-descriptions-item label="M">权益循环</el-descriptions-item>
            <el-descriptions-item label="N">税项</el-descriptions-item>
          </el-descriptions>
          <el-alert type="warning" :closable="false" style="margin-top: 10px" show-icon>
            <template #title>
              分配循环后，成员仅能查看和编辑其负责循环下的底稿（服务端强制隔离）
            </template>
          </el-alert>
        </div>

        <el-divider content-position="left">第四步：保存委派</el-divider>
        <div class="gt-guide-step">
          <p>完成以上设置后，关闭本弹窗时系统将<strong>自动保存</strong>委派信息。你也可以随时重新打开本弹窗修改角色与循环分配。</p>
          <ul>
            <li><strong>移除成员</strong>：点击操作列的「移除」按钮即可将该成员从本项目撤回</li>
            <li><strong>修改角色/循环</strong>：直接在表格中切换下拉/勾选，即时生效</li>
          </ul>
        </div>

        <el-divider content-position="left">常见问题</el-divider>
        <div class="gt-guide-step gt-guide-faq">
          <p><strong>Q：分配循环后成员看不到底稿？</strong></p>
          <p>A：请确认该循环下的底稿已生成（通过「程序裁剪」保留并生成），未生成的底稿不会出现在成员视图中。</p>
          <p style="margin-top: 10px"><strong>Q：签字合伙人/项目经理需要分配循环吗？</strong></p>
          <p>A：签字合伙人与项目经理默认可查看全部循环底稿（管理权限覆盖），但建议仍勾选其重点关注的循环以便系统精准推送复核提醒。</p>
          <p style="margin-top: 10px"><strong>Q：如何调整底稿的具体编制人/复核人？</strong></p>
          <p>A：本页面为项目级粗分配（循环级）。更细粒度的底稿级编制人/复核人分派，请前往「底稿列表 → 生命周期视图 → 程序裁剪」中的委派向导设置。</p>
        </div>
      </div>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
          <el-checkbox v-model="guideDismissForever" @change="onGuideDismissChange">不再自动弹出</el-checkbox>
          <el-button type="primary" @click="showGuideDialog = false">我知道了</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 已委派成员列表 -->
    <el-table :data="members" border stripe style="width: 100%" empty-text="暂未委派成员">
      <el-table-column prop="staff_name" label="姓名" width="120" />
      <el-table-column prop="employee_no" label="工号" width="100" />
      <el-table-column prop="staff_title" label="职级" width="100" />
      <el-table-column label="角色" width="150">
        <template #default="{ row, $index }">
          <el-select v-model="row.role" size="small" @change="onRoleChange($index)">
            <el-option label="签字合伙人" value="signing_partner" />
            <el-option label="项目经理" value="manager" />
            <el-option label="审计员" value="auditor" />
            <el-option label="质控人员" value="qc" />
            <el-option label="独立复核合伙人" value="eqcr" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="审计循环" min-width="200">
        <template #default="{ row, $index }">
          <div style="display: flex; align-items: center; gap: 6px;">
            <el-checkbox-group v-model="row.assigned_cycles" size="small" @change="onCycleChange($index)">
              <el-checkbox v-for="c in cycles" :key="c" :label="c">{{ c }}</el-checkbox>
            </el-checkbox-group>
            <el-dropdown trigger="click" size="small" @command="(cmd: string) => onQuickAssign(cmd, $index)">
              <el-button link size="small" type="primary" style="padding: 2px 4px; font-size: 11px;">快捷</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all">全选(B~N)</el-dropdown-item>
                  <el-dropdown-item command="upper">上半循环(B~H)</el-dropdown-item>
                  <el-dropdown-item command="lower">下半循环(I~N)</el-dropdown-item>
                  <el-dropdown-item command="clear" divided>清空</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeMember($index)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- #3 委派完整性校验提示 -->
    <transition name="el-fade-in">
      <div v-if="validationWarnings.length > 0" class="gt-team-warnings">
        <el-alert
          v-for="(w, i) in validationWarnings"
          :key="i"
          :title="w"
          type="warning"
          show-icon
          :closable="false"
          style="margin-bottom: 6px;"
        />
      </div>
    </transition>

    <!-- #4 覆盖率矩阵缩略图 -->
    <div v-if="members.length > 0" class="gt-team-matrix">
      <div class="gt-team-matrix__title">循环覆盖一览</div>
      <div class="gt-team-matrix__grid">
        <div class="gt-matrix-header">
          <span class="gt-matrix-name-col"></span>
          <span v-for="c in cycles" :key="c" class="gt-matrix-cycle-col">{{ c }}</span>
        </div>
        <div v-for="m in members" :key="m.staff_id" class="gt-matrix-row">
          <span class="gt-matrix-name-col" :title="m.staff_name">{{ m.staff_name }}</span>
          <span
            v-for="c in cycles"
            :key="c"
            class="gt-matrix-cycle-col"
            :class="{ 'gt-matrix-dot--active': m.assigned_cycles.includes(c) }"
          >
            {{ m.assigned_cycles.includes(c) ? '\u25CF' : '' }}
          </span>
        </div>
        <div class="gt-matrix-row gt-matrix-row--footer">
          <span class="gt-matrix-name-col">覆盖数</span>
          <span
            v-for="c in cycles"
            :key="c"
            class="gt-matrix-cycle-col"
            :class="{ 'gt-matrix-dot--warn': cycleCoverage(c) === 0 }"
          >
            {{ cycleCoverage(c) }}
          </span>
        </div>
      </div>
    </div>

    <!-- 添加成员弹窗：勾选模式 -->
    <el-dialog append-to-body v-model="showAddDialog" width="700px" :close-on-click-modal="false">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px; font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-primary)">
          <el-icon><User /></el-icon> 从人员库选择成员
        </div>
      </template>

      <!-- 搜索栏 -->
      <div style="display: flex; gap: 10px; margin-bottom: 12px">
        <el-input v-model="staffSearch" placeholder="搜索姓名/工号" clearable style="flex: 1" @input="debouncedLoadStaffList" />
        <el-select v-model="staffDeptFilter" placeholder="部门" clearable style="width: 150px" @change="loadStaffList">
          <el-option label="审计一部" value="审计一部" />
          <el-option label="审计二部" value="审计二部" />
          <el-option label="审计三部" value="审计三部" />
        </el-select>
      </div>

      <!-- 人员列表（勾选） -->
      <el-table
        ref="staffTableRef"
        :data="staffListForSelect"
        v-loading="staffListLoading"
        size="small"
        max-height="360"
        @selection-change="onStaffSelectionChange"
        row-key="id"
      >
        <el-table-column type="selection" width="45" :selectable="isSelectable" />
        <el-table-column prop="name" label="姓名" width="100">
          <template #default="{ row }">
            <span style="font-weight: 600">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="employee_no" label="工号" width="90" />
        <el-table-column prop="department" label="部门" width="100" />
        <el-table-column prop="title" label="职级" width="90" />
        <el-table-column prop="partner_name" label="所属合伙人" width="110" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="isAlreadyAdded(row.id)" type="info" size="small">已添加</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 8px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary)">
        已选 <span style="color: var(--gt-color-primary); font-weight: 600">{{ selectedStaffIds.length }}</span> 人
        <el-button link type="primary" size="small" @click="showQuickCreate = true" style="margin-left: 16px">搜不到？快速创建</el-button>
      </div>

      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :disabled="selectedStaffIds.length === 0" @click="addSelectedMembers">
          添加 {{ selectedStaffIds.length }} 人
        </el-button>
      </template>
    </el-dialog>

    <!-- 快速创建人员弹窗 -->
    <el-dialog v-model="showQuickCreate" title="快速创建人员" width="450px" append-to-body>
      <el-form ref="newStaffFormRef" :model="newStaff" :rules="newStaffRules" label-width="80px">
        <el-form-item label="姓名" prop="name" required>
          <el-input v-model="newStaff.name" />
        </el-form-item>
        <el-form-item label="职级">
          <el-select v-model="newStaff.title" placeholder="选择职级" style="width: 100%">
            <el-option v-for="t in titles" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="newStaff.department" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="newStaff.phone" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showQuickCreate = false">取消</el-button>
        <el-button type="primary" @click="quickCreateStaff" :loading="creating">创建并选中</el-button>
      </template>
    </el-dialog>

    <!-- #2 参照其他项目弹窗 -->
    <el-dialog v-model="showRefProjectDialog" title="从其他项目复制委派" width="600px" append-to-body>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
        <template #title>选择一个历史项目，将其团队委派配置（成员+角色+循环）一键复制到当前项目</template>
      </el-alert>
      <el-input v-model="refProjectSearch" placeholder="搜索项目名称" clearable style="margin-bottom: 12px" />
      <el-table
        :data="filteredRefProjects"
        v-loading="refProjectsLoading"
        size="small"
        max-height="300"
        highlight-current-row
        @current-change="onRefProjectSelect"
      >
        <el-table-column prop="name" label="项目名称" />
        <el-table-column prop="audit_year" label="审计年度" width="100" />
        <el-table-column prop="member_count" label="成员数" width="80" align="center" />
      </el-table>
      <template #footer>
        <el-button @click="showRefProjectDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedRefProject" @click="applyRefProject">
          复制委派到当前项目
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { User, QuestionFilled, CopyDocument } from '@element-plus/icons-vue'
import { listStaff, createStaff, listAssignments, saveAssignments, type StaffMember, type Assignment } from '@/services/staffApi'
import { useWizardStore } from '@/stores/wizard'
import { rules } from '@/utils/formRules'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'

const props = defineProps<{ projectId?: string }>()
const wizardStore = useWizardStore()

const cycles = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
const titles = ['合伙人', '总监', '高级经理', '经理', '高级审计员', '审计员', '实习生']

interface MemberRow {
  staff_id: string
  staff_name: string
  staff_title: string
  employee_no: string
  role: string
  assigned_cycles: string[]
}

const members = ref<MemberRow[]>([])
const showAddDialog = ref(false)
const showGuideDialog = ref(false)
const showQuickCreate = ref(false)
const creating = ref(false)
const newStaff = ref({ name: '', title: '', department: '', phone: '' })
const newStaffFormRef = ref<FormInstance>()
const newStaffRules: FormRules = {
  name: [rules.required('姓名')],
}

// ========== #2 参照其他项目 ==========
const showRefProjectDialog = ref(false)
const refProjectSearch = ref('')
const refProjects = ref<any[]>([])
const refProjectsLoading = ref(false)
const selectedRefProject = ref<any>(null)

const filteredRefProjects = computed(() => {
  if (!refProjectSearch.value) return refProjects.value
  const kw = refProjectSearch.value.toLowerCase()
  return refProjects.value.filter(p => p.name?.toLowerCase().includes(kw))
})

watch(showRefProjectDialog, async (v) => {
  if (v) {
    refProjectSearch.value = ''
    selectedRefProject.value = null
    refProjectsLoading.value = true
    try {
      const res = await api.get(P_proj.list())
      const allProjects = res?.items || res || []
      // 排除当前项目，只显示有成员的历史项目
      refProjects.value = allProjects
        .filter((p: any) => p.id !== props.projectId)
        .map((p: any) => ({ id: p.id, name: p.name || p.client_name, audit_year: p.audit_year, member_count: p.member_count ?? '—' }))
    } catch { refProjects.value = [] }
    finally { refProjectsLoading.value = false }
  }
})

function onRefProjectSelect(row: any) { selectedRefProject.value = row }

async function applyRefProject() {
  if (!selectedRefProject.value) return
  try {
    const existing = await listAssignments(selectedRefProject.value.id)
    if (!existing || existing.length === 0) {
      ElMessage.warning('该项目暂无委派记录')
      return
    }
    await ElMessageBox.confirm(
      `将从「${selectedRefProject.value.name}」复制 ${existing.length} 名成员的委派配置到当前项目。已有成员不会被覆盖。`,
      '确认复制',
      { type: 'info', confirmButtonText: '复制', cancelButtonText: '取消' },
    )
    let added = 0
    for (const a of existing) {
      if (members.value.some(m => m.staff_id === a.staff_id)) continue
      members.value.push({
        staff_id: a.staff_id,
        staff_name: a.staff_name || '',
        staff_title: a.staff_title || '',
        employee_no: a.employee_no || '',
        role: a.role || 'auditor',
        assigned_cycles: a.assigned_cycles || [],
      })
      added++
    }
    ElMessage.success(`已复制 ${added} 名成员（${existing.length - added} 名已存在跳过）`)
    showRefProjectDialog.value = false
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') handleApiError(e, '复制委派失败')
  }
}

// ========== #3 委派完整性校验 ==========
const validationWarnings = computed<string[]>(() => {
  if (members.value.length === 0) return []
  const warnings: string[] = []
  // 角色校验
  if (!members.value.some(m => m.role === 'signing_partner')) {
    warnings.push('尚未指定签字合伙人')
  }
  if (!members.value.some(m => m.role === 'manager')) {
    warnings.push('缺少项目经理，进度把控可能受限')
  }
  // 循环覆盖校验
  const uncovered = cycles.filter(c => !members.value.some(m => m.assigned_cycles.includes(c)))
  if (uncovered.length > 0) {
    warnings.push(`循环 ${uncovered.join('/')} 尚未分配编制人`)
  }
  // 成员无循环
  const noCycle = members.value.filter(m => m.assigned_cycles.length === 0 && m.role === 'auditor')
  if (noCycle.length > 0) {
    warnings.push(`${noCycle.map(m => m.staff_name).join('、')} 尚未分配审计循环`)
  }
  // 职责不相容：同一人角色为审计员且循环与经理/合伙人完全重叠(简化判断)
  // 此处简化为不做SOD检查，留给更细粒度的底稿级委派
  return warnings
})

// ========== #4 矩阵缩略 ==========
function cycleCoverage(c: string): number {
  return members.value.filter(m => m.assigned_cycles.includes(c)).length
}

// ========== #5 快捷分配 ==========
function onQuickAssign(cmd: string, index: number) {
  const row = members.value[index]
  if (!row) return
  switch (cmd) {
    case 'all': row.assigned_cycles = [...cycles]; break
    case 'upper': row.assigned_cycles = ['B', 'C', 'D', 'E', 'F', 'G', 'H']; break
    case 'lower': row.assigned_cycles = ['I', 'J', 'K', 'L', 'M', 'N']; break
    case 'clear': row.assigned_cycles = []; break
  }
}

// ========== #1 首次自动弹出 ==========
const guideDismissForever = ref(!!localStorage.getItem('gt_team_guide_dismissed'))
function onGuideDismissChange(val: boolean | string | number) {
  if (val) {
    localStorage.setItem('gt_team_guide_dismissed', '1')
  } else {
    localStorage.removeItem('gt_team_guide_dismissed')
  }
}

// 勾选模式相关
const staffSearch = ref('')
const staffDeptFilter = ref('')
const staffListForSelect = ref<StaffMember[]>([])
const staffListLoading = ref(false)
const selectedStaffIds = ref<string[]>([])
const staffTableRef = ref<any>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function debouncedLoadStaffList() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadStaffList, 300)
}

async function loadStaffList() {
  staffListLoading.value = true
  try {
    const res = await listStaff({
      search: staffSearch.value || undefined,
      department: staffDeptFilter.value || undefined,
      limit: 50,
    })
    staffListForSelect.value = res.items || []
  } catch { staffListForSelect.value = [] }
  finally { staffListLoading.value = false }
}

function isAlreadyAdded(id: string): boolean {
  return members.value.some(m => m.staff_id === id)
}

function isSelectable(row: StaffMember): boolean {
  return !isAlreadyAdded(row.id)
}

function onStaffSelectionChange(selection: StaffMember[]) {
  selectedStaffIds.value = selection.map(s => s.id)
}

function addSelectedMembers() {
  for (const id of selectedStaffIds.value) {
    if (isAlreadyAdded(id)) continue
    const staff = staffListForSelect.value.find(s => s.id === id)
    if (!staff) continue
    members.value.push({
      staff_id: staff.id,
      staff_name: staff.name,
      staff_title: staff.title || '',
      employee_no: staff.employee_no || '',
      role: 'auditor',
      assigned_cycles: [],
    })
  }
  ElMessage.success(`已添加 ${selectedStaffIds.value.length} 名成员`)
  showAddDialog.value = false
  selectedStaffIds.value = []
}

// 打开弹窗时加载人员列表
watch(showAddDialog, (v) => {
  if (v) {
    staffSearch.value = ''
    staffDeptFilter.value = ''
    selectedStaffIds.value = []
    loadStaffList()
  }
})

function removeMember(index: number) { members.value.splice(index, 1) }
function onRoleChange(_: number) { /* auto-save handled by validate */ }
function onCycleChange(_: number) { /* auto-save handled by validate */ }

async function quickCreateStaff() {
  if (!newStaff.value.name) { ElMessage.warning('请输入姓名'); return }
  creating.value = true
  try {
    const staff = await createStaff({ ...newStaff.value, source: 'custom' })
    showQuickCreate.value = false
    newStaff.value = { name: '', title: '', department: '', phone: '' }
    ElMessage.success('人员创建成功')
    // 刷新列表并自动添加
    await loadStaffList()
    if (!isAlreadyAdded(staff.id)) {
      members.value.push({
        staff_id: staff.id,
        staff_name: staff.name,
        staff_title: staff.title || '',
        employee_no: staff.employee_no || '',
        role: 'auditor',
        assigned_cycles: [],
      })
    }
  } finally { creating.value = false }
}

async function validate(): Promise<boolean> {
  // 保存到 project_assignments 表
  if (props.projectId) {
    try {
      await saveAssignments(props.projectId, members.value.map(m => ({
        staff_id: m.staff_id, role: m.role, assigned_cycles: m.assigned_cycles,
      })))
    } catch (e) { handleApiError(e, '保存委派失败'); return false }
  }
  // 保存到 wizard_state
  await wizardStore.saveStep('team_assignment', {
    members: members.value.map(m => ({ staff_id: m.staff_id, staff_name: m.staff_name, role: m.role, assigned_cycles: m.assigned_cycles })),
  })
  return true
}

defineExpose({ validate })

onMounted(async () => {
  // #1 首次进入自动弹出操作手册
  if (!localStorage.getItem('gt_team_guide_dismissed')) {
    showGuideDialog.value = true
  }

  // 恢复已有委派
  if (props.projectId) {
    try {
      const existing = await listAssignments(props.projectId)
      members.value = existing.map((a: Assignment) => ({
        staff_id: a.staff_id, staff_name: a.staff_name || '', staff_title: a.staff_title || '',
        employee_no: a.employee_no || '', role: a.role, assigned_cycles: a.assigned_cycles || [],
      }))
    } catch { /* ignore */ }
  }
  // 从 wizard_state 恢复
  const saved = wizardStore.stepData?.team_assignment as any
  if (saved?.members && members.value.length === 0) {
    members.value = saved.members
  }
})
</script>

<style scoped>
.gt-team-step { padding: var(--gt-space-2) 0; }
.gt-team-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-team-header__actions { display: flex; align-items: center; gap: 10px; }
.gt-team-title { font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-primary); }

/* #3 校验提示 */
.gt-team-warnings { margin-top: 12px; }

/* #4 覆盖率矩阵 */
.gt-team-matrix { margin-top: 16px; padding: 12px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 6px; }
.gt-team-matrix__title { font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.gt-team-matrix__grid { font-size: 11px; font-family: 'Courier New', monospace; }
.gt-matrix-header { display: flex; font-weight: 600; color: var(--el-text-color-secondary); border-bottom: 1px solid #e4e7ed; padding-bottom: 4px; margin-bottom: 4px; }
.gt-matrix-row { display: flex; align-items: center; height: 22px; }
.gt-matrix-row--footer { border-top: 1px solid #e4e7ed; margin-top: 4px; padding-top: 4px; font-weight: 600; }
.gt-matrix-name-col { width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.gt-matrix-cycle-col { width: 26px; text-align: center; flex-shrink: 0; }
.gt-matrix-dot--active { color: var(--gt-color-primary, #4b2d77); font-size: 13px; }
.gt-matrix-dot--warn { color: var(--el-color-danger); }

/* 操作手册弹窗样式 */
.gt-guide-content { font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); }
.gt-guide-intro { padding: 12px 16px; background: linear-gradient(135deg, #f0e6ff 0%, #e8f4fd 100%); border-radius: 8px; margin-bottom: 16px; }
.gt-guide-intro p { margin: 0; }
.gt-guide-step { padding: 0 4px; }
.gt-guide-step ol, .gt-guide-step ul { padding-left: 20px; margin: 6px 0; }
.gt-guide-step li { margin-bottom: 6px; }
.gt-guide-step li ul { margin-top: 4px; }
.gt-guide-faq p { margin: 0; line-height: 1.8; }
:deep(.el-divider__text) { font-size: 13px; font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
:deep(.el-descriptions) { --el-descriptions-item-bordered-label-background: #fafafa; }
</style>
