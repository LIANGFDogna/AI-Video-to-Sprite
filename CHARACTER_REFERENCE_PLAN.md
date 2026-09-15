# Character Reference 第一阶段

本轮在既有五页编辑器上增加角色级固定轴和整动画 XY 偏移。保持原项目 CanvasFit、decoder、sequence scanner 和输出 canvas_normalizer，不另写中心裁补。

## 边界与兼容
- character_reference 是项目级不可变参考：reference_animation_id/frame、origin_x/ground_y、项目画布宽高；不是追踪 Root、Canonical Root 或 Root Motion。旧工程缺省 null。
- animation_transform 为单动画 offset_x/y（项目画布像素），缺省零；所有帧共用，不生成逐帧 override。此前已有逐帧编辑保留，参考模式下默认拖动整个动画。
- 初次校准消费已抠像项目画布的 Idle frame 0；像素不动，只拖 Ground/Y Axis/Origin。保存锁定，显式 Edit Reference 才进入草稿校准；取消无状态变化。
- 若从旧完整处理进入新手工参考工作流，校准说明明确保存后使用直通源位置；旧 Root/Motion/Profile 数据保留，已有整画布输出尺寸保留，AUTO Bounds 改为保持源画布。参考坐标本身不进入 CanvasFit 或 Normalize 签名。后续新动画默认手工直通。
- 纯数据赋值 character_reference 不改变旧渲染流程；UI 工作流切换是保存校准时独立、可撤销的模式命令。旧 Character Profile 编辑器保留独立入口。

## 数据与渲染
- 新整动画变换阶段复用源 RGBA 与现有预乘输出 Normalize；源 RGBA/视频不改。直通的 XY 在项目画布上平移及裁切后进入既有输出 Normalize；旧全流程额外显式 Offset 按既有缩放换算。
- 实时与落盘 final 共用 renderer；没有时间线编辑时也能导出 Offset。零偏移/无编辑保留旧签名与逐字节结果。Reference 变更只刷新 Overlay/JSON，不重建图像。
- Idle Ghost 从指定参考动画 keyed 缓存读取，LRU/单帧缓存复用；不套用当前或 Idle 动画的 Offset，也不导出。缓存丢失时一次后台重建，播放中不反复解码。
- 超出项目画布只发非阻塞 warning，不改变画布/缩放/居中；原有其他裁切规则保持。
- Undo/Redo 包含参考修改和整动画 Offset，防止其他动画的旧撤销快照回滚无关的项目 Reference。

## UI / 验收
- 保持现有编辑页；Inspector 增加 Reference 状态/校准入口、显示开关、35% Ghost、整动画 Offset。
- 独立非模态校准视图固定源图像，轴命中阈值使用屏幕像素，拖动转换为项目画布坐标；方向键1px/Shift10px。
- 新增模型、源像素不变、全帧Offset、保存/切换、旧工程、CanvasFit隔离、Preview/Export、Ghost、Undo、真实鼠标与125%/150%冻结验收；运行全量测试。
- 新建独立发布候选并全验收；用户旧程序退出后使用已有 publish_release.ps1 更新 dist，再实际运行 dist 的 Smoke Test。

后续仅记录、不实现：Project Animation Library（Project→Character→Animation Group→Animation）、Character Templates、Animation Set（JumpUp/FallLoop/Land）、Ctrl+A Create、Tree Drag & Drop、Loose Animations、Character/Enemy/Boss 分类。

## 不修改的算法基线
- `app/core/canvas_fit.py` SHA256 `0e641bc113e2ab7c4a253eedd8322e80399067e92490557eb69ba6cce97b1dc3`
- `app/core/canvas_normalizer.py` SHA256 `e60d27093c67a9f23953d3b5c0697669f2178425f159469ac58a981235679369`
- `app/core/frame_sequence.py` SHA256 `7f55239ee29045873969fe8d9431957f1323a8713c9de5082d9c088d55462fe3`
- `app/core/video_decoder.py` SHA256 `9a9934a327db16213def8071303355f218128fdc555f33ba342f6a6fbb8d71d8`

## 已完成验收

全量163 passed；689双语键检查通过。原生125%及150%真实视频→Idle校准→Run→全帧Offset→512输出→逐像素预览/PNG/Sheet→Undo/Redo/重开通过。四个算法SHA256与上列基线相同。构建与实际dist发布证据记录在VALIDATION.md。

已发布日常dist EXE，构建20260915-character-reference，SHA256 97CB2A6465A4EB85FF820F1949313759BF7CACCF9A5D2B0BD17A53159761A361；实际dist启动及150%完整参考流程通过，详见VALIDATION.md。
