import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarkdownAnswer from '../../frontend/src/features/chat/MarkdownAnswer.vue'
import { clearDrafts, useDraft } from '../../frontend/src/features/chat/drafts'

describe('reading workspace', () => {
  it('keeps navigation drafts scoped and clears deleted sessions', () => {
    useDraft('p', 's', 'question').value = '未发送的问题'
    expect(useDraft('p', 's', 'question').value).toBe('未发送的问题')
    expect(useDraft('p', 'other', 'question').value).toBe('')
    expect(useDraft('other', 's', 'question').value).toBe('')
    expect(useDraft('p', 's', 'note').value).toBe('')
    clearDrafts('p', 's')
    expect(useDraft('p', 's', 'question').value).toBe('')
  })
  it('renders fractions, scripts and Greek letters without exposing raw HTML', async () => {
    const view = mount(MarkdownAnswer, {
      props: {
        text: String.raw`公式 $f_d(u)\approx\frac{1}{2}\rho C_d A u_0^2$。<img src=x onerror=alert(1)>`,
      },
    })
    expect(view.find('.katex').exists()).toBe(true)
    expect(view.find('.mfrac').exists()).toBe(true)
    expect(view.find('img').exists()).toBe(false)
    expect(view.find('math').exists()).toBe(true)
    await view.setProps({ text: String.raw`\[\frac{x_1}{2}\]` })
    expect(view.find('.katex-display').exists()).toBe(true)
    await view.setProps({ text: String.raw`$\href{javascript:alert(1)}{x}$` })
    expect(view.find('a').exists()).toBe(false)
    await view.setProps({ text: '`$x_1$`' })
    expect(view.find('.katex').exists()).toBe(false)
    view.unmount()
  })
})
