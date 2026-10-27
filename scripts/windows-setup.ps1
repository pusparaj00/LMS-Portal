# TR-O-05, TR-O-06: run once, in an administrator PowerShell, on the Windows PC that hosts the system.
#   powershell -ExecutionPolicy Bypass -File scripts\windows-setup.ps1 -OffsiteTarget /d/lms-backups
# The PC must not sleep: Modern Standby freezes Docker silently. Containers restart by themselves
# (restart: unless-stopped) once Docker Desktop starts, so set Docker Desktop to start at sign-in.
# OffsiteTarget is a Git Bash path on another disk (/d/...): a Windows path with a colon would be read as host:folder.
param([string]$OffsiteTarget = "", [string]$GitBash = "C:\Program Files\Git\bin\bash.exe")

$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $GitBash)) { throw "Git Bash not found at $GitBash" }

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

$env = if ($OffsiteTarget) { "OFFSITE_TARGET='$OffsiteTarget' " } else { "" }
$backup = "cd '$($repo -replace '\','/')' && scripts/backup.sh"
$offsite = "cd '$($repo -replace '\','/')' && ${env}scripts/offsite-copy.sh"

function Register($name, $time, $command) {
  $action = New-ScheduledTaskAction -Execute $GitBash -Argument "-lc `"$command`""
  $trigger = New-ScheduledTaskTrigger -Daily -At $time
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  "registered $name at $time"
}

Register "LMS-Backup" "02:00" $backup
if ($OffsiteTarget) { Register "LMS-Offsite-Copy" "02:30" $offsite } else { "no -OffsiteTarget: the off-disk copy is not scheduled" }
