# 新建公开 Streamlit Demo

本次部署使用附件 v1.2.1 完整源码，单独创建新应用。

在 https://share.streamlit.io/ 登录并连接有仓库访问权的 GitHub 账号，选择 Create app / Deploy a public app from GitHub：

| 配置 | 值 |
| --- | --- |
| Repository | `l865645461/1` |
| Branch | `main` |
| Main file path | `A_demo_base/app.py` |
| Advanced settings → Python | `3.12` |
| Secrets | 无需配置 |

选择一个可用的新应用域名，点击 Deploy。在应用分享设置中确认允许所有人查看，并用未登录窗口检查访问。不要使用附件旧部署文档中的原应用链接作为新部署结果。

根目录 requirements.txt 引用 A_demo_base/requirements.txt；冻结数据和模型均随 Git 提交，不需要额外下载或重训。

## 本地验证

```bash
python3 -m venv /workspace/venvs/yangshan
/workspace/venvs/yangshan/bin/python -m pip install -r requirements.txt
/workspace/venvs/yangshan/bin/python validate_joint_demo.py
/workspace/venvs/yangshan/bin/python -m streamlit run A_demo_base/app.py --server.headless=true
```

验收页面标题“洋山港 JIT 历史回放”，切换典型案例、回放时间及历史真值显示，确认地图和数据加载。覆盖不足的 MMSI 211886810 不生成 C 情景；诊断指标为 34/4/2/2/0，正式执行建议保持 0。

## 来源完整性

导入前已核对附件 MANIFEST_SHA256.csv 中全部 129 个文件，均匹配。原清单保留用于附件审计；本仓库根 .gitignore 已调整为跟踪冻结数据与模型，因此其哈希与原清单不同。应用逻辑、依赖版本、数据和模型保持附件原样。

公开部署的创建和最终访问验收必须以 Streamlit 实际返回的应用地址和状态为准。
