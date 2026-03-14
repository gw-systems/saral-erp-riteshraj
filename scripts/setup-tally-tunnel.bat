@echo off
REM Keep window open even if script crashes unexpectedly.
REM First run: SETUP_RUNNING is not defined, so we re-launch inside "cmd /k".
REM "cmd /k" keeps the window open after the child process exits.
REM Second run: SETUP_RUNNING=1 is inherited, so we skip into main body.
if not defined SETUP_RUNNING (
    SET "SETUP_RUNNING=1"
    cmd /k call "%~f0" %*
    exit /b
)
REM ============================================================
REM  Saral ERP - Tally Tunnel Setup  (v3.3 -- Window stays open)
REM
REM  Installs ngrok as a native Windows service that silently
REM  relays Tally XML API traffic from Saral ERP (GCP Cloud Run)
REM  through this PC to the Tally cloud server.
REM
REM  Requirements:
REM    - Windows 10/11 or Server 2016+
REM    - Run as Administrator
REM    - Internet access (outbound HTTPS only, no inbound rules)
REM    - This PC must be able to reach the Tally server
REM
REM  What this script does:
REM    1. Pre-flight checks (admin, internet, Tally reachability)
REM    2. Downloads ngrok (official binary)
REM    3. Writes ngrok v3 config (endpoints syntax)
REM    4. Installs ngrok as a native Windows service (auto-start)
REM    5. Configures Windows service recovery (auto-restart on crash)
REM    6. Tests tunnel end-to-end
REM
REM  Idempotent: safe to re-run. Stops existing service first.
REM
REM  Logs: C:\ngrok\logs\setup.log (this script)
REM        C:\ngrok\logs\ngrok.log (runtime, from ngrok itself)
REM ============================================================
SETLOCAL EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  CONFIGURATION -- edit only this section
REM ============================================================
SET "NGROK_AUTHTOKEN=3Ar3WqGmU2HljdgVzefTurdJPkV_3KSpcxBsAyB2MfpqTWK7"
SET "NGROK_DOMAIN=pellucidly-unwearied-vertie.ngrok-free.dev"
SET "TALLY_HOST=103.251.94.79"
SET "TALLY_PORT=2245"
SET "INSTALL_DIR=C:\ngrok"
SET "LOG_DIR=%INSTALL_DIR%\logs"
SET "LOG_FILE=%LOG_DIR%\setup.log"
SET "NGROK_EXE=%INSTALL_DIR%\ngrok.exe"
SET "NGROK_CONFIG=%INSTALL_DIR%\ngrok.yml"
SET "SERVICE_NAME=TallyTunnel"
SET "SERVICE_DISPLAY=Saral ERP - Tally Tunnel"
SET "NGROK_ZIP_URL_64=https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
SET "NGROK_ZIP_URL_32=https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-386.zip"

echo.
echo ============================================================
echo   Saral ERP - Tally Tunnel Setup  v3.3
echo ============================================================
echo.

REM ============================================================
REM  STEP 0: Pre-requisites
REM ============================================================

REM --- Check admin privileges (fltmc is more reliable than net session) ---
fltmc >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] This script must be run as Administrator.
    echo        Right-click the file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)
echo [OK] Running as Administrator

REM --- Check Windows version (need PowerShell 5+) and architecture ---
powershell -NoProfile -Command "if ($PSVersionTable.PSVersion.Major -lt 5) { exit 1 } else { exit 0 }" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [FAIL] PowerShell 5.0 or higher required.
    echo        This script requires Windows 10/Server 2016 or newer.
    pause
    exit /b 1
)
echo [OK] PowerShell version OK

REM --- Detect architecture and select correct ngrok binary ---
SET "NGROK_ARCH=64"
SET "NGROK_ZIP_URL=%NGROK_ZIP_URL_64%"
if defined PROCESSOR_ARCHITEW6432 (
    REM 32-bit cmd on 64-bit OS -- OS is 64-bit, use amd64
    SET "NGROK_ARCH=64"
    SET "NGROK_ZIP_URL=%NGROK_ZIP_URL_64%"
) else (
    if /i "%PROCESSOR_ARCHITECTURE%" equ "AMD64" (
        SET "NGROK_ARCH=64"
        SET "NGROK_ZIP_URL=%NGROK_ZIP_URL_64%"
    ) else (
        SET "NGROK_ARCH=32"
        SET "NGROK_ZIP_URL=%NGROK_ZIP_URL_32%"
    )
)
echo [OK] Windows !NGROK_ARCH!-bit detected

REM --- Create directories ---
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM --- Init log ---
echo. >> "%LOG_FILE%"
echo ================================================================ >> "%LOG_FILE%"
call :log "========== SETUP STARTED =========="
call :log "Script version: v3.3"
call :log "Computer: %COMPUTERNAME%"
call :log "User: %USERNAME%"
call :log "Install dir: %INSTALL_DIR%"
call :log "Architecture: !NGROK_ARCH!-bit"

REM ============================================================
REM  STEP 1/6: Pre-flight connectivity checks
REM ============================================================
echo.
echo [1/6] Pre-flight connectivity checks...

REM --- Check 1a: Internet access via ngrok.com ---
call :log "Pre-flight: checking internet..."
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $r = Invoke-WebRequest -Uri 'https://ngrok.com/docs' -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop; if ($r.StatusCode -eq 200) { Write-Output 'OK' } else { Write-Output 'FAIL' } } catch { Write-Output 'FAIL' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "INET_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!INET_CHECK!" neq "OK" (
    echo   [FAIL] Cannot reach ngrok.com -- check internet connection.
    call :log "Pre-flight: INTERNET FAILED"
    goto :fail
)
echo   Internet access ........... OK
call :log "Pre-flight: internet OK"

REM --- Check 1b: Tally server reachable from this PC ---
call :log "Pre-flight: checking Tally at %TALLY_HOST%:%TALLY_PORT%..."
powershell -NoProfile -Command "try { $tcp = New-Object System.Net.Sockets.TcpClient; $async = $tcp.BeginConnect('%TALLY_HOST%', %TALLY_PORT%, $null, $null); $wait = $async.AsyncWaitHandle.WaitOne(10000, $false); if ($wait -and $tcp.Connected) { $tcp.Close(); Write-Output 'OK' } else { $tcp.Close(); Write-Output 'TIMEOUT' } } catch { Write-Output 'FAIL' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "TALLY_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!TALLY_CHECK!" equ "OK" (
    echo   Tally %TALLY_HOST%:%TALLY_PORT% .. OK
    call :log "Pre-flight: Tally reachable"
) else if /i "!TALLY_CHECK!" equ "TIMEOUT" (
    echo   [FAIL] Tally at %TALLY_HOST%:%TALLY_PORT% -- connection timed out.
    echo          Is this PC on the correct network? Is Tally running?
    call :log "Pre-flight: TALLY TIMEOUT"
    goto :fail
) else (
    echo   [FAIL] Tally at %TALLY_HOST%:%TALLY_PORT% -- connection refused.
    echo          Check that Tally is running and the port is correct.
    call :log "Pre-flight: TALLY REFUSED"
    goto :fail
)

REM --- Check 1c: DNS resolution for ngrok domain ---
call :log "Pre-flight: checking DNS for %NGROK_DOMAIN%..."
powershell -NoProfile -Command "try { [System.Net.Dns]::GetHostAddresses('%NGROK_DOMAIN%') | Out-Null; Write-Output 'OK' } catch { Write-Output 'FAIL' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "DNS_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!DNS_CHECK!" neq "OK" (
    echo   [FAIL] Cannot resolve %NGROK_DOMAIN% -- DNS issue.
    call :log "Pre-flight: DNS FAILED for %NGROK_DOMAIN%"
    goto :fail
)
echo   DNS for ngrok domain ...... OK
call :log "Pre-flight: DNS OK"

echo   All pre-flight checks passed.

REM ============================================================
REM  STEP 2/6: Download ngrok
REM ============================================================
echo.
echo [2/6] Downloading ngrok...

if exist "%NGROK_EXE%" (
    REM Verify it actually runs
    "%NGROK_EXE%" version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('"%NGROK_EXE%" version 2^>^&1') do (
            echo   Already installed: %%v
            call :log "ngrok: already installed -- %%v"
        )
        goto :skip_download
    ) else (
        echo   Existing ngrok.exe is corrupted. Re-downloading...
        call :log "ngrok: existing exe corrupted, re-downloading"
        REM Kill any process locking the file before deleting
        taskkill /f /im ngrok.exe >nul 2>&1
        timeout /t 2 /nobreak >nul
        del /f "%NGROK_EXE%" 2>nul
        if exist "%NGROK_EXE%" (
            echo   [FAIL] Cannot delete corrupted ngrok.exe -- file is locked.
            echo          Close any programs using it and re-run this script.
            call :log "ngrok: cannot delete locked exe"
            goto :fail
        )
    )
)

call :log "ngrok: downloading from %NGROK_ZIP_URL%"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%NGROK_ZIP_URL%' -OutFile '%INSTALL_DIR%\ngrok.zip' -UseBasicParsing -ErrorAction Stop; Write-Output 'OK' } catch { Write-Output ('FAIL: ' + $_.Exception.Message) }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "DL_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!DL_CHECK!" neq "OK" (
    echo   [FAIL] Download failed: !DL_CHECK!
    call :log "ngrok download: FAILED -- !DL_CHECK!"
    del "%INSTALL_DIR%\ngrok.zip" 2>nul
    goto :fail
)

REM Verify zip is not empty/corrupt (must be > 1MB for ngrok)
powershell -NoProfile -Command "$f = Get-Item '%INSTALL_DIR%\ngrok.zip' -ErrorAction SilentlyContinue; if ($f -and $f.Length -gt 1MB) { Write-Output 'OK' } else { Write-Output 'BAD' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "ZIP_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!ZIP_CHECK!" neq "OK" (
    echo   [FAIL] Downloaded file is corrupted or truncated.
    call :log "ngrok download: zip file corrupt"
    del "%INSTALL_DIR%\ngrok.zip" 2>nul
    goto :fail
)

REM Extract
powershell -NoProfile -Command "try { Expand-Archive -Path '%INSTALL_DIR%\ngrok.zip' -DestinationPath '%INSTALL_DIR%' -Force -ErrorAction Stop; Write-Output 'OK' } catch { Write-Output 'FAIL' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "EXT_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!EXT_CHECK!" neq "OK" (
    echo   [FAIL] Failed to extract ngrok.zip
    call :log "ngrok extract: FAILED"
    goto :fail
)
del "%INSTALL_DIR%\ngrok.zip" 2>nul

REM Verify exe exists and runs
if not exist "%NGROK_EXE%" (
    echo   [FAIL] ngrok.exe not found after extraction.
    call :log "ngrok: exe missing after extract"
    goto :fail
)
"%NGROK_EXE%" version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo   [FAIL] ngrok.exe exists but fails to run.
    echo          This is often caused by antivirus software blocking ngrok.
    echo          Add an exclusion for %INSTALL_DIR% in Windows Defender / your antivirus.
    call :log "ngrok: exe exists but won't run (likely antivirus)"
    goto :fail
)

for /f "tokens=*" %%v in ('"%NGROK_EXE%" version 2^>^&1') do (
    echo   Downloaded: %%v
    call :log "ngrok: downloaded -- %%v"
)

:skip_download

REM ============================================================
REM  STEP 3/6: Write ngrok configuration
REM ============================================================
echo.
echo [3/6] Writing ngrok configuration...

REM Write YAML via PowerShell (avoids batch echo trailing-space issues that break YAML)
REM Using v3 endpoints syntax (tunnels is deprecated, removed end of 2025)
REM Note: We pass config values as environment variables to avoid quoting nightmares
SET "CFG_TOKEN=%NGROK_AUTHTOKEN%"
SET "CFG_DOMAIN=%NGROK_DOMAIN%"
SET "CFG_TALLY=http://%TALLY_HOST%:%TALLY_PORT%"
SET "CFG_LOGPATH=%LOG_DIR%\ngrok.log"
SET "CFG_OUTPATH=%NGROK_CONFIG%"
powershell -NoProfile -Command "$L = [System.Collections.ArrayList]@(); [void]$L.Add('version: 3'); [void]$L.Add('agent:'); [void]$L.Add('  authtoken: ' + $env:CFG_TOKEN); [void]$L.Add('  console_ui: false'); [void]$L.Add('  log: ' + $env:CFG_LOGPATH); [void]$L.Add('  log_level: info'); [void]$L.Add('  log_format: json'); [void]$L.Add('endpoints:'); [void]$L.Add('  - name: tally-relay'); [void]$L.Add('    url: https://' + $env:CFG_DOMAIN); [void]$L.Add('    upstream:'); [void]$L.Add('      url: ' + $env:CFG_TALLY); [void]$L.Add('      protocol: http1'); $yaml = ($L -join [char]10) + [char]10; [IO.File]::WriteAllText($env:CFG_OUTPATH, $yaml, (New-Object Text.UTF8Encoding $false)); Write-Output 'OK'" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "CFG_CHECK=" < "%LOG_DIR%\tmp_check.txt"
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!CFG_CHECK!" neq "OK" (
    echo   [FAIL] Failed to write config file.
    call :log "ngrok config: WRITE FAILED"
    goto :fail
)

REM Validate config with ngrok
"%NGROK_EXE%" config check --config "%NGROK_CONFIG%" > "%LOG_DIR%\tmp_cfgcheck.txt" 2>&1
SET "CFG_EXIT=!ERRORLEVEL!"
findstr /i "valid" "%LOG_DIR%\tmp_cfgcheck.txt" >nul 2>&1
SET "CFG_HAS_VALID=!ERRORLEVEL!"

if !CFG_EXIT! equ 0 (
    echo   Config written and validated: %NGROK_CONFIG%
    call :log "ngrok config: written and validated at %NGROK_CONFIG%"
) else if !CFG_HAS_VALID! equ 0 (
    echo   Config written and validated: %NGROK_CONFIG%
    call :log "ngrok config: written and validated at %NGROK_CONFIG%"
) else (
    REM Config check failed -- likely endpoints syntax not supported by this ngrok version
    REM Fall back to deprecated but widely-supported tunnels syntax
    echo   [INFO] Endpoints syntax not supported by this ngrok version.
    echo          Falling back to tunnels syntax...
    call :log "ngrok config: endpoints syntax failed, falling back to tunnels"
    powershell -NoProfile -Command "$L = [System.Collections.ArrayList]@(); [void]$L.Add('version: 3'); [void]$L.Add('agent:'); [void]$L.Add('  authtoken: ' + $env:CFG_TOKEN); [void]$L.Add('  console_ui: false'); [void]$L.Add('  log: ' + $env:CFG_LOGPATH); [void]$L.Add('  log_level: info'); [void]$L.Add('  log_format: json'); [void]$L.Add('tunnels:'); [void]$L.Add('  tally-relay:'); [void]$L.Add('    proto: http'); [void]$L.Add('    addr: ' + $env:CFG_TALLY); [void]$L.Add('    domain: ' + $env:CFG_DOMAIN); [void]$L.Add('    inspect: false'); $yaml = ($L -join [char]10) + [char]10; [IO.File]::WriteAllText($env:CFG_OUTPATH, $yaml, (New-Object Text.UTF8Encoding $false)); Write-Output 'OK'" > "%LOG_DIR%\tmp_check.txt" 2>&1
    SET /p "CFG_FALLBACK=" < "%LOG_DIR%\tmp_check.txt"
    del "%LOG_DIR%\tmp_check.txt" 2>nul
    if /i "!CFG_FALLBACK!" neq "OK" (
        echo   [FAIL] Failed to write fallback config.
        call :log "ngrok config: FALLBACK WRITE FAILED"
        goto :fail
    )
    REM Validate fallback config
    "%NGROK_EXE%" config check --config "%NGROK_CONFIG%" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo   [FAIL] Both config formats rejected by ngrok.
        echo          Config contents:
        type "%NGROK_CONFIG%"
        call :log "ngrok config: BOTH FORMATS FAILED"
        goto :fail
    )
    echo   Config written (tunnels syntax): %NGROK_CONFIG%
    call :log "ngrok config: written with tunnels fallback at %NGROK_CONFIG%"
)
del "%LOG_DIR%\tmp_cfgcheck.txt" 2>nul

REM ============================================================
REM  STEP 4/6: Stop existing service (idempotent cleanup)
REM ============================================================
echo.
echo [4/6] Preparing service...

REM Kill any stray ngrok processes
taskkill /f /im ngrok.exe >nul 2>&1

REM Stop and remove any existing ngrok services (handles both names)
for %%s in (ngrok ngrok-agent ngrok_agent %SERVICE_NAME%) do (
    sc query %%s >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo   Removing existing service: %%s
        call :log "Service: removing existing %%s"
        net stop %%s >nul 2>&1
        timeout /t 2 /nobreak >nul
        "%NGROK_EXE%" service uninstall --config "%NGROK_CONFIG%" >nul 2>&1
        sc delete %%s >nul 2>&1
        timeout /t 2 /nobreak >nul
    )
)

echo   Ready for fresh install.

REM ============================================================
REM  STEP 5/6: Install ngrok as Windows service
REM ============================================================
echo.
echo [5/6] Installing Windows service...

REM Use ngrok's native service installer
call :log "Service: installing via 'ngrok service install'"
"%NGROK_EXE%" service install --config "%NGROK_CONFIG%" > "%LOG_DIR%\tmp_svc.txt" 2>&1
SET "SVC_INSTALL_EXIT=!ERRORLEVEL!"
if !SVC_INSTALL_EXIT! neq 0 (
    echo   Native service install returned error code !SVC_INSTALL_EXIT!.
    call :log "Service: native install error !SVC_INSTALL_EXIT!"
    type "%LOG_DIR%\tmp_svc.txt" >> "%LOG_FILE%" 2>nul
)
del "%LOG_DIR%\tmp_svc.txt" 2>nul

REM Find the service -- ngrok may register under any name (ngrok, ngrok-agent, etc.)
REM Strategy: first try known names, then search for any service with ngrok in its binary path
SET "ACTUAL_SERVICE="
for %%s in (ngrok ngrok-agent ngrok_agent %SERVICE_NAME%) do (
    sc query %%s >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        SET "ACTUAL_SERVICE=%%s"
        goto :found_service
    )
)

REM Known names didn't match -- search registry for any service with ngrok in binary path
call :log "Service: known names not found, searching registry..."
REM reg query /s /f "ngrok" /d returns lines like:
REM   HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\SomeServiceName
REM   HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\SomeServiceName\Parameters
REM We want the service name = token 5 when split by backslash (0-indexed: token 5)
powershell -NoProfile -Command "Get-WmiObject Win32_Service | Where-Object { $_.PathName -match 'ngrok' } | ForEach-Object { Write-Output $_.Name }" > "%LOG_DIR%\tmp_svc.txt" 2>&1
SET /p "FOUND_SVC=" < "%LOG_DIR%\tmp_svc.txt"
del "%LOG_DIR%\tmp_svc.txt" 2>nul
if defined FOUND_SVC (
    SET "FOUND_SVC=!FOUND_SVC: =!"
    sc query !FOUND_SVC! >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        SET "ACTUAL_SERVICE=!FOUND_SVC!"
        echo   Found ngrok service via WMI: !FOUND_SVC!
        call :log "Service: found via WMI -- !FOUND_SVC!"
        goto :found_service
    )
)

REM Still not found -- fallback: create service manually with sc create
call :log "Service: no ngrok service found anywhere, using sc create"
SET "SVC_BIN=%NGROK_EXE% start --all --config %NGROK_CONFIG%"
sc create %SERVICE_NAME% binPath= "!SVC_BIN!" start= auto DisplayName= "%SERVICE_DISPLAY%" > "%LOG_DIR%\tmp_svc.txt" 2>&1
SET "SC_CREATE_EXIT=!ERRORLEVEL!"
type "%LOG_DIR%\tmp_svc.txt" >> "%LOG_FILE%" 2>nul
del "%LOG_DIR%\tmp_svc.txt" 2>nul
if !SC_CREATE_EXIT! neq 0 (
    echo   [FAIL] Could not create Windows service (error !SC_CREATE_EXIT!).
    call :log "Service: sc create FAILED with !SC_CREATE_EXIT!"
    goto :fail
)
REM Verify it actually exists now
sc query %SERVICE_NAME% >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo   [FAIL] sc create reported success but service not found.
    call :log "Service: sc create claimed success but query fails"
    goto :fail
)
SET "ACTUAL_SERVICE=%SERVICE_NAME%"

:found_service
REM Safety check: if ACTUAL_SERVICE is still empty, something went very wrong
if "!ACTUAL_SERVICE!" equ "" (
    echo   [FAIL] Service was not created. Neither ngrok native install nor sc create worked.
    call :log "Service: ACTUAL_SERVICE is empty -- no service created"
    goto :fail
)
echo   Service registered: !ACTUAL_SERVICE!
call :log "Service: registered as !ACTUAL_SERVICE!"

REM Set service description
sc description !ACTUAL_SERVICE! "Forwards Tally XML API traffic from Saral ERP (GCP) through this PC to Tally server at %TALLY_HOST%:%TALLY_PORT%" >nul 2>&1

REM Configure auto-restart on failure (restart after 30s, 60s, 120s; reset counter daily)
sc failure !ACTUAL_SERVICE! actions= restart/30000/restart/60000/restart/120000 reset= 86400 >nul 2>&1
call :log "Service: recovery policy set (restart on crash: 30s, 60s, 120s)"

REM Ensure service is set to auto-start
sc config !ACTUAL_SERVICE! start= auto >nul 2>&1

REM ============================================================
REM  STEP 6/6: Start service and verify end-to-end
REM ============================================================
echo.
echo [6/6] Starting service and verifying...

REM Start the service (try ngrok native first, then net start as fallback)
"%NGROK_EXE%" service start --config "%NGROK_CONFIG%" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    net start !ACTUAL_SERVICE! >nul 2>&1
)
call :log "Service: start command issued for !ACTUAL_SERVICE!"

REM Wait and check status (poll every 2s for 10s)
SET "SVC_RUNNING=0"
for /L %%i in (1,1,5) do (
    timeout /t 2 /nobreak >nul
    sc query !ACTUAL_SERVICE! | findstr /i "RUNNING" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        SET "SVC_RUNNING=1"
        goto :svc_running_check
    )
)
:svc_running_check

if !SVC_RUNNING! equ 0 (
    echo   [FAIL] Service did not start within 10 seconds.
    echo.
    echo   Diagnostic info:
    sc query !ACTUAL_SERVICE!
    echo.
    echo   Check logs:
    echo     %LOG_DIR%\ngrok.log
    echo     Windows Event Viewer
    call :log "Service: FAILED TO START within 10s"
    goto :fail
)
echo   Service status: RUNNING
call :log "Service: RUNNING"

REM --- End-to-end verification: hit tunnel URL and check Tally responds ---
echo   Verifying tunnel end-to-end (may take 10-15 seconds)...
call :log "E2E test: starting..."

SET "E2E_RESULT=FAIL"
for /L %%i in (1,1,6) do (
    timeout /t 3 /nobreak >nul
    call :e2e_single_check
    if /i "!E2E_RESULT!" equ "TALLY_OK" goto :e2e_done
    if /i "!E2E_RESULT!" equ "HTTP_OK" goto :e2e_done
)
:e2e_done
del "%LOG_DIR%\tmp_check.txt" 2>nul

if /i "!E2E_RESULT!" equ "TALLY_OK" (
    echo   End-to-end test: PASSED
    echo   Tally is responding through the tunnel.
    call :log "E2E test: PASSED -- Tally responding via tunnel"
) else if /i "!E2E_RESULT!" equ "HTTP_OK" (
    echo   Tunnel is active (HTTP 200 received).
    echo   Tally signature not detected -- Tally may not be running right now.
    echo   The tunnel will work once Tally is started.
    call :log "E2E test: PARTIAL -- tunnel up, Tally not responding"
) else (
    echo   [WARN] Could not verify tunnel end-to-end.
    echo          The service IS running -- tunnel may need a moment.
    echo          Check: https://%NGROK_DOMAIN% from a browser.
    call :log "E2E test: WARN -- could not reach tunnel URL after 18s"
)

REM ============================================================
REM  SUCCESS
REM ============================================================
echo.
echo ============================================================
echo   SETUP COMPLETE
echo ============================================================
echo.
echo   Tunnel URL   : https://%NGROK_DOMAIN%
echo   Tally Server : %TALLY_HOST%:%TALLY_PORT%
echo   Service Name : !ACTUAL_SERVICE!
echo   Startup      : Automatic (starts at boot)
echo   Recovery     : Auto-restart on crash (30s, 60s, 120s)
echo.
echo   Logs:
echo     Setup     : %LOG_FILE%
echo     Runtime   : %LOG_DIR%\ngrok.log
echo.
echo   Management commands (run as Administrator):
echo     Status    : sc query !ACTUAL_SERVICE!
echo     Stop      : net stop !ACTUAL_SERVICE!
echo     Start     : net start !ACTUAL_SERVICE!
echo     Restart   : net stop !ACTUAL_SERVICE! ^& net start !ACTUAL_SERVICE!
echo     Uninstall : "%NGROK_EXE%" service uninstall --config "%NGROK_CONFIG%"
echo.
echo   This tunnel runs silently. No user interaction needed.
echo   It auto-starts on boot and auto-restarts on crash.
echo.
call :log "========== SETUP COMPLETED SUCCESSFULLY =========="
call :log "Service: !ACTUAL_SERVICE!, Domain: %NGROK_DOMAIN%, Tally: %TALLY_HOST%:%TALLY_PORT%"
pause
ENDLOCAL
exit /b 0

REM ============================================================
REM  FAILURE HANDLER
REM ============================================================
:fail
echo.
echo ============================================================
echo   SETUP FAILED -- Check the log for details
echo   Log: %LOG_FILE%
echo ============================================================
echo.
call :log "========== SETUP FAILED =========="
pause
ENDLOCAL
exit /b 1

REM ============================================================
REM  LOGGING FUNCTION
REM ============================================================
:log
echo [%DATE% %TIME:~0,8%] %~1 >> "%LOG_FILE%" 2>nul
goto :eof

:e2e_single_check
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $r = Invoke-WebRequest -Uri 'https://%NGROK_DOMAIN%' -UseBasicParsing -TimeoutSec 10 -Headers @{ 'ngrok-skip-browser-warning' = '1' } -ErrorAction Stop; if ($r.Content -match 'Tally') { Write-Output 'TALLY_OK' } elseif ($r.StatusCode -eq 200) { Write-Output 'HTTP_OK' } else { Write-Output 'WAIT' } } catch { Write-Output 'WAIT' }" > "%LOG_DIR%\tmp_check.txt" 2>&1
SET /p "E2E_RESULT=" < "%LOG_DIR%\tmp_check.txt"
goto :eof
