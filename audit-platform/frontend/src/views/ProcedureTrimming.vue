<template>
  <div class="gt-procedure gt-fade-in">
    <!-- 顶部工具栏 -->
    <div class="gt-proc-toolbar">
      <div class="gt-proc-toolbar__left">
        <h2 class="gt-proc-toolbar__title">审计程序裁剪</h2>
        <el-tag size="small" type="info">{{ projectId.slice(0, 8) }}</el-tag>
      </div>
      <div class="gt-proc-toolbar__right">
        <el-button size="small" @click="resetAll">🔄 恢复初始</el-button>
        <el-button size="small" @click="showRefDialog = true">📋 参照其他项目</el-button>
        <el-button size="small" type="warning" @click="onSmartTrim">🤖 一键智能裁剪</el-button>
        <el-button size="small" type="primary" @click="saveTrim" :loading="saving">💾 保存裁剪</el-button>
      </div>
    </div>

    <!-- 统计卡片（点击联动筛选） -->
    <div class="gt-proc-stats">
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === '' }" @click="statsFilter = ''">
        <div class="gt-proc-stat-card__num">{{ progressStats.total }}</div>
        <div class="gt-proc-stat-card__label">总程序</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'execute' }" @click="statsFilter = statsFilter === 'execute' ? '' : 'execute'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-primary)">{{ progressStats.execute }}</div>
        <div class="gt-proc-stat-card__label">保留执行</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'trimmed' }" @click="statsFilter = statsFilter === 'trimmed' ? '' : 'trimmed'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-coral)">{{ progressStats.trimmed }}</div>
        <div class="gt-proc-stat-card__label">已裁剪</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'custom' }" @click="statsFilter = statsFilter === 'custom' ? '' : 'custom'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-success)">{{ progressStats.custom }}</div>
        <div class="gt-proc-stat-card__label">自定义新增</div>
      </div>
      <div class="gt-proc-stat-card gt-proc-stat-card--progress">
        <el-progress
          type="circle"
          :percentage="progressStats.total > 0 ? Math.round(progressStats.execute / progressStats.total * 100) : 0"
          :width="50"
          :stroke-width="5"
        />
        <div class="gt-proc-stat-card__label">执行率</div>
      </div>
    </div>

    <!-- 循环 Tab -->
    <div class="gt-proc-cycle-bar">
      <el-tabs v-model="activeCycle" @tab-change="loadProcedures" class="gt-proc-tabs">
        <el-tab-pane v-for="c in cycles" :key="c.code" :label="c.label" :name="c.code" />
      </el-tabs>
    </div>

    <!-- 表格工具栏 -->
    <div class="gt-proc-table-toolbar">
      <span class="gt-proc-table-toolbar__label">{{ activeCycle }} 循环 · {{ filteredProcedures.length }} 个程序</span>
      <div class="gt-proc-table-toolbar__actions">
        <el-button size="small" type="primary" text @click="batchSetAll('execute')">✓ 全部执行</el-button>
        <el-button size="small" type="danger" text @click="batchSetAll('not_applicable')">✗ 全部不适用</el-button>
        <el-divider direction="vertical" />
        <el-button size="small" @click="addCustom">+ 新增程序</el-button>
      </div>
    </div>

    <!-- 程序列表 -->
    <div class="gt-proc-table-wrap">
      <el-table
        :data="filteredProcedures"
        v-loading="loading"
        border
        stripe
        style="width: 100%; font-size: 13px"
        max-height="calc(100vh - 340px)"
        row-key="id"
      >
        <el-table-column prop="procedure_code" label="编号" min-width="100" resizable sortable />
        <el-table-column prop="procedure_name" label="程序名称" min-width="280" resizable show-overflow-tooltip />
        <el-table-column label="适用性" width="140" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row._applicable"
              active-text="执行"
              inactive-text="裁剪"
              :active-value="true"
              :inactive-value="false"
              @change="onApplicableChange(row)"
              inline-prompt
              style="--el-switch-on-color: var(--gt-color-primary); --el-switch-off-color: var(--gt-color-coral)"
            />
          </template>
        </el-table-column>
        <el-table-column label="裁剪理由" min-width="200" resizable>
          <template #default="{ row }">
            <el-input
              v-if="!row._applicable"
              v-model="row.skip_reason"
              placeholder="填写裁剪理由..."
              size="small"
              clearable
            />
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="wp_code" label="关联底稿" width="100" resizable />
        <el-table-column label="委派执行人" width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="row._applicable"
              v-model="row.assigned_to"
              placeholder="选择执行人"
              size="small"
              clearable
              filterable
              style="width: 100%"
              @change="onAssigneeChange(row)"
            >
              <el-option
                v-for="m in teamMembers"
                :key="m.staff_id"
                :label="m.staff_name + (m.role_label ? ` (${m.role_label})` : '')"
                :value="m.staff_id"
              />
            </el-select>
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_custom ? 'success' : 'info'">
              {{ row.is_custom ? '自定义' : '模板' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row._applicable && row.wp_id"
              size="small"
              text
              type="primary"
              @click="enterProgramConsole(row)"
            >
              程序裁剪 ›
            </el-button>
            <el-tooltip
              v-else-if="row._applicable && !row.wp_id"
              content="该程序底稿尚未生成，请先生成底稿"
              placement="top"
            >
              <el-button size="small" text disabled>未生成</el-button>
            </el-tooltip>
            <el-button v-if="row.is_custom" size="small" text type="danger" @click="removeCustom(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 底部提示 -->
    <div class="gt-proc-footer-tip">
      💡 双层裁剪：此处粗筛底稿是否执行 + 委派执行人；点「程序裁剪 ›」进入底稿程序表控制台对每条审计程序细裁。保存后保留执行的程序即进入待执行底稿库。
    </div>

    <!-- 新增自定义程序弹窗 -->
    <el-dialog append-to-body v-model="showAddCustomDialog" title="新增自定义程序" width="520px">
      <el-form :model="customForm" label-width="100px">
        <el-form-item label="程序名称" required>
          <el-input v-model="customForm.name" placeholder="如：XX 专项核查程序" />
        </el-form-item>
        <el-form-item label="程序编码">
          <el-input v-model="customForm.code" placeholder="可选，留空自动生成（如 D-C01）" />
        </el-form-item>
        <el-form-item label="底稿模板">
          <div class="gt-proc-custom-template-area">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept=".xlsx,.xls"
              :on-change="onCustomFileChange"
              :file-list="customForm.fileList"
            >
              <el-button size="small" type="primary">📄 上传已有文件</el-button>
            </el-upload>
            <span class="gt-proc-custom-template-or">或</span>
            <el-button size="small" @click="downloadBlankTemplate" :loading="downloadingTemplate">
              📥 下载空白模板
            </el-button>
          </div>
          <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 6px">
            下载空白模板包含：编制要求说明 + 数据表（顶部编制信息表头已自动配齐：被审计单位/编制人/复核人/截止日/索引号，并预填试算表科目余额）
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddCustomDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!customForm.name.trim()" @click="submitCustomProcedure">
          {{ customForm.fileList.length ? '创建并上传模板' : '仅创建程序' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 参照弹窗 -->
    <el-dialog append-to-body v-model="showRefDialog" title="参照其他项目程序" width="480px">
      <p style="font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 16px">
        从已有项目复制程序裁剪方案，适用于同类型客户或续聘项目。
      </p>
      <el-form label-width="80px">
        <el-form-item label="参照项目">
          <el-select
            v-model="refProjectId"
            filterable
            placeholder="搜索并选择参照项目"
            style="width: 100%"
          >
            <el-option
              v-for="p in projectOptions"
              :key="p.id"
              :label="p.name || p.client_name || p.id"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRefDialog = false">取消</el-button>
        <el-button type="primary" @click="applyRef" :disabled="!refProjectId">应用方案</el-button>
      </template>
    </el-dialog>

    <!-- 智能裁剪确认弹窗 -->
    <el-dialog append-to-body v-model="showSmartTrimDialog" title="智能裁剪" width="560px">
      <p style="font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 12px">
        系统将根据以下规则自动裁剪不适用的程序：
      </p>
      <ul class="gt-proc-smart-rules">
        <li><strong>保留</strong>：A 完成阶段 / S 专项程序（必须执行）</li>
        <li><strong>保留</strong>：标记为"必须"的程序（is_mandatory）</li>
        <li><strong>保留</strong>：已有执行进度的程序（进行中/已完成）</li>
        <li><strong>保留</strong>：已手动设置裁剪理由的程序</li>
        <li><strong>裁剪</strong>：B/C/D~N 中"非必须 + 未开始 + 无手动理由"的程序</li>
      </ul>

      <!-- 裁剪范围选择 -->
      <div class="gt-proc-smart-scope">
        <div class="gt-proc-smart-scope__title">裁剪范围：</div>
        <el-radio-group v-model="smartTrimScope" style="margin-bottom: 8px">
          <el-radio value="all">全部循环（一键裁剪所有）</el-radio>
          <el-radio value="current">仅当前循环（{{ activeCycle }}）</el-radio>
          <el-radio value="custom">自定义选择循环</el-radio>
        </el-radio-group>
        <div v-if="smartTrimScope === 'custom'" class="gt-proc-smart-scope__cycles">
          <el-checkbox-group v-model="smartTrimCycles">
            <el-checkbox v-for="c in cycles.filter(x => x.code !== 'A' && x.code !== 'S')" :key="c.code" :value="c.code" :label="c.label" />
          </el-checkbox-group>
        </div>
      </div>

      <p style="font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 8px">
        💡 裁剪后可逐条检查并恢复，重要循环（如收入/货币资金）的穿行测试建议手动恢复
      </p>
      <template #footer>
        <el-button @click="showSmartTrimDialog = false">取消</el-button>
        <el-button type="warning" @click="confirmSmartTrim">确认一键裁剪</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getProcedures, updateProcedureTrim, initProcedures,
  addCustomProcedure, applyProcedureScheme, listProjects,
  assignProcedures,
} from '@/services/commonApi'
import { listAssignments } from '@/services/staffApi'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)

const cycles = [
  { code: 'B', label: 'B 初步业务' }, { code: 'C', label: 'C 控制测试' },
  { code: 'D', label: 'D 收入' }, { code: 'E', label: 'E 货币资金' },
  { code: 'F', label: 'F 存货' }, { code: 'G', label: 'G 投资' },
  { code: 'H', label: 'H 固定资产' }, { code: 'I', label: 'I 无形资产' },
  { code: 'J', label: 'J 职工薪酬' }, { code: 'K', label: 'K 管理' },
  { code: 'L', label: 'L 债务' }, { code: 'M', label: 'M 权益' },
  { code: 'N', label: 'N 税金' }, { code: 'A', label: 'A 完成阶段' },
  { code: 'S', label: 'S 专项' },
]

const activeCycle = ref('D')
const procedures = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const showRefDialog = ref(false)
const showSmartTrimDialog = ref(false)
const smartTrimScope = ref<'all' | 'current' | 'custom'>('all')
const smartTrimCycles = ref<string[]>([])
const refProjectId = ref('')
const projectOptions = ref<any[]>([])
const statsFilter = ref('') // '' | 'execute' | 'trimmed' | 'custom'
const teamMembers = ref<{ staff_id: string; staff_name: string; role_label?: string }[]>([])
let originalSnapshot: any[] = [] // 用于恢复初始状态

const filteredProcedures = computed(() => {
  if (!statsFilter.value) return procedures.value
  if (statsFilter.value === 'execute') return procedures.value.filter(p => p._applicable)
  if (statsFilter.value === 'trimmed') return procedures.value.filter(p => !p._applicable)
  if (statsFilter.value === 'custom') return procedures.value.filter(p => p.is_custom)
  return procedures.value
})
const progressStats = computed(() => {
  const procs = procedures.value
  const total = procs.length
  const execute = procs.filter(p => p._applicable).length
  const trimmed = procs.filter(p => !p._applicable).length
  const custom = procs.filter(p => p.is_custom).length
  return { total, execute, trimmed, custom }
})

// 加载程序列表
async function loadProcedures() {
  loading.value = true
  try {
    let procs = await getProcedures(projectId.value, activeCycle.value)
    if (!procs || procs.length === 0) {
      procs = await initProcedures(projectId.value, activeCycle.value)
    }
    // 转换 status → _applicable 布尔值
    procedures.value = (procs || []).map((p: any) => ({
      ...p,
      _applicable: p.status !== 'not_applicable' && p.status !== 'skip',
      is_custom: p.is_custom || p.source === 'custom',
      assigned_to: p.assigned_to || null,
      wp_id: p.wp_id || null,
    }))
    // 保存初始快照用于恢复
    originalSnapshot = JSON.parse(JSON.stringify(procedures.value))
  } finally { loading.value = false }
}

// 适用性切换
function onApplicableChange(row: any) {
  row.status = row._applicable ? 'execute' : 'not_applicable'
  if (row._applicable) row.skip_reason = ''
}

// 恢复初始状态
function resetAll() {
  ElMessageBox.confirm('确定恢复到初始状态？所有未保存的修改将丢失。', '恢复初始', {
    confirmButtonText: '确定恢复',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    procedures.value = JSON.parse(JSON.stringify(originalSnapshot))
    statsFilter.value = ''
    ElMessage.success('已恢复初始状态')
  }).catch(() => {})
}

// 批量设置
function batchSetAll(status: 'execute' | 'not_applicable') {
  for (const p of procedures.value) {
    p._applicable = status === 'execute'
    p.status = status
    if (status === 'execute') p.skip_reason = ''
  }
}

// 保存裁剪
async function saveTrim() {
  // 检查裁剪的程序是否都填了理由
  const noReason = procedures.value.filter(p => !p._applicable && !p.skip_reason?.trim())
  if (noReason.length > 0) {
    ElMessage.warning(`${noReason.length} 个裁剪程序未填写理由，建议补充`)
  }
  saving.value = true
  try {
    await updateProcedureTrim(projectId.value, activeCycle.value,
      procedures.value.map(p => ({ id: p.id, status: p._applicable ? 'execute' : 'not_applicable', skip_reason: p.skip_reason })))
    ElMessage.success('裁剪已保存，保留执行的程序已加入待执行底稿库')
  } catch (e: any) {
    handleApiError(e, '保存裁剪')
  } finally { saving.value = false }
}

// 新增自定义程序
const showAddCustomDialog = ref(false)
const downloadingTemplate = ref(false)
const customForm = ref<{ name: string; code: string; fileList: any[] }>({ name: '', code: '', fileList: [] })

function addCustom() {
  customForm.value = { name: '', code: '', fileList: [] }
  showAddCustomDialog.value = true
}

function onCustomFileChange(file: any) {
  customForm.value.fileList = [file]
}

async function downloadBlankTemplate() {
  const name = customForm.value.name.trim() || '自定义底稿'
  downloadingTemplate.value = true
  try {
    const response = await http.get(
      `/api/projects/${projectId.value}/procedures/${activeCycle.value}/blank-template`,
      {
        params: { procedure_name: name },
        responseType: 'blob',
      },
    )
    // http.ts blob 模式返回完整 response
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `底稿模板_${activeCycle.value}_${name}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('模板已下载，编辑后可上传回来')
  } catch (e: any) {
    handleApiError(e, '下载模板')
  } finally {
    downloadingTemplate.value = false
  }
}

async function submitCustomProcedure() {
  const name = customForm.value.name.trim()
  if (!name) return

  try {
    if (customForm.value.fileList.length > 0) {
      // 带模板文件：调用 custom-with-template 接口
      const params = new URLSearchParams({
        procedure_name: name,
        ...(customForm.value.code ? { procedure_code: customForm.value.code } : {}),
      })
      const { data: result } = await http.post(
        `/api/projects/${projectId.value}/procedures/${activeCycle.value}/custom-with-template?${params}`,
      )
      procedures.value.push({
        ...result,
        _applicable: true,
        is_custom: true,
        procedure_name: name,
        procedure_code: result.wp_code || customForm.value.code,
      })

      // 上传文件到底稿存储（如果有 wp_index_id）
      if (result.wp_index_id && customForm.value.fileList[0]?.raw) {
        const formData = new FormData()
        formData.append('file', customForm.value.fileList[0].raw)
        try {
          await http.post(
            `/api/projects/${projectId.value}/workpapers/${result.wp_index_id}/upload`,
            formData,
            { headers: { 'Content-Type': 'multipart/form-data' } },
          )
          ElMessage.success(`已创建自定义程序 ${result.wp_code} 并上传模板文件`)
        } catch {
          ElMessage.warning(`程序已创建（${result.wp_code}），但模板上传失败，可稍后在底稿列表中重新上传`)
        }
      } else {
        ElMessage.success(`已创建自定义程序 ${result.wp_code}`)
      }
    } else {
      // 不带文件：调用原接口
      const newProc = await addCustomProcedure(projectId.value, activeCycle.value, {
        procedure_name: name,
        procedure_code: customForm.value.code || undefined,
      })
      procedures.value.push({ ...newProc, _applicable: true, is_custom: true })
      ElMessage.success('已添加自定义程序（无模板文件，可稍后在底稿列表中上传）')
    }
    showAddCustomDialog.value = false
  } catch (e: any) { handleApiError(e, '新增程序') }
}

// 删除自定义程序
function removeCustom(row: any) {
  const idx = procedures.value.indexOf(row)
  if (idx >= 0) procedures.value.splice(idx, 1)
}

// 加载项目团队成员（委派候选人）
async function loadTeamMembers() {
  try {
    const list = await listAssignments(projectId.value)
    const ROLE_LABELS: Record<string, string> = {
      partner: '合伙人', signing_partner: '签字合伙人', manager: '项目经理',
      auditor: '审计员', reviewer: '复核', eqcr: 'EQCR',
    }
    teamMembers.value = (Array.isArray(list) ? list : [])
      .filter((a: any) => a.staff_id)
      .map((a: any) => ({
        staff_id: a.staff_id,
        staff_name: a.staff_name || a.staff_id.slice(0, 8),
        role_label: ROLE_LABELS[a.role] || a.role || '',
      }))
  } catch {
    teamMembers.value = []
  }
}

// 委派执行人变更 → 立即持久化
async function onAssigneeChange(row: any) {
  if (!row.id) return
  try {
    await assignProcedures(projectId.value, [{ procedure_id: row.id, staff_id: row.assigned_to }])
    const member = teamMembers.value.find(m => m.staff_id === row.assigned_to)
    ElMessage.success(row.assigned_to ? `已委派给 ${member?.staff_name || '执行人'}` : '已取消委派')
  } catch (e: any) {
    handleApiError(e, '委派')
  }
}

// 进入该底稿的程序表控制台做逐条程序裁剪
function enterProgramConsole(row: any) {
  if (!row.wp_id) {
    ElMessage.warning('该程序底稿尚未生成，请先生成底稿')
    return
  }
  router.push({
    path: `/projects/${projectId.value}/workpapers/${row.wp_id}/edit`,
  })
}

// 智能裁剪
function onSmartTrim() {
  showSmartTrimDialog.value = true
}
async function confirmSmartTrim() {
  // 确定裁剪范围
  let targetCycles: Set<string>
  if (smartTrimScope.value === 'current') {
    targetCycles = new Set([activeCycle.value])
  } else if (smartTrimScope.value === 'custom') {
    if (smartTrimCycles.value.length === 0) {
      ElMessage.warning('请至少选择一个循环')
      return
    }
    targetCycles = new Set(smartTrimCycles.value)
  } else {
    // all — 除 A/S 外全部
    targetCycles = new Set(cycles.filter(c => c.code !== 'A' && c.code !== 'S').map(c => c.code))
  }

  const protectedCycles = new Set(['A', 'S'])
  let trimCount = 0
  let keepCount = 0

  for (const p of procedures.value) {
    // 判断该程序属于哪个循环
    const cycleCode = (p.procedure_code || p.wp_code || '').charAt(0).toUpperCase()

    // 不在目标范围内的跳过
    if (!targetCycles.has(cycleCode)) continue
    // 跳过已手动裁剪的
    if (!p._applicable) continue
    // 跳过必须程序
    if (p.is_mandatory) { keepCount++; continue }
    // 跳过 A/S 类
    if (protectedCycles.has(cycleCode)) { keepCount++; continue }
    // 跳过已有执行进度的
    if (p.execution_status === 'in_progress' || p.execution_status === 'completed' || p.execution_status === 'reviewed') {
      keepCount++; continue
    }
    // 跳过已手动设置理由的
    if (p.skip_reason) continue

    // 符合裁剪条件
    p._applicable = false
    p.status = 'not_applicable'
    p.skip_reason = `智能裁剪：${cycleCode}循环该程序非必须，可根据风险评估结果决定是否恢复`
    trimCount++
  }

  showSmartTrimDialog.value = false
  const scopeLabel = smartTrimScope.value === 'all' ? '全部循环' :
    smartTrimScope.value === 'current' ? `${activeCycle.value} 循环` :
    `${smartTrimCycles.value.join('/')} 循环`
  if (trimCount > 0) {
    ElMessage.success(`[${scopeLabel}] 已智能裁剪 ${trimCount} 个程序（保留 ${keepCount} 个必须/进行中程序），请检查后保存`)
  } else {
    ElMessage.info(`[${scopeLabel}] 未发现可裁剪的程序`)
  }
}

// 参照其他项目
async function applyRef() {
  if (!refProjectId.value) return
  try {
    await applyProcedureScheme(projectId.value, activeCycle.value, refProjectId.value)
    ElMessage.success('已应用参照方案')
    showRefDialog.value = false
    await loadProcedures()
  } catch (e: any) { handleApiError(e, '应用参照') }
}

onMounted(async () => {
  await loadProcedures()
  await loadTeamMembers()
  try {
    const list = await listProjects()
    projectOptions.value = Array.isArray(list) ? list : []
  } catch { /* 静默 */ }
})
</script>

<style scoped>
.gt-procedure { padding: 16px 20px; height: 100%; display: flex; flex-direction: column; }

/* 工具栏 */
.gt-proc-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.gt-proc-toolbar__left { display: flex; align-items: center; gap: 10px; }
.gt-proc-toolbar__title { margin: 0; font-size: 18px; font-weight: 700; color: var(--gt-color-text-primary); }
.gt-proc-toolbar__right { display: flex; gap: 8px; }

/* 统计卡片 */
.gt-proc-stats {
  display: flex; gap: 12px; margin-bottom: 14px;
}
.gt-proc-stat-card {
  flex: 1; text-align: center; padding: 12px 8px;
  background: var(--gt-color-bg-white); border-radius: 10px;
  border: 2px solid var(--gt-color-border-light, #f0f0f0);
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  cursor: pointer; transition: all 0.15s;
}
.gt-proc-stat-card:hover { border-color: var(--gt-color-primary); }
.gt-proc-stat-card.is-active {
  border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #f0ebff);
  box-shadow: 0 0 0 3px rgba(103, 80, 164, 0.1);
}
.gt-proc-stat-card--progress { display: flex; align-items: center; justify-content: center; gap: 10px; }
.gt-proc-stat-card__num { font-size: 22px; font-weight: 800; color: var(--gt-color-text-primary); line-height: 1.2; }
.gt-proc-stat-card__label { font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }

/* 循环 Tab */
.gt-proc-cycle-bar {
  margin-bottom: 0; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-proc-tabs { }
:deep(.gt-proc-tabs .el-tabs__header) { margin: 0; }
:deep(.gt-proc-tabs .el-tabs__nav-wrap::after) { display: none; }

/* 表格工具栏 */
.gt-proc-table-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; margin-bottom: 8px;
  background: var(--gt-color-bg, #fafafa); border-radius: 8px;
}
.gt-proc-table-toolbar__label { font-size: 13px; font-weight: 600; color: var(--gt-color-text-secondary); }
.gt-proc-table-toolbar__actions { display: flex; align-items: center; gap: 4px; }

/* 表格区 */
.gt-proc-table-wrap {
  flex: 1; min-height: 0; background: var(--gt-color-bg-white);
  border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  overflow: hidden;
}
.gt-proc-text-muted { color: var(--gt-color-text-placeholder); font-size: 12px; }

/* 底部提示 */
.gt-proc-footer-tip {
  margin-top: 12px; padding: 10px 14px; font-size: 12px;
  color: var(--gt-color-text-secondary); background: var(--gt-color-primary-bg, #f8f5ff);
  border-radius: 8px; border-left: 3px solid var(--gt-color-primary);
}

/* 智能裁剪规则列表 */
.gt-proc-smart-rules {
  padding-left: 20px; margin: 0; font-size: 13px; color: var(--gt-color-text-primary); line-height: 2;
}
.gt-proc-smart-scope {
  margin-top: 16px; padding: 12px 14px; background: var(--gt-color-bg, #fafafa);
  border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-proc-smart-scope__title { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px; }
.gt-proc-smart-scope__cycles { margin-top: 8px; padding: 8px 12px; background: var(--gt-color-bg-white); border-radius: 6px; }

/* 自定义模板上传区 */
.gt-proc-custom-template-area {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.gt-proc-custom-template-or {
  font-size: 12px; color: var(--gt-color-text-tertiary); font-style: italic;
}
</style>
