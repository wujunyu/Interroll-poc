#!/usr/bin/env node
/**
 * P9-3 前端背压实测：打开看板，采样 5 秒
 *  - fps：requestAnimationFrame 计数
 *  - ws_frames：注入 WebSocket 钩子统计收到的帧
 *  - long_tasks：>50ms 的任务数（卡顿）
 * 用法：node scripts/bench_ui.mjs [url] [seconds]
 */
import { createRequire } from 'node:module'
const require = createRequire('/mnt/disk1t/workspacePersonal/course-reservation/package.json')
const puppeteer = require('puppeteer')

const url = process.argv[2] || 'http://127.0.0.1:5174/'
const seconds = Number(process.argv[3] || 8)

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--disable-gpu'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 900 })

// 在页面脚本执行前挂钩 WebSocket / rAF
await page.evaluateOnNewDocument(() => {
  window.__wsFrames = 0
  const Orig = window.WebSocket
  window.WebSocket = function (...args) {
    const ws = new Orig(...args)
    ws.addEventListener('message', () => { window.__wsFrames++ })
    return ws
  }
  window.WebSocket.prototype = Orig.prototype
  window.__fps = 0
  let frames = 0
  let last = performance.now()
  window.__long = 0
  new PerformanceObserver((l) => { window.__long += l.getEntries().length })
    .observe({ entryTypes: ['longtask'] })
  function loop(now) {
    frames++
    if (now - last >= 1000) { window.__fps = frames; frames = 0; last = now }
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
})

const cdp = await page.target().createCDPSession()
await cdp.send('Network.enable')
let wsFrames = 0
cdp.on('Network.webSocketFrameReceived', () => { wsFrames++ })
cdp.on('Network.webSocketCreated', (e) => console.error('[ws] created', e.url))
cdp.on('Network.webSocketClosed', (e) => console.error('[ws] closed'))
page.on('console', (m) => { if (m.type() === 'error') console.error('[console]', m.text()) })

await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 3000))   // 预热
wsFrames = 0
await page.evaluate(() => { window.__long = 0 })

const samples = []
for (let i = 0; i < seconds; i++) {
  await new Promise((r) => setTimeout(r, 1000))
  samples.push({ fps: await page.evaluate(() => window.__fps), frames: wsFrames })
}
const long = await page.evaluate(() => window.__long)
const fpsValues = samples.map((s) => s.fps).filter((v) => v > 0)
const avg = fpsValues.reduce((a, b) => a + b, 0) / Math.max(fpsValues.length, 1)
const min = Math.min(...fpsValues)
const wsTotal = samples.at(-1)?.frames ?? 0

console.log(JSON.stringify({
  url, seconds,
  fps_avg: Number(avg.toFixed(1)),
  fps_min: min,
  ws_frames: wsTotal,
  ws_fps: Number((wsTotal / seconds).toFixed(1)),
  long_tasks: long,
}, null, 0))
await browser.close()
