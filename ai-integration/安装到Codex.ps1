param([switch]$AllowSubmit,[string]$CodexDirectory)
$ErrorActionPreference='Stop'
$bundleRoot=$PSScriptRoot
$server=Join-Path $bundleRoot 'xmu-study-mcp-1.10.2.exe'
if (-not (Test-Path -LiteralPath $server)) { throw '请从完整运行包执行安装脚本，缺少 xmu-study-mcp-1.10.2.exe。' }
$codexRoot=if ($CodexDirectory) { $CodexDirectory } elseif ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$configPath=Join-Path $codexRoot 'config.toml'
$skillBase=if ($CodexDirectory) { Join-Path $codexRoot 'skills' } else { Join-Path $env:USERPROFILE '.agents\skills' }
$skillTarget=Join-Path $skillBase 'xmu-study-assistant'
$skillSource=Join-Path $bundleRoot 'skills\xmu-study-assistant'
if (-not (Test-Path -LiteralPath (Join-Path $skillSource 'SKILL.md'))) { throw '运行包缺少 Skill。' }
New-Item -ItemType Directory -Path $codexRoot,$skillTarget -Force | Out-Null
$content=if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }
$section='(?ms)^\[mcp_servers\.xmu-study\]\s*\r?\n.*?(?=^\[|\z)'
$command=$server.Replace('\','/') | ConvertTo-Json -Compress
$arguments=if ($AllowSubmit) { '["--allow-submit"]' } else { '[]' }
$newSection="[mcp_servers.xmu-study]`ncommand = $command`nargs = $arguments`nstartup_timeout_sec = 30`ntool_timeout_sec = 180`n`n"
if ($content -match $section) {
    $updated=[regex]::Replace($content,$section,[System.Text.RegularExpressions.MatchEvaluator]{param($match) $newSection})
} else {
    $updated=$content.TrimEnd()+"`n`n"+$newSection
}
# Keep any backup beside the user's config; never copy unrelated settings into a distributable folder.
if ((Test-Path -LiteralPath $configPath) -and $content -ne $updated) {
    $backup=$configPath+'.before-xmu-study-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
    Copy-Item -LiteralPath $configPath -Destination $backup
}
$temporary=$configPath+'.xmu-study.tmp'
[IO.File]::WriteAllText($temporary,$updated,[Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporary -Destination $configPath -Force
Copy-Item -LiteralPath (Join-Path $skillSource 'SKILL.md') -Destination $skillTarget -Force
foreach ($directory in @('agents','references')) {
    $destination=Join-Path $skillTarget $directory
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $skillSource $directory) -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $destination -Force }
}
Write-Output '已配置 xmu-study MCP 并安装厦大学习助手 Skill。重启客户端或重新加载 MCP 后使用。'
Write-Output ('正式交付：'+$(if ($AllowSubmit) { '已启用，仍需用户明确要求' } else { '未启用；支持平台草稿' }))
