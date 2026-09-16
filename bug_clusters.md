# Bug clusters

设计期重点：坐标语义不一致（bbox exclusive 与像素 Ground）；缓存依赖遗漏；取消后误用部分结果；Qt 线程生命周期；大画布内存；文件路径 Unicode 与相对引用。

实测问题与解决结果按阶段记录在本文件；避免为同一职责建立第二份算法。

## 项目标准画布复核

- 数据来源：原始decoded、适配后raw和最终Cell必须分开；若改video.width却继续解码到该宽度，会引入错误缩放。decoded manifest保存原信息，video恢复工作宽高，original_size单独保存。
- 混尺寸：不能先按最大画布右下pad再居中，否则每张原中心不同；新项目每张直接CanvasFit，旧工程沿用pad策略。
- 需求优先级：本轮项目规则高于原直通原尺寸承诺，旧UI测试从32px原尺寸改为1536项目中心透明补边；保持逐像素验证，没有关闭测试。
- Qt数据匹配：元组itemData经过Qt转换后findData匹配失败，矩形预设未改变宽高；改为稳定字符串键1536x1536/1024x1536/512x512/custom，UI测试覆盖。
- UI高DPI：多种原尺寸的裁补说明置于滚动区域；按钮完整可见。独立AnimationPreview默认第0帧，验收需显式select(4)再检查第4帧，不能把默认打开行为当成像素不一致。

三角色复核：core窗口复制与输出normalizer职责分开；项目字段唯一继承、工作坐标一致、缓存依赖完整；实际PNG/视频fixture、Qt、旧工程和发布测试验证行为。

## V0.4 视频抠像直通复核

- 分支隔离：is_passthrough 同时覆盖两种输入，视频读取 keyed、序列读取 raw；在 Root/Motion/Profile 前分流，不能只禁用 UI。禁用调用的测试同时覆盖既有 Profile 和保留的运动参数。
- 缓存依赖：视频必须使用 key_signature，不能照搬序列 raw 签名，否则改变色键后会导出旧透明帧；切回完整处理不会修改 key 签名。主视图同样复用已验证的 keyed cache。
- 状态往返：模式与 full_processing_canvas_mode 按动画保存，旧工程默认 full；最终快照失效不删除手动 Root、Motion 或 Profile。
- 元数据：直通没有实际 Root 轨迹，禁止伪造原地动画或把 sequence_fps 当成视频帧率。导出 effective passthrough、Root null、Root Motion unavailable。
- 可见性：ParameterPanel 的按钮默认排在参数表后，150% 原生截图发现新入口被滚动遮挡；两入口、状态与恢复按钮移至表前，抠像完成自动滚回顶部。UI 测试检查完整按钮 visibleRegion。截图等待 Qt 布局/绘制和帧加载完成。
- 发布目录占用：原 dist 成品进程占用日志，PyInstaller 清理旧输出时报 WinError 32。本轮使用独立 release-v0.4 目录；build.ps1 增加工作区内输出目录参数与目标 EXE 运行预检查，避免再次先清理后才发现占用。不结束用户原进程。

三角色复核：架构复用唯一 Cell/Provider；数据流检查输入分支、签名、最终帧和动画状态往返；工程检查合成位移、实际 Qt MP4、保存迁移及冻结 EXE。修复均属于本轮已授权需求。

## 阶段 4 复核

- 测试工具/GIL：GUI 测试最初用 QTest.qWait 循环，占用 Python GIL 导致后台图像处理饥饿。改为 processEvents + time.sleep，完整流程降至约 5 秒；应用正常事件循环不受该测试问题影响。
- 预览依赖：播放计时器频率高于预览防抖时会一直延后预览，播放时改为立即派发、工作中合并请求。
- 线程生命周期：换工程时创建新的预览 LRU，正在运行的请求保留原缓存引用；避免清理正在被使用的 LRU。
- 缓存发布：Save As 迁移缓存先移除目标阶段完成标志、最后复制 manifests；取消不留下假完成状态。
- 操作连续性：未保存提示选择 Save 后，成功保存会继续原先的打开/导入/关闭动作。
- 视觉验收：Windows offscreen 平台缺少系统字体，截图显示方框；Windows 验收使用原生 Qt 平台。截图等待最新预览完成，避免旧 Root 被误判。
- 打包依赖：首次 PyInstaller 分析从 PATH 中的 Poppler 收集了 `icuuc.dll`（仅导出 `ucnv_open_78`），而 Qt6Core 需要 Windows ICU 的 `ucnv_open`。独立 exe 因缺少符号在 QtCore 导入时失败。用 console 构建和 PE import/export 检查确认；build.ps1 隔离 PATH 到项目环境和 Windows 系统目录，防止混入第三方 ICU/API shim。
- 打包复验：托管运行环境在 Python 启动时重新加入工具路径，单独修改 shell PATH 不足。最终由 scripts/build_release.py 在 Python 进程内设置干净 PATH 后导入 PyInstaller；成品依赖不含无关 DLL，原生启动 exit code 0。

三角色复核：架构保持 core/Qt 分离；数据流用同一源 index 和签名传递；工程检查了取消、错误、保存续接和 GUI 线程释放。修复均在已授权首版交付范围内。

## v0.2 复核

- 数据字段/API 一致性：新增主视图预乘 resize 调用曾误传 tuple，1536 GUI 验收发现；改为明确 width/height 参数，并保持全源尺寸抠像后才缩略。
- 坐标语义：Godot raw/filtered 应为归一化后的补偿前曲线，不重复加逐帧 correction；补偿只进入 final root。
- UI/国际化：文本与内部枚举混用会破坏工程；所有组合框使用英文 itemData，资源双向覆盖及旧工程序列化测试防止回归。
- 高 DPI：长说明与不适用参数挤压属性页；左栏滚动、说明保留最小高度，统一画布隐藏无效参数，顶部增加预览入口。
- 运动异常分类：快速抛物线最高点也可能单帧反向且超过阈值；先排除该点拟合邻域加速度曲线，避免把正常最高点当 spike。
- 测试适配：独立帧出口延续 0000.png 命名，验收需与真实导出契约一致；没有更改旧文件命名来迁就测试。

修复均在用户授权的当前升级范围内。无新增云依赖，无第二套最终图像算法；结果与验证记录见 VALIDATION.md。

## v0.3 复核

- 数据类型：JSON point 数组加载后原为 list，导致缓存重载时精确 tuple 比较不一致；FrameData 统一恢复 point tuple，缓存命中和新建结果一致。
- Qt 类型：Alpha 检查返回 NumPy bool，PySide6 的 setEnabled 需要原生 bool；确认状态在 UI 边界显式转换，原生点击验收覆盖。
- 数据语义：Profile 的实际 X/Y 策略为 EXTRACT，UI 和 Godot 元数据同步显示有效规则，避免仍显示旧 Ground Lock。
- 警告语义：扩大宽度只能消除横向越界；脚或特效低于参考框底边仍应提示。实际 Qt 验收按横向和纵向分别核对，不能要求扩大宽度消除所有警告。
- 项目边界：只在首次校准调用 Alpha 站地提议；后续动画固定 Profile 变换。宽度从缓存签名排除，并在读取缓存后重新审查警告，防止旧框警告残留。
- 验收精度：宽度输入框以两位小数显示；二进制浮点的 126.10000000000001 经控件舍入为 126.1。宽度增量按显示精度检查，其他 Profile 字段仍逐项精确相等；禁止为通过验收而改变固定 Root 的精确要求。

三角色复核：架构上固定数据与逐帧检测分层，未新增第二套最终渲染；数据流上源/角色/最终坐标明确，单 Profile 多动画与 Root Motion 保存连通；工程上 48 项回归、原生 Qt 控制柄、保存切换、缓存字节及 DPI 检查通过。实现修正在用户授权升级范围内。

## v0.4 复核

- 分支污染：直通必须早于 ensure_motion/Profile 进入，不能仅关闭 UI 参数。测试将 Key/Root/Motion/Align/Profile 函数替换为抛错，并验证仍正常构建。
- 透明数据：直通不能经过预乘/恢复或色键，否则透明区 RGB 可能被清零。原尺寸直接保存 RGBA，最终 PNG 与输入解码值逐像素一致。
- 数据语义：未运行跟踪时零 Root 只能是内部占位；UI 显示已跳过，Godot Root/Confidence 为 null，Root Motion available=false。禁止提示假的 Ground=0 或低置信度警告。
- UI 事件参数：顶部按钮的 clicked(bool) 可能传入预览 export_folder；在入口归一化为 None，防止未导出就显示打开目录。
- 导入边界：混尺寸不静默缩放；确认前不改变当前项目。用户明确 pad 时只补右/下透明画布，取消保持原项目快照。
- 缓存与时间：sequence_fps 与 VideoInfo 同步，保存前再次统一时序；FPS 不进入 raw/final 像素签名。序列文件新增/修改触发最终缓存更新。
- 格式边界：管线是 RGBA8，扫描拒绝高位深和多页/动态图像，避免精度截断或只读取首帧。损坏图像记录完整文件路径，不能静默跳帧。

三角色复核：core 扫描与 UI 确认分离，现有 Provider/Export 复用；视频/序列路径和动画快照完整往返；67 项测试、真实 Qt 序列导出、中英文 DPI、旧视频和角色基准回归通过。修正属于用户授权的 V0.4 第一阶段。


## 本轮直通入口复现与交付修复

- 成品不一致：dist EXE 的 SHA256 为 E8D69D...，仍为直通实现之前版本；release-v0.4 为7C73D4...，后者日志已有 key→align→sheet 且无Root/Motion的成功记录。原dist日志最新流程仍包含手动Root。不能只在新目录打包而让用户常用入口保留旧程序。
- UI分支：即使新版完成Key，用户直接点通用Build且没有首帧Root，旧逻辑仍切回Anchor。现在转到Sprite显示明确的直通／继续Root入口；模式由用户选择，已有Root完整处理不变。
- 回归：原画布及启用项目画布两种情况下，从通用Build选择直通，禁止Key/Root/Motion再运行，56帧Preview/PNG与keyed逐像素相同。
- 测试环境：系统旧pytest临时目录与沙箱helper权限异常，改用工作区内新UUID临时目录运行测试；不变更文件ACL。全量136项通过。

## 2026-09-15 编辑器重构复核

- 索引与时间：源 video/tracking 不可被减帧覆盖；实例 ID、最终帧索引、源索引与 final_timing 分离。Root Motion 明示原源时间基准，Godot 保存最终 duration。
- 缓存一致性：实时 Provider 和落盘 final 共用 renderer；签名纳入编辑数据、FPS、loop；移除 Alpha/Root 的隐式内容居中。空时间线拒绝构建，避免导出旧 Sheet。
- 未跟踪直通：最终警告扫描不能把 confidence=0 的已对齐帧当跟踪失败；参考轨与辅助叠加禁止写入最终 PNG。
- UI 状态：七页假索引改为真实五页；Root 校准始终展示适配后的源画布。基础对齐因 Root 修正失效时，左侧源帧浏览和步进仍可用。
- DPI：单个屏幕整数坐标的 fit 缩放拖动有量化误差；精确 -6/+14 测试使用 100% 画布。属性 Bezier 四列改为两行，仅自定义显示；轨道表头取消最后列自动拉伸，修复锁定列溢出。
- 实际 Qt：等待异步画布就绪后再点击；框选测试从帧块内侧边界圈选，避免邻块笔宽交叠；帧块文字裁限于块内。

## Path Memory审查
已复现/静态确认：空FileDialog路径隐式使用dist cwd、NewProject硬编码Documents、语言保存覆盖整个设置、NewProject长表单无滚动。修复授权来自本轮用户需求；采用统一服务与业务成功回调，保留算法边界。方案比较见PATH_MEMORY_PLAN.md。


## Path/UI本轮验证收敛
状态类回归：直通控件被Profile else分支重新启用，保留直通禁用条件修复；路径类：Qt侧栏恢复旧动态目录、默认cwd、语言覆盖设置，统一service+成功回调+侧栏重建。方案比较：逐入口补丁易漂移；仅Qt状态无法表达业务成功；统一服务与模式条件更清晰，已按本轮授权采用。191项全量及705翻译检查通过。31个算法文件哈希未变。UI_AUDIT.md列出全部调用和审查边界。


## Phase 2A前置审查
当前_select_animation会导入/构建，旧success闭包直接覆盖self.project，_loaded重置Frame。均是单上下文假设，在多Group中形成串数据风险；采用UUID任务上下文、只读缓存恢复和Library控制器，不改核心算法。
