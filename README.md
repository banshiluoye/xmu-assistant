<div align="center">
<img src="assets/xmu-assistant-mark.png" alt="厦大助手图标" width="80">

# 厦大助手

面向厦门大学学生的个人学习工具。查看课程和待办，管理课件与作业，并在电脑上连接 AI 学习助手。

这是基于 [democard/xmu_assistant 1.8.4](https://github.com/democard/xmu_assistant/tree/v1.8.4) 的个人魔改版。原作者提供了 Windows、Android、签到监控和教务查询的基础。我按自己的日常学习流程，重新做了待办、作业、课件、手机课表和 AI 接入。感谢上游作者。

[下载 1.10.1](https://github.com/banshiluoye/xmu-assistant/releases/tag/v1.10.1)
</div>

## 相比上游改了什么

| 范围 | 个人版的改动 |
| --- | --- |
| 学习待办 | 新增独立待办页，按课程、类型、截止时间和完成状态筛选，默认隐藏已过期项。临期时间可调，测验可直接在浏览器打开。 |
| 课件 | 按课程、章节和课件活动组织文件。支持添加外部教材和笔记，大文件可引用原位置。Windows 目录展开按需更新，大目录无需每次重新建树。 |
| 作业 | 从待办查看要求与教师附件，支持富文本、附件上传和本地草稿。Windows 支持拖入，安卓支持拍照。仅交附件时无需生成空白正文。 |
| Android 课表 | 七天周表显示教室，支持单次调课、临时加课和节假日调课。平板宽屏可同时查看周表和课程详情。 |
| 监控和诊断 | Android 增加锁屏续登、厂商后台设置指引和断网重试。双端连点校徽五次可导出监控日志，Windows 日志也能通过 MCP 读取。 |
| 桌面 AI | 新增 MCP 与独立 Skill，可查作业、课件、本地资料和待办，可分析用户提供的成绩表。 |
| 外观 | 外观大改。双端改为厦大校徽、黑白界面与蓝色强调色，支持浅色和深色模式。 |

## 界面预览

截图中的课程、附件和教师均为演示数据。

**Windows · 课程课件**

按章节浏览资料，也可以将自己的教材和笔记加到课程里。

<img src="assets/screenshots/windows-courseware.png" width="860" alt="Windows 课程课件页面，展示章节目录、文件类型图标和本地补充资料">

**Android 平板 · 周课表**

左侧切换模块，点课程卡片后可在右侧查看地点、节次和教师。

<img src="assets/screenshots/android-tablet-timetable.png" width="860" alt="Android 平板横屏，左侧为导航和七天周课表，右侧为课程详情">

## 安装

| 平台 | 发布文件 | 使用方式 |
| --- | --- | --- |
| Windows | [1.10.1 EXE](https://github.com/banshiluoye/xmu-assistant/releases/download/v1.10.1/XMU-Assistant-1.10.1.exe) | 从托盘退出旧版，再运行新文件 |
| Android | [1.10.1 APK](https://github.com/banshiluoye/xmu-assistant/releases/download/v1.10.1/XMU-Assistant-Android-1.10.1.apk) | Android 8.0 及以上。兼容同签名旧版覆盖安装 |
| AI 扩展（Windows） | [MCP 1.10.0](https://github.com/banshiluoye/xmu-assistant/releases/download/v1.10.0/XMU-Study-MCP-1.10.0-Windows.zip) | 解压后运行包内的 Codex 安装脚本，或在支持本地 STDIO 的客户端配置可执行文件 |
| 学习 Skill | [Skill 1.10.0](https://github.com/banshiluoye/xmu-assistant/releases/download/v1.10.0/xmu-study-assistant-skill-1.10.0.zip) | 解压后把 `xmu-study-assistant` 放入支持 Agent Skills 的客户端技能目录 |

发布文件的 SHA-256 见 Release 中的 `SHA256SUMS.txt`。Windows 可用 PowerShell 的 `Get-FileHash` 核对。安卓沿用历史版本的调试签名用于覆盖更新，请以本仓库的 Release 文件与校验值核实来源。

macOS 和 iOS 暂缓，本次发布包含 Windows 和 Android。

## 主要功能

- Windows：学习待办筛选、按章节浏览与下载课件、导入本地资料、上传作业和在浏览器打开测验。
- Android：七天周课表、临时调课、成绩和考试安排、学习待办、课件以及支持拍照附件的作业页。
- 两端：首次用自己的校园账号登录。后台监控依赖网络、有效会话和系统许可。Android 在首页打开「锁屏监控设置」，按手机厂商提示配置。快速连点校徽五次可以导出本机诊断日志。
- 雷达签到使用现场地点。没有课程地点时，请在畅课处理签到。
- MCP 与 Skill：查找作业要求和附件、按需读取课件与本地补充资料、分析用户提供的成绩文件，以及读取 Windows 监控诊断。教学平台的正式提交默认关闭。

## 安装 MCP 和 Skill

1. 在 Windows 助手用自己的账号登录。读取本机监控诊断无需校园会话。
2. 解压 AI 扩展 ZIP。使用 Codex 时运行 `安装到Codex.ps1`，随后重载 MCP 或重启客户端。
3. 其他支持本地 STDIO 的客户端可将 `xmu-study-mcp-1.10.0.exe` 的绝对路径填为命令，参数留空。Skill 可单独安装。
4. 可以试着问「按课程列出未过期的待办」或「读取最近的 Windows 监控日志」。在 AI 客户端中查看资料会把选定内容传给所用模型服务，按实际需要选择资料。
5. 可以把该网址复制到harness里让ai自己下载。

[AI 扩展说明](ai-integration/README.md) · [学习 Skill](ai-integration/skills/xmu-study-assistant/SKILL.md)

## 源码构建

- Windows：在仓库根目录用 Python 建立虚拟环境，安装 `requirements-ci.txt` 和 PyInstaller。执行 `python -m PyInstaller --noconfirm xmu-assistant.spec`。
- MCP：安装 `ai-integration/requirements.txt`。从源码运行时，把 `xmu-rollcall-cli` 加入 Python 搜索路径，再执行 `python -m xmu_rollcall.mcp_bridge`。可用 `python -m PyInstaller --noconfirm scripts/xmu-mcp.spec` 构建独立运行包。
- Android：需要 JDK 17 和 Android SDK 35。进入 `android`，用 `gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`（Windows）或 `bash gradlew` 执行相同任务。自定义签名通过本机环境变量 `XMU_ANDROID_KEYSTORE`、`XMU_ANDROID_STORE_PASSWORD`、`XMU_ANDROID_KEY_ALIAS`、`XMU_ANDROID_KEY_PASSWORD` 提供。自行签名的 APK 与已安装版本签名不同时，Android 会拒绝覆盖。

## 隐私与来源

公开源码和发布包只包含应用、构建输入与合成测试数据。账号、会话、课程数据、个人资料、运行日志与签名密钥保存在使用者或构建者本机。反馈问题时请先检查并遮盖日志中的个人信息。

代码沿用 [Apache-2.0 许可](LICENSE)。图标来源见 [校徽说明](assets/XMU-EMBLEM-SOURCE.md) 和各素材目录的署名文件。此项目由个人独立维护。
