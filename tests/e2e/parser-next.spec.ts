import { _electron as electron, expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

test('native full text, correction history and chart calibration work in the desktop', async () => {
  test.setTimeout(180000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-next-'))
  const source = join(temporary, 'source')
  execFileSync(resolve('.venv/Scripts/python.exe'), ['scripts/create_next_fixtures.py', source])
  const before = await readFile(join(source, 'native.docx'))
  const app = await electron.launch({
    args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
    executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
    env: { ...process.env, LITEXTRACT_DATA_DIR: join(temporary, 'data') },
  })
  try {
    const page = await app.firstWindow()
    await page.getByRole('button', { name: '＋ 新建项目' }).click()
    await page.getByRole('dialog').getByLabel('名称', { exact: true }).fill('新版解析构造样例')
    await page.getByRole('dialog').getByLabel('文献文件夹', { exact: true }).fill(source)
    await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '扫描文件夹', exact: true }).click()
    await page.getByRole('button', { name: '确认分组并更新索引' }).click()
    await page.locator('.document-card summary').first().click()
    await page.getByRole('button', { name: '阅读正文与附件' }).first().click()
    await page.getByRole('button', { name: /主论文.*native.docx/ }).click()
    await page.getByRole('button', { name: '生成新版全文', exact: true }).click()
    await expect(page.locator('.full-document-panel [role="status"]')).toHaveText('ready', {
      timeout: 30000,
    })
    await expect(page.locator('.full-blocks')).toContainText('0.00004')
    await expect(page.locator('.full-blocks .katex')).toBeVisible()
    const block = page
      .locator('.full-blocks .content-block')
      .filter({ hasText: 'Known abundance' })
      .first()
    await block.getByRole('button', { name: '修正', exact: true }).click()
    await block
      .getByLabel('修正内容')
      .fill('Known abundance: 0.00004 particles/L. Reviewed fixture.')
    await block.getByPlaceholder('修正原因').fill('Compared with constructed source')
    await block.getByRole('button', { name: '保存修正记录' }).click()
    await expect(block).toContainText('Reviewed fixture.')
    await page.getByRole('button', { name: '检查完整全文出口' }).click()
    await expect(page.getByText(/批 · 全文覆盖 完整/)).toBeVisible()
    const imageBlock = page
      .locator('.full-blocks .content-block')
      .filter({ has: page.locator('img') })
      .first()
    await imageBlock.locator('summary').first().click()
    await imageBlock.getByRole('button', { name: '提取图表数据' }).click()
    const dialog = page.getByRole('dialog', { name: '图表数据提取' })
    await dialog.getByLabel('点击操作').selectOption('point')
    const svg = dialog.locator('.chart-image svg')
    await svg.click({ position: { x: 200, y: 150 } })
    await dialog.getByLabel('修订／限制说明').fill('Synthetic calibration test')
    await dialog.getByLabel('我已核对并完成坐标轴／圆心／色标标定').check()
    await dialog.getByRole('button', { name: '计算并保存新修订' }).click()
    await expect(dialog.locator('pre')).toContainText('image_estimate')
    await expect(dialog.getByLabel('历史图表修订').locator('option')).toHaveCount(2)
    await dialog.getByLabel('历史图表修订').selectOption('1')
    await expect(dialog.locator('pre')).toContainText('image_estimate')
    const originalPoint = await dialog.locator('tbody tr').innerText()
    const dot = await svg.locator('circle[fill="#ee4422"]').boundingBox()
    if (!dot) throw new Error('digitized point missing')
    await page.mouse.move(dot.x + dot.width / 2, dot.y + dot.height / 2)
    await page.mouse.down()
    await page.mouse.move(dot.x + 30, dot.y + 30, { steps: 5 })
    await page.mouse.up()
    await expect(dialog.locator('tbody tr')).not.toHaveText(originalPoint)
    await dialog.getByRole('button', { name: '删除点', exact: true }).click()
    await expect(dialog.locator('tbody tr')).toHaveCount(0)
    await page.screenshot({ path: 'test-results/parser-next-digitizer.png', fullPage: true })
    await dialog.getByRole('button', { name: '关闭图表' }).click()
    expect(await readFile(join(source, 'native.docx'))).toEqual(before)
  } catch (error) {
    const page = app.windows()[0]
    if (page) {
      await test.info().attach('page-text', {
        body: await page.locator('body').innerText(),
        contentType: 'text/plain',
      })
      await page.screenshot({ path: 'test-results/parser-next-failure.png', fullPage: true })
    }
    throw error
  } finally {
    await app.close()
    await rm(temporary, { recursive: true, force: true })
  }
})
