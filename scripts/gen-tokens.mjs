#!/usr/bin/env node
/** tokens.json -> src/styles/tokens.css（色值只允许从这里来） */
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const tokens = JSON.parse(readFileSync(resolve(HERE, '../docs/design/tokens.json'), 'utf8'))
const out = resolve(HERE, '../code/web/src/styles/tokens.css')

const lines = ['/* 由 scripts/gen-tokens.mjs 从 docs/design/tokens.json 生成，别手改 */', ':root {']
for (const [k, v] of Object.entries(tokens.color)) lines.push(`  --c-${k}: ${v};`)
for (const [k, v] of Object.entries(tokens.font.sizes)) lines.push(`  --fs-${k}: ${v}px;`)
for (const [k, v] of Object.entries(tokens.radius)) lines.push(`  --r-${k}: ${v}px;`)
for (const [k, v] of Object.entries(tokens.grid)) lines.push(`  --g-${k}: ${v}px;`)
lines.push(`  --font: '${tokens.font.family}', system-ui, sans-serif;`, '}')
writeFileSync(out, lines.join('\n') + '\n')
console.log(`✓ ${out}  (${Object.keys(tokens.color).length} 个颜色)`)
