import { _electron as electron, expect, test } from '@playwright/test'
import { mkdtemp, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

test('real Electron starts backend, renders health and shuts it down', async () => {
  const workspace = await mkdtemp(join(tmpdir(), 'litextract-e2e-'))
  const env: Record<string, string> = Object.fromEntries(
    Object.entries(process.env).filter((pair): pair is [string, string] => pair[1] !== undefined),
  )
  env.LITEXTRACT_DATA_DIR = workspace
  delete env.ELECTRON_RUN_AS_NODE
  const app = await electron.launch({
    args: process.env.LITEXTRACT_TEST_EXECUTABLE ? [] : ['.'],
    executablePath: process.env.LITEXTRACT_TEST_EXECUTABLE,
    env,
  })
  let closed = false
  try {
    const page = await app.firstWindow()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await expect(page.getByTestId('connection-state')).toHaveText('工作台已就绪')
    await expect(page.getByText('SQLite · WAL', { exact: false })).toBeVisible()
    await expect(page.getByRole('region', { name: '首次使用向导' })).toContainText(
      '1. 选择文献文件夹',
    )
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await expect(page.getByRole('region', { name: '首次使用向导' })).toContainText(
      '2. 解析并查看原文',
    )
    expect(
      await page.evaluate(() => typeof (window as unknown as { require?: unknown }).require),
    ).toBe('undefined')
    expect(await page.evaluate(() => Object.keys(window.litextract ?? {}))).toEqual([
      'health',
      'chooseFolder',
      'request',
      'watchJob',
    ])
    await page.getByRole('button', { name: '重新检查' }).click()
    await expect(page.getByTestId('connection-state')).toHaveText('工作台已就绪')
    await page.screenshot({ path: 'test-results/workbench.png', fullPage: true })
    expect(errors).toEqual([])
    await app.close()
    closed = true
    // A leaked Python process holds its SQLite files open on Windows.
    await rm(workspace, { recursive: true, force: true, maxRetries: 3 })
  } finally {
    if (!closed) await app.close()
    await rm(workspace, { recursive: true, force: true, maxRetries: 3 })
  }
})
