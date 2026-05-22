import type { Meta, StoryObj } from '@storybook/vue3'
import ReviewLayerBadges from '@/components/workpaper/ReviewLayerBadges.vue'

const meta = {
  title: 'Business/ReviewLayerBadges',
  component: ReviewLayerBadges,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: '5 层复核体系状态 badge（L1~L5 + 专委会/IT审计/税务专家）',
      },
    },
  },
} satisfies Meta<typeof ReviewLayerBadges>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectId: 'proj-001',
    wpId: 'wp-001',
    wpCode: 'D2-1',
  },
}

export const WithWpCode: Story = {
  args: {
    projectId: 'proj-001',
    wpId: 'wp-002',
    wpCode: 'H1-12',
  },
}
