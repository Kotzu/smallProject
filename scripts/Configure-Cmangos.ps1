[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [string]$BoostRoot = 'E:\WoWserver\TBC-LAB\toolchain\boost-1.87.0',
    [switch]$WithoutPlayerbots
)

$ErrorActionPreference = 'Stop'

$cmake = 'C:\Program Files\CMake\bin\cmake.exe'
$source = Join-Path $LabRoot 'source\mangos-tbc'
$profile = if ($WithoutPlayerbots) { 'core-standard' } else { 'core-playerbots' }
$build = Join-Path $LabRoot ("build\{0}" -f $profile)
$runtime = Join-Path $LabRoot ("runtime\{0}" -f $profile)

foreach ($required in @($cmake, $source, $BoostRoot)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing prerequisite: $required"
    }
}

$playerbots = if ($WithoutPlayerbots) { 'OFF' } else { 'ON' }

& $cmake -S $source -B $build -G 'Visual Studio 17 2022' -A x64 `
    "-DCMAKE_INSTALL_PREFIX=$runtime" `
    "-DBOOST_ROOT=$BoostRoot" `
    '-DBUILD_GAME_SERVER=ON' `
    '-DBUILD_LOGIN_SERVER=ON' `
    '-DBUILD_SCRIPTDEV=ON' `
    "-DBUILD_PLAYERBOTS=$playerbots" `
    '-DBUILD_AHBOT=OFF' `
    '-DBUILD_EXTRACTORS=ON' `
    '-DDEBUG=OFF' `
    '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'

if ($LASTEXITCODE -ne 0) {
    throw "CMake configure failed for $profile"
}

Write-Output "CMAKE_CONFIGURE_OK:$profile"

