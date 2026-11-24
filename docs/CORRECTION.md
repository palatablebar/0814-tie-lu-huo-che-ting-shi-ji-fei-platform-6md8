# 费率更正与可签账单

费率更正回溯到月初重算。已签发批次原样保留用于追责，更正运行生成按实际
计费区间拆分的新账单；更正不影响已签单据，原结果保留原费率，差额可追溯。

## 不可变与版本

- 运行编号 = 哈希（规则版本 + 数据源指纹 + 费率表指纹）。同源数据配合不同
  费率表必然产生不同编号，已存在的批次原样返回，**同源重跑不覆盖旧版、不
  丢失记录、金额一致**。
- 历史批次 `manifest.kind = LEGACY`，沿用规则 `1.0.0` 与原报告结构；更正
  批次 `manifest.kind = CORRECTION`，规则版本 `2.0.0`，并携带
  `schedule_fingerprint`。
- 更正报告的 `lineage.prior_runs` 列出同数据源的全部历史批次，按业务组记录
  `prior_cents`、`corrected_cents` 与 `delta_cents`，已签批次的状态一并保留。

## 计费拆分规则

分钟段均为左闭右开。

1. 暂停段先剪裁到停时区间再合并；暂停与停时交叠部分只扣一次，暂停之间的
   重叠合并后不重复扣除。
2. 免计分钟是整笔停时的额度，**跨费率区间只使用一次且不随费段重置**，从
   第一个计费分钟起顺序冲抵，扣完为止。
3. 剩余计费分钟按费率表生效区间（period）与区间内档位（tier）切分。每个
   分段 `segments[]` 记录：`key`、`start_min/end_min`、`minutes`、
   `rate_cents`、`amount_cents`，金额 = 分钟 × 费率。
4. 分段金额之和等于账单总额 `amount_cents`。

## 挡签（必须并列记录）

出现下列任一情况，分组状态为 `BLOCKED`，批次 `balance.releasable = false`，
签发接口返回 `UNRESOLVED_ISSUES`：

- `RATE_INTERVAL_MISSING`：费率表存在覆盖缺口，某计费分钟没有对应费率区间，
  记录首个缺失分钟 `at_min`。
- `INVOICE_MISMATCH`：分段金额之和与票据 `amount_cents` 不符，记录票据额、
  计算额与差额。
- `SEGMENT_MINUTES_MISMATCH`：分段分钟之和与计费分钟不符（守恒自检）。

领域约束错误（如 `INVALID_STAY`、`INVALID_PAUSE`）同样使批次不可签发。

## 费率表结构

JSON 顶层为 `code`、`version`、`periods[]`。每个 period 含 `start_min`、
`end_min`（末区间可为 `null` 表示开放）与 `tiers[]`；每个 tier 含
`width_min`（开放档为 `null`）与非负整数 `rate_cents`。

- 区间重叠/乱序、缺开放档、费率非整数等**结构错误**在解析阶段拒绝（422）。
- 覆盖缺口不是结构错误，允许登记，在计费阶段以 `RATE_INTERVAL_MISSING` 挡签。
- 内置档案：`legacy`（历史费率）、`corrected`（月初更正费率 2.0.0）、
  `gapped`（含缺口，挡签演示）。样例见 `sample_data/rate_*.json`。
