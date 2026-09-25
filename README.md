# 港口集装箱作业调度平台

面向船舶靠泊、集装箱装卸、堆场堆存、闸口进出与理货结算的一体化港口作业调度后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 提交前一键自检

新人不必再分别问「箱区数据怎么造、接口怎么验、前端怎么打包」：一条命令按
固定口径跑完三步，并直接给出**这次能不能提交**的结论。

```bash
make verify          # 顺序跑：箱区样板数据 -> 后端接口自检 -> 前端构建
```

三步各自做什么：

| 步骤 | 脚本 | 做的事 | 产物 |
| --- | --- | --- | --- |
| 箱区样板数据 | `ci/gen_yard_data.py` | 按固定口径确定性生成箱区清单，写出前逐条校验编号、容量、状态覆盖等规则 | `.ci-work/data/yard.json` |
| 后端接口自检 | `ci/check_backend.py` | 用样板数据起临时 uvicorn，打健康检查、18 个模块列表接口、箱区动作流转（启用→封闭→腾空），并核对接口数据与样板逐条一致 | `.ci-work/reports/backend-selfcheck.log` |
| 前端构建 | `ci/build_frontend.sh` | 确认依赖可用后清掉旧产物，跑 `vue-tsc` 类型检查 + `vite build` | `frontend/dist/` |

跑完最后一行就是结论：`✓ 三步全部通过……本次可以提交`，或
`✗ 本次不能提交 —— 数据问题/构建问题/环境问题`。

哪一步失败就只重跑哪一步（每步开跑前都会先清掉自己上一次的产物，不残留中间结果）：

```bash
make verify-data       # 只重跑箱区样板数据
make verify-backend    # 只重跑后端接口自检
make verify-frontend   # 只重跑前端构建
make verify-clean      # 清掉全部中间产物（.ci-work/ 与 frontend/dist/）
```

问题分类（对应退出码，CI 里可直接判断）：

- **数据问题（2）**：样板不合口径，或接口返回与样板对不上；
- **构建问题（3）**：后端代码/接口报错、动作流转不对，或前端类型检查、打包失败；
- **环境问题（4）**：venv 失效、依赖装不上、服务起不来。脚本会尝试自动重建
  `backend/.venv` 与 `frontend/node_modules`（含换平台后原生二进制不匹配的情况）。

说明：自检只通过环境变量 `YARD_SEED_FILE` 让后端临时加载生成的箱区数据；
不设置该变量时后端行为与以前完全一致，**上面的手工启动方式照旧**。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 泊位计划 | `berth` | 泊位计划 | 计划编号、泊位编号、靠泊船舶 |
| 船舶档案 | `vessel` | 船舶 | 船舶编号、船舶名称、船舶类型 |
| 航次管理 | `voyage` | 航次 | 航次编号、关联船舶、进口航次号 |
| 岸桥作业 | `crane` | 岸桥 | 设备编号、岸桥型号、额定起重量 |
| 装卸任务 | `loading` | 装卸任务 | 任务编号、关联航次、作业类型 |
| 堆场管理 | `yard` | 箱区 | 箱区编号、箱区名称、堆放层数 |
| 集装箱档案 | `container` | 集装箱 | 箱号、箱型、箱况等级 |
| 堆存记录 | `yardstore` | 堆存单 | 堆存单号、关联箱号、箱区编号 |
| 闸口通行 | `gate` | 通行记录 | 通行编号、车牌号码、关联箱号 |
| 集卡调度 | `truck` | 集卡 | 调度单号、集卡牌号、司机姓名 |
| 理货作业 | `tally` | 理货单 | 理货单号、关联航次、理货方式 |
| 残损登记 | `damage` | 残损记录 | 残损编号、关联箱号、残损类型 |
| 单证处理 | `manifest` | 单证 | 单证编号、单证类型、关联航次 |
| 堆存计费 | `storage` | 计费单 | 计费单号、关联箱号、计费周期 |
| 引航拖轮 | `pilot` | 引航作业 | 作业编号、作业类型、关联船舶 |
| 安全监督 | `safety` | 安全检查 | 检查编号、检查区域、检查类型 |
| 货主档案 | `customer` | 货主 | 客户编码、客户名称、客户类型 |
| 作业结算 | `settle` | 结算单 | 结算单号、结算对象、结算周期 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
