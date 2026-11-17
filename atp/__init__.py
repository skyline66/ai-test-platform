"""AI 测试平台内核。

分层与仓库同构：
    pages/   只放定位与动作      → 「页面改了只改一个文件」
    tests/   只放步骤与断言      → 被执行的资产
    utils/   配置/日志/数据/现场 → 公共能力
    atp/     平台本身           → 调度、分析、管理、环境

平台四块（按重要性排，与文章一致）：
    1. 执行调度  runner.py + scheduler.py
    2. 结果分析  triage.py + report.py
    3. 用例管理  registry.py  (+ drafts 表)
    4. 环境与数据 config.py + Dockerfile
"""

__version__ = "0.1.0"

__all__ = ["__version__"]