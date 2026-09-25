# 笔试题要求对照

本表根据项目内《人文训练师笔试题.pdf》三页核对。PDF hash见audit/scope.json；原PDF不随公开仓库复制。报告正文与完整统计附录分开，附件不计正文建议长度。

| 要求 | 交付与状态 |
|---|---|
| 问题场景、改善与不合格定义、事实/推测边界 | REPORT正文1、规则/维度说明；只解释本轮系统表现 |
| 至少一条个人真实对话/经历记录 | 用户明确另行处理，本Eval不编造incident；笔试整体验收仍需用户补充 |
| 10个case及覆盖、必要上下文 | dataset.json、docs/CASE_CATALOG.md、SKILL.md、config.json |
| 合格/失败、参考信息与可接受变化 | rubric.json、H规则、CASE_CATALOG；直接以原文为证据，不设标准人物/场景答案 |
| 至少一组单条件pair | C01/C02内白许可，C03/C04目标时长；脚本校验仅该字段不同 |
| 可运行Judge prompt、输入与输出 | JUDGE.md、eval.judge_payload/validate_judge、runtime.py；输出仅F/D/L |
| 至少6个case实际运行并人工/Judge比较 | 共运行10case，15份抽中作品覆盖8个不同case；frozen/保存原答和对照 |
| 预选、dev与validation隔离 | 固定种子在生成后、人工/Judge前选15份；dev2个case、validation3个case、rest3个case。不是严格的生成前预选，报告披露该差异 |
| 人工在Judge之前完成 | frozen/human/review.json及human.seal.json；保留hash与时间 |
| 人工与Judge各自关键依据 | 用户选择score-only，两方仅保存分数；缺少原始逐项理由，未编造补齐 |
| 分歧、原因、修改或不修改理由 | 对照表量化分歧；具体语义原因未知。使用dev完成格式契约修订后锁定，未按validation改分/调规则 |
| 2条新SFT、拒收标准、副作用与独立验证 | sft/sft.jsonl和docs/SFT_REVIEW.md；AI构造，机械通过，human_approved=false，无训练效果声明 |
| 后续评测与避免泄漏 | REPORT正文4、SFT独立评测计划；使用全新来源，不在既用validation反复调参 |
| AI披露、模型版本/设置/运行日期 | REPORT及config.json、冻结记录、实际wire与usage |
| 不编造、不泄露未经授权敏感信息 | 用户公开确认见audit/publish_authorization；无.env/API key；未知usage不填0，旧结果不混分 |

“有效评测已结束”与“全部笔试要件已满足”分别描述。当前仍有个人经历、双方关键依据以及SFT人工验收缺口；本次开放快照不假称已补齐。
