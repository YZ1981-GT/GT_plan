/**
 * wpPopupDocxConfigsS — S 循环 docx 子底稿弹窗配置
 *
 * S 类（专项循环）docx 底稿弹窗注册：S12A / S34-1-1
 *
 * ═══ 为什么没有 S33-REV（Task 63 裁决）═══
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
 * Requirements: 7.7, 9.4, 9.5, 12.8
 *
 * `S33-REV`（综合核查-程序修订说明）在 `backend/wp_templates/` 下**零载体**，Task 58
 * 统一 resolver 现算判 `template_missing`。本弹窗只提供两个动作 ——「在线编辑」（走
 * `onlyoffice-config`）与「下载模板」（走 `wp-templates/{code}/prefilled-download`）
 * —— 对零载体 wp_code **两者都必然失败**，属 Requirement 12.8 点名的假切换，故整条
 * 配置移除，不留 DEPRECATED 墓碑。
 *
 * 移除后 `INLINE_POPUP_WP_CODES.has('S33-REV') === false` ⇒ `GtAProgramConsole` 不再
 * 拦截跳转，chip 走正常导航到它的 `word-template` 宿主，由 `WorkpaperWordEditor` 按
 * 后端下发的 `html_data.word_carrier` 显示明确的「暂无 Word 模板」说明（同一判据、
 * 单一文案），而不是两个死按钮。`S33-REV` 在 `wp_index` 有真实记录（实测 2 个项目各
 * 1 条、2 个 working_paper 实例），跳转不会落空。
 *
 * 🔴 若日后模板库补齐了 `S33-REV` 的 DOCX 载体（裁决建议见
 * `backend/data/workpaper_sync_task63_subcode_adjudication.json` 的
 * `s33rev_carrier_hint`），恢复本条目时 `templatePath` 必须填**磁盘实存**路径 ——
 * 守卫 `test_popup_docx_template_paths_exist_on_disk` 会逐条比对磁盘。
 */

import type { DocxPopupConfig } from './wpPopupDocxConfigs'

export const S_DOCX_POPUP_CONFIGS: Record<string, DocxPopupConfig> = {
  'S12A': {
    title: '评估专家报告',
    guidance: [
      '本底稿用于评价利用专家工作时，评估专家出具报告的相关情况。',
      '应评估专家的胜任能力、客观性及工作范围是否满足审计目的。',
      '红色字体需根据项目具体情况填写或删除。',
    ],
    applicableNote: '利用评估专家工作时适用',
    // 磁盘实存名（Task 63 勘查修正）：原值 `S12A 评估专家报告.docx` 在模板库不存在。
    templatePath: 'wp_templates/S/S12A 评估专家工作报告（或评估专家工作总结）.docx',
    relatedLinks: [
      { label: 'S12 利用专家工作', wpCode: 'S12' },
      { label: 'S13 利用管理层专家', wpCode: 'S13' },
    ],
  },
  'S34-1-1': {
    title: '信息披露豁免专项核查意见',
    guidance: [
      '本文档为涉秘豁免信息披露专项核查意见书。',
      '适用于 IPO/上市公司申请信息披露豁免的情况。',
      '应包括豁免事项说明、法律依据及核查结论。',
    ],
    applicableNote: 'IPO/上市/新三板/再融资项目涉及信息披露豁免时适用',
    // 磁盘实存名（Task 63 勘查修正）：原值缺「申请的」三字，模板库无此文件。
    templatePath: 'wp_templates/S/S34-1-1 信息披露豁免申请的专项核查意见.docx',
    relatedLinks: [
      { label: 'S34-0 证监会核查事项清单', wpCode: 'S34-0' },
      { label: 'S34-1 涉秘豁免', wpCode: 'S34-1' },
    ],
  },
}
