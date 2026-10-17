# A+B+C完整Demo整合验收

验收日期：2026-10-17

## 输入底版

- A：`A完整Demo源码_全量公网版_20261017.zip`
- A+B：`A_B_complete_demo_source_20261017.zip`
- C：2026-10-17等待驱动JIT诊断闭环版

## 冻结内容保护

- A的7个原始数据文件逐文件SHA256核对：0项变化；
- A的 `data_loader.py`、`map_utils.py`、`replay_utils.py`、`requirements.txt`
  和 `.gitignore`：与A公网版一致；
- B_runtime共69个文件逐文件SHA256核对：0项变化；
- 未重训B模型，未重新识别A事件，未重算原C冻结成果。

## 接口修正

B原A+B包中的页面层仍引用旧 `*_reproduced.parquet` 和源 `lead_time_min`。
当前页面已改为仅读取 `*_online_safe.parquet`，接口升级为
`A_B_C_replay_interface_v1_2_1`，使用 `prediction_age_min`。
旧B_runtime作为冻结审计材料保留，但不被Streamlit页面读取。

## 自动化与页面验收

- 自动化测试：12/12通过；
- 在线接口中的源 `lead_time_min`：0；
- 在线接口中的 `*_evaluation_only`：0；
- A未来正式事件输入：0；
- 无独立Gate触发时ARR→BER：不可用；
- MMSI 211886810覆盖不足：停止C情景；
- C页面分开显示PVAT对齐情景与等待驱动JIT诊断；
- 单船情景已完整展示8项：当前速度、推荐RTA、建议速度、可利用等待时间、
  原方案燃油、JIT方案燃油、节油量和CO₂减排；
- 页面标题及面向用户的模块标题不再显示A/B/C字母，接口版本、字段名和审计来源保持不变；
- 等待驱动诊断指标：34/4/2/2/0；
- 本地Streamlit页面启动及关键内容可视化检查：通过。

