import { _electron as electron, expect, test } from '@playwright/test'
import { createServer } from 'node:http'
import { mkdtemp, mkdir, rm, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import type { JobDetail, ResultRecord } from '../../desktop/src/shared/contracts'

test('confirmed schema runs in a worker, emits progress, isolates failures and supports cancel/retry', async () => {
  test.setTimeout(150000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-jobs-'))
  const source = join(temporary, 'source')
  await mkdir(source)
  await writeFile(join(source, 'data.csv'), 'Site,Value\nAlpha,12.5\nBeta,8.2\n')
  const plan = {
    name: '站点浓度',
    granularity: '每个采样站点一行',
    fields: [
      { key: 'site', label: '站点', type: 'string', unit: '', description: '' },
      { key: 'concentration', label: '浓度', type: 'number', unit: 'mg/L', description: '' },
    ],
    record_key: ['site'],
    missing_policy: 'null_with_reason',
    evidence_policy: 'quoted_source_required',
    conflict_policy: 'keep_separate_and_flag',
  }
  let slow = false
  const server = createServer((req, res) => {
    let text = ''
    req.on('data', (chunk) => {
      text += String(chunk)
    })
    req.on('end', () => {
      const request = JSON.parse(text)
      const payload = JSON.parse(request.messages.at(-1).content)
      const body = payload.goal
        ? plan
        : {
            records: [
              ['Alpha', 12.5],
              ['Beta', 8.2],
            ].map(([site, value]) => ({
              fields: {
                site: { value: site, evidence_ids: [payload.sources[0].id] },
                concentration: { value, unit: 'mg/L', evidence_ids: [payload.sources[0].id] },
              },
              risks: [],
            })),
            warnings: [],
          }
      const reply = () => {
        if (!res.destroyed) {
          res.setHeader('Content-Type', 'application/json')
          res.end(
            JSON.stringify({
              choices: [{ finish_reason: 'stop', message: { content: JSON.stringify(body) } }],
            }),
          )
        }
      }
      if (slow && !payload.goal) setTimeout(reply, 15000).unref()
      else reply()
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as { port: number }).port
  const env: Record<string, string> = Object.fromEntries(
    Object.entries(process.env).filter((pair): pair is [string, string] => pair[1] !== undefined),
  )
  env.LITEXTRACT_DATA_DIR = join(temporary, 'data')
  delete env.ELECTRON_RUN_AS_NODE
  const app = await electron.launch({
    args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
    executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
    env,
  })
  app.process().stderr?.on('data', (chunk) => process.stderr.write(chunk))
  try {
    const page = await app.firstWindow()
    page.on('pageerror', (error) => console.error('Renderer error:', error.message))
    const projectId = await page.evaluate(
      async ({ source, port }) => {
        const bridge = window.litextract!
        const project = (await bridge.request({
          action: 'createProject',
          name: '提取验收',
          source_path: source,
        })) as { id: string }
        const draft = (await bridge.request({ action: 'scan', projectId: project.id })) as {
          id: string
          snapshot: { groups: { title: string; main_path: string | null; asset_paths: string[] }[] }
        }
        await bridge.request({
          action: 'confirmScan',
          projectId: project.id,
          draft_id: draft.id,
          groups: draft.snapshot.groups.map(({ title, main_path, asset_paths }) => ({
            title,
            main_path,
            asset_paths,
          })),
        })
        await bridge.request({ action: 'createSession', projectId: project.id, name: '提取会话' })
        await bridge.request({
          action: 'saveModel',
          projectId: project.id,
          base_url: `http://127.0.0.1:${port}`,
          model: 'fixture-model',
          apiKey: 'fixture-only',
        })
        return project.id
      },
      { source, port },
    )
    await page.reload()
    await page.getByRole('button', { name: '◌ 提取会话', exact: true }).click()
    await page.getByLabel('整理目标', { exact: true }).fill('提取各站点浓度，每个站点一行')
    await page.getByRole('button', { name: '生成提取方案', exact: true }).click()
    await expect(page.getByLabel('一行数据代表什么', { exact: true })).toHaveValue(
      '每个采样站点一行',
    )
    await expect(page.locator('.job-item')).toHaveCount(0)
    await page.getByRole('button', { name: '确认方案并开始提取', exact: true }).click()
    await expect(page.locator('.job-detail')).toContainText('生成 2 条记录', { timeout: 60000 })
    await expect(page.locator('.job-detail > h3')).toContainText('全部完成')
    await page.screenshot({ path: 'test-results/stage4-worker.png', fullPage: true })
    const firstJobId = await page.evaluate(async (projectId) => {
      const sessions = (await window.litextract!.request({ action: 'sessions', projectId })) as {
        id: string
      }[]
      const jobs = (await window.litextract!.request({
        action: 'jobs',
        projectId,
        sessionId: sessions[0].id,
      })) as { id: string }[]
      return jobs[0].id
    }, projectId)
    const records = (await page.evaluate(
      async ({ projectId, jobId }) =>
        window.litextract!.request({ action: 'records', projectId, jobId }),
      { projectId, jobId: firstJobId },
    )) as ResultRecord[]
    expect(records.map((row) => row.values_json.site.value).sort()).toEqual(['Alpha', 'Beta'])
    await page.locator('.result-table').getByRole('button', { name: 'Alpha', exact: true }).click()
    await page.getByLabel('修订值', { exact: true }).fill('Alpha corrected')
    await page.getByLabel('修订原因', { exact: true }).fill('核对站点名称')
    await page.getByRole('button', { name: '保存为新修订', exact: true }).click()
    await expect(page.locator('.result-table')).toContainText('Alpha corrected')
    await page.getByLabel('结果版本', { exact: true }).selectOption('automatic')
    await expect(page.locator('.result-table')).not.toContainText('Alpha corrected')
    await page.getByLabel('结果版本', { exact: true }).selectOption('1')
    await expect(page.locator('.result-table')).toContainText('Alpha corrected')
    await page.screenshot({ path: 'test-results/stage5-review.png', fullPage: true })
    const exportPath = join(temporary, 'reviewed.csv')
    await app.evaluate(({ dialog }, filePath) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath })
    }, exportPath)
    await page.getByRole('button', { name: '导出 CSV', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('已导出')
    expect(await readFile(exportPath, 'utf8')).toContain('Alpha corrected')
    slow = true
    await page.getByRole('button', { name: '确认方案并开始提取', exact: true }).click()
    await expect(page.getByRole('button', { name: '取消任务', exact: true })).toBeVisible()
    await expect(page.locator('.job-detail > h3')).toContainText('正在处理', { timeout: 30000 })
    await page.getByRole('button', { name: '取消任务', exact: true }).click()
    await expect(page.locator('.job-detail > h3')).toContainText('已取消')
    slow = false
    await page.getByRole('button', { name: '重试未完成文献', exact: true }).click()
    await expect(page.locator('.job-detail > h3')).toContainText('全部完成', { timeout: 60000 })
    const detail = (await page.evaluate(
      async ({ projectId, jobId }) =>
        window.litextract!.request({ action: 'job', projectId, jobId }),
      { projectId, jobId: firstJobId },
    )) as JobDetail
    expect(detail.record_count).toBe(2)
    await mkdir(join(source, 'broken'))
    await writeFile(join(source, 'broken', 'supp.docx'), 'deliberately invalid office document')
    await page.evaluate(async (projectId) => {
      const draft = (await window.litextract!.request({ action: 'scan', projectId })) as {
        id: string
        snapshot: { groups: { title: string; main_path: string | null; asset_paths: string[] }[] }
      }
      await window.litextract!.request({
        action: 'confirmScan',
        projectId,
        draft_id: draft.id,
        groups: draft.snapshot.groups.map(({ title, main_path, asset_paths }) => ({
          title,
          main_path,
          asset_paths,
        })),
      })
    }, projectId)
    await page.getByRole('button', { name: '生成提取方案', exact: true }).click()
    await expect(page.locator('.plan-editor')).toContainText('范围：2 篇文献')
    await page.getByRole('button', { name: '确认方案并开始提取', exact: true }).click()
    await expect(page.locator('.job-detail > h3')).toContainText('部分完成', { timeout: 60000 })
    await expect(page.locator('.job-detail')).toContainText('生成 2 条记录')
    await expect(page.locator('.job-detail .error-box')).toContainText('解析失败')
    await page.locator('.plugin-panel summary').first().click()
    await page.getByRole('button', { name: '启用微塑料插件', exact: true }).click()
    await page.getByRole('button', { name: '加载微塑料模板', exact: true }).click()
    await expect(page.getByLabel('任务名称', { exact: true })).toHaveValue('微塑料站点数据')
    await expect(page.locator('.plan-editor')).toContainText('microplastics v1.0.0')
    await page.getByRole('button', { name: '禁用微塑料插件', exact: true }).click()
    await expect(page.getByRole('button', { name: '加载微塑料模板', exact: true })).toHaveCount(0)
    await expect(page.locator('.plan-editor')).toContainText('microplastics v1.0.0')
  } finally {
    await app.close()
    server.closeAllConnections()
    await new Promise<void>((resolve) => server.close(() => resolve()))
    await rm(temporary, { recursive: true, force: true, maxRetries: 3 })
  }
})
