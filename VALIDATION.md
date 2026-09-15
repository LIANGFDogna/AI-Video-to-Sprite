# Validation record · v0.4

## 2026-09-16：Path Memory / UI Audit

交付前完整回归：**191 passed，60.89秒**，`build/path-complete-regression.log`。新增28项（21项路径服务、7项窗口与业务接入），保留原163项测试。**705 keys**中英键集、占位符及源码覆盖通过。第一次完整回归发现直通模式Root/Motion字段重新启用，修正UI状态优先级后两次全量191项通过；未修改像素算法。31个core/models/exporters文件逐个SHA256等于PATH_MEMORY_PLAN.md基线，`build/path-protected-hashes.json`为passed。

原生窗口：`build/path-native-actual100`实际DPR1.0；`build/path-native-final-1.25`实际DPR1.25且英文；`build/path-native-150d`实际DPR1.5。exercise.json与**独立第二进程**restart.json均passed。视频A、透明序列B、Sheet导出C、工程D和新建父目录独立恢复；取消保持历史。中文、空格、深层目录超过275字符、新建1366×768/1920×1080/2560×1440等效逻辑尺寸固定底部按钮通过。

100%初次配置被本机125%系统缩放影响，`path-native-final-1`的实际DPR1.25，**不作为100%证据**。后续用明确屏幕因子1.25×全局0.8得到实际1.0；正式构建对每个报告断言实际DPR，防止误报。

UI审查计数：10个业务FileDialog调用、120个控件/Action构造或帮助函数声明点、149个信号连接点。19种窗口/状态记录438次控件观察；去除主窗口空/就绪重复状态为286条控件实例记录（含Qt内部控件，不代表286个独立产品功能）。完整清单、覆盖方式、修复和限制见UI_AUDIT.md。UI脚本自身曾发生文件选择模型异步、弹窗重入/未保存确认及变量作用域问题，均修正后才计作通过。

### 冻结候选验证（本轮）

`build.ps1 -DistPath release-v0.4-path-memory-ui-audit` exit code 0，日志build/release-path-memory-ui-audit.log。独立EXE启动、旧视频Normalize、旧CharacterProfile、无FFmpeg序列、新建/RGBA16/文件夹、56帧视频直通与返回完整处理、项目Canvas Fit、编辑器三流程和Character Reference 125/150%均通过。

新增路径冻结证据（每项包含exercise.json与第二进程restart.json，均passed）：

- 实际DPR 1.0 / zh_CN：`build/path-frozen-1-76d962a30abe41b1a9e2bf21aa513a08`。
- 实际DPR 1.25 / en_US：`build/path-frozen-1.25-215af90038d04203bfadc9012a164aa2`。
- 实际DPR 1.5 / zh_CN：`build/path-frozen-1.5-b2bebea0acce433ca6bfa55321ac37b4`。

构建标识`20260915-path-memory-ui-audit`；候选EXE文件时间2026-09-16 00:05:39；SHA256 `B61D423A4507E2AC2D16FC5C3ECE3AB76620DD01CC5476DB43B96676F19CEEB8`。正式dist已替换并通过独立启动验收，见下节。

### 正式dist发布与实际启动（本轮完成）

2026-09-16用户继续后确认旧程序已退出，执行scripts/publish_release.ps1成功。正式路径：`E:\AI Video to Sprite\dist\AI Video to Sprite\AI Video to Sprite.exe`。运行文件已备份到`E:\AI Video to Sprite\build\previous-runtime-0e4d4b64222b4b29a91af6034f0985dc`，既有工程、素材、cache和exports未删除。根目录启动bat继续指向正式dist。

正式EXE文件修改时间：`2026-09-16T00:05:39`；发布完成记录：`2026-09-16T06:35:35+08:00`；SHA256 `B61D423A4507E2AC2D16FC5C3ECE3AB76620DD01CC5476DB43B96676F19CEEB8`，与候选成品一致。**实际从上述dist EXE启动**新建/视频A/序列B/导出C/工程D/另存/预览/对话框审查，并关闭再以独立进程重新验证路径恢复；100/125/150%全部通过。

- 实际DPR1.0，zh_CN：`build/path-published-1-064bcc4c9a49414c8418ff4708992ead`中的exercise.json/restart.json均passed。
- 实际DPR1.25，en_US：`build/path-published-1.25-909a1ecbe2a0424581ae51889e7f7e9f`中的exercise.json/restart.json均passed。
- 实际DPR1.5，zh_CN：`build/path-published-1.5-3a805ba7c70e4122b3728d4dd6ed174b`中的exercise.json/restart.json均passed。

正式验收汇总build/path-published-receipt.json；最终交付build/path-memory-delivery.json。每轮438条窗口状态观察（去除主窗口重复状态286条控件实例）；三次属于重复DPI验收，不累计成更多产品按钮。

以下旧版记录保留为历史。

## 2026-09-15：Character Reference 第一阶段

最终全量 **163 passed，70.11秒**，`build/reference-complete-regression.log`；包含全部旧测试及新增角色参考/缺失素材UI保护。中英文 **689 keys**，键集/变量/源码覆盖检查通过。初次复核曾遇到一次Windows WinError5目录重命名拒绝，位深导出12项独立复测与上述完整163项均通过，未更改导出事务语义。

覆盖参考创建、锁定、Ground/YAxis/Origin拖动、1/10px微调、Idle像素不变、项目唯一/各动画偏移独立、全帧统一XY、RGBA16与1536→512、越界非阻塞、Undo/Redo、旧CharacterProfile兼容和保存重开。输入1024×1536/1920×1536/1920×1080的中心裁补在Reference修改前后逐像素一致；真实视频keyed直通不调用重复decode/key/Root。

原生窗口验收：`build/reference-native-actual125/validation.json`（DPR1.25）与 `build/reference-native-150-verified/validation.json`（编辑窗口及校准窗口均DPR1.5）通过。已查看150%校准/Run编辑截图：轴、原点坐标、整动画XY和保存按钮清晰；Ghost固定，属性区无水平滚动。早期仅对第一个显示器设置150%的报告实际为125%，不计作150%证据；发布测试现对所有显示器显式设置缩放并断言实际DPR。

新增 `app/character_reference_smoke.py` 为原生/冻结通用入口。真实1024×1536 Idle MP4→1536项目左右补256→抠像→直通→校准固定Idle→锁定→设置Idle自身Offset→导入Run RGBA→共轴及固定Ghost→拖动全动画/1px与Shift10px→512输出→播放→6张PNG/3列Sheet逐像素一致→Undo/Redo→保存重开→Run内重编辑仍读取Idle原图并取消。每次结果JSON记录实际DPR，避免系统缩放与QT_SCALE_FACTOR叠乘误报。

### 本轮冻结成品

构建 `build.ps1 -DistPath release-v0.4-character-reference` **exit code 0**，日志 `build/release-character-reference.log`。已完成真实EXE启动、旧视频Normalize、CharacterProfile、无FFmpeg序列、新项目/RGBA16/FolderPicker、56帧视频直通、五种项目画布输入、编辑器三流程，以及角色参考125%/150%全流程。

冻结角色参考证据：

- 实际DPR 1.25，校准窗口同值：`build/reference-frozen-1.25-068359009e10478a8f7f72f6800a78c1/validation.json`，passed。
- 实际DPR 1.5，校准窗口同值：`build/reference-frozen-1.5-3920b1a78cde4e60aaba6392f327bb9a/validation.json`，passed。

成品构建标识：`20260915-character-reference`；窗口标题可见。SHA256：`97CB2A6465A4EB85FF820F1949313759BF7CACCF9A5D2B0BD17A53159761A361`。

候选程序：`release-v0.4-character-reference/AI Video to Sprite/AI Video to Sprite.exe`。

**已发布到实际日常路径**：`E:\AI Video to Sprite\dist\AI Video to Sprite\AI Video to Sprite.exe`。用户确认保存关闭后，`scripts/publish_release.ps1 -SourceRoot release-v0.4-character-reference`成功更新并实际启动dist Smoke Test，exit code 0。日志 `build/publish-character-reference.log`；旧运行文件备份 `build/previous-runtime-90f7f9860e7749bda3e88d5b6b79b4e9`。用户工程、素材、缓存、已有示例和导出均保留。

实际dist EXE文件时间：`2026-09-15T18:40:17`；SHA256与冻结验收候选完全一致。根目录 `Start AI Video to Sprite.bat`继续指向该dist EXE。

随后**直接启动同一个dist EXE**：`--smoke-character-reference build/published-reference-150`，exit code 0。`build/published-reference-150/validation.json`记录编辑/校准DPR均1.5、真实MP4抠像与中心补边、固定Idle校准/共轴/整动画XY、原Idle缓存mtime不变、Ghost忽略双方Offset、6帧最终Preview/PNG/Sheet像素一致、Undo/Redo及保存重开全部passed。不是从源码或旧release目录运行。测试窗口已正常退出。

本轮限制：每项目一套角色参考；只新增整动画XY，旧逐帧编辑保留独立入口；参考/Ghost均辅助显示；完整Library/Character Templates/Animation Set目录结构为下一阶段。

## 2026-09-15：五页帧动画编辑器

Windows x64 / Python 3.12.14。最终全量 **147 passed，45.71 秒**，日志 `build/editor-final-regression.log`；中英文 **655 keys**，源码覆盖、键集合与变量检查通过。保留旧视频/序列/高位深/画布/直通/角色基准测试；旧 UI 断言仅将入口迁移到五页与编辑页内“对齐”标签。

- 39→20 Ease In Out，保留首尾和标记关键帧；单/多删除、复制独立实例、选段倒放、跨轨移动、锁定禁止修改、Undo/Redo 与 Root 修正。
- 源索引和源文件不改变；位移按最终 Cell 像素应用，透明隐藏 RGB、Alpha 与身份变换逐字节保留；多轨浮点预乘合成顺序正确。
- 选段目标时长、曲线、不同停顿分布、自定义 Bezier 单调校验；位置/比例/透明度插值保留中间关键帧。
- 实时 Provider 与落盘 final、Sheet/PNG/JSON 的像素和时长一致；参考轨不导出，空时间线不能误导出旧结果。
- 真实 Qt 点击/Ctrl/Shift/框选、鼠标跨轨拖动、曲线控制柄、画布拖动和 Shift 微移通过；Root 修改使缓存失效后仍可浏览源帧并向后步进。

150% 原生 Qt 三流程：`build/editor-native-150-verified/validation.json` **passed**，DPR=1.5，五个页面；源码入口 `python -m app.main --smoke-editor <新目录>`。

| 实际操作 | 输出 | 验证 |
|---|---|---|
| 39 帧全选→20 帧→缓入缓出 | 20 帧，0.8333333333 秒 | 首末源帧 0/38；实时预览与全部 PNG/JSON duration 相同 |
| Undo→拖动第12帧(-6,+14)→第13帧数值偏移→删除3帧→复制1帧→末段倒放 | 37 帧，1.5416666667 秒 | 源39张不变；洋葱皮/残影仅预览；全部 PNG 一致 |
| 复制末段并倒放→中段2倍速→特效轨→参考轨→Bezier | 46 个输出时间区间，1.5003333333 秒 | 时间边界合成、PNG逐帧一致；工程保存重开保持编辑数据与输出 |

已查看 `editor-20-ease.png`：深色文字清晰、选中帧高亮、锁定列完整、属性无水平滚动、旧重复视图工具栏隐藏；曲线与“应用目标帧数”可见。自定义 Bezier 控件两行显示，其他曲线隐藏数值控件。

旧视频实际窗口：`build/editor-old-video-verified.log` **passed**；24 帧，Cell=197×221，最低跟踪置信度0.94858656，Root 添加/删除、跟踪、编辑内播放、保存重开和 Godot 导出通过。项目标准画布仍先于跟踪和时间线，视频抠像直通仍无需 Root。

编辑器独立候选已通过冻结125%/150%三流程验收（`build/editor-smoke-a66f826db5e5436c8feb146b3cdf2506/validation.json`、`build/editor-frozen-150/validation.json`）。本轮合并角色参考后再次构建，最终dist以本文件最上方最新记录为准。下文为历史版本记录。

---

## 2026-09-14 历史：项目标准画布

Windows x64 / Python 3.12.14。全量pytest **136 passed，40.00秒**（画布11项、此次直通UI2项、未接入UI的编辑模型9项）；中英文574条，源码覆盖和变量检查通过。前轮新项目直通测试的预期按新要求改为先适配项目画布，其余测试保留。

- 1024×1536左右补256、1920×1536左右裁192、1536×1024上下补256、1536×1920上下裁192、1920×1080左右裁192且上下补228；逐像素切片一致，补区RGBA全0。
- 奇数差的右/下余量、uint16不插值、不量化；混尺寸每帧按自身原中心适配，无最大画布中转，无Root/Motion/Profile调用。
- 视频64×48→48×64混合裁补，先背景色补边再Chroma；适配后Root=(16,25)、Alpha Bounds=(12,20,22,36)，Character Profile再从这些工作坐标对齐，直通像素和导出相同。
- 项目字段创建/自定义/保存/切换/继承、旧工程none默认值；原始尺寸单独保留；修改画布使下游失效但复用视频decoded缓存。
- Qt矩形预设、自定义宽高、混尺寸确认提示、逐帧适配信息、预览与PNG导出逐像素一致。

真实Qt验收：`python -m app.main --smoke-project-canvas .test-output/project-canvas-150-final`，**exit code 0**，实际DPR1.5。创建1536项目，导入上述五种实际PNG尺寸；Cell均1536，位置完全由尺寸中心差派生；Sheet为12288×1536（8列，末3格透明），Preview/Export相同并保存重开。截图与validation.json保存在该目录。

本轮 `.\build.ps1 -DistPath release-v0.4-canvas` **exit code 0**，构建日志 `build/release-canvas-direct.log`。冻结EXE完成启动、旧视频Normalize、Character Profile、无FFmpeg序列、新项目/RGBA16、视频直通和项目画布验收。

125%冻结证据：`build/keyed-smoke-9e11287848224158a20f2dcdba941ae6/validation.json`、`build/canvas-smoke-1fb8a3e2610c43cfacd32e0e9c765718/validation.json`，均passed。

随后 `.\scripts\publish_release.ps1 -SourceRoot release-v0.4-canvas` 将同一已验收程序更新到 **`dist/AI Video to Sprite/AI Video to Sprite.exe`**，启动检查成功。发布日志 `build/publish-canvas-direct.log`；旧运行文件备份在 `build/previous-runtime-66db408cd2d54c80923bf91faa4a47cf`。发布仅覆盖程序、依赖和文档，保留原工程、素材、缓存、日志及已有示例；新建根目录 `Start AI Video to Sprite.bat` 固定启动dist。

最终EXE的SHA256（dist与验收目录一致）：
`AC86205CA8E5C7613C8155F83226F1CE4B696A17E9807BA20C52F496B2ADF5CC`

直接运行已更新的dist EXE进行150%验收，均 **exit code 0**：

- `build/published-keyed-150/validation.json`：实际DPR1.5，56帧、24 FPS；通用Build无Root进入Sprite选择；直接构建native与keyed逐像素一致；512输出Sheet为4096×3584；Preview/Export、保存重开、恢复完整流程不重做Key均通过。
- `build/published-canvas-150/validation.json`：实际DPR1.5，新建1536项目及五种输入尺寸；透明补边和中心裁切正确；最终Preview/Export一致，保存重开成功。
- 人工查看最终EXE截图 `sprite-keyed-choice.png` 和 `sequence-canvas-fit.png`：两入口完整可见、文字清晰、尺寸说明滚动显示、导入按钮可见。新建、预览及导出截图同目录保存。

此历史轮次交付为七阶段V0.4。帧编辑器模型的9项测试属于预研，尚未接入主界面，不计为五阶段编辑器功能完成。

新增直通入口回归：无Root时从通用Build进入Sprite选择，继续Root保持完整模式；直接构建使用已有RGBA。在旧画布和128×112项目画布两种情况下，56帧无额外跟踪、抠像、对齐调用，PNG/Preview逐像素相等。源全量测试日志：`build/canvas-direct-pytest.log`。

---

## 2026-09-14 前轮：视频抠像后的直通精灵图

Windows x64 / Python 3.12.14。全量 pytest：**114 passed，37.05 秒**，保留原有 101 项，新增 13 项。双语言 **543 个 key**，源码覆盖和变量检查通过。

- 56 帧 synthetic Dash / Jump：原画布 final 与 keyed RGBA 逐像素一致；水平 55px 位移、垂直 45px 跳跃保持。强制禁止 Root/Motion/Profile/自动居中调用仍能构建。
- 原生、1536、1024、768、512 和自定义尺寸；所有帧使用同一个 CanvasTransform。1536→512 为整画布 1/3，角落及位移像素保留，不按 Alpha Bounds 裁切。
- Sheet、Provider、导出 PNG 逐像素一致；56 帧 × 8 列布局正确。Godot 的 Root/Confidence 为 null，有效 alignment_mode=passthrough；Root Motion available=false，FPS 使用真实视频值。
- 进入直通、恢复完整流程保留手动 Root/Alignment/Motion/Profile；退出重建实际跟踪不重做 Chroma。源或抠像参数变更使最终缓存失效；旧 Provider 不能继续使用过期帧。
- 保存、另存、重开、动画模式快照及旧工程 full 默认值；保留旧序列直通、位深、新建项目、角色坐标系和目录选择行为。
- 真实 Qt 两入口/跳过导航/Anchor 恢复、预览播放/步进/FPS/洋葱皮/残影。抠像处理前将参数面板滚到底部，完成后两个按钮必须完整可见。

### 实际视频与界面

`python -m app.main --smoke-keyed-passthrough examples/keyed_passthrough_56.aivsprite --smoke-output .test-output/keyed-video-150-final`：**exit code 0**。真实 FFmpeg 解码 56 帧合成 MP4，原生 Qt 默认深色主题，实际 DPR **1.5**。截图和 `validation.json` 保存在上述目录。

检查：全帧抠像 → 无 Root 选择直通 → 默认 256×256 源画布像素相等 → 明确选择 512×512 → 8 列 × 7 行 **4096×3584** → 独立预览播放/12 FPS（源仍24）→ 56张导出逐像素相同 → 保存重开仍直通 → 启用完整处理并实际跟踪，keyed PNG 时间戳不变且 Chroma 函数禁止调用。

150% 截图验证抠像页两按钮、Sprite 直通状态/恢复按钮置顶可读。最初截图发现按钮排在参数表后，现已修正；截图等待布局与异步帧完成，不使用尚未绘制的控件作为验收证据。示例为合成视频，不代表所有真实 AI 素材均无需调参。

### 本轮发布验证

`.\build.ps1 -DistPath release-v0.4`：**exit code 0**。日志 `build/release-v04-keyed-final.log`；约40秒完成 PyInstaller，随后启动、旧视频 Normalize、Character Profile、无 FFmpeg 的序列、新建项目/RGBA16，以及新增 56 帧视频直通全流程均通过。运行记录位于 `logs/app.log`（2026-09-14 16:14）。

冻结 EXE 的新流程证据：`build/keyed-smoke-e8bd03d1b96c4de3ba4f082584cbc335/validation.json`，实际 DPR **1.25**；56帧、24 FPS、4096×3584、keyed/native 像素一致、Preview/Export 一致、保存重开、恢复完整处理不重做 Chroma 全部为 passed。

新版成品：`release-v0.4/AI Video to Sprite/AI Video to Sprite.exe`。必须保留同名目录的全部文件。原 dist 进程占用日志，首次覆盖构建因 WinError 32 失败；已改用独立发布目录，并给构建脚本增加目标进程运行预检查及工作区目录校验，没有结束原进程。

本轮 EXE SHA256：`7C73D44987F5408CF13B6062F263834E6BEC7D1D3D0ABE181F0927FC211AE2FF`。

---

## 2026-09-14 前轮：新建项目 / RGB(A) 16 位 / 深色目录选择

Windows x64，Python 3.12.14。全量 pytest：**101 passed，28.30 秒**；原有 67 项全部保留，新增 34 项。中英文 **527 个 key**，源码覆盖和变量检查通过。

- 独立构造 PNG/TIFF 文件，验证 RGB8/RGBA8/RGB16/RGBA16。RGB8 为 24 bits/pixel，RGBA16 为 64；Alpha 缺失补满，16 位 raw PNG 缓存仍为 uint16。
- 遍历完整 65536 个输入值，RGB 与 Alpha 的 16→8 四舍五入结果正确；1536→512 float32 预乘缩放保持轮廓颜色。16 位继续 Tracking/Align 也可运行，源对齐缓存保留 16 位。
- FinalFrameProvider / Before 显示 / 最终 PNG 像素一致；单帧位置和透明 RGB 按直通规则保留。TIFF associated alpha 有独立覆盖。
- 新建项目、目录树和工程文件、三个模板/自定义画布、默认 FPS、Windows 非法/设备名、显式空目录复用与拒绝覆盖非空目录。
- 未保存确认三条路径：保存后续接、不保存后打开创建窗、取消保留工程。空工程保存重开无需素材；首个序列导入保留名称/项目 ID/默认 FPS/保存位置，直通覆盖模板自动尺寸转换。
- 旧工程与空 animations 数组兼容；当前 animations 字典及 Character Profile 不迁移、不复制进 Clip。

### 实际 Qt 窗口

`scripts/smoke_workspace.py`：浅色/深色**宿主 Qt palette**，各在实际 DPR **1.25 / 1.5** 下运行。未修改 Windows 系统设置；未把 palette 模拟宣称为实际切换系统主题。

四组证据：`.test-output/v04-ui-dark125`、`v04-ui-dark150`、`v04-ui-light125`、`v04-ui-light150`。每组保存截图和 report.json。

- 选中背景 `#287e71`，白色文字；Hover `#34485f`，像素检查与截图均通过。
- 返回/前进/上一级和新建文件夹为文字按钮，导航历史可用；路径栏和当前选择清晰。
- 单击不提交，双击进入目录，确认按钮才返回路径；输入不存在目录提示错误。
- 中文路径和 **274/275 字符**目录可进入、显示并选择；完整路径保留在输入框和提示中。
- RGBA16 导入窗口同时显示 16-bit/channel 来源和 8-bit/channel 最终帧；新建窗口和空项目首页无文字裁切。

`scripts/smoke_character_space.py --new-project`：`.test-output/v04-new-project-character/validation.json` 通过。实际创建 MainCharacter → Idle 站地/拖动/偏轴 Root 吸附 → 4 动画 → 预览/导出/保存重开；所有 Root 为 `(256, 334.07624633431084)`，Y Axis X=256，框宽编辑不修改 PNG 字节/时间戳，项目级参数与 Profile 保持一致。

### 本轮发布验证

`python -m app.main --smoke-workspace .test-output/workspace-release-source` 已通过：22 张 RGBA16、最终 RGBA8、24 FPS 预览、5120×1536 Sheet、导出逐像素一致并保存重开。

`.\build.ps1`：**exit code 0**。日志 `build/release-v04-workspace.log`，PyInstaller 构建完成；成品启动、旧视频 Normalize、Character Profile 与框宽编辑、无 FFmpeg 的 22 张 RGBA8 序列，以及新增项目/目录/RGBA16 全流程检查均通过。运行记录位于 `logs/app.log`（2026-09-14 11:16）。

成品：`dist/AI Video to Sprite/AI Video to Sprite.exe`，须保留完整同名文件夹。可选“最近项目”列表及父文件夹批量发现动画留待后续。

前轮 EXE SHA256（历史记录）：`E8D69D0388AF48958299CE4415740D6B2C198AE754493B9E99C663F6833EE4BD`。

---

## V0.4 初始序列导入：历史记录

验证日期：2026-09-14。Windows x64 / Python 3.12.14。

## 初始单文件夹序列帧

`.venv\Scripts\python.exe -m pytest -q`：**67 passed，23.93 秒**。保留 V0.3 全部 48 项测试，新增 19 项覆盖：

- 22 张 512×512 PNG、RGBA 检测、目录名作为动画名、默认 24 FPS。
- Natural Sort：frame_1、frame_2、frame_10；忽略非图像文件。
- 直通不调用色键、Root、Motion、Align、Profile、Auto Bounds；即使保留 Root/Scale/Profile 参数，图像也不改变。
- 输入完整 RGBA 与最终帧逐像素一致，透明 RGB、半透明 Alpha 和角落像素保留，无裁切/居中。
- 22 帧、10 列 Sheet 为 5120×1536，末尾透明；输入/Provider/导出逐像素相同。
- 1536 默认保留原尺寸，显式 Normalize 后为 512，比例 1/3，预乘边缘无透明 RGB 污染。
- 混尺寸默认拒绝，明确 pad 后保持左上坐标，只补透明区域。
- Animation FPS、保存/重载、相对目录、源文件变化缓存失效、FPS 变更复用 raw/final PNG。
- 序列处理模式保留 Alpha、跳过 Chroma，再进入现有 Root/Motion/Align。
- PNG/WEBP/TIFF/BMP/JPG/JPEG；V0.1～V0.3 示例兼容；视频与序列动画快照共享 Profile。

`python -m scripts.check_i18n`：**473 个 key，源码覆盖及中英文变量一致**。

## 原生 Qt 验收

`scripts/smoke_sequence.py` 完成顶部点击导入→目录选择→默认直通/24 FPS 确认→自动进入 Sprite→每行 10 帧→直接打开预览→播放→导出。验收工程保留已有 Character Profile，以确认它不影响直通像素。

| 检查 | 结果 |
| --- | --- |
| 输入、最终预览、导出 | 22 帧逐像素一致，包含透明区 RGB |
| Cell / Sheet | 512×512 / 5120×1536，最后 8 格透明 |
| Root/Chroma/Motion/Align | 已跳过，无 Root 种子要求 |
| Character Profile | 数据保留但不应用变换，预览不画假 Root |
| 播放 | 24 FPS，1.3 秒遍历全部 22 帧 |
| 步进、FPS、Loop Seam | 正常；接缝序列 [19,20,21,0,1,2] |
| 洋葱皮、残影、前后切换 | 正常，合成不改变 Provider 图像 |
| 实际 Animation FPS | 改为 18.5，保存/导出正确，raw/final PNG 修改时间不变 |
| 文件夹拖入 | 正确进入导入确认窗口 |
| 混尺寸 | 默认禁用导入；取消不改项目；明确补画布后 Cell=600×512 |
| 语言/DPI | 中文本机缩放、中文 150%、英文 150% 通过 |

证据：`.test-output/sequence-zh/validation.json`、`.test-output/sequence-zh150-final/validation.json`、`.test-output/sequence-en150/validation.json`。截图：`docs/sequence-import.png`、`docs/sequence-sprite.png`、`docs/sequence-preview.png`。

旧功能实际窗口回归：`scripts/smoke_gui.py .test-output/v04-video-regression` 通过 24 帧视频全流程，Cell=197×221；`scripts/smoke_character_space.py .test-output/v04-character-regression` 通过首帧校准、左右控制柄、4 动画共享基准、宽度缓存和 PNG 一致性。

## Windows 发布包

`.\build.ps1`：**exit code 0**，日志 `build/release-v04.log`。

- `--smoke-test`：独立 exe 启动并退出。
- 22 帧旧 Normalize 视频项目：构建与最终播放通过，512×512、24 FPS。
- 22 帧 Character Profile 项目：固定 Root `(256,350)`、Y Axis=256，动画播放与框宽独立编辑通过。
- 发布包内 `examples/sequence_idle.aivsprite`：从 22 张 PNG 冷缓存构建、播放，全部输入/最终像素一致。测试将 FFmpeg 与 ffprobe 指向不存在的程序，仍正常通过。
- 成品附带 22 张序列示例 PNG、序列工程和旧示例；Qt/Python/OpenCV/Pillow 及中英文资源已打包。

成品：`dist/AI Video to Sprite/AI Video to Sprite.exe`。请保留完整同名文件夹。

本轮之前的历史 exe SHA256：`837A1E753715A4F3BDF378FDFD367E1A8C367B2D6F886FDD74CFD536F0B7191A`。

## 范围与数据流复核

初始阶段完成单个动画文件夹，父目录批量识别多个 Clip 留到第二阶段。原先仅允许每通道 8 位的限制已被本轮 8/16 位支持取代；多页/动态图像仍需先拆帧。视频输入继续需要 FFmpeg，序列输入不需要。

直通分支在跟踪/对齐前分流，Profile 和 Alpha Bounds 不参与位置计算。混尺寸只在用户明确同意后补画布。最终 PNG、Sheet 与 Preview 继续使用唯一 FinalFrameProvider；只有明确 Normalize 才缩放，真实 FPS 与预览 FPS 分开。Root/Confidence 未测量时导出 null，Root Motion unavailable。所有验收素材为合成数据，真实 AI 视频的跟踪限制仍适用。

---

# v0.3 历史验收记录

本轮验证完成于 2026-09-13，记录整理于 2026-09-14。Windows x64 / Python 3.12.14。

## 当前版本：角色基准

`.venv\Scripts\python.exe -m pytest -q`：**48 passed，26.25 秒**。原有 38 项回归全部保留，新增 10 项覆盖：

- 左右边界按原点 ± 半宽派生；修改任一控制柄只改变半宽，其余 Profile 字段完全相等。
- 首次偏轴点击强制吸附；加载偏离 Y Axis 的 Canonical Root 会拒绝。
- Idle、Run、Ground Attack、Jump 共用一份 Profile；保存、重载、切换保留 Canonical 和更新后的框宽。
- 不同动作轨迹和 Alpha Bounds 均按固定 Canonical 原地对齐，原始和平滑运动位移独立保留。
- 越界只警告，扩大框不改变 PNG 字节及修改时间，也不改变角色比例、Origin、Root。
- 1536→512 Profile 管线保持源尺寸抠像，Scale 为 1/3，所有最终 Root 精确一致，PNG 与 Provider 逐像素相等，Godot 有效策略为 EXTRACT。

`.venv\Scripts\python.exe -X utf8 -m scripts.check_i18n`：**432 个 key，源码覆盖完整，中英文变量一致**。

## 原生 Qt 交互

`scripts/smoke_character_space.py` 使用实际 FFmpeg 编码的 8 帧素材，执行：导入 Idle → 首次校准 → 拖动整帧 → 偏轴 Root 点击 → 左右控制柄拖动 → 确认基准 → 构建 → 缩小/扩大参考框 → 添加 Run / Ground Attack / Jump → 切回 Idle → 保存重载 → 最终预览 → Godot 导出。

| 检查 | 结果 |
| --- | --- |
| Canonical X 与 Y Axis | 始终精确等于 256.0 |
| 首帧整图拖动 | 改变图像位置，Scale / Ground Origin 不变 |
| 两侧控制柄 | 对称联动，只改变半宽 |
| 确认后编辑 | 仅开放框宽，Canonical/Scale/Origin 固定 |
| 动画共享 | 4 个动画、一份 Profile；切换/保存/加载保留同一 Root |
| 越界与缓存 | 警告正确；PNG 字节与修改时间不变 |
| 垂直越界 | 扩宽后仍按实际 Ground 越界保留警告 |
| 输出与预览 | 全部 512×512，逐像素相等，JSON Root 精确相同 |
| 中文/英文 | 本机显示缩放及中英文 150% 检查通过 |

证据：`.test-output/character-zh3/validation.json`、`.test-output/character-zh150/validation.json`、`.test-output/character-en150/validation.json`。截图：`docs/character-space.png`、`docs/character-preview.png`。

这些素材为合成验证，不能代表真实 AI 视频的跟踪准确率。每个新视频仍需设置自己的首帧跟踪种子；项目 Canonical Root 不会随之改变。

## Windows 发布包

`.\build.ps1` 最终运行 **exit code 0**；日志为 `build/release-v03-final.log`。

- `--smoke-test`：启动并正常关闭。
- `--smoke-preview examples/normalized_512.aivsprite`：22 帧、24 FPS、512×512 最终动画播放，与 Provider 一致。
- `--smoke-preview examples/character_profile.aivsprite`：22 帧全部 Root 精确为 `(256.0, 350.0)`，Y Axis 为 256；最终动画播放后打开角色编辑器，框宽变化只修改半宽。
- 角色示例的实际 Sheet 为 **5120×1536**，10 列×3 行；末尾空格透明。源 1536×1536，Scale `0.3333333333333333`。
- 独立 exe 首轮从冷缓存完成角色管线与播放；修正验收脚本的宽度舍入比较后重新打包，最终所有 smoke 通过。固定 Root 比较始终使用精确相等。

成品：`dist/AI Video to Sprite/AI Video to Sprite.exe`，需要保留整个同名文件夹。JSON 语言包、Qt/Python/OpenCV 和三个示例工程已包含；FFmpeg/ffprobe 继续使用本机依赖。

当前 exe SHA256：`4BD5AAE4A8F39204042E8B2A0C89E9C356626A77765061E7736704A4A7DC6501`。

## 最终数据流复核

Profile 与 Alpha Bounds 分层，动画快照不复制 Profile；首次辅助站地与后续固定变换分开；Root 跟踪在源尺寸进行，角色坐标补偿转换回源像素后整帧平移，最终统一缩放。框宽仅进入 Overlay/警告，未进入图像签名。Preview 与 Export 继续共用 FinalFrameProvider，无第二套最终图像算法。原始 Root Motion 单独保存，原地对齐不删除运动数据。

---

# v0.2 历史验收记录

验证日期：2026-09-13。环境：Windows 11 x64，Python 3.12.14；依赖见 requirements-lock.txt。

## 核心与集成测试

`.venv\Scripts\python.exe -m pytest -q`：**38 passed**，最终运行 18.69 秒。保留原有 24 项回归，加入：

- 静止 ±3px Root 抖动、连续加速 Dash、Jump 抛物线、单帧 tracking spike、脚下剑尖、循环 Root 漂移。
- 高速抛物线最高点不被误判为 spike。
- 1536→512 完整源画布、等比与透明留白、Root 比例、无透明 RGB 黑/绿污染、22 帧 10 列布局和空格透明。
- 源尺寸 Key/Alignment，FinalFrameProvider 与 PNG 导出逐像素一致；JSON Root/Ground/Motion 使用目标像素。
- 目标尺寸改变复用源处理缓存、旧 Provider 签名失效。
- 透明背景特征排除、综合置信度、强制光流失败后的相位相关、再失败后的有限预测。
- 旧工程新增字段默认值、语言切换不改工程枚举、设置持久化。

`.venv\Scripts\python.exe scripts/check_i18n.py`：**389 个 key，覆盖完整**。zh_CN / en_US 集合和格式参数一致；默认简体中文。

## 实际 Qt 桌面验收

`scripts/smoke_upgrade.py` 使用 FFmpeg 实际编码的 **22 帧、1536×1536、24 FPS** 合成 MP4，经导入、源尺寸抠像、点击 Root、Dash 策略、统一画布构建、最终动画预览、保存工程、Godot 导出。

| 检查 | 结果 |
| --- | --- |
| 最终单帧 | 22 张，全部 512×512 |
| Sprite Sheet | 5120×1536，10 列×3 行；最后 8 格透明 |
| 预览与导出 | 22 张 PNG 与 Provider 逐像素相等 |
| 源 Key / Alignment | 保持 1536×1536 |
| 播放 | 24 FPS 设置，1.25 秒内实际遍历全部 22 帧 |
| 独立窗口 | 非模态，关闭不影响主窗口 |
| 按键与 FPS | 左右/Home/End 步进正常；修改预览 FPS 不改变项目 24 FPS |
| Loop Seam | [19,20,21,0,1,2] |
| 对比与合成 | Before 源尺寸；After 512；洋葱皮/残影有效且不改 Provider |
| Overlay / 背景 / Zoom | Root、Ground、Bounds、Path；棋盘格/白底、100%/200%/Fit 验证 |
| 导出按钮 | 路由至主程序 Godot 导出 |
| 参数修改 | 旧窗口 stale，停止播放、禁止导出 |
| 语言 | 中文、英文真实控件；切换只保存 app_settings，不改工程 |
| DPI | 中文 125%、150%；英文 150%；截图及控件几何检查 |

合成片段最低跟踪置信度约 **0.81485**。该数值不代表真实 AI 视频准确率。片段末尾武器姿态与开头不同，审查正确保留循环不连续提示；视觉闭环不等同于仅 Root 曲线闭环。

证据：

- 完整首次处理：`.test-output/upgrade-zh2/`
- 中文 125%：`.test-output/upgrade-125/validation.json`
- 中文 150% 最终界面：`.test-output/final-zh150/validation.json`
- 英文 150%：`.test-output/upgrade-150/validation.json`
- 公开截图：`docs/ui-preview.png`、`docs/animation-preview.png`、`docs/motion-curves.png`

原有 `scripts/smoke_gui.py` 24 帧流程再次通过：调参、4 种预览、手动 Root 添加/删除、构建、播放、保存重开、导出。新默认 Motion 策略下 AUTO Cell 为 197×221，无裁切，最低置信度 0.94859。旧项目的关闭 Motion 兼容分支另由核心回归覆盖。

## Windows 成品

`.\build.ps1`：**exit code 0**。PyInstaller 6.22.2 生成：

`dist/AI Video to Sprite/AI Video to Sprite.exe`

实际运行：

1. `--smoke-test`：窗口启动并正常退出。
2. `--smoke-preview examples/normalized_512.aivsprite`：在独立 exe 内从冷缓存完成 Decode→Key→Root→Motion→Source Align→Normalize→Sheet，打开非模态最终预览并播放；**exit code 0**。
3. 运行日志确认：`language=zh_CN frames=22 cell=512x512 fps=24.0 pixel_match=True`。
4. 成品包含两份 JSON 语言包和 Qt 的 `qtbase_zh_CN.qm`。
5. FFmpeg/ffprobe 为本机外部依赖；Qt/Python/OpenCV 已打包。不附带字体文件。

exe SHA256：

`2EBFC9F2573432ED1DDEBBB571A93B0272BC2A6CE75BAC55482F78EF8FCFD3DD`

## 最终复核与范围

- 架构：core 不依赖 Qt；最终图像变换只有一条；导出与预览共用 Provider。
- 数据流：源坐标用于编辑和跟踪，目标坐标用于导出；循环视觉校正不删除提取的位移；英文枚举稳定。
- 工程：后台线程、缓存完成标志、取消、只读 LRU、旧工程、Unicode 路径、独立 exe 均验证。
- 限制：实际 AI 素材、语义身体分割、原生 Godot .tres、逐帧可变时长未在本次实现范围内。地面 ROI 和手动 Root 是遮挡/武器/特效歧义的调整入口。
