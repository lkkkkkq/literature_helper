<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import type { DomainPlugin } from '../../../../desktop/src/shared/contracts'
import { request, readableError } from '../../api/workspace'
const props = defineProps<{ projectId: string }>()
defineEmits<{ template: [pluginId: string] }>()
const error = ref('')
const busy = ref(false)
const plugins = useQuery({
  queryKey: ['plugins', props.projectId],
  queryFn: () => request<DomainPlugin[]>({ action: 'plugins', projectId: props.projectId }),
})
async function toggle(plugin: DomainPlugin) {
  busy.value = true
  error.value = ''
  try {
    await request({
      action: 'togglePlugin',
      projectId: props.projectId,
      pluginId: plugin.id,
      enabled: !plugin.enabled,
    })
    await plugins.refetch()
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <details class="plugin-panel">
    <summary>领域插件 · 按项目配置</summary>
    <p>通用提取无需插件。插件版本随方案保存，开关只影响新方案，历史任务保持原版本。</p>
    <p v-if="error || plugins.isError.value" role="alert" class="error-box">
      {{ error || readableError(plugins.error.value) }}
    </p>
    <article v-for="plugin in plugins.data.value ?? []" :key="plugin.id">
      <h4>{{ plugin.name }} v{{ plugin.version }} · {{ plugin.enabled ? '已启用' : '未启用' }}</h4>
      <p>{{ plugin.description }}</p>
      <button :disabled="busy" @click="toggle(plugin)">
        {{ plugin.enabled ? '禁用' : '启用' }}{{ plugin.name }}插件
      </button>
      <template v-if="plugin.enabled">
        <p v-if="plugin.configured_version !== plugin.version" class="error-box">
          已配置版本与安装版本不同，请重新启用后创建新方案；历史任务需要其原版本。
        </p>
        <button @click="$emit('template', plugin.id)">加载{{ plugin.name }}模板</button>
        <ul>
          <li v-for="rule in plugin.context.rules" :key="rule">{{ rule }}</li>
        </ul>
        <details>
          <summary>领域术语</summary>
          <pre>{{ JSON.stringify(plugin.context.synonyms, null, 2) }}</pre>
        </details>
      </template>
    </article>
  </details>
</template>
