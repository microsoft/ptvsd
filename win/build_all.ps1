param($packages, [switch]$pack)

$root = $script:MyInvocation.MyCommand.Path | Split-Path -parent;
if ($env:BUILD_BINARIESDIRECTORY) {
    $bin = mkdir -Force $env:BUILD_BINARIESDIRECTORY\bin
    $obj = mkdir -Force $env:BUILD_BINARIESDIRECTORY\obj
    $dist = mkdir -Force $env:BUILD_BINARIESDIRECTORY\dist
} else {
    $bin = mkdir -Force $root\bin
    $obj = mkdir -Force $root\obj
    $dist = mkdir -Force $root\dist
}

$env:SKIP_CYTHON_BUILD = "1"

if (-not $pack) {
    (Get-ChildItem $packages\python* -Directory) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | ForEach-Object{
        Write-Host "Building with $_"
        & $_ -m pip install -U pip
        if ($_ -match 'python2'){
            & $_ -m pip install -U pathlib
        }
        & $_ -m pip install -U pyfindvs setuptools wheel cython
        
        Push-Location "$root\..\src\ptvsd\_vendored\pydevd"
        & $_ setup_cython.py enable_msbuildcompiler build_ext -b "$bin" -t "$obj"
        Pop-Location
    }

} else {
    Get-ChildItem $dist\*.whl, $dist\*.zip | Remove-Item -Force

    (Get-ChildItem $packages\python* -Directory) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | Select-Object -last 1 | ForEach-Object{
        Write-Host "Building sdist with $_"
        & $_ setup.py sdist -d "$dist" --formats zip
    }

    (Get-ChildItem $packages\python* -Directory) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | ForEach-Object{
        $plat = 'win_amd64'
        if ($_ -match 'x86'){
            $plat = 'win32'
        }

        Write-Host "Building wheel with $_  for platform $plat"
        & $_ setup.py build -b "$bin" -t "$obj" bdist_wheel -d "$dist" -p $plat
        Get-ChildItem $dist\ptvsd-*.whl | ForEach-Object{
            Write-Host "Built wheel found at $_"
        }
    }

    (Get-ChildItem $packages\python* -Directory) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | Select-Object -last 1 | ForEach-Object{
        $plat = 'win_amd64'
        if ($_ -match 'x86'){
            $plat = 'win32'
        }

        Write-Host "Building wheel with $_  for platform $plat"
        & $_ setup.py build -b "$bin" -t "$obj" bdist_wheel -d "$dist" -p $plat --pure
        Get-ChildItem $dist\ptvsd-*.whl | ForEach-Object{
            Write-Host "Built wheel found at $_"
        }
    }

}

