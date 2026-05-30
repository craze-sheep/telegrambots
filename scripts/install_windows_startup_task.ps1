$ErrorActionPreference = "Stop"

$TaskName = "Telegram AI Team Bot2Bot"
$LinuxCommand = "cd /home/lzy/project/telegrambots && mkdir -p logs && nohup ./run_team.sh >> logs/bot2bot.log 2>&1 &"

$Action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-- bash -lc `"$LinuxCommand`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Start Telegram AI Team Bot-to-Bot service in WSL" -Force | Out-Null

Write-Host "Installed Windows startup task: $TaskName"
Write-Host "Start now: wsl.exe -- bash -lc `"$LinuxCommand`""
