# RetailGuard 智能售后系统 Makefile
# 用法：make <target>

.PHONY: help install test eval eval-smoke eval-report langfuse up down logs clean

PYTHON := python
PYTEST := $(PYTHON) -m pytest
EVAL   := $(PYTHON) -m eval.runner

help:
	@echo "RetailGuard 开发工具"
	@echo ""
	@echo "  make install        安装 Python 依赖"
	@echo "  make test           运行单元测试（11 条）"
	@echo "  make eval           全量评测（200 条）"
	@echo "  make eval-ab        三版本 A/B 对比评测"
	@echo "  make eval-smoke     快速 smoke 评测（10 条/数据集）"
	@echo "  make eval-report    全量评测 + 生成 Markdown + 图表"
	@echo "  make langfuse       在浏览器打开 Langfuse（需先 make up）"
	@echo "  make up             启动全部 docker-compose 服务"
	@echo "  make down           停止 docker-compose 服务"
	@echo "  make logs           查看 python-agent 日志"
	@echo "  make clean          清理 __pycache__ 和 .pytest_cache"

install:
	cd python-impl && pip install -r requirements.txt

test:
	cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true \
		$(PYTEST) tests/ -x -q --tb=short

eval:
	cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true \
		$(EVAL) --dataset all

eval-smoke:
	cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true \
		$(EVAL) --smoke

eval-report:
	cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true \
		$(EVAL) --dataset all \
		--output docs/eval_reports/eval_latest.json \
		--report

eval-ab:
	cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true \
		$(EVAL) --dataset all --smoke --version v1,v2,v3 --report

langfuse:
	@echo "Opening Langfuse at http://localhost:3000 ..."
	@open http://localhost:3000 2>/dev/null || start http://localhost:3000 2>/dev/null || \
		echo "Please open http://localhost:3000 in your browser"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f python-agent

clean:
	find python-impl -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find python-impl -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	@echo "Clean done."
