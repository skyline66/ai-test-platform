# 给 AI 的约束：四段式任务书

> 这是「AI 一次只改一处」的可执行版本。
> 直接复制下面模板去用；平台侧的 `atp/authoring.py` 也按同一套约束做校验。

## 一、为什么需要这份文档

AI 写得出「**能跑的定位**」，写不出「**稳的定位**」。

- 稳的：`get_by_role("button", name="登录")`、`get_by_label("手机号")`、页面上的可见文案。
- 不稳的：`div:nth-child(3)`、动态生成的 `#id`、`/html/body/div[2]/div[3]`。

模型不知道你们前端下周要重构，你知道。所以约束必须由人写下来，
并且**在代码层面被检查**（`python -m atp lint`），而不是靠每次叮嘱。

## 二、四段式任务书模板

交代任务时，四样东西别少：

```text
目标：为登录页写一个 Page Object，放在 pages/login_page.py
参考：@pages/order_page.py 是已有写法，照着它的结构来
约束：只用 get_by_role / get_by_label / get_by_text / get_by_test_id；不要用 xpath；
      不要改 conftest.py；元素名用页面上的中文原文；页面对象里不许写断言
验收：能通过 tests/test_login.py 里的两条用例，且 `python -m atp lint` 无输出
```

四段的作用：

| 段落 | 少了会怎样 |
| --- | --- |
| 目标 | 它自己发明一个文件路径，或者顺手重构三个模块 |
| 参考 | 它不看现有风格，新人接手要维护两套写法 |
| 约束 | 它默认给你路径式定位，而且会在页面对象里塞断言 |
| 验收 | 你只能「看着像对的」，无法判断它是否真的合格 |

## 三、硬约束清单（违反即重写）

1. 定位只用 `get_by_role` / `get_by_label` / `get_by_text` / `get_by_placeholder` / `get_by_test_id`。
2. 禁止 `xpath`、`nth-child`、`css=`、`#id` 选择器。
3. 用例文件里不出现 `.locator(`，也不直接 `.click(` / `.fill(`——动作封装进页面对象。
4. 页面对象里不写 `assert` / `expect(`。页面只回答「怎么点」。
5. 不改 `conftest.py`、不新增依赖、不调整目录结构。
6. 元素名用页面上的中文原文，不要自己翻译成英文。
7. 一次只改一处；跑不过就把报错贴回去，不要让它「顺便优化结构」。

## 四、交付前的三步验收

```bash
python -m atp lint                          # ① 纪律：无输出才算过
python -m pytest platform_tests -q           # ② 语法与模板校验
python -m atp run tests/drafts/<file> --triage  # ③ 真跑一遍，看归因
```

三步全绿，再把它从 `tests/drafts/` 移到 `tests/`，并去掉 `pytest.mark.draft`。

## 五、改版后批量修定位的用法

页面改版，二十条用例一起红。正确姿势不是逐条猜，而是：

```bash
# 1. 取一份新快照，让平台列出所有可选语义定位
python -m atp doctor --locator "page.locator('#app > div:nth-child(3) > button')" \
                     --url http://127.0.0.1:8811/index.html

# 2. 人抽三条验一遍（这一步不能省）
# 3. 改 pages/ 里的一个文件，而不是改二十个用例
```

模型在这个环节比你快，但结论得你抽三条验一遍——
因为「分数高」只说明新旧定位沾边，不说明它在业务上真的是同一个元素。

## 六、平台侧怎么配合

| 约束 | 平台里由谁兜底 |
| --- | --- |
| 不用 xpath / 路径定位 | `atp/lint.py` TESTS-001 |
| 页面对象不写断言 | `atp/lint.py` PAGES-001 |
| 草稿必须人工确认 | `pytest.mark.draft`，runner 默认 `-m 'not draft'` |
| 生成的代码要能导入 | `atp/authoring.py::_validate` 做 `ast.parse` + 禁用词检查 |
| 模型瞎造 API | 起草时把 `pages/` 的类与方法签名拼进 prompt（`page_objects_digest()`） |