# 测试集覆盖与验收目录

本表仅供评测者/复用agent阅读，不注入生成或Judge输入；是对既有条件的说明，不新增隐藏评分义务。完整原文在dataset.json，source_id对模型统一投影为TEXT。

| Case | 来源家族 | 条件 | 主要考察点 | 合格/允许变化 | 关键失败 | 参考信息 |
|---|---|---|---|---|---|---|
| C01 | KAF | 90秒 / forbid / zh | 心理叙事在禁止内白条件下的改编 | 人物关系与材料边界保持；用允许的外显形式表达 | 出现inner标签或把无来源信息当事实 | dataset.json /cases/0/task/source_text；rubric.json |
| C02 | KAF | 90秒 / allow_limited / zh | 相同文本在有限内白许可下的边界 | 最多2个inner；完全不用内白也可合格 | 把许可理解为必须内白或超过2段 | dataset.json /cases/1/task/source_text；rubric.json |
| C03 | RED | 90秒 / forbid / zh | 复杂人物交流在90秒预算下的取舍 | 自报人物/场景引用自洽，保留核心关系 | 角色引用错乱、句长或代理时长超限 | dataset.json /cases/2/task/source_text；rubric.json |
| C04 | RED | 150秒 / forbid / zh | 与C03同文，预算扩到150秒 | 只改变时长条件，增加内容应有组织而非填充 | 通过重复对白或拆动作凑时长 | dataset.json /cases/3/task/source_text；rubric.json |
| C05 | ZUO | 90秒 / forbid / zh | 古典叙事的中文短剧转换 | 忠于所给文本，表达清晰，不调用外部续篇 | 依记忆补故事、改变关键因果 | dataset.json /cases/4/task/source_text；rubric.json |
| C06 | HAM_ZH | 90秒 / forbid / zh | 多事件尾声压缩与角色知情边界 | 以当前中文底本为准，合理压缩仍可理解 | 借熟悉作品背景补全未给信息 | dataset.json /cases/5/task/source_text；rubric.json |
| C07 | LI | 60秒 / forbid / zh | 诗歌片段的舞台呈现 | 允许最小舞台承载，不强求完整冲突或固定人物 | 过度补造情节、把意象解读设为唯一答案 | dataset.json /cases/6/task/source_text；rubric.json |
| C08 | ODY | 90秒 / forbid / zh | 较长叙事片段的组织与预算 | 仅用选段，合理取舍不改变材料边界 | 外接其他篇章或超时/超长台词 | dataset.json /cases/7/task/source_text；rubric.json |
| C09 | GHOST | 90秒 / forbid / zh | 短篇材料的戏剧化与取舍 | 保留文本支持的关系及事件变化 | 为凑时长反复解释或发明事件 | dataset.json /cases/8/task/source_text；rubric.json |
| C10 | WEB | 90秒 / forbid / zh | 网文节选的边界控制 | 只改编当前节选，保持连续可读 | 续写未提供后文、用套路强加转折 | dataset.json /cases/9/task/source_text；rubric.json |

共同机械与人文标准以eval.py、rubric.json为准；开放式改编允许场景合并、人物合理省略与不同文风，不提供预制人物/场景卡。

成对预期：P1只改变内白许可，合格范围从0段扩到最多2段，不要求模型一定使用；P2只改变90/150秒，代理估时接受范围相应变化，内容不要求只差一个字面变量。单次结果不证明条件的因果效果。

Side：S01对照C06，输入语言及译本共同改变；T01/T02对照C01/C03只提供工具机会，实际是否用工具必须看轨迹。三类均三模型各一次，排除主分。
