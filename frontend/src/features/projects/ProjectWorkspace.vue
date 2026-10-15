<script setup lang="ts">
import { ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type {
  ConfirmGroup,
  Document,
  Project,
  ScanDraft,
} from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import DocumentList from './DocumentList.vue'
import ScanReview from './ScanReview.vue'
import DocumentReader from '../reading/DocumentReader.vue'

const props = defineProps<{ project: Project }>()
defineEmits<{ rename: []; remove: [] }>()
const client = useQueryClient()
const error = ref('')
const reading = ref<Document | null>(null)
const documents = useQuery({
  queryKey: ['documents', props.project.id],
  queryFn: () => request<Document[]>({ action: 'documents', projectId: props.project.id }),
})
const draft = useQuery({
  queryKey: ['draft', props.project.id],
  queryFn: () => request<ScanDraft | null>({ action: 'draft', projectId: props.project.id }),
})
function retryLoad() {
  void documents.refetch()
  void draft.refetch()
}
const scan = useMutation({
  mutationFn: () => request<ScanDraft>({ action: 'scan', projectId: props.project.id }),
  onMutate: () => {
    error.value = ''
  },
  onError: (cause) => {
    error.value = readableError(cause)
  },
  onSuccess: (value) => {
    client.setQueryData(['draft', props.project.id], value)
  },
})
const confirm = useMutation({
  mutationFn: (groups: ConfirmGroup[]) =>
    request<Document[]>({
      action: 'confirmScan',
      projectId: props.project.id,
      draft_id: draft.data.value!.id,
      groups,
    }),
  onMutate: () => {
    error.value = ''
  },
  onError: (cause) => {
    error.value = readableError(cause)
  },
  onSuccess: async (value) => {
    client.setQueryData(['documents', props.project.id], value)
    client.setQueryData(['draft', props.project.id], null)
    await client.invalidateQueries({ queryKey: ['projects'] })
  },
})
</script>

<template>
  <DocumentReader
    v-if="reading"
    :key="reading.id"
    :project-id="project.id"
    :document="reading"
    @close="reading = null"
  />
  <div v-else class="project-workspace">
    <section class="project-heading">
      <div class="eyebrow">LITERATURE PROJECT</div>
      <h1>{{ project.name }}</h1>
      <p class="file-path">{{ project.source_path }}</p>
      <div class="toolbar">
        <button
          class="primary"
          :disabled="scan.isPending.value || confirm.isPending.value"
          @click="scan.mutate()"
        >
          {{
            scan.isPending.value
              ? '扫描中，正在计算文件指纹…'
              : project.scanned_at
                ? '重新扫描'
                : '扫描文件夹'
          }}
        </button>
        <button @click="$emit('rename')">重命名项目</button>
        <button class="danger" @click="$emit('remove')">移除项目</button>
      </div>
    </section>
    <p v-if="error" role="alert" class="error-box">{{ error }}</p>
    <p v-if="documents.isError.value || draft.isError.value" role="alert" class="error-box">
      项目内容加载失败。
      <button @click="retryLoad">重试</button>
    </p>
    <p v-if="documents.isPending.value || draft.isPending.value">正在加载项目…</p>
    <ScanReview
      v-if="draft.data.value"
      :key="draft.data.value.id"
      :draft="draft.data.value"
      :busy="scan.isPending.value || confirm.isPending.value"
      @confirm="confirm.mutate"
    />
    <DocumentList
      v-if="documents.data.value"
      :documents="documents.data.value"
      @read="reading = $event"
    />
  </div>
</template>
