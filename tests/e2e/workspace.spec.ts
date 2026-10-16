import { _electron as electron, expect, test, type Page } from '@playwright/test'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

async function createProject(page: Page, name: string, source: string) {
  await page.getByRole('button', { name: '＋ 新建项目' }).click()
  const dialog = page.getByRole('dialog', { name: '新建文献项目' })
  await dialog.getByLabel('名称', { exact: true }).fill(name)
  await dialog.getByLabel('文献文件夹', { exact: true }).fill(source)
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
}
async function createSession(page: Page, name: string, projectName: string) {
  const tree = page
    .locator('.project-tree')
    .filter({ has: page.getByRole('button', { name: projectName, exact: true }) })
  await tree.getByRole('button', { name: '＋ 新建会话' }).click()
  const dialog = page.getByRole('dialog', { name: '新建会话' })
  await dialog.getByLabel('名称').fill(name)
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
}

test('projects, grouping and isolated sessions survive a real desktop restart', async () => {
  test.setTimeout(120000)
  const temporary = await mkdtemp(join(tmpdir(), 'litextract-workspace-'))
  const source = join(temporary, '中文论文')
  await mkdir(join(source, 'study'), { recursive: true })
  await writeFile(join(source, 'study', 'paper.pdf'), 'fixture paper')
  await writeFile(join(source, 'study', 'supp.csv'), 'site,value\nA,12\n')
  const original = await readFile(join(source, 'study', 'paper.pdf'))
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
  let closed = false
  try {
    let page = await app.firstWindow()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await createProject(page, '河流研究', source)
    await page.getByRole('button', { name: '扫描文件夹', exact: true }).click()
    await expect(page.getByRole('heading', { name: '确认文献与附件分组' })).toBeVisible()
    await page.getByRole('button', { name: '确认分组并更新索引' }).click()
    await expect(page.locator('.document-card')).toHaveCount(1)
    await page.locator('.document-card summary').click()
    await expect(page.locator('.asset-row')).toHaveCount(2)
    await page.screenshot({ path: 'test-results/stage1-documents.png', fullPage: true })
    await createSession(page, '方法阅读', '河流研究')
    await page.getByLabel('会话笔记', { exact: true }).fill('只属于方法会话的笔记')
    await page.getByRole('button', { name: '保存笔记', exact: true }).click()
    await expect(page.locator('.note')).toContainText('只属于方法会话的笔记')
    await page.getByLabel('文献问题', { exact: true }).fill('暂存研究问题')
    await page.getByLabel('会话笔记', { exact: true }).fill('暂存阅读笔记')
    await page.getByRole('button', { name: '河流研究', exact: true }).click()
    await page.getByRole('button', { name: '◌ 方法阅读', exact: true }).click()
    await expect(page.getByLabel('文献问题', { exact: true })).toHaveValue('暂存研究问题')
    await expect(page.getByLabel('会话笔记', { exact: true })).toHaveValue('暂存阅读笔记')
    await createSession(page, '结果核查', '河流研究')
    await expect(page.getByLabel('文献问题', { exact: true })).toHaveValue('')
    await expect(page.locator('.note')).toHaveCount(0)
    await createProject(page, '湖泊研究', source)
    await expect(page.locator('.document-card')).toHaveCount(0)
    await createSession(page, '湖泊笔记', '湖泊研究')
    await expect(page.locator('.note')).toHaveCount(0)
    await page.getByRole('button', { name: '◌ 方法阅读', exact: true }).click()
    await expect(page.locator('.note')).toContainText('只属于方法会话的笔记')
    await page.screenshot({ path: 'test-results/stage1-sessions.png', fullPage: true })
    expect(errors).toEqual([])
    await app.close()
    closed = true
    app = await electron.launch({
      args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
      executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
      env,
    })
    closed = false
    page = await app.firstWindow()
    await expect(page.getByRole('button', { name: '河流研究', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '湖泊研究', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '◌ 方法阅读', exact: true }).click()
    await expect(page.locator('.note')).toContainText('只属于方法会话的笔记')
    await page.getByRole('button', { name: '重命名会话', exact: true }).click()
    await page.getByRole('dialog').getByLabel('名称').fill('方法复核')
    await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.getByRole('heading', { name: '方法复核', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '河流研究', exact: true }).click()
    await page.getByRole('button', { name: '重新扫描', exact: true }).click()
    await page.getByRole('button', { name: '确认分组并更新索引' }).click()
    await expect(page.locator('.scan-review')).toHaveCount(0)
    await expect(page.locator('.document-card')).toHaveCount(1)
    await page.getByRole('button', { name: '移除项目', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(page.getByRole('button', { name: '河流研究', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '湖泊研究', exact: true })).toBeVisible()
    expect(await readFile(join(source, 'study', 'paper.pdf'))).toEqual(original)
    await app.close()
    closed = true
  } catch (error) {
    const page = app.windows()[0]
    if (page) {
      await test.info().attach('desktop-state', {
        body: await page.locator('body').innerText(),
        contentType: 'text/plain',
      })
      await page.screenshot({ path: 'test-results/stage1-failure.png', fullPage: true })
    }
    throw error
  } finally {
    if (!closed) await app.close()
    await rm(temporary, { recursive: true, force: true, maxRetries: 3 })
  }
})
