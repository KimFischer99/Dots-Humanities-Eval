# SFT草稿审阅

以下是AI构造训练示范，不是真实模型原答，未训练、未经人类验收。分数均值仅支持优先查看D维的假设，不能证明具体的“因果推进”缺陷已被独立验证。

## SFT-ORIG-01

原创新原文：

图书馆闭馆前，阅览室的漏水警报响起。值班员岑禾看见地毯角湿了，窗台却干；保安陆祺想关窗。岑禾沿着水痕找到借阅机后的墙脚，墙后是饮水间。维修簿记着当天换过软管，维修员在电话里确认支管已关，但水仍沿墙渗出。插座离水边一步，书车停在干处。大厅今晚空着，原定读书会十分钟后开始。墙边有警示带。

条件：`{"target_seconds": 35, "interior_policy": "forbid", "output_language": "zh"}`。完整system已包含在sft.jsonl，使用当前统一生成Skill。

目标回答：

```json
{
  "source_id": "TEXT",
  "cast": [
    {
      "id": "P01",
      "name": "岑禾"
    },
    {
      "id": "P02",
      "name": "陆祺"
    }
  ],
  "locations": [
    {
      "id": "L01",
      "name": "阅览室"
    }
  ],
  "scenes": [
    {
      "sceneId": "L01",
      "characters": [
        "P01",
        "P02"
      ],
      "flow": [
        {
          "action": "漏水警报急响，地毯角洇开一片深色。"
        },
        {
          "speaker": "P02",
          "line": "先关窗，雨水多半从这儿进。",
          "mode": "spoken"
        },
        {
          "speaker": "P01",
          "line": "窗台没湿，水印从墙脚往外走。",
          "mode": "spoken"
        },
        {
          "action": "陆祺扣紧窗闩，水痕仍从借阅机后渗出。"
        },
        {
          "speaker": "P01",
          "line": "墙后是饮水间，我查维修簿。",
          "mode": "spoken"
        },
        {
          "action": "岑禾翻到当天换软管的记录，拨通维修员。"
        },
        {
          "speaker": "P01",
          "line": "支管已经关了，水却还在渗。",
          "mode": "spoken"
        },
        {
          "speaker": "P02",
          "line": "插座挨着水边，我先围警示带。",
          "mode": "spoken"
        },
        {
          "action": "陆祺隔开插座，岑禾沿干地推书车。"
        },
        {
          "speaker": "P01",
          "line": "大厅空着，读书会转过去。",
          "mode": "spoken"
        },
        {
          "speaker": "P02",
          "line": "我去门口改地点，你守住水边。",
          "mode": "spoken"
        },
        {
          "action": "两人分头行动，湿区前立起暂停入场牌。"
        }
      ]
    }
  ]
}
```

验收、拒收、副作用和独立验证：

```json
{
  "acceptance": {
    "basis": {
      "sample_size": 15,
      "human_dimension_means": {
        "F": 2.867,
        "D": 2.4,
        "L": 2.467
      },
      "lowest_dimension": "D",
      "based_on_runs": [
        "M1.C01",
        "M1.C08",
        "M3.C03"
      ]
    },
    "mechanical_checks": [
      "schema_errors=[]",
      "H1-H5 all pass",
      "spoken lines <=35 nonspace characters",
      "estimated duration within 85%-115% of target",
      "no inner monologue when forbidden"
    ],
    "mechanical_result": {
      "H": 20,
      "hard_pass": true,
      "estimated_seconds": 33.166667
    },
    "human_acceptance": [
      "F >= 3: preserves stated facts without inventing material facts",
      "D >= 3: at least three grounded cause/effect transitions; a decision changes the next action; outcome follows from available evidence",
      "L >= 3: concise, distinct voices without repeated exposition"
    ],
    "review_status": "pending"
  },
  "rejected_data": [
    {
      "type": "disconnected_beats",
      "reason": "把关窗、查簿、搬书、通知并列罗列，动作没有由证据或前一决定引出。"
    },
    {
      "type": "unsupported_resolution",
      "reason": "让渗水突然停止或直接恢复活动，输入没有支持这个结果的事实。"
    }
  ],
  "side_effects": [
    "把短剧都写成故障排查流程，削弱人物关系或诗性表达。",
    "为追求因果清楚而添加输入未给出的解释或结局。"
  ],
  "independent_validation": "用未用于本轮生成、评审或提示调试的原创生活场景盲测；人类检查动作是否改变下一步选择，并同时核验材料保真与语言表达。",
  "based_on_runs": [
    "M1.C01",
    "M1.C08",
    "M3.C03"
  ],
  "human_approved": false
}
```

## SFT-ORIG-02

原创新原文：

社区电台原定六点播报步道情况。值班台有两张巡查条：清晨的记录写东门已清理，十五分钟前的记录写桥边积水。主持人袁宁准备照第一张播出，编辑柏澜发现两张记录说的是不同入口。巡查员电话占线，播音灯一分钟后亮起。电台已确认的通用提醒是绕过积水并听从现场公告。

条件：`{"target_seconds": 35, "interior_policy": "forbid", "output_language": "zh"}`。完整system已包含在sft.jsonl，使用当前统一生成Skill。

目标回答：

```json
{
  "source_id": "TEXT",
  "cast": [
    {
      "id": "P01",
      "name": "袁宁"
    },
    {
      "id": "P02",
      "name": "柏澜"
    }
  ],
  "locations": [
    {
      "id": "L01",
      "name": "播音室"
    }
  ],
  "scenes": [
    {
      "sceneId": "L01",
      "characters": [
        "P01",
        "P02"
      ],
      "flow": [
        {
          "action": "播音灯开始倒数，袁宁把清晨的巡查条放上稿纸。"
        },
        {
          "speaker": "P01",
          "line": "六点就播，照这条念就行。",
          "mode": "spoken"
        },
        {
          "speaker": "P02",
          "line": "它只写东门，桥边那条更新。",
          "mode": "spoken"
        },
        {
          "action": "柏澜并排放下两张记录，分别圈出入口和时间。"
        },
        {
          "speaker": "P01",
          "line": "我打给巡查员，确认桥边情况。",
          "mode": "spoken"
        },
        {
          "action": "电话里仍是占线音，倒数跳到最后十秒。"
        },
        {
          "speaker": "P02",
          "line": "桥边没确认，不能说步道全开放。",
          "mode": "spoken"
        },
        {
          "speaker": "P01",
          "line": "我只播已确认的避水提醒。",
          "mode": "spoken"
        },
        {
          "action": "袁宁划去开放路线，播音灯转绿。"
        },
        {
          "speaker": "P01",
          "line": "请绕过积水，并听从现场公告。",
          "mode": "spoken"
        },
        {
          "speaker": "P02",
          "line": "巡查回电后，再补播路线信息。",
          "mode": "spoken"
        },
        {
          "action": "播音结束，柏澜把待核路线留在稿纸空栏。"
        }
      ]
    }
  ]
}
```

验收、拒收、副作用和独立验证：

```json
{
  "acceptance": {
    "basis": {
      "sample_size": 15,
      "human_dimension_means": {
        "F": 2.867,
        "D": 2.4,
        "L": 2.467
      },
      "lowest_dimension": "D",
      "based_on_runs": [
        "M1.C01",
        "M1.C08",
        "M3.C03"
      ]
    },
    "mechanical_checks": [
      "schema_errors=[]",
      "H1-H5 all pass",
      "spoken lines <=35 nonspace characters",
      "estimated duration within 85%-115% of target",
      "no inner monologue when forbidden"
    ],
    "mechanical_result": {
      "H": 20,
      "hard_pass": true,
      "estimated_seconds": 33.388889
    },
    "human_acceptance": [
      "F >= 3: preserves stated facts without inventing material facts",
      "D >= 3: at least three grounded cause/effect transitions; a decision changes the next action; outcome follows from available evidence",
      "L >= 3: concise, distinct voices without repeated exposition"
    ],
    "review_status": "pending"
  },
  "rejected_data": [
    {
      "type": "unsupported_certainty",
      "reason": "把较早的东门记录扩大成全步道开放，忽略更新时间和入口差别。"
    },
    {
      "type": "exposition_without_decision",
      "reason": "只复述巡查条，却不改变播报内容或后续行动。"
    }
  ],
  "side_effects": [
    "把留白或开放结尾误判为结构不足。",
    "让角色重复解释道具已经展示的信息，造成台词冗余。"
  ],
  "independent_validation": "在与本轮材料、调试记录和八个来源家族均无关的新写实场景上盲测；人类检查信息时序是否转化为角色选择与后续行动，并并行检查F/L没有退步。",
  "based_on_runs": [
    "M1.C01",
    "M1.C08",
    "M3.C03"
  ],
  "human_approved": false
}
```

