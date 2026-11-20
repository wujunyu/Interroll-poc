# 知识库健康度（Dataview 看板）

> 挂进 Obsidian 后自动可用；命令行自检见 `_契约/SCHEMA.md` 第五节。

## 未验证的卡

```dataview
TABLE confidence, verified, source
FROM "docs/kb/1-卡"
WHERE confidence = "待确认" OR !source
SORT file.mtime DESC
```

## 最近新增

```dataview
LIST FROM "docs/kb/1-卡" SORT file.ctime DESC LIMIT 10
```

## 缺口

- 还没有卡：B 批跑通后从「实测数据」开始写。
