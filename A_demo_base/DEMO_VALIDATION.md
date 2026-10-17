# ABC JIT Demo 验证记录

验证日期：2026-10-17

## 自动化检查

- Python 语法编译：通过
- 单元测试：12/12通过（原Demo 8项 + 新增诊断闭环4项）
- B 输入表：仅使用 `*_online_safe.parquet`
- B 源 `lead_time_min`：0 个在线字段
- `*_evaluation_only`：0 个在线接口字段
- C 冻结结果：262 条提前决策、171 条情景、75 条影子推荐
- 正式执行建议：0 条
- MMSI `211886810`：`insufficient_crop_coverage`，不生成情景
- 更早候选：4条；A上下文完整2条；B联合键精确核验2条
- 同Port Call候选时间不一致：0条；历史替代候选保留1条
- 等待驱动JIT合格样本：0条

## 页面回归

- A 观测状态与 Port Status：正常显示
- B VAT、Direct/Indirect：正常显示，概率阈值保留
- B ARR→BER：无独立在线 Gate 触发时显示为不可用
- C 单船 JIT 案例：显示 17.000 kn → 13.127 kn、节油 7.2119 t、
  CO2 减少 22.4577 t，并明确标为PVAT对齐参数化情景估算
- 等待驱动JIT诊断：与PVAT对齐情景分开，显示34/4/2/2/0闭环指标
- `477454100`：13:36:54原候选与14:54:42历史替代候选均保留且不混同
- 历史真值：默认隐藏于 B 评价区域，不改变 B/C 输入
- C 接口 JSON：可以下载且为严格 JSON

## C 接口抽样结果

- `interface_version = A_B_C_replay_interface_v1_2_1`
- `observed_formal_events = []`
- `formal_event_online_input_policy = disabled_unverified_availability_a_v1_2_1`
- `arr_to_ber_prediction.source_type = unavailable/not_applicable`
- `arr_to_ber_prediction.qc_flag = independent_arrival_gate_trigger_required`
- `lead_time_min`：不存在
- `*_evaluation_only`：不存在
- `NaN`：不存在
