import { _electron as electron, expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtemp, mkdir, copyFile, rm, readFile, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

test('local PDF parser covers scan and rotation, locates evidence and repairs a page', async () => {
  test.setTimeout(240000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-pdf-next-'))
  const source = join(temporary, 'papers')
  await mkdir(source)
  execFileSync(resolve('.venv/Scripts/python.exe'), [
    'scripts/create_parser_pdf_fixture.py',
    join(temporary, 'fixtures'),
  ])
  const pdf = join(source, 'boundary.pdf')
  await copyFile(join(temporary, 'fixtures', 'constructed-boundaries.pdf'), pdf)
  const before = await readFile(pdf)
  const app = await electron.launch({
    args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
    executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
    env: { ...process.env, LITEXTRACT_DATA_DIR: join(temporary, 'data') },
  })
  try {
    const page = await app.firstWindow()
    await page.getByRole('button', { name: '＋ 新建项目' }).click()
    await page.getByRole('dialog').getByLabel('名称', { exact: true }).fill('PDF 构造边界验收')
    await page.getByRole('dialog').getByLabel('文献文件夹', { exact: true }).fill(source)
    await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '扫描文件夹', exact: true }).click()
    await page.getByRole('button', { name: '确认分组并更新索引' }).click()
    await page.locator('.document-card summary').first().click()
    await page.getByRole('button', { name: '阅读正文与附件' }).first().click()
    const panel = page.locator('.full-document-panel')
    await panel.getByRole('button', { name: '生成新版全文', exact: true }).click()
    await expect(panel.locator('span[role="status"]')).toHaveText('ready', { timeout: 120000 })
    const blocks = panel.locator('.content-block')
    for (const number of [1, 2, 3, 4]) {
      await expect(
        blocks
          .filter({ hasText: `第 ${number} 页 · 定位原文` })
          .filter({ hasText: number === 2 ? '12.50' : '0.00004' }),
      ).toHaveCount(1)
    }
    await panel.getByRole('button', { name: '第 3 页 · 定位原文' }).first().click()
    await expect(panel.locator('[data-testid="evidence-bbox"]')).toBeVisible()
    await page.screenshot({ path: 'test-results/parser-pdf-side-by-side.png', fullPage: true })
    await panel.getByText('仅重做指定 PDF 页', { exact: true }).click()
    await panel.getByPlaceholder('例如 3-5,8').fill('3')
    await panel.getByRole('button', { name: '生成新版全文', exact: true }).click()
    await expect(panel.locator('span[role="status"]')).toHaveText(/queued|running/)
    await expect(panel.locator('span[role="status"]')).toHaveText('ready', { timeout: 120000 })
    await expect(panel.locator('.full-blocks')).toContainText('12.50')
    expect(await readFile(pdf)).toEqual(before)
  } catch (error) {
    for (const name of await readdir(join(temporary, 'data'), { recursive: true })) {
      if (name.endsWith('.log'))
        await test
          .info()
          .attach('parser-log', { path: join(temporary, 'data', name), contentType: 'text/plain' })
    }
    const page = app.windows()[0]
    if (page)
      await test.info().attach('page-text', {
        body: await page.locator('body').innerText(),
        contentType: 'text/plain',
      })
    throw error
  } finally {
    await app.close()
    await rm(temporary, { recursive: true, force: true })
  }
})
