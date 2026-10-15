<script setup lang="ts">
import { ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type { ChatRun, Document, Evidence } from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import ModelSettings from './ModelSettings.vue'
import MarkdownAnswer from './MarkdownAnswer.vue'
import EvidenceView from './EvidenceView.vue'
const props = defineProps<{ projectId: string; sessionId: string }>()
const emit = defineEmits<{ design: [intent: { goal: string; document_ids: string[] }] }>()
const client = useQueryClient()
const question = ref('')
const selected = ref('')
const busy = ref(false)
const error = ref('')
const evidence = ref<Evidence>()
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
        placeholder="请说明研究问题、方法、结果和局限"
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
  <EvidenceView
    v-if="evidence"
    :key="`${evidence.asset_id}:${evidence.id}`"
    :project-id="projectId"
    :evidence="evidence"
    @close="evidence = undefined"
  />
</template>
