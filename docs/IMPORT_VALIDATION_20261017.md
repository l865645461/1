# 完整源码导入与部署前验证

- 来源：洋山港JIT完整Demo源码_20261017_v1.2.1展示版.zip。
- 仓库：l865645461/1；导入时仓库无提交，创建 main，不改写远端历史。
- 导入前校验：MANIFEST_SHA256.csv 全部 129 项匹配。
- 源码、冻结数据及模型保持附件原样；仅根 .gitignore 调整为跟踪部署需要的数据与模型，新增部署说明和本记录。原附件清单保留。
- 实际环境：Python 3.12.14，按 requirements.txt 安装；pip check 通过。
- python validate_joint_demo.py：12 项测试全部通过。
- 导出 PC_202401_477166500_20240123T172010 在 2024-01-23T13:19:30Z 的接口：严格 JSON 校验通过，无 lead_time_min 或 *_evaluation_only 字段，observed_formal_events 为空。
- Streamlit AppTest：默认页面、C 案例在决策时刻、历史真值开关和覆盖不足案例均验证通过，无未捕获异常。覆盖不足案例的 st.error 面板是预期门禁。
- 页面决策时刻显示原方案燃油 18.9785 t、JIT 方案燃油 11.7667 t、CO₂减排 22.4577 t；均为研究情景估算，正式执行建议为 0。
- 诊断指标：34 / 4 / 2 / 2 / 0。
- Streamlit 进程已启动，首页和 /_stcore/health 均返回 HTTP 200，健康响应为 ok。
- 未进行人工浏览器视觉验收；未创建或验收新的 Streamlit 公网应用。部署参数见根目录 DEPLOY_STREAMLIT.md。
- 附件中原有 CRLF 和末尾空行产生 git diff --check 风格提示，保留原文件字节，不影响上述功能验证。
