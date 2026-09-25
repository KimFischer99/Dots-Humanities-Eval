# Dots-Humanities-Eval

统一Pi与生成Skill下的文学改编小型评测：MiMo-V2.6-Pro、Dots3 Note Preview、Qwen3.8-27B生成，Kimi K3评分。运行日期2026-09-25（UTC）。这是一次真实评测的可核查快照，以及可供其他agent复用于类似任务的执行代码。

## 结果入口

| 模型 | Judge加权均分 | 人工加权均分 | 样本数 |
|---|---:|---:|---:|
| M1 MiMo | 86.0 | 73.5 | 5 |
| M2 Dots | 83.3 | 70.8 | 5 |
| M3 Qwen | 77.0 | 68.0 | 5 |

公式为 H+7.5F+7.5D+5L，H满分20、F/D/L各0—4。两套评分分开，不混合平均。只代表此次小样本；不同模型抽中case不同。留出集Judge与人工的维度MAE为1.00，加权总分平均绝对差19.58，不能声称Judge已足够可靠。

- [完整报告与统计附录](REPORT.md)
- [逐例对照](docs/HUMAN_JUDGE_COMPARISON.md)
- [Token消耗](docs/TOKEN_USAGE.md)：有效正式过程1,095,748 token；全部现存过程已知1,143,636 token，另一次旧Judge超时usage未知。
- [测试集覆盖说明](docs/CASE_CATALOG.md)与[完整测试集](dataset.json)
- [题目要求对照与缺项](docs/REQUIREMENTS.md)
- [SFT草稿审阅](docs/SFT_REVIEW.md)
- [提交文件清单](SUBMISSION_LIST.md)

## 离线复算（推荐先运行）

仅需Python 3.11+标准库，不需要API key、Docker或网络。在仓库根目录运行：

```bash
export TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR"
python3 scripts/reproduce.py
```

脚本检查manifest、原生成源码与冻结哈希、人工封存、固定种子抽样、39份机械结果、15份加权成绩、原始SSE usage与两条SFT的机械约束。不会生成新模型回答。历史响应字节可以核验；再次联网采样不保证重现同样文字或分数。

## JSONL 可读副本

`readable_json/`为每个原始 `.jsonl` 或 `.jsonl.gz` 建立独立目录，并按 `run_id`（SFT按`case_id`）将记录格式化为 UTF-8、缩进 JSON 数组。每个组内保留源记录顺序；原始 JSONL/GZIP 文件保持不变，可继续用于复算。

## 证据范围

- 30份Primary全部保留，包括规则不合格结果；每模型固定种子抽5份，人工先评，Judge使用同批15份。
- 新版Judge按dev 3→锁定→validation 6→rest 6串行完成，严格JSON分数15/15有效。
- 9份Side保留，均不入主分；Dots S01因length截断且正文为空是正式观测，不隐藏。
- 有效正式54个run、67次API调用的完整轨迹经无损gzip保存。4个探活单列。
- 旧Judge的4个run正文/轨迹不进入公开有效结果；audit/exclusions.json记录排除范围，usage仍记已知消耗。原工作目录中的失败记录未删除。
- frozen/generation_sources/是原生成版本；根目录是最终scores-only评估代码。不能把当前宿主源码哈希冒充历史镜像源码。

## 复用

见 [复现与新实验操作](docs/REPRODUCE.md)。模型输出契约为 source_id/cast/locations/scenes，Judge只输出F/D/L。当前脚本专门约束10case、3生成器和15份抽样，并非任意规模的通用框架。复用时先离线核验，再经用户授权运行独立的新实验。

## 公开范围与未完成项

请仅以本目录作为独立Git仓库根目录；Eval_Kit包含本地工作材料，不应整体推送。

用户已确认九份原文及派生轨迹可公开，记录绑定dataset哈希，见 audit/publish_authorization.json。dataset中not_confirmed保留原冻结历史；本记录不修改或重新授权第三方原文。代码与修改过的Skill保留原LICENSE/NOTICE。题目PDF仅作本地参考，不放入此公开目录。

SFT是AI构造草稿且待人类验收，没有训练；个人经历由用户另行处理；人工与Judge未留逐项原始判分理由。这个仓库是评测快照，不是已经满足笔试所有要求的最终稿，也没有伪造原eval.py export所需的incident或human_approved。
