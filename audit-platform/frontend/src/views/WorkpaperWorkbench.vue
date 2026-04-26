<template>
  <div class="gt-wp-bench gt-fade-in">
    <!-- ҳ -->
    <div class="gt-wpb-banner">
      <div class="gt-wpb-banner-text">
        <h2>׸幤̨</h2>
        <p>{{ mappings.length }} Ŀ׸  ͸ı븽ע</p>
      </div>
      <div class="gt-wpb-banner-actions">
        <el-button size="small" @click="refreshAll" :loading="loading" round>ˢ</el-button>
        <el-button size="small" @click="onBatchPrefill" :loading="prefillLoading" round>Ԥ</el-button>
        <el-button size="small" @click="onSmartRecommend" :loading="recommendLoading" round>
          Ƽ׸
        </el-button>
      </div>
    </div>

    <!-- Ƽ -->
    <div v-if="recommendations.length > 0" class="gt-wpb-recommend-panel gt-fade-in">
      <div class="gt-wpb-recommend-header">
        <h4 class="gt-wpb-section-title">
          Ƽ
          <el-badge :value="recommendations.length" :max="99" type="primary" style="margin-left: 6px" />
        </h4>
        <el-button size="small" text @click="recommendations = []"></el-button>
        <el-button size="small" type="primary" @click="onGenerateRecommended" :loading="generatingWps">
          һƼ׸
        </el-button>
      </div>
      <div class="gt-wpb-recommend-list">
        <div v-for="rec in recommendations" :key="rec.wp_code" class="gt-wpb-recommend-item">
          <div class="gt-wpb-rec-left">
            <span class="gt-wpb-rec-code">{{ rec.wp_code }}</span>
            <span class="gt-wpb-rec-name">{{ rec.wp_name || rec.account_name }}</span>
          </div>
          <div class="gt-wpb-rec-right">
            <el-tag size="small" :type="rec.priority === 'required' ? 'danger' : 'info'" round>
              {{ rec.priority === 'required' ? 'ر' : '' }}
            </el-tag>
            <span class="gt-wpb-rec-reason">{{ rec.reason }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="gt-wpb-body">
      <!-- ѭĵ׸ -->
      <div class="gt-wpb-tree">
        <div class="gt-wpb-tree-header">
          <el-input v-model="searchText" placeholder="׸..." size="small" clearable />
          <div class="gt-wpb-tree-filters">
            <el-checkbox v-model="onlyMine" size="small">ҵ</el-checkbox>
            <el-select v-model="filterStatus" size="small" placeholder="״̬" clearable style="width: 80px">
              <el-option label="" value="pending" />
              <el-option label="" value="in_progress" />
              <el-option label="" value="review" />
              <el-option label="ͨ" value="passed" />
            </el-select>
          </div>
          <!-- ȸ -->
          <div class="gt-wpb-tree-progress">
            <span class="gt-wpb-prog-item gt-wpb-prog--done">{{ doneCount }}</span>
            <span class="gt-wpb-prog-sep">/</span>
            <span class="gt-wpb-prog-item">{{ totalCount }}</span>
            <el-progress :percentage="progressPct" :stroke-width="4" :show-text="false" style="flex:1; margin-left: 8px" />
          </div>
        </div>
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          :filter-node-method="filterNode"
          ref="treeRef"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <div class="gt-wpb-node">
              <span class="gt-wpb-node-icon" v-if="data.statusIcon">{{ data.statusIcon }}</span>
              <span class="gt-wpb-node-label">{{ data.label }}</span>
              <span v-if="data.assignee" class="gt-wpb-node-assignee">{{ data.assignee }}</span>
            </div>
          </template>
        </el-tree>
      </div>

      <!-- ׸Ԥ -->
      <div class="gt-wpb-detail">
        <template v-if="selectedMapping">
          <div class="gt-wpb-detail-header">
            <div class="gt-wpb-detail-title-row">
              <h3>{{ selectedMapping.wp_code }} {{ selectedMapping.wp_name }}</h3>
              <el-tag :type="selectedMapping.note_section ? 'success' : 'info'" size="small" effect="plain" round>
                {{ selectedMapping.account_name }}
              </el-tag>
            </div>
            <div class="gt-wpb-detail-tags">
              <el-tag size="small" round>{{ selectedMapping.cycle }}ѭ</el-tag>
              <el-tag v-if="selectedMapping.report_row" size="small" type="info" round> {{ selectedMapping.report_row }}</el-tag>
              <el-tag v-if="selectedMapping.note_section" size="small" type="warning" round>ע {{ selectedMapping.note_section }}</el-tag>
            </div>
          </div>

          <!-- ָ̲ʾ -->
          <div class="gt-wpb-workflow">
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--done': true }">
              <div class="gt-wpb-step-dot"></div>
              <span></span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--done': !!prefillData }">
              <div class="gt-wpb-step-dot"></div>
              <span>Ԥ</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--active': !!prefillData }">
              <div class="gt-wpb-step-dot"></div>
              <span>Ƶ׸</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step">
              <div class="gt-wpb-step-dot"></div>
              <span></span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step">
              <div class="gt-wpb-step-dot"></div>
              <span>鵵</span>
            </div>
          </div>

          <!-- ĸָ꿨Ƭ -->
          <div class="gt-wpb-data-section">
            <h4 class="gt-wpb-section-title"></h4>
            <div v-if="prefillData" class="gt-wpb-prefill-cards gt-stagger">
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--muted">
                <span class="gt-wpb-pf-label">ڳ</span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(totalOpening) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--primary">
                <span class="gt-wpb-pf-label">δ</span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(prefillData.total_unadjusted) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--teal">
                <span class="gt-wpb-pf-label">Ӱ</span>
                <span class="gt-wpb-pf-value" :class="{ 'gt-wpb-pf-value--diff': totalAdj !== '0' }">{{ fmtAmt(totalAdj) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--success">
                <span class="gt-wpb-pf-label"></span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(prefillData.total_audited) }}</span>
              </div>
            </div>
            <el-skeleton v-else-if="prefillLoading" :rows="2" animated />

            <!-- Ŀϸ -->
            <el-table v-if="prefillData?.accounts?.length" :data="prefillData.accounts" size="small" border stripe style="margin-top: 12px" class="gt-wpb-acct-table">
              <el-table-column prop="code" label="Ŀ" width="90" />
              <el-table-column prop="name" label="" min-width="120" show-overflow-tooltip />
              <el-table-column label="ڳ" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.opening) }}</template>
              </el-table-column>
              <el-table-column label="δ" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.unadjusted) }}</template>
              </el-table-column>
              <el-table-column label="" width="90" align="right">
                <template #default="{ row }">
                  <span :style="{ color: adjVal(row) !== 0 ? '#FF5149' : '#999' }">{{ fmtAmt(adjVal(row)) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="" width="110" align="right">
                <template #default="{ row }">
                  <span style="font-weight: 700; color: var(--gt-color-primary); cursor: pointer; text-decoration: underline dotted"
                    @dblclick="onDrillToAdjustment(row)"
                    title="˫鿴">{{ fmtAmt(row.audited) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!--  -->
          <div class="gt-wpb-data-section">
            <h4 class="gt-wpb-section-title"></h4>
            <div class="gt-wpb-attach-list" v-if="attachments.length">
              <div v-for="att in attachments" :key="att.id" class="gt-wpb-attach-item">
                <div class="gt-wpb-attach-icon">{{ getFileIcon(att.file_type) }}</div>
                <div class="gt-wpb-attach-info">
                  <span class="gt-wpb-attach-name">{{ att.file_name }}</span>
                  <span class="gt-wpb-attach-meta">
                    {{ att.attachment_type || 'ͨ' }}  {{ formatSize(att.file_size) }}
                    <span v-if="att.ocr_status === 'success'" class="gt-wpb-ocr-badge gt-wpb-ocr--ok">OCR?</span>
                    <span v-else-if="att.ocr_status === 'processing'" class="gt-wpb-ocr-badge gt-wpb-ocr--ing">OCR</span>
                    <span v-else-if="att.ocr_status === 'failed'" class="gt-wpb-ocr-badge gt-wpb-ocr--fail">OCR?</span>
                  </span>
                </div>
                <el-button size="small" text type="primary" @click="onPreviewAttachment(att.id)">Ԥ</el-button>
              </div>
            </div>
            <div v-else class="gt-wpb-attach-empty">
              <span>޹</span>
            </div>
            <div class="gt-wpb-attach-actions">
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :on-change="onAttachFileSelect"
                accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                style="display: inline-block"
              >
                <el-button size="small" round>
                  <el-icon style="margin-right: 4px"><Paperclip /></el-icon>ϴ
                </el-button>
              </el-upload>
              <el-button size="small" @click="onManageAttachments" round>ȫ</el-button>
            </div>
          </div>

          <!-- ť -->
          <div class="gt-wpb-actions">
            <el-button type="primary" @click="onOpenWorkpaper" round>
              <el-icon style="margin-right: 4px"><EditPen /></el-icon>༭׸
            </el-button>
            <el-button @click="showAssignDialog = true" round>
              ?? 
            </el-button>
            <el-button @click="onGoTrialBalance" round>͸</el-button>
            <el-button v-if="selectedMapping.note_section" @click="onGoNote" round>鿴ע</el-button>
            <el-button @click="onGoLedger" round>鿴ʱ</el-button>
          </div>

          <!-- ׸嵯 -->
          <el-dialog v-model="showAssignDialog" title="׸" width="420" append-to-body>
            <el-form label-width="70px">
              <el-form-item label="">
                <el-select v-model="assignForm.assigned_to" filterable clearable placeholder="ѡ" style="width: 100%">
                  <el-option v-for="s in staffList" :key="s.id" :label="s.name" :value="s.user_id || s.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="">
                <el-select v-model="assignForm.reviewer" filterable clearable placeholder="ѡ񸴺" style="width: 100%">
                  <el-option v-for="s in staffList" :key="s.id" :label="s.name" :value="s.user_id || s.id" />
                </el-select>
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="showAssignDialog = false">ȡ</el-button>
              <el-button type="primary" @click="onConfirmAssign" :loading="assignLoading">ȷϷ</el-button>
            </template>
          </el-dialog>

          <!-- ݲ -->
          <div class="gt-wpb-data-section" v-if="priorYearData">
            <h4 class="gt-wpb-section-title">ݲ</h4>
            <div class="gt-wpb-prior-cards">
              <div class="gt-wpb-prior-card">
                <span class="gt-wpb-prior-label">{{ year - 1 }}</span>
                <span class="gt-wpb-prior-value">{{ fmtAmt(priorYearData.total_audited) }}</span>
              </div>
              <div class="gt-wpb-prior-card">
                <span class="gt-wpb-prior-label">ͬȱ䶯</span>
                <span class="gt-wpb-prior-value" :class="{ 'gt-wpb-prior-diff': yoyChange !== 0 }">
                  {{ yoyChange > 0 ? '+' : '' }}{{ fmtAmt(yoyChange) }}
                </span>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="gt-wpb-empty-state">
          <div class="gt-wpb-empty-icon">??</div>
          <h4>ѡ׸忪ʼ</h4>
          <p>ఴѭѡ׸壬鿴ݲʼ</p>
        </div>
      </div>

      <!-- AI  -->
      <div class="gt-wpb-ai">
        <h4 class="gt-wpb-section-title">AI </h4>
        <div v-if="selectedMapping" class="gt-wpb-ai-content">
          <div class="gt-wpb-ai-hint">
            <el-icon style="color: var(--gt-color-primary); margin-right: 6px"><MagicStick /></el-icon>
             {{ selectedMapping.account_name }} Ҫ
          </div>

          <!-- AI 䶯 -->
          <div v-if="aiAnalysis" class="gt-wpb-ai-analysis gt-fade-in">
            <div class="gt-wpb-ai-analysis-header">
              <span class="gt-wpb-ai-analysis-badge">AI 䶯</span>
              <span v-if="aiAnalysis.change_rate !== null" :class="Math.abs(aiAnalysis.change_rate) > 20 ? 'gt-wpb-ai-sig' : 'gt-wpb-ai-normal'">
                {{ aiAnalysis.change_rate > 0 ? '+' : '' }}{{ aiAnalysis.change_rate }}%
              </span>
            </div>
            <p class="gt-wpb-ai-analysis-text">{{ aiAnalysis.ai_analysis }}</p>
          </div>
          <el-skeleton v-else-if="aiLoading" :rows="2" animated style="margin-bottom: 12px" />

          <div class="gt-wpb-ai-tips">
            <div class="gt-wpb-ai-tip" v-for="(tip, i) in auditTips" :key="i">
              <span class="gt-wpb-ai-tip-num">{{ i + 1 }}</span>
              <span>{{ tip }}</span>
            </div>
          </div>
          <el-input v-model="aiQuestion" type="textarea" :rows="2" placeholder="⣬"ĿƷյʲ"" style="margin-top: 12px" />
          <el-button type="primary" size="small" style="margin-top: 8px" :disabled="!aiQuestion.trim()" @click="onAskAI" :loading="aiAsking" round>
            <el-icon style="margin-right: 4px"><MagicStick /></el-icon>
          </el-button>
          <div v-if="aiAnswer" class="gt-wpb-ai-answer gt-fade-in">
            <p>{{ aiAnswer }}</p>
          </div>

          <!-- Ƴ嵥 -->
          <div class="gt-wpb-checklist" v-if="auditChecklist.length">
            <h4 class="gt-wpb-section-title" style="margin-top: 20px">Ƴ嵥</h4>
            <div v-for="(item, i) in auditChecklist" :key="i" class="gt-wpb-check-item" @click="item.done = !item.done">
              <el-checkbox v-model="item.done" size="small" />
              <span :class="{ 'gt-wpb-check-done': item.done }">{{ item.label }}</span>
            </div>
            <div class="gt-wpb-check-progress">
              {{ auditChecklist.filter(c => c.done).length }} / {{ auditChecklist.length }} 
            </div>
          </div>
        </div>
        <el-empty v-else description="ѡ׸ʾҪ" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, EditPen, Paperclip } from '@element-plus/icons-vue'
import { getAllWpMappings, getWpPrefillData, getWpRecommendations, type WpAccountMapping, type WpPrefillData, type WpRecommendation } from '@/services/workpaperApi'
import { getProjectAuditYear } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = ref(new Date().getFullYear())

const loading = ref(false)
const prefillLoading = ref(false)
const mappings = ref<WpAccountMapping[]>([])
const selectedMapping = ref<WpAccountMapping | null>(null)
const prefillData = ref<WpPrefillData | null>(null)
const searchText = ref('')
const treeRef = ref<any>(null)
const aiQuestion = ref('')
const onlyMine = ref(false)
const filterStatus = ref('')
const attachments = ref<any[]>([])
const aiLoading = ref(false)
const aiAnalysis = ref<any>(null)
const aiAsking = ref(false)
const aiAnswer = ref('')
const priorYearData = ref<WpPrefillData | null>(null)
const recommendations = ref<WpRecommendation[]>([])
const recommendLoading = ref(false)
const generatingWps = ref(false)

// ׸
const showAssignDialog = ref(false)
const assignLoading = ref(false)
const staffList = ref<Array<{ id: string; name: string; user_id?: string }>>([])
const assignForm = reactive({ assigned_to: '', reviewer: '' })

const yoyChange = computed(() => {
  if (!prefillData.value || !priorYearData.value) return 0
  return (parseFloat(prefillData.value.total_audited) || 0) - (parseFloat(priorYearData.value.total_audited) || 0)
})
// ͳƣӵ׸бȡʵ״̬
const wpStatusMap = ref<Record<string, { status: string; review_status: string; assigned_to?: string }>>({})
const totalCount = computed(() => mappings.value.length)
const doneCount = computed(() => {
  return Object.values(wpStatusMap.value).filter(
    w => w.status === 'review_passed' || w.status === 'archived' ||
         w.review_status === 'level1_passed' || w.review_status === 'level2_passed'
  ).length
})
const progressPct = computed(() => totalCount.value > 0 ? Math.round(doneCount.value / totalCount.value * 100) : 0)

// 
const totalOpening = computed(() => {
  if (!prefillData.value?.accounts) return '0'
  return String(prefillData.value.accounts.reduce((s, a) => s + (parseFloat(a.opening) || 0), 0))
})
const totalAdj = computed(() => {
  if (!prefillData.value?.accounts) return '0'
  const total = prefillData.value.accounts.reduce((s, a) => s + (parseFloat(a.rje) || 0) + (parseFloat(a.aje) || 0), 0)
  return String(total)
})
function adjVal(row: any): number {
  return (parseFloat(row.rje) || 0) + (parseFloat(row.aje) || 0)
}

// ѭҪ㣨 TSJ ʾʿ⶯̬أ
const AUDIT_TIPS_FALLBACK: Record<string, string[]> = {
  'ʽ': ['ʵдڱ', '޻ʽ', '֤д', '쳣֧'],
  'Ӧ˿': ['ṹ仯', '׼', '֤Ӧ', 'ںؿ'],
  '': ['', '׼', 'ת', 'עʹ'],
  '̶ʲ': ['ʲ', '۾ɼ', 'עֵ', '鴦'],
  'Ӫҵ': ['ִֹ', '벨ԭ', '', 'עȷʱ'],
}

const tsjData = ref<{ tips: string[]; checklist: string[]; risk_areas: any[] } | null>(null)

const auditTips = computed(() => {
  if (tsjData.value?.tips?.length) return tsjData.value.tips
  if (!selectedMapping.value) return []
  const name = selectedMapping.value.account_name
  return AUDIT_TIPS_FALLBACK[name] || ['ĩĺ', 'ڱ䶯ԭ', 'ʵƾ֤͸', 'ƹƵǡ']
})

// Ƴ嵥
const AUDIT_CHECKLISTS_FALLBACK: Record<string, string[]> = {
  'ʽ': ['ȡдڱ', '֤д', '̵ֽ', '޻ʽ', '쳣֧', '󶨱'],
  'Ӧ˿': ['ȡ', '֤Ӧ', 'ںؿ', '׼', '', '󶨱'],
  '': ['', 'Ƽ', '׼', 'ֹ', 'ת', '󶨱'],
  '̶ʲ': ['ʲ', '۾ɼ', '鴦', 'ֵ', 'ʵȨ֤', '󶨱'],
  'Ӫҵ': ['ִнֹ', '벨', '˻', 'ʵ', 'ȷ', '󶨱'],
}

const auditChecklist = ref<Array<{ label: string; done: boolean }>>([])

watch(selectedMapping, async (m) => {
  if (!m) { auditChecklist.value = []; tsjData.value = null; return }

  //  TSJ 
  tsjData.value = null
  try {
    const data = await api.get(
      `/api/projects/${projectId.value}/wp-mapping/tsj/${encodeURIComponent(m.account_name)}`,
      { validateStatus: () => true }
    )
    const result = data?.data ?? data
    if (result?.tips?.length || result?.checklist?.length) {
      tsjData.value = result
    }
  } catch { /* TSJ ʱ fallback */ }

  // 嵥
  const tsjChecklist = tsjData.value?.checklist
  const items = tsjChecklist?.length
    ? tsjChecklist
    : (AUDIT_CHECKLISTS_FALLBACK[m.account_name] || ['ȡϸ', 'ʵ', '䶯', '', '󶨱'])
  auditChecklist.value = items.map(label => ({ label, done: false }))
})

interface TreeNode {
  id: string; label: string; children?: TreeNode[]
  wpCode?: string; stale?: boolean; consistent?: boolean | null
  statusIcon?: string; assignee?: string
}

function _wpStatusIcon(wp?: { status: string; review_status: string }): string {
  if (!wp) return '?'
  if (wp.status === 'review_passed' || wp.status === 'archived') return '?'
  if (wp.review_status?.startsWith('pending_')) return '??'
  if (wp.review_status?.includes('rejected')) return '??'
  if (wp.status === 'draft' || wp.status === 'edit_complete') return '??'
  if (wp.status === 'under_review') return '??'
  return '?'
}

const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TreeNode> = {}
  const CYCLE_NAMES: Record<string, string> = {
    D: 'D ѭ', E: 'E ʽ', F: 'F ', G: 'G Ͷ',
    H: 'H ̶ʲ', I: 'I ʲ', J: 'J н', K: 'K ',
    L: 'L ծ', M: 'M Ȩ', N: 'N ˰',
  }
  for (const m of mappings.value) {
    const key = m.cycle
    if (!groups[key]) {
      groups[key] = { id: `g-${key}`, label: CYCLE_NAMES[key] || `${key}ѭ`, children: [] }
    }
    groups[key].children!.push({
      id: m.wp_code, label: `${m.wp_code} ${m.wp_name}`, wpCode: m.wp_code,
      statusIcon: _wpStatusIcon(wpStatusMap.value[m.wp_code]),
      assignee: wpStatusMap.value[m.wp_code]?.assigned_to || undefined,
    })
  }
  // ڵͳ
  for (const g of Object.values(groups)) {
    const total = g.children?.length || 0
    g.label = `${g.label}${total}`
  }
  return Object.values(groups).sort((a, b) => a.label.localeCompare(b.label))
})

function filterNode(value: string, data: TreeNode) {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

watch(searchText, (val) => { treeRef.value?.filter(val) })

function fmtAmt(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onNodeClick(data: TreeNode) {
  if (!data.wpCode) return
  const m = mappings.value.find(x => x.wp_code === data.wpCode)
  if (!m) return
  selectedMapping.value = m
  prefillData.value = null
  priorYearData.value = null
  prefillLoading.value = true
  try {
    const [current, prior] = await Promise.all([
      getWpPrefillData(projectId.value, m.wp_code, year.value),
      getWpPrefillData(projectId.value, m.wp_code, year.value - 1).catch(() => null),
    ])
    prefillData.value = current
    priorYearData.value = prior
  } catch { /* ignore */ }
  finally { prefillLoading.value = false }
  await loadAttachments()
  await loadAiAnalysis()
}

async function loadAiAnalysis() {
  if (!selectedMapping.value) { aiAnalysis.value = null; return }
  const codes = selectedMapping.value.account_codes
  if (!codes.length) { aiAnalysis.value = null; return }
  aiLoading.value = true
  aiAnalysis.value = null
  try {
    // һĿԸ
    const data = await api.post(
      `/api/projects/${projectId.value}/working-papers/00000000-0000-0000-0000-000000000000/ai/analytical-review`,
      null,
      { params: { account_code: codes[0], year: year.value }, timeout: 30000, validateStatus: () => true }
    )
    const result = data?.data ?? data
    if (result && !result.error) {
      aiAnalysis.value = result
    }
  } catch { /* LLMʱĬ */ }
  finally { aiLoading.value = false }
}

async function onAskAI() {
  if (!aiQuestion.value.trim() || !selectedMapping.value) return
  aiAsking.value = true
  aiAnswer.value = ''
  try {
    const data = await api.post('/api/chat/stream', {
      message: aiQuestion.value,
      context: `ǰڱ ${selectedMapping.value.account_name} ׸壨${selectedMapping.value.wp_code}Ŀ ${selectedMapping.value.account_codes.join(',')}`,
    }, { timeout: 30000, validateStatus: () => true })
    const result = data?.data ?? data
    aiAnswer.value = typeof result === 'string' ? result : (result?.reply || result?.content || 'ʱ޷شԺ')
  } catch {
    aiAnswer.value = 'AI ݲȷ vLLM '
  } finally {
    aiAsking.value = false
  }
}

function onOpenWorkpaper() {
  if (!selectedMapping.value) return
  router.push({
    path: `/projects/${projectId.value}/workpapers`,
    query: { highlight: selectedMapping.value.wp_code },
  })
}

function onGoTrialBalance() {
  router.push({ path: `/projects/${projectId.value}/trial-balance`, query: { year: String(year.value) } })
}

function onGoNote() {
  if (!selectedMapping.value?.note_section) return
  router.push({ path: `/projects/${projectId.value}/disclosure-notes`, query: { year: String(year.value) } })
}

function onGoLedger() {
  if (!selectedMapping.value) return
  const firstCode = selectedMapping.value.account_codes[0]
  router.push({ path: `/projects/${projectId.value}/ledger`, query: { year: String(year.value), account: firstCode } })
}

function onDrillToAdjustment(row: any) {
  // ˫  תҳĿɸѡ
  router.push({
    path: `/projects/${projectId.value}/adjustments`,
    query: { year: String(year.value), account_code: row.code },
  })
}

function onManageAttachments() {
  if (!selectedMapping.value) return
  router.push({ path: `/projects/${projectId.value}/attachments`, query: { wp_code: selectedMapping.value.wp_code } })
}

function getFileIcon(fileType: string): string {
  if (!fileType) return '??'
  const t = fileType.toLowerCase()
  if (t.includes('pdf')) return '??'
  if (t.includes('xls') || t.includes('xlsx')) return '??'
  if (t.includes('doc') || t.includes('docx')) return '??'
  if (t.includes('jpg') || t.includes('png') || t.includes('jpeg')) return '???'
  return '??'
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

function onPreviewAttachment(attId: string) {
  // Ԥǩ򿪣ԤӿڷصǿֱȾݣҪ Authorization
  // Ҫ֤Ϊ downloadFileAsBlob
  window.open(`/api/attachments/${attId}/preview`, '_blank')
}

async function onAttachFileSelect(_file: any) {
  if (!selectedMapping.value) return
  const rawFile = _file.raw || _file
  if (!rawFile) return
  try {
    const formData = new FormData()
    formData.append('file', rawFile)
    formData.append('attachment_type', 'workpaper')
    // 1. ϴ
    const uploadResult = await api.post(
      `/api/projects/${projectId.value}/attachments/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const attId = uploadResult?.data?.id ?? uploadResult?.id
    if (!attId) {
      ElMessage.warning('ϴɹδȡID')
      await loadAttachments()
      return
    }
    // 2. ׸
    try {
      await api.post(`/api/attachments/${attId}/associate`, {
        working_paper_code: selectedMapping.value.wp_code,
        relation_type: 'evidence',
      })
    } catch { /* APIܲڣĬ */ }
    ElMessage.success('ϴ')
    await loadAttachments()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || 'ϴʧ')
  }
}

async function loadAttachments() {
  if (!selectedMapping.value) { attachments.value = []; return }
  try {
    const data = await api.get(
      `/api/projects/${projectId.value}/attachments`,
      { params: { wp_code: selectedMapping.value.wp_code, page_size: 10 } }
    )
    attachments.value = Array.isArray(data) ? data : data?.items ?? []
  } catch { attachments.value = [] }
}

async function onBatchPrefill() {
  prefillLoading.value = true
  try {
    ElMessage.info('Ԥ书ܿУǰ鿴Ԥ')
  } finally { prefillLoading.value = false }
}

async function onSmartRecommend() {
  recommendLoading.value = true
  try {
    recommendations.value = await getWpRecommendations(projectId.value, year.value)
    if (recommendations.value.length === 0) {
      ElMessage.info('ݣȵı')
    } else {
      ElMessage.success(`Ƽ ${recommendations.value.length} ׸`)
    }
  } catch {
    ElMessage.error('Ƽʧܣȷ')
  } finally { recommendLoading.value = false }
}

async function onGenerateRecommended() {
  if (!recommendations.value.length) return
  generatingWps.value = true
  try {
    const codes = recommendations.value.map(r => r.wp_code)
    await api.post(`/api/projects/${projectId.value}/working-papers/generate-from-codes`, {
      wp_codes: codes,
      year: year.value,
    })
    ElMessage.success(` ${codes.length} ׸ļ`)
    recommendations.value = []
    await refreshAll()
  } catch (e: any) {
    ElMessage.error('ʧ: ' + (e?.response?.data?.detail || e?.message || ''))
  } finally {
    generatingWps.value = false
  }
}

async function refreshAll() {
  loading.value = true
  try {
    const [mappingList, wpList] = await Promise.all([
      getAllWpMappings(projectId.value),
      (async () => {
        try {
          const { listWorkpapers } = await import('@/services/workpaperApi')
          return await listWorkpapers(projectId.value)
        } catch { return [] }
      })(),
    ])
    mappings.value = mappingList
    // ׸״̬ӳ䣨wp_code  ״̬
    const statusMap: Record<string, { status: string; review_status: string; assigned_to?: string }> = {}
    for (const wp of wpList) {
      if (wp.wp_code) {
        statusMap[wp.wp_code] = {
          status: wp.status || 'draft',
          review_status: wp.review_status || 'not_submitted',
          assigned_to: wp.assigned_to || undefined,
        }
      }
    }
    wpStatusMap.value = statusMap
  } catch { mappings.value = [] }
  finally { loading.value = false }
}

async function loadStaffList() {
  try {
    const data = await api.get('/api/staff', { params: { page_size: 200 }, validateStatus: () => true })
    const raw = data?.data ?? data
    staffList.value = Array.isArray(raw) ? raw : raw?.items ?? []
  } catch { staffList.value = [] }
}

async function onConfirmAssign() {
  if (!selectedMapping.value) return
  // ҵӦ working_paper id
  const wpCode = selectedMapping.value.wp_code
  assignLoading.value = true
  try {
    const { assignWorkpaper, listWorkpapers } = await import('@/services/workpaperApi')
    // ҵ wp id
    const wpList = await listWorkpapers(projectId.value)
    const wp = wpList.find((w: any) => w.wp_code === wpCode)
    if (!wp) {
      ElMessage.warning('δҵӦ׸壬ڵ׸бд')
      return
    }
    await assignWorkpaper(projectId.value, wp.id, {
      assigned_to: assignForm.assigned_to || undefined,
      reviewer: assignForm.reviewer || undefined,
    })
    ElMessage.success('ɹ')
    showAssignDialog.value = false
    await refreshAll()
  } catch (e: any) {
    ElMessage.error('ʧ: ' + (e?.message || ''))
  } finally {
    assignLoading.value = false
  }
}

onMounted(async () => {
  try { year.value = await getProjectAuditYear(projectId.value) ?? year.value } catch {}
  await Promise.all([refreshAll(), loadStaffList()])
})
</script>

<style scoped>
.gt-wp-bench { padding: var(--gt-space-5); height: 100%; display: flex; flex-direction: column; }

/*  */
.gt-wpb-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 18px 28px; margin-bottom: var(--gt-space-4);
  color: #fff; position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
  flex-shrink: 0;
}
.gt-wpb-banner::before {
  content: ''; position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-wpb-banner-text h2 { margin: 0 0 2px; font-size: 18px; font-weight: 700; }
.gt-wpb-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-wpb-banner-actions { display: flex; gap: 8px; position: relative; z-index: 1; }
.gt-wpb-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-wpb-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }

/*  */
.gt-wpb-body { display: flex; gap: var(--gt-space-4); flex: 1; min-height: 0; }

/* Ƽ */
.gt-wpb-recommend-panel {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4);
  margin-bottom: var(--gt-space-4);
  box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.06);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-wpb-recommend-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-wpb-recommend-list {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 8px;
}
.gt-wpb-recommend-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg); transition: all var(--gt-transition-fast);
  border: 1px solid transparent;
}
.gt-wpb-recommend-item:hover { background: var(--gt-color-primary-bg); border-color: rgba(75, 45, 119, 0.08); }
.gt-wpb-rec-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.gt-wpb-rec-code { font-size: 12px; font-weight: 700; color: var(--gt-color-primary); white-space: nowrap; }
.gt-wpb-rec-name { font-size: 13px; color: var(--gt-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-wpb-rec-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.gt-wpb-rec-reason { font-size: 11px; color: var(--gt-color-text-tertiary); }

/*  */
.gt-wpb-tree {
  width: 280px; min-width: 280px; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
  display: flex; flex-direction: column; overflow: hidden;
}
.gt-wpb-tree-header { padding: var(--gt-space-3); border-bottom: 1px solid rgba(75, 45, 119, 0.06); display: flex; flex-direction: column; gap: 8px; }
.gt-wpb-tree-filters { display: flex; gap: 8px; align-items: center; }
.gt-wpb-tree-progress {
  display: flex; align-items: center; font-size: 12px; font-weight: 600;
  color: var(--gt-color-text-secondary);
}
.gt-wpb-prog-item { font-variant-numeric: tabular-nums; }
.gt-wpb-prog--done { color: var(--gt-color-success); }
.gt-wpb-prog-sep { margin: 0 2px; color: var(--gt-color-border); }
.gt-wpb-tree :deep(.el-tree) { flex: 1; overflow-y: auto; padding: var(--gt-space-2); }
.gt-wpb-node { display: flex; align-items: center; gap: 4px; width: 100%; }
.gt-wpb-node-icon { font-size: 12px; flex-shrink: 0; }
.gt-wpb-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.gt-wpb-node-assignee {
  font-size: 10px; color: var(--gt-color-text-tertiary);
  background: var(--gt-color-bg); padding: 1px 5px; border-radius: var(--gt-radius-full);
  flex-shrink: 0;
}
.gt-wpb-node-stale { color: var(--gt-color-wheat); font-size: 12px; }
.gt-wpb-node-ok { color: var(--gt-color-success); font-size: 12px; font-weight: 700; }
.gt-wpb-node-diff { color: var(--gt-color-coral); font-size: 12px; font-weight: 700; }

/*  */
.gt-wpb-detail {
  flex: 1; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
  padding: var(--gt-space-5); overflow-y: auto;
}
.gt-wpb-detail-header { margin-bottom: var(--gt-space-3); padding-bottom: var(--gt-space-3); border-bottom: 1px solid rgba(75, 45, 119, 0.06); }
.gt-wpb-detail-title-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.gt-wpb-detail-header h3 { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 700; color: var(--gt-color-primary-dark); }
.gt-wpb-detail-tags { display: flex; gap: 6px; }

/* ̲ */
.gt-wpb-workflow {
  display: flex; align-items: center; gap: 0;
  padding: 14px 20px; margin-bottom: var(--gt-space-4);
  background: linear-gradient(135deg, #faf9fd, #f4f0fa);
  border-radius: var(--gt-radius-md); border: 1px solid rgba(75, 45, 119, 0.06);
}
.gt-wpb-step {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--gt-color-text-tertiary); font-weight: 500;
  white-space: nowrap;
}
.gt-wpb-step-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--gt-color-border); transition: all var(--gt-transition-base);
}
.gt-wpb-step--done .gt-wpb-step-dot { background: var(--gt-color-success); box-shadow: 0 0 0 3px rgba(40, 167, 69, 0.15); }
.gt-wpb-step--done { color: var(--gt-color-success); }
.gt-wpb-step--active .gt-wpb-step-dot { background: var(--gt-color-primary); box-shadow: 0 0 0 3px rgba(75, 45, 119, 0.15); animation: gtPulse 2s ease-in-out infinite; }
.gt-wpb-step--active { color: var(--gt-color-primary); font-weight: 600; }
.gt-wpb-step-line { flex: 1; height: 2px; background: var(--gt-color-border-light); margin: 0 6px; min-width: 16px; }

/*  */
.gt-wpb-attach-hint {
  display: flex; align-items: center; font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary); margin-bottom: var(--gt-space-2);
}

/* ״̬ */
.gt-wpb-empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; text-align: center; color: var(--gt-color-text-tertiary);
}
.gt-wpb-empty-icon { font-size: 48px; margin-bottom: var(--gt-space-3); opacity: 0.5; }
.gt-wpb-empty-state h4 { margin: 0 0 6px; font-size: var(--gt-font-size-lg); color: var(--gt-color-text-secondary); }
.gt-wpb-empty-state p { margin: 0; font-size: var(--gt-font-size-sm); }
.gt-wpb-section-title {
  font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text);
  margin: 0 0 var(--gt-space-3); display: flex; align-items: center; gap: 8px;
}
.gt-wpb-section-title::before {
  content: ''; width: 3px; height: 14px;
  background: var(--gt-gradient-primary); border-radius: 2px;
}
.gt-wpb-data-section { margin-bottom: var(--gt-space-5); }

/* Ԥ俨Ƭ */
.gt-wpb-prefill-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--gt-space-3); }
.gt-wpb-prefill-card {
  padding: var(--gt-space-3) var(--gt-space-4); border-radius: var(--gt-radius-md);
  text-align: center; border: 1px solid rgba(75, 45, 119, 0.04);
  transition: all var(--gt-transition-base); position: relative; overflow: hidden;
}
.gt-wpb-prefill-card:hover { transform: translateY(-2px); box-shadow: var(--gt-shadow-md); }
.gt-wpb-prefill-card--muted { background: linear-gradient(135deg, #f7f7fa, #f0f0f5); }
.gt-wpb-prefill-card--primary { background: linear-gradient(135deg, #f8f6fb, #f4f0fa); }
.gt-wpb-prefill-card--teal { background: linear-gradient(135deg, #f0fbfd, #e6f7fa); }
.gt-wpb-prefill-card--success { background: linear-gradient(135deg, #f5fbf6, #edf7ef); }
.gt-wpb-pf-label { display: block; font-size: 11px; color: var(--gt-color-text-secondary); font-weight: 500; letter-spacing: 0.3px; }
.gt-wpb-pf-value { display: block; font-size: 20px; font-weight: 800; margin-top: 4px; letter-spacing: -0.5px; font-variant-numeric: tabular-nums; }
.gt-wpb-prefill-card--muted .gt-wpb-pf-value { color: var(--gt-color-text-secondary); }
.gt-wpb-prefill-card--primary .gt-wpb-pf-value { color: var(--gt-color-primary); }
.gt-wpb-prefill-card--teal .gt-wpb-pf-value { color: var(--gt-color-teal); }
.gt-wpb-prefill-card--success .gt-wpb-pf-value { color: var(--gt-color-success); }
.gt-wpb-pf-value--diff { color: var(--gt-color-coral) !important; }

/* Ŀϸ */
.gt-wpb-acct-table :deep(.el-table__header th) { font-size: 12px; }

.gt-wpb-actions { display: flex; gap: var(--gt-space-2); margin-top: var(--gt-space-4); padding-top: var(--gt-space-3); border-top: 1px solid rgba(75, 45, 119, 0.06); }

/* б */
.gt-wpb-attach-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--gt-space-3); }
.gt-wpb-attach-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg); transition: all var(--gt-transition-fast);
  border: 1px solid transparent;
}
.gt-wpb-attach-item:hover { background: var(--gt-color-primary-bg); border-color: rgba(75, 45, 119, 0.08); }
.gt-wpb-attach-icon { font-size: 20px; flex-shrink: 0; }
.gt-wpb-attach-info { flex: 1; min-width: 0; }
.gt-wpb-attach-name { display: block; font-size: 13px; font-weight: 500; color: var(--gt-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-wpb-attach-meta { display: block; font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 1px; }
.gt-wpb-attach-empty { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); padding: 12px 0; text-align: center; }
.gt-wpb-attach-actions { display: flex; gap: 8px; }

/* OCR ״̬ǩ */
.gt-wpb-ocr-badge { font-size: 10px; padding: 1px 4px; border-radius: 3px; margin-left: 4px; font-weight: 600; }
.gt-wpb-ocr--ok { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.gt-wpb-ocr--ing { background: var(--gt-color-wheat-light); color: #e6a817; }
.gt-wpb-ocr--fail { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }

/* ݲ */
.gt-wpb-prior-cards { display: flex; gap: var(--gt-space-3); }
.gt-wpb-prior-card {
  flex: 1; padding: 10px 14px; border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg); text-align: center;
  border: 1px dashed var(--gt-color-border);
}
.gt-wpb-prior-label { display: block; font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wpb-prior-value { display: block; font-size: 16px; font-weight: 700; color: var(--gt-color-text-secondary); margin-top: 2px; font-variant-numeric: tabular-nums; }
.gt-wpb-prior-diff { color: var(--gt-color-coral); }

/* AI 䶯 */
.gt-wpb-ai-analysis {
  padding: 10px 12px; border-radius: var(--gt-radius-md);
  background: linear-gradient(135deg, #f8f6fb, #f0ebf8);
  border: 1px solid rgba(75, 45, 119, 0.08);
  margin-bottom: 12px;
}
.gt-wpb-ai-analysis-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.gt-wpb-ai-analysis-badge {
  font-size: 10px; font-weight: 600; padding: 2px 6px;
  border-radius: var(--gt-radius-full);
  background: var(--gt-gradient-primary); color: #fff;
}
.gt-wpb-ai-sig { font-size: 13px; font-weight: 700; color: var(--gt-color-coral); }
.gt-wpb-ai-normal { font-size: 13px; font-weight: 600; color: var(--gt-color-success); }
.gt-wpb-ai-analysis-text { font-size: 13px; color: var(--gt-color-text); line-height: 1.6; margin: 0; }

/* AI ش */
.gt-wpb-ai-answer {
  margin-top: 10px; padding: 10px 12px;
  background: linear-gradient(135deg, #f0fbfd, #e6f7fa);
  border-radius: var(--gt-radius-md);
  border-left: 3px solid var(--gt-color-teal);
  font-size: 13px; line-height: 1.6; color: var(--gt-color-text);
}
.gt-wpb-ai-answer p { margin: 0; }

/*  AI */
.gt-wpb-ai {
  width: 300px; min-width: 300px; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
  padding: var(--gt-space-4); overflow-y: auto;
}
.gt-wpb-ai-content { }
.gt-wpb-ai-hint {
  display: flex; align-items: center; font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary); font-weight: 500; margin-bottom: var(--gt-space-3);
}
.gt-wpb-ai-tips { display: flex; flex-direction: column; gap: 8px; }
.gt-wpb-ai-tip {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: var(--gt-font-size-sm); color: var(--gt-color-text);
  padding: 8px 10px; border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg); transition: background var(--gt-transition-fast);
}
.gt-wpb-ai-tip:hover { background: var(--gt-color-primary-bg); }
.gt-wpb-ai-tip-num {
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--gt-gradient-primary); color: #fff;
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}

/* Ƴ嵥 */
.gt-wpb-checklist { }
.gt-wpb-check-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: var(--gt-radius-sm);
  cursor: pointer; transition: background var(--gt-transition-fast);
  font-size: 13px; color: var(--gt-color-text);
}
.gt-wpb-check-item:hover { background: var(--gt-color-primary-bg); }
.gt-wpb-check-done { text-decoration: line-through; color: var(--gt-color-text-tertiary); }
.gt-wpb-check-progress {
  font-size: 11px; color: var(--gt-color-text-secondary); margin-top: 8px;
  padding: 4px 8px; background: var(--gt-color-bg); border-radius: var(--gt-radius-sm);
  text-align: center; font-weight: 500;
}
</style>