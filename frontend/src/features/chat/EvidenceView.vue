<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import type { Evidence, ParsedContent } from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import PdfReader from '../../components/pdf/PdfReader.vue'
const props = defineProps<{ projectId: string; evidence: Evidence }>()
defineEmits<{ close: [] }>()
const verified = useQuery({
  queryKey: computed(() => [
    'evidence-source',
    props.projectId,
    props.evidence.asset_id,
    props.evidence.source_sha256,
  ]),
  queryFn: async () => {
    const content = await request<ParsedContent>({
      action: 'parsedContent',
      projectId: props.projectId,
      assetId: props.evidence.asset_id,
    })
    if (content.source_sha256 !== props.evidence.source_sha256)
      throw new Error('原文已经变化，此历史引用不能定位到当前文件，请重新提问。')
    return true
  },
  staleTime: 0,
  gcTime: 0,
})
const pdf = useQuery({
  queryKey: computed(() => [
    'evidence-pdf',
    props.projectId,
    props.evidence.asset_id,
    props.evidence.source_sha256,
  ]),
  enabled: computed(
    () => !!verified.data.value && props.evidence.filename.toLowerCase().endsWith('.pdf'),
  ),
  queryFn: () =>
    request<Uint8Array>({
      action: 'pdfBytes',
      projectId: props.projectId,
      assetId: props.evidence.asset_id,
    }),
  gcTime: 0,
})
</script>
<template>
  <section class="evidence-detail">
    <div class="section-heading">
      <h2>原文证据 · {{ evidence.filename }}</h2>
      <button @click="$emit('close')">关闭证据</button>
    </div>
    <blockquote>{{ evidence.quote }}</blockquote>
    <p v-if="verified.isError.value" role="alert" class="error-box">
      {{ readableError(verified.error.value) }}
    </p>
    <p v-if="pdf.isError.value" role="alert" class="error-box">
      {{ readableError(pdf.error.value) }}
    </p>
    <PdfReader
      v-if="verified.data.value && pdf.data.value"
      :key="evidence.id"
      :data="pdf.data.value"
      :location="evidence.locations[0]"
      :quote="evidence.quote"
    />
    <p v-else-if="verified.data.value && !evidence.locations.length">
      此附件无可靠 PDF 页码，以上为对应内容块的原文。
    </p>
  </section>
</template>
