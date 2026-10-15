<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useVueTable,
} from '@tanstack/vue-table'
import type {
  Evidence,
  JobDetail,
  ResultRecord,
  ResultSnapshot,
} from '../../../../desktop/src/shared/contracts'
import { request, readableError } from '../../api/workspace'
import EvidenceView from '../chat/EvidenceView.vue'
const props = defineProps<{ projectId: string; job: JobDetail }>()
const version = ref('latest')
const filter = ref('')
const error = ref('')
const notice = ref('')
const busy = ref(false)
const evidence = ref<Evidence>()
const selected = ref<{ row: ResultRecord; key: string }>()
const edited = ref('')
const unit = ref('')
const missing = ref(false)
const reason = ref('')
const missingReason = ref('')
const evidenceIds = ref<string[]>([])
const results = useQuery({
  queryKey: computed(() => [
    'results',
    props.projectId,
    props.job.id,
    props.job.status,
    props.job.record_count,
    version.value,
  ]),
  queryFn: () =>
    request<ResultSnapshot>({
      action: 'results',
      projectId: props.projectId,
      jobId: props.job.id,
      version: version.value,
    }),
})
const columns = computed(() => [
  ...props.job.schema.plan.fields.map((field) => ({
    id: field.key,
    header: field.label,
    accessorFn: (row: ResultRecord) => row.values_json[field.key]?.value ?? '缺失',
  })),
  { id: 'risks', header: '风险提示', accessorFn: (row: ResultRecord) => row.risks.join('；') },
])
const rows = computed(() => results.data.value?.records ?? [])
const table = useVueTable({
  get data() {
    return rows.value
  },
  get columns() {
    return columns.value
  },
  state: {
    get globalFilter() {
      return filter.value
    },
  },
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  initialState: { pagination: { pageSize: 20 } },
})
function inspect(row: ResultRecord, key: string) {
  selected.value = { row, key }
  const field = row.values_json[key]!
  edited.value = String(field.value ?? '')
  unit.value = field.unit
  missing.value = field.value === null
  missingReason.value = field.missing_reason
  evidenceIds.value = [...field.evidence_ids]
  reason.value = ''
}
async function save() {
  if (!selected.value || !results.data.value) return
  busy.value = true
  error.value = ''
  try {
    const field = props.job.schema.plan.fields.find((item) => item.key === selected.value!.key)!
    if (
      !missing.value &&
      field.type === 'number' &&
      (!edited.value.trim() || !Number.isFinite(Number(edited.value)))
    )
      throw new Error('请输入有效数值')
    if (!missing.value && field.type === 'boolean' && !['true', 'false'].includes(edited.value))
      throw new Error('是/否字段请填写 true 或 false')
    const value = missing.value
      ? null
      : field.type === 'number'
        ? Number(edited.value)
        : field.type === 'boolean'
          ? edited.value === 'true'
          : edited.value
    await request({
      action: 'review',
      projectId: props.projectId,
      jobId: props.job.id,
      base_version: results.data.value.latest_version,
      record_id: selected.value.row.id,
      field_key: selected.value.key,
      after: {
        value,
        unit: unit.value,
        missing_reason: missing.value ? missingReason.value : '',
        evidence_ids: evidenceIds.value,
      },
      reason: reason.value,
    })
    selected.value = undefined
    await results.refetch()
    notice.value = '修订已保存为新版本，自动提取原值仍然保留。'
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
async function exportFile(format: 'csv' | 'xlsx') {
  error.value = ''
  busy.value = true
  try {
    const response = await request<{ cancelled: boolean; path?: string }>({
      action: 'exportResults',
      projectId: props.projectId,
      jobId: props.job.id,
      version: version.value,
      format,
    })
    if (!response.cancelled) notice.value = `已导出：${response.path}`
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <section class="results-panel">
    <h3>提取结果与复核</h3>
    <div class="toolbar">
      <label>
        结果版本
        <select v-model="version" aria-label="结果版本" @change="selected = undefined">
          <option value="latest">最新修订</option>
          <option value="automatic">自动提取原值</option>
          <option
            v-for="item in results.data.value?.history ?? []"
            :key="item.id"
            :value="String(item.version)"
          >
            修订 v{{ item.version }}
          </option>
        </select>
      </label>
      <label>
        筛选记录
        <input v-model="filter" placeholder="输入站点、数值或风险" />
      </label>
      <button :disabled="busy || !results.data.value?.records.length" @click="exportFile('csv')">
        导出 CSV
      </button>
      <button :disabled="busy || !results.data.value?.records.length" @click="exportFile('xlsx')">
        导出 Excel
      </button>
    </div>
    <p v-if="error || results.isError.value" role="alert" class="error-box">
      {{ error || readableError(results.error.value) }}
    </p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p>
      点击字段值查看证据并复核。当前版本：{{
        results.data.value?.version ?? 0
      }}；自动提取的风险标记始终保留。
    </p>
    <div class="result-table-scroll">
      <table class="result-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.id">{{ column.header }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in table.getRowModel().rows" :key="row.id">
            <td v-for="cell in row.getVisibleCells()" :key="cell.id">
              <span v-if="cell.column.id === 'risks'">{{ cell.getValue() || '—' }}</span>
              <button v-else @click="inspect(row.original, cell.column.id)">
                {{ cell.getValue() }} {{ row.original.values_json[cell.column.id]?.unit }}
                <small v-if="row.original.values_json[cell.column.id]?.standardized">
                  归一化建议：{{ row.original.values_json[cell.column.id]?.standardized?.value }}
                  {{ row.original.values_json[cell.column.id]?.standardized?.unit }}
                </small>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="toolbar">
      <button :disabled="!table.getCanPreviousPage()" @click="table.previousPage()">上一页</button>
      <span>
        {{ table.getState().pagination.pageIndex + 1 }} / {{ Math.max(1, table.getPageCount()) }}
      </span>
      <button :disabled="!table.getCanNextPage()" @click="table.nextPage()">下一页</button>
    </div>
    <section v-if="selected" class="field-review">
      <h4>
        字段复核 · {{ job.schema.plan.fields.find((item) => item.key === selected?.key)?.label }}
      </h4>
      <p>原始证据：</p>
      <p v-if="!selected.row.evidence_json.length">
        无原文证据，不能将缺失字段改成无证据的非空值。
      </p>
      <div v-for="item in selected.row.evidence_json" :key="item.id" class="review-evidence">
        <label class="inline-check">
          <input v-model="evidenceIds" type="checkbox" :value="item.id" />
          {{ item.filename }}
        </label>
        <blockquote>{{ item.quote }}</blockquote>
        <button @click="evidence = item">打开原文</button>
      </div>
      <form @submit.prevent="save">
        <label class="inline-check">
          <input v-model="missing" type="checkbox" />
          标记为缺失
        </label>
        <label v-if="!missing">
          修订值
          <input v-model="edited" />
        </label>
        <label v-else>
          缺失原因
          <input v-model="missingReason" required />
        </label>
        <label>
          修订单位
          <input v-model="unit" />
        </label>
        <label>
          修订原因
          <textarea v-model="reason" required maxlength="2000" />
        </label>
        <p v-if="version !== 'latest'">历史版本仅供查看，请切换“最新修订”后修改。</p>
        <button
          :disabled="busy || version !== 'latest' || ['pending', 'running'].includes(job.status)"
        >
          保存为新修订
        </button>
        <button type="button" @click="selected = undefined">关闭复核</button>
      </form>
    </section>
    <details v-if="results.data.value?.history.length">
      <summary>修订历史</summary>
      <p v-for="item in results.data.value.history" :key="item.id">
        v{{ item.version }} · {{ item.field_key }}：{{ item.before.value }} →
        {{ item.after.value }}；{{ item.reason }} · {{ item.created_at }}
      </p>
    </details>
    <EvidenceView
      v-if="evidence"
      :key="evidence.id"
      :project-id="projectId"
      :evidence="evidence"
      @close="evidence = undefined"
    />
  </section>
</template>
