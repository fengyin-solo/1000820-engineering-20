.PHONY: install backend frontend verify verify-data verify-backend verify-frontend verify-clean

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# 手工启动方式照旧，不受流水线影响
backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# ===== 提交前一键自检流水线 =====
# 顺序：箱区样板数据 -> 后端接口自检 -> 前端构建，跑完给出能否提交的结论
verify:
	bash ci/pipeline.sh

# 只重跑某一步（会先清掉该步上一次的中间产物）
verify-data:
	bash ci/pipeline.sh data

verify-backend:
	bash ci/pipeline.sh backend

verify-frontend:
	bash ci/pipeline.sh frontend

# 清理流水线全部中间产物（.ci-work/ 与 frontend/dist/）
verify-clean:
	bash ci/pipeline.sh clean
