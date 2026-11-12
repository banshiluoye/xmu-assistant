<div align="center">
<img src="assets/xmu-assistant-mark.png" alt="虾大助手图标" width="80">

# 虾大助手

面向厦门大学学生的个人学习工具。查看课程和待办，管理课件与作业，并在电脑上连接 AI 学习助手。

[下载 1.10.0](https://github.com/banshiluoye/xmu-assistant/releases/tag/v1.10.0)
</div>

## 安装

| 平台 | 发布文件 | 使用方式 |
| --- | --- | --- |
| Windows | `XMU-Assistant-1.10.0.exe` | 从托盘退出旧版，再运行新文件 |
| Android | `XMU-Assistant-Android-1.10.0.apk` | Android 8.0 及以上。兼容同签名旧版覆盖安装 |
| AI 扩展（Windows） | `XMU-Study-MCP-1.10.0-Windows.zip` | 解压后运行包内的 Codex 安装脚本，或在支持本地 STDIO 的客户端配置可执行文件 |
| 学习 Skill | `xmu-study-assistant-skill-1.10.0.zip` | 解压后把 `xmu-study-assistant` 放入支持 Agent Skills 的客户端技能目录 |

发布文件的 SHA-256 见 Release 中的 `SHA256SUMS.txt`。Windows 可用 PowerShell 的 `Get-FileHash` 核对。安卓沿用历史版本的调试签名用于覆盖更新，请以本仓库的 Release 文件与校验值核实来源。

macOS 和 iOS 暂缓，本次发布包含 Windows 和 Android。Apple 平台构建只在之后的大版本评估。

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

[AI 扩展说明](ai-integration/README.md) · [学习 Skill](ai-integration/skills/xmu-study-assistant/SKILL.md)

## 源码构建

- Windows：在仓库根目录用 Python 建立虚拟环境，安装 `requirements-ci.txt` 和 PyInstaller。执行 `python -m PyInstaller --noconfirm xmu-assistant.spec`。
- MCP：安装 `ai-integration/requirements.txt`。从源码运行时，把 `xmu-rollcall-cli` 加入 Python 搜索路径，再执行 `python -m xmu_rollcall.mcp_bridge`。可用 `python -m PyInstaller --noconfirm scripts/xmu-mcp.spec` 构建独立运行包。
- Android：需要 JDK 17 和 Android SDK 35。进入 `android`，用 `gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`（Windows）或 `bash gradlew` 执行相同任务。自定义签名通过本机环境变量 `XMU_ANDROID_KEYSTORE`、`XMU_ANDROID_STORE_PASSWORD`、`XMU_ANDROID_KEY_ALIAS`、`XMU_ANDROID_KEY_PASSWORD` 提供。自行签名的 APK 与已安装版本签名不同时，Android 会拒绝覆盖。

## 隐私与来源

公开源码和发布包只包含应用、构建输入与合成测试数据。账号、会话、课程数据、个人资料、运行日志与签名密钥保存在使用者或构建者本机。反馈问题时请先检查并遮盖日志中的个人信息。

项目基于 [democard/xmu_assistant 1.8.4](https://github.com/democard/xmu_assistant/tree/v1.8.4) 修改，沿用 [Apache-2.0 许可](LICENSE)。本仓库包含 Windows 和 Android 功能增强、MCP 与学习 Skill。图标来源见 [校徽说明](assets/XMU-EMBLEM-SOURCE.md) 和各素材目录的署名文件。此项目是独立维护的个人工具。
