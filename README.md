# keyword-radar（新词雷达）

> 本项目不是 [new-term-radar](https://github.com/zhuyansen/new-term-radar) 的 GitHub fork，而是基于它（MIT）重建的独立项目，聚焦海外 AI 新词的**发现**：不做建站、不做推送、不做页面生成。仓库名是 keyword-radar；Python 包、MCP 清单和 PyPI 身份仍沿用上游的 new-term-radar。

每天一份报告：AI 领域里刚开始冒头的名字（新模型、新产品、新工具、新仓库），以及每个名字背后**大家本来就在搜的老词**——规模多大、首页还有没有位置、值不值得做。

## 为什么做这个

一个新名字会按这个顺序留下痕迹：

1. 实验室或大号在 X 上先说出来；模型进入 Hugging Face 热门榜。
2. GitHub 上某一个仓库自己涨起来。
3. 导航站和竞品给它加页面；有人为它注册域名，新站开始有排名。
4. 你自己的站第一次因为这个词有了搜索曝光。
5. Google Trends 上出现曲线，这已经是几天到几周之后了。

关键词工具读的是第 5 步。这个雷达每天读第 1 到 4 步，第 5 步只用来复盘自己准不准。

它最初照着一个例子做：[Niko1221/Strata](https://github.com/Niko1221/Strata) 创建于 2026-09-24，九天后 7,700 星，9 月 26 日起有人在搜「niko strata」——而当时关键词工具里还查不到。一个仓库每天涨 800 星，这本身就是全部信号。

## 核心思路：新名字是入口，老需求是答案

- **新名字**（专名）搜索量小、寿命短、通常属于别人：「SynthID Detector」是 Google 的。
- **它做的事**（通用词）才是长期有人搜、没人拥有的词：「ai image detector」。
- 所以雷达不直接「搜关键词」；它**先发现名字，再把名字翻译成它背后的老需求**，然后用搜索量、Trends、首页竞争给这个老需求定价。
- 发现靠信号，判断靠模型 + 数据，校准靠复盘。

一句话：**名字是线索，通用词是答案，复盘是校准。**

## 机制：一条新词是怎么被发现的

一句话：**信号找名字 → 模型判名字 → 配额选名字 → 读名字、提通用词 → 数据定价 → 复盘校准。**

![雷达的机制：①–⑩ 信号 → 名字判断 → 配额 → 新词表 → 日报 → 复盘；慢线每周单独跑；紫色是后加的 ⑧⑨⑩、慢线和精度段](docs/make_diagram/radar.zh.gif?v=20261018)

图是 2026-10-18 按当前代码重画的：紫色是 0.4 之后加的（⑧⑨⑩、慢线、精度段），灰色虚线是复盘结果回到日报。下面是同一流程的文字版。

```
① X   ① HF   ② GitHub   ③ sitemap   ③ 新站   ④ GSC
⑥ 收入   ⑦ 求助   ⑧ 官方   ⑨ HN   ⑩ PH
        │
        ▼  原始候选：帖子 / 仓库 / 网址 / 产品 / 求助
  terms.py  抽名字
        │
        ▼
  judge  打分：是具体东西的名字，还是普通词？
        │
        ▼
  entity  合并同一个东西的不同写法；known / stop 过滤
        │
        ▼
  select  20 个可见名额按信号轮发；每天挑 5 个名字来读
        │
        ▼
  usecases  取证 → 提通用词 → 筛选 → 搜索量 → Trends → 首页 → 决策
        │
        ▼
  store（terms / signals / reviews / samples）──► report.md / report.json
        │
        ▼
  复盘：1/3 天本地免费；7/14 天 Trends；慢线 14/30
```

### 八步

| # | 步骤 | 代码 | 做什么 | 关键旋钮 |
|---|---|---|---|---|
| 1 | 采集 | `sources.py`、`breakout.py`、`sitemaps.py`、`new_sites.py`、`hn.py`、`official.py`、`ph.py`、`revenue.py`、`asks.py`、`gsc.py` | 每个信号吐一批候选；一个信号挂了只占一行，不拖垮整次运行 | 账号、sitemap、各信号的阈值 |
| 2 | 抽名字 | `terms.py` | 从帖子、标题、README 里抽「像名字」的短语 | 停用词、长度、X 的点赞门槛 |
| 3 | 判名字 | `judge.py` | 小模型给每个词 0–1 分：一个具体东西的名字，还是普通词 | `judge.model`、`judge.min_score` |
| 4 | 合并 | `entity.py` | 同一个东西的不同写法并成一行；只由 sitemap/新站找到的词标 `echo` | 合并规则（保守） |
| 5 | 选谁上桌 | `select.py`、`usecases.names_to_read` | 20 个可见名额按信号轮发；每天挑 5 个来读 | `usecases.per_day`、`recheck_days` |
| 6 | 读 + 提词 | `usecases.py` | 取证（推文/README）→ 模型提通用词 → 相关查询 → 筛选 | 模型、`RELEVANT_MIN` |
| 7 | 定价 | `usecases.py`、`benchmarks.py`、`competition.py` | Google Ads 月搜 → Trends 形状/规模 → 首页 | `min_daily`、基准篮子、`competition.max_rows` |
| 8 | 记忆 + 复盘 | `store.py`、`review.py`、`precision.py` | 入库；1/3 天本地，7/14 天 Trends；慢线 14/30；月度精度抽样 | 窗口、`per_day` |

### 几个容易被忽略的设计

- **判名字不是判关键词。** 模型只回答「这是不是一个具体东西的名字」，不判断有没有搜索量、值不值得做。名字分 0.5 是「算名字」的线，0.8 是「值得花一次读」的线。
- **每天只读 5 个名字。** 读一个名字要取证、提词、筛选、量、Trends、首页，约 $0.05 和一分钟；所以先选 5 个。没被读到的名字留在库里，等它的信号再响。
- **`min_volume` 不是门槛。** 新词常常没有量；低于阈值只标 `below_threshold`，不丢行。「优先/观察/跳过」看的是「有没有涨 + 规模 + 首页」，不是单看月搜。
- **配额不是硬砍。** 20 个可见名额按信号轮发；只有一个信号有名字时它就填满，报告会提示「这个信号占了多数」。这是为了防止 X 把名额吃光，不是为了凑比例。
- **慢线不占快线名额。** 组合词只进自己的表，不参与快线的 5 个读、不进 14 天复盘；被快线信号命名后才翻成快线。

### 一个例子：solidcraft

2026-10-18：GitHub 爆发 4,348★、422/天 → 名字分 0.95 → 进当天的 5 个读 → 读 README → 提出「open source parametric cad」「ai cad modeling」等写法 → 量：名字 162/天，写法暂无量或低于阈值 → Trends：名字 10-13 开始涨 → 首页：3 个弱站、KD 0 → 决策：**观察**（涨了，但规模还小；首页能进）。

这一行背后是完整的八步：信号 → 抽名字 → 判名字 → 配额 → 取证提词 → 量/Trends/首页 → 决策 → 入库复盘。

### 老词从哪来

这是最容易误解的一点：**雷达的主要目标是新名字，不是「发现老词在涨」。** 老词通过三条路进来：

1. **名字 → 通用词（主路径）**：模型读完这个名字的证据，写出「一个没听过它的人会搜什么」。SynthID Detector 拿到的是「ai photo detector」「google ai detector」「ai detector」；这些是已经存在的老词，雷达只负责把它们找出来、量出来。
2. **慢线的组合词**：`ai {品类} {动作}` 的种子（20 × 8 = 160 个）丢给 Google suggest，展开成「ai tattoo generator」这类**旧词根的新组合**。这是每周单独跑的慢线，不是从名字反推。
3. **复盘回流（只测不选）**：通用词会作为线索入库，按慢线 14/30 天复盘，看名字有没有把老词带起来。现在**只统计，不回灌选词**。

**没做的：独立发现「上升期老词」。** 目前没有一个通道会说「ai humanizer 自己在涨」而不需要新名字。Trends Rising 不是发现通道，慢线也只做组合词。如果你以后想让雷达发现「老词新涨」，这是要新加的一条通道（Trends Rising / 相关查询 / 老词种子表），也是最大的一个优化方向。

### 每天只有 5 个名字，怎么选

1. **先筛「值得读」**：`names_to_read` 只从「东西」类信号里选（X、HF、GitHub、新站、收入、官方、HN、PH），名字分 ≥0.8；只由 sitemap 找到的词不算；同一个东西的不同写法先合并。
2. **再排「今天读谁」**：`due` 先放新名字，再放 3 天前读过一次的；每天最多 `usecases.per_day`（默认 5）个。
3. **不是完整轮换**：排第 6 的，要等它的信号再响一次；所以 `due` 会增长，报告会打印待查数。
4. **这是成本/覆盖的取舍**：`per_day` 是旋钮；调大更全，但更贵、更慢。

### 快线 / 慢线

| | 快线 | 慢线 |
|---|---|---|
| 找什么 | 新出现的专名（模型、产品、仓库） | 组合词/通用词（`ai {品类} {动作}`） |
| 怎么发现 | ①–④、⑥–⑩ 的发现信号（⑤ 是复盘，不算发现） | Google suggest（免费），160 个种子 |
| 什么时候跑 | 每天 `daily` | 每周 `slow`（`--free` 跳过付费步骤） |
| 报告 | `report.md` / `report.json` | `slow.md` / `slow.json` |
| 复盘窗口 | 1/3/7/14 天 | 14/30 天 |
| 名字名额 | 有（每天读 5 个） | 没有，只进新词表 |

隔离是结构性的：慢词存在 `terms.window='slow'`，不进快线的名字名额（`select.SLOW`）、不被读（`usecases.READ_KINDS`）、不进快线复盘（`due()` 和 `summary()` 过滤）。如果一个慢词后来被快线信号命名，它的 `window` 翻成 `fast`，从那天起按快线复盘。

## 信号：它在哪里找

①–④、⑥–⑩ 是发现信号；⑤ 是复盘；「新词表」和「名字判断」是发现之后的后处理，不是信号。

| 信号 | 抓什么 | 需要 | 花费 |
|---|---|---|---|
| ① X | 你关注的账号里，60 天内第一次出现的名字 | AIsa key | 每个账号每次 $0.003 |
| ① Hugging Face | 新进热门榜前 50 的模型和 Space（大家实际在试的 demo）；量化版、微调版和模型自己的 demo 归到同一个基础名下 | 无 | 免费 |
| ② GitHub 爆发 | 创建不到 14 天、至少 300 星，且平均每天涨 200 星以上，或比昨天多 400 星的仓库；附带大家实际会搜的写法（「niko strata」） | 无（有 GitHub token 限额更高） | 免费 |
| ③ 竞品 sitemap | 某个站新增的几个网址共用、而它的旧网址里很少出现的词。示例配置盯着 8 个 AI 工具导航站（toolify、aixploria、ai-bot.cn、opentools、dang.ai、clipfly、aitoptools、futurepedia）和 4 个 MCP、skill 目录 | 你列出的 sitemap | 免费 |
| ③ 新站 | 近 90 天注册且首次被收录、已经有 20 个以上排名词的域名 | AIsa key | 每个查询约 $0.13，每周一次 |
| ④ Search Console | 你的站第一次获得曝光的查询词（用新鲜数据） | 你自己的 Google 授权 | 免费 |
| ⑤ 复盘 | 快线 1/3/7/14 天、慢线 14/30 天；1/3 天本地免费，7/14/30 天查 Google Trends，和它自己的基线比；按信号统计命中率和提前天数 | AIsa key | 每个搜索写法 $0.0012 |
| ⑥ 收入 | 有人付钱的产品，来自 TrustMRR 核验过的收入：增长最快的（30 天收入 $500 以上）和最新上榜的；上次 $0、这次过了门槛的排最前。它自己的介绍会作为依据交给新词表 | TrustMRR key | 免费，6 次请求，每周一次 |
| ⑦ 求助 | Reddit 上大家在要什么（"is there an AI tool that…" 等 12 种问法）：模型留下 AI 工具能解决的求助和抱怨，把每件事写成大家会搜的说法；有搜索量的再做首页竞争检查 | AIsa key | 每周约 $0.12 |
| ⑧ 官方 | 六个实验室/机构的 RSS（OpenAI、Google AI、DeepMind、Hugging Face、Mistral、Microsoft Research）最近 7 天的发布；标题里取名字，发布词和动名词过滤 | 无 | 免费 |
| ⑨ Show HN | 最近 30 小时、30 分以上的 Show HN，最多 25 个名字；每个帖子只报一次 | 无 | 免费 |
| ⑩ Product Hunt | AI 主题最近 26 小时、50 票以上，按票数排序 | `PH_API_KEY`（开发者 token） | 免费 |
| 新词表 | 针对当天的新名字：找出它背后的通用搜索词（大家拿这个新东西做什么），逐个估算规模、看首页还有没有位置，并给出决策 | AIsa key；[GoAnyAPI](https://goanyapi.com) key 可选 | 5 个名字约 $0.25–0.30（含 GoAnyAPI） |
| 名字判断 | 小模型给每个词打分：是某个具体东西的名字，还是普通词？ | AIsa key | 每次不到一美分 |

价格是 2026 年 10 月 AIsa 的实际收费。按示例配置（35 个 X 账号，每天跑一次 `daily`，新词表读 5 个名字），单次约 **$0.34–0.40**（2026-10-18 实测 $0.395）；周跑一次慢线约 $0.19（首次 $0.349，调参后未复测）；月跑一次精度 $0.09；一个月合计约 **$12**。少读几个账号或减少名字，费用按比例下降。建议把日上限设在 $1。

## 快线细节

### 名字判断与合并

- **帖子里的名字**（`terms.py`）：首字母大写的词、带数字的词（`Qwen3.8`）、中间有大写的词（`HyperFrames`）；名字后面的数字会并进去（`Opus 5.5`）。两个账号都用过的名字算数；只有一个账号用的，需要 100 个赞，而且必须明显是名字。
- **官方 / HN / PH 的名字**：标题开头 1–3 个词，去掉发布词和动名词；只有一个 maker 名、没有版本号的（`openai`）不算；每个帖子/产品只报一次，低于门槛的以后再涨上来仍算新。
- **sitemap 里的上升词**：按不同网址计数，并和这个站自己的基线比，所以一个长网址造不出一波假信号。
- **合一件事**（`entity.py`）：只有「一个是另一个的连续一段、多出来的词是 maker/格式/版本/尺寸」才合并；`pro` / `sol` / `max` 这类变体不合并。合并错了比留个重复更贵。
- **名字判断**（`judge.py`）：每 25 个词一次模型调用，每个词附带最多三处出现的原文。调用失败时报告照常发出，只是不排序。
- **`echo`**：只由 sitemap/新站找到的词保留，但标 `echo`，不进复盘（省 Trends 预算）；sitemap 词不在可读信号里，新站是「东西」信号、可能被读。它的用途是精度抽样。

### 新词表：从证据到一行决策

只有名字是不够的。「SynthID Detector」作为关键词寿命短，而且是 Google 的；它做的那件事「ai image detector」才是大家会一直搜的词。雷达每天把新名字再读一遍，把两种词写进同一张表：

```
| 关键词 | 类型 | 来自 | 新词? | 估算日搜 | 规模 | 开始上涨 | 现在 | 首页竞争 | 决策 |
|---|---|---|---|---|---|---|---|---|---|
| **solidcraft** | 名字 | — | 是 | 162 | 已知 | 2026-10-13 | 还在涨 (US) | 能进 · 3 个弱站 · KD 0 · 已有 312 个页面 · 3 家在投广告 | 观察 |
| **free llm api** | 通用词 | beam | 否 | 79 | 已知 | 2026-10-14 | 还在涨 (US) | 一般 · 0 个弱站 · KD 22 · 有广告 · 已有 71 个页面 | 观察 |
| **gpt 6.1 soul** | 名字 | — | 是 | 0 | 已知 | 2026-10-04 | 回落 | — | 跳过 |
```

（2026-10-18 一次真实运行的节选，省略了峰值、近 7 天比等列）

它是怎么做出来的（`radar/usecases.py`）：

1. **取证**：搜提到这个名字的高赞帖子（X 高级搜索，近 14 天、至少 50 赞）；如果是仓库，再读它的 README（前 3,000 字）。
2. **提词**：模型读完证据，针对它看到的每一种用法，写出普通人会搜的关键词，并附上原话作依据（最多 6 个，不许用名字本身或 maker 名）。借别的产品名字的写法（「photoshop alternative」）会保留并标 ⚠。
   如果配了 GoAnyAPI 的 key（可选），雷达还会取这个名字在 **Google Trends 里的相关查询**：大家实际把什么词和它一起搜。这些行带 🔎。包含名字本身的查询列为它的长尾；本身是别的新东西名字的查询单独记为线索。
3. **筛选**：再调一次模型，给每个写法打分：这个名字能不能回答这个搜索；同时标出品牌、认出别的东西的名字。相关性低于 0.6 的丢掉。
4. **搜索量**：一次批量查询，取剩下写法的 Google Ads 月搜索量。**低于 `min_volume` 的不丢**，标成 `below_threshold`；没量的标 `unknown`。量只是决策的一个输入，不是门槛。
5. **Trends**：每个写法先单独查一次，得到曲线形状（是不是新词、哪天开始涨、峰值、近 7 天比前 7 天、现在的走势）；名字再和基准篮子里的每个词各查一次（默认 6 个：`chatgpt`、`ai image generator`、`ai video generator`、`text to speech`、`canva`、`pdf converter`），得到规模。篮子不通过月度检查的词会被剔除并在表下写明。
6. **首页竞争**，只查会被采取行动的行（最多 8 行）：Google 第一页（每词约 $0.002）、第一页上每个站的评分（GoAnyAPI，每站 $0.002，保留 30 天）和关键词难度（每次 $0.012）。有 GoAnyAPI key 时，还会看谁已经在为这个词做东西、谁在为它付钱：近一个月标题里带这个词的页面数（「已有页面」）和在这个词上投谷歌广告的域名（「在投广告」，来自广告透明度），每行 $0.008。

日搜是估算值。通用词用它自己的 Google Ads 月搜索量，沿它自己的 Trends 曲线推到今天。再用这些词反推出基准篮子的规模，名字还没有搜索量数据，就对比篮子来估。规模读不出来时，用领先规则：≥2 个信号发现它且名字分 ≥0.8 也算「优先」。

决策：**优先** = 近 30 天涨过、现在还在高位、估算日搜不低于 `min_daily`。**观察** = 涨了但规模小，或还太早读不出，或没动但本身有这个规模的稳定需求。**跳过** = 已回落，或没动且规模小。

首页 `挤满` 的 **优先** 会降成 **观察 ↓**：还在涨，但首页被强站占满。`能进` = 前十里有 3 个以上评分低于 30 的站，或难度低于 20；`挤满` = 一个弱站都没有、难度 40 以上；其余为 `一般`。

标记：🎬 视频、🎙 语音、🖼 图片 说明它产出什么，一般用户愿意付费的顺序是 视频 > 语音 > 图片 > 文字；同等条件的线索按这个排序。⚡ = 有 1,000 赞以上的帖子在手把手讲一套手动流程，或在跟一个热梗：还没人做成一键工具。按标记行动前先读原帖。

从我们最早跑的 8 个名字看，对它应该有这样的预期：

- **名字涨了；通用词在五天内大多没涨。** PhotoCraft、Claude Haiku 5.5、SynthID Detector 的搜索都明显上升。它们背后的通用词里有一个动了：PhotoCraft 出现后，「photoshop alternative」在美国连续五天比之前高出约 80%。这张表读的全球日数据几乎没反映出来（2、1、1、2、4、2），而另一个来源的美国日数据看得很清楚。所以全球数据显示「没动」，不能证明这个词真的没动。配了 GoAnyAPI 的 key 后，规模较大的行改读单个国家的数据。
- 这张表今天靠得住的用处，是告诉你**一个新东西对应的是哪个已有需求、这个需求有多大**（「ai image detector」约每天 2,500 次搜索）。通用词会不会跟着名字涨，要等慢线 14/30 天复盘才知道。
- **Google Trends 最后两天的数据没有结算**（互不相关的词会返回 0 和 100，像尖峰）；代码里所有读 Trends 的地方都会丢掉这两天，上涨必须持续两天才算数。Google Ads 的搜索量滞后约两个月。

### 某个数据源没配或挂了的时候

表照常产出，但会变薄，并且会写明缺了哪一块：

| 情况 | 表里少了什么 | 表下面会出现的一行 |
|---|---|---|
| 没配 `GOANYAPI_API_KEY`（默认就是这样） | 没有 🔎 行、没有名字的长尾、没有「一起被搜的其他名字」、没有 `(US)` 走势。通用词只来自模型，走势全部读全球数据 | 「相关查询未开启：设置 GOANYAPI_API_KEY 后…」 |
| GoAnyAPI 的 Trends 挂了 | 这一次运行等同于没配 key | 「相关查询失败：…」和「国家数据获取失败，已退回全球数据：…」 |
| 某个名字的 AIsa 推文搜索失败 | 这个名字的推文证据。仓库还有 README 可用；没有 README 的模型或产品就只剩相关查询 | 「推文搜索失败，这次只用了 README 和相关查询：…」 |
| 某个名字既没有推文也没有 README | 它的通用词；名字自己那一行还在 | 「没找到帖子或 README：…」 |
| 当天没有名字得分 0.8 以上的「东西」类线索 | 整张表 | 「今天没有要读的名字…」 |
| AIsa 的搜索量或 Trends 查询失败 | 整张表：这两项没有替代来源 | 表的位置直接显示报错 |

表变薄不等于今天没动静。下结论说「什么都没涨」之前，先看表下面这几行。把配置写成 `"usecases": {"per_day": 0}`，或者加 `--skip usecases`，可以关掉它。

### 复盘：1/3/7/14 天和 14/30 天

| 线 | 窗口 | 怎么读 | 花费 |
|---|---|---|---|
| 快线 | 1 天、3 天 | 本地免费：`name_real` = 判断分 ≥ `review.name_real_score`（默认 0.80）；`persistence` = `last_seen > first_seen` | 免费 |
| 快线 | 7 天、14 天 | 最终检查时一次拉一条 Trends 序列，按 `first_seen + 天数` 切出两个窗口 | 每个搜索写法 $0.0012 |
| 慢线 | 14 天、30 天 | 同上，一条序列切两段 | 同上 |

- 一个搜索写法「涨了」= 报出之后的峰值 ≥ 它自己之前基线的 2 倍且高出 10 点；有旧含义的词（「strata」：岩层）基线本来就高，不算。
- 每线每天最多 5 条（`review.per_day`）。这是抽样：新线索约 20 条/天，`due` 会增长；报告会打印每线待查和到期数（2026-10-18：快线待查 58、慢线 24）。
- 7 天/14 天的行在最终检查时一起产生，不会提前 7 天查；还没满 14 天的词要等下一次检查。
- 一批 Trends 失败只影响那一条线，词留在待查里，错误写进报告的 ⑤ 和 `runs.errors`；一个词缺一个变体答案时也留在待查里。
- `name_real` 读的是检查时的判断分，`record()` 之后还能重新打分；它回答的是「检查时它还是不是个名字」，不是「第一天是不是」。
- 第一批付费行：快线 **2026-10-29**、慢线 **2026-11-14**。在那之前报告写「Trends 没有到期（第一个检查在 2026-10-29）」。

### 精度抽样（sitemap / 新站的 echo 词）

`python -m radar precision --n 10` 抽 10 个只有 sitemap/新站信号、还没抽过的 `status='echo'` 词，一次 Google Ads 批量查它们的月搜，标成 `new`（低于阈值）/ `searched`（≥ `review.sampling.existing_volume`，默认 1000/月）/ `unknown`（没查到量）。2026-10-18 首跑：10 个样本，7 new / 3 searched（aws 368k、bitbucket 33.1k、engram 12.1k），0 unknown，花费 **$0.090**。报告和 `leads` 汇总最近 90 天。

## 慢线：组合词

慢线不是「发现老词在涨」，是「把旧词根组合成新的搜索表达」。

- **种子**：`slow.objects`（20 个品类：video、image、photo、headshot、logo…）× `slow.actions`（8 个动作：generator、editor、remover…）= 160 个 `ai {品类} {动作}`。
- **展开**：每个种子一次免费的 Google suggest，拿到候选；候选必须带品类词（复数也算）、2–6 个词、不以疑问词开头、不是 `known_terms`。
- **测量**：和快线同一条链——Google Ads 量、Trends 形状、日搜、首页竞争、决策。每类最多 8 行，近似重复最多 3 条；预算上限 120 个量 / 25 条 Trends / 5 个首页，最终最多 30 行。
- **输出**：`slow.md` + `slow.json`，每周一次；`--free` 只列候选，不花钱。
- **隔离**：`terms.window='slow'`；不占快线名字名额、不被读、不进快线复盘；被快线信号命名后翻成 `fast`。
- **成本**：首次 $0.349；调参后估计约 $0.19，下一次付费跑验证。

## 现在能信什么 / 还没验证

- **名字判断**（`gpt-4.1-mini`）：拿我们自己日常使用中、之前的判断器放行的 170 个词重判，它同意 149 个。它拒掉的 21 个里大部分是噪音（sitemap 路径碎片、`asd`），真正漏掉的名字约 3 个；40 个普通词（`dashboard`、`pricing`、`today`）没有一个被放行。
- **命中率**：快线的 1 天/3 天窗口已经在跑（2026-10-18：44 条 1 天、13 条 3 天；1 天里 30 个名字通过强名字线，14 个没有），7 天/14 天要等 **2026-10-29**，慢线 14/30 天等 **2026-11-14**。唯一一条手工放进去的检查是 Strata，命中，比 Trends 曲线起来早 3 天。
- **2026-10-18 的完整一天**：`daily` **$0.395**（`runs` #5，无错误），20 条新线索，57 条免费复盘；`precision --n 10` **$0.090**，7 个新名字 / 3 个已经被搜过，0 个查不到量。
- **`name_real` 是判断器分数**（≥0.8），不是人工标注；**`precision` 是月搜阈值**（≥1000/月算「已经被搜过」），不是「这个产品是否已存在」的判定。50 个名字的人工抽检还没做。
- **复盘是抽样**：每线每天 5 条，新线索约 20 条/天，`due` 会增长；2026-10-18 快线待查 58、慢线 24。
- **7/14 天行在最终检查时一起产生**，不会提前 7 天查；还没满 14 天的词要等下一次检查。
- **慢线 30 天窗口**用的是一条 61 天的 Trends 序列，端点是否返回这个跨度要到 2026-11-14 才知道；当前 24 个慢词大多是迁移来的通用词，不代表 M4 的组合词。
- **没有调度器**：`daily` / `slow` / `precision` 都手动跑；`.github/workflows/radar.yml` 是参考，默认关闭。
- **benchmark 手动刷新**（`scripts/bench_check.py --apply`）；SQLite 的 `keywords` 表还没有写入；新词表的 `新词?` 列仍读 Trends 基线，不是 `first_seen`。
- **日搜是估算**：Google Ads 月搜滞后约两个月，月搜几百的词读不准；首页竞争只查会被采取行动的行（最多 8 行）。
- 内置停用词和 Hugging Face 名字清洗是按 AI 模型和 agent 工具领域调的。换领域请加 `stop_words`。

## 优化方向

| 环节 | 现在 | 可调 / 瓶颈 |
|---|---|---|
| 信号覆盖 | 11 个来源；35 个 X 账号；12 个 sitemap | 加账号/站点；X 一天读一次还是三次；新源（Discord、YouTube、Steam…） |
| 名字判断 | `gpt-4.1-mini`；0.5 算名字、0.8 才读 | 换模型；改阈值；50 词人工抽检；误报/漏报 |
| 合并 | 保守；maker/格式/版本/尺寸才并 | 漏并、误并；`same_entity` 是 O(n) |
| 配额与预算 | 20 可见、5 读/天、3 天复读 | `per_day`、`recheck_days`、轮换；`due` 增长 |
| 提词 | 模型 + GoAnyAPI 相关查询；筛选 0.6 | 提示词、模型、筛选阈值、品牌处理 |
| 量/形状 | Ads 月搜；Trends 全球/美国；6 词篮子 | 篮子校准；Ads 滞后；最后两天；慢线 61 天 |
| 首页 | 最多 8 行；弱站/KD/广告/页面数 | 只查行动行；GoAnyAPI 稳定性 |
| 复盘 | 1/3 免费、7/14 付费、5/线/天 | 抽样 vs 全量；人工标签；**回灌选词（未做）** |
| 老词发现 | 只从名字反推 + 慢线组合 | **没有独立的老词上升通道**（Trends Rising/种子表） |
| 慢线 | 20×8 种子、周跑 | 种子表、成本、30 天验证 |
| 运维 | 手动；无调度器 | VPS + 远端 MCP（未来） |

**先看哪一块**：等 2026-10-29 的 7/14 天数据。如果名字命中率高、但通用词不动，问题在提词/筛选/复盘；如果名字命中率就低，问题在信号/判断/配额。不要在还没有命中率的时候靠感觉改权重。

## 运行参考

### Key 与可选数据源

所有付费的部分都走 [AIsa](https://go.aisa.one/yansen-zhu)：X 帖子、Google Trends 和域名数据（背后是 DataForSEO）、判断名字的模型。一个 key，按次付费，不用分别订阅 X API 和 DataForSEO。上面是推荐链接。

**可选：`GOANYAPI_API_KEY`**（[goanyapi.com](https://goanyapi.com/r/ga-95708898fb)）从两方面改进新词表，每天约 $0.07：给每个名字加上 Google Trends 的相关查询；名字和规模较大的通用词（月搜 1,000 以上，最多 8 行）的走势，改用单个国家的 30 天日数据来读，结算到昨天。这些行的「现在」一列后面会标出国家，例如 `还在涨 (US)`。这个服务很新（2026 年 8 月才发布）；测试时每次调用 20 到 55 秒，大约十次有一次失败，所以雷达会试两次，失败就写在表里。

`PH_API_KEY` 是 Product Hunt 开发者后台的 token（公开读，免费），不配就没有 ⑩。`TRUSTMRR_API_KEY` 不配就没有 ⑥。没有 AIsa 的 key 时，免费的信号照常运行（Hugging Face、GitHub、sitemap、Search Console、HN、官方 RSS），只是报告里所有词不分先后列出。

### 快速开始

需要 Python 3.10 或更高版本。雷达本身只用标准库。

```bash
git clone https://github.com/pang3fan-creator/keyword-radar
cd keyword-radar
cp config.example.json config.json      # 然后编辑：你的 X 账号、sitemap、主题；想要中文报告把 lang 改成 "zh"
cp .env.example .env                    # 填 AISA_API_KEY（可选 GOANYAPI_API_KEY、PH_API_KEY）
python -m radar daily --out report.md
```

也可以直接 `export AISA_API_KEY=...`，`.env` 里的同名值会覆盖 shell 变量。

第一次运行只是建立快照：昨天的 X 词表、星数、sitemap 网址都还没有，所以只会报出 GitHub 爆发仓库（它不依赖昨天的数据）。从第二次运行起，每个信号都会报告变化。

### 命令

| 命令 | 做什么 | 花费 |
|---|---|---|
| `daily --out report.md` | 全部信号 + 新词表 + 复盘，每天一次 | 约 $0.34–0.40 |
| `sources --out sources.md` | 只跑 ① X 和 HF，几小时一次 | $0.003 × 账号数 |
| `slow --out slow.md` | 慢线组合词，每周一次（`--free` 只列候选） | 约 $0.19（首次 $0.349） |
| `precision --n 10` | 名字精度抽样，每月一次 | 约 $0.09 |
| `leads --days 7` | 看库里的线索和复盘 | 免费 |
| `keywords "名字"` | 按需出新词表 | 每个名字约 $0.05，每次调用另加 $0.09 |
| `pains "ai headshot"` | 痛点 | 每个词约 $0.05 |

`daily` 带 `--skip x,hf` 时，会列出 `sources` 在过去 24 小时记下的线索。如果你每天只跑一次，直接用 `daily`，什么都不跳过。`sources` 只在有新名字时才写报告。

其他参数：`--skip` 可选 `x,hf,breakout,sitemaps,newsites,revenue,asks,gsc,review,judge,usecases,tutorials,hn,official,ph`；`--new-sites` / `--revenue` / `--asks` 让周信号今天就跑；`--free`（slow）跳过所有付费步骤；`--n`（precision）指定样本数；`--json`、`--days`（leads）、`--mail`、`--state DIR`。

### 报告长什么样

2026-10-18 一次真实运行的节选（中文报告，`"lang": "zh"`）：

```
### 候选新词(名额按信号轮发;已覆盖的会标出)

| 词 | 信号 | 名字得分 | 已覆盖 | 搜索变体 | 例子 |
|---|---|---|---|---|---|
| **beam** | huggingface:发布公告 | 0.90 | 无 | — | Welcome Beam: a 501B open model you can own, custo |
| **solidcraft** | GitHub 爆发 tangency-labs/solidcraft ★4348(均 422/天,一天 +732) | 0.95 | 无 | tangency-labs solidcraft, tangency solidcraft | tangency-labs/solidcraft: SolidCraft: an open-sour |
| **esp32sim** | HN 125 分,13 条评论 | 0.90 | 无 | — | Show HN: Esp32sim – Run ESP32 firmware in the brow |
| **nitrostack** | Product Hunt 275 票 | 0.90 | 无 | — | Build, test, and deploy MCP servers in one place |

### ⑤ 复盘(1 天、3 天免费;快线 7 天、14 天;慢线 14 天、30 天;后两者查 Google Trends)

今天已查:1 天 44, 3 天 13(免费);Trends 没有到期(第一个检查在 2026-10-29)。

| 信号 | 1 天名字 | 1 天强名字 | 3 天名字 | 3 天又出现 |
|---|---|---|---|---|
| ⑧ 官方 | 2 | 2/2 | 0 | — |
| ① X | 25 | 15/25 | 0 | — |
| ① HF | 2 | 2/2 | 0 | — |
| ② 爆发 | 18 | 14/18 | 13 | 0/13 |
```

`daily` 还会在 Markdown 旁边写一份 `report.json`，包含生成报告用到的全部数据。

### config.json

| 字段 | 含义 |
|---|---|
| `lang` | `"en"` 或 `"zh"`：报告的语言 |
| `x_accounts` | `labs` 和 `bloggers`：要读的 X 账号。实验室最先说出名字；博主选你这个领域里新词靠谁传开 |
| `sitemaps` | 想看哪些站新增了什么页面。`index` 是一个 sitemap；如果它是 sitemap 索引，用 `shards`（正则）挑要读的子 sitemap。`pause` 是对这个站两次请求之间的秒数。`strip_locale` 去掉 `/en/`、`/zh-CN/` 这类前缀 |
| `topics` | 名称和正则：每个主题单独一节，列出匹配的线索、仓库和查询 |
| `known_terms` | 你已经有页面的词，或者永远不想看到的词。包含它或被它包含的线索会被标出，不进入复盘 |
| `stop_words` | 你这个领域的日常用词，追加到内置列表 |
| `judge` | `model`（AIsa 上任意对话模型）和 `min_score`（默认 0.5） |
| `breakout` | `window_days`、`min_stars`、`velocity_min`（每天涨星）、`delta_min`（比昨天多的星） |
| `hn` | `min_points`（30）、`top`（25）、`lookback_hours`（30） |
| `ph` | `min_votes`（50）、`top`（25）、`lookback_hours`（26）、`topic` |
| `official` | `feeds`（六个 RSS）、`max_per_run`（10）、`lookback_days`（7） |
| `slow` | 慢线的种子和上限：`objects`、`actions`、`template`、`max_queries`（160）、`max_volumes`（120）、`trends_max`（25）、`page_one`（5）、`max_rows`（30）、`per_category`（8） |
| `new_sites` | `queries`：名称和域名的 SQL LIKE 模式（`"%ai%"`），每个是一次付费查询；`weekday`（0 = 周一）；`window_days`（90）、`min_etv`（1000）、`min_keywords`（20） |
| `review` | `windows.fast`（[1,3,7,14]）、`windows.slow`（[14,30]）、`per_day`（每线每天 5 条）、`name_real_score`（0.8）、`sampling`（`per_run` 10、`existing_volume` 1000） |
| `usecases` | 新词表。`per_day`（每天读几个名字，0 = 关闭）、`model`、`benchmarks`（比规模用的基准篮子）、`min_volume`（低于它只标 `below_threshold`，不丢行）、`min_daily`（判为「优先」所需的日搜）、`recheck_days`（3）、`related`、`related_geo`、`country_trends`、`country_min_volume`（1000）、`country_max`（8） |
| `gsc` | `site`（`sc-domain:example.com`）和 `token_file`。留 `{}` 即关闭 |

`revenue`、`asks`、`tutorials`、`pains`、`competition` 的键见 `config.example.json` 和 `radar/config.py` 的 `DEFAULTS`。

添加某个站的 sitemap 之前，请先看它的 robots.txt，`pause` 不要低于它的 crawl-delay。示例配置每天总共几十次请求，按 `pause` 间隔发出。

### 附加信号：收入、求助、教程观众

- **⑥ 收入**：`TRUSTMRR_API_KEY` 配好后每周一读：近 30 天收入 ≥$500、增长最快的 30 个产品 + 最新上榜的 30 个；隐藏条目不读，公司全称换成网站名。每个产品的介绍会作为依据交给新词表。TrustMRR 的条款禁止转载数据，这些线索只供自己研究。
- **⑦ 求助**：每周按 12 种问法搜 Reddit，留下最近一周、得分 ≥2 的帖子；模型分类，把 AI 能解决的求助/抱怨写成大家会搜的说法；月搜 ≥50 的做首页竞争，其余作为点子列出。帖子可以引用，不要转载。
- **⚡ 教程观众**：对每天最多 3 条带 ⚡ 的线索，找热门教程视频（GoAnyAPI），读评论（AIsa，每页 $0.001），让模型挑出「哪一步太难、能不能一键搞定」。找视频需要 GoAnyAPI key。

### 痛点命令

`python -m radar pains "ai headshot"` 把大家对一类工具的抱怨归成缺口：Google 上这个词对应的 Chrome 扩展低星评论（GoAnyAPI；也可以用 `--extension ID` 指定）、Reddit 抱怨帖、热门教程视频评论（AIsa）。每个词约 $0.05。次数是读到的条目数，不代表市场规模。App Store、Google Play、Trustpilot 的评论，There's An AI For That 的求助板，Facebook 小组，都读不到。

### MCP 服务器

仓库不附带 Agent Skill 或 Claude Code 插件（2026-10-18 移除：三套接口各自漂，MCP 一套就够）。MCP 是 stdio 的本地服务，读运行它的那台机器上的 `state/radar.db`。

```bash
pip install "new-term-radar[mcp] @ git+https://github.com/pang3fan-creator/keyword-radar"
```

```json
{
  "mcpServers": {
    "new-term-radar": {
      "command": "new-term-radar-mcp",
      "env": {
        "AISA_API_KEY": "...",
        "RADAR_CONFIG": "/绝对路径/config.json",
        "RADAR_STATE": "/绝对路径/state"
      }
    }
  }
}
```

| 工具 | 返回什么 | 花费和耗时 |
|---|---|---|
| `recent_leads` | 雷达记下的线索，带复盘结论和各信号命中率 | 免费，立刻返回 |
| `keyword_table` | 你给的名字的新词表 | 每个名字约 $0.05，每次调用另加 $0.09；每个名字 40 到 90 秒 |
| `run_radar` | 跑一次 `sources` 或 `daily`，返回报告 | 付费，要几分钟。只适合第一次试用，定时运行应该交给 cron 或 Actions |

把 `RADAR_STATE` 指向定时任务写入的那个目录，`recent_leads` 看到的就是定时任务记下的线索；前提是定时任务和 MCP 服务器在同一台机器上。GitHub Actions 的缓存不在本机，本地 MCP 看不到它；要读 Actions 的结果，把 `report.json` 或 `radar-state` artifact 取回来。

### GitHub Actions

`.github/workflows/radar.yml` 每 8 小时跑一次 `sources`、每天跑一次 `daily`（`daily --skip x,hf`，X/HF 由 `sources` 先跑），状态存在 Actions 缓存里，报告写到每次运行的摘要页。默认关闭，需要你主动开启：

1. 把这个仓库放进你的 GitHub 账号（私有 fork 也可以）。
2. 把 `config.json` 从 `.gitignore` 里删掉，提交你的配置。配置里没有任何密钥。
3. 添加 secret `AISA_API_KEY`；可选 `GOANYAPI_API_KEY`、`PH_API_KEY`、`RESEND_API_KEY`、`EMAIL_FROM`、`RADAR_EMAIL_TO`、`GSC_TOKEN_JSON`。
4. 把仓库变量 `RADAR_ENABLED` 设为 `true`。

缓存是按运行恢复的：缓存没命中时，第二天只是重新建快照、报告为空；线索库会从头开始，所以在意复盘历史的话，定期把 `radar-state` artifact 下载下来。

### 文档

- [AGENTS.md](AGENTS.md)：协作契约——布局、命令、测试、成本、交接清单、当前状态。
- [docs/README.md](docs/README.md)：文档索引（现行 / 历史）。
- [docs/Roadmap/](docs/Roadmap/)：00 约束、01–04 路线调研、05 方法论、06 范围与垂直扩展。
- [docs/里程碑.md](docs/里程碑.md)：M0–M5 的开发记录（数字、提交、当时留下的问题）。

### 开发

```bash
pip install pytest markdown
python -m pytest -q tests
```

测试覆盖逻辑部分（名字提取、打分、存储、报告），不访问网络。跑单个文件更快：`python -m pytest tests/test_store_next.py -q`。

### 致谢

- [子木 @CoderJeffLee](https://x.com/CoderJeffLee)：新词表的想法来自他的建议，新名字和它下游的通用词应该放在同一张表里，每行给出决策。
- [饭特稀 | Fentix @fantexi997](https://x.com/fantexi997)：[GoAnyAPI](https://goanyapi.com)，相关查询和单个国家 Trends 走势这个可选数据源。
- [Jason Zhu](https://github.com/zhuyansen)：上游 [new-term-radar](https://github.com/zhuyansen/new-term-radar)，本项目的起点。

流程图由 `docs/make_diagram/make_diagram.py` 生成（2026-10-18 按当前代码重画；需要 `rsvg-convert` 和 `ffmpeg`）。

### 许可

MIT。这套雷达提取自 [agentskillshub.top](https://agentskillshub.top) 背后每天在跑的版本；本项目的改动见 [docs/里程碑.md](docs/里程碑.md)。

<!-- mcp-name: io.github.zhuyansen/new-term-radar -->
