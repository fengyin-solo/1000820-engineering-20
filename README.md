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
│   └── app/store.py          内存数据仓库（seed.py 为生成产物，勿手改）
├── scripts/                  提交前自检流水线（数据生成、接口自检、前端构建）
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

## 提交前自检流水线

一条命令把「箱区样板数据生成 → 后端接口自检 → 前端构建打包」跑完，并给出这次能不能提交的结论：

```bash
make check
```

三步各自做什么：

1. **样板数据生成（数据步）**：`backend/app/seed.py` 不再手工维护，由
   `scripts/seed_spec.py`（声明式规格）结合各 service/router 的字段与状态定义，
   通过 `scripts/generate_seed.py` 确定性生成并自校验；要改样板内容改规格再重跑。
2. **后端接口自检（构建步）**：`scripts/check_backend.py` 起一个临时 uvicorn
   （随机端口、跑完即停），对 18 个模块的列表、明细、404、创建、缺字段拦截、
   动作状态流转、导出逐一打真实 HTTP 请求。
3. **前端构建打包（构建步）**：先清掉上一次的 `dist`，再跑 `npm run build`
   （含 vue-tsc 类型检查）。

失败时结论会写明是**数据问题**还是**构建问题**，日志在 `.pipeline/<步骤>.log`，
并提示只重跑那一步的命令：

```bash
make check-seed       # 只重跑样板数据生成
make check-backend    # 只重跑后端接口自检
make check-frontend   # 只重跑前端构建
```

每一步开跑前都会先清掉自己上一次的中间产物（数据临时文件、前端 `dist`），
整条流水线的工作目录 `.pipeline/` 每次运行整体重建，成功后自动删除；
失败时保留日志用于定位。环境依赖没装时会提示先跑 `make install`。

上面的手工启动方式（`backend/run.sh`、`npm run dev`、`make backend`、`make frontend`）
照旧可用，流水线不影响日常起服务。


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
