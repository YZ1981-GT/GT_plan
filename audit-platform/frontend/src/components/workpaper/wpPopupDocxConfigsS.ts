/**
 * wpPopupDocxConfigsS — S 循环 docx 子底稿弹窗配置
 *
 * S 类（专项循环）docx 底稿弹窗注册：S12A / S33-REV / S34-1-1
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
    templatePath: 'wp_templates/S/S12A 评估专家报告.docx',
    relatedLinks: [
      { label: 'S12 利用专家工作', wpCode: 'S12' },
      { label: 'S13 利用管理层专家', wpCode: 'S13' },
    ],
  },
  'S33-REV': {
    title: '综合核查程序修订说明',
    guidance: [
      '本文档记录 IPO 综合核查程序的修订说明及变更原因。',
      '修订说明应包括修订日期、修订内容及修订原因。',
    ],
    applicableNote: 'IPO/上市/新三板项目综合核查程序发生修订时适用',
    templatePath: 'wp_templates/S/S33 程序修订说明.docx',
    relatedLinks: [
      { label: 'S33-1 综合核查-内控制度', wpCode: 'S33-1' },
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
    templatePath: 'wp_templates/S/S34-1-1 信息披露豁免专项核查意见.docx',
    relatedLinks: [
      { label: 'S34-0 证监会核查事项清单', wpCode: 'S34-0' },
      { label: 'S34-1 涉秘豁免', wpCode: 'S34-1' },
    ],
  },
}
