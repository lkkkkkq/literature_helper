<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth } from '../api/health'
import type { HealthStatus } from '../../../desktop/src/shared/contracts'
const health = ref<HealthStatus | null>(null)
const error = ref('')
const loading = ref(false)
async function refresh() {
  loading.value = true
  error.value = ''
  health.value = null
  try {
    health.value = await getHealth()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '连接失败，请重试。'
  } finally {
    loading.value = false
  }
}
onMounted(refresh)
</script>
<template>
  <section class="status-card" aria-live="polite">
    <div>
      <div class="card-label">运行状态</div>
      <h2 data-testid="connection-state">
        {{ loading ? '正在检查本地服务…' : error ? '本地服务连接失败' : '工作台已就绪' }}
      </h2>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-else-if="health">
        SQLite · {{ health.database.toUpperCase() }} · {{ health.migration }}
      </p>
    </div>
    <button :disabled="loading" @click="refresh">{{ loading ? '检查中…' : '重新检查' }}</button>
  </section>
</template>
