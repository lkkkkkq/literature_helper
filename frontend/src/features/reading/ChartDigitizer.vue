<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request, readableError } from '../../api/workspace'
const props = defineProps<{
  projectId: string
  assetId: string
  version: string
  resource: string
  imageUrl: string
}>()
defineEmits<{ close: [] }>()
type Point = {
  x: number
  y: number
  category: string
  label_value: number | null
  rgb: [number, number, number] | null
}
const point = (x: number, y: number): Point => ({
  x,
  y,
  category: '',
  label_value: null,
  rgb: null,
})
const specification = ref({
  resource: props.resource,
  panel: '子图 1',
  series: '系列 1',
  kind: 'curve',
  x_unit: '',
  y_unit: '',
  origin: point(0.1, 0.9),
  x_reference: point(0.9, 0.9),
  y_reference: point(0.1, 0.1),
  x_min: 0,
  x_max: 1,
  y_min: 0,
  y_max: 1,
  x_log: false,
  y_log: false,
  points: [] as Point[],
  color_scale: [] as Point[],
  confirmed: false,
  calibrated: false,
  reason: '',
  base_revision: 0,
})
const mode = ref<'point' | 'origin' | 'x_reference' | 'y_reference' | 'color'>('origin')
const error = ref('')
const result = ref<{ revision: number; rows: Record<string, unknown>[] }>()
const history = ref<
  { revision: number; specification: typeof specification.value; rows: Record<string, unknown>[] }[]
>([])
const dragging = ref<number>()
const image = ref<HTMLImageElement>()
const colorValue = ref(0)
async function load() {
  try {
    history.value = await request({
      action: 'fullDocument',
      projectId: props.projectId,
      assetId: props.assetId,
      operation: 'charts',
      version: props.version,
    })
    specification.value.base_revision = history.value.length
  } catch (cause) {
    error.value = readableError(cause)
  }
}
onMounted(load)
function at(event: PointerEvent) {
  const box = (event.currentTarget as SVGElement).getBoundingClientRect()
  const item = point(
    Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)),
    Math.max(0, Math.min(1, (event.clientY - box.top) / box.height)),
  )
  if (image.value) {
    const canvas = document.createElement('canvas')
    canvas.width = image.value.naturalWidth
    canvas.height = image.value.naturalHeight
    const context = canvas.getContext('2d')!
    context.drawImage(image.value, 0, 0)
    const rgb = context.getImageData(
      Math.min(canvas.width - 1, Math.floor(item.x * canvas.width)),
      Math.min(canvas.height - 1, Math.floor(item.y * canvas.height)),
      1,
      1,
    ).data
    item.rgb = [rgb[0]!, rgb[1]!, rgb[2]!]
  }
  return item
}
function place(event: PointerEvent) {
  if (dragging.value !== undefined) return
  const item = at(event)
  if (mode.value === 'point') specification.value.points.push(item)
  else if (mode.value === 'color') {
    item.label_value = colorValue.value
    specification.value.color_scale.push(item)
  } else specification.value[mode.value] = item
}
function beginDrag(event: PointerEvent, index: number) {
  event.stopPropagation()
  dragging.value = index
  ;(event.currentTarget as SVGElement).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (dragging.value === undefined) return
  const old = specification.value.points[dragging.value]!
  Object.assign(old, at(event), { category: old.category, label_value: old.label_value })
}
async function save() {
  error.value = ''
  try {
    result.value = await request({
      action: 'fullDocument',
      projectId: props.projectId,
      assetId: props.assetId,
      operation: 'save_chart',
      version: props.version,
      payload: { ...specification.value },
    })
    await load()
  } catch (cause) {
    error.value = readableError(cause)
  }
}
function restore(revision: number) {
  const saved = history.value.find((item) => item.revision === revision)
  if (saved) {
    specification.value = JSON.parse(JSON.stringify(saved.specification))
    specification.value.base_revision = history.value.length
    result.value = saved
  }
}
function exportCsv() {
  if (!result.value) return
  const keys = [...new Set(result.value.rows.flatMap((row) => Object.keys(row)))]
  const escape = (value: unknown) =>
    '"' +
    String(value ?? '')
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"'
  const csv =
    '\uFEFF' +
    [
      keys.map(escape).join(','),
      ...result.value.rows.map((row) => keys.map((key) => escape(row[key])).join(',')),
    ].join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'chart-data.csv'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <div class="chart-overlay" role="dialog" aria-modal="true" aria-label="图表数据提取">
    <header>
      <h2>图表数据提取与核对</h2>
      <button @click="$emit('close')">关闭图表</button>
    </header>
    <p>
      先查看原生附件是否已有数据。这里保存的是图像估计或人工抄录标注，不能冒充原始数据。每个子图单独标定；不执行绘图代码。
    </p>
    <div class="chart-controls">
      <label>
        图型
        <select v-model="specification.kind">
          <option value="curve">曲线／普通剖面</option>
          <option value="scatter">散点</option>
          <option value="bar">柱状图（纵轴数值）</option>
          <option value="pie">饼图</option>
          <option value="heatmap">简单热力图</option>
          <option value="manual">人工抄录图上标注</option>
          <option value="not_applicable">不适用／无法可靠提取</option>
        </select>
      </label>
      <label>
        子图
        <input v-model="specification.panel" />
      </label>
      <label>
        系列
        <input v-model="specification.series" />
      </label>
      <label>
        X 单位
        <input v-model="specification.x_unit" />
      </label>
      <label>
        Y／数值单位
        <input v-model="specification.y_unit" />
      </label>
      <label>
        点击操作
        <select v-model="mode">
          <option value="origin">设原点／饼图圆心</option>
          <option value="x_reference">设 X 参考点</option>
          <option value="y_reference">设 Y 参考点</option>
          <option value="point">添加数据点／扇区边界</option>
          <option value="color">采集色标颜色</option>
        </select>
      </label>
      <label>
        X 起点
        <input v-model.number="specification.x_min" type="number" />
      </label>
      <label>
        X 终点
        <input v-model.number="specification.x_max" type="number" />
      </label>
      <label>
        Y 起点
        <input v-model.number="specification.y_min" type="number" />
      </label>
      <label>
        Y 终点
        <input v-model.number="specification.y_max" type="number" />
      </label>
      <label>
        <input v-model="specification.x_log" type="checkbox" />
        X 对数
      </label>
      <label>
        <input v-model="specification.y_log" type="checkbox" />
        Y 对数
      </label>
      <label>
        色标点数值
        <input v-model.number="colorValue" type="number" />
      </label>
    </div>
    <p>
      依次点击原点、X 参考点、Y
      参考点并填写数值，再添加数据点。点可拖动。饼图无标注时按顺时针点击扇区边界，仅适用于无透视的平面圆；热力图按色标顺序采集至少两个色标点。
    </p>
    <div class="chart-image">
      <img ref="image" :src="imageUrl" alt="待数字化原图" />
      <svg
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        @pointerdown="place"
        @pointermove="move"
        @pointerup="dragging = undefined"
        @pointercancel="dragging = undefined"
      >
        <polyline
          v-if="specification.kind === 'curve'"
          :points="specification.points.map((p) => `${p.x * 1000},${p.y * 1000}`).join(' ')"
          fill="none"
          stroke="#e34325"
          stroke-width="2"
        />
        <template
          v-for="(p, key) in {
            O: specification.origin,
            X: specification.x_reference,
            Y: specification.y_reference,
          }"
          :key="key"
        >
          <circle :cx="p.x * 1000" :cy="p.y * 1000" r="7" fill="#1475c1" />
          <text :x="p.x * 1000 + 10" :y="p.y * 1000" fill="#1475c1" font-size="24">{{ key }}</text>
        </template>
        <circle
          v-for="(p, i) in specification.points"
          :key="i"
          :cx="p.x * 1000"
          :cy="p.y * 1000"
          r="7"
          fill="#ee4422"
          style="cursor: move"
          @pointerdown="beginDrag($event, i)"
        />
      </svg>
    </div>
    <table>
      <thead>
        <tr>
          <th>点</th>
          <th>类别</th>
          <th>标注数值（可选）</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(p, i) in specification.points" :key="i">
          <td>{{ i + 1 }} ({{ p.x.toFixed(4) }}, {{ p.y.toFixed(4) }})</td>
          <td><input v-model="p.category" /></td>
          <td><input v-model.number="p.label_value" type="number" /></td>
          <td><button @click="specification.points.splice(i, 1)">删除点</button></td>
        </tr>
      </tbody>
    </table>
    <p v-for="(stop, i) in specification.color_scale" :key="i">
      色标 {{ stop.rgb }} → {{ stop.label_value }}
      <button @click="specification.color_scale.splice(i, 1)">删除色标</button>
    </p>
    <label>
      修订／限制说明
      <input v-model="specification.reason" />
    </label>
    <label>
      <input v-model="specification.confirmed" type="checkbox" />
      我已对照原图核对本系列
    </label>
    <label>
      <input v-model="specification.calibrated" type="checkbox" />
      我已核对并完成坐标轴／圆心／色标标定
    </label>
    <button @click="save">计算并保存新修订</button>
    <button :disabled="!result" @click="exportCsv">导出数值 CSV</button>
    <select
      aria-label="历史图表修订"
      @change="restore(Number(($event.target as HTMLSelectElement).value))"
    >
      <option value="">载入历史修订</option>
      <option
        v-for="entry in history.filter((item) => item.specification.resource === resource)"
        :key="entry.revision"
        :value="entry.revision"
      >
        {{ entry.revision }} · {{ entry.specification.panel }} · {{ entry.specification.series }}
      </option>
    </select>
    <p v-if="error" role="alert" class="error-box">{{ error }}</p>
    <pre v-if="result">{{ result.rows }}</pre>
  </div>
</template>
<style scoped>
.chart-overlay {
  position: fixed;
  inset: 20px;
  z-index: 100;
  background: white;
  box-shadow: 0 0 0 40px #0008;
  border-radius: 12px;
  padding: 24px;
  overflow: auto;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chart-controls {
  display: grid;
  grid-template-columns: repeat(4, minmax(100px, 1fr));
  gap: 12px;
}
.chart-image {
  position: relative;
  max-width: 900px;
  margin: 20px auto;
  line-height: 0;
}
.chart-image img {
  width: 100%;
  display: block;
}
.chart-image svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  touch-action: none;
}
pre {
  white-space: pre-wrap;
}
table {
  width: 100%;
}
</style>
