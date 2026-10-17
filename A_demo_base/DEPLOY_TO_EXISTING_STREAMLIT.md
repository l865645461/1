# 替换现有 Streamlit Demo 的部署说明

目标页面：`https://yangshan-ab-history-demo.streamlit.app/`

本包用于把现有 A+B 历史回放页面升级为 A+B+C JIT 历史影子决策 Demo。若希望保留原链接，必须更新该应用当前绑定的 GitHub 仓库和分支；不要使用 Streamlit 的 Fork 功能另建应用。

## 1. 上线前准备

- 取得现有 Demo 所绑定 GitHub 仓库的写入权限，确认部署分支和 Main file path。
- 在该仓库创建一个可回退的提交或标签，保留当前 A+B 版本。
- 本包目录内容应复制到应用实际运行目录；不要把外层 ZIP 文件名目录再嵌套一层。
- Main file path 应为 `app.py`；若应用位于仓库子目录，则填写 `<子目录>/app.py`。
- Python 建议使用 3.11；依赖由 `requirements.txt` 安装，无需 Streamlit secrets。

## 2. 替换范围

用本包中的以下内容更新应用目录：

- `app.py` 及全部本地 Python 模块；
- `requirements.txt`；
- `data/` 下 A 冻结数据、B `*_online_safe.parquet` 和 C 冻结结果；
- README、验证记录与完整性清单。

不得从旧表恢复 `lead_time_min`，不得把 A 最终事件或事后真值接回 B/C 在线输入，也不得绕过 `insufficient_coverage` / `not_applicable` 门禁。

## 3. 提交前验证

在应用目录执行：

```bash
python -m unittest discover -v -p "test*.py"
python export_c_interface.py \
  --port-call-id PC_202401_477166500_20240123T172010 \
  --replay-time-utc 2024-01-23T13:19:30Z \
  --output c_interface_smoke_test.json
streamlit run app.py
```

预期结果：

- 12 项自动化测试全部通过；
- 页面能加载 A 观测、B 冻结预测和 C 情景建议；
- C 导出 JSON 不含 `lead_time_min`、`*_evaluation_only` 或 `NaN`；
- 正式执行建议仍为 0。

`c_interface_smoke_test.json` 仅为本地冒烟测试产物，验证后可删除，不需要提交到部署仓库。

## 4. 云端验收

提交并推送到现有应用绑定分支后，等待 Streamlit Community Cloud 自动重新部署，再依次检查：

1. 页面标题为“洋山港 A+B+C JIT 历史回放 Demo”。
2. 选择包含 C 情景的单船案例，能够看到 Baseline 与 JIT 航速、燃油和 CO2 参数化情景结果。
3. MMSI `211886810` 显示 `insufficient_crop_coverage`，且不生成速度、RTA 或燃油建议。
4. ARR→BER 在没有独立 Gate 到达触发时保持不可用。
5. 历史真值默认隐藏，开启后只改变历史评价展示，不改变 B/C 输入和结果。
6. 下载 C 接口 JSON，确认四层信息和时间因果字段正确。
7. “C · 等待驱动JIT可用性诊断”显示34/4/2/2/0，且明确0仅适用于裁剪AIS与固定筛选范围。
8. `PC_202401_477454100_20240111T042304`显示C原候选13:36:54Z；14:54:42Z仅作为B历史替代候选保留，不混同。

## 5. 回滚

若云端启动失败或验收不通过，将部署分支回退到上线前保留的提交并重新部署。不要通过删除冻结数据、放宽 QC 或启用未来信息来修复页面。

## 6. 发布边界

该 Demo 是历史影子决策与情景回放，不是实际港口调度系统。C 的 RTA、航速、燃油和 CO2 均为研究情景估算；在缺少官方 ETB/ETD、泊位计划、可航路线、实船油耗曲线和港口授权的情况下，`operational_advice` 必须保持“不建议执行”。
