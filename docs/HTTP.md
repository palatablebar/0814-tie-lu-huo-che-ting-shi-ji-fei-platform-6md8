# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据和复核信息的 JSON。

## 费率更正

`POST /api/corrections/preview` 接收同样的来源输入，另带 `rate_profile`
（`legacy`、`corrected`、`gapped`）或 `rate_file=<JSON>` 二选一；缺省按
历史费率。预览不入库，返回按费率区间拆分的 `segments`、`schedule` 指纹与
`balance.block_reasons`。

`POST /api/runs` 增加表单字段 `kind=correction` 即登记更正批次，费率表
字段同上。运行编号绑定数据源与费率表指纹，同源重跑返回原批次，不同费率表
生成独立批次。更正批次报告额外含 `schedule` 与 `lineage`（同数据源历史批次
的原费率金额与差额）。证据包在更正批次下使用 `review-evidence/2`。

详见 [费率更正](CORRECTION.md)。
