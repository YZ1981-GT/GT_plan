/**
 * H1 / H2 / H4 / H5 / H6 披露说明文本域的 AI section 键集与中文名（单一真源）
 *
 * 这五个循环的披露 Tab 原本**压根没有 AI 按钮**（探针实测 AI按钮=0），违反平台铁律
 * 「多 section 底稿每个文本区都要 AI 辅助」。H8/H9 另有 `h8/h9NoteAiSections.ts`
 * （它们是「按钮存在但 `emit` 无人处理」的死按钮，成因不同故单独文件记录）。
 *
 * 键集同时被后端守卫 `test_review_dialog_h_cycle_prompts.py` 读取，断言
 * `review_dialog._SECTION_PROMPTS` 全部登记且无孤儿。
 *
 * 🔴 H6 只有一个披露组件 `H6TabDisclosure.vue`（Listed/Soe 是 `v-bind="$props"`
 * 薄壳），故两变体共用同一批键。
 */
export type HCycleAiVariant = 'listed' | 'soe'

export const H_CYCLE_NOTE_AI_SECTIONS = {
  H1: {
    listed: {
      impairment: '减值测试披露说明',
      mortgage: '抵押、担保固定资产情况说明',
      sale: '明显高于账面价值出售交易说明',
      govSubsidy: '政府补助冲减固定资产说明',
      clearing: '超 1 年固定资产清理进展说明',
    },
    soe: {
      clearing: '固定资产清理说明',
    },
  },
  H2: {
    listed: {
      fundSource: '资金来源补充说明',
      impairment: '减值测试披露说明',
      mortgage: '抵押、担保在建工程情况说明',
    },
    soe: {
      impairment: '减值补充说明',
    },
  },
  H4: {
    listed: {
      note: '工程物资附注披露说明',
    },
    soe: {
      note: '工程物资附注披露说明',
    },
  },
  H5: {
    listed: {
      disclosure: '油气资产补充披露',
    },
    soe: {
      disclosure: '补充披露（国资监管要求）',
    },
  },
  H6: {
    listed: {
      clearing: '固定资产清理说明',
    },
    soe: {
      clearing: '固定资产清理说明',
    },
  },
} as const satisfies Record<string, Record<HCycleAiVariant, Record<string, string>>>

export type HCycleAiWpCode = keyof typeof H_CYCLE_NOTE_AI_SECTIONS

export function hCycleNoteAiSectionId(
  wpCode: HCycleAiWpCode,
  variant: HCycleAiVariant,
  key: string,
): string {
  return `${wpCode}-disclosure-${variant}-${key}`
}

export function hCycleNoteAiLabel(
  wpCode: HCycleAiWpCode,
  variant: HCycleAiVariant,
  key: string,
): string {
  const map = H_CYCLE_NOTE_AI_SECTIONS[wpCode][variant] as Record<string, string>
  return map[key] ?? key
}
