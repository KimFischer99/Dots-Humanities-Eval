# Dots-Humanities-Eval

固定 Pi 与单一生成 Skill 下，对三个模型进行文学片段改编测评的可复核快照；实验日期为 2026-09-25（UTC）。

## 结果

| 模型 | Judge 均分 /100 | 人工均分 /100 | 合格数（Judge / 人工） |
|---|---:|---:|---:|
| MiMo-V2.6-Pro | 86.00 | 73.50 | 4/5 / 2/5 |
| Dots3-note-prev | 83.30 | 70.80 | 1/5 / 1/5 |
| Qwen3.8-27B | 77.00 | 68.00 | 3/5 / 1/5 |

总分为 <code>S = H + 7.5F + 7.5D + 5L</code>，人工与 Judge 分开报告。每个模型抽评不同的 5 份作品；样本量和题目组合都不足以形成稳定排名。验证组维度 MAE 为 1.00、加权总分 MAE 为 19.58，自动评分与人工评分仍有明显差异。详见 [最终报告](REPORT.md)。

## 文件入口

- [交互式报告](index.html) · [机器可读复算数据](analysis.json)
- [复用流程与十题说明](RUNBOOK.md) · [公开文件清单](REPOSITORY_FILES.md)
- [SFT 示例审阅](sft/SFT_REVIEW.md)：两条记录均为 <code>human_approved=true</code>；没有进行模型训练或验证训练收益。
- [离线核验脚本](scripts/verify_release.py)

## 离线核验

需要 Python 3.11 及以上；不需凭据、Docker 或网络。以下核验不会生成模型回答、修改历史分数或更改人工批准：

~~~bash
export TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR"
python3 scripts/verify_release.py --check-sft-only
python3 scripts/verify_release.py --self-test
python3 scripts/verify_release.py
python3 scripts/verify_release.py --check-release
~~~

<code>--seal-release</code>会更新根目录发布层的 <code>manifest.json</code>，应在有意修改发布文件并完成核验后运行；之后用 <code>--check-release</code>复核。<code>frozen/publication_manifest.json</code>保留历史清单，不随发布更新。旧版 <code>eval.py export</code>有另一套格式与历史字段，不是本仓库的发布入口，不应为满足它虚构记录。

本目录单独作为仓库根目录；上级工作目录不属于发布树。冻结生成源码保存在 <code>frozen/generation_sources/</code>，不得用当前代码替代。代码许可不自动覆盖第三方原文，出处与发布范围见 <code>audit/</code>。新实验应在独立副本和空工作目录中进行，并遵循 RUNBOOK 的数据、运行授权及费用边界。
