<template>
  <div class="progress-board">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📊 项目进度看板</h2>
        <span class="gt-banner-sub" v-if="totalStats">
          完成率 {{ passedRate }}% · {{ totalStats.passed }}/{{ totalStats.total }} 已通过
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="board">看板</el-radio-button>
          <el-radio-button value="table">表格</el-radio-button>
          <el-radio-button value="brief">简报</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="handleExportBrief(false)" :loading="exportingBrief">📄 简报</el-button>
        <el-button size="small" @click="handleExportBrief(true)" :loading="exportingBrief">✨ AI简报</el-button>
        <el-button size="small" @click="handleExportAdj">📊 导出调整汇总</el-button>
        <el-button size="small" @click="handleCrossRefCheck" :loading="checkingRefs">🔗 交叉引用检查</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards" v-if="totalStats">
      <div class="stat-card" v-for="s in statCards" :key="s.label" :style="{ borderLeftColor: s.color }">
        <div class="stat-num">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>

    <!-- 看板视图 -->
    <div v-if="viewMode === 'board'" class="board-container">
      <div class="board-column" v-for="col in boardColumns" :key="col.key">
        <div class="board-col-header" :style="{ backgroundColor: col.bgColor }">
          <span>{{ col.label }}</span>
          <el-badge :value="columnItems(col.key).length" type="info" />
        </div>
        <div class="board-col-body">
          <div
            v-for="item in columnItems(col.key)"
            :key="item.id"
            class="board-card"
            @click="goToWorkpaper(item)"
          >
            <div class="card-code">{{ item.wp_code }}</div>
            <div class="card-name">{{ item.wp_name }}</div>
            <div class="card-meta">
              <el-tag size="small" effect="plain">{{ item.audit_cycle }}</el-tag>
            </div>
          </div>
          <div v-if="!columnItems(col.key).length" class="board-empty">暂无</div>
        </div>
      </div>
    </div>

    <!-- 表格视图 -->
    <div v-if="viewMode === 'table'" class="table-container">
      <el-table :data="boardItems" stripe style="width: 100%">
        <el-table-column label="底稿编号" prop="wp_code" width="120" sortable />
        <el-table-column label="底稿名称" prop="wp_name" min-width="200" />
        <el-table-column label="审计循环" prop="audit_cycle" width="100" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="bucketTagType(row.bucket)" size="small">{{ bucketLabel(row.bucket) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="goToWorkpaper(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 简报视图 -->
    <div v-if="viewMode === 'brief'" class="brief-container">
      <div v-if="briefLoading" v-loading="true" style="min-height: 200px" />
      <div v-else-if="briefData" class="brief-content" v-html="renderMarkdown(briefData.text_summary)" />
      <el-empty v-else description="点击上方按钮生成简报" />
    </div>

    <!-- 交叉引用检查弹窗 -->
    <el-dialog v-model="showCrossRefDialog" title="🔗 交叉引用检查结果" width="680" append-to-body>
      <div v-if="crossRefResult">
        <div style="margin-bottom: 12px">
          共 {{ crossRefResult.total_refs }} 个引用，发现 {{ crossRefResult.issue_count }} 个问题
          <el-tag v-if="crossRefResult.high_count" type="danger" size="small" style="margin-left: 8px">
            高风险 {{ crossRefResult.high_count }}
          </el-tag>
          <el-tag v-if="crossRefResult.medium_count" type="warning" size="small" style="margin-left: 4px">
            中风险 {{ crossRefResult.medium_count }}
          </el-tag>
        </div>
        <el-table :data="crossRefResult.issues" v-if="crossRefResult.issues.length" stripe size="small">
          <el-table-column label="严重性" width="80">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'high' ? 'danger' : 'warning'" size="small">
                {{ row.severity === 'high' ? '高' : '中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源底稿" prop="source_code" width="100" />
          <el-table-column label="引用底稿" prop="target_code" width="100" />
          <el-table-column label="问题描述" prop="message" min-width="250" />
        </el-table>
        <el-empty v-else description="所有交叉引用完整 ✅" />
      </div>
    </el-dialog>

    <!-- 客户沟通记录面板 -->
    <div class="comm-section" v-if="viewMode === 'board' || viewMode === 'table'">
      <div class="comm-header">
        <h3>💬 客户沟通记录</h3>
        <el-button size="small" type="primary" @click="showCommDialog = true">+ 新增</el-button>
      </div>
      <el-table :data="communications" stripe size="small" v-if="communications.length">
        <el-table-column label="日期" prop="date" width="100" />
        <el-table-column label="联系人" prop="contact_person" width="100" />
        <el-table-column label="主题" prop="topic" width="160" />
        <el-table-column label="内容" prop="content" min-width="200" show-overflow-tooltip />
        <el-table-column label="承诺事项" prop="commitments" width="160" show-overflow-tooltip />
        <el-table-column label="关联底稿" width="120">
          <template #default="{ row }">
            <span v-if="row.related_wp_codes?.length">{{ row.related_wp_codes.join(', ') }}</span>
            <span v-else style="color: #999">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="handleDeleteComm(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无沟通记录" :image-size="60" />
    </div>

    <!-- 新增沟通记录弹窗 -->
    <el-dialog v-model="showCommDialog" title="新增客户沟通记录" width="560" append-to-body>
      <el-form :model="commForm" label-width="80px">
        <el-form-item label="日期">
          <el-date-picker v-model="commForm.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="commForm.contact_person" placeholder="客户方联系人" />
        </el-form-item>
        <el-form-item label="主题">
          <el-input v-model="commForm.topic" placeholder="沟通主题" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="commForm.content" type="textarea" :rows="3" placeholder="沟通内容" />
        </el-form-item>
        <el-form-item label="承诺事项">
          <el-input v-model="commForm.commitments" type="textarea" :rows="2" placeholder="双方承诺事项" />
        </el-form-item>
        <el-form-item label="关联底稿">
          <el-input v-model="commForm.related_wp_codes_str" placeholder="底稿编号，逗号分隔，如 E1-1,E2-1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCommDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAddComm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getProgressBoard, getProgressBrief, checkCrossRefs,
  listCommunications, addCommunication, deleteCommunication,
  exportAdjustmentSummary,
  type ProgressBoardResult, type ProgressBrief, type CrossRefCheckResult,
  type BoardItem, type CommunicationRecord,
} from '@/services/pmApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)

const viewMode = ref<'board' | 'table' | 'brief'>('board')
const loading = ref(false)
const boardData = ref<ProgressBoardResult | null>(null)
const boardItems = computed(() => boardData.value?.board_items || [])
const totalStats = computed(() => boardData.value?.total)
const passedRate = computed(() => {
  const t = totalStats.value
  return t && t.total > 0 ? Math.round(t.passed / t.total * 100) : 0
})

const statCards = computed(() => {
  const t = totalStats.value
  if (!t) return []
  return [
    { label: '已通过', value: t.passed, color: '#67c23a' },
    { label: '待复核', value: t.pending_review, color: '#e6a23c' },
    { label: '编制中', value: t.in_progress, color: '#409eff' },
    { label: '未开始', value: t.not_started, color: '#909399' },
  ]
})

const boardColumns = [
  { key: 'not_started', label: '未开始', bgColor: '#f0f0f0' },
  { key: 'in_progress', label: '编制中', bgColor: '#e6f1fc' },
  { key: 'pending_review', label: '待复核', bgColor: '#fdf6ec' },
  { key: 'passed', label: '已通过', bgColor: '#e8f8e8' },
]

function columnItems(bucket: string) {
  return boardItems.value.filter(i => i.bucket === bucket)
}

function bucketLabel(b: string) {
  const m: Record<string, string> = { not_started: '未开始', in_progress: '编制中', pending_review: '待复核', passed: '已通过' }
  return m[b] || b
}
function bucketTagType(b: string) {
  const m: Record<string, string> = { not_started: 'info', in_progress: '', pending_review: 'warning', passed: 'success' }
  return m[b] || ''
}

function goToWorkpaper(item: BoardItem) {
  if (item.id) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: item.id } })
  } else {
    router.push(`/projects/${projectId.value}/workpapers`)
  }
}

// 简报
const briefData = ref<ProgressBrief | null>(null)
const briefLoading = ref(false)
const exportingBrief = ref(false)

async function handleExportBrief(polish = false) {
  exportingBrief.value = true
  try {
    briefData.value = await getProgressBrief(projectId.value, polish)
    viewMode.value = 'brief'
  } catch (e: any) {
    ElMessage.error('生成简报失败')
  } finally {
    exportingBrief.value = false
  }
}

function renderMarkdown(md: string): string {
  // 简单 Markdown 渲染
  return md
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '<br/>')
    .replace(/⚠️/g, '⚠️')
    .replace(/📋/g, '📋')
}

// 调整汇总导出
async function handleExportAdj() {
  const year = new Date().getFullYear() - 1
  try {
    await exportAdjustmentSummary(projectId.value, year)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

// 交叉引用检查
const checkingRefs = ref(false)
const showCrossRefDialog = ref(false)
const crossRefResult = ref<CrossRefCheckResult | null>(null)

async function handleCrossRefCheck() {
  checkingRefs.value = true
  try {
    crossRefResult.value = await checkCrossRefs(projectId.value)
    showCrossRefDialog.value = true
  } catch {
    ElMessage.error('检查失败')
  } finally {
    checkingRefs.value = false
  }
}

// 客户沟通记录
const communications = ref<CommunicationRecord[]>([])
const showCommDialog = ref(false)
const commForm = reactive({
  date: new Date().toISOString().slice(0, 10),
  contact_person: '',
  topic: '',
  content: '',
  commitments: '',
  related_wp_codes_str: '',
})

async function loadComms() {
  try {
    communications.value = await listCommunications(projectId.value)
  } catch { /* ignore */ }
}

async function handleAddComm() {
  try {
    await addCommunication(projectId.value, {
      ...commForm,
      related_wp_codes: commForm.related_wp_codes_str.split(',').map(s => s.trim()).filter(Boolean),
    })
    ElMessage.success('保存成功')
    showCommDialog.value = false
    Object.assign(commForm, { contact_person: '', topic: '', content: '', commitments: '', related_wp_codes_str: '' })
    await loadComms()
  } catch {
    ElMessage.error('保存失败')
  }
}

async function handleDeleteComm(commId: string) {
  await ElMessageBox.confirm('确认删除此沟通记录？', '确认')
  try {
    await deleteCommunication(projectId.value, commId)
    ElMessage.success('已删除')
    await loadComms()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function loadData() {
  loading.value = true
  try {
    boardData.value = await getProgressBoard(projectId.value)
  } catch (e: any) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadData(), loadComms()])
})
</script>

<style scoped>
.progress-board { padding: 0; }
.gt-page-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20px 24px; margin-bottom: 16px;
  background: linear-gradient(135deg, var(--gt-color-primary, #4b2d77) 0%, #6b4d97 100%);
  border-radius: 8px; color: #fff;
}
.gt-page-banner h2 { margin: 0; font-size: 18px; font-weight: 600; }
.gt-banner-sub { font-size: 13px; opacity: 0.85; margin-top: 4px; display: block; }
.gt-banner-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.stat-cards {
  display: flex; gap: 12px; margin-bottom: 20px;
}
.stat-card {
  flex: 1; padding: 16px 20px; background: #fff; border-radius: 8px;
  border-left: 4px solid #ccc; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.stat-num { font-size: 28px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 13px; color: #666; margin-top: 4px; }

.board-container {
  display: flex; gap: 12px; min-height: 400px;
}
.board-column {
  flex: 1; background: #fafafa; border-radius: 8px; overflow: hidden;
  display: flex; flex-direction: column;
}
.board-col-header {
  padding: 10px 14px; font-weight: 600; font-size: 14px;
  display: flex; justify-content: space-between; align-items: center;
}
.board-col-body {
  flex: 1; padding: 8px; overflow-y: auto; max-height: 500px;
  display: flex; flex-direction: column; gap: 6px;
}
.board-card {
  background: #fff; border-radius: 6px; padding: 10px 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); cursor: pointer;
  transition: box-shadow 0.15s;
}
.board-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.card-code { font-size: 12px; color: #999; font-family: monospace; }
.card-name { font-size: 13px; margin-top: 2px; color: #333; }
.card-meta { margin-top: 6px; }
.board-empty { text-align: center; color: #ccc; padding: 20px; font-size: 13px; }

.brief-container { padding: 20px; background: #fff; border-radius: 8px; min-height: 300px; }
.brief-content { line-height: 1.8; }
.brief-content :deep(h2) { font-size: 18px; margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
.brief-content :deep(h3) { font-size: 15px; margin-top: 16px; }
.brief-content :deep(ul) { padding-left: 20px; }
.brief-content :deep(li) { margin-bottom: 4px; }
.brief-content :deep(strong) { color: var(--gt-color-primary, #4b2d77); }

.table-container { margin-bottom: 20px; }

.comm-section {
  margin-top: 24px; padding: 16px 20px; background: #fff; border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.comm-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.comm-header h3 { margin: 0; font-size: 15px; }
</style>
