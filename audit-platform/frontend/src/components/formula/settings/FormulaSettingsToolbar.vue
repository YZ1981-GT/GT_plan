<!--
  公式管理中心顶栏的「全局设置 / 保存为模板 / 订阅模板 / 公式包」入口 + 保存后的「应用范围」对话框
  （spec formula-global-settings-sync，design §11 / §16.6，R7 / R13.10；公式包见 formula-governance-coverage-closure R4）。
  取代旧的共享配置「公式审核配置」模板（只回填报表段、引用会写全局行，已下线）：
  模板改为订阅一层（只写本项目层，绝不写全局行），模板更新经同一同步内核与待确认弹窗。
  `askApplyScope(domain, slotKeys)`：本项目保存成功后由宿主调用，弹出应用范围选择。
-->
<template>
  <el-button size="small" data-testid="fm-global-settings" @click="openGlobalSettings">⚙ 全局设置</el-button>
  <template v-if="projectId">
    <el-button size="small" data-testid="fm-template-save" @click="showSave = true">📑 保存为模板</el-button>
    <el-button v-if="canEditProject" size="small" data-testid="fm-template-subscribe" @click="showSubscribe = true">🔗 订阅模板</el-button>
    <!-- spec formula-governance-coverage-closure R4：本项目公式包（导出本项目适配 / 导入为本项目适配） -->
    <FormulaImportExportDropdown mode="package" :project-id="projectId" :can-edit-project="canEditProject"
      @package-applied="onPackageApplied" />
    <!-- spec formula-management-repair-closure R1.4：公式变更推到下游的结果（处理中 / 失败原因 / 已完成） -->
    <FormulaPropagationStatus ref="propagationRef" :project-id="projectId" />
  </template>
  <FormulaTemplateSaveDialog v-model="showSave" :project-id="projectId" :default-domain="domain"
    :default-scope="defaultScope" :can-edit-project="canEditProject" />
  <FormulaTemplateSubscribeDialog v-model="showSubscribe" :project-id="projectId" :default-domain="domain"
    :initial-template-id="initialTemplateId" :initial-template-action="initialTemplateAction"
    :initial-template-domain="initialTemplateDomain"
    @changed="(d: string) => changed(d)" />
  <FormulaApplyScopeDialog v-model="apply.visible" :project-id="projectId" :domain="apply.domain"
    :slot-keys="apply.slotKeys" :can-edit-global="canEditGlobal" @done="() => changed(apply.domain)" />
</template>

<script lang="ts">
/**
 * 支持「应用范围」的域白名单（单一来源）——域不在列表内点应用范围按钮时禁用并提示。
 * 生产调用方：公式管理中心的 report / tb_detail / cross_check / wp（底稿公式保存后按后端回执的公式位问，
 * spec formula-management-repair-closure R4）。附注 / 合并附注 / 推送规则的保存入口在各自弹窗里，暂不接。
 */
export const APPLY_SCOPE_DOMAINS: ReadonlyArray<string> = ['report', 'tb_detail', 'cross_check', 'wp'] as const
</script>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormulaTemplateSaveDialog from './FormulaTemplateSaveDialog.vue'
import FormulaTemplateSubscribeDialog from './FormulaTemplateSubscribeDialog.vue'
import FormulaApplyScopeDialog from './FormulaApplyScopeDialog.vue'
import FormulaPropagationStatus from './FormulaPropagationStatus.vue'
import FormulaImportExportDropdown from '../FormulaImportExportDropdown.vue'

defineOptions({ name: 'FormulaSettingsToolbar' })

const props = withDefaults(defineProps<{
  projectId?: string
  /** 当前节点对应的公式域（report / tb_detail / cross_check / note …） */
  domain?: string
  /** 默认适用范围（如 `soe_standalone`），用于保存模板与跳转全局设置 */
  defaultScope?: string
  /** 当前用户是否 admin（决定应用范围里显示「设为全局」还是「提交为全局候选」） */
  canEditGlobal?: boolean
  /** 当前账号能否改本项目公式（导入公式包用；宿主的只读态取反） */
  canEditProject?: boolean
  /** 模板详情深链自动打开订阅弹窗。 */
  initialTemplateId?: string
  initialTemplateAction?: 'subscribe'
  initialTemplateDomain?: string
}>(), { projectId: '', domain: 'report', defaultScope: '', canEditGlobal: false, canEditProject: false })

const emit = defineEmits<{ navigate: []; changed: [domain: string] }>()

const router = useRouter()
const showSave = ref(false)
const showSubscribe = ref(false)
const apply = reactive({ visible: false, domain: 'report', slotKeys: [] as string[] })
const propagationRef = ref<InstanceType<typeof FormulaPropagationStatus> | null>(null)

/** 宿主保存公式后调用（订阅 / 应用 / 公式包在本组件内已自动刷新） */
function refreshPropagation() {
  void propagationRef.value?.refresh?.()
}

/** 本项目有效定义变了：通知宿主重取，并刷新联动状态 */
function changed(domain: string) {
  emit('changed', domain)
  refreshPropagation()
}

watch(() => [props.initialTemplateId, props.initialTemplateAction, props.canEditProject] as const,
  ([templateId, action, canEdit]) => {
    if (templateId && action === 'subscribe' && canEdit) showSubscribe.value = true
  }, { immediate: true })

function openGlobalSettings() {
  emit('navigate')
  void router.push({
    path: '/settings/formula-global',
    query: { domain: props.domain, ...(props.defaultScope ? { scope: props.defaultScope } : {}) },
  })
}

/** 公式包写入了若干类公式：通知宿主刷新一次（当前类别有写入就报当前类别） */
function onPackageApplied(domains: string[]) {
  if (domains.length) changed(domains.includes(props.domain) ? props.domain : domains[0])
}

/** 本项目保存成功后调用：选择仅本项目 / 设为全局（或提交候选）/ 应用到指定项目。 */
function askApplyScope(domain: string, slotKeys: string[]) {
  if (!props.projectId || !slotKeys.length) return
  if (!APPLY_SCOPE_DOMAINS.includes(domain)) {
    ElMessage.warning('该域暂不支持按范围应用')
    return
  }
  apply.domain = domain
  apply.slotKeys = [...slotKeys]
  apply.visible = true
}

defineExpose({ askApplyScope, refreshPropagation })
</script>
