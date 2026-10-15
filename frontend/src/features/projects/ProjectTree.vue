<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { request } from '../../api/workspace'
import type { Conversation, Project } from '../../../../desktop/src/shared/contracts'

const props = defineProps<{ project: Project; activeProject: string; activeSession: string }>()
const emit = defineEmits<{
  select: [project: string, session: string]
  createSession: [project: Project]
}>()
const expanded = ref(true)
const sessions = useQuery({
  queryKey: ['sessions', props.project.id],
  queryFn: () => request<Conversation[]>({ action: 'sessions', projectId: props.project.id }),
})
</script>

<template>
  <div class="project-tree">
    <div class="project-row" :class="{ selected: activeProject === project.id && !activeSession }">
      <button
        class="icon-button"
        :aria-label="`${expanded ? '折叠' : '展开'} ${project.name}`"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '▾' : '▸' }}
      </button>
      <button
        class="project-name"
        :title="project.source_path"
        @click="emit('select', project.id, '')"
      >
        {{ project.name }}
      </button>
    </div>
    <div v-if="expanded" class="session-tree">
      <button
        v-for="session in sessions.data.value ?? []"
        :key="session.id"
        class="session-link"
        :class="{ selected: activeSession === session.id }"
        @click="emit('select', project.id, session.id)"
      >
        <span>◌</span>
        {{ session.name }}
      </button>
      <p v-if="sessions.isError.value" class="small-error">
        会话加载失败
        <button @click="sessions.refetch()">重试</button>
      </p>
      <button class="new-session" @click="emit('createSession', project)">＋ 新建会话</button>
    </div>
  </div>
</template>
