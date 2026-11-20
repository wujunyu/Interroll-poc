#!/usr/bin/env node
/**
 * 把本地 .drawio 渲染成 PNG（手机看 / 贴文档）。
 * drawio 的 ?url= 在自建实例里不生效，改用官方的 #R 内联格式：
 *   #R + base64( deflateRaw( encodeURIComponent(xml) ) )
 * 用法：node scripts/shot_drawio.mjs <file.drawio> <out.png> [宽] [高]
 */
import { readFileSync } from 'node:fs'
import { deflateRawSync } from 'node:zlib'
import { createRequire } from 'node:module'

const require = createRequire('/mnt/disk1t/workspacePersonal/course-reservation/package.json')
const puppeteer = require('puppeteer')

const [file, out, w = '1600', h = '1000'] = process.argv.slice(2)
const xml = readFileSync(file, 'utf8')
const payload = encodeURIComponent(xml)
const b64 = deflateRawSync(Buffer.from(payload, 'utf8'), { level: 9 }).toString('base64')
const base = process.env.DRAWIO_BASE || 'https://192.168.1.200:3024'
const url = `${base}/?pv=0&grid=0&nav=0&chrome=0#R${b64}`

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--disable-gpu', '--ignore-certificate-errors'],
})
const page = await browser.newPage()
await page.setIgnoreHTTPSErrors?.(true)
await page.setViewport({ width: Number(w), height: Number(h), deviceScaleFactor: 2 })
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
await new Promise((r) => setTimeout(r, 8000))
await page.screenshot({ path: out })
console.log(`✓ ${out}  (${(xml.length / 1024).toFixed(1)}KB XML)`)
await browser.close()
