# LQ：地面风险评估与安全治理

状态：模块可交付。基线`starter-v0`；已检查ZC提交`be027dc9c94d2416836f2b8f24fe4e3fee81000c`，完成风险适配与规划联合验证。YHT/ZQO/LJ实际成果待后续接入。

- [报告章节与技术决定](design.md)：风险因果链、候选模型、代理定义、数据字段、硬约束和权衡。
- [治理方案](governance.md)：权限、职责分离、来源、发布、审计、隐私及滥用防范。
- [验证记录](evaluation.md)、[原始结果](results/evaluation.json)、[取舍CSV](results/tradeoffs.csv)。
- [适配代码](prototype/risk.py)、[19项测试](prototype/test_risk.py)、[实验入口](prototype/evaluate.py)。只需Python标准库。
- [跨模块接口与检查](integration.md)、[参考文献](references.md)。
- [第5–6页PPT](slides/lq-risk-governance.pptx)、[讲稿与答辩准备](slides/notes.md)。

从仓库根目录复现：

```sh
python3 -m unittest discover -s docs/modules/lq/prototype -v
python3 -m unittest discover -s docs/modules/zc/prototype -v
python3 docs/modules/lq/prototype/evaluate.py
```

报告整合：设计章节用于风险定义及技术论证，治理章节用于数据安全、隐私与伦理，评估章节用于实证与反思。两页PPT插入团队第5–6页，保留合成参数及代理指标标签。未代填贡献比例、同伴认可或正式签字。
