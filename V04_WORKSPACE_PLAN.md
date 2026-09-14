# V0.4 工程创建、位深与目录选择升级

目标：保留现有视频、序列、角色基准和动画快照，完成 RGB/RGBA 8/16 位输入、正式空工程创建以及统一深色目录选择器。

模块边界：rgba_image 负责原生样本和明确范围转换；Project / project_workspace 负责项目元数据和无覆盖创建；FolderPicker 独立承载目录浏览；NewProjectDialog 提交参数，MainWindow 管理未保存确认和空项目状态。

约束：序列直通位置不变；uint16 源缓存、float32 预乘缩放、最终 RGBA8；不生成虚构 Root/Profile；项目级默认值和 Profile 必须跨动画继承；沿用 cache/<project_id>/animations；现有非空目录绝不覆盖或删除；文件夹单击选择、双击进入、确认按钮才提交；局部 Qt 深色样式不修改系统主题。

数据流：新建参数 → 校验/显式空目录复用 → 项目目录与原子工程文件 → 空项目首页 → 导入素材 → 现有管线。无工程直接导入仍建立未保存临时工程。animations 沿用 V0.3/V0.4 的字典快照，兼容空数组输入，不破坏已有 Clip。

验证：旧全套 + 位深/Alpha/Resize/PreviewExport；创建/模板/目录冲突/保存重开/未保存确认/跨素材继承；真实 Qt 目录选择的 selection/hover/path/history/双击/中文长路径，125%/150% 与应用模拟系统明暗 palette；更新四份用户文档并重新构建与成品 smoke。

完成复核：101 项测试通过，含原有67项；数据流确认 uint16 输入保留到渲染、跟踪分析副本不替换源帧、最终 RGBA8 单一提供器。架构确认项目元数据/Clip/Profile 不混存、空工程导入继承与目录无覆盖。UI 确认局部样式、四种 palette/DPR 组合、长中文路径和显式选定。Windows EXE 重新构建并通过旧三路、新工程22帧16位完整预览导出保存检查。详细记录见 VALIDATION.md。
