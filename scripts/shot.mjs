#!/usr/bin/env node
/** 真实等待后截图（SPA + WebSocket 需要真时间，headless 的 virtual-time 会截到空图）
 *  用法：node scripts/shot.mjs <url> <out.png> [waitMs] [w] [h]
 */
import { createRequire } from 'node:module'
const require = createRequire('/mnt/disk1t/workspacePersonal/course-reservation/package.json')
const puppeteer = require('puppeteer')

const [url, out, waitMs = '8000', w = '1440', h = '900'] = process.argv.slice(2)
const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: Number(w), height: Number(h) })
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
await new Promise((r) => setTimeout(r, Number(waitMs)))
await page.screenshot({ path: out })
console.log(`✓ ${out}`)
await browser.close()
