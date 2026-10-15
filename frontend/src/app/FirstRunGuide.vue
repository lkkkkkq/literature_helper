<script setup lang="ts">
import { ref } from 'vue'
defineEmits<{ start: [] }>()
const step = ref(0)
const steps = [
  {
    title: '1. 选择文献文件夹',
    text: '把主论文和补充材料放在同一子文件夹。导入后先检查附件归属；应用只读引用原文件。',
  },
  {
    title: '2. 解析并查看原文',
    text: '打开文献并解析 PDF、扫描件、CSV、Excel 或 Word。PDF 支持页码与证据高亮；本地解析不需要模型密钥。',
  },
  {
    title: '3. 配置 DeepSeek 并确认方案',
    text: '在会话的“模型设置”中保存你的 API Key，然后测试连接。提问会发送相关原文到所选服务；结构化提取必须先检查并确认方案。',
  },
  {
    title: '4. 复核后导出',
    text: '点击结果表格中的字段查看证据。修订会保留原值和历史版本；导出 Excel 包含主数据、证据和元数据。',
  },
]
</script>
<template>
  <section class="first-run-guide" aria-label="首次使用向导">
    <h2>开始使用 · {{ step + 1 }} / 4</h2>
    <h3>{{ steps[step]!.title }}</h3>
    <p>{{ steps[step]!.text }}</p>
    <div class="toolbar">
      <button :disabled="step === 0" @click="step--">上一步</button>
      <button v-if="step < 3" @click="step++">下一步</button>
      <button v-else class="primary" @click="$emit('start')">创建第一个项目</button>
    </div>
  </section>
</template>
