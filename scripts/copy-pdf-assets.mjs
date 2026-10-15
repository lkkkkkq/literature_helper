import { cp, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

for (const folder of ['cmaps', 'standard_fonts', 'wasm']) {
  const target = resolve('frontend/public/pdfjs', folder)
  await mkdir(target, { recursive: true })
  await cp(resolve('node_modules/pdfjs-dist', folder), target, { recursive: true })
}
