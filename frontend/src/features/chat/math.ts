import type MarkdownIt from 'markdown-it'
import katex from 'katex'

export function mathPlugin(markdown: InstanceType<typeof MarkdownIt>) {
  markdown.inline.ruler.before('escape', 'formula', (state, silent) => {
    const rest = state.src.slice(state.pos)
    const delimiter = [
      ['$$', '$$', true],
      ['\\[', '\\]', true],
      ['\\(', '\\)', false],
      ['$', '$', false],
    ].find(([left]) => rest.startsWith(String(left)))
    if (!delimiter) return false
    const [left, right, display] = delimiter as [string, string, boolean]
    const end = state.src.indexOf(right, state.pos + left.length)
    if (end < 0) return false
    const formula = state.src.slice(state.pos + left.length, end)
    if (!formula.trim() || (left === '$' && (/^\s|\s$/.test(formula) || formula.includes('\n'))))
      return false
    if (!silent) {
      const token = state.push('formula', '', 0)
      token.content = formula
      token.meta = { display }
    }
    state.pos = end + right.length
    return true
  })
  markdown.renderer.rules.formula = (tokens, index) =>
    katex.renderToString(tokens[index]!.content, {
      displayMode: tokens[index]!.meta?.display === true,
      throwOnError: false,
      trust: false,
      maxExpand: 500,
      maxSize: 20,
      strict: 'ignore',
    })
}
