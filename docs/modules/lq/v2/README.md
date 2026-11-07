# LQ v2：数据库治理与访问控制

开工基线：`61fed41bbcea5b40495d8de37d13f19a0b0ba4ed`（ZQO PR #4已合入develop）。分支`lq/v2-governance`。

- [第7章](section.md)、[展示文字与讲稿](slides.md)、[引用](references.md)。
- [统一模式](../../../v2/schema/schema.sql)：LQ分节、模型不可变、派生/质量/审批表与受限视图。
- [治理服务](experiments/governance.py)、[测试](experiments/test_governance.py)、[操作C SQL](experiments/op_c.sql)。
- [治理原始结果](experiments/results/governance.json)、[前棒审阅](experiments/results/zqo-review-before.json)、[变更后事务兼容复跑](experiments/results/zqo-review-after.json)。

复现（输出使用新路径，不覆盖已交付结果）：

```sh
python3 -B -m unittest discover -s docs/v2/schema -v
python3 -B docs/modules/lq/v2/experiments/run.py --output /tmp/lq-v2.json
python3 -B docs/modules/zqo/v2/experiments/run.py --output /tmp/zqo-v2-review.json
```

数据库字段、临时消费者合同、权限边界、迁移与未完成的他人问题见[对接说明](integration.md)。v1代码及历史报告/PPT没有改写，本轮按提示词仅交付v2展示文字。
