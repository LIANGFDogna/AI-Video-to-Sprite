# Character Profile / Reference Box

项目只保存一份 CharacterProfile，动画保存自己的源视频、跟踪与动作参数。首次 Idle 校准允许用身体检测辅助站地；确认后 Canonical Root X 必须严格等于 Ground Origin X。后续动画的 Alpha Bounds 不参与坐标原点或水平中心的计算。

Profile 使用最终画布像素：canvas_size、character_scale（源像素到角色空间的比例）、ground_origin、canonical_root、派生 canonical_root_offset、reference_box_half_width、facing。基准框顶边为画布顶边，底边为 Ground Origin，垂直中线为固定 Y Axis。只保存半宽，左右控制柄对称联动。

管线继续在源分辨率抠像和跟踪。tracked_root = raw_root * character_scale；Character Space correction = canonical_root - tracked_root。内部源尺寸补偿为该 correction / character_scale，再统一归一化。所有已确认 Profile 的动画使用固定 In-Place 位置，根运动曲线另行保留。现有无 Profile 工程维持原算法。

宽度编辑只更新参考范围和警告，不修改像素、Scale、Ground Origin、Canonical Root，也不使图像缓存失效。Reference Box 与每帧 Alpha Bounds 使用不同数据和绘制样式。

实施顺序：Profile 与动画快照模型 → 固定角色坐标管线/警告/导出 → 首帧拖动校准和对称控制柄 → 导入继承/动画切换 → i18n/回归/实际 Qt 校准验收/发布。

重点验证：左右对称；拖动只改半宽；首次 Root X 强制吸附；Run/Attack/Jump 继承；越框仅警告、像素与缩放不变；所有动画最终 Root 一致；原始根运动保留；保存重开与旧项目兼容。

完成状态：模型、管线、编辑器、动画继承、国际化和 Windows 发布全部完成。48 项测试通过；实际 Qt 中英文/150% 校准与 4 动画共享基准通过；独立 exe 的 22 帧最终播放与框宽编辑通过。详细证据见 VALIDATION.md。
