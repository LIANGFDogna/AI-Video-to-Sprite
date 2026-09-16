# Test plan

## 项目标准画布

- 五种1024/1920/1080到1536尺寸示例、四侧裁补精确、RGBA透明区、视频背景填充、uint16原值和奇数差。
- 每帧按原分辨率中心适配，Root/Alpha/Profile不决定偏移；Root/ROI跟踪坐标和后续Profile源坐标基于适配后工作画布。
- 混尺寸序列、所有直通入口、Preview/Export逐像素、项目字段/动画继承/旧工程、改画布复用decoded并使下游失效。
- 新建矩形预设/自定义、导入多尺寸滚动信息、逐帧值、实际150%窗口、冻结EXE五张1536级PNG流程及原有全部回归。

## V0.4 视频抠像直通

- 56 帧合成 Dash/Jump；关键帧/跟踪/运动/Profile/自动居中函数设为抛错，仍能构建原画布且 keyed/final RGBA 完全相等。
- 1536、1024、768、512、自定义分辨率采用同一个 CanvasTransform；源1536→512、边缘和位置、0..1/3 比例。
- 56 帧/8列 sheet，所有 Cell 与 Provider/PNG 逐像素相等；Godot 不伪造 Root，Root Motion 未提取，源FPS保留。
- 完整模式↔直通、Profile/动作/Root设置保留、旧Provider失效、keyed文件时间戳不变；Chroma变化时最终缓存失效。
- 新旧工程、保存重开、动画模式快照；真实 Qt 两入口/跳过导航/Anchor恢复、预览FPS/播放/步进/洋葱皮/残影。
- 高DPI按钮必须完整落在可视区，抠像完成滚回顶部；源码与冻结EXE用56帧MP4验收像素、缩放、预览/导出/工程重开、恢复实际跟踪且不重新抠像。

阶段 1：合成绿色背景/红色角色、柔和边缘和噪声；RGBA/尺寸校验；FFmpeg 生成已知帧数视频，验证无丢帧和 Unicode 路径。

阶段 2：空 Alpha、小噪点过滤、三模式 Root/Ground、全帧 UNION、Padding、Round Up、统一 Scale、固定画布 clipping；PNG Sheet cell 顺序。

阶段 3：带纹理平移角色测试 LK/RANSAC 去漂移；无特征低置信保留；手动关键帧重启。

阶段 4：完整视频→Key→Root→Align→Sheet→Godot/单帧；缓存重用/失效、取消后恢复、JSON 往返；Qt offscreen 模拟导入、点击 Root、参数、保存和预览；PyInstaller 产物启动检查。

## v0.2 验收

- A–F：静止 ±3 像素、连续加速 Dash、跳跃抛物线、单帧 spike、脚下武器、循环漂移。追加高速抛物线最高点不能被误判为尖峰。
- 1536→512：源角落不裁掉、等比、Root 相对位置、半透明边缘颜色、全部帧/Cell 尺寸、22 帧 10 列 Sheet、空格透明。
- Pipeline：源尺寸 Key/Tracking、归一化和 Ground/Root JSON 单位、目标尺寸变化复用源缓存、旧 Provider 失效、最终 PNG 逐像素一致。
- 跟踪：透明 RGB 噪声不得产生特征；置信度指标齐全；强制光流失败后相位相关接管，再失败时有限预测。
- i18n：双语言 key/placeholder/源码覆盖、默认中文、设置持久化、旧工程字段默认值、切换语言不改变英文枚举。
- Windows 原生 Qt：22 帧 / 1536 / 24 FPS；播放全部最终帧、键盘步进、FPS 不改导出、非模态、Loop Seam、洋葱皮、残影、Before/After、导出按钮、像素一致和 stale。
- 中文 125%/150%、英文 150% 截图与控件几何；PyInstaller 启动和最终预览 smoke。

## v0.3 验收

- 左右边界恒为原点 ± 半宽；宽度编辑后其他 Profile 字段全部相等。
- 首次 Root X 吸附；加载不符合轴约束的 Profile 必须拒绝。
- Idle/Run/Attack/Jump 快照继承唯一 Profile，保存/重载/切换时 Canonical 固定。
- 不同 Alpha Bounds、不同 Root 轨迹均对齐至同一 Canonical，保留运动累计量。
- 参考越界只警告；扩大框后 PNG 字节与修改时间不变；与实际画布裁切区分。
- 1536→512 Profile 管线、精确 Root X/Y、固定 scale、源分辨率 keyed、JSON 元数据与逐像素 PNG 导出一致。
- 原生 Qt 实际拖动整帧、左右控制柄、偏轴 Root 点击吸附、确认/宽度重编、4 动画导入切换、中文与英文 150%。
- 打包 exe 在 22 帧示例上运行最终预览，并打开角色框宽编辑检查其他字段不变。

## v0.4 验收

- 22×512 PNG、Natural Sort 1/2/10、全部格式、完整 RGBA、像素位置和原画布尺寸。
- 对禁用函数注入失败：直通不得调用 Key/Root/Motion/Align/Profile/Auto Bounds。
- 1536 默认原尺寸，显式缩至512/预乘边缘；混尺寸拒绝和显式 pad 左上位置不变。
- 22 帧 10 列 Sheet、透明尾格，输入/Provider/PNG 逐像素相等，Root 元数据不伪造。
- FPS/缓存复用、源文件变更失效、相对路径往返、旧示例及混合输入快照。
- 原生 Qt 顶部导入、确认、自动 Sprite/Preview、播放步进/合成/接缝、FPS、拖入/取消/混尺寸，中英文 DPI。
- Windows 成品旧视频、角色基准、序列三路检查；无效 FFmpeg 路径下序列仍通过。

## V0.4 工程 / 位深 / 目录

- 独立 PNG/TIFF RGB8/RGBA8/RGB16/RGBA16 文件、完整 65536 色值/Alpha 映射、RGB 满 Alpha、16 位缓存、TIFF associated alpha、缩放前不丢精度、最终预览导出相等。
- 新建模板与自定义、保存重开、源/输出/FPS 继承、非法 Windows 名称、保留名称、空目录显式复用、非空目录不覆盖、旧工程/动画快照。
- 实际 Qt 未保存 Save/Discard/Cancel、空项目首页/状态、导入首个序列保留项目、Idle 校准后四动画继承、预览导出相等。
- 文件夹选择/双击/历史/路径回车/错误，浅色与深色宿主 Qt palette × 实际 DPR 125%/150%，中文与大于260字符路径，selected/hover 像素和截图。
- 冻结 EXE 增加新建→目录选择→22帧RGBA16→Preview→Export→保存自动检查。

## 编辑器
39→20首尾/关键帧、帧复制/删除/逆序/移动、区段时长与Bezier、4轨显隐/锁定/合成、拖动与批量偏移、Undo/Redo含Root、源文件不变、保存重开旧工程、最终预览与PNG/Sheet/JSON逐像素及时长一致。原生Qt125/150%和冻结EXE三条用户流程。

## Path Memory
用途隔离、创建父目录独立、E/D/C回退、缺失父目录恢复、失败/取消无写、语言合并、跨实例/进程重载、全部选择器动态侧栏；100/125/150%、小屏滚动底栏、中文空格长路径；按钮绑定/状态/快捷键/Enter/Esc；全量及最终dist。


## Path/UI本轮验证收敛
状态类回归：直通控件被Profile else分支重新启用，保留直通禁用条件修复；路径类：Qt侧栏恢复旧动态目录、默认cwd、语言覆盖设置，统一service+成功回调+侧栏重建。方案比较：逐入口补丁易漂移；仅Qt状态无法表达业务成功；统一服务与模式条件更清晰，已按本轮授权采用。191项全量及705翻译检查通过。31个算法文件哈希未变。UI_AUDIT.md列出全部调用和审查边界。


## Phase 2A验收
模型树/多源多动画多Sheet、旧迁移、UIState、Group媒体门禁/拖放、CRUD及Undo、无Reprocess、后台跨Group结果、树路径导出/空组/同名/非法字符/取消、中文及125/150%、全量旧测试、正式dist验收。
