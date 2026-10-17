# 洋山港 A+B+C JIT 历史回放 Demo（完整源码）

本包以B提供的 `A_B_complete_demo_source_20261017` 为底版，并逐文件核对
A提供的 `A完整Demo源码_全量公网版_20261017`。A侧数据、地图、事件、Port Call、
标签、Port Status和AIS裁剪文件保持不变；仅将页面运行接口升级为已核验的
A/B v1.2.1在线安全回放接口，并接入C的PVAT对齐情景和等待驱动JIT诊断闭环。

## 页面分层

1. A观测状态：截至回放时刻的AIS与Port Status；
2. B冻结预测：仅读取 `A_demo_base/data/b_predictions/*_online_safe.parquet`；
3. C的PVAT对齐影子情景：RTA、航速、燃油与CO₂参数化估算；
4. C的等待驱动JIT可用性诊断：与PVAT情景分开，不混算效果；
5. 离线历史真值：仅用于页面叠加和事后评价，不进入B/C输入。

## 关键结论

- A数据范围：712个Port Call、562艘船、1600个正式事件、4464个Port Status快照；
- C冻结结果：262条提前决策、171条参数化情景、75条PVAT对齐影子降速建议；
- 正式执行建议：0；
- 更早时刻诊断：34个访问、4个候选、2个完整A上下文、2个B联合键精确核验；
- 当前等待驱动JIT合格样本：0。

“0”仅适用于A v1.2.1打包裁剪AIS与固定24小时离线筛选范围，不代表全量AIS
不存在机会。候选选择是离线回溯诊断，不是实时触发规则。

## 安全接口

- 接口版本：`A_B_C_replay_interface_v1_2_1`；
- 在线输出不得包含源 `lead_time_min` 或任何 `*_evaluation_only` 字段；
- 使用 `prediction_age_min = replay_time - prediction_time`；
- `data_available_until_utc <= prediction_time_utc <= replay_time_utc`；
- 没有独立Gate到达触发时，ARR→BER保持不可用；
- `observed_formal_events=[]`，因为A v1.2.1没有验证最终事件当时可用时间；
- MMSI `211886810`覆盖不足时停止生成C情景。

根目录中的 `B_runtime/` 保留B的完整冻结模型、特征流水线与离线评估材料，
但Streamlit页面不会读取其中含历史评价字段的旧 `*_reproduced.parquet`。
原B包中的10月10日报告保留作历史审计，不代表当前v1.2.1页面验收；当前结果以
`A_demo_base/DEMO_VALIDATION.md`和12项自动化测试为准。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python validate_joint_demo.py
streamlit run A_demo_base\app.py
```

Streamlit Community Cloud的Main file path填写 `A_demo_base/app.py`。
具体替换与验收步骤见 `A_demo_base/DEPLOY_TO_EXISTING_STREAMLIT.md`。

