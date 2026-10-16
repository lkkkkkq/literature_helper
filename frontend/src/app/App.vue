<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Conversation, Project } from '../../../desktop/src/shared/contracts'
import { readableError, request } from '../api/workspace'
import HealthPanel from './HealthPanel.vue'
import FirstRunGuide from './FirstRunGuide.vue'
import ProjectTree from '../features/projects/ProjectTree.vue'
import ProjectWorkspace from '../features/projects/ProjectWorkspace.vue'
import SessionWorkspace from '../features/chat/SessionWorkspace.vue'
import { clearDrafts } from '../features/chat/drafts'

const client = useQueryClient()
const projects = useQuery({
  queryKey: ['projects'],
  queryFn: () => request<Project[]>({ action: 'projects' }),
})
const selectedProject = ref('')
const selectedSession = ref('')
const project = computed(() =>
  projects.data.value?.find((item) => item.id === selectedProject.value),
)
const conversations = useQuery({
  queryKey: computed(() => ['sessions', selectedProject.value]),
  enabled: computed(() => !!selectedProject.value),
  queryFn: ({ queryKey }) =>
    request<Conversation[]>({ action: 'sessions', projectId: String(queryKey[1]) }),
})
const session = computed(() =>
  conversations.data.value?.find((item) => item.id === selectedSession.value),
)
type DialogMode =
  | 'createProject'
  | 'renameProject'
  | 'deleteProject'
  | 'createSession'
  | 'renameSession'
  | 'deleteSession'
const modal = ref<{ mode: DialogMode; project?: Project; session?: Conversation } | null>(null)
const name = ref('')
const sourcePath = ref('')
const error = ref('')
const busy = ref(false)
const title = computed(() =>
  modal.value
    ? {
        createProject: '新建文献项目',
        renameProject: '重命名项目',
        deleteProject: '移除项目',
        createSession: '新建会话',
        renameSession: '重命名会话',
        deleteSession: '删除会话',
      }[modal.value.mode]
    : '',
)
const deleting = computed(() => modal.value?.mode.startsWith('delete'))
function select(projectId: string, sessionId: string) {
  selectedProject.value = projectId
  selectedSession.value = sessionId
}
function open(mode: DialogMode, targetProject = project.value, targetSession = session.value) {
  modal.value = { mode, project: targetProject, session: targetSession }
  error.value = ''
  sourcePath.value = ''
  name.value =
    mode === 'createProject'
      ? ''
      : mode === 'createSession'
        ? '新会话'
        : mode === 'renameSession'
          ? (targetSession?.name ?? '')
          : (targetProject?.name ?? '')
}
async function chooseFolder() {
  try {
    const path = await window.litextract?.chooseFolder()
    if (path) {
      sourcePath.value = path
      if (!name.value) name.value = path.split(/[\\/]/).filter(Boolean).pop() ?? ''
    }
  } catch (cause) {
    error.value = readableError(cause)
  }
}
async function submit() {
  const dialog = modal.value
  if (!dialog || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const projectId = dialog.project?.id ?? ''
    if (dialog.mode === 'createProject') {
      const created = await request<Project>({
        action: 'createProject',
        name: name.value,
        source_path: sourcePath.value,
      })
      await client.invalidateQueries({ queryKey: ['projects'] })
      select(created.id, '')
    } else if (dialog.mode === 'renameProject') {
      await request({ action: 'renameProject', projectId, name: name.value })
      await client.invalidateQueries({ queryKey: ['projects'] })
    } else if (dialog.mode === 'deleteProject') {
      await request({ action: 'deleteProject', projectId })
      clearDrafts(projectId)
      if (selectedProject.value === projectId) select('', '')
      await client.cancelQueries({ predicate: (query) => query.queryKey.includes(projectId) })
      client.removeQueries({ predicate: (query) => query.queryKey.includes(projectId) })
      await client.invalidateQueries({ queryKey: ['projects'] })
    } else if (dialog.mode === 'createSession') {
      const created = await request<Conversation>({
        action: 'createSession',
        projectId,
        name: name.value,
      })
      await client.invalidateQueries({ queryKey: ['sessions', projectId] })
      select(projectId, created.id)
    } else if (dialog.mode === 'renameSession') {
      await request({
        action: 'renameSession',
        projectId,
        sessionId: dialog.session!.id,
        name: name.value,
      })
      await client.invalidateQueries({ queryKey: ['sessions', projectId] })
    } else if (dialog.mode === 'deleteSession') {
      await request({ action: 'deleteSession', projectId, sessionId: dialog.session!.id })
      if (selectedSession.value === dialog.session!.id) select(projectId, '')
      clearDrafts(projectId, dialog.session!.id)
      await client.cancelQueries({ queryKey: ['messages', projectId, dialog.session!.id] })
      client.removeQueries({ queryKey: ['messages', projectId, dialog.session!.id] })
      await client.invalidateQueries({ queryKey: ['sessions', projectId] })
    }
    modal.value = null
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="workbench">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">L</span>
        <div>
          LitExtract
          <span class="version">v2</span>
          <small>文献 · 数据 · 证据</small>
        </div>
      </div>
      <button class="create-project primary" @click="open('createProject')">＋ 新建项目</button>
      <button class="home-link" @click="select('', '')">工作台概览</button>
      <div class="nav-label">文献项目 · {{ projects.data.value?.length ?? 0 }}</div>
      <div class="project-trees">
        <ProjectTree
          v-for="item in projects.data.value ?? []"
          :key="item.id"
          :project="item"
          :active-project="selectedProject"
          :active-session="selectedSession"
          @select="select"
          @create-session="open('createSession', $event)"
        />
        <p v-if="projects.isPending.value" class="muted">加载中…</p>
        <p v-if="projects.isError.value" role="alert" class="small-error">
          {{ readableError(projects.error.value) }}
          <button @click="projects.refetch()">重试</button>
        </p>
        <p v-if="projects.data.value?.length === 0" class="empty-projects">
          从一个文献文件夹开始。
          <br />
          源文件仅引用，不移动。
        </p>
      </div>
      <div class="sidebar-footer">
        <span class="local-dot"></span>
        本地运行 · 数据独立保存
      </div>
    </aside>
    <main>
      <header>
        <span>工作台 / {{ project?.name ?? '概览' }}{{ session ? ` / ${session.name}` : '' }}</span>
        <span class="stage-label">v2 · Beta</span>
      </header>
      <template v-if="!project">
        <section class="welcome">
          <div class="eyebrow">EVIDENCE FIRST</div>
          <h1>从一份文献，开始有据可查的研究。</h1>
          <p>创建项目，整理主论文与附件，为每个阅读目标建立独立会话。</p>
          <button class="primary" @click="open('createProject')">选择文献文件夹</button>
        </section>
        <HealthPanel />
        <FirstRunGuide v-if="projects.data.value?.length === 0" @start="open('createProject')" />
        <section class="roadmap">
          <h2>已开放的工作流程</h2>
          <div class="feature-grid">
            <article>
              <span>01 / 项目</span>
              <h3>导入文件夹</h3>
              <p>只读引用原始文件，支持多个独立项目。</p>
            </article>
            <article>
              <span>02 / 文献</span>
              <h3>确认附件归属</h3>
              <p>检查分组，重新扫描时标记变更和缺失。</p>
            </article>
            <article>
              <span>03 / 会话</span>
              <h3>提问、提取与复核</h3>
              <p>确认方案后后台提取，每条数据都保留原文证据。</p>
            </article>
          </div>
        </section>
        <p class="milestone-note">
          支持引用问答、方案确认、批量提取、人工修订和 CSV/Excel 导出。领域插件可按项目启用。
        </p>
      </template>
      <SessionWorkspace
        v-else-if="session"
        :key="session.id"
        :project="project"
        :session="session"
        @rename="open('renameSession')"
        @remove="open('deleteSession')"
      />
      <p v-else-if="selectedSession && conversations.isPending.value">正在加载会话…</p>
      <p v-else-if="selectedSession && conversations.isError.value" role="alert" class="error-box">
        会话加载失败。
        <button @click="conversations.refetch()">重试</button>
      </p>
      <ProjectWorkspace
        v-else
        :key="project.id"
        :project="project"
        @rename="open('renameProject')"
        @remove="open('deleteProject')"
      />
    </main>
    <div v-if="modal" class="modal-backdrop" @keydown.esc="!busy && (modal = null)">
      <section class="modal" role="dialog" aria-modal="true" :aria-label="title">
        <h2>{{ title }}</h2>
        <form @submit.prevent="submit">
          <template v-if="deleting">
            <p>
              确认{{ modal.mode === 'deleteProject' ? '移除项目' : '删除会话' }}“{{
                modal.session && modal.mode === 'deleteSession'
                  ? modal.session.name
                  : modal.project?.name
              }}”？
            </p>
            <p class="warning">
              {{
                modal.mode === 'deleteProject'
                  ? '这会删除此项目的文献索引、扫描预览、会话和笔记。磁盘上的源文件保持不变。'
                  : '这会删除该会话及其笔记，其他会话保持不变。'
              }}
            </p>
          </template>
          <template v-else>
            <label for="record-name">名称</label>
            <input
              id="record-name"
              v-model="name"
              maxlength="200"
              required
              autofocus
              :disabled="busy"
            />
            <template v-if="modal.mode === 'createProject'">
              <label for="source-path">文献文件夹</label>
              <div class="path-input">
                <input
                  id="source-path"
                  v-model="sourcePath"
                  placeholder="选择文件夹，或粘贴完整路径"
                  required
                  :disabled="busy"
                />
                <button type="button" :disabled="busy" @click="chooseFolder">浏览…</button>
              </div>
              <p class="muted">
                引用原位置，不复制、不移动、不覆盖源文件。创建后可扫描并确认分组。
              </p>
            </template>
          </template>
          <p v-if="error" role="alert" class="error-box">{{ error }}</p>
          <div class="modal-actions">
            <button type="button" :disabled="busy" @click="modal = null">取消</button>
            <button
              :class="deleting ? 'danger' : 'primary'"
              :disabled="busy || (!deleting && !name.trim())"
            >
              {{ busy ? '正在保存…' : deleting ? '确认删除' : '保存' }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>
