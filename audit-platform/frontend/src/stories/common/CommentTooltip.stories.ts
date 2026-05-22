import type { Meta, StoryObj } from '@storybook/vue3'
import CommentTooltip from '@/components/common/CommentTooltip.vue'

const meta = {
  title: 'Common/CommentTooltip',
  component: CommentTooltip,
  tags: ['autodocs'],
  decorators: [
    () => ({ template: '<div style="padding: 60px;"><story /></div>' }),
  ],
} satisfies Meta<typeof CommentTooltip>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    comment: {
      id: '1',
      project_id: 'p1',
      year: 2025,
      module: 'tb',
      sheet_key: 'sheet1',
      row_idx: 4,
      col_idx: 1,
      row_name: '银行存款',
      col_name: '期末余额',
      comment: '此金额需要复核确认',
      comment_type: 'comment',
      status: 'pending',
      created_at: '2025-06-01T10:30:00Z',
    },
  },
  render: (args) => ({
    components: { CommentTooltip },
    setup: () => ({ args }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥5,000,000</span></CommentTooltip>',
  }),
}

export const ReviewComment: Story = {
  args: {
    comment: {
      id: '2',
      project_id: 'p1',
      year: 2025,
      module: 'tb',
      sheet_key: 'sheet1',
      row_idx: 9,
      col_idx: 2,
      row_name: '应收账款',
      col_name: '期末余额',
      comment: '已复核，金额正确',
      comment_type: 'review',
      status: 'reviewed',
      created_at: '2025-06-02T14:00:00Z',
    },
  },
  render: (args) => ({
    components: { CommentTooltip },
    setup: () => ({ args }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#e8f5e9;border-radius:4px">¥1,200,000</span></CommentTooltip>',
  }),
}

export const NoComment: Story = {
  args: {
    comment: null,
  },
  render: (args) => ({
    components: { CommentTooltip },
    setup: () => ({ args }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥800,000</span></CommentTooltip>',
  }),
}
