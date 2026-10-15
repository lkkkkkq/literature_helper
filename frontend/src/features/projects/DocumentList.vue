<script setup lang="ts">
import type { Document } from '../../../../desktop/src/shared/contracts'
defineProps<{ documents: Document[] }>()
defineEmits<{ read: [document: Document] }>()
function size(bytes: number) {
  return bytes < 1024
    ? `${bytes} B`
    : bytes < 1048576
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / 1048576).toFixed(1)} MB`
}
function status(value: string) {
  return (
    ({ active: '已索引', changed: '文件已变化', missing: '源文件缺失' } as Record<string, string>)[
      value
    ] ?? value
  )
}
</script>

<template>
  <div class="document-list">
    <div class="section-heading">
      <h2>文献与附件</h2>
      <span class="muted">
        {{ documents.filter((doc) => doc.status === 'active').length }} 组有效文献
      </span>
    </div>
    <div v-if="!documents.length" class="empty-state">
      <strong>还没有导入文献</strong>
      <p>点击“扫描文件夹”，检查分组后确认导入。源文件始终留在原位置。</p>
    </div>
    <details v-for="document in documents" :key="document.id" class="document-card">
      <summary>
        <span>▤ {{ document.title }}</span>
        <span class="badge" :class="{ amber: document.status === 'missing' }">
          {{ document.status === 'missing' ? '已失效' : `${document.assets.length} 个文件` }}
        </span>
      </summary>
      <p v-if="document.status === 'missing'" class="warning">
        原文件已缺失或重新分组，保留此文献标识供追溯。
      </p>
      <button
        class="primary open-reader"
        :disabled="document.status === 'missing'"
        @click="$emit('read', document)"
      >
        阅读正文与附件
      </button>
      <div v-for="asset in document.assets" :key="asset.id" class="asset-row">
        <div>
          <strong>{{ asset.relative_path }}</strong>
          <span class="badge">{{ asset.role === 'main' ? '主论文' : '附件' }}</span>
          <span class="asset-state" :class="{ warning: asset.status !== 'active' }">
            {{ status(asset.status) }}
          </span>
        </div>
        <p>
          {{ size(asset.size) }} · {{ asset.kind.toUpperCase() }} ·
          {{ new Date(asset.mtime_ns / 1000000).toLocaleString() }}
        </p>
        <div class="file-path">{{ asset.absolute_path }}</div>
        <div class="fingerprint">SHA-256 {{ asset.sha256 }}</div>
      </div>
    </details>
    <p class="milestone-note">展开文献后可阅读正文与附件。源文件变化时，请先重新扫描。</p>
  </div>
</template>
