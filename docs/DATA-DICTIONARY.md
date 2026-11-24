# 字段与业务定义

输入编码 UTF-8，允许 BOM。首行必须匹配样例列顺序。记录键和业务组保留原始字符串。`kind` 允许 stay, pause, invoice。说明列 `note` 可以跨行，限制 200 字。

业务字段按 `start_min`、`end_min`、`free_min`、`amount_cents` 排列。数字接受非负整数、全角数字和完整千分位。空串、短横线、N/A、NULL 与未知为缺值。无关字段用 0 占位。

停时按左闭右开分钟段记录。先剪裁并合并暂停时段，再扣除免计分钟。前 60 分钟每分 1 分钱，后 60 分钟每分 3 分钱，余下每分 5 分钱。

`incoming.csv` 包含四个业务组，第二组提供不同边界，第三组触发业务拒收，第四组需要核对。另含重复表头、冲突记录、重复回放与错误列数。`ready.csv` 含可以签发的两个组。

## 费率表 JSON

费率更正使用独立的费率表（`sample_data/rate_*.json` 或工作台上传）。顶层字段为 `code`、`version`、`periods[]`；`periods[]` 按分钟轴给出 `start_min`、`end_min`（末区间 `null` 表示开放）和 `tiers[]`，档位含 `width_min`（开放档为 `null`）与 `rate_cents`（分/分钟，非负整数）。区间重叠或乱序、缺开放档、非法费率在解析阶段拒收；覆盖缺口允许登记但在计费阶段以 `RATE_INTERVAL_MISSING` 挡签。更正账单的分段字段（`key`、`minutes`、`rate_cents`、`amount_cents`）与挡签原因见 [费率更正](CORRECTION.md)。
