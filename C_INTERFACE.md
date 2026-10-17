# C接口与页面入口

页面入口为 `A_demo_base/app.py`。当前回放接口可从页面下载，也可以运行
`A_demo_base/export_c_interface.py`生成。

- 接口版本：`A_B_C_replay_interface_v1_2_1`；
- 字段说明：`docs/C_INTERFACE_FIELD_DICTIONARY.md`；
- JSON Schema：`docs/C_INTERFACE_SCHEMA.json`；
- C影子情景：`A_demo_base/data/c_results/`；
- 等待驱动JIT诊断：`A_demo_base/data/c_diagnostics/`。

页面已实现C的PVAT对齐情景与等待驱动JIT可用性诊断，但仍是历史影子回放，
不是生产调度系统。正式执行建议保持0。

