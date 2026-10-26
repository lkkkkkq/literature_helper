<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type {
  Document,
  ExtractionPlan,
  Job,
  JobDetail,
  PlanVersion,
} from '../../../../desktop/src/shared/contracts'
import { readableError, request } from '../../api/workspace'
import ResultsPanel from './ResultsPanel.vue'
import PluginPanel from './PluginPanel.vue'
import { useDraft } from '../chat/drafts'
const props = defineProps<{
  projectId: string
  sessionId: string
  intent?: { goal: string; document_ids: string[] }
}>()
const client = useQueryClient()
const goal = useDraft(props.projectId, props.sessionId, 'goal')
const fulltextBatch = ref<number>()
const selectedDocument = useDraft(props.projectId, props.sessionId, 'goal-scope')
const error = ref('')
const busy = ref(false)
const selectedPlan = ref('')
const plan = ref<ExtractionPlan>()
const activeJob = ref('')
const detail = ref<JobDetail>()
const plansKey = ['plans', props.projectId, props.sessionId]
const jobsKey = ['jobs', props.projectId, props.sessionId]
const plans = useQuery({
  queryKey: plansKey,
  queryFn: () =>
    request<PlanVersion[]>({
      action: 'plans',
      projectId: props.projectId,
      sessionId: props.sessionId,
    }),
})
const jobs = useQuery({
  queryKey: jobsKey,
  queryFn: () =>
    request<Job[]>({ action: 'jobs', projectId: props.projectId, sessionId: props.sessionId }),
})
const documents = useQuery({
  queryKey: ['documents', props.projectId],
  queryFn: () => request<Document[]>({ action: 'documents', projectId: props.projectId }),
})
const sourcePlan = computed(() => plans.data.value?.find((item) => item.id === selectedPlan.value))
const running = computed(() => ['pending', 'running'].includes(detail.value?.status ?? ''))
const completed = computed(
  () => detail.value?.documents.filter((doc) => doc.status === 'complete').length ?? 0,
)
let unsubscribe: (() => void) | undefined
function status(value: string) {
  return (
    (
      {
        pending: '等待执行',
        running: '正在处理',
        completed: '全部完成',
        complete: '完成',
        partial: '部分完成',
        failed: '失败',
        cancelled: '已取消',
        interrupted: '已中断',
      } as Record<string, string>
    )[value] ?? value
  )
}
function documentTitle(id: string) {
  return documents.data.value?.find((item) => item.id === id)?.title ?? '文献已移除'
}
function edit(id: string) {
  selectedPlan.value = id
  const found = plans.data.value?.find((item) => item.id === id)
  if (found) plan.value = JSON.parse(JSON.stringify(found.plan)) as ExtractionPlan
}
async function generate(ids?: string[]) {
  busy.value = true
  error.value = ''
  try {
    const draft = await request<PlanVersion>({
      action: 'design',
      projectId: props.projectId,
      sessionId: props.sessionId,
      goal: goal.value,
      fulltext_batch: typeof fulltextBatch.value === 'number' ? fulltextBatch.value : undefined,
      document_ids: ids ?? (selectedDocument.value ? [selectedDocument.value] : []),
    })
    await client.invalidateQueries({ queryKey: plansKey })
    edit(draft.id)
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
async function confirm() {
  if (!plan.value) return
  busy.value = true
  error.value = ''
  try {
    const job = await request<Job>({
      action: 'confirmPlan',
      projectId: props.projectId,
      sessionId: props.sessionId,
      schema_id: selectedPlan.value,
      request_id: crypto.randomUUID(),
      plan: plan.value,
    })
    activeJob.value = job.id
    await client.invalidateQueries({ queryKey: plansKey })
    await client.invalidateQueries({ queryKey: jobsKey })
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
async function loadTemplate(pluginId: string) {
  busy.value = true
  error.value = ''
  try {
    const draft = await request<PlanVersion>({
      action: 'template',
      projectId: props.projectId,
      sessionId: props.sessionId,
      plugin_id: pluginId,
    })
    await client.invalidateQueries({ queryKey: plansKey })
    edit(draft.id)
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
async function subscribe(id: string) {
  unsubscribe?.()
  detail.value = undefined
  if (!id) return
  try {
    const snapshot = await request<JobDetail>({
      action: 'job',
      projectId: props.projectId,
      jobId: id,
    })
    if (activeJob.value !== id) return
    detail.value = snapshot
    unsubscribe = window.litextract?.watchJob?.(props.projectId, id, (value) => {
      if (activeJob.value !== id) return
      if ('documents' in value) {
        detail.value = value
        if (!['pending', 'running'].includes(value.status))
          void client.invalidateQueries({ queryKey: jobsKey })
      } else error.value = value.error
    })
  } catch (cause) {
    error.value = readableError(cause)
  }
}
async function control(action: 'cancelJob' | 'resumeJob') {
  busy.value = true
  try {
    await request({ action, projectId: props.projectId, jobId: activeJob.value })
    await subscribe(activeJob.value)
    await client.invalidateQueries({ queryKey: jobsKey })
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
function addField() {
  plan.value?.fields.push({
    key: `field_${plan.value.fields.length + 1}`,
    label: '新字段',
    description: '',
    type: 'string',
    unit: '',
  })
}
function removeField(index: number) {
  if (!plan.value) return
  const removed = plan.value.fields.splice(index, 1)[0]
  plan.value.record_key = plan.value.record_key.filter((key) => key !== removed?.key)
}
watch(activeJob, (value) => {
  void subscribe(value)
})
watch(
  () => props.intent,
  (value) => {
    if (value) {
      goal.value = value.goal
      void generate(value.document_ids)
    }
  },
)
onBeforeUnmount(() => unsubscribe?.())
</script>
<template>
  <section class="extraction-workspace">
    <h2>整理与提取</h2>
    <PluginPanel :project-id="projectId" @template="loadTemplate" />
    <p>先描述目标并检查方案。只有点击确认后才会启动提取，普通文献提问不会创建任务。</p>
    <form @submit.prevent="generate()">
      <label>
        提取范围
        <select v-model="selectedDocument" :disabled="busy">
          <option value="">当前项目全部有效文献</option>
          <option v-for="doc in documents.data.value ?? []" :key="doc.id" :value="doc.id">
            {{ doc.title }}
          </option>
        </select>
      </label>
      <label>
        整理目标
        <textarea
          v-model="goal"
          rows="3"
          maxlength="10000"
          :disabled="busy"
          placeholder="例如：按采样站点整理浓度、单位和采样时间，每个站点一行"
        />
      </label>
      <details>
        <summary>超长全文：指定方案参考批次</summary>
        <label>
          参考第几批
          <input v-model.number="fulltextBatch" type="number" min="1" />
        </label>
        <p>仅在提示超出预算后填写。方案参考所选批次，执行提取仍按全部来源分批。</p>
      </details>
      <button :disabled="busy || !goal.trim()">{{ busy ? '正在处理…' : '生成提取方案' }}</button>
    </form>
    <p v-if="error" role="alert" class="error-box">{{ error }}</p>
    <label v-if="plans.data.value?.length">
      历史方案
      <select :value="selectedPlan" @change="edit(($event.target as HTMLSelectElement).value)">
        <option value="">选择方案版本</option>
        <option v-for="item in plans.data.value" :key="item.id" :value="item.id">
          v{{ item.version }} · {{ item.plan.name }} ·
          {{ item.status === 'confirmed' ? '已确认' : '待确认' }}
        </option>
      </select>
    </label>
    <section v-if="plan" class="plan-editor">
      <h3>确认提取方案</h3>
      <p v-if="plan.plugins?.length">
        领域规则：{{ plan.plugins.map((item) => `${item.id} v${item.version}`).join('、') }}
      </p>
      <p>范围：{{ sourcePlan?.document_ids.length }} 篇文献；修改后确认将保存为新版本。</p>
      <label>
        任务名称
        <input v-model="plan.name" :disabled="busy" />
      </label>
      <label>
        一行数据代表什么
        <textarea v-model="plan.granularity" :disabled="busy" rows="2" />
      </label>
      <div v-for="(field, index) in plan.fields" :key="index" class="plan-field">
        <label>
          字段名称
          <input v-model="field.label" :disabled="busy" />
        </label>
        <label>
          类型
          <select v-model="field.type" :disabled="busy">
            <option value="string">文本</option>
            <option value="number">数值</option>
            <option value="boolean">是/否</option>
          </select>
        </label>
        <label>
          单位
          <input v-model="field.unit" :disabled="busy" />
        </label>
        <label>
          字段说明
          <input v-model="field.description" :disabled="busy" />
        </label>
        <label class="inline-check">
          <input v-model="plan.record_key" type="checkbox" :value="field.key" :disabled="busy" />
          用于区分记录
        </label>
        <button :disabled="busy || plan.fields.length <= 1" @click="removeField(index)">
          移除此字段
        </button>
      </div>
      <button :disabled="busy || plan.fields.length >= 50" @click="addField">添加字段</button>
      <p>缺失值留空并说明原因；非空字段必须有原文证据；冲突保留分行并标记复核。</p>
      <button class="primary" :disabled="busy || !plan.record_key.length" @click="confirm">
        确认方案并开始提取
      </button>
    </section>
    <h3>当前会话的任务</h3>
    <p v-if="jobs.isError.value" class="error-box">{{ readableError(jobs.error.value) }}</p>
    <button
      v-for="job in jobs.data.value ?? []"
      :key="job.id"
      class="job-item"
      @click="activeJob = job.id"
    >
      {{ status(job.status) }} · {{ job.id.slice(0, 8) }}
    </button>
    <section v-if="detail" class="job-detail">
      <h3>{{ detail.schema.plan.name }} · {{ status(detail.status) }}</h3>
      <p>
        已完成 {{ completed }} / {{ detail.documents.length }} 篇文献，生成
        {{ detail.record_count }} 条记录。
      </p>
      <progress
        :value="
          detail.documents.filter((doc) => !['pending', 'running'].includes(doc.status)).length
        "
        :max="detail.documents.length"
      />
      <div class="toolbar">
        <button v-if="running" :disabled="busy" @click="control('cancelJob')">取消任务</button>
        <button
          v-else-if="detail.status !== 'completed'"
          :disabled="busy"
          @click="control('resumeJob')"
        >
          重试未完成文献
        </button>
        <button @click="subscribe(activeJob)">刷新任务</button>
      </div>
      <ul>
        <li v-for="doc in detail.documents" :key="doc.document_id">
          {{ documentTitle(doc.document_id) }}：{{ status(doc.status) }}
          <p v-if="doc.error" class="error-box">{{ doc.error }}</p>
          <p v-for="warning in doc.warnings" :key="warning">{{ warning }}</p>
        </li>
      </ul>
      <ResultsPanel :key="detail.id" :project-id="projectId" :job="detail" />
    </section>
  </section>
</template>
