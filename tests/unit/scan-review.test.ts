import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { readonly } from 'vue'
import ScanReview from '../../frontend/src/features/projects/ScanReview.vue'
import type { ScanDraft } from '../../desktop/src/shared/contracts'

const draft: ScanDraft = {
  id: 'draft',
  project_id: 'project',
  base_revision: 0,
  created_at: '',
  snapshot: {
    assets: [],
    warnings: [],
    groups: [
      {
        key: 'a',
        title: '论文 A',
        main_path: 'a.pdf',
        asset_paths: ['a.pdf'],
        confidence: 'high',
        reason: 'test',
      },
      {
        key: 'b',
        title: '附件 B',
        main_path: null,
        asset_paths: ['b.csv'],
        confidence: 'review',
        reason: 'test',
      },
    ],
  },
}
describe('scan review', () => {
  it('edits a readonly server result without mutating the query cache', async () => {
    const view = mount(ScanReview, { props: { draft: readonly(draft) as ScanDraft, busy: false } })
    await view.get('select[aria-label="文件归属 b.csv"]').setValue('a')
    await view.get('button.primary').trigger('click')
    expect(view.emitted('confirm')?.[0]?.[0]).toEqual([
      { title: '论文 A', main_path: 'a.pdf', asset_paths: ['a.pdf', 'b.csv'] },
    ])
    expect(draft.snapshot.groups).toHaveLength(2)
    view.unmount()
  })
  it('blocks confirmation while rechecking or when titles are empty', async () => {
    const view = mount(ScanReview, { props: { draft, busy: true } })
    expect(view.get('button.primary').attributes('disabled')).toBeDefined()
    await view.setProps({ busy: false })
    await view.get('input[aria-label="文献标题"]').setValue(' ')
    expect(view.get('button.primary').attributes('disabled')).toBeDefined()
    view.unmount()
  })
})
