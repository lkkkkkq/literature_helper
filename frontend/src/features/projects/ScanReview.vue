<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ConfirmGroup, ScanDraft, ScanGroup } from '../../../../desktop/src/shared/contracts'

const props = defineProps<{ draft: ScanDraft; busy: boolean }>()
const emit = defineEmits<{ confirm: [groups: ConfirmGroup[]] }>()
const groups = ref<ScanGroup[]>(
  props.draft.snapshot.groups.map((group) => ({ ...group, asset_paths: [...group.asset_paths] })),
)
const invalid = computed(() => groups.value.some((group) => !group.title.trim()))
function moveFile(source: ScanGroup, path: string, target: string) {
  if (!target || target === source.key) return
  let group = groups.value.find((candidate) => candidate.key === target)
  if (target === 'new') {
    group = {
      key: crypto.randomUUID(),
      title: path.split('/').pop() ?? path,
      main_path: /\.(pdf|docx)$/i.test(path) ? path : null,
      asset_paths: [],
      confidence: 'review',
      reason: '手动分组',
    }
    groups.value.push(group)
  }
  if (!group) return
  source.asset_paths = source.asset_paths.filter((item) => item !== path)
  if (source.main_path === path) source.main_path = null
  group.asset_paths.push(path)
  groups.value = groups.value.filter((item) => item.asset_paths.length > 0)
}
function confirm() {
  emit(
    'confirm',
    groups.value.map(({ title, main_path, asset_paths }) => ({
      title,
      main_path,
      asset_paths: [...asset_paths],
    })),
  )
}
</script>

<template>
  <section class="scan-review" aria-label="扫描分组预览">
    <div class="section-heading">
      <div>
        <div class="eyebrow">IMPORT REVIEW</div>
        <h2>确认文献与附件分组</h2>
      </div>
      <span class="badge">{{ draft.snapshot.assets.length }} 个文件 / {{ groups.length }} 组</span>
    </div>
    <p>预览已保存。检查主论文和附件归属后再导入；已有索引在确认前保持不变。</p>
    <p v-if="!groups.length" class="warning">
      源目录中没有可导入文件。确认后，已有文件将标为缺失。
    </p>
    <details v-if="draft.snapshot.warnings.length" class="warning">
      <summary>{{ draft.snapshot.warnings.length }} 条扫描提示</summary>
      <ul>
        <li v-for="warning in draft.snapshot.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </details>
    <fieldset :disabled="busy" class="scan-groups">
      <article v-for="group in groups" :key="group.key" class="scan-group">
        <div class="group-meta">
          <span class="badge" :class="{ amber: group.confidence === 'review' }">
            {{ group.confidence === 'review' ? '需要复核' : '自动建议' }}
          </span>
          <span>{{ group.reason }}</span>
        </div>
        <label>
          文献标题
          <input v-model="group.title" maxlength="200" aria-label="文献标题" />
        </label>
        <label>
          主论文
          <select v-model="group.main_path" aria-label="主论文">
            <option :value="null">独立资料（无主论文）</option>
            <option v-for="path in group.asset_paths" :key="path" :value="path">{{ path }}</option>
          </select>
        </label>
        <div v-for="path in group.asset_paths" :key="path" class="scan-file">
          <span :title="path">{{ path }}</span>
          <select
            :value="group.key"
            :aria-label="`文件归属 ${path}`"
            @change="moveFile(group, path, ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="target in groups" :key="target.key" :value="target.key">
              {{ target.title }}
            </option>
            <option value="new">拆为独立资料</option>
          </select>
        </div>
      </article>
    </fieldset>
    <button class="primary" :disabled="busy || invalid" @click="confirm">
      {{ busy ? '正在核验文件并导入…' : '确认分组并更新索引' }}
    </button>
  </section>
</template>
