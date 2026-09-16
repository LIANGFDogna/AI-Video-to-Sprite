# Global constraints

本轮项目标准画布规则优先：新建项目必须先按原始分辨率中心裁剪/补边到项目宽高，视频抠像前补原背景色、RGBA补全透明，不缩放、不依赖内容。Root/Motion/Align/直通随后才执行。下文“直通保持原画布”对新项目指适配后的工作画布；旧工程0/0/none保留旧行为与坐标。

- Python 3.12；PySide6 原生 Windows GUI；所有核心算法可独立调用。
- 保留全部视频帧及唯一源编号；不自动降分辨率，不按 UI 播放速度抽帧。
- 所有帧统一 Scale；Root XY 与 Ground Y 冲突必须通过明确模式选择解决。
- AUTO 全帧联合边界；固定画布裁切必须提示具体帧。
- 磁盘缓存、有限 RAM、后台执行、取消、日志和原子完成状态。
- 先文档，逐阶段测试，更新 TASKS；不留伪实现。

## v0.2

- 统一源画布模式：源分辨率 Key/Tracking/Alignment 完成后才 Normalize；禁止按 bbox 裁剪缩放，1536→512 使用整画布 1/3。
- Root Motion、姿态、噪声分别处理；仅轨迹滤波，EXTRACT 保留位移 JSON，Jump 空中不强制贴地。
- Preview/Export 共享最终帧提供器；预览 FPS 和 Overlay 不能写回工程帧。
- 默认中文 JSON i18n，英文内部枚举稳定；旧工程可读；系统 UI 字体；高 DPI 可操作。

## v0.3 角色基准

- Alpha Bounds 属于帧；Reference Box、Canonical Root、Ground Origin、Scale 属于项目唯一 Profile。
- 首次 Canonical X 无条件吸附 Y Axis；所有后续帧最终 Root 精确等于 Canonical，禁止 Alpha 水平重居中。
- Reference Box 仅存半宽，对称派生左右，底边中心固定 Ground；框宽不改比例/Root/Origin/图像缓存。
- 超出参考框只 Warning；原始和平滑 Root Motion 独立保留。源尺寸 Key/Tracking/Alignment、最终统一 Normalize 顺序不变。

## v0.4

- 序列直通优先于 Profile：不跟踪、不对齐、不裁 Alpha Bounds，输入画布直接作为 Cell。
- 原尺寸默认；仅明确开启 Normalize 才缩放。混尺寸默认拒绝，用户同意后只补右/下透明画布。
- RGBA8 完整保留；序列不调用 FFmpeg/Chroma，处理模式也跳过 Chroma。
- Preview/Export 共享 Provider；FPS 不改变像素；旧视频工程及默认行为兼容。

- 新建项目不创建 Root/Profile；首个素材也继承已保存空项目。项目名/默认参数与角色基准为项目级数据，不随动画切换改变。
- 创建不覆盖非空目录，空目录复用须明确；保留直接导入的临时工程路径。
- 位深描述区分 bpc 与 bpp；uint16 源缓存，float32 预乘，最终 RGBA8 完整范围转换；禁止直接 dtype 截断。
- 目录选择统一自有 Qt 组件，局部主题；单击选中/双击进入/确认提交互相分离，不更改系统主题。

- 视频 keyed_passthrough 只消费抠像后完整 RGBA；禁止 Root/Ground/Profile 对齐、运动提取、逐帧居中或 Alpha 裁切。原画布默认，统一尺寸转换需用户选择。
- 抠像完成显示两个入口，模式按动画保存；恢复完整处理保留设置并复用 keyed cache。未跟踪时不导出虚构 Root，真实运动留在帧内。

## 帧编辑器当前约束
- source_frames/video/tracking保持源索引；编辑结果独立final_frames/final_timing。删除仅移除实例；同源复制帧有独立ID与偏移。
- 编辑偏移以最终Cell像素计；用户手动变换发生在项目CanvasFit和原自动处理之后；参考轨只作预览，不进入PNG。
- 五页导航，Root/Motion/Align合并编辑侧栏；源素材只读，撤销保存参数快照，耗时渲染走Worker。

## Character Reference 边界（2026-09-15）

Reference是用户摆放且锁定的项目坐标轴，不是旧跟踪Root/CanonicalRoot。首次Idle像素固定；普通编辑只改AnimationTransform整动画XY（项目像素）。中心CanvasFit及旧Profile算法不改。Ghost不套用任何动画Offset、不导出。全帧偏移复用最终Provider，越界只警告，旧字段缺省兼容。

## Path Memory本轮
机器路径历史只进app_settings，不进.aivsprite；新建成功父目录独立记忆，Work按E/D/C/Home回退；取消/失败不写历史；全部算法保持基线。


## Phase 2A当前规则优先
必须Project→Group→媒体；此前无项目直接导入流程由本轮要求取代。旧内容工程自动逻辑迁移；新增Group仅容器不改变Canvas/Key/Root/Motion/Reference/Offset。Group切换禁止隐式处理；任务绑定project/group/animation。

## Phase 2B当前规则优先
Character Reference 属于角色，不再属于项目；每个角色的基准动画必须属于该角色，跨角色移动必须阻止悬空引用或显式清除基准。跨角色移动不自动对齐、不改 Offset，只标记 Alignment Review Required。模板只创建初始 Group 结构，不限制后续编辑；本轮不实现 Animation Set 语义。
