import { _electron as electron } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve, join } from 'node:path'

const output = resolve('.local/real-literature-acceptance')
await mkdir(output, { recursive: true })
const env = { ...process.env, LITEXTRACT_DATA_DIR: join(output, 'data') }
delete env.ELECTRON_RUN_AS_NODE
const app = await electron.launch({
  executablePath: resolve('.local/installed-beta/LitExtract v2.exe'),
  args: [],
  env,
})
const report = { started: new Date().toISOString(), projects: [], files: [], errors: [] }
const checkpoint = () => writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2))
app.process().stderr.on('data', (chunk) => {
  if (/error|failed/i.test(chunk.toString())) console.log(chunk.toString().slice(0, 600))
})
try {
  const page = await app.firstWindow()
  const request = (value) => page.evaluate((value) => window.litextract.request(value), value)
  for (const [name, source, count] of [
    ['真实单篇验收', 'D:/literature-test/single-paper', 1],
    ['真实批量验收', 'D:/literature-test/batch', 12],
  ]) {
    const existing = await request({ action: 'projects' })
    const project =
      existing.find((item) => item.name === name) ??
      (await request({ action: 'createProject', name, source_path: source }))
    const draft = await request({ action: 'scan', projectId: project.id })
    const documents = await request({
      action: 'confirmScan',
      projectId: project.id,
      draft_id: draft.id,
      groups: draft.snapshot.groups.map(({ title, main_path, asset_paths }) => ({
        title,
        main_path,
        asset_paths,
      })),
    })
    report.projects.push({
      name,
      id: project.id,
      expected_documents: count,
      actual_documents: documents.length,
      groups: draft.snapshot.groups,
    })
    if (documents.length !== count)
      report.errors.push(`${name}: expected ${count} groups, got ${documents.length}`)
    await checkpoint()
    console.log(`${name}: ${documents.length} documents`)
    for (const document of documents)
      for (const asset of document.assets) {
        const started = Date.now()
        const entry = {
          project: name,
          document: document.title,
          path: asset.absolute_path,
          role: asset.role,
          asset_id: asset.id,
        }
        report.files.push(entry)
        const hash = (data) => createHash('sha256').update(data).digest('hex')
        entry.sha256 = hash(await readFile(asset.absolute_path))
        try {
          await request({
            action: 'parseAsset',
            projectId: project.id,
            assetId: asset.id,
            ocr: false,
            force: false,
          })
          let status
          do {
            await new Promise((done) => setTimeout(done, 2000))
            status = await request({
              action: 'parseStatus',
              projectId: project.id,
              assetId: asset.id,
            })
            if (Date.now() - started > 900000) throw Error('Parse exceeded 15 minutes')
          } while (['queued', 'running'].includes(status.status))
          entry.status = status.status
          entry.error = status.error
          if (status.status === 'ready') {
            const content = await request({
              action: 'parsedContent',
              projectId: project.id,
              assetId: asset.id,
            })
            await writeFile(join(output, `${asset.id}.json`), JSON.stringify(content))
            entry.pages = content.pages.length
            entry.blocks = content.blocks.length
            entry.tables = content.blocks.filter((block) => block.kind === 'table').length
            entry.located_blocks = content.blocks.filter((block) => block.locations.length).length
            entry.characters = content.blocks.reduce((n, block) => n + block.text.length, 0)
            entry.warnings = content.warnings
            entry.sample = content.blocks
              .filter((block) => block.text)
              .slice(0, 4)
              .map((block) => block.text.slice(0, 500))
            if (!entry.characters)
              report.errors.push(`${asset.relative_path}: empty parsed content`)
          } else report.errors.push(`${asset.relative_path}: ${status.status} ${status.error}`)
        } catch (error) {
          entry.error = String(error)
          report.errors.push(`${asset.relative_path}: ${error}`)
        }
        entry.source_unchanged = entry.sha256 === hash(await readFile(asset.absolute_path))
        entry.seconds = Math.round((Date.now() - started) / 1000)
        console.log(JSON.stringify(entry))
        await checkpoint()
      }
  }
  await page.reload()
  await page.screenshot({ path: join(output, 'workspace.png'), fullPage: true })
} finally {
  report.finished = new Date().toISOString()
  await checkpoint()
  await app.close()
}
