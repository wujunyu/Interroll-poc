SHELL := /bin/bash
COMPOSE := docker compose --env-file .env -f deploy/compose/compose.yaml

.DEFAULT_GOAL := help
.PHONY: help env config up-infra up down logs ps sim qos-lab demo demo-offline verify diag backup rollback clean

help: ## 列出所有目标
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: .env ## 确保 .env 存在
.env:
	@cp .env.example .env && echo "· 已从 .env.example 生成 .env（记得改 DB_PASSWORD）"

config: .env ## 校验 compose 与变量（不启动）
	$(COMPOSE) config -q && echo "✓ compose 校验通过"

up-infra: .env ## 只起 mqtt + db（骨架期可用）
	$(COMPOSE) up -d mqtt db

up: .env ## 起全栈（用已构建好的镜像，不现场 build）
	$(COMPOSE) up -d

down: ## 停栈，保留数据卷
	$(COMPOSE) down

logs: ## 跟随日志
	$(COMPOSE) logs -f --tail=100

ps: ## 容器状态
	$(COMPOSE) ps

web: ## 前端开发服务器（5174，需先起 ingest/api）
	cd code/web && npm run dev

tokens: ## 设计色板 -> CSS 变量
	node scripts/gen-tokens.mjs

images: ## 用 podman 构建四个镜像（需在宿主机执行，见脚本）
	bash deploy/scripts/build-images.sh

sim: ## 10Hz 造数 10 秒（QoS1）
	.conda-env/bin/python code/simulator/main.py --duration 10 --qos 1

qos-lab: ## QoS 0/1/2 故障注入实验（先 make up-infra）
	@for cfg in "0 0" "1 1" "2 2" "2 0"; do set -- $$cfg; \
		.conda-env/bin/python code/simulator/qos_lab.py --qos $$1 --sub-qos $$2 \
			--count 300 --rate 100 --offline-at 1.0 --offline-for 1.5 --drain 4.0 2>/dev/null | grep '^RESULT'; \
	done

demo: ## 走一遍演示脚本（B 批）
	@echo "TODO(B 批): 起栈 → 看板出曲线 → 打印验收点"

demo-offline: ## 断网演练（B 批）
	@echo "TODO(B 批): 断网 60s → 恢复 → 断言零丢点"

verify: config ## 验收：compose + 脚本语法
	@bash -n deploy/scripts/*.sh && echo "✓ shell 语法通过"
	@python3 -m compileall -q code >/dev/null && echo "✓ python 语法通过"
	@echo "✓ verify 通过（B 批将追加单元测试与 smoke）"

diag: ## 导出诊断包（B 批）
	@echo "TODO(B 批): 收集 system/config/logs/mqtt-tail/db-stats → dist/diag-<ts>.zip"

backup: ## 备份数据卷
	@bash deploy/scripts/backup.sh

rollback: ## 回滚到指定 TAG（默认上一版）
	@bash deploy/scripts/rollback.sh $(TAG)

clean: ## 停栈并删卷（会丢数据）
	$(COMPOSE) down -v
