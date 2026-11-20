#!/usr/bin/env node
/** spec -> 本地 PNG 目检（Chrome headless，不需要 puppeteer） */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const specPath = process.argv[2] || resolve(HERE, 'screens/poc-dashboard.json')
const outDir = resolve(HERE, 'exports')
mkdirSync(outDir, { recursive: true })
const spec = JSON.parse(readFileSync(specPath, 'utf8'))
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const render = (b) => {
  const kids = b.children.map((c) => {
    if (c.k === 'rect') {
      const stroke = c.strokeColor ? `box-shadow:inset 0 0 0 ${c.strokeWidth || 1}px ${c.strokeColor};` : ''
      const op = c.opacity === undefined ? 1 : c.opacity
      return `<div style="position:absolute;left:${c.x}px;top:${c.y}px;width:${c.w}px;height:${c.h}px;background:${c.fill || 'transparent'};border-radius:${c.r || 0}px;opacity:${op};${stroke}"></div>`
    }
    const w = c.w ? `width:${c.w}px;` : 'white-space:pre;'
    return `<div style="position:absolute;left:${c.x}px;top:${c.y}px;${w}font-size:${c.size || 14}px;line-height:1.4;font-weight:${c.weight || 400};color:${c.color || '#fff'};text-align:${c.align || 'left'};letter-spacing:0;font-family:'Noto Sans SC','PingFang SC',system-ui,sans-serif;">${esc(c.s)}</div>`
  }).join('')
  return `<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;width:${b.w}px;height:${b.h}px;background:${b.fill};position:relative;overflow:hidden">${kids}</body></html>`
}

let i = 0
for (const b of spec.boards) {
  i += 1
  const no = String(i).padStart(2, '0')
  const html = resolve(outDir, `.preview-${no}.html`)
  const png = resolve(outDir, `${no}-${(b.name.split('#')[1] || 'board')}.png`)
  writeFileSync(html, render(b))
  execFileSync('google-chrome', [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--force-device-scale-factor=1', `--window-size=${b.w},${b.h}`,
    `--screenshot=${png}`, `file://${html}`,
  ], { stdio: 'pipe' })
  console.log(`✓ ${png}  ${b.w}x${b.h}`)
}
