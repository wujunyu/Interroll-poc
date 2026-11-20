# RB-04 把 docs 挂进 Obsidian（后期，需 sudo）

> vault 一个字节都不改：仓库仍是唯一真源，Obsidian 只是**只读视图 + 双链**。

## 为什么挂到 git-docs

vault 的 git 根是 `个人笔记/` 的上一级，每天 03:30 有 `vault-git-sync.sh` 跑 `git add -A`。
它的 `.gitignore` 里已经有 `git-docs`（无斜杠，任意层级匹配），所以挂到这里**不会**被误提交进笔记历史。

## 命令

```bash
sudo mkdir -p "/mnt/disk1t/dockerVolumes/obsidian/个人笔记/git-docs"
sudo mount --bind /mnt/disk1t/workspacePersonal/Interroll-poc/docs \
                "/mnt/disk1t/dockerVolumes/obsidian/个人笔记/git-docs/interroll-poc"
```

重启后失效；持久化写进 `/etc/fstab`：

```
/mnt/disk1t/workspacePersonal/Interroll-poc/docs /mnt/disk1t/dockerVolumes/obsidian/个人笔记/git-docs/interroll-poc none bind 0 0
```

不想动 sudo 就 `ln -s`（移动端同步会断）。

## 挂完必须核对

```bash
cd /mnt/disk1t/dockerVolumes/obsidian && git status --short   # 应该一行都不多
```

## 命名约束（挂进去之后才成立的规矩）

- 文件名全局唯一并带前缀：`C-` / `MOC-` / `SRC-` / `OUT-` / `ADR-` / `RB-`；
- 不用 `README.md`、`index.md` 这类通用名（Obsidian 里重名解析会歧义）；
- 双链只按 basename 写 `[[C-RENDER-002]]`，不写相对路径。
