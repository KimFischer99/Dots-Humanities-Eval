# 文学改编 Eval v3.3：施工方案与操作手册

版本：3.3｜资料核查日期：2026-09-24｜评分抽样修订：2026-09-25｜接手执行者：Codex

**当前状态：新版 scores-only Judge 流程已完整串行完成。** 新Judge hash `9208fde1645ea9fe55a18b10703cb850ba5f097a8ced2d3ccfce008ff6ce35fd`；dev 3、validation 6、rest 6，共15/15份严格JSON分数结果通过校验。旧版历史调用保留且未计入新版分数。人类与Judge总分均按 `H+7.5F+7.5D+5L` 分别计算；明细见 `.work/scores.json`，阶段对照见 `.work/judge_compare_*.json`。

## 0. 交付范围与最短入口

目标：在固定 Pi、单一 Skill、单次生成条件下，评价三个模型将给定文学材料改编为受约束中文短剧的表现；随后由人类先核对，Kimi K3 在同版 Pi 沙箱中评分。结论限定于本数据集和本运行条件，不宣称裸模型的普遍人文能力或参数规模的因果效应。

本包只保留两个执行脚本：`runtime.py` 管 Pi/容器/请求与轨迹，`eval.py` 管数据、机械评分、人工封存、Judge 校验与汇总。没有 Agent SDK 二次框架、数据库、工作流服务器、分布式队列、检索或多 Skill 链。

| 文件 | 用途 | 是否给被测模型 |
|---|---|---|
| `RUNBOOK.md` | 取段审计、调研、施工、提交规范合并在本文 | 否 |
| `dataset.json` | 私有原文、出处审计、实验条件与侧例 | 仅给 `model_task()` 投影后的当前 TASK；不发送出处或预拆解答案 |
| `rubric.json` | 五项自动检查、三维锚点、权重与计分原则 | 否；Judge 只取 `dimensions` |
| `SKILL.md` | 唯一生成Skill | 只注入正文 |
| `JUDGE.md` | Kimi 的评审角色和严格输出契约 | 只给 Judge |
| `eval.py`、`runtime.py`、`Dockerfile` | 校验、编排、固定环境 | 仅工具侧例可调用校验器 |
| `config.json`、`.env.example`、`.gitignore` | 模型配置、凭证入口和私有材料保护 | 否 |
| `test_eval.py` | 84 项离线单元/合同测试；构造响应仅用于测试代码 | 否 |
| `LICENSE`、`NOTICE` | 分发许可与改编出处 | 否 |

运行时自动产生的中间文件全部收在 `.work/`；不要把它们逐个当作提交附件。最终导出只有六个文件，见第 8 节。

**方案与材料审核：已完成（用户明确确认）。** dataset、Skill、rubric以当前审核版为准。15份盲评的人工F/D/L分数已封存；新版scores-only Judge的dev、validation、rest已完整串行运行并锁定。后续不得将旧Judge调用并入新版成绩。

### 0.1 后续任务的固定工作边界

- **文件边界**：仅在本目录 Eval_Kit 及本项目专用 Pi Docker 环境内工作。所有命令以 kit 为 cwd，文档、数据、运行与临时产物均留在 kit；不再读取或修改 kit 外的项目文件、原始素材、凭据或旧方案。
- **宿主职责**：只在 kit 内编辑、执行 Git/Python 编排和控制 Docker；固定 `DOCKER_CONTEXT=colima-eval`，复用已验收环境，不修改宿主全局配置、其他容器或项目。Pi 的任务内容仅在沙箱内执行。
- **网络边界**：除经固定网关发送已配置的模型 API 请求外，禁止 Codex、Subagent、Pi 和模型联网搜索、浏览网页或调用检索服务。Primary/Judge 禁用工具；T01/T02 仅在断网沙箱内使用既定 read/write/bash。参考文献链接是历史出处，不是后续联网指令。
- **环境维护**：默认使用现有镜像。若必须下载依赖、改变端点或扩大范围，先取得具体授权；不把构建/排错当作通用外网许可。
- **Git 边界**：本地仓库只跟踪可版本化的代码、配置、规则和文档。`.env`、`dataset.json`、`.work/`、`.work-*/`、临时文件保持忽略；私有完整数据和轨迹仍在 kit 内由哈希封存，不因 Git 忽略而删除。初始 Git 建立不等于实验冻结或对外发布。

### 0.2 当前进度与接续位置

已完成人工评分封存；根目录 `review.json` 保留原件，工作副本位于 `.work/review.json`。原冻结、39份生成结果、人工seal和旧Judge原答均保留。scores-only prompt/hash已锁定；新版15份Kimi评分与三阶段人工对照已落盘。新版运行记录与校准汇总见 `.work/judge_score_only_revision/final_summary.json`。依据人工样本中D均值最低的观察，两个原创SFT草稿已写入 `.work/sft.jsonl` 并通过H1-H5机械校验，待专家审阅；incident按用户指示由用户另行处理，不在本Eval中创建。

Judge执行阶段已完成；两条SFT草稿已机械通过且待人工验收。个人经历由用户另行处理。完整测试报告在 `.work/REPORT.md`；按用户最新要求，另整理可复用公开快照 `Dots-Humanities-Eval/`，有效结果与用量口径见该目录的REPORT和SUBMISSION_LIST。旧版Judge不纳入新版总分。

## 1. 文本有效性审计与正式数据

### 1.1 审计结论

九份文本已按用户校订决定同步，当前dataset已通过用户审核：红楼梦三处、变形记一处、中文哈姆莱特选段外两处，共六项；另六项指定保留。校订底本保存在sources.original_utf8，各选段保持连续切片，全文/选段哈希保存在每个source中。当前dataset为权威底本，调整前备份已清理；不得从历史版本回填。archive_sha256仅标识原接收ZIP，不代表校订后文本。

这里的“有效”指编码、可读性、任务适配、取段连续性与证据可定位；**不等于逐页核对了纸本版本、证明未进入预训练、证明具有公开再分发许可**。现代中文译本多未列译者；网文缺作者和原链接。这些缺项已标明，不自行补造。

表中行号对应dataset内当前校订底本original_utf8的物理行，不表示kit外原文件已被改写；历史定位备份已清理，以当前dataset定位为准。长度是选段非空白Unicode码点，包含标点，不是token。短古文、诗歌与英文不强行拉齐长度。

| Case | 实际采用材料 | 原文件取段 | 字符数 | 实验条件 |
|---|---|---|---:|---|
| C01 | 《变形记》开篇心理—动作段 | `变形记.md` 1—13 行 | 2143 | 90秒，禁止内白 |
| C02 | 同 C01 | 原文与全部其他任务字段完全相同 | 2143 | 同C01，仅允许至多2条内白 |
| C03 | 《红楼梦》元妃省亲节选 | `红楼梦.md` 1—12 行 | 1144 | 90秒，禁止内白 |
| C04 | 同 C03 | 原文与全部其他任务字段完全相同 | 1144 | 同C03，仅改为150秒 |
| C05 | 《左传》隐公元年用户节选 | `左传.md` 1—11 行 | 624 | 90秒，禁止内白 |
| C06 | 《哈姆莱特》第五幕第二场决斗尾声，中译 | `莎士比亚_ZH.md` 校订底本31—113 行 | 1352 | 90秒，禁止内白 |
| C07 | 李白长诗中的战乱段，非全诗 | `李白.md` 1—12 行 | 132 | 60秒，禁止内白 |
| C08 | 《奥德赛》第十卷基尔克段，非求婚者决斗 | `奥德赛.md` 1—67 行 | 1040 | 90秒，禁止内白 |
| C09 | 用户版本《宗定伯卖鬼》 | `搜神记.md` 1—3 行 | 356 | 90秒，禁止内白 |
| C10 | 用户提供《倒计时4659》第一章节选 | `网文.md` 1—73 行 | 1216 | 90秒，禁止内白 |

共10 Primary Cases、8个来源家族。当前dataset已删除cast、locations、adaptation_goal、adaptation_limits以及reference/focus/acceptable/failure；仅保留原文、出处与实验安排。旧运行轨迹仅作为历史证据，不进入新任务。

**原文独立理解契约**：生成user消息逐字等于source_text，不加标题、摘要或人物提示。system包含当前唯一Skill完整正文一次，末尾仅附target_seconds、interior_policy、output_language。相同case的三模型及工具对照system逐字一致；不同case只允许上述预登记条件不同。工具task.json仅含中性source_id=TEXT、原文及这三个条件。Judge也只收到该白名单TASK、rubric与匿名候选。

**输出与判分**：顶层source_id固定TEXT；cast和locations由模型自行声明id/name，scenes引用这些ID。cast可为空，locations/scenes非空。H1检查结构，H2检查表内ID唯一及场次/发话人引用自洽，不判断人物识别正确性。F根据原文评价人物身份、关系、动机、知情状态与材料边界，自报表也属于待评作品；D评价自主场景安排和组织。不设标准人物名单，不因合理省略、合并或诗歌的最小舞台承载自动扣分。权重仍为H20/F30/D30/L20。

### 1.2 校订与出处审计边界

原文保持用户已审核的当前dataset字节与取段边界。校订记录已完成其用途并清理；后续核查直接验证sources.original_utf8、连续选段及raw_sha256/text_sha256，不重新推翻用户确认的保留决定。

当前方案已移除逐篇人物、动机、知情状态、角色合并和情节结论，避免留下另一份预拆解答案。作者、译本、发表时间和授权缺项仍是出处审计问题，不把它们转为隐藏评分义务，也不宣称预训练曝光已排除。

### 1.3 成对与 Side 的边界

P1=C01/C02，只变 `interior_policy`；不是从全局禁令中删一句，实际是明确的许可开关。两例都不用内白仍可合格。P2=C03/C04，只变 `target_seconds`。脚本对 `task` 做字段级 diff；不要求输出内容机械地只差一个变量，也不凭单次采样声称因果效应已证实。

Side 不计入总体分数：

| Side | 比较基线 | 新增运行 | 范围 |
|---|---|---:|---|
| S01 英文《哈姆莱特》同段 | C06 中译；两边均输出中文 | 三模型各 1 次，共 3 次 | 英文原文件 79—259 行，2666 非空白码点；输入语言与译本共同变化，只是匹配式跨语言观察 |
| T01 工具辅助 | 各自模型的 C01 无工具结果 | M1/M2/M3 各 1 次，共 3 次 | read/write/bash；观察有提示的自检、读错、修复、落盘 |
| T02 工具辅助 | 各自模型的 C03 无工具结果 | M1/M2/M3 各 1 次，共 3 次 | 与 T01 同工具契约 |

默认共 39 份生成产物：30 Primary + 3 S01 + 6 工具 Side，不是39个独立原文。三家各有两个工具条件结果，只能作小样本探索性比较。工具循环带来额外交互/算力，不能把差异全部解释成纯工具效应。Side不计主分，也不自动追加Kimi评分；机械差异与轨迹单独报告，需要语言质量结论时由专家另作标记复核。

每个工具 Side 使用独立容器/上下文；输入和生成 Skill 与对应无工具基线相同，仅提供 `read/write/bash`。Skill 统一提示可写 `/workspace/script.json` 并执行 `python /app/eval.py check-script /workspace/script.json /job/task.json`。实际是否调用、调用顺序、失败后是否修改与复检由模型决定，不能称为完全无提示的自发行为。合理路径是写稿→校验→按错误修复/复检→返回同一JSON；不强制固定调用序列，也不由Codex替模型操作。

每份上限为8次工具调用、9次API请求、600秒；保持断网与权限隔离。完整trajectory记录工具名、参数、结果、错误、后续修订与最终回复，结束时另捕获 `script.json`。未落盘、未校验、校验失败及落盘内容与最终回复不一致均按实际轨迹报告；最终回复仍是作品，落盘文件不偷偷替代它。当前运行器不把“完成过自检”设为传输成功门槛。

## 2. 参考 benchmark 核查与采用边界

以下区分来源陈述与本项目设计。**没有查得一套可直接套用、同时覆盖中文文学改编/短剧/诗歌/三模型小样本的统一行业评分标准。** 本包是任务化、预注册的小型诊断评测，不冒称官方标准复刻。

| 参考 | 已核查及修正 | 本项目采用／不采用 |
|---|---|---|
| DramaChain Bench，2026-09 | 官方论文覆盖商业短剧生产链，重点从剧本意图到分镜/影像/成片及缺陷传播；不能直接称为本任务“文学原文→剧本”的已验证评分器 | 借鉴意图保真、呈现可执行性与缺陷证据；不搬入 63 个叶子维度、分镜/视频指标或作者系统的可靠性数值。[R1] |
| LongJudgeBench，2026-06，查阅 v2 | Judge 对长文本的能力需要独立验证；更多提示、参考或推理不是准确性的自动保证 | 缩短单次评审任务、保留原文与局部证据、人工先评和留出验证；不声称本次小样本能证明统计可靠性。[R2] |
| WritingBench | query-dependent criteria 是重要方法；其跨领域规模不是我们的小样本成绩可直接对标的基准 | 三个共享维度及原文证据要求；不对每个模型现编标准，不用另一模型自动生成的标准替代专家审核。[R3] |
| SkyScript-100M | 是剧本/拍摄脚本相关大规模数据资源；论文对规模的陈述不等于十亿条人工审美金标 | 借鉴文本向可呈现行动的转换；不据此宣称“35 字、4.5 字/秒”是行业统一标准，也不增加摄影分镜要求。[R4] |
| EQ-Bench Creative Writing v3 | 创意写作榜有较多提示、多轮生成及相对比较程序 | 借鉴风格多样性与输出质量判断；不为 3×10 引入 Elo/Glicko 或全量两两比较，避免扩大标注。[R5] |
| lechmazur/writing | 当前仓库与早期版本评分流程不同，需按版本看；相对/调整分的负值不等于不合格 | 借鉴约束元素是否自然融入；不把榜单名次当作 Kimi K3 的裁判资格证明，不将外榜分数与本分数相减。[R6] |
| Hemingway-bench | 作者主张专业写作者的整体判断，警惕清单替代写作质量 | 保留有锚点的整体语义/表达评价；不数华丽辞藻、比喻数量或使用“AI 腔词表”。[R7] |
| Judgemark | 用户给的 Reddit 介绍不是最新方法入口；已检查官方 v4 页面 | 写作者强不等于裁判准；裁判区分度也不等于每一判断都符合人类，仍需本任务校准。[R8] |
| SuperCLUE 中文写作 | 查到官方入口及项目，但未取得足够完整的该分项可复现评分协议 | 作为中文任务背景，不编造官方权重或宣称逐项遵循其标准。[R9] |
| Omdia 2026 中文创意写作 | 官方报告入口可确认；本次未取得完整付费正文/详细 rubric | 不把用户摘述的维度数量扩写成未经核查的评分细则。[R10] |

**本项目新增的规范选择**：H20+F30+D30+L20、0—4 档、每模型从10份Primary中固定种子随机抽评5份，人工专家与Judge共评同一批15份，均是本次为测量目标和负担作出的设计，不是上述论文给出的“公认最优权重”。

## 3. 低负担 rubric 与总体分数

### 3.1 自动部分 H：20 分

五项各 4 分，通过得 4，不通过得 0：H1 严格 JSON/字段/自报表/节拍结构；H2 输出表内ID唯一及人物、发话人、场景引用内部一致；H3 单句上限；H4 代理估时；H5 内白标签许可。所有模型使用同一代码，不让人类或 Judge 数字数/拍数。

字符数按 NFC 后的非空白 Unicode 码点计，标点计入；每条台词最多 35。代理估时 = 全部台词字符数/4.5 + 动作拍数×2.5，接受目标的 85%—115%，含端点。**这是被冻结的本任务规则，不是实际拍摄秒表或视频模型可生成性的证明。** 一拍塞入多个事件、把台词藏进动作等作弊式做法仍需 D 维语义判断。

结构无法解析时 H1 失败，H2—H5 标记 unavailable、贡献 0；不是宣称五种错误均已被观察到。可读的非 JSON 文本仍交人类/Judge 评文学质量，不自动连带全零。

### 3.2 人文部分：只评三个 0—4 分

| 维度 | 权重 | 一句话问题 |
|---|---:|---|
| F 材料保真与人物理解 | 30 | 核心因果/意象、关系、知情状态和材料边界是否保持？ |
| D 戏剧形式与组织 | 30 | 是否形成可感知的行动/交流，取舍、连续性、情绪推进是否适合预算？ |
| L 语言与角色表达 | 20 | 是否自然、具体、贴合人物/体裁，有表达辨识度而非空泛套话？ |

各维均用0—4档，具体含义以用户最新版 `rubric.json` 的dimensions/anchors为准，不再用旧版通用档位措辞覆盖各维标准。必须依据锚点独立选择整数，不设置默认分。

出处信息只供Codex收尾审计，不发送给四个模型，也不展示在盲评页面；预制参考卡已从当前dataset删除。模型与人类评审仅依据给定原文和公开实验条件判断；不以预拆解答案增加隐藏义务。诗歌以意象和呈现判断，不另加秘密剧情标准；合法内白不天然低分。主要不是指定中文输出时，L 至多1；专名外文不算此错误。

避免重复惩罚：机械超时只扣 H4；若同时 D 低，必须另有注水、主次失衡等独立语义证据。Judge只返回三个分数，复核线索由实际人工审阅另行记录，不另乘惩罚系数。

### 3.3 总分与合格分开报告

```text
单例 S = H + 7.5×F + 7.5×D + 5×L       （满分 100）
模型主分 = 恰好 5 个随机抽中 Primary S 的算术平均
敏感性分 = 在该模型被抽中的来源家族内等权平均
合格 = H=20 且 F、D、L 均至少 3
```

演算例（不是模型结果）：H20且三维均3时，S=80且合格；H20、F2、D4、L4时，S=85但不合格。报告主分同时列 H 均值、三维均值、合格数/5、抽中来源家族数及家族等权敏感性均值，不能只给一个排名。

主分依据每模型5份（每份从其10份Primary中等概率无放回抽取）；相对于全10例均值存在抽样波动。Side与未抽中的15份Primary不进主分或Judge评分。有限小样本不支持总体能力或显著性结论。

基础设施错误、Judge 缺失或输出不符合三分数契约：记 null，整体 incomplete，不补零、不补均值、不按九例重算分母。成功完成调用后的拒答、空答、截断/坏格式属于实际模型输出，要保留并按契约评，不因成绩差重跑。

## 4. 人工核对与 Kimi Judge

### 4.1 人类负担：15 份匿名复核与三维评分

全部Primary结果生成后，先运行 `python eval.py prepare-review`，再运行 `python eval.py review`。前者按固定种子从30份Primary中分层随机、无放回抽取15份，每个模型5份；样本及dev/validation/rest分组写入 `.work/review_plan.json`。新版本地HTML仅展示这15份匿名剧本、原始JSON及去出处的TASK/原文，不展示作者、书名、来源代号、Citation或独立参考卡。阅读视图展示模型自报人物/场景表并使用这些名称显示ID；自报表同样待审，不是参考答案。不补句、不改文本。

每份样本后只提供 F、D、L 三个分数选项；不要求粘贴原文、作品引文或填写判别依据。UI不显示模型名，样本顺序另行打乱；不要事后挑漂亮或容易打分的回答。`review.json` 保留评审者、时间、盲样本ID、输出哈希及三个分数，Seal据输出哈希校验候选未变。

人工封存前，Kimi不得接收真实候选。封存后仅对同一15份中的dev分组作提示校准；validation分组用于锁定后的留出对照；extension来源分组在 `rest` 阶段完成最终评分。每个分组的实际数量写在 `.work/review_plan.json`，不预设固定数量。人工分数在15份上一次性完成；Judge调试只用dev对照，不能利用validation意见调规则。

专家填写并保存 `review.json` 后由脚本封存哈希。Codex不得代写人类分数、把自动评分冒充人工或修改模型原答。人类检查发现材料不可满足/错误锚点，应暂停并声明协议变更；不能悄悄改完继承旧分数。

### 4.2 Judge 顺序

1. Kimi 先评抽中dev分组，每份新 Pi 沙箱/新上下文。
2. 对照人类，记录三维分差和同权重总分差。允许一次有记录的 `JUDGE.md` 措辞修订，或说明不修；不改已冻结的权重、原文、事实卡、评分锚点和 Skill。
3. 修订后重新评抽中dev分组，保留旧 Judge 结果，不覆盖；冻结最终 Judge hash。
4. 最后才评抽中validation分组，展示锁定版本在未用于调试来源上的情况。若验证仍有问题，诚实报告，不再调完重称“留出验证”。
5. 同一最终版本只评其余被抽中的extension来源样本（`rest`）。三个阶段合计恰好15份；未抽中的15份Primary永不送Judge，不计最终分。

人工封存之前仅允许Kimi的PONG连通性检查，不允许评价真实候选。Kimi只接收固定JUDGE指令、三维rubric、去出处TASK（含source_text）及匿名候选；不传REFERENCE、Citation、作者、书名、来源代号、模型名、人工分数、其他候选、原报告或招聘上下文。不加载生成Skill，不开启工具。候选若自行输出外部引用标记，保留原答并阻断向Judge发送，记录为待复核；不静默删改候选以通过检查。

Judge user输入恰好包含 `RUBRIC`、`TASK`、`CANDIDATE`：沿用已审核三维锚点、五字段白名单TASK和逐字候选。宿主保存sample_id、generation_id、Judge hash和human seal关联，不要求模型复述身份信息。输出必须是裸JSON对象 `{"F":整数,"D":整数,"L":整数}`，每项0—4；拒绝代码围栏、重复/额外/缺失键、字符串、小数、布尔值、null和非有限数。无理由、引句、Pointer或critical_errors字段，不自动去围栏或修答案。每份请求结束先保留原答再校验，无效即停止后续发送。

`compare`只对照当前Judge版本的同一分组，输出逐维分差、MAE、相差不超过1档比例，以及人工/Judge分别用 `H+7.5F+7.5D+5L` 计算的单例总分。`score`并列保存两套总分与每模型5份均值；不把人工分数覆盖为Judge分数。三维属于同一作品，不视为独立样本。只输出分数使依据的可审计性降低；格式通过也不证明评分语义正确。


### 4.3 不确定与事后复核

机械检查、预先人工意见、Kimi 原判与事后仲裁分别保存。需要专家补判的触发原因限定为 uncertain、Judge 无效、关键错误、校准分歧或证据错误；不要只替某一家模型挑有利样本复核。

可创建 `.work/adjudication.json`（只在确实发生时创建）：

```json
{"reviewer":"实际评审者","reviewed_at":"实际时间","items":[{"run_id":"实际run_id","trigger":"uncertain","scores":{"F":0,"D":0,"L":0},"reason":"实际证据说明；这里的0不是默认值","quote":"实际候选引文或遗漏时空串","source_quote":"TASK.source_text中的逐字依据"}]}
```

`eval.py score` 同时保留统一 Kimi 的原总分/原状态、复核后总分及覆盖数量；表头标清 `judge_only` 或 `human_audited`，不能冒称混合分全由 Kimi 给出。基础设施失败或根本没调用 Judge 不能靠人工补为已执行。系统性问题应重建实验版本，不采用选择性补丁。

## 5. Pi、API 与输入隔离

### 5.1 固定运行环境

Pi 固定 **0.87.1**、Linux x64 官方发布二进制；SHA-256：`80d78dd62d50049a006b981d994c61255bcc10e730b0c278d4ea0a755909764c`。Docker build 会把 Python 基础镜像解析到 digest，再记录最终 image ID、Pi 版本和 Docker 服务版本。Mac ARM 可经 Docker 的 linux/amd64 仿真运行，但报告须记录，不拿延迟作跨硬件性能榜。[R13]

每次调用新建容器，非 root、只读根文件系统、去 capabilities、no-new-privileges、2 GB 内存、2 CPU、128 进程上限。只有临时目录和 `/workspace` 可写，无宿主目录、Docker socket、完整数据集、其他答案、密钥文件挂载给 Pi。Pi 仅接内部网络，关闭外部 DNS，固定访问评测网关；启动前进行无上游密钥、无宿主 socket、无完整数据集、外网 TCP 不通检查。容器不是绝对安全证明，宿主 Docker 管理员仍属于信任边界。

网关在独立容器持有当前供应商一个 key，只允许当前固定模型和 HTTPS 路由。原始消息/工具 schema 不改写；仅替换模型路由、token 限额和预先登记的供应商参数。禁重定向、任意 URL、自动重试、内容增强、自动 JSON 修复与 best-of-N。

Pi 禁用扩展、自动 Skill 发现、上下文文件、提示模板、持久会话、压缩、重试、遥测/版本及模型目录自动刷新。思考模式下固定 `compat.supportsDeveloperRole=false`，三家首条消息均为 system，不能让 Pi 自动改成部分端点不支持的 developer。`--system-prompt` 仍可能附加固定 cwd，因此网关校验实际角色与正文：只接受 system/user 起始，以及规定正文或正文加准确的 `/workspace` cwd 段；其他上下文一律失败。同一case三条主测实际system哈希须完全一致；跨case只允许预登记条件不同。[R13]

唯一SKILL.md的完整正文由 `generation_system()` 显式注入system一次，`--no-skills`用于禁用自动发现，并不表示漏加载。YAML frontmatter、分发说明、上游名字和评测设计不进入生成上下文；许可证与改编出处保留在NOTICE/LICENSE，不能删除分发义务。三家Primary及工具Side使用同一正文，并附同case实验条件；运行入口拒绝缺失、替换或过期Skill，并在每个正式job前复核冻结哈希。实际wire system须逐字一致，不能只比较提示文件名。Judge使用独立固定评审system，不把它与生成system混为一谈。

四模型输入边界：`model_task()`只选取原文及预算/内白/语言条件，source_id统一为不含出处线索的 `TEXT`，去除title、作者、来源代号、Citation、URL及额外元数据。工具可读的 `/job/task.json` 同样使用投影版本；原文正文不改写，私有dataset仍保留完整来源用于收尾审计。发现URL/引用标记时先阻断，不静默清洗正文。这个措施移除额外出处提示，不声称模型无法凭原文或人物识别作品、也不宣称排除了预训练记忆。

### 5.2 四个端点与参数

| 角色 | 固定请求模型 ID | 凭证环境变量 | 关键映射 |
|---|---|---|---|
| M1 | `mimo-v2.6-pro` | `MIMO_API_KEY` | api-key；thinking.type=enabled；max_completion_tokens |
| M2 | `dots3-note-prev` | `DOTS_API_KEY` | api-key；chat_template_kwargs.enable_thinking=true；max_tokens |
| M3 | `qwen3.8-27b` | `QWEN_API_KEY` | Bearer；enable_thinking=true；max_tokens |
| Judge | `kimi-k3` | `KIMI_API_KEY` | Bearer；reasoning_effort=high；max_tokens |

按用户要求，三个被测模型全部开启原生thinking，共同固定temperature=0.2、top_p=1、请求token上限32768、单次生成及600秒壁钟上限；Judge也使用32768上限。由8192提高上限是为thinking与最终正文预留空间，不修改单句35字、剧本目标时长或评分规则；不同供应商的token计量口径仍不假定等价。当前四路已实际接受该上限并正常结束；Dots本次completion_tokens=11079，旧8192预算曾造成截断。遇到不支持参数错误须保留失败，不静默删参数或改变供应商。[R14–R16]

**Effort 对齐边界**：三家使用各自原生 thinking 默认 effort，不发送未经本地证据确认的统一 `reasoning_effort` 或 `thinking_budget`。Pi 统一 `--thinking medium` 且模型声明 reasoning=true，仅用于本地 harness 识别思考模式；网关剥离 Pi 的 effort 字段，再应用上表的供应商参数，不能把 Pi medium 写成三家真实 medium。相同档名、token 上限或输出 reasoning 长度都不能证明实际计算量等价。报告比较的是共同任务约束下的原生 thinking 表现，记录 API 公开的 reasoning、usage 及用时；缺失 reasoning token 计量写 unknown，不拿字符数代替 token。

Kimi使用reasoning_effort=high、最大输出32768，不覆盖其采样默认；当前探活返回了推理计量及PONG。Pi公共CLI档位不代表最终upstream参数，报告以wire请求为准。当前经用户确认使用 `https://tokenrhythm.studio/v1/chat/completions`，不得再按原默认.cn端点执行，也不冒称已独立验证官方直连。[R11]

Qwen 当前经用户确认使用 `https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions`，不再使用原默认北京端点。四路实际地址以 `config.json` 为准，任何变更须记录并重新验证；未授权模型、地区不匹配、余额不足都停止，不换模型、不自动充值。核对响应自报模型 ID、stop/finish reason、usage；自报 ID 不等于独立证明服务内部路由，不知道训练快照就写 unknown。Pi 自定义模型目录没有价格不代表 API 免费。

### 5.3 轨迹与失败口径

`prompts.jsonl` 保存请求的 system/user、首个实际 wire request 及环境 ID；`trajectory.jsonl` 保存每个 run 的完整 Pi stdout/stderr、API 流块、工具事件及请求/时间/usage/结束原因。API 返回的 reasoning_content/reasoning 与 Pi thinking 事件均保留，最终剧本只取正文，不把 reasoning 混入文学评分。二进制流以 base64 无损保存；可另导出解码阅读副本，但原轨迹始终保留。完整是指客户端能够观测到的完整轨迹，供应商未公开的内部推理不可获取或补造。先剥离凭证头，真实 key 和代理临时 token 不得进入导出记录。

无工具生成每例最多1次请求、600秒；Judge串行逐例，每次仅一个候选、最多1次请求，用户授权的新时限为1200秒。仅先前600秒超时且无最终答案的首例获准进行attempt2，完整保留attempt1；不自动重试再次失败的请求。工具侧例仍最多8次工具调用、9次API请求。

基础设施失败默认停止并保留失败证据；现有运行器**不提供自动续跑重试**。不能删除 job 文件再跑冒充首答。冻结前探活失败，可封存整个失败 `.work` 后在新目录重新探活；冻结后确需恢复，应先记录缺失单元、原错误、是否已有正文及新的 attempt 规则，保留全部尝试并在报告披露，不凭质量选答案。宁可报告 incomplete，也不生成伪完整总分。

## 6. Codex 执行顺序

### A. 在 kit 内核对既有准备与探活证据

先读本文、Skill、rubric；向人类展示第 1 节取段和边界。文本已经嵌入 dataset，不需要用户重新填十份 JSON。执行前确认材料可发送给四家 API；不要把公开版权状态擅自改成 confirmed。

每次会话从 kit 目录设置执行环境：

```bash
export DOCKER_CONTEXT=colima-eval
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
export PYTHONDONTWRITEBYTECODE=1
# .env 已存在，权限 0600；不要覆盖，不回显其内容。
# 按改动需要执行离线检查：
python3 -m unittest -v test_eval.py
python3 eval.py check-kit
# 核对 .work/build.json、.work/probe.json 的哈希与镜像是否仍一致。
# 旧探活已清理；须完成当前版本构建与探活后才能冻结。
```

现有宿主Python已就绪；专用Docker环境是否运行须在联调前核实。脚本只用标准库；本目录内 Python 负责编排，模型通过 Pi Docker 执行。后续不再安装宿主组件或改全局设置。若必须重建或重新探活，先核对授权范围，保留旧尝试，再在 kit 内执行；重建所需下载不属于默认网络许可。

`probe` 三家使用同一新构造的杯子归还短故事，仅测链路与格式接口；Kimi 只答 PONG。探活不计入文学评测。核对实际版本、响应模型 ID、采样/思考字段、提示哈希、沙箱检查、API 流完整性。既不通过 probe 的文学得分筛选模型，也不通过调整正式材料迁就输出。

当前四模型统一请求32768-token上限。旧探活产物已清理，正式冻结前须以当前审核版完成新探活。`probe`列出budget_exhausted_runs，预算截断不能通过冻结；正式输出截断仍保留为实际结果，不自动重试。方案与材料审核已完成，本次不调用模型。

### B. 冻结与生成

人类批准材料、rubric、Skill 后：

```bash
python eval.py freeze --reviewer "Anoki"
python runtime.py run --phase primary
python runtime.py run --phase side
python eval.py prepare-review
python eval.py review
```

冻结包含数据、rubric、Skill、配置、执行器与 Dockerfile 哈希以及实际镜像 ID。按固定种子交错三家运行顺序；每例只采一次。不得边生成边改prompt、修模型答案、填金标准或从失败中挑更好版本。全部30份原输出完整后，先执行 `python eval.py prepare-review` 固定15份评分样本，再运行 `python eval.py review` 生成匿名页面。若冻结后仅需改评审执行代码，`prepare-review` 会验证其余冻结哈希不变，并记录父冻结与抽样计划的review-only amendment；不得用它批准生成配置或模型输出变更。

**此处暂停。** 人类专家打开 `.work/review.html` 审阅并为15份匿名样本各填写F/D/L三个分数，下载 `review.json` 并放回 `.work/review.json`。这是实际人工行为，不是要求Codex模拟点击。

### C. 封存、调 Judge、留出验证、抽样评分

```bash
python eval.py seal
python runtime.py judge --phase dev
python eval.py compare --phase dev
# 仅根据本次抽中的dev分组记录修改或不修改理由。
# 如修改JUDGE.md，重新执行judge --phase dev，再compare；保留旧判。
python eval.py lock-judge --reason "填写实际修订内容，或不修改的实际理由"
python runtime.py judge --phase validation
python eval.py compare --phase validation
python runtime.py judge --phase rest
python eval.py score
```

Judge镜像ID已核对与freeze/build/probe一致。完整源码哈希因宿主评审编排改动而不同，review amendment绑定当前代码；容器入口及参数读取逻辑保持原版。恢复执行后的Judge时限通过worker与gateway任务JSON设置为1200秒，宿主等待为1230秒；原build/probe记录保留，不伪写新探活结果。

三个Judge阶段使用 `.work/review_plan.json` 中的分组，合计仅运行被抽中的15份。`score` 输出30条Primary记录，其中未抽中的15份标记 `not_selected`，不参与各模型主分；每模型分数以5份为分母。任何Judge调用缺失、失败或三分数格式无效都标记待复核；只在确需时按4.3请人类仲裁，再重算，不让Codex冒充专家。验证阶段出现系统性错误必须列为方法限制，不能偷看后重调还称独立验证。

### D. 真实记录、改进假设与 SFT

题面第1问需要至少一条真实对话/执行记录。目前文学素材包没有提供这条个人真实经历。不能把讨论稿、测试夹具或生成的“示例日志”充当原始经历。可引用用户补充的脱敏旧记录；或在本轮确实出现问题后引用真实 run，明确写“本轮观察”，由用户确认场景与经历表述，不虚构此前发生过。

Codex据实测选择一个最值得改进的问题，不预设必然是内白。输出两个**新的** SFT 示例，使用与8个评测来源家族无关的原创短情境，不能改名复写测试材料；不做实际训练。每条包含：

```text
input：新原文＋统一Skill/system＋预算/内白/语言条件；不提供人物、场景或情节解读
target：期望的结构化剧本或与选定问题匹配的关键轨迹
acceptance：可复现硬检查 + 人文验收条件
rejected_data：不能接受的数据类型与反例原因
side_effects：可能副作用，例如压抑必要内白/过度机械动作
independent_validation：未用于训练、评审或规则调试的新来源验证方法
based_on_runs：真实支持该改进假设的本轮run_id
human_approved：只有专家真的通过时为true
```

先用相同机械校验器检查目标剧本；人工审核人文质量和新来源独立性。导出器只做字段与批准状态检查，不替代上述语义验收。没有有效实测依据时不包装成“已证实有效训练数据”。SFT引入的改善仍是假设，不宣称未经训练的提升。

## 7. 验收与停止条件

现有84项离线测试覆盖数据哈希、连续取段、输入白名单、自报人物/场景结构、paired task条件、计分、Side排除、人工封存、15份抽样及Judge选择边界。测试构造响应不进入dataset、不随正式结果提交；临时测试文件只写kit的 `.work/tmp/`。

已完成：15份人工F/D/L评分及seal；同15份Kimi dev/validation/rest原始记录；分歧/修改说明；每模型5份有效抽样分；两条原创SFT草稿及机械校验。报告与独立公开快照也已完成。仍未完成人类对两条SFT的验收；个人经历由用户另行处理，当前两方score-only记录没有原始逐项理由。不得把探活原答充当正式结果。

报告不得出现未经证据支持的：模型普遍“最懂人文”、预训练污染已排除、参数越大导致成绩越好、某Judge外榜名次证明其公正、离线测试证明供应商已联通、Skill控制消除了所有Harness影响。样本是目的抽样，原文整理经过AI辅助与人类校订，当前输入不含AI预拆解答案，单次输出仍有随机性和供应商版本漂移风险。

## 8. 最终提交：严格收敛为六个文件

Codex在 `.work/REPORT.md` 写建议不超过2500字的主文，正文围绕笔试四问，而不是贴本施工文档：

1. 真实使用问题、事实/推测界限、改善/仍不合格的定义。
2. 十例覆盖、两个单条件pair、Side边界与材料版本。
3. 自动规则、人类与Kimi分工，同一批15份随机评分、dev/validation/extension分组、分歧与实际修改。
4. 三模型各5份Primary抽样主分/抽中家族敏感性分/合格数，典型真实失败、改进假设、两条新SFT指向及副作用/独立验证，并披露小样本限制。
5. 简短注明AI辅助方式、本人关键判断、模型版本/日期/设置及已知限制。

正文的依据链接到附件run_id/case_id/证据位置。不是所有数字都必须塞正文；完整逐例结果留附件。完成真实记录 `.work/incident.json`、两条 `.work/sft.jsonl` 后：

```bash
python eval.py export --report .work/REPORT.md --sft .work/sft.jsonl --incident .work/incident.json --mode private
```

输出 `.work/submission.zip`，内仅：

| 文件 | 必含内容 |
|---|---|
| `REPORT.md` | 四问主文、结果摘要、分歧/改进与AI披露 |
| `dataset.json` | 完整十例、九份源文件、原文/取段/版本哈希、证据卡、Side定义 |
| `prompts.jsonl` | 生成与Judge的实际prompt、版本、实际请求设置 |
| `trajectory.jsonl` | 所有可获得的API/Pi/工具原始轨迹，包括失败和探活的清楚标记 |
| `results.jsonl` | 30份Primary原答及机械结果；同15份Kimi原判/人工记录；未抽中结果标为not_selected；另含仲裁、Side、冻结/总分/真实事件/校准审计 |
| `sft.jsonl` | 两条新的经专家验收的训练示范及其依据与拒收条件 |

**本次公开快照授权与范围（2026-09-25）。** 用户明确确认“全部文本及派生轨迹可以公开”，授权另记 `Dots-Humanities-Eval/audit/publish_authorization.json` 并绑定dataset哈希；九份原文的冻结 `public_text_permission` 保持原历史值，不改冻结字节。该确认是用户提供的授权声明，不是独立许可调查；代码LICENSE不自动覆盖原文。

用户最新交付要求为完整报告、四模型token账本及可供agent复用的开源文件树，因此 `Dots-Humanities-Eval/` 是独立整理的公开评测快照，包含核心数据、代码、有效全轨迹和冻结源码，不限于旧版六文件提交格式。原 `eval.py export` 仍保留incident、SFT人工通过与旧许可字段校验；本次未调用它、未伪造通过标志。原始失败记录留在原 `.work`，公开有效数据仅含正式生成和新版Judge；被排除调用的已知成本另列，未知usage不填零。题目PDF仅用于本地核对，不复制进公开目录。不自动初始化Git、提交或推送。

## 9. 给 Codex 的启动指令

> 仅在 Eval_Kit 与专用 Pi Docker 环境内执行，遵守本目录 AGENTS.md。以 kit 为 cwd，设置 DOCKER_CONTEXT=colima-eval 和 kit 内 TMPDIR；不访问父目录材料或修改宿主全局设置，禁止所有 agent/模型联网搜索。当前冻结、39份生成结果、人工seal、新版15份Judge结果和两个SFT草稿均已存在；不重跑生成或Judge，不重写SFT草稿。incident由用户另行处理，不在本Eval内生成。接续时由专家审核 `.work/sft.jsonl` 中的两个target，只有真实通过后才标记 `human_approved`；报告及64文件公开评测快照已完成，先读 `.work/REPORT.md` 与 `Dots-Humanities-Eval/SUBMISSION_LIST.md`。当前原六文件导出器仍要求真实且人工确认的incident记录；本次公开快照另按用户要求整理，未伪造或绕过原导出器条件。用户已确认文本与派生轨迹可公开，仍不自动提交或推送GitHub。

## 10. 调研来源（仅维护者阅读，不注入模型）

用户依据：《人文训练师笔试题.pdf》1—3页、《岗位 JD.md》、讨论记录、v2评估报告、`Eval References.md`及本次ZIP；材料的具体内容和书目以ZIP为准，外部网页只用于方法核查、API配置及标明的英文源站对照。

[R1] DramaChain Bench，arXiv:2609.00646，2026-09-01，官方摘要及HTML正文：https://arxiv.org/abs/2609.00646 ；https://arxiv.org/html/2609.00646v1 。

[R2] LongJudgeBench，arXiv:2606.01629，查阅最新版入口与v2 PDF：https://arxiv.org/abs/2606.01629 。

[R3] WritingBench，arXiv:2503.05244，最新入口标示2025-11-27修订v4；具体方法同时参照其公开早期HTML：https://arxiv.org/abs/2503.05244 。

[R4] SkyScript-100M，arXiv:2408.09333：https://arxiv.org/abs/2408.09333 。

[R5] EQ-Bench Creative Writing v3及官方方法说明：https://eqbench.com/creative_writing.html ；https://eqbench.com/about.html 。

[R6] lechmazur / writing 官方仓库及其协议说明：https://github.com/lechmazur/writing 。本项目不引用随更新变化的模型排序来论证自身评分。

[R7] Surge，Hemingway-bench 方法文章：https://surgehq.ai/blog/hemingway-bench-ai-writing-leaderboard 。

[R8] EQ-Bench Judgemark v4及about页：https://eqbench.com/judgemark-v4.html ；https://eqbench.com/about.html 。

[R9] SuperCLUE 官方入口与仓库：https://www.superclueai.com/ ；https://github.com/CLUEbenchmark/SuperCLUE 。未获得充分的写作分项开放评分协议。

[R10] Omdia，Market Radar: Foundation Models for Chinese Creative Writing, 2026：https://omdia.tech.informa.com/om143577/omdia-market-radar-foundation-models-for-chinese-creative-writing-2026 。仅取得官方入口，非完整付费报告。

[R11] Kimi 官方 API 常见问题（模型ID、区域、K3思考模式）：https://www.kimi.com/help/kimi-api/api-troubleshooting ；开放平台：https://platform.kimi.com/ 。

[R12] MIT Shakespeare，Hamlet：https://shakespeare.mit.edu/hamlet/full.html 。此对照不补写或替换用户选段。

[R13] Pi官方v0.87.1发布与版本对应文档：https://github.com/earendil-works/pi/releases/tag/v0.87.1 ；https://raw.githubusercontent.com/earendil-works/pi/v0.87.1/packages/coding-agent/docs/cli.md ；https://raw.githubusercontent.com/earendil-works/pi/v0.87.1/packages/coding-agent/docs/sdk.md 。

[R14] Dots官方接入文档：https://dots.ai/platform/docs 。

[R15] MiMo官方模型与API FAQ：https://mimo.mi.com/models/zh-CN/mimo-v2.6-pro ；https://mimo.mi.com/docs/zh-CN/quick-start/faq/api-integration 。

[R16] 阿里云官方Qwen3.8-27B与思考模式文档：https://help.aliyun.com/zh/model-studio/qwen3-8-27b ；https://help.aliyun.com/zh/model-studio/deep-thinking 。

审核版文件指纹（本次清理不修改这些文件）：

- `dataset.json` SHA-256：`e1d73fb4470f3649bed2d243b08ec30b4e3c39fd6c57f646dc5e2754115a0a4a`
- `SKILL.md` SHA-256：`9dbe65b1d2ecae269e64ca0b08b4c470ca64eac4a9118f93eeb8a9fd63dbc53e`
- `rubric.json` SHA-256：`7671cae32dab92941032174daeda7bddd597ead9d11c3cc6084113fd15cfc9b6`
- `JUDGE.md` SHA-256：`e5719b8cf79f424668ebefc6c98a322a58c6dd63d44e16a41eb5d6b78a8fb1cb`
