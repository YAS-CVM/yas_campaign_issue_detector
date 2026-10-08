# Installe une tâche planifiée Windows (sans droits administrateur) qui lance `cvm-monitor run`
# toutes les heures de 9 h à 18 h, du lundi au samedi.
#
# Usage (PowerShell, depuis la racine du projet) :
#   powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Remove

param(
    [string]$Start = "09:00",
    [switch]$Remove
)

$TaskName = "Yas CVM Monitor"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root ".venv\Scripts\cvm-monitor.exe"
$Log = Join-Path $Root "data\task.log"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tâche « $TaskName » supprimée."
    exit 0
}

if (-not (Test-Path $Exe)) {
    Write-Error "Introuvable : $Exe. Installer d'abord le projet (voir README)."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$Exe`" run >> `"$Log`" 2>&1`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday -At $Start
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $Start `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 9)).Repetition
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Surveillance des campagnes CVM Yas (dossier inbox)" -Force | Out-Null
Write-Host "Tâche « $TaskName » installée : toutes les heures à partir de $Start (lun-sam)."
Write-Host "Journal : $Log"
