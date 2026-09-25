# 测评复用与结果核验

用于其他Agent接手。历史记录固定在提交`bf33da8d35715602c7daab0aed53ba2c4733d698`。本版简化操作说明，不修改原生成任务、冻结规则和实测结果。

## 1. 两种操作

**核验已有结果**无需API、Docker或密钥，使用Python 3.11及以上即可。保留冻结文件后运行`scripts/verify_release.py`。当前仓库已合入增补文件并保留完整冻结证据，可执行全量离线核验。

**执行新实验**需要可用Docker、构建依赖、Pi二进制和已授权模型API。现有runtime锁定专用Docker context及供应商路由，不能承诺任意机器无需配置即运行。环境、费用及文本外发授权就绪后按第4节执行。没有明确运行授权时只做离线核验。

## 2. 已冻结实验的字段边界

生成输入只有原文、目标秒数、内白许可和输出语言。模型自行输出cast、locations和scenes；不把下面的案例说明、报告、人类意见、盲评样本ID或外部出处混入生成输入。Judge收到RUBRIC、TASK、CANDIDATE，输出三个0至4整数，身份由宿主绑定。

H1至H5检查结构、引用、句长、代理时长和标签许可；F/D/L检查材料、组织和语言。`S=H+7.5F+7.5D+5L`。合格须H=20且三维均至少3。人类先评后封存；锁定后不根据验证分数改规则；不替换失败原答或选择更好的重跑结果。

## 3. 十题覆盖与可接受变化

| 题目 | 材料与条件 | 主要考察点 | 允许变化与失败条件 |
|---|---|---|---|
| C01 | 变形记，90秒，禁内白 | 内心叙事转为可感知表达 | 可压缩或舍去次要心理；不能将私下活动无依据地公开给其他角色 |
| C02 | 同C01，仅允许至多2条内白 | 许可边界 | 可使用或不用内白；不得超过2条，不强制与C01字面不同 |
| C03 | 红楼梦，90秒 | 多人物交流与短预算 | 可合理省略、合并；不能错置发话人或改变核心关系 |
| C04 | 同C03，仅150秒 | 预算变化后的取舍 | 可保留更多细节；不得重复动作或对白凑时间 |
| C05 | 左传，90秒 | 古典叙事转写 | 以当前节选为准；不得从外部后文补情节或改核心因果 |
| C06 | 哈姆莱特中译节选，90秒 | 多事件尾声压缩 | 可取舍；不得把熟悉的作品背景当作新增已知信息 |
| C07 | 李白长诗节选，60秒 | 意象与最小舞台呈现 | 可保持开放、抒情；不强求完整冲突，不虚构独立支线 |
| C08 | 奥德赛节选，90秒 | 信息分布与叙事组织 | 允许压缩；不得让门外角色无依据知道室内事件 |
| C09 | 宗定伯卖鬼用户版本，90秒 | 短材料的可呈现性 | 不靠反复解释或发明新事件凑预算 |
| C10 | 网文节选，90秒 | 材料边界与组织 | 只处理当前片段，不续写未给后文或套用固定反转 |

这些是对冻结材料的阅读说明，不是新加分项。直接参考`dataset.json`中的source_text与`rubric.json`，没有唯一人物名单或标准剧本。C01/C02只变内白许可，C03/C04只变时间；Side的S01同时变语言与译本，T01/T02只给工具机会。

## 4. 新实验的可执行顺序

在独立项目副本与新的空`.work/`执行。不要复制旧seal/lock作为新实验记录。当前代码固定10题、3生成器、每模型抽5份评分，改变规模需要新版本及相应测试。要修复本轮生成后抽样和共同题目不足的问题，应先修订新实验协议及选择器，不能把下面兼容旧协议的命令说成已修复这些方法缺口。

```bash
export DOCKER_CONTEXT=colima-eval
export PYTHONDONTWRITEBYTECODE=1
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
python3 -m unittest -v test_eval.py
python3 eval.py check-kit

# 以下构建/探活会下载依赖或产生API费用，需已有明确授权。
python3 runtime.py build
python3 runtime.py probe
python3 eval.py freeze --reviewer "实际审核者姓名"
python3 runtime.py run --phase primary
python3 runtime.py run --phase side
python3 eval.py prepare-review
python3 eval.py review
```

此处需要真实的人类打开匿名review页面，填写并保存review.json。Agent不得模拟专家、自动填分或修改模型原答。待实际评分文件就位后：

```bash
python3 eval.py seal
python3 runtime.py judge --phase dev
python3 eval.py compare --phase dev
python3 eval.py lock-judge --reason "填写实际修订或不修订的理由"
python3 runtime.py judge --phase validation
python3 eval.py compare --phase validation
python3 runtime.py judge --phase rest
python3 eval.py score
```

使用供应商原生thinking设置；Pi本地medium不代表跨供应商等推理预算。凭据只放环境变量或私有.env，不回显、不打包。Primary与Judge禁工具；工具Side仅read/write/bash，沙箱禁外网。失败按基础设施失败与真实输出失败区分，保留所有实际记录，不按质量重跑。

## 5. 发布层核验

保存原manifest后，运行：

```bash
python3 scripts/verify_release.py
python3 scripts/verify_release.py --seal-release
python3 scripts/verify_release.py --check-release
```

历史manifest由Git blob `293b61c9f39500d9d3bad41cfaa6310204bc79dd`固定。新脚本检查保留的核心文件、原文与冻结契约、抽样、评分、人工seal、实际prompt、轨迹行数和原始usage，并附SFT机械检查。工具artifact另报字节和JSON结构两种一致性，解析失败为未知。

仅凭JSON相等仍不能证明最后版本已复检。需要按对应run的tool_execution事件确认校验命令、返回值、后续修改及最终回答。供应商未公开的内部信息不得补造。

## 6. 后续方法改进

新版本在生成前冻结共同题单，按来源家族划分调试和验证。人类与Judge均保留一句理由和局部证据，不确定时转人工。增加独立的模糊要求澄清、材料冲突和跨场知情状态配对，不在本轮验证集上反复调参。

评估SFT时使用新的来源、相同提示和重复采样，报告误差类型及F/D/L是否退步。需要降低审核负担时，记录审核用时、漏检和返工，而非只记录表单字段减少了多少。
