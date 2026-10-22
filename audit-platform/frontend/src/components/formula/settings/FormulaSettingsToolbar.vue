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
    <el-button size="small" data-testid="fm-template-subscribe" @click="showSubscribe = true">🔗 订阅模板</el-button>
    <!-- spec formula-governance-coverage-closure R4：本项目公式包（导出本项目适配 / 导入为本项目适配） -->
    <FormulaImportExportDropdown mode="package" :project-id="projectId" :can-edit-project="canEditProject"
      @package-applied="onPackageApplied" />
  </template>
  <FormulaTemplateSaveDialog v-model="showSave" :project-id="projectId" :default-domain="domain"
    :default-scope="defaultScope" />
  <FormulaTemplateSubscribeDialog v-model="showSubscribe" :project-id="projectId" :default-domain="domain"
    @changed="(d: string) => emit('changed', d)" />
  <FormulaApplyScopeDialog v-model="apply.visible" :project-id="projectId" :domain="apply.domain"
    :slot-keys="apply.slotKeys" :can-edit-global="canEditGlobal" @done="() => emit('changed', apply.domain)" />
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import FormulaTemplateSaveDialog from './FormulaTemplateSaveDialog.vue'
import FormulaTemplateSubscribeDialog from './FormulaTemplateSubscribeDialog.vue'
import FormulaApplyScopeDialog from './FormulaApplyScopeDialog.vue'
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
}>(), { projectId: '', domain: 'report', defaultScope: '', canEditGlobal: false, canEditProject: false })

const emit = defineEmits<{ navigate: []; changed: [domain: string] }>()

const router = useRouter()
const showSave = ref(false)
const showSubscribe = ref(false)
const apply = reactive({ visible: false, domain: 'report', slotKeys: [] as string[] })

function openGlobalSettings() {
  emit('navigate')
  void router.push({
    path: '/settings/formula-global',
    query: { domain: props.domain, ...(props.defaultScope ? { scope: props.defaultScope } : {}) },
  })
}

/** 公式包写入了若干类公式：通知宿主刷新一次（当前类别有写入就报当前类别） */
function onPackageApplied(domains: string[]) {
  if (domains.length) emit('changed', domains.includes(props.domain) ? props.domain : domains[0])
}

/** 本项目保存成功后调用：选择仅本项目 / 设为全局（或提交候选）/ 应用到指定项目。 */
function askApplyScope(domain: string, slotKeys: string[]) {
  if (!props.projectId || !slotKeys.length) return
  apply.domain = domain
  apply.slotKeys = [...slotKeys]
  apply.visible = true
}

defineExpose({ askApplyScope })
</script>
