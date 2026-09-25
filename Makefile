.PHONY: install backend frontend check check-seed check-backend check-frontend clean-check

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# 提交前自检：样板数据生成 -> 后端接口自检 -> 前端构建打包，跑完给能否提交的结论。
check:
	bash scripts/pipeline.sh all

# 只重跑某一步；每步开跑前会先清自己上一次的中间产物。
check-seed:
	bash scripts/pipeline.sh seed

check-backend:
	bash scripts/pipeline.sh backend

check-frontend:
	bash scripts/pipeline.sh frontend

# 清掉流水线的中间产物（前端 dist 由 check-frontend 自行清理，这里只清流水线工作目录）。
clean-check:
	rm -rf .pipeline
