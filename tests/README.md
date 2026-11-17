# 用例层

这个目录只写两件事：**步骤** 和 **断言**。

判断标准：`grep -E "locator\(|xpath|nth-child|#\w" tests/` 应该无输出。
有输出说明定位泄漏到了用例层，`python -m atp lint` 会直接失败。

```bash
python -m pytest tests -v          # 直跑
python -m atp run --all --triage   # 走平台：跑 + 存 + 归因 + 出报告
```