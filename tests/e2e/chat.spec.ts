import { _electron as electron, expect, test } from '@playwright/test'
import { createServer } from 'node:http'
import { execFileSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

test('QA uses encrypted credentials and persists source citations', async () => {
  test.setTimeout(240000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-chat-'))
  const source = join(temporary, 'source')
  execFileSync(resolve('.venv/Scripts/python.exe'), ['scripts/create_reading_fixtures.py', source])
  await rm(join(source, 'scanned.pdf'))
  const secret = 'fixture-secret-never-store-plain'
  const server = createServer((req, res) => {
    let body = ''
    req.on('data', (chunk) => {
      body += String(chunk)
    })
    req.on('end', () => {
      if (req.headers.authorization !== `Bearer ${secret}`) {
        res.writeHead(401)
        res.end()
        return
      }
      const payload = JSON.parse(JSON.parse(body).messages.at(-1).content)
      const evidence = payload.sources.find((item: { quote: string }) =>
        item.quote.includes('observed concentration'),
      )
      res.setHeader('Content-Type', 'application/json')
      res.end(
        JSON.stringify({
          choices: [
            {
              finish_reason: 'stop',
              message: {
                content: JSON.stringify({
                  parts: [
                    {
                      text: String.raw`**研究结果**：Alpha 站点浓度为 12.5 mg/L。公式排版示例：$f_d(u)\approx\frac{1}{2}\rho C_d A u_0^2$。`,
                      kind: 'claim',
                      evidence_ids: [evidence.id],
                    },
                    {
                      text: '当前证据不足以完整说明研究局限。',
                      kind: 'uncertainty',
                      evidence_ids: [],
                    },
                  ],
                }),
              },
            },
          ],
        }),
      )
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as { port: number }).port
  const env: Record<string, string> = Object.fromEntries(
    Object.entries(process.env).filter((pair): pair is [string, string] => pair[1] !== undefined),
  )
  env.LITEXTRACT_DATA_DIR = join(temporary, 'data')
  delete env.ELECTRON_RUN_AS_NODE
  let app = await electron.launch({
    args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
    executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
    env,
  })
  try {
    let page = await app.firstWindow()
    const project = await page.evaluate(async (source) => {
      const bridge = window.litextract!
      const project = (await bridge.request({
        action: 'createProject',
        name: '问答验收',
        source_path: source,
      })) as { id: string }
      const draft = (await bridge.request({ action: 'scan', projectId: project.id })) as {
        id: string
        snapshot: { groups: { title: string; main_path: string | null; asset_paths: string[] }[] }
      }
      const documents = (await bridge.request({
        action: 'confirmScan',
        projectId: project.id,
        draft_id: draft.id,
        groups: draft.snapshot.groups.map(({ title, main_path, asset_paths }) => ({
          title,
          main_path,
          asset_paths,
        })),
      })) as { assets: { id: string; role: string }[] }[]
      const asset = documents[0].assets.find((item) => item.role === 'main')!
      await bridge.request({
        action: 'parseAsset',
        projectId: project.id,
        assetId: asset.id,
        ocr: false,
        force: false,
      })
      await bridge.request({ action: 'createSession', projectId: project.id, name: '研究问题' })
      return { ...project, assetId: asset.id }
    }, source)
    await expect
      .poll(
        () =>
          page.evaluate(
            async (project) =>
              (
                (await window.litextract!.request({
                  action: 'parseStatus',
                  projectId: project.id,
                  assetId: project.assetId,
                })) as { status: string }
              ).status,
            project,
          ),
        { timeout: 120000 },
      )
      .toBe('ready')
    await page.reload()
    await page.getByRole('button', { name: '◌ 研究问题', exact: true }).click()
    await page.locator('.model-settings summary').click()
    await page.getByLabel('接口地址', { exact: true }).fill(`http://127.0.0.1:${port}`)
    await page.getByLabel('API Key', { exact: true }).fill(secret)
    await page.getByRole('button', { name: '保存模型配置' }).click()
    await expect(page.getByText('配置已保存', { exact: true })).toBeVisible()
    expect(
      (await readFile(join(temporary, 'data', 'credentials', `${project.id}.bin`))).includes(
        Buffer.from(secret),
      ),
    ).toBe(false)
    await app.close()
    app = await electron.launch({
      args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
      executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
      env,
    })
    page = await app.firstWindow()
    await page.getByRole('button', { name: '◌ 研究问题', exact: true }).click()
    await page.getByLabel('文献问题', { exact: true }).fill('请说明研究问题、方法、结果和局限')
    await page.getByRole('button', { name: '发送问题', exact: true }).click()
    await expect(page.locator('.markdown-answer')).toHaveCount(2)
    await expect(page.locator('.qa-history')).toContainText('12.5 mg/L')
    await expect(page.locator('.qa-history .katex')).toBeVisible()
    await page.locator('.citation').click()
    await expect(page.getByRole('complementary', { name: '原文证据侧栏' })).toBeVisible()
    const answerBounds = await page.locator('.qa-conversation').boundingBox()
    const evidenceBounds = await page.locator('.evidence-sidebar').boundingBox()
    expect(evidenceBounds!.x).toBeGreaterThanOrEqual(answerBounds!.x + answerBounds!.width)
    await expect(page.getByLabel('PDF 页码', { exact: true })).toHaveValue('2')
    await expect(page.getByTestId('evidence-bbox')).toBeVisible()
    await page.screenshot({ path: 'test-results/stage3-qa.png', fullPage: true })
    expect(
      (await readFile(join(temporary, 'data', 'workspace.db'))).includes(Buffer.from(secret)),
    ).toBe(false)
  } finally {
    await app.close()
    await new Promise<void>((resolve) => server.close(() => resolve()))
    await rm(temporary, { recursive: true, force: true, maxRetries: 3 })
  }
})
