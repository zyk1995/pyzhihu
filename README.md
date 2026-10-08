# Zhihu-Spider

抓取知乎**一个问题下的全部回答**，保存为 JSON Lines 和 Excel 可打开的 CSV。

2017–2018 年的用户主页爬虫（`spider/crawl.py`、`spider/run.py`、`spider/proxy.py` 以及 `old/`）依赖当时的页面结构和西刺代理站，已经不能用。新的入口只做回答抓取，不再启动那套代理池。

## 环境

- Python 3.10 及以上
- 依赖：`requests`、`beautifulsoup4`、`segno`（终端二维码，纯 Python，不需要图形界面）

```bash
pip install -r requirements.txt
```

在仓库根目录执行命令。也可以 `pip install -e .`，之后使用 `zhihu-answers`。

## 登录

没有可用 Cookie 时，程序会走知乎官方扫码接口：先打开登录页拿 `_xsrf`，再请求 `udid` 和验证码状态，然后 `POST /api/v3/account/api/login/qrcode` 拿到 `token` 和 `link`。字符二维码直接画在终端里，SSH 和无图形界面的云主机不用打开图片查看器。同一份链接会另存成 PNG，只是备用。

```bash
python -m spider.answers 19581624
# 已有会话过期，或想换账号时
python -m spider.answers 19581624 --login
```

终端里会看到这些提示：`等待扫码`、`已扫码请在手机确认`、`二维码过期自动刷新`、`登录成功`。用手机知乎 App 扫终端里的码并确认。成功后 Cookie 写到 `~/.config/zhihu-spider/session.cookie`，权限 `0600`。下次运行会先请求 `/api/v4/me` 检查会话；失效就再扫一次。

二维码大约两分钟过期，过期会自动刷新。总等待默认 300 秒，可用 `--login-timeout` 修改，`0` 表示一直等到你按 Ctrl+C。如果知乎返回验证码或安全验证，程序会停下来说明原因，不会去解验证码。

也可以继续自己提供 Cookie，优先级高于本地会话：

```bash
export ZHIHU_COOKIE='d_c0="你的值"; z_c0=你的值; _xsrf=你的值'
# 或
python -m spider.answers 19581624 --cookie-file ./cookies.txt
```

`--cookie-file`、环境变量 `ZHIHU_COOKIE`、`ZHIHU_COOKIE_FILE` 三者里，命令行文件优先。这些文件不要提交到仓库。

2026 年 10 月在本仓库的验证环境里，不带登录态时问题详情是 HTTP 403、错误码 `40353`（「请您登录后查看更多专业优质内容」）。扫码令牌接口可以返回 `link`，但官方二维码图片和 `scan_info` 轮询在这台机器上是 HTTP 403、错误码 `40352`（安全验证）。所以这里只能确认二维码生成和终端显示，不能代替你在手机上点确认。

## 请求节奏

默认把请求拉开，降低触发风控的可能：

- 回答页之外的接口，以及页与页之间，随机等待 **3 到 8 秒**
- 每抓 **5** 页回答，再额外停 **15 到 30 秒**
- 间隔不能低于 **1 秒**，除非显式加上 `--allow-fast`
- `--max-requests` 限制这一次运行的请求数
- `--max-requests-per-day` 限制当天请求数，计数在 `~/.config/zhihu-spider/request-count.json`

```bash
python -m spider.answers 19581624 --delay-min 4 --delay-max 9 --pause-every 4
python -m spider.answers 19581624 --max-requests 30 --max-requests-per-day 80
```

`--delay 2` 会把间隔固定成 2 秒，并取消额外长停。遇到验证码、安全验证、403 或持续的 429，程序停止继续请求，把偏移写进 `progress.json`，并说明下次执行同一条命令即可续传。429 最多再等一次，不会连着打。

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

# 只抓前 50 条。间隔仍用默认的 3 到 8 秒
python -m spider.answers 19581624 --max-answers 50 --output output

# 可选 HTTP 代理。旧的西刺代理池不再使用
python -m spider.answers 19581624 --proxy http://127.0.0.1:7890
```

中断后再执行同一条命令会从 `progress.json` 记录的偏移继续，并跳过已经写入的回答。全部完成后再次运行不会重复抓取。想从偏移 0 再扫一遍（仍跳过已有回答）时加上 `--force`。

默认每页 20 条（知乎单页上限）。请求间隔见上面的「请求节奏」。抓取过程会打印 `进度 已保存/总数`。结束时打印本次写入条数、目录和耗时。

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

- 本机验证只能确认扫码令牌和终端二维码。手机确认登录、以及确认后的抓取，需要你自己扫一次。
- 官方二维码图片和扫码状态在部分机房 IP 上会返回 40352。这时终端仍会画出根据 `link` 生成的二维码，但轮询会停下来，不会空转。
- `x-zse-96` 随知乎网页脚本变化。签名失效时，接口会返回「请求参数异常」或 403。
- 只抓你确实需要的问题，遵守知乎的使用条款。不要把别人的 Cookie 用于未授权账号。
- 旧的多线程用户爬虫不要再运行。`spider/crawl.py` 在导入时会去拉已经失效的代理列表。

## 许可

MIT，见 `LICENSE`。
