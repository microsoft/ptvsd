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
$env:PYDEVD_USE_CYTHON = "NO"

if (-not $pack) {
    (gci $packages\python* -Directory) | %{ gi $_\tools\python.exe } | ?{ Test-Path $_ } | %{
        Write-Host "Building with $_"
        & $_ -m pip install -U pyfindvs setuptools wheel cython
        pushd "$root\..\src\ptvsd\_vendored\pydevd"
        & $_ setup_cython.py enable_msbuildcompiler build_ext -b "$bin" -t "$obj"
        popd
    }

} else {
    gci $dist\*.whl, $dist\*.zip | Remove-Item -Force

    (gci $packages\python* -Directory) | %{ gi $_\tools\python.exe } | ?{ Test-Path $_ } | select -last 1 | %{
        $plat = 'win_amd64'
        if ($_ -contains 'x86'){
            $plat = 'win32'
        }
        Write-Host "Building sdist with $_"
        & $_ setup.py sdist -d "$dist" --formats zip

        Write-Host "Building wheel with $_  for platform $plat"
        & $_ setup.py build -b "$bin" -t "$obj" bdist_wheel -d "$dist" -p $plat
        gci $dist\ptvsd-*.whl | %{
            Write-Host "Built wheel found at $_"
        }
    }

}

