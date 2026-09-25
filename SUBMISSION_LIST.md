# 提交目录范围与文件清单

目标目录：Dots-Humanities-Eval。用途：公开可复用评测快照；本清单限定独立仓库根目录内的交付范围。用户已确认九份原文和派生轨迹可公开，记录在audit/publish_authorization.json；原冻结数据不变。

## 纳入

1. 完整报告REPORT.md：主文不超过2500个非空白字符（含表格/Markdown计数也低于上限），附录给完整结果与用量。
2. 完整dataset.json、统一SKILL、rubric和JUDGE；eval/runtime/测试、Dockerfile、脱敏.env.example、LICENSE/NOTICE。
3. frozen/：全部30份Primary与9份Side原答；新版15份Judge；对应54个run的prompt与全轨迹；原生成源码、freeze/build/probe、人工review/seal、抽样、锁定和修订记录、完整成绩。
4. setup探活单列；不计主分或有效正式token。旧Judge正文/轨迹不纳入，排除清单保留；它们实际发生的已知成本在usage单列。
5. usage/：75个run_id/call去重后的API账目（74个有usage、1个未知），分有效正式、探活、排除Judge汇总；reasoning/cache不重复相加。
6. sft/及审阅文档：两条AI原创草稿与验收/拒收/副作用/独立验证，human_approved=false。
7. 复用说明、题目对照、case目录、逐例人工/Judge比较；离线reproduce脚本、manifest与检查日志。
8. `readable_json/`：每个JSONL/GZIP源一个目录，按run_id（SFT按case_id）导出缩进JSON；原始JSONL保留不变。

## 排除

- .env、真实API key、网关临时token/env、Docker socket、宿主配置、原.git、缓存、临时文件、个人经历incident。
- 旧Judge的无效/已替代输出不进入有效结果。原项目.work未删除这些历史记录。
- 本地《人文训练师笔试题.pdf》原件：仅用来核对要求，公开目录提供要求映射与文件hash。
- 不把已截断或规则不合格的正式生成当作基础设施无效重跑。M1.C04、M2若干硬规则失败与M2.S01截断都是正式观测，原样保留；Side无论好坏均不入主分。

## 交付缺口

个人真实经历由用户另行完成；两方只记录分数，缺少原始逐项理由；SFT待人类验收。评测快照已可核验，不声称笔试全部要件齐备。原六文件export门槛未伪造/绕过；当前是用户另行要求的开源工程快照。

## 文件树（仅实际交付文件，空的本地.work临时目录不提交）

```text
Dots-Humanities-Eval/
  .dockerignore
  .env.example
  .gitignore
  Dockerfile
  JUDGE.md
  LICENSE
  NOTICE
  README.md
  REPORT.md
  RUNBOOK.md
  SKILL.md
  SUBMISSION_LIST.md
  audit/VALIDATION.md
  audit/credential_scan.json
  audit/exclusions.json
  audit/offline_tests.log
  audit/publish_authorization.json
  audit/scope.json
  config.json
  dataset.json
  docs/CASE_CATALOG.md
  docs/HUMAN_JUDGE_COMPARISON.md
  docs/REPRODUCE.md
  docs/REQUIREMENTS.md
  docs/SFT_REVIEW.md
  docs/TOKEN_USAGE.md
  eval.py
  frozen/comparisons/dev.json
  frozen/comparisons/rest.json
  frozen/comparisons/validation.json
  frozen/generation_sources/Dockerfile
  frozen/generation_sources/SKILL.md
  frozen/generation_sources/config.json
  frozen/generation_sources/dataset.json
  frozen/generation_sources/eval.py
  frozen/generation_sources/rubric.json
  frozen/generation_sources/runtime.py
  frozen/generations.jsonl
  frozen/human/human.seal.json
  frozen/human/review.json
  frozen/judges.jsonl
  frozen/mechanical_checks.json
  frozen/metadata/build.json
  frozen/metadata/freeze.json
  frozen/metadata/judge.lock.json
  frozen/metadata/judge_execution_plan.json
  frozen/metadata/probe.json
  frozen/metadata/review_amendment.json
  frozen/metadata/review_plan.json
  frozen/prompts.jsonl
  frozen/results.jsonl
  frozen/scores.json
  frozen/setup/prompts.jsonl
  frozen/setup/trajectory.jsonl.gz
  frozen/trajectory.jsonl.gz
  readable_json/
    frozen/generations/<run_id>.json (39 files)
    frozen/judges/<run_id>.json (15 files)
    frozen/prompts/<run_id>.json (54 files)
    frozen/results/<run_id>.json (39 files)
    frozen/setup/prompts/<run_id>.json (4 files)
    frozen/setup/trajectory/<run_id>.json (4 files)
    frozen/trajectory/<run_id>.json (54 files)
    sft/sft/<case_id>.json (2 files)
    usage/calls/<run_id>.json (62 files)
  manifest.json
  rubric.json
  runtime.py
  scripts/reproduce.py
  sft/sft.jsonl
  test_eval.py
  usage/calls.jsonl
  usage/summary.json
```

manifest.json为逐文件最终SHA-256与字节清单，文件自身不递归计算；所有有效轨迹无损压缩为gzip，避免单文件过大。副本中的运行记录路径均相对仓库；README给出可直接执行的离线核验入口。
