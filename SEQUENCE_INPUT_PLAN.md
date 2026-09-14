# V0.4 单文件夹序列帧

范围：单层文件夹扫描、自然排序、导入确认、RGBA 保留、直通/继续跟踪两种路径、FPS、保存兼容、共享最终预览导出、测试与 Windows 发布。多动画父文件夹批量识别作为第二阶段。

约束：直通优先于 Character Profile，禁止 Root/Ground/Alpha Bounds/Motion 对齐。原尺寸帧直接成为 Cell；仅明确选择 Normalize 时调用现有预乘 Alpha 缩放。尺寸不一致默认不能导入；用户同意后按最大宽高建立画布，左上角保持不变，右侧/下侧补透明像素，绝不按帧分别缩放。

模型：旧字段保持；新增 input_mode、sequence_folder、sequence_fps、passthrough_alignment、sequence_size_policy、有序文件清单/尺寸/Alpha 摘要。视频仍以 video 为默认输入模式。现有 VideoInfo 承载当前输入统一尺寸/帧数/时序，不对序列调用 FFmpeg。

数据流：sequence scan → 用户确认 → RGBA raw cache（可显式补画布）→ passthrough final cache（可显式整画布 Normalize）→ 原有 FinalFrameProvider → Sheet/Preview/Export。选择处理模式时 raw RGBA → Root/Motion/Align，仍跳过 Chroma Key。

缓存：源签名包含自然排序清单及每个文件身份、尺寸处理策略；FPS 仅改变动画时序，不改变 raw 像素。直通最终签名不包含 Root、Chroma、Motion、Profile 或自动边界参数。文件新增/删除/修改失效；部分导入不提交 manifest。

审查：扫描与模型无 Qt；UI 只提交参数和消费 worker 快照；最终帧只有一个提供器。未跟踪的 Root/Confidence 不伪装成检测结果，导出明确标注直通。原工程默认值兼容，动画快照同时支持视频和序列路径。

实施：输入模型/扫描 → 管线直通与处理分支 → UI 确认/导航/预览 → 回归和真实 Qt 文件夹导入 → 文档/示例/Windows exe。

验收：22×512 PNG、1/2/10 排序、透明 RGB 与 Alpha 精确保留、位置不变、不调用跟踪/对齐、1536→512、混尺寸拒绝和显式补画布、22帧10列Sheet、Preview/Export像素相等、目录动画名、旧工程和路径迁移。

完成：第一阶段全部实现。67 项测试、原生 Qt 中英文与 DPI、旧视频和 V0.3 角色回归、Windows exe 视频/角色/序列三路检查通过。序列成品验证使用无效 FFmpeg 路径，确认不依赖视频工具。详细证据见 VALIDATION.md。
