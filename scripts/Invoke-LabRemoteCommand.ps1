[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Username,
    [Parameter(Mandatory)] [string]$Password,
    [Parameter(Mandatory)] [string]$Command,
    [string]$HostName = '127.0.0.1',
    [int]$Port = 3443,
    [int]$TimeoutSeconds = 15
)

$ErrorActionPreference = 'Stop'
$client = [System.Net.Sockets.TcpClient]::new()
$client.ReceiveTimeout = $TimeoutSeconds * 1000
$client.SendTimeout = $TimeoutSeconds * 1000
$client.Connect($HostName, $Port)

try {
    $stream = $client.GetStream()
    $stream.ReadTimeout = $TimeoutSeconds * 1000
    $writer = [System.IO.StreamWriter]::new($stream, [System.Text.Encoding]::ASCII, 4096, $true)
    $writer.NewLine = "`r`n"
    $writer.AutoFlush = $true

    function Read-Until([string]$Marker) {
        $buffer = [System.Text.StringBuilder]::new()
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            $value = $stream.ReadByte()
            if ($value -lt 0) { throw 'RA connection closed unexpectedly' }
            [void]$buffer.Append([char]$value)
            if ($buffer.ToString().Contains($Marker)) { return $buffer.ToString() }
        }
        throw "Timed out waiting for RA marker: $Marker"
    }

    [void](Read-Until 'Username: ')
    $writer.WriteLine($Username)
    [void](Read-Until 'Password: ')
    $writer.WriteLine($Password)
    $login = Read-Until 'mangos>'
    if (-not $login.Contains('+Logged in.')) { throw 'RA login failed' }
    $writer.WriteLine($Command)
    $response = Read-Until 'mangos>'
    $writer.WriteLine('quit')
    return ($response -replace 'mangos>$', '').Trim()
}
finally {
    $client.Dispose()
}
