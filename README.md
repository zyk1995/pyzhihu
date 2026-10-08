# Zhihu-Spider

抓取知乎**一个问题下的全部回答**，保存为 JSON Lines 和 Excel 可打开的 CSV。

2017–2018 年的用户主页爬虫（`spider/crawl.py`、`spider/run.py`、`spider/proxy.py` 以及 `old/`）依赖当时的页面结构和西刺代理站，已经不能用。新的入口只做回答抓取，不再启动那套代理池。

## 环境

- Python 3.10 及以上
- 依赖：`requests`、`beautifulsoup4`

```bash
pip install -r requirements.txt
```

在仓库根目录执行命令。也可以 `pip install -e .`，之后使用 `zhihu-answers`。

## 准备 Cookie

2026 年 10 月在本仓库的验证环境里，不带浏览器 Cookie 时无法抓取。实测 `python -m spider.answers 19581624` 在问题详情接口得到 HTTP 403、错误码 `40353`，原文是「请您登录后查看更多专业优质内容」。按标题搜索则得到 HTTP 403、错误码 `40362`，原文是「您当前请求存在异常，暂时限制本次访问」。另外抽查问题 `267209533`、`22042028`、`348322816`，详情接口同样是 `40353`。问题页 HTML 在不带签名时还会返回带 `zh-zse-ck` 的校验页。程序会为签名本地生成一个 `d_c0`，知乎不接受这种匿名值。

请使用你自己的浏览器 Cookie：

1. 在浏览器打开并登录 [https://www.zhihu.com](https://www.zhihu.com)。
2. 按 F12 打开开发者工具，切到网络（Network）。
3. 刷新页面，点开任意发往 `www.zhihu.com` 的请求。
4. 在请求头里复制整段 `Cookie`。其中必须有 `d_c0`。已登录时一般还有 `z_c0`。
5. 用下面任一方式提供，**不要把 Cookie 写进仓库或提交到 Git**：

```bash
# 环境变量（当前终端有效）
export ZHIHU_COOKIE='d_c0="你的值"; z_c0=你的值; _xsrf=你的值'

# 或写到文件。cookies.txt 已被 .gitignore 忽略
cp cookies.txt.example cookies.txt
# 编辑 cookies.txt 后：
export ZHIHU_COOKIE_FILE="$PWD/cookies.txt"
```

命令行也可以显式指定文件：`--cookie-file ./cookies.txt`。优先级是 `--cookie-file`，然后 `ZHIHU_COOKIE`，然后 `ZHIHU_COOKIE_FILE`。

Cookie 会过期。知乎经常把 Cookie 和当时的出口 IP 绑在一起，所以家用浏览器里复制的 Cookie，放到云主机或机房 IP 上仍可能被拒绝。出现「网络环境异常」「请求存在异常」时，换本机网络再试，或重新复制 Cookie。

## 用法

```bash
# 按标题搜索。只命中一个问题时直接抓取
python -m spider.answers "如何系统地学习 Python"

# 命中多个问题时，程序会列出候选（标题、ID、回答数、关注数）
# 交互终端里输入序号；非交互终端不会猜测，需要 --pick
python -m spider.answers "Python" --pick 2

# 问题链接或纯数字 ID
python -m spider.answers "https://www.zhihu.com/question/19581624"
python -m spider.answers 19581624

# 请求间隔、重试、只抓前 50 条、自定义输出目录
python -m spider.answers 19581624 --delay 1.5 --retries 4 --max-answers 50 --output output

# 可选 HTTP 代理。旧的西刺代理池不再使用
python -m spider.answers 19581624 --proxy http://127.0.0.1:7890
```

中断后再执行同一条命令会从 `progress.json` 记录的偏移继续，并跳过已经写入的回答。全部完成后再次运行不会重复抓取。想从偏移 0 再扫一遍（仍跳过已有回答）时加上 `--force`。

默认每页 20 条（知乎单页上限），成功请求之间等待 1 秒。429 和 5xx 会按 1s、2s、4s…退避重试。403 / 登录墙不会空转重试。

## 输出

目录名是问题 ID，例如 `output/19581624/`：

| 文件 | 内容 |
| --- | --- |
| `question.json` | 问题 ID、标题、回答数、关注数、问题链接 |
| `answers.jsonl` | 每行一个回答 JSON，UTF-8 |
| `answers.csv` | 同上字段，UTF-8 带 BOM，方便 Excel |
| `progress.json` | 下一页偏移、是否完成、已保存条数 |

每条回答至少包含：

- `answer_id`：回答 ID
- `author_name`：作者名（匿名时可能为空）
- `author_url_token`：作者主页 token
- `content_html`：接口返回的原始 HTML
- `content_text`：去掉脚本和标签后的纯文本
- `voteup_count`：赞同数
- `comment_count`：评论数
- `created_time` / `updated_time`：Unix 秒
- `answer_url`：`https://www.zhihu.com/question/{问题ID}/answer/{回答ID}`
- `question_id`

回答按接口默认排序分页拉取。`--max-answers` 只限制本次新写入的条数，方便试跑。很长的回答在 Excel 里可能超过单元格长度上限，完整内容以 `answers.jsonl` 为准。

## 测试

测试使用伪造的接口响应，不会访问知乎。

```bash
python -m unittest discover -s tests -v
```

## 限制

- 匿名访问目前不可用，必须准备浏览器 Cookie。本仓库在验证环境里的实测结果见上文。
- `x-zse-96` 随知乎网页脚本变化。签名失效时，接口会返回「请求参数异常」或 403，需要按当时的网页请求头更新签名逻辑。
- 请控制 `--delay`，只抓你确实需要的问题，遵守知乎的使用条款。不要把别人的 Cookie 用于未授权账号。
- 旧的多线程用户爬虫不要再运行。`spider/crawl.py` 在导入时会去拉已经失效的代理列表。

## 许可

MIT，见 `LICENSE`。
