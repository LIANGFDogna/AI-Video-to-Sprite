# Roadmap

1. 视频与色键：项目骨架、依赖检测、无丢帧解码、RGBA、即时预览、透明帧导出，先测试。
2. 最小工作流：Root 编辑、Alpha bbox、三种对齐、全帧 UNION Cell、Sheet，再测试。
3. 跟踪：Shi-Tomasi + LK + RANSAC、置信度、低置信保留、手动重启，测试漂移。
4. 桌面集成：Timeline、Overlay、后台任务、缓存、工程保存、Godot JSON、日志与打包。
5. 后续扩展：双向跟踪、Godot SpriteFrames .tres、VFR 时间戳编辑、批量动画与自动升级。

首版范围包含需求中完整可运行工作流；自动 .tres 和双向跟踪明确留待后续。

当前状态：阶段 1–4 已实现并通过核心、GUI 和 Windows 打包启动验收。下一步属于阶段 5，优先使用实际 AI 视频积累边界样本。
