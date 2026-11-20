# WBS

格式与 `course-reservation/docs/WBS/` 一致：一个阶段一个文件 `P<n>.<名称>.md`，
任务行带 `[type:: task] [EST:: x🍅] [ID:: P<n>-<m>-<kk>]`，可被 vault 的
`scripts/project-wbs/task-tree.js` 直接渲染（挂载后 `scanPath: git-docs/WBS`）。

- 编号：`P<n>` 阶段 / `P<n>-<m>` 里程碑 / `P<n>-<m>-<kk>` 任务
- 估时单位：番茄（🍅 ≈ 25 分钟）
- 每个任务必须有一个可执行的验收动作
