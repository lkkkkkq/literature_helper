import { _electron as electron, expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

test('real documents parse and PDF evidence opens on the correct page', async () => {
  test.setTimeout(180000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-reading-'))
  const source = join(temporary, 'source')
  execFileSync(resolve('.venv/Scripts/python.exe'), ['scripts/create_reading_fixtures.py', source])
  await rm(join(source, 'scanned.pdf'))
  const original = await readFile(join(source, 'paper.pdf'))
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
  const backendLogs: string[] = []
  app.process().stderr?.on('data', (chunk: Buffer) => backendLogs.push(chunk.toString()))
  try {
    const page = await app.firstWindow()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.getByRole('button', { name: '＋ 新建项目' }).click()
    await page.getByRole('dialog').getByLabel('名称', { exact: true }).fill('原文阅读验收')
    await page.getByRole('dialog').getByLabel('文献文件夹', { exact: true }).fill(source)
    await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '扫描文件夹', exact: true }).click()
    await page.getByRole('button', { name: '确认分组并更新索引' }).click()
    await page.locator('.document-card summary').click()
    await page.getByRole('button', { name: '阅读正文与附件' }).click()
    await expect(page.getByTestId('pdf-pages')).toHaveText('/ 2', { timeout: 15000 })
    await expect(page.locator('.pdf-page canvas')).toBeVisible()
    await page.getByRole('button', { name: '解析文档', exact: true }).click()
    await expect(page.getByText('解析完成', { exact: true })).toBeVisible({ timeout: 90000 })
    const evidence = page.locator('.content-block').filter({ hasText: 'observed concentration' })
    await evidence.getByRole('button', { name: '第 2 页 · 定位原文' }).click()
    await expect(page.getByLabel('PDF 页码', { exact: true })).toHaveValue('2')
    await expect(page.getByTestId('evidence-bbox')).toBeVisible()
    await expect(page.locator('.textLayer .evidence-text')).not.toHaveCount(0)
    await expect(page.locator('.textLayer .evidence-text')).toHaveCount(1)
    await page.screenshot({ path: 'test-results/stage2-evidence.png', fullPage: true })
    for (const name of ['supp.csv', 'supp.xlsx', 'supp.docx']) {
      await page.getByRole('button', { name: new RegExp(name.replace('.', '\\.')) }).click()
      await expect(page.locator('.pdf-reader')).toHaveCount(0)
      await page.getByRole('button', { name: '解析文档', exact: true }).click()
      await expect(page.getByText('解析完成', { exact: true })).toBeVisible({ timeout: 30000 })
      await expect(page.locator('.parsed-table-scroll')).toContainText('Alpha')
      await expect(page.locator('.source-link')).toHaveCount(0)
    }
    await page.screenshot({ path: 'test-results/stage2-attachment.png', fullPage: true })
    expect(await readFile(join(source, 'paper.pdf'))).toEqual(original)
    expect(errors).toEqual([])
  } catch (error) {
    await test
      .info()
      .attach('backend-log', { body: backendLogs.join(''), contentType: 'text/plain' })
    const page = app.windows()[0]
    if (page) {
      await test.info().attach('reading-state', {
        body: await page.locator('body').innerText(),
        contentType: 'text/plain',
      })
      await page.screenshot({ path: 'test-results/stage2-failure.png', fullPage: true })
    }
    throw error
  } finally {
    await app.close()
    await rm(temporary, { recursive: true, force: true, maxRetries: 3 })
  }
})
