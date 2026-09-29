/**
 * useNoteDisclosureJumpActions — 附注 → 底稿披露表 / 上次同步底稿 的跳转动作
 *
 * 从 `DisclosureEditor.vue` 抽出（该宿主 HARD_CAPS ceiling 1800）。
 *
 * 两条跳转路径语义不同，不可合并：
 *   jumpToLastSyncWorkpaper —— 按 `note.last_sync_wp_id` 回到**实际推送过**的那张底稿
 *                              （sheet 名取 `_last_sync_sheet` / `_last_sync_sheet_name`）
 *   jumpToDisclosureSheet   —— 按章节**应当**关联的披露表族跳转：优先用同步记录里的
 *                              wp_id，缺失时经 ACNR `resolveInstance` 解析；解析不到
 *                              给出可执行提示（"请先在项目中生成"）而不是静默失败
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Router } from 'vue-router'

/** 披露表族 → 中文名（仅用于给用户可读提示，解析逻辑不依赖它） */
const WP_FAMILY_LABEL: Record<string, string> = {
  D1: '应收票据',
  E1: '货币资金',
  F1: '预付款项',
  F2: '存货',
  G1: '交易性金融资产',
  G7: '长期股权投资',
  G10: '交易性金融负债',
  G11: '投资收益',
  G13: '公允价值变动收益',
  G14: '信用减值损失',
  H1: '固定资产',
  H2: '在建工程',
  H8: '使用权资产',
  H9: '租赁负债',
  H10: '资产处置收益',
  I1: '无形资产',
  I2: '开发支出',
  I3: '商誉',
  I4: '长期待摊费用',
  I5: '其他非流动资产',
  I6: '研发费用',
  K1: '其他应收款',
  K11: '资产减值损失',
  K13: '营业外支出',
  N1: '递延所得税资产',
  J1: '应付职工薪酬',
}

export interface NoteDisclosureJumpTarget {
  wpCode?: string
  wpId?: string
  sheet: string
}

export interface UseNoteDisclosureJumpActionsOptions {
  currentNote: Ref<any> | ComputedRef<any>
  projectId: Ref<string> | ComputedRef<string>
  router: Router
  /** 从当前章节解析目标披露表（纯函数，来自 views/composables/noteDisclosureJump） */
  resolveTarget: (note: any) => NoteDisclosureJumpTarget | null
  /** ACNR 实例解析（wp_id 缺失时的兜底通路） */
  acnrResolveInstance: (p: {
    project_id: string
    parent: string
    sheet_code: string
  }) => Promise<{ found?: boolean; wp_id?: string } | null | undefined>
}

export function useNoteDisclosureJumpActions(options: UseNoteDisclosureJumpActionsOptions) {
  const { currentNote, projectId, router, resolveTarget, acnrResolveInstance } = options

  const jumpingDisclosure = ref(false)

  const disclosureJumpTarget = computed(() => resolveTarget(currentNote.value))

  function jumpToLastSyncWorkpaper(): void {
    const note = currentNote.value as any
    const wpId = note?.last_sync_wp_id
    if (!wpId || !projectId.value) return
    const sheet = note?.table_data?._last_sync_sheet
      || note?.table_data?._last_sync_sheet_name
      || ''
    router.push({
      path: `/projects/${projectId.value}/workpapers/${wpId}/edit`,
      query: sheet ? { sheet: String(sheet) } : {},
    })
  }

  /** 附注 → 披露表（上市/国企 sheet）；优先同步 wp_id，否则 ACNR 解析 */
  async function jumpToDisclosureSheet(): Promise<void> {
    const target = disclosureJumpTarget.value
    const wpFamily = target?.wpCode ?? 'G7'
    const wpFamilyLabel = WP_FAMILY_LABEL[wpFamily] ?? wpFamily
    if (!target || !projectId.value) {
      ElMessage.warning(`当前章节未关联${wpFamilyLabel}披露表`)
      return
    }
    jumpingDisclosure.value = true
    try {
      let wpId = target.wpId
      if (!wpId) {
        const res = await acnrResolveInstance({
          project_id: projectId.value,
          parent: wpFamily,
          sheet_code: wpFamily,
        })
        if (res?.found && res.wp_id) wpId = res.wp_id
      }
      if (!wpId) {
        ElMessage.warning(`未找到 ${wpFamily} 底稿，请先在项目中生成`)
        return
      }
      router.push({
        path: `/projects/${projectId.value}/workpapers/${wpId}/edit`,
        query: { sheet: target.sheet },
      })
    } catch {
      ElMessage.warning(`跳转披露表失败，请手动打开 ${wpFamily} 底稿`)
    } finally {
      jumpingDisclosure.value = false
    }
  }

  return { jumpingDisclosure, disclosureJumpTarget, jumpToLastSyncWorkpaper, jumpToDisclosureSheet }
}

export { WP_FAMILY_LABEL }
