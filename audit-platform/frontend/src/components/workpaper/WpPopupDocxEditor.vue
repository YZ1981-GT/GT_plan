<script setup lang="ts">
/**
 * WpPopupDocxEditor — 通用 Word 底稿弹窗编辑器
 *
 * 适用于程序表关联的 docx 子底稿（A8-1 声明/A8-2 比对记录等），提供：
 * - 使用说明提示区（引导用户何时使用、注意事项）
 * - OnlyOffice 在线编辑（可用时）
 * - 降级预览（vue-office-docx）
 * - 下载模板到本地编辑
 * - 关联模块跳转链接
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const route = useRoute()
const loading = ref(false)
const editorVisible = ref(false)
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')

// ─── A8-1/A8-2 配置 ───
interface DocxConfig {
  title: string
  guidance: string[]
  applicableNote: string
  templatePath: string
  relatedLinks: Array<{ label: string; routeName?: string; wpCode?: string }>
}

const DOCX_CONFIGS: Record<string, DocxConfig> = {
  'A8-1': {
    title: '管理层关于审计报告日后公布其他信息的书面声明',
    guidance: [
      '本声明书系根据《中国注册会计师审计准则第1521号》的相关规定编制，针对只能在审计报告日后获取的其他信息时，注册会计师应从管理层获取的书面声明。',
      '红色字体显示的内容，由项目组根据企业或约定项目的具体情况填入适当的内容或删除不适用之处。蓝色字体显示的内容，是对相关内容的提示，使用时删除。',
      '注册会计师应在审计计划阶段通过与管理层讨论，确定哪些文件组成年度报告，以及被审计单位计划公布这些文件的方式和时间安排。',
      '对于注册会计师在审计报告日前未获取的其他信息，应要求管理层提供本书面声明，包括拟编制并发布这些其他信息，以及预计发布的时间。',
      '本书面声明的签署日期通常应与审计报告日一致，不得晚于审计报告日。',
      '本书面声明可单独要求管理层出具，也可以整合在《A16 管理层声明书》中。',
    ],
    applicableNote: '当被审计单位的年度报告（含其他信息）在审计报告日后才能获取时适用',
    templatePath: 'wp_templates/A/A8-1 管理层对审计报告日后公布其他信息的书面声明201707.docx',
    relatedLinks: [
      { label: 'A16 管理层声明书', wpCode: 'A16' },
      { label: 'A8 其他信息程序表', wpCode: 'A8' },
    ],
  },
  'A8-2': {
    title: '其他信息比对记录',
    guidance: [
      '本底稿用于记录注册会计师将其他信息中的金额或其他项目与财务报表进行比对的过程和结论。',
      '比对内容包括：关键财务业绩摘要、经营数据、特殊项目、流动性信息、资本支出、表外安排、担保及或有事项、财务比率等金额类信息。',
      '以及：会计估计解释、关联方识别、风险管理政策、法律监管变化、新准则影响、业务环境描述、战略概述等其他项目类信息。',
      '对于识别出的不一致或可能的重大错报，应记录与管理层讨论的结果及后续处理。',
    ],
    applicableNote: '所有审计项目均适用，在获取年度报告其他信息后编制',
    templatePath: 'wp_templates/A/A8-2 其他信息比对记录20170725.docx',
    relatedLinks: [
      { label: 'A8 其他信息程序表', wpCode: 'A8' },
      { label: '财务报表（试算表）', routeName: 'trial-balance' },
    ],
  },
}

const config = computed(() => DOCX_CONFIGS[props.wpCode] || null)

async function checkOnlyoffice() {
  try {
    const pid = props.projectId || (route.params.projectId as string)
    const res = await api.get(`/api/projects/${pid}/deliverables/onlyoffice/health`)
    onlyofficeAvailable.value = res?.available === true
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function openEditor() {
  if (!config.value) return
  loading.value = true
  try {
    const pid = props.projectId || (route.params.projectId as string)
    // 查找该 wpCode 对应的独立底稿实例（非父底稿）
    // A8-1/A8-2 当前无独立实例，走模板下载
    // 未来若有独立实例，可通过 wp-index-resolve 接口查找
    if (props.wpId && config.value.templatePath.endsWith('.docx')) {
      try {
        const res = await api.get(`/api/projects/${pid}/working-papers/${props.wpId}/onlyoffice-config`)
        if (res?.document_url) {
          documentUrl.value = res.document_url
          documentKey.value = res.document_key
          editorVisible.value = true
          return
        }
      } catch {
        // 端点失败（底稿可能是 xlsx 非 docx），降级到模板下载
      }
    }
    downloadTemplate()
  } catch {
    ElMessage.warning('打开编辑器失败，请下载到本地编辑')
    downloadTemplate()
  } finally {
    loading.value = false
  }
}

function downloadTemplate() {
  if (!config.value) return
  const path = config.value.templatePath
  const url = `/api/wp-templates/download?path=${encodeURIComponent(path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = path.split('/').pop() || 'template.docx'
  a.click()
}

function onSaved() {
  ElMessage.success('文档已保存')
  emit('save')
  emit('completed')
}

function navigateToLink(_link: { label: string; routeName?: string; wpCode?: string }) {
  emit('save')
}

onMounted(() => {
  checkOnlyoffice()
})
</script>

<template>
  <div class="wp-popup-docx-editor" v-if="config">
    <el-alert type="info" :closable="false" show-icon class="wp-popup-docx-editor__guidance">
      <template #title>
        <span class="guidance-title">📋 使用说明</span>
      </template>
      <div class="guidance-content">
        <ol>
          <li v-for="(item, idx) in config.guidance" :key="idx">{{ item }}</li>
        </ol>
        <el-tag type="warning" size="small" effect="plain" style="margin-top: 8px">
          适用条件：{{ config.applicableNote }}
        </el-tag>
      </div>
    </el-alert>
    <div class="wp-popup-docx-editor__toolbar">
      <el-button type="primary" size="small" @click="openEditor" :loading="loading">
        {{ onlyofficeAvailable ? '📝 在线编辑' : '📄 预览文档' }}
      </el-button>
      <el-button size="small" @click="downloadTemplate">⬇️ 下载模板</el-button>
      <el-divider direction="vertical" />
      <template v-for="link in config.relatedLinks" :key="link.label">
        <el-button text size="small" type="primary" @click="navigateToLink(link)">
          🔗 {{ link.label }}
        </el-button>
      </template>
    </div>
    <OnlyOfficeEditor
      v-if="editorVisible"
      v-model:visible="editorVisible"
      :document-url="documentUrl"
      :document-key="documentKey"
      :title="config.title"
      mode="edit"
      @saved="onSaved"
      @close="editorVisible = false"
    />
  </div>
  <div v-else class="popup-empty">
    <p>未配置该文档类型（{{ wpCode }}）</p>
  </div>
</template>

<style scoped>
.wp-popup-docx-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wp-popup-docx-editor__guidance {
  margin-bottom: 8px;
}
.guidance-title {
  font-weight: 600;
  font-size: 14px;
}
.guidance-content ol {
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.guidance-content ol li {
  margin-bottom: 4px;
}
.wp-popup-docx-editor__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.popup-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
