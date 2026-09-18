# 12-ladderbill（阶梯电费）

Ladderbill — 居民阶梯电价分段累进（含尖峰系数）

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |

## 主链

抄表录入 → 阶梯分段计费 → 账单明细

## 年度档位进度冻结

按户按自然年累计已落库（`kind='bill'`）测算的净电量；冻结后本年内后续测算的阶梯累进以上一冻结点为起点，解冻则恢复按运行实时累计，冻结点记录长期可查。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/accounts/{id}/annual?year=` | 年累计净电量、冻结态、当前分段起点、冻结点历史 |
| POST | `/api/accounts/{id}/freeze` | 写入冻结点（电量+时间）；同户同年旧冻结点自动失效 |
| POST | `/api/accounts/{id}/unfreeze` | 解冻，恢复实时累计（无生效冻结点返回 409） |
| GET | `/api/accounts/{id}/annual/verify` | 重算校验：累计值 vs 运行明细逐笔合计 |
| POST | `/api/bill` | 带 `account_id` 时回包含 `base_kwh` 与 `annual`（年累计/冻结点/本段新增） |

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。
