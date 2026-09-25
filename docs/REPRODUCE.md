# 离线复算与复用

## 1. 已冻结结果

从仓库根目录运行README的 `python3 scripts/reproduce.py`。所有依赖为Python标准库，脚本不读.env、不使用Docker、不发送请求。

`manifest.json`列每个交付文件的SHA-256和字节数（不自包含）。原freeze的源码哈希在 `frozen/generation_sources/` 逐个验证；当前代码由 `frozen/metadata/review_amendment.json` 绑定。原始review和seal保持字节一致，输入/输出hash可核验。

`frozen/trajectory.jsonl.gz`按run_id从原轨迹逐行抽取54个正式run，不改行内容；`frozen/setup/trajectory.jsonl.gz`只含4个成功探活。解压后是JSONL，不需要重跑模型。原始总轨迹hash和逐run行数在audit/scope.json，排除清单在audit/exclusions.json。

`readable_json/`是上述JSONL源的可读派生副本：每个源对应一个目录，按`run_id`（SFT按`case_id`）生成缩进JSON数组；副本不参与评分或离线复算，原始记录不变。

复算只使用新版Judge hash；未抽中Primary为not_selected。模型均分分母5，家族等权分只基于抽中家族。程序将API返回usage按run_id/call归并一次，验证原始SSE流与usage账本一致；旧版被排除调用只有元数据，不宣称能从当前有效轨迹重建其正文。

## 2. 可选离线单元测试

```bash
export TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR"
python3 -m unittest -q test_eval
```

夹具是合成数据，不进入真实成绩。冻结结果复算与单元测试用途不同。

## 3. 新的类似实验

在新的项目副本中准备新材料，保留本仓库frozen/作为只读参考。当前代码固定10case、3生成器、每模型随机5份评分；不是只改模型名字就适用于任意数量。数据保留source原始字节、取段和hash；模型TASK只含白名单字段，不能把CASE_CATALOG的说明放入prompt。

人工先审核新的dataset、Skill、rubric及端点；使用新.env凭据和新的空.work。未经明确授权，不下载Pi/基础镜像、不更换端点、不发模型请求。Docker需要专用colima-eval context。Dockerfile的基础镜像digest、Pi版本/hash和历史image_id可在frozen/metadata/build.json核对；仓库不包含镜像二进制，也不保证未来供应商后端版本相同。

授权后按RUNBOOK的新实验步骤：check-kit→构建/探活→freeze→Primary/Side→prepare-review→review→人工真实填写→seal→Judge dev→compare→lock-judge→validation→compare→rest→score。任何运行代码变更都要重新核对冻结和镜像边界；不要复制旧.work的seal/lock到新实验冒充新结果。

本次发布包没有将快照恢复到.work，故不要在空.work直接运行score再声称复算失败；离线入口是scripts/reproduce.py。eval.py export是原六文件提交器，仍要求incident、人工通过的SFT以及原dataset许可字段；它不理解新增的独立发布授权记录。不要伪填这些字段。本仓库按用户另行要求整理为可复用公开快照，并未宣称调用该export成功。

## 4. 已知限制

单次采样、每模型5份目的材料中的随机抽样，不足以推断总体可靠性。匿名Judge输入不含模型名，但仍可能有风格线索。真实provider的reasoning预算不等价；Dots不报告reasoning拆分。时长是代理公式；人工/Judge仅数字分数，不保存判分依据，事后分析不能替代原始理由。
