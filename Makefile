# 一把梭：make demo   → 跑通最小闭环（跑用例 + 出报告 + 看归因）
PY ?= python

.PHONY: help install demo suite lint triage serve test-platform clean

help:
	@echo "install       安装依赖 + 下载 chromium"
	@echo "demo          跑一遍最小闭环：全量用例 → 报告 → 归因"
	@echo "suite         只跑测试（pytest 直出，不经过平台）"
	@echo "lint          检查 PO 分层纪律"
	@echo "triage        归因最近一次运行"
	@echo "serve         启动平台服务（http://127.0.0.1:8077）"
	@echo "test-platform 跑平台自身单测"

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m playwright install chromium

demo:
	$(PY) -m atp run --all --triage

suite:
	$(PY) -m pytest tests -v

lint:
	$(PY) -m atp lint

triage:
	$(PY) -m atp triage

serve:
	$(PY) -m atp serve

test-platform:
	$(PY) -m pytest platform_tests -v

clean:
	rm -rf artifacts reports allure-results .pytest_cache