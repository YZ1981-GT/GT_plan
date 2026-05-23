import type { Meta, StoryObj } from '@storybook/vue3'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'

const meta = {
  title: 'Common/SignGateChecklist',
  component: GateReadinessPanel,
  tags: ['autodocs'],
} satisfies Meta<typeof GateReadinessPanel>

export default meta
type Story = StoryObj<typeof meta>

const sampleData = {
  ready: false,
  groups: [
    {
      id: 'workpapers',
      name: '底稿完成度',
      status: 'warning' as const,
      findings: [
        { error_code: 'WP_NOT_REVIEWED', severity: 'warning' as const, message: '部分底稿未复核', action_hint: '前往底稿列表完成复核' },
      ],
    },
    {
      id: 'reports',
      name: '报表与附注',
      status: 'blocking' as const,
      findings: [
        { error_code: 'NOTES_PENDING', severity: 'blocking' as const, message: '附注未定稿', action_hint: '前往附注模块完成定稿' },
      ],
    },
  ],
}

export const Default: Story = {
  args: { data: sampleData },
}

export const ReadyToSign: Story = {
  args: {
    data: {
      ready: true,
      groups: sampleData.groups.map((g) => ({ ...g, status: 'pass' as const, findings: [] })),
    },
  },
  parameters: {
    docs: { description: { story: '所有前置条件满足，可签字状态' } },
  },
}
