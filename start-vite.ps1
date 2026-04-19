$nodePath = "c:\Users\Kalev\supptracker\node_portable\node-v22.14.0-win-x64"
$env:PATH = "$nodePath;$env:PATH"
Set-Location "c:\Users\Kalev\supptracker"
& ".\node_modules\.bin\vite.cmd" "--port" "5173"
