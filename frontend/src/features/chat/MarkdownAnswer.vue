<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
const props = defineProps<{ text: string }>()
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true })
const html = computed(() =>
  DOMPurify.sanitize(markdown.render(props.text), {
    FORBID_TAGS: ['img', 'a', 'iframe', 'form', 'input', 'style'],
  }),
)
</script>
<template>
  <!-- Raw HTML is disabled and the rendered Markdown is sanitized by DOMPurify. -->
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="markdown-answer" v-html="html"></div>
</template>
