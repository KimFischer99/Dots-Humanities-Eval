# 本地交付核验

- 从交付目录运行84项单元/合同测试：通过，日志见offline_tests.log。全部是离线合成夹具，无模型调用。
- 离线复算：54个正式run，67次正式API调用，39份机械结果、15份加权成绩、人工seal、固定种子抽样、原始SSE usage、生成/评分源码hash和SFT机械约束通过。
- 同case实际wire system在三个生成器间一致，工具对照匹配无工具基线；允许的Pi固定cwd封套按真实wire哈希核对。
- 已知API key与Bearer token模式扫描未命中；公开目录不含.env、临时env、原.git、缓存或个人宿主路径。扫描范围与数量见credential_scan.json。
- 正式有效token为1,095,748；现存全过程已知token为1,143,636，另1次旧Judge超时usage未知，不估填。
- 两条SFT的human_approved仍为false；未执行训练、模拟人工验收、Git提交或GitHub推送。

完整性以manifest.json为准。文件修改后manifest会失配；这是有意的不可变快照检查，不应为了通过而无记录地改校验值。历史镜像二进制未随包发布，build/probe/source/digest记录可核验，不声称能从源码保证供应商响应逐字重现。
