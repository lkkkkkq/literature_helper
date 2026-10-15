<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { ModelProfile } from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
const props = defineProps<{ projectId: string }>()
const base = ref('https://api.deepseek.com')
const model = ref('deepseek-flash')
const key = ref('')
const hasKey = ref(false)
const busy = ref(false)
const status = ref('')
onMounted(async () => {
  try {
    const profile = await request<ModelProfile | null>({
      action: 'modelProfile',
      projectId: props.projectId,
    })
    if (profile) {
      base.value = profile.base_url
      model.value = profile.model
      hasKey.value = profile.hasKey
    }
  } catch (error) {
    status.value = readableError(error)
  }
})
async function save() {
  busy.value = true
  status.value = ''
  try {
    const profile = await request<ModelProfile>({
      action: 'saveModel',
      projectId: props.projectId,
      base_url: base.value,
      model: model.value,
      apiKey: key.value,
    })
    hasKey.value = profile.hasKey
    status.value = '配置已保存'
  } catch (error) {
    status.value = readableError(error)
  } finally {
    key.value = ''
    busy.value = false
  }
}
async function testConnection() {
  busy.value = true
  try {
    await request({ action: 'testModel', projectId: props.projectId })
    status.value = '模型连接成功'
  } catch (error) {
    status.value = readableError(error)
  } finally {
    busy.value = false
  }
}
async function remove() {
  try {
    await request({ action: 'deleteModelKey', projectId: props.projectId })
    hasKey.value = false
    status.value = '已删除此项目的密钥'
  } catch (error) {
    status.value = readableError(error)
  }
}
</script>
<template>
  <details class="model-settings">
    <summary>模型设置 · {{ hasKey ? '已保存密钥' : '尚未配置密钥' }}</summary>
    <p>提问时，会将所选文献的原文片段及当前会话近期历史发送到此接口。解析和本地阅读无需密钥。</p>
    <form @submit.prevent="save">
      <label>
        接口地址
        <input v-model="base" required :disabled="busy" />
      </label>
      <label>
        模型名称
        <input v-model="model" required :disabled="busy" />
      </label>
      <label>
        API Key
        <input
          v-model="key"
          type="password"
          autocomplete="off"
          :disabled="busy"
          placeholder="留空保留原密钥；更换接口后请重新填写"
        />
      </label>
      <p>密钥使用系统加密保存，仅用于此项目，不显示已保存的密钥。</p>
      <div class="toolbar">
        <button class="primary" :disabled="busy">保存模型配置</button>
        <button type="button" :disabled="busy || !hasKey" @click="testConnection">测试连接</button>
        <button type="button" :disabled="busy || !hasKey" @click="remove">删除密钥</button>
      </div>
    </form>
    <p v-if="status" role="status">{{ status }}</p>
  </details>
</template>
