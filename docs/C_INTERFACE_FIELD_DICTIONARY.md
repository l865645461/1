# C 接口字段说明 v1.2.1

## 版本与门禁

| 字段 | 含义 |
|---|---|
| `interface_version` | 固定为 `A_B_C_replay_interface_v1_2_1`。 |
| `a_interface_version` | 固定为 `A_INTERFACE_V1.2.1`。 |
| `b_recompute_allowed` | B 适配器是否允许当前裁剪输入进入冻结特征/模型链。只有 `true` 可生成 C 情景。 |
| `b_blocking_qc_flags` | 覆盖、AIS、Port Status 或 warmup 阻断原因。 |
| `b_non_blocking_qc_flags` | 不阻断但必须保留的预处理提醒，如 heading 缺失。 |
| `qc_flag` | C 当前记录的主要 QC；阻断时保留 B 首个阻断标记。 |

## AIS 与覆盖

| 字段 | 含义 |
|---|---|
| `ais_time_utc` | 决策时点前最新 AIS 时间，必须不晚于 `decision_time_utc`。 |
| `current_lon`, `current_lat` | 最新 AIS WGS84 位置。 |
| `current_heading_deg` | A Stage2 原始 heading；缺失不以 COG 或未来点填补。 |
| `ais_age_min` | 决策时点减 AIS 时间，超过 10 分钟不生成情景。 |
| `a_context_observed_point_count` | 指定 30 分钟窗口内 A 裁剪包实际返回点数。 |
| `a_packaged_interval_complete` | 请求区间是否落在 A 已打包裁剪窗口内；只作覆盖 QC。 |
| `a_heading_nonnull_count` | 窗口内 heading 非空点数。 |

## Port Status

| 字段 | 含义 |
|---|---|
| `port_status_snapshot_time_utc` | 向后 as-of 快照时间，必须不晚于决策时点。 |
| `port_status_age_min` | 决策时点减快照时间。 |
| `port_status_source_version` | A v1.2.1 状态文件及清单哈希。 |
| `unique_inbound_vessels_60m` | 60 分钟内入港方向去重船数。 |
| `unique_outbound_vessels_60m` | 60 分钟内出港方向去重船数。 |

六项 raw crossing 是重复穿越次数，只可由 B 冻结特征兼容层使用，不属于 C 对外字段，也不得解释为船舶数量。

## B 预测溯源

| 字段 | 含义 |
|---|---|
| `prediction_time_utc` | B 生成预测的时刻。 |
| `data_available_until_utc` | B 输入数据截至时刻，必须不晚于预测时刻。 |
| `prediction_age_min` | 当前回放时刻减预测时刻。 |
| `lead_time_definition` | 固定为 `elapsed_since_prediction`。 |
| `direct_indirect_prediction` / `indirect_class` | B 的冻结分类 `Direct` 或 `Indirect`。 |
| `direct_indirect_probability` / `indirect_probability_uncalibrated` | B 的 `P(Indirect)`，未经校准。 |
| `direct_indirect_decision_threshold` | B 冻结分类阈值，本批为 0.5。 |
| `feature_schema_version` | B 冻结特征 schema 版本。 |
| `target_definition` | B 任务目标定义。 |
| `historical_precomputed_source` | 固定说明预测来自原冻结 Stage2，不代表从 A 裁剪包重推。 |

在线接口不得出现 `lead_time_min` 或任何 `*_evaluation_only` 字段。

## 距离、场景和评价

| 字段 | 含义 |
|---|---|
| `distance_method` | `great_circle_to_gate_times_route_factor`。 |
| `route_factor` | 1.15。 |
| `distance_quality` | `research_approximation_not_navigable_route`。 |
| `research_recommendation` | 历史影子研究建议，不是港口执行指令。 |
| `operational_advice` | 正式执行层；当前缺少部署条件，保持“不建议执行”。 |
| `*_evaluation_only` | 决策后历史评价字段，禁止进入 `c_decision.calculate()`。 |
