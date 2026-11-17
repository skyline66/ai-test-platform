# 文章 → 代码对照表

原文：《AI测试54：Playwright+PO 到 AI 测试平台》（微信公众号「我是阿蔡」）
链接：<https://mp.weixin.qq.com/s/LpnSpiA5kGdgecWRH4fPvw>

这张表是「按大框架搭建」的验收单：文章说的每一条，都能指到具体文件和行。

## 一、五个阶段

| # | 文章主张 | 本仓库落点 |
| --- | --- | --- |
| 01 | 录制起步：codegen 探路，**录制是草稿不是产物** | `atp/authoring.py`（机械化出草稿）+ `docs/checklist.md` 第 1 条；草稿统一进 `tests/drafts/` 并带 `pytest.mark.draft` |
| 02 | Allure：让失败能自证——截图 + 当前 URL + 控制台日志 | `utils/evidence.py`；每次运行的原始 allure 结果在 `artifacts/runs/<id>/allure-results/` |
| 03 | PO 分层：把选择器关进笼子（pages / tests / utils） | 三个目录 + `atp/lint.py` 强制检查 |
| 04 | Cursor + Playwright MCP：让 AI 边看边写 | `atp/locator_doctor.py`（先取快照再出定位）+ `docs/ai-constraints.md`（四段式任务书） |
| 05 | AI Agent 搭平台：从脚本到服务 | `atp/`（runner / scheduler / triage / report / api / cli / static） |

## 二、具体纪律

| 文章原话 | 落地方式 |
| --- | --- |
| 「`get_by_role` / `get_by_label` / `get_by_text` 全是语义定位」 | `pages/login_page.py`、`pages/inventory_page.py` 全部用语义定位，零 `nth-child` |
| 「断言式等待，别用 sleep 赌时间」 | `atp/lint.py` 的 `PAGES-002` 规则直接禁掉 `time.sleep` / `wait_for_timeout` |
| 「失败时挂附件，一行就够」 | `utils/evidence.py::capture()`，截图 + URL + 控制台三件套 |
| 「把当时在哪个 URL 写进报告」 | evidence JSON 的 `url` 字段 → 报告「当时 URL」行 |
| 「报告里最没用的指标是通过率」 | `atp/report.py` 在通过率下方直接印这句话；归因分布是主视图 |
| 「选择器只准出现在一个地方」 | `TESTS-001`：tests/ 出现定位即失败 |
| 「页面对象里不放断言」 | `PAGES-001`：pages/ 出现 `assert` / `expect(` 即失败 |
| 「组件比页面更值得抽」 | `pages/components/navbar.py`（跨页导航）、`pages/components/cart_dialog.py`（跨页弹窗） |
| 「用例文件里 grep 不到 locator、#、xpath」 | `python -m atp lint`，CI 里是必过闸门 |
| 「每条用例独立登录，别共用登录态」 | `tests/conftest.py`：pytest-playwright 每用例一个新 context；`inventory_page` 夹具每次重新登录 |
| 「账号密码走配置，别写死在用例里」 | `utils/data.py` 集中管理，用例只引常量 |
| 「AI 一次只改一处，别顺便优化结构」 | `docs/ai-constraints.md` 的「约束 / 验收」两段 |
| 「先有三十条跑得稳的用例，再谈平台」 | runner 默认 `-m 'not draft'`；草稿永不自动进冒烟集；`docs/checklist.md` 第 10 条 |
| 「平台不是第一步，是第四步」 | README 顶部明确：本仓库同时提供「没有平台也能跑」的裸 pytest 路径（`make suite`） |
| 「先把容器镜像固定下来，再谈调度」 | `Dockerfile`：基础镜像 + tzdata + 中文字体 + `playwright==1.55.0` 的 chromium 全锁 |
| 「Agent 擅长：需求→用例草稿 / 失败日志归类 / 改版后批量修定位」 | `atp/authoring.py` / `atp/triage.py` / `atp/locator_doctor.py`，一一对应三件事 |
| 「Agent 不擅长定标准——什么算通过还得你写」 | 平台不生成断言标准；`triage` 只分类不给结论；草稿必须人工去掉 draft 标记 |

## 三、平台四块

| 文章里的四块 | 模块 | 可验证的表现 |
| --- | --- | --- |
| 执行调度 | `atp/runner.py`、`atp/scheduler.py` | `python -m atp run -m smoke`；`ATP_SCHEDULE_ENABLED=1` 后每小时自动跑 |
| 结果分析 | `atp/triage.py`、`atp/report.py` | `python -m atp triage` 出归因表；报告里失败用例带截图 |
| 用例管理 | `atp/registry.py`、`atp/store.py` | `python -m atp cases` 自动列出 tests/ 全部用例与标记 |
| 环境与数据 | `atp/config.py`、`Dockerfile`、`utils/data.py` | `GET /api/env` 返回浏览器版本/时区/被测地址 |

## 四、最小闭环

文章要求的最小可用版本：

> 提交一句自然语言 → 生成/选中一条用例 → 跑 → 出一份带截图的报告

对应命令（三步）：

```bash
python -m atp draft "登录成功后加入购物车并结算" --write   # ① 一句话 → 草稿
python -m atp run tests/drafts/test_draft_xxx.py --triage  # ② 跑 + 归因
python -m atp report                                       # ③ 报告路径
```

网页版同一条线在 <http://127.0.0.1:8077>：左边选用例、右边写需求、下方看历史与失败现场。