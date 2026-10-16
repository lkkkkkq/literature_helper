<script setup lang="ts">
import { ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Conversation, Note, Project } from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import QuestionPanel from './QuestionPanel.vue'
import ExtractionPanel from '../jobs/ExtractionPanel.vue'
import { useDraft } from './drafts'

const props = defineProps<{ project: Project; session: Conversation }>()
defineEmits<{ rename: []; remove: [] }>()
const client = useQueryClient()
const content = useDraft(props.project.id, props.session.id, 'note')
const intent = ref<{ goal: string; document_ids: string[] }>()
const error = ref('')
const key = ['messages', props.project.id, props.session.id]
const messages = useQuery({
  queryKey: key,
  queryFn: () =>
    request<Note[]>({
      action: 'messages',
      projectId: props.project.id,
      sessionId: props.session.id,
    }),
})
const save = useMutation({
  mutationFn: (text: string) =>
    request<Note>({
      action: 'addMessage',
      projectId: props.project.id,
      sessionId: props.session.id,
      content: text,
    }),
  onMutate: () => {
    error.value = ''
  },
  onError: (cause) => {
    error.value = readableError(cause)
  },
  onSuccess: async () => {
    content.value = ''
    await client.invalidateQueries({ queryKey: key })
  },
})
</script>

<template>
  <section class="session-workspace">
    <div class="section-heading">
      <div>
        <div class="eyebrow">{{ project.name }}</div>
        <h1>{{ session.name }}</h1>
      </div>
      <div class="toolbar">
        <button @click="$emit('rename')">重命名会话</button>
        <button class="danger" @click="$emit('remove')">删除会话</button>
      </div>
    </div>
    <QuestionPanel :project-id="project.id" :session-id="session.id" @design="intent = $event" />
    <ExtractionPanel :project-id="project.id" :session-id="session.id" :intent="intent" />
    <h2>独立阅读笔记</h2>
    <p v-if="messages.isPending.value">正在加载会话…</p>
    <p v-if="messages.isError.value" role="alert" class="error-box">
      会话加载失败。
      <button @click="messages.refetch()">重试</button>
    </p>
    <div class="notes">
      <div v-if="messages.data.value?.length === 0" class="empty-state">
        <strong>一个新的阅读会话</strong>
        <p>记录研究问题、阅读目标或待核对事项。</p>
      </div>
      <article v-for="note in messages.data.value ?? []" :key="note.id" class="note">
        <div class="note-meta">阅读笔记 · {{ new Date(note.created_at).toLocaleString() }}</div>
        <p>{{ note.content }}</p>
      </article>
    </div>
    <form class="note-form" @submit.prevent="save.mutate(content)">
      <label for="note-content">会话笔记</label>
      <textarea
        id="note-content"
        v-model="content"
        placeholder="写下这个会话要关注的问题…"
        maxlength="20000"
        :disabled="save.isPending.value"
        rows="4"
      ></textarea>
      <p v-if="error" role="alert" class="error-box">{{ error }}</p>
      <button
        class="primary"
        :disabled="!content.trim() || save.isPending.value || messages.isError.value"
      >
        {{ save.isPending.value ? '正在保存…' : '保存笔记' }}
      </button>
    </form>
  </section>
</template>
