# 洋山港 A+B+C JIT 历史回放 Demo

这是在现有 A+B Streamlit 历史回放页面中接入 C 模块后的独立、可部署版本。
页面严格区分四层信息：

1. **A 观测状态**：截至回放时刻的 AIS 与 Port Status；
2. **B 冻结预测**：来自 `*_online_safe.parquet`，按预测时刻和数据截至时刻过滤；
3. **C 影子建议**：冻结的PVAT对齐RTA、JIT航速、燃油与CO2参数化情景结果；
4. **离线历史真值**：正式事件、访问归属、标签和完整时长仅作页面历史叠加或
   事后评价，永不回流到 B/C 输入。

页面另设“等待驱动JIT可用性诊断”，与PVAT对齐情景分开展示，不混算效果。

## 接口版本

- A：`A_INTERFACE_V1.2.1`
- B：`B_to_C_A_INTERFACE_V1_2_1_update_20261014`
- C：`A_B_C_replay_interface_v1_2_1`

Demo 不重训模型、不重新识别 A 事件，也不重新计算冻结 C 结果。

## 关键边界

- B 在线表不含源 `lead_time_min`，页面仅计算
  `prediction_age_min = replay_time - prediction_time`。
- `data_available_until_utc <= prediction_time_utc <= replay_time_utc`。
- A 正式事件缺少经验证的当时可用时间，导出给 C 时固定为
  `observed_formal_events=[]`，历史阶段只作页面叠加。
- 没有独立在线 Gate 到达触发，因此 ARR→BER 在给 C 的安全接口中保持不可用；
  A 的最终 ARR 事件不能充当该触发器。
- MMSI `211886810` 的指定窗口覆盖不足，C 保留
  `insufficient_crop_coverage`，不生成速度/RTA/燃油情景。
- C 等待代理为 `offline_cross_sectional_backtest / research_only`。
- RTA 是研究候选，不是官方 ETB、泊位可用时间或港口承诺。
- 距离为 Gate 大圆距离乘 `route_factor=1.15`，不是可航路线。
- 燃油和 CO2 为参数化情景估算，不是实际节油减排。
- 缺少官方 ETB/ETD、泊位计划、可航路线、实船油耗曲线和港口授权，
  正式执行建议保持 0。

## PVAT对齐冻结结果口径

- 提前决策：262 条
- B 重算门禁允许：261 条
- 覆盖不足阻断：1 条
- 可计算情景：171 条
- 影子推荐降速：75 条
- PVAT对齐情景：92 条，其中影子推荐降速75条
- 171条情景均为预测Direct，`berth_jit_evidence_status`均为`insufficient`
- 正式执行建议：0 条

169.7334吨节油和528.5505吨CO₂减少是包含训练、验证和测试记录的全样本
参数化情景汇总，不作为独立测试效果。B标记test的22条情景对应12.2081吨
参数化节油和38.0165吨参数化CO₂减少，但尚未确认A→B→C全链路独立测试。

## 等待驱动JIT诊断闭环（2026-10-17）

- 诊断访问：34个；固定24小时AIS筛选找到候选：4个；
- 30分钟A上下文完整：2个；B按“Port Call ID + candidate UTC”精确核验：2个；
- MMSI `477454100`的C原候选`2024-01-10T13:36:54Z`已被B精确复核；
  B历史替代候选`2024-01-10T14:54:42Z`被保留但不混同；
- 冻结Direct/Indirect模型只按ARR−4h协议验证，不能迁移至更早候选；
  ARR→BER也不得在独立Gate到达触发前调用；
- 当前等待驱动JIT合格样本：0。

“0”仅适用于A v1.2.1打包裁剪AIS和固定24小时离线筛选范围，不代表全量AIS
不存在机会；该筛选是离线回溯诊断，不是实时触发规则。本版不重训模型、不修改
冻结结果、不重算燃油或CO₂。

## 目录

```text
app.py
b_runtime_adapter.py
c_interface.py
c_results.py
c_diagnostics.py
data_loader.py
map_utils.py
replay_utils.py
test_demo_contract.py
test_c_diagnostics.py
requirements.txt
data/
  b_predictions/*_online_safe.parquet
  c_results/*
  c_diagnostics/*
  demo_ais_all_port_calls_000.parquet
  A 冻结事件、Port Call、标签、Port Status 与 GeoJSON
```

## 本地运行

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

将本目录作为一个独立仓库或仓库子目录提交，Main file path 指向 `app.py`。
运行时只读取本目录文件，不依赖开发电脑盘符，也不会写回 A/B/C 冻结数据。

若要在不改变现有 Demo 链接的前提下升级 A+B 页面，请按
[`DEPLOY_TO_EXISTING_STREAMLIT.md`](DEPLOY_TO_EXISTING_STREAMLIT.md) 执行替换、验收与回滚。
