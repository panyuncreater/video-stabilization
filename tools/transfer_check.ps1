<#
.SYNOPSIS
  一键迁移核查：环境自检 -> 测试 -> 合成档端到端（-> 实拍档），并把报告落盘。

.DESCRIPTION
  跨机器/跨 agent 接手本工程后的推荐入口。所有输出同时写入
  .workbuddy\baseline-local\reports\<时间戳>\ 下，便于留证与比对。

  退出码：0 = 全部通过；1 = 环境或测试阻断；2 = 仅缺实拍素材（合成档通过）。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\transfer_check.ps1 -Full
  powershell -ExecutionPolicy Bypass -File tools\transfer_check.ps1 -RunTest1
#>
param(
    [switch]$RunTest1,     # 追加实拍档 end-to-end（需 data\test1.mp4，单遍 pass2 约 18 分钟）
    [switch]$Cov,          # pytest 带覆盖率（隐含 --cov 参数）
    [switch]$Full,         # = -Cov -RunTest1
    [switch]$SkipTests     # 跳过 pytest（只做环境/数据/红线 + end-to-end）
)

$ErrorActionPreference = 'Continue'
if ($Full) { $Cov = $true; $RunTest1 = $true }

$root = Split-Path -Parent $PSScriptRoot          # 项目根目录（tools/ 的上一级）
Set-Location $root

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$reportDir = Join-Path $root ".workbuddy\baseline-local\reports\$stamp"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$logPath = Join-Path $reportDir 'transfer_check.log'
$log = [System.Collections.Generic.List[string]]::new()

# 中文输出不乱码：Python 侧指定 UTF-8，PowerShell 侧统一 UTF-8 写文件；
# 并 chcp 65001 把控制台代码页切到 UTF-8（Windows PowerShell 5.1 默认 936，否则显示乱码）
try { [void](chcp 65001) } catch { }
$env:PYTHONIOENCODING = 'utf-8'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)

$script:ExitCode = 0

function Write-Both {
    param([string]$Text)
    Write-Host $Text
    $log.Add($Text)
}

function Save-Log {
    $log | Out-File -Encoding UTF8 -FilePath $logPath
}

function ConvertTo-ArgString {
    <# 把参数数组拼成命令行字符串。
       Windows PowerShell 5.1 的 ProcessStartInfo 没有 ArgumentList（.NET Framework），
       只能用 Arguments 字符串，故此处手工加引号（含空格的路径必须引，内部引号翻倍）。 #>
    param([string[]]$Items)
    $parts = @()
    foreach ($it in $Items) {
        $s = [string]$it
        if ($s -match '[\s"]') { $parts += '"' + ($s -replace '"', '""') + '"' }
        else { $parts += $s }
    }
    return ($parts -join ' ')
}

function Invoke-Py {
    <# 执行 python 脚本：回显 + 记录 + 返回确定的退出码。

    实现要点（踩坑记录，勿改回）：
    - Windows PowerShell 5.1 的 ProcessStartInfo 没有 ArgumentList，用 Arguments 字符串。
    - 必须把子进程 stdout/stderr 重定向到【文件】再读回。若设 RedirectStandardOutput=$true
      却用 ReadToEnd() 读，父子进程会在管道上死锁（Windows PowerShell 5.1 实测挂起）。
    - 不用 $LASTEXITCODE 判成败：解释器是 PATH 上的命令名（如 'python'）时它不可靠。
    #>
    param([string[]]$PyArgs, [string]$Label, [int]$TimeoutSec = 900)
    Write-Both ''
    Write-Both ("#" * 78)
    Write-Both "# $Label"
    Write-Both ("#" * 78)
    Save-Log

    $safe = $Label -replace '[\\/:*?"<>|（）()\s]', '_'
    $tmpOut = Join-Path $reportDir ("_{0}_out.txt" -f $safe)
    $tmpErr = Join-Path $reportDir ("_{0}_err.txt" -f $safe)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:Python
    $psi.WorkingDirectory = $root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $psi.Arguments = ConvertTo-ArgString $PyArgs

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()

    # 关键：用 CopyTo 把管道内容落到文件（同步、无死锁），再读回
    $fsOut = [System.IO.File]::Create($tmpOut)
    $fsErr = [System.IO.File]::Create($tmpErr)
    try {
        $proc.StandardOutput.BaseStream.CopyTo($fsOut)
        $proc.StandardError.BaseStream.CopyTo($fsErr)
    } finally {
        $fsOut.Dispose(); $fsErr.Dispose()
    }

    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch { }
        Write-Both "! 超时 $TimeoutSec s，已强制终止（$Label）。"
        Write-Both "[$Label] 退出码 = 124"
        Save-Log
        $proc.Dispose()
        return 124
    }
    $code = $proc.ExitCode
    $proc.Dispose()

    foreach ($f in @($tmpOut, $tmpErr)) {
        if (Test-Path $f) {
            foreach ($line in (Get-Content -Encoding UTF8 $f -ErrorAction SilentlyContinue)) {
                if ($line -ne '') { Write-Both $line }
            }
            Remove-Item $f -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Both "[$Label] 退出码 = $code"
    Save-Log
    return $code
}

Write-Both '=================================================================='
Write-Both " video-stabilization 迁移核查  $stamp"
Write-Both " 项目根目录: $root"
Write-Both '=================================================================='

# ---------- 选 python 解释器 ----------
# 注意：不能只看文件是否存在——历史上出现过残缺/损坏的 venv（python.exe 存在但不可执行），
# 因此这里实际执行一次自检，只有真正能跑起来的解释器才会被采纳。
$script:Python = $null
foreach ($cand in @((Join-Path $root '.venv\Scripts\python.exe'), 'python')) {
    if ($cand -ne 'python' -and -not (Test-Path $cand)) { continue }
    try {
        $probe = & $cand -c "import sys;sys.stdout.write(sys.version.split()[0])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe -and $probe -match '^\d+\.\d+') {
            $script:Python = $cand
            break
        }
    } catch { }
}
if (-not $script:Python) {
    Write-Both 'x 找不到可用的 python 解释器（.venv\Scripts\python.exe 损坏，或 PATH 中的 python 不可用）。'
    Write-Both '  请按 HANDOVER.md 第二节重建虚拟环境后重试。'
    Save-Log
    exit 1
}
$pyver = & $script:Python -c "import sys;print(sys.version.split()[0])" 2>$null
Write-Both "使用解释器 : $script:Python (Python $pyver)"

# ---------- 1) 环境 + 数据 + 红线 (+ 测试) ----------
$envRows = @('tools\verify_env.py', '--json', (Join-Path $reportDir 'verify_env.json'))
if (-not $SkipTests) { $envRows += '--run-tests' }
if ($Cov) { $envRows += '--cov' }
$codeEnv = Invoke-Py -PyArgs $envRows -Label '环境 / 数据 / 红线 / 测试' -TimeoutSec 300

# 守卫：即使退出码被误读，也以 JSON 为准再判一次依赖是否齐备
$envJson = Join-Path $reportDir 'verify_env.json'
if (Test-Path $envJson) {
    try {
        $envReport = Get-Content -Raw -Encoding UTF8 $envJson | ConvertFrom-Json
        $depMissing = @($envReport.rows | Where-Object {
            $_.name -like '依赖*' -and -not $_.ok
        })
        if ($depMissing.Count -gt 0) {
            Write-Both ''
            Write-Both 'x 以下依赖不可用或版本不符，无法执行端到端：'
            foreach ($d in $depMissing) { Write-Both ("  - {0} : {1}" -f $d.name, $d.detail) }
            Write-Both '  请按 HANDOVER.md 第二节安装锁定依赖后重试。'
            Save-Log
            exit 1
        }
    } catch {
        Write-Both "! verify_env.json 解析失败（$($_.Exception.Message)），退化为按退出码判定。"
    }
}

if ($codeEnv -eq 1) {
    Write-Both ''
    Write-Both 'x 环境或测试未通过：先按 README 第二节安装依赖 / 排查测试失败，不要继续跑 end-to-end。'
    Save-Log
    exit 1
}
if ($codeEnv -eq 2) { Write-Both '! 依赖就绪但缺 data\test1.mp4：本次只做合成档验收。' }

# ---------- 2) 合成素材 ----------
$synthMp4 = Join-Path $root 'data\synthetic\synthetic_shaky.mp4'
if (-not (Test-Path $synthMp4)) {
    $code = Invoke-Py -PyArgs @('tools\make_synthetic.py') -Label '生成合成素材（种子 42）'
    if ($code -ne 0) { Save-Log; exit 1 }
}

# ---------- 3) 合成档 end-to-end ----------
$synthOut = Join-Path $root 'output\synthetic'
New-Item -ItemType Directory -Force -Path $synthOut | Out-Null
$code = Invoke-Py -PyArgs @(
    'main.py',
    '--input', 'data\synthetic\synthetic_shaky.mp4',
    '--output', (Join-Path $synthOut 'stabilized.mp4'),
    '--smooth', 'gauss', '--window', '31', '--vis'
) -Label '合成档 end-to-end'
if ($code -ne 0) { Write-Both 'x 合成档运行失败。'; Save-Log; exit 1 }

# ---------- 4) 实拍档（可选） ----------
$test1 = Join-Path $root 'data\test1.mp4'
if ($RunTest1) {
    if (-not (Test-Path $test1)) {
        Write-Both '! 请求了 -RunTest1 但 data\test1.mp4 不存在：跳过实拍档。'
        if ($script:ExitCode -eq 0) { $script:ExitCode = 2 }
    } else {
        $t1Out = Join-Path $root 'output\test1'
        New-Item -ItemType Directory -Force -Path $t1Out | Out-Null
        $code = Invoke-Py -PyArgs @(
            'main.py',
            '--input', 'data\test1.mp4',
            '--output', (Join-Path $t1Out 'stabilized.mp4'),
            '--smooth', 'gauss', '--window', '31', '--vis'
        ) -Label '实拍档 end-to-end（耗时较长）'
        if ($code -ne 0) { $script:ExitCode = 1 }
    }
} elseif (-not (Test-Path $test1)) {
    if ($script:ExitCode -eq 0) { $script:ExitCode = 2 }
}

# ---------- 5) 汇总指标 ----------
Write-Both ''
Write-Both '================= 本次运行指标摘要 ================='
$rows = @(
    @{名 = '合成档'; 路径 = (Join-Path $synthOut 'metrics.json') },
    @{名 = '实拍档'; 路径 = (Join-Path $root 'output\test1\metrics.json') }
)
foreach ($r in $rows) {
    if (-not (Test-Path $r.路径)) { continue }
    try {
        $m = Get-Content -Raw -Encoding UTF8 $r.路径 | ConvertFrom-Json
        $itfGain = [math]::Round($m.metrics.itf_stabilized_db - $m.metrics.itf_original_db, 3)
        Write-Both ("[{0}] ITF {1} -> {2} dB (增益 {3}) | S {4} | 裁剪率 {5} | D {6} | 切换 {7} 处 | pass1 {8}s / pass2 {9}s" -f `
            $r.名, [math]::Round($m.metrics.itf_original_db, 3), [math]::Round($m.metrics.itf_stabilized_db, 3),
            $itfGain, [math]::Round($m.metrics.stability.S, 4), [math]::Round($m.metrics.cropping_ratio, 4),
            [math]::Round($m.metrics.distortion, 5), $m.shots.cuts.Count,
            $m.runtime_sec.pass1, $m.runtime_sec.pass2)
    } catch {
        Write-Both ("[{0}] metrics.json 解析失败: {1}" -f $r.名, $_.Exception.Message)
    }
}
Write-Both '对照基准见 docs\RESULTS.md 与 PROJECT_STATE.md（v2.5 数值）。'
Write-Both '===================================================='

Write-Both ''
Write-Both "报告目录：$reportDir"
if ($script:ExitCode -eq 0) { Write-Both '结论：PASS —— 该机器上工程可正常验收。' }
elseif ($script:ExitCode -eq 2) { Write-Both '结论：合成档 PASS；实拍档因缺 data\test1.mp4 未执行。' }
else { Write-Both '结论：FAIL —— 见上方日志。' }
Save-Log
exit $script:ExitCode
