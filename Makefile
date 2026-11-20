SHELL := /bin/bash
COMPOSE := docker compose --env-file .env -f deploy/compose/compose.yaml

.DEFAULT_GOAL := help
.PHONY: help env config up-infra up down logs ps demo demo-offline verify diag backup rollback clean

help: ## 列出所有目标
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: .env ## 确保 .env 存在
.env:
	@cp .env.example .env && echo "· 已从 .env.example 生成 .env（记得改 DB_PASSWORD）"

config: .env ## 校验 compose 与变量（不启动）
	$(COMPOSE) config -q && echo "✓ compose 校验通过"

up-infra: .env ## 只起 mqtt + db（骨架期可用）
	$(COMPOSE) up -d mqtt db

up: .env ## 起全栈（B 批完成后可用）
	$(COMPOSE) up -d --build

down: ## 停栈，保留数据卷
	$(COMPOSE) down

logs: ## 跟随日志
	$(COMPOSE) logs -f --tail=100

ps: ## 容器状态
	$(COMPOSE) ps

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
