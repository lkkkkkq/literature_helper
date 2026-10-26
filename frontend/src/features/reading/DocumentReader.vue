<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type {
  Document,
  DocumentBlock,
  ParsedContent,
  ParseStatus,
  SourceLocation,
} from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import PdfReader from '../../components/pdf/PdfReader.vue'
import FullDocumentPanel from './FullDocumentPanel.vue'

const props = defineProps<{ projectId: string; document: Document }>()
defineEmits<{ close: [] }>()
const client = useQueryClient()
const selected = ref(
  props.document.assets.find((asset) => asset.role === 'main')?.id ??
    props.document.assets[0]?.id ??
    '',
)
const asset = computed(() => props.document.assets.find((item) => item.id === selected.value))
const isPdf = computed(() => asset.value?.kind === 'pdf')
const supported = computed(() => ['pdf', 'csv', 'xlsx', 'docx'].includes(asset.value?.kind ?? ''))
const ocr = ref(false)
const newReady = ref(false)
watch(selected, () => {
  newReady.value = false
})
const location = ref<SourceLocation>()
const quote = ref('')
const selectedBlock = ref('')
const filter = ref('')
const tab = ref<'all' | 'table'>('all')
const parseStatus = useQuery({
  queryKey: computed(() => ['parse', props.projectId, selected.value]),
  enabled: computed(() => !!selected.value),
  queryFn: ({ queryKey }) =>
    request<ParseStatus>({
      action: 'parseStatus',
      projectId: props.projectId,
      assetId: String(queryKey[2]),
    }),
  refetchInterval: (query) =>
    ['queued', 'running'].includes(query.state.data?.status ?? '') ? 1200 : false,
  refetchIntervalInBackground: true,
})
const content = useQuery({
  queryKey: computed(() => [
    'content',
    props.projectId,
    selected.value,
    parseStatus.data.value?.run_id,
  ]),
  enabled: computed(() => parseStatus.data.value?.status === 'ready'),
  queryFn: ({ queryKey }) =>
    request<ParsedContent>({
      action: 'parsedContent',
      projectId: props.projectId,
      assetId: String(queryKey[2]),
    }),
})
const pdf = useQuery({
  queryKey: computed(() => ['pdf', props.projectId, selected.value, asset.value?.sha256]),
  enabled: computed(() => isPdf.value && asset.value?.status !== 'missing'),
  queryFn: ({ queryKey }) =>
    request<Uint8Array>({
      action: 'pdfBytes',
      projectId: props.projectId,
      assetId: String(queryKey[2]),
    }),
  staleTime: 0,
  gcTime: 0,
})
const parse = useMutation({
  mutationFn: (assetId: string) =>
    request<ParseStatus>({
      action: 'parseAsset',
      projectId: props.projectId,
      assetId,
      ocr: ocr.value && isPdf.value,
      force: true,
    }),
  onSuccess: (state, assetId) => {
    client.setQueryData(['parse', props.projectId, assetId], state)
  },
})
const running = computed(
  () =>
    parse.isPending.value || ['queued', 'running'].includes(parseStatus.data.value?.status ?? ''),
)
const blocks = computed(() =>
  (content.data.value?.blocks ?? []).filter(
    (block) =>
      (tab.value !== 'table' || block.kind === 'table') &&
      (!filter.value ||
        `${block.text} ${block.cells.map((cell) => cell.text).join(' ')}`
          .toLowerCase()
          .includes(filter.value.toLowerCase())),
  ),
)
const headings = computed(
  () => content.data.value?.blocks.filter((block) => block.kind === 'heading') ?? [],
)
function focusBlock(block: DocumentBlock, source = block.locations[0]) {
  selectedBlock.value = block.id
  quote.value = block.text
  location.value = source ? { ...source } : undefined
}
async function goSection(id: string) {
  const block = content.data.value?.blocks.find((item) => item.id === id)
  if (block) {
    filter.value = ''
    tab.value = 'all'
    focusBlock(block)
    await nextTick()
    window.document.getElementById(`block-${id}`)?.scrollIntoView({ block: 'nearest' })
  }
}
watch(selected, () => {
  location.value = undefined
  quote.value = ''
  selectedBlock.value = ''
  filter.value = ''
  parse.reset()
})
</script>

<template>
  <section class="document-reader">
    <div class="reader-heading">
      <button @click="$emit('close')">← 返回文献清单</button>
      <h1>{{ document.title }}</h1>
    </div>
    <nav class="asset-tabs" aria-label="主论文与附件">
      <button
        v-for="file in document.assets"
        :key="file.id"
        :class="{ selected: selected === file.id }"
        @click="selected = file.id"
      >
        {{ file.role === 'main' ? '主论文' : '附件' }} · {{ file.relative_path }}
      </button>
    </nav>
    <div v-if="asset" class="reader-controls">
      <span>{{ asset.kind.toUpperCase() }}</span>
      <label v-if="isPdf" class="inline-check">
        <input v-model="ocr" type="checkbox" :disabled="running" />
        识别扫描页文字（中英文）
      </label>
      <button
        class="primary"
        :disabled="!supported || running || asset.status === 'missing'"
        @click="parse.mutate(selected)"
      >
        {{
          running
            ? '正在解析…'
            : parseStatus.data.value?.status === 'ready'
              ? '重新解析'
              : '解析文档'
        }}
      </button>
      <span v-if="parseStatus.data.value?.status === 'ready'" class="badge">解析完成</span>
    </div>
    <p v-if="!supported" class="warning">
      此格式暂不支持正文解析，请转换为 PDF、CSV、XLSX 或 DOCX。
    </p>
    <p v-if="asset?.status === 'missing'" class="error-box">源文件缺失，请检查路径并重新扫描。</p>
    <p v-if="running" class="notice" role="status">
      正在本机处理文档，可切换项目。首次解析 PDF 可能需要下载阅读资源；这不会上传论文内容。
    </p>
    <p v-if="parse.isError.value" role="alert" class="error-box">
      {{ readableError(parse.error.value) }}
    </p>
    <p v-if="parseStatus.isError.value" role="alert" class="error-box">
      {{ readableError(parseStatus.error.value) }}
    </p>
    <p v-if="parseStatus.data.value?.error" role="alert" class="error-box">
      {{ parseStatus.data.value.error }}
    </p>
    <FullDocumentPanel
      v-if="asset"
      :key="selected"
      :project-id="projectId"
      :asset-id="selected"
      :pdf-data="isPdf ? pdf.data.value : undefined"
      @locate="location = $event"
      @active="newReady = $event"
    />
    <details :open="!newReady">
      <summary v-if="newReady">展开旧版解析与核对</summary>
      <div class="reader-panels" :class="{ 'with-pdf': isPdf }">
        <div class="parsed-panel">
          <div class="section-heading">
            <h2>正文与表格</h2>
            <span v-if="content.data.value" class="muted">
              {{ content.data.value.blocks.length }} 个内容块
            </span>
          </div>
          <p v-if="content.isError.value" role="alert" class="error-box">
            {{ readableError(content.error.value) }}
          </p>
          <p v-if="parseStatus.data.value?.status === 'unparsed'" class="empty-state">
            点击“解析文档”读取正文、章节和表格。PDF 原文可直接在右侧阅读。
          </p>
          <template v-if="content.data.value && parseStatus.data.value?.status === 'ready'">
            <details v-if="content.data.value.warnings.length" class="parse-notices">
              <summary>阅读提示（{{ content.data.value.warnings.length }}）</summary>
              <p v-for="warning in content.data.value.warnings" :key="warning">{{ warning }}</p>
            </details>
            <div class="content-filters">
              <input v-model="filter" aria-label="搜索正文和表格" placeholder="搜索正文和表格…" />
              <select v-model="tab" aria-label="内容类型">
                <option value="all">全部内容</option>
                <option value="table">只看表格</option>
              </select>
            </div>
            <select
              v-if="headings.length"
              aria-label="跳转章节"
              @change="goSection(($event.target as HTMLSelectElement).value)"
            >
              <option value="">跳转到章节…</option>
              <option v-for="heading in headings" :key="heading.id" :value="heading.id">
                {{ heading.text }}
              </option>
            </select>
            <div class="parsed-blocks">
              <p v-if="!blocks.length" class="muted">没有匹配的内容。</p>
              <article
                v-for="block in blocks"
                :id="`block-${block.id}`"
                :key="block.id"
                class="content-block"
                :class="{ active: selectedBlock === block.id }"
              >
                <div class="block-meta">
                  <span>
                    {{
                      block.kind === 'table'
                        ? '表格'
                        : block.kind === 'heading'
                          ? '章节'
                          : block.kind === 'picture'
                            ? '图示说明'
                            : '原文'
                    }}
                  </span>
                  <button
                    v-for="(position, index) in block.locations"
                    :key="index"
                    class="source-link"
                    @click="focusBlock(block, position)"
                  >
                    第 {{ position.page }} 页 · 定位原文
                  </button>
                  <span v-if="!block.locations.length" class="muted">无 PDF 页码</span>
                </div>
                <h3 v-if="block.kind === 'heading'">{{ block.text }}</h3>
                <p v-else-if="block.text">{{ block.text }}</p>
                <div v-if="block.kind === 'table'" class="parsed-table-scroll">
                  <table>
                    <tbody>
                      <tr v-for="row in block.rows" :key="row">
                        <component
                          :is="cell.header ? 'th' : 'td'"
                          v-for="(cell, cellIndex) in block.cells
                            .filter((cell) => cell.row === row - 1)
                            .sort((a, b) => a.column - b.column)"
                          :key="cellIndex"
                          :rowspan="cell.row_span"
                          :colspan="cell.column_span"
                        >
                          {{ cell.text }}
                        </component>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
            </div>
            <p class="milestone-note">解析结果仅用于阅读与定位；表格和文字仍需结合原文复核。</p>
          </template>
        </div>
        <div v-if="isPdf" class="original-panel">
          <h2>PDF 原文</h2>
          <p v-if="pdf.isPending.value">正在读取 PDF…</p>
          <p v-if="pdf.isError.value" role="alert" class="error-box">
            {{ readableError(pdf.error.value) }}
          </p>
          <PdfReader
            v-if="pdf.data.value && !pdf.isError.value"
            :key="`${selected}:${asset?.sha256}`"
            :data="pdf.data.value"
            :location="location"
            :quote="quote"
          />
        </div>
      </div>
    </details>
  </section>
</template>
