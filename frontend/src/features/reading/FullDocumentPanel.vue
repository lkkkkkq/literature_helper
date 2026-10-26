<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { mathPlugin } from '../chat/math'
import { request, readableError } from '../../api/workspace'
import type { SourceLocation, WorkspaceRequest } from '../../../../desktop/src/shared/contracts'
import ChartDigitizer from './ChartDigitizer.vue'
import PdfReader from '../../components/pdf/PdfReader.vue'
import 'katex/dist/katex.min.css'

const props = defineProps<{ projectId: string; assetId: string; pdfData?: Uint8Array }>()
const emit = defineEmits<{ locate: [location: SourceLocation]; active: [value: boolean] }>()
type Block = {
  id: string
  kind: string
  markdown: string
  resources: string[]
  locations: (SourceLocation & {
    file?: string
    native_block?: number
    sheet?: string
    range?: string
  })[]
}
type Content = {
  blocks: Block[]
  report: { status: string; issues: Record<string, unknown>[] }
  corrections: { revision: number; block_id: string; markdown: string; reason: string }[]
}
const state = ref<{ status: string; error?: string; active?: { version: string } }>({
  status: 'idle',
})
const content = ref<Content>()
const error = ref('')
const busy = ref(false)
const version = computed(() => state.value.active?.version ?? '')
watch(version, (value) => emit('active', !!value))
const resourceUrls = ref<Record<string, string>>({})
const resourceTexts = ref<Record<string, string>>({})
const selectedChart = ref('')
const editing = ref('')
const revised = ref('')
const reason = ref('')
const batches = ref<{ complete: boolean; batches: { text: string; evidence_ids: string[] }[] }>()
const budget = ref(48000)
const focusedLocation = ref<SourceLocation>()
function locate(location: SourceLocation) {
  focusedLocation.value = { ...location }
  emit('locate', location)
}
const repairPages = ref('')
const sameVersion = ref(false)
const sourceNotice = ref('')
const markdown = new MarkdownIt({ html: true, linkify: false }).use(mathPlugin)
const safeTable = (content: string) =>
  DOMPurify.sanitize(content, {
    ALLOWED_TAGS: [
      'table',
      'thead',
      'tbody',
      'tfoot',
      'tr',
      'td',
      'th',
      'caption',
      'br',
      'sup',
      'sub',
      'strong',
      'em',
    ],
    ALLOWED_ATTR: ['colspan', 'rowspan'],
  })
markdown.renderer.rules.html_block = (tokens, index) => safeTable(tokens[index]!.content)
markdown.renderer.rules.html_inline = (tokens, index) => {
  const tag = tokens[index]!.content
  return /^<\/?(?:sup|sub|strong|em|br)\s*\/?>$/i.test(tag) ? tag : ''
}
markdown.renderer.rules.image = (tokens, index) => {
  const source = resourceUrls.value[tokens[index]!.attrGet('src') ?? '']
  return source ? `<img src="${source}" alt="解析图片" />` : '<span>图片正在加载或资源缺失</span>'
}
const api = <T,>(
  operation: Extract<WorkspaceRequest, { action: 'fullDocument' }>['operation'],
  payload?: Record<string, unknown>,
) =>
  request<T>({
    action: 'fullDocument',
    projectId: props.projectId,
    assetId: props.assetId,
    operation,
    version: version.value,
    payload,
  })
function render(text: string) {
  const html = DOMPurify.sanitize(markdown.render(text), {
    FORBID_TAGS: [
      'iframe',
      'script',
      'style',
      'form',
      'input',
      'object',
      'embed',
      'a',
      'image',
      'use',
      'foreignObject',
      'video',
      'audio',
      'source',
      'link',
      'base',
      'meta',
    ],
    FORBID_ATTR: ['srcset'],
  })
  const container = window.document.createElement('div')
  container.innerHTML = html
  return container.innerHTML
}
async function guarded(task: () => Promise<void>) {
  error.value = ''
  busy.value = true
  try {
    await task()
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
async function refresh() {
  await guarded(async () => {
    state.value = await api('status')
  })
  if (!disposed && ['queued', 'running'].includes(state.value.status))
    timer = setTimeout(refresh, 1500)
}
watch(version, async (value) => {
  if (!value) return
  await guarded(async () => {
    content.value = await api<Content>('content')
    resourceUrls.value = {}
    resourceTexts.value = {}
    selectedChart.value = ''
    for (const name of new Set(content.value.blocks.flatMap((block) => block.resources))) {
      const result = await api<{ data_url?: string; text?: string }>('resource', { name })
      if (result.data_url) resourceUrls.value[name] = result.data_url
      if (result.text) resourceTexts.value[name] = result.text
    }
  })
})
void refresh()
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
})
async function start() {
  await guarded(async () => {
    state.value = await api('start', { pages: repairPages.value.trim() || 'all' })
  })
  clearTimeout(timer)
  timer = setTimeout(refresh, 1000)
}
async function cancel() {
  await guarded(async () => {
    state.value = await api('cancel')
  })
}
function blockText(block: Block) {
  return (
    content.value?.corrections.filter((item) => item.block_id === block.id).at(-1)?.markdown ??
    block.markdown
  )
}
async function saveCorrection() {
  await guarded(async () => {
    await api('correct', {
      block_id: editing.value,
      markdown: revised.value,
      reason: reason.value,
      base_revision: content.value?.corrections.length ?? 0,
    })
    content.value = await api('content')
    editing.value = ''
    reason.value = ''
  })
}
function beginCorrection(block: Block) {
  editing.value = block.id
  revised.value = blockText(block)
}
async function preferSource(confirmed: boolean) {
  await guarded(async () => {
    const response = await api<{ notice: string }>('prefer_source', {
      confirmed_same_version: confirmed,
    })
    sourceNotice.value = response.notice
  })
}
</script>
<template>
  <section class="full-document-panel">
    <h2>新版完整解析</h2>
    <p>PDF 使用本地 MinerU Standard。原生附件独立解析；不会替代主论文，也不会覆盖旧答案引用。</p>
    <button :disabled="busy || ['queued', 'running'].includes(state.status)" @click="start">
      生成新版全文
    </button>
    <button v-if="['queued', 'running'].includes(state.status)" @click="cancel">取消解析</button>
    <span role="status">{{ state.status }}</span>
    <details v-if="version">
      <summary>仅重做指定 PDF 页</summary>
      <label>
        页码（留空为整篇）
        <input v-model="repairPages" placeholder="例如 3-5,8" />
      </label>
      <p>重做页与其他原页合成一个新版本；旧版本和修正记录保留，不自动套用旧修正。</p>
    </details>
    <p v-if="error || state.error" role="alert" class="error-box">{{ error || state.error }}</p>
    <template v-if="content">
      <details>
        <summary>原生正文优先设置</summary>
        <p>
          仅当 Word／LaTeX／Markdown 是与主 PDF
          相同版本的正文时使用。补充材料和草稿不应替代正式论文。
        </p>
        <label>
          <input v-model="sameVersion" type="checkbox" />
          我已核对标题、版本和正文，确认同版
        </label>
        <button :disabled="!sameVersion" @click="preferSource(true)">
          将当前原生文件设为正文优先来源
        </button>
        <button @click="preferSource(false)">恢复主论文与附件各自使用</button>
        <p>{{ sourceNotice }}</p>
      </details>
      <details>
        <summary>处理报告 · {{ content.report.issues.length }} 项待核对</summary>
        <p>已生成内容不等于已核对准确；图像已保存不等于图表数据已提取。</p>
        <pre v-for="(issue, i) in content.report.issues" :key="i">{{ issue }}</pre>
      </details>
      <label>
        全文分批预算（字符）
        <input v-model.number="budget" type="number" min="256" max="2000000" />
      </label>
      <button
        @click="
          guarded(async () => {
            batches = await api('fulltext', { budget })
          })
        "
      >
        检查完整全文出口
      </button>
      <details v-if="batches">
        <summary>
          {{ batches.batches.length }} 批 · 全文覆盖 {{ batches.complete ? '完整' : '不完整' }}
        </summary>
        <p>这里只展示输入内容，不调用模型。图片需另行读取，不能仅凭路径认为已理解图像。</p>
        <textarea
          v-for="(batch, i) in batches.batches"
          :key="i"
          :value="batch.text"
          readonly
          rows="8"
          :aria-label="`全文第 ${i + 1} 批`"
        />
      </details>
      <div class="full-reading-layout" :class="{ 'has-original': pdfData }">
        <div class="full-blocks">
          <article v-for="block in content.blocks" :key="block.id" class="content-block">
            <div class="block-meta">
              <span>{{ block.kind }} · {{ block.id.split(':').at(-1) }}</span>
              <template v-for="(location, i) in block.locations" :key="i">
                <button v-if="location.page" @click="locate(location)">
                  第 {{ location.page }} 页 · 定位原文
                </button>
                <span v-else>
                  {{ location.file }} {{ location.sheet }} {{ location.range }}
                  {{ location.native_block ? `内容块 ${location.native_block}` : '' }}
                </span>
              </template>
              <button @click="beginCorrection(block)">修正</button>
            </div>
            <!-- Content is sanitized, with images restricted to authenticated local resources. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div class="markdown-answer" v-html="render(blockText(block))"></div>
            <template v-for="name in block.resources" :key="name">
              <details v-if="resourceUrls[name]">
                <summary>原图／公式截图 · {{ name }}</summary>
                <img :src="resourceUrls[name]" :alt="name" style="max-width: 100%" />
                <button @click="selectedChart = name">提取图表数据</button>
              </details>
              <details v-else-if="resourceTexts[name]">
                <summary>原生数据 · {{ name }}</summary>
                <pre>{{ resourceTexts[name] }}</pre>
              </details>
            </template>
            <div v-if="editing === block.id">
              <textarea v-model="revised" rows="8" aria-label="修正内容" />
              <input v-model="reason" placeholder="修正原因" />
              <button @click="saveCorrection">保存修正记录</button>
              <button @click="editing = ''">放弃修改</button>
            </div>
          </article>
        </div>
        <aside v-if="pdfData" class="full-original">
          <h3>原文对照</h3>
          <PdfReader :data="pdfData" :location="focusedLocation" />
        </aside>
      </div>
      <ChartDigitizer
        v-if="selectedChart && resourceUrls[selectedChart]"
        :key="`${version}:${selectedChart}`"
        :project-id="projectId"
        :asset-id="assetId"
        :version="version"
        :resource="selectedChart"
        :image-url="resourceUrls[selectedChart]"
        @close="selectedChart = ''"
      />
    </template>
  </section>
</template>
<style scoped>
.full-document-panel {
  border: 1px solid #b8cfc5;
  border-radius: 12px;
  padding: 20px;
  margin: 20px 0;
}
.full-blocks {
  max-height: 70vh;
  overflow: auto;
  margin-top: 16px;
}
.full-reading-layout.has-original {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 20px;
}
.full-original {
  min-width: 0;
}
@media (max-width: 1000px) {
  .full-reading-layout.has-original {
    grid-template-columns: 1fr;
  }
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
button {
  margin: 4px;
}
</style>
