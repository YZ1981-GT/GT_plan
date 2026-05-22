import type { Meta, StoryObj } from '@storybook/vue3'
import VRSummaryCard from '@/components/dashboard/VRSummaryCard.vue'
import type { VRSummaryData } from '@/composables/useDashboardData'

const meta = {
  title: 'Business/VRSummaryCard',
  component: VRSummaryCard,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'VR 验证规则汇总卡片：blocking 失败数 / 按循环分组展开 / 全部通过标识',
      },
    },
  },
} satisfies Meta<typeof VRSummaryCard>

export default meta
type Story = StoryObj<typeof meta>

const sampleVRData: VRSummaryData = {
  total_rules: 24,
  blocking_failed: 3,
  all_passed: false,
  by_cycle: [
    {
      cycle: 'D',
      blocking_failed: 1,
      failed_rules: [
        { rule_id: 'VR-D4-01', rule_name: '收入确认完整性', details: '期末余额差异 ¥12,500 超过容差 ¥5,000' },
      ],
    },
    {
      cycle: 'H',
      blocking_failed: 2,
      failed_rules: [
        { rule_id: 'VR-H1-01', rule_name: '固定资产期末勾稽', details: '期初+增加-减少-折旧 ≠ 期末，差异 ¥8,200' },
        { rule_id: 'VR-H8-01', rule_name: '使用权资产余额', details: '使用权资产与租赁负债不匹配' },
      ],
    },
  ],
}

export const Default: Story = {
  args: {
    vrSummary: sampleVRData,
    error: null,
  },
}

export const AllPassed: Story = {
  args: {
    vrSummary: {
      total_rules: 24,
      blocking_failed: 0,
      all_passed: true,
      by_cycle: [],
    },
    error: null,
  },
}

export const ErrorState: Story = {
  args: {
    vrSummary: null,
    error: '网络请求超时，请稍后重试',
  },
}
