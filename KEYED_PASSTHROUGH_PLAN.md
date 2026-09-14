# V0.4 视频抠像直通

范围：视频完成 Chroma Key 后选择完整 Root/Motion/Align 或 keyed_passthrough。复用现有最终 Cell、预览及导出，加入明确状态与恢复入口、统一分辨率预设、工程兼容和成品验证。

约束：默认源画布，所有帧原 X/Y 不变；只有用户选择 Normalize 才缩放。Profile、Root/Ground Lock、Motion Extraction、Alpha 自动居中完全跳过。与序列直通共用一套 Cell 生成代码，视频输入来自 keyed cache，不能误用未抠像 raw。Alpha Bounds 仅检测信息。

数据：processing_mode 默认为 full，按动画保存；keyed_passthrough 仅用于视频。完整对齐模式、手动 Root、Motion Settings、Character Profile 均保留。记录进入直通前的 canvas_mode，恢复完整处理时复用 keyed cache；直通签名依赖 key_signature 与显式画布变换。

UI：抠像全部完成后显示两入口并停留抠像页；直通跳到 Sprite 自动构建。导航标明跳过锚点/运动/对齐，锚点页仍可访问恢复按钮；Sprite 明显显示视频直通说明。分辨率支持原生/1536/1024/768/512/自定义，使用现有 float32 预乘 INTER_AREA 和同一公共变换。

审查：架构上通用直通判断覆盖 Preview/Export；数据流上两个来源与缓存签名分开，视频 FPS 来自 VideoInfo；工程上旧项目缺省完整流程，退出直通不重做抠像。测试需阻止隐藏跟踪调用、验证 jump/dash、RGBA 像素、共享变换和导出、模式往返和重开、真实 Qt 选择入口/预览/恢复。

实施：模型与管线 → UI/元数据 → synthetic+Qt 回归 → 文档与 Windows exe。保持前101项测试。

实施结果：通用直通分支与动画级保存已接通；全量114项测试、实际 Qt 56 帧视频及冻结成品验收通过。150% 截图发现按钮在表后导致首屏不可见，已移至顶部并加入完整可见区断言。原 dist 进程占用日志，新增构建输出目录参数与运行预检查，发布到 release-v0.4。全部文档已同步，验证结果与校验值记入 VALIDATION.md。
