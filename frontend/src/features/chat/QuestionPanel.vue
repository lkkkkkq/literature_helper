<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type { ChatRun, Document, Evidence } from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import ModelSettings from './ModelSettings.vue'
import MarkdownAnswer from './MarkdownAnswer.vue'
import EvidenceView from './EvidenceView.vue'
import { useDraft } from './drafts'
const props = defineProps<{ projectId: string; sessionId: string }>()
const emit = defineEmits<{ design: [intent: { goal: string; document_ids: string[] }] }>()
const client = useQueryClient()
const question = useDraft(props.projectId, props.sessionId, 'question')
const selected = useDraft(props.projectId, props.sessionId, 'question-scope')
const busy = ref(false)
const error = ref('')
const evidence = ref<Evidence>()
const layout = ref<HTMLElement>()
const sidebarWidth = ref(50)
const sidebar = ref<HTMLElement>()
const sidebarHeight = ref('calc(100vh - 220px)')
function fitSidebar() {
  if (!sidebar.value) return
  sidebarHeight.value = `${Math.max(300, window.innerHeight - Math.max(16, sidebar.value.getBoundingClientRect().top) - 16)}px`
}
watch(evidence, async () => {
  await nextTick()
  fitSidebar()
})
onMounted(() => {
  window.addEventListener('scroll', fitSidebar, { passive: true })
  window.addEventListener('resize', fitSidebar)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', fitSidebar)
  window.removeEventListener('resize', fitSidebar)
})
const canSend = computed(
  () =>
    !busy.value &&
    !!question.value.trim() &&
    !history.data.value?.some((row) => row.status === 'running'),
)
function questionKeydown(event: KeyboardEvent) {
  if (
    event.key !== 'Enter' ||
    event.shiftKey ||
    event.ctrlKey ||
    event.altKey ||
    event.metaKey ||
    event.isComposing ||
    event.keyCode === 229
  )
    return
  event.preventDefault()
  if (!event.repeat && canSend.value) void ask()
}
function resizeSidebar(event: PointerEvent) {
  if (!(event.currentTarget instanceof HTMLElement)) return
  event.currentTarget.setPointerCapture(event.pointerId)
}
function moveSidebar(event: PointerEvent) {
  const handle = event.currentTarget as HTMLElement
  if (!handle.hasPointerCapture(event.pointerId) || !layout.value) return
  const box = layout.value.getBoundingClientRect()
  sidebarWidth.value = Math.max(30, Math.min(65, ((box.right - event.clientX) / box.width) * 100))
}
function stopResize(event: PointerEvent) {
  const handle = event.currentTarget as HTMLElement
  if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId)
}
function resizeKey(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return
  event.preventDefault()
  sidebarWidth.value =
    event.key === 'Home'
      ? 50
      : Math.max(30, Math.min(65, sidebarWidth.value + (event.key === 'ArrowLeft' ? 2 : -2)))
}
const key = ['answers', props.projectId, props.sessionId]
const history = useQuery({
  queryKey: key,
  queryFn: () =>
    request<ChatRun[]>({
      action: 'answers',
      projectId: props.projectId,
      sessionId: props.sessionId,
    }),
  refetchInterval: (query) =>
    query.state.data?.some((row) => row.status === 'running') ? 1500 : false,
  refetchIntervalInBackground: true,
})
const documents = useQuery({
  queryKey: ['documents', props.projectId],
  queryFn: () => request<Document[]>({ action: 'documents', projectId: props.projectId }),
})
async function ask() {
  if (!canSend.value) return
  busy.value = true
  error.value = ''
  try {
    const route = await request<{ intent: string }>({
      action: 'route',
      projectId: props.projectId,
      text: question.value,
    })
    if (route.intent === 'DESIGN') {
      emit('design', { goal: question.value, document_ids: selected.value ? [selected.value] : [] })
      question.value = ''
      return
    }
    const result = await request<ChatRun>({
      action: 'ask',
      projectId: props.projectId,
      sessionId: props.sessionId,
      question: question.value,
      document_ids: selected.value ? [selected.value] : [],
      request_id: crypto.randomUUID(),
    })
    if (result.status === 'failed') error.value = result.error ?? '回答失败'
    else question.value = ''
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
    await client.invalidateQueries({ queryKey: key })
  }
}
</script>
<template>
  <div
    ref="layout"
    class="qa-layout"
    :class="{ 'has-evidence': evidence }"
    :style="{ '--evidence-width': `${sidebarWidth}%`, '--evidence-height': sidebarHeight }"
  >
    <div class="qa-conversation">
      <ModelSettings :project-id="projectId" />
      <div class="qa-history">
        <p v-if="history.isError.value" role="alert" class="error-box">
          {{ readableError(history.error.value) }}
        </p>
        <article v-for="run in history.data.value ?? []" :key="run.id" class="qa-turn">
          <h3>{{ run.question }}</h3>
          <p v-if="run.status === 'running'" role="status">正在检索原文并生成回答…</p>
          <p v-if="run.error" role="alert" class="error-box">{{ run.error }}</p>
          <template v-if="run.answer">
            <section v-for="(part, index) in run.answer.parts" :key="index" class="answer-part">
              <MarkdownAnswer :text="part.text" />
              <button
                v-for="source in run.answer.evidence.filter((item) =>
                  part.evidence_ids.includes(item.id),
                )"
                :key="source.id"
                class="citation"
                @click="evidence = source"
              >
                [{{ source.id }}] {{ source.filename
                }}{{ source.locations[0] ? ` · 第 ${source.locations[0].page} 页` : ' · 附件原文' }}
              </button>
            </section>
            <details>
              <summary>回答范围与提示</summary>
              <p v-for="warning in run.answer.warnings" :key="warning">{{ warning }}</p>
            </details>
          </template>
        </article>
      </div>
      <form class="question-form" @submit.prevent="ask">
        <label>
          回答范围
          <select v-model="selected" :disabled="busy">
            <option value="">当前项目已解析的文献与附件</option>
            <option v-for="doc in documents.data.value ?? []" :key="doc.id" :value="doc.id">
              {{ doc.title }}
            </option>
          </select>
        </label>
        <label>
          文献问题
          <textarea
            v-model="question"
            rows="3"
            maxlength="10000"
            :disabled="busy"
            placeholder="请说明研究问题、方法、结果和局限（Enter 发送，Shift+Enter 换行）"
            @keydown="questionKeydown"
          />
        </label>
        <p v-if="error" role="alert" class="error-box">{{ error }}</p>
        <button
          class="primary"
          :disabled="
            busy || !question.trim() || history.data.value?.some((row) => row.status === 'running')
          "
        >
          {{ busy ? '正在回答…' : '发送问题' }}
        </button>
      </form>
    </div>
    <div
      v-if="evidence"
      class="evidence-divider"
      role="separator"
      tabindex="0"
      aria-label="调整证据侧栏宽度"
      aria-orientation="vertical"
      :aria-valuenow="Math.round(sidebarWidth)"
      :aria-valuemin="30"
      :aria-valuemax="65"
      @pointerdown="resizeSidebar"
      @pointermove="moveSidebar"
      @pointerup="stopResize"
      @pointercancel="stopResize"
      @keydown="resizeKey"
    />
    <aside v-if="evidence" ref="sidebar" class="evidence-sidebar" aria-label="原文证据侧栏">
      <EvidenceView
        v-if="evidence"
        :key="`${evidence.asset_id}:${evidence.id}`"
        :project-id="projectId"
        :evidence="evidence"
        @close="evidence = undefined"
      />
    </aside>
  </div>
</template>
