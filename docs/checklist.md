# 开工前扫一眼的 10 条

原文的 10 条纪律，右侧是「本仓库里它长什么样」——能指到文件才算落地。

| # | 纪律 | 本仓库落点 |
| --- | --- | --- |
| 1 | **录制是草稿** —— 探路可以，交付不行 | `atp/authoring.py` 生成的草稿一律带 `pytest.mark.draft`，永不自动进冒烟集 |
| 2 | **语义定位优先** —— role / label / text，别用 nth-child | `pages/*.py`；`atp/lint.py` TESTS-001 拦截 |
| 3 | **断言式等待** —— 别用 sleep 赌时间 | `expect(...)`；`PAGES-002` 禁掉 `time.sleep` / `wait_for_timeout` |
| 4 | **Allure 挂现场** —— 截图 + URL + 日志 | `utils/evidence.py`，失败时自动挂三件套 |
| 5 | **报告别看通过率** —— 看误报率和定位耗时 | `atp/report.py` 主视图是归因分布，通过率下方印着这句话 |
| 6 | **选择器只在一处** —— `pages/` 之外不许出现 | `atp/lint.py` TESTS-001 / TESTS-002 |
| 7 | **页面对象不写断言** —— 它只回答「怎么点」 | `atp/lint.py` PAGES-001 |
| 8 | **组件比页面更该抽** —— 导航栏、弹窗、日期控件 | `pages/components/navbar.py`、`pages/components/cart_dialog.py` |
| 9 | **AI 一次只改一处** —— 别让它「顺便优化」 | `docs/ai-constraints.md` 的四段式任务书 |
| 10 | **先有 30 条稳用例，再谈平台** | 本仓库是**框架示范**（12 条可跑用例）；真实项目请先攒够再扩平台；runner 默认排除 draft |

---

# 你能照搬的 5 件事（都能在本仓库里直接跑）

### 第一件：录一条流程，然后手改一遍

```bash
# 起内置演示站
python -m utils.demo_server          # http://127.0.0.1:8811/index.html

# 用它探路（需要 playwright CLI）
python -m playwright codegen http://127.0.0.1:8811/index.html
```

录完别提交。把 `#app > div:nth-child(3) > button` 换成
`page.get_by_role("button", name="登录")`，再对照 `pages/login_page.py` 看差别。

### 第二件：给失败挂三样东西

```python
from utils import evidence
info = evidence.capture(page, "nodeid", console_logs, base_url)
# → 截图 + 当时 URL + 控制台日志，同时挂进 Allure
```

### 第三件：把最常用的那个页面抽成 Page Object

看 `pages/inventory_page.py`：`__init__` 里只放定位，方法只放动作。
用例层就瘦成三行（见 `tests/test_cart.py`）。

### 第四件：让 AI 写一个新页面的定位，然后看它错在哪

```bash
python -m atp doctor --url http://127.0.0.1:8811/index.html \
                     --locator "page.locator('#app > div:nth-child(3) > button')"
```

它错的地方，就是你需要补约束的地方——把结论写进 `docs/ai-constraints.md`。

### 第五件：把现有用例接进 CI，每天跑一次冒烟

`.github/workflows/smoke.yml` 已配好：push + 每天 09:00（Asia/Shanghai）+
手动触发，跑完上传 `artifacts/`（含报告与截图）。不用等平台，这就是起点。

```bash
# 本地等价物
python -m atp run -m smoke --triage
```