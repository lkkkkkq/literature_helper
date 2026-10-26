<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  getDocument,
  GlobalWorkerOptions,
  TextLayer,
  type PDFDocumentProxy,
  type PDFDocumentLoadingTask,
  type RenderTask,
} from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'
import type { SourceLocation } from '../../../../desktop/src/shared/contracts'

GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps<{ data: Uint8Array; location?: SourceLocation; quote?: string }>()
const pageNumber = ref(1)
const pages = ref(0)
const zoom = ref(-1)
const scroller = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref('')
const holder = ref<HTMLDivElement>()
let document: PDFDocumentProxy | undefined
let loadingTask: PDFDocumentLoadingTask | undefined
let renderTask: RenderTask | undefined
let textLayer: TextLayer | undefined
let generation = 0
let disposed = false
const highlight = computed(() => {
  if (props.location?.page !== pageNumber.value || !props.location.bbox) return undefined
  const [left, top, width, height] = props.location.bbox
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  }
})
async function renderPage() {
  if (!document || !holder.value) return
  const ticket = ++generation
  renderTask?.cancel()
  textLayer?.cancel()
  loading.value = true
  error.value = ''
  holder.value.replaceChildren()
  try {
    const page = await document.getPage(pageNumber.value)
    if (ticket !== generation || disposed) return
    const natural = page.getViewport({ scale: 1 })
    const widthScale = Math.max(
      0.1,
      ((scroller.value?.clientWidth ?? natural.width) - 28) / natural.width,
    )
    const heightScale = Math.max(0.1, ((scroller.value?.clientHeight || 720) - 28) / natural.height)
    const scale = zoom.value === -1 ? Math.min(widthScale, heightScale) : zoom.value || widthScale
    const viewport = page.getViewport({ scale })
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    const canvas = window.document.createElement('canvas')
    canvas.width = Math.ceil(viewport.width * ratio)
    canvas.height = Math.ceil(viewport.height * ratio)
    canvas.style.width = `${viewport.width}px`
    canvas.style.height = `${viewport.height}px`
    const context = canvas.getContext('2d')!
    renderTask = page.render({
      canvas,
      canvasContext: context,
      viewport,
      transform: [ratio, 0, 0, ratio, 0, 0],
    })
    await renderTask.promise
    if (ticket !== generation || disposed) return
    const text = window.document.createElement('div')
    text.className = 'textLayer'
    text.style.setProperty('--scale-factor', String(scale))
    text.style.setProperty('--total-scale-factor', String(scale))
    textLayer = new TextLayer({
      textContentSource: await page.getTextContent(),
      container: text,
      viewport,
    })
    await textLayer.render()
    if (ticket !== generation || disposed) return
    holder.value.style.width = `${viewport.width}px`
    holder.value.style.height = `${viewport.height}px`
    holder.value.append(canvas, text)
    const pageBounds = holder.value.getBoundingClientRect()
    const region = props.location?.page === pageNumber.value ? props.location.bbox : undefined
    const normalized = props.quote?.replace(/\s+/g, ' ').trim()
    if (normalized)
      for (const span of text.querySelectorAll('span')) {
        const value = span.textContent?.replace(/\s+/g, ' ').trim()
        const bounds = span.getBoundingClientRect()
        if (region) {
          const [x, y, width, height] = region
          if (
            bounds.right < pageBounds.left + x * viewport.width ||
            bounds.left > pageBounds.left + (x + width) * viewport.width ||
            bounds.bottom < pageBounds.top + y * viewport.height ||
            bounds.top > pageBounds.top + (y + height) * viewport.height
          )
            continue
        }
        if (value && value.length > 2 && (normalized.includes(value) || value.includes(normalized)))
          span.classList.add('evidence-text')
      }
  } catch (cause) {
    if (
      ticket === generation &&
      !disposed &&
      !(cause instanceof Error && cause.name === 'RenderingCancelledException')
    )
      error.value = cause instanceof Error ? cause.message : '页面渲染失败'
  } finally {
    if (ticket === generation && !disposed) loading.value = false
  }
}
async function load() {
  try {
    const base = window.document.baseURI
    loadingTask = getDocument({
      data: new Uint8Array(props.data),
      cMapUrl: new URL('./pdfjs/cmaps/', base).href,
      cMapPacked: true,
      standardFontDataUrl: new URL('./pdfjs/standard_fonts/', base).href,
      wasmUrl: new URL('./pdfjs/wasm/', base).href,
    })
    document = await loadingTask.promise
    if (disposed) return
    pages.value = document.numPages
    pageNumber.value = Math.max(1, Math.min(pages.value, props.location?.page ?? 1))
    await renderPage()
  } catch (cause) {
    if (!disposed) {
      error.value = cause instanceof Error ? cause.message : 'PDF 无法打开'
      loading.value = false
    }
  }
}
function navigate(value: number) {
  if (Number.isFinite(value))
    pageNumber.value = Math.max(1, Math.min(pages.value, Math.trunc(value)))
}
watch([pageNumber, zoom], () => {
  void renderPage()
})
watch(
  () => props.location,
  (value) => {
    if (!value || !pages.value) return
    if (value.page === pageNumber.value) void renderPage()
    else navigate(value.page)
  },
)
let resizeTimer: ReturnType<typeof setTimeout> | undefined
let observer: ResizeObserver | undefined
function resize() {
  clearTimeout(resizeTimer)
  if (zoom.value <= 0)
    resizeTimer = setTimeout(() => {
      void renderPage()
    }, 120)
}
onMounted(() => {
  window.addEventListener('resize', resize)
  observer = new ResizeObserver(resize)
  if (scroller.value) observer.observe(scroller.value)
  void load()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  observer?.disconnect()
  clearTimeout(resizeTimer)
  disposed = true
  generation++
  renderTask?.cancel()
  textLayer?.cancel()
  void loadingTask?.destroy()
})
</script>

<template>
  <section class="pdf-reader" aria-label="PDF 原文阅读器">
    <div class="pdf-toolbar">
      <button :disabled="pageNumber <= 1 || !pages" @click="navigate(pageNumber - 1)">
        上一页
      </button>
      <label>
        页码
        <input
          aria-label="PDF 页码"
          type="number"
          :value="pageNumber"
          min="1"
          :max="pages"
          @change="navigate(Number(($event.target as HTMLInputElement).value))"
        />
      </label>
      <span data-testid="pdf-pages">/ {{ pages }}</span>
      <button :disabled="pageNumber >= pages || !pages" @click="navigate(pageNumber + 1)">
        下一页
      </button>
      <select v-model.number="zoom" aria-label="PDF 缩放">
        <option :value="-1">适应整页</option>
        <option :value="0">适应宽度</option>
        <option :value="0.75">75%</option>
        <option :value="1">100%</option>
        <option :value="1.25">125%</option>
        <option :value="1.5">150%</option>
      </select>
    </div>
    <p v-if="error" role="alert" class="error-box">PDF 无法显示：{{ error }}</p>
    <p v-if="loading" class="muted" role="status">正在渲染原文页面…</p>
    <div ref="scroller" class="pdf-scroll">
      <div class="pdf-page-wrap">
        <div ref="holder" class="pdf-page"></div>
        <div
          v-if="highlight && !loading && !error"
          class="evidence-bbox"
          data-testid="evidence-bbox"
          :style="highlight"
          aria-label="原文证据区域"
        ></div>
      </div>
    </div>
  </section>
</template>
