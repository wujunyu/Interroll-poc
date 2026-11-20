# RB-04 把 docs 挂进 Obsidian（已落地，走 Ignis 容器 volume）

> 结论先说：**不用宿主机 bind mount，也不用软链**。Obsidian 跑在 `ignis` 容器里，
> 直接把仓库 `docs/` 作为 volume 挂到 vault 内的 `git-docs` 即可。

## 一、现状

| 项 | 值 |
|---|---|
| 仓库 docs | `/mnt/disk1t/workspacePersonal/Interroll-poc/docs` |
| 容器内目标 | `/vaults/个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs` |
| 宿主机实际路径 | `/mnt/disk1t/dockerVolumes/obsidian/个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs` |
| vault 入口页 | `开发-英特诺POC/开发-英特诺POC.md`（含 WBS 任务树） |
| 配置文件 | `/mnt/disk3/dockerVolumes/dockerDockman/stacks/Ignis/Ignis-compose.yaml` |

## 二、为什么挂 `git-docs` 而不是别的名字

1. vault 的 `.gitignore` 有一条 `git-docs`（无斜杠，任意层级匹配）→ 挂进来的
   仓库文档**不会**被 03:30 的 `vault-git-sync.sh` 提交进笔记历史；
2. 现有四个开发项目（约课小程序 / WPF 上位机 / 麻将伴侣 / ABP 改造）全用这个约定，
   WBS 索引页的 `scanPath: "git-docs/WBS"` 因此可以直接复用。

## 三、加一个项目（照抄这段）

```yaml
      # 代码仓库 docs -> vault 内 git-docs（真实目录：规避 Ignis 软链接守卫 + readdir 类型判定）
      - /mnt/disk1t/workspacePersonal/Interroll-poc/docs:/vaults/个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs
```

先在宿主机建好目标目录（否则 docker 会以 root 创建，属主不对）：

```bash
mkdir -p "/mnt/disk1t/dockerVolumes/obsidian/个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs"
```

再重建容器（**注意文件名不是 `compose.yaml`**）：

```bash
cd /mnt/disk3/dockerVolumes/dockerDockman/stacks/Ignis
docker compose -f Ignis-compose.yaml up -d --pull never
```

## 四、验证四条

```bash
docker inspect ignis --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' | grep 开发-英特诺POC
docker exec ignis ls "/vaults/个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs"
cd /mnt/disk1t/dockerVolumes/obsidian && git status --short | grep 开发-英特诺POC   # 只应有入口页，无 git-docs
git -C /mnt/disk1t/dockerVolumes/obsidian check-ignore -v "个人笔记/0.年度日记本/PARA/1.Project/开发-英特诺POC/git-docs"
```

前两条能列出 `adr/ kb/ WBS/` 等目录即通；第三条只出现 `.md` 入口页即正确。

## 五、两个坑

1. **compose 文件属主是 `nobody:nogroup`**，`vincent` 无写权限，`sudo` 在本机不可用
   （`/etc/sudo.conf` 属主不是 root）。改法：用一次性 root 容器写回，写完 `chown 1000:1000`。
2. **别用符号链接**。Ignis 有软链守卫 + `readdir` 类型判定，软链进去的项目在 Obsidian 里看不到。

## 六、改动历史

| 日期 | 动作 |
|---|---|
| 2026-11-20 | 新建 vault 项目 `开发-英特诺POC`，把 `Interroll-poc/docs` 挂到其 `git-docs`；重建 ignis 容器 |
