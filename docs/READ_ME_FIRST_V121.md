# v1.2.1页面与历史材料边界

本目录原有的A/B测试报告和20-Port-Call记录来自B早期历史回放包，作为审计材料保留。
它们使用过旧接口术语，不应覆盖当前页面的v1.2.1安全契约。

当前可执行页面只读取：

- `A_demo_base/data/b_predictions/*_online_safe.parquet`；
- `A_demo_base/data/c_results/`；
- `A_demo_base/data/c_diagnostics/`。

当前验收以 `A_demo_base/DEMO_VALIDATION.md`、`A_demo_base/test_*.py` 和根目录
`validate_joint_demo.py` 为准。B_runtime中的冻结模型、旧预测表、流水线与评估文件
未被修改，也不会由页面在线调用。

