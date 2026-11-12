# 厦大 AI 学习助手 1.10.0

适用于 Windows 桌面助手 1.10.0 的独立 MCP＋Skill 扩展。主程序仍使用原版本；本扩展按需启动，没有新增桌面常驻轮询、Qt 窗口或内置模型。

## 本机使用

AI 客户端启动 `xmu-study-mcp-1.10.0.exe`，通过 STDIO 调用 20 个工具。查校园数据前先在桌面助手完成登录，保留有效登录态。进程会等待客户端输入。

诊断 Windows 监控时，使用 `get_monitor_logs` 读取最近的启停、轮询、会话过期和处理结果。默认 100 条，最多 300 条。它与点校徽导出使用同一份固定诊断日志，无需校园登录。

运行包的 `安装到Codex.ps1` 可注册本地 MCP，并把 `xmu-study-assistant` Skill 安装到用户的 `.agents/skills` 目录；已有 Codex 配置先在原位置备份，只修改本服务条目。关闭并重新打开客户端，或重新加载 MCP；当前已经启动的会话不保证立即获得新工具。首次可输入：

> 用厦大学习助手列出我的课程和未过期待办。

> 根据《计算机网络与通信》课件讲解 IPv6，注明课件页码，并给我几道练习。

> 查这门课期末、实验和平时成绩各占多少，给出依据。

> 读取 Redis 实验作业的要求和附件，参考相关课件生成报告和代码，先保存本地成果。

成绩构成来自实际课程介绍/大纲；个人分布需要提供成绩文件，班级分布需要真实的班级数据。当前扩展不连接教务成绩接口，也不自动获取全班成绩。默认 `score,credits` 两列的 CSV 或 JSON 数组可做均分、学分加权均分和分段统计，支持自定义中文列名，不推算 GPA。

## 其他 AI 客户端

用包内 `MCP通用配置.json` 的 `mcpServers.xmu-study` 条目配置支持本地 STDIO 的客户端。不同客户端的配置文件位置和外层结构可能不同；命令与参数可以复用。若移动运行包，需要更新绝对路径。

支持 Agent Skills 的客户端可安装 `skills/xmu-study-assistant`；安装目录遵循各客户端规则。没有 Skill 支持的客户端仍能发现工具，并使用服务内置 `study_assistant` Prompt 或读取 `xmu://guide`。本地目录不会自动暴露给纯网页 AI，网页端需另有本地桥接或远程服务；当前版本只提供本地 STDIO。

官方依据：[MCP](https://modelcontextprotocol.io/docs/learn/architecture)、[Agent Skills](https://agentskills.io/specification)、[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)、[Codex Skills](https://learn.chatgpt.com/docs/build-skills)。

## 资料与成果

首次 `get_status` 会返回当前账号的工作目录。默认是桌面配置目录下 `mcp-workspaces/账号摘要`，可以用启动参数 `--workspace D:/AI学习资料` 更改根目录，仍自动按账号隔离。如果桌面助手使用 `XMU_ROLLCALL_CONFIG_DIR` 自定义配置目录，MCP 启动环境需使用相同值。

`list_course_materials` 查标题与章节；选取文件下载后，`read_document` 按页/幻灯片读取，`search_documents` 在已索引内容中找关键词。下载默认缓存，课件更新后用 `refresh=true` 重新获取。搜索不会暗中扫描全盘或自动下载全部课程。

内置读取 PDF 文字、DOCX、PPTX、XLSX、常见文本/代码和 ZIP 目录及选定成员。PDF 扫描页、旧版 DOC/PPT、音视频需要客户端现有视觉/OCR或专用工具；图片可用 `read_image`。不会执行附件中的宏或代码。

`create_artifact` 新建文本成果，保存在账号工作目录的 `outputs` 内。DOCX/PDF等可由 AI 客户端文件工具生成，再调用 `register_artifact` 登记相对此账号目录的路径。文件命名冲突不覆盖原成果；课程、作业ID可用于防止错传。

自动下载单文件256 MiB；文本解析单文件64 MiB、文本最多200万字符，PDF/PPTX最多500页/张；一次读取最多24000字符。达到上限会注明。全文查询一次最多检索100个已索引文件，请用课程筛选缩小范围。大文件仍可在助手中下载，再由专用工具处理。

## 平台写入

用户明确要求后，先 `prepare_submission` 生成可核对的本地计划，默认保留原平台附件；随后 `commit_submission(mode="draft")` 保存平台草稿。正文可空，避免附件作业产生空白正文预览。

正式交付需在 MCP 启动参数增加 `--allow-submit`，并由用户明确要求交付，才调用 `mode="submit"`。例如在通用配置的 `args` 中加入该参数，或重新运行安装脚本并带 `-AllowSubmit`。默认安装支持平台草稿，未启用正式交付。

计划有效期30分钟，成果文件与平台记录改变会阻止写入。上传和提交不会自动重试；结果不明时先读回平台记录，不要反复新建计划绕过核实。同一已确认计划只返回旧回执。分组作业仍在原平台处理。

账号登录态在服务内部复用，不传密码、Cookie或任意系统文件。云端 AI 会收到你选择读取的课程和作业内容；本地 MCP 本身不代表模型在本地运行。

## 开发与验证

源码安装可用 `pip install -e ./xmu-rollcall-cli[mcp]`，或安装 `ai-integration/requirements.txt` 后设置源码目录。启动：

```powershell
python -m xmu_rollcall.mcp_bridge
```

独立程序构建：`python -m PyInstaller --noconfirm scripts/xmu-mcp.spec`。使用官方 Python SDK 1.30.0；PDF解析器6.21.4。扩展是可选依赖，原桌面打包排除了 MCP 模块。

验证包含模拟账号/平台接口的单元回归、官方 MCP 客户端的真实 STDIO 子进程往返，以及最终程序的离线端到端检查。没有使用真实账号上传或提交测试作业；真实课程文件、平台写入回执仍需正常使用时验收。

## 0.2.0 本地补充资料

使用桌面助手添加教材或笔记后，list_local_materials 按课程列出资料，open_local_material 接入原文件，不再复制。可用 read_document/read_image 按需读取。大于64 MiB的有效PDF可按指定页读取（最大1 GiB），不全文索引；移除课程关联后旧file_id失效。作业正文会读取平台data.description字段；download_assignment_attachment同时支持教师附件和本人已提交附件，仍核对课程和作业归属。
