"""Build the experimental bridge with workspace-local Microsoft tool packages."""
from pathlib import Path
import hashlib
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    portable=ROOT/'storage/tools/portable-native'
    sdk=ROOT/'storage/tools/objectarx2027/CDROM1'
    compiler=next(portable.glob('Microsoft.VC.*Tools.HostX64.TargetX64.base/Contents/VC/Tools/MSVC/14.44*/bin/Hostx64/x64/cl.exe'),None)
    headers=next(portable.glob('Microsoft.VC.*CRT.Headers.base/Contents/VC/Tools/MSVC/14.44*/include'),None)
    runtime=next(portable.glob('Microsoft.VC.*CRT.x64.Desktop.base/Contents/VC/Tools/MSVC/14.44*/lib/x64'),None)
    windows=next((p.parent.parent for p in (portable/'microsoft.windows.sdk.cpp').rglob('Windows.h')),None)
    if windows is None:
        windows=next((p.parent.parent for p in (portable/'microsoft.windows.sdk.cpp').rglob('windows.h')),None)
    if not all([compiler,headers,runtime,windows]):
        raise RuntimeError('Portable compiler/Windows SDK packages are incomplete')
    output=ROOT/'autodesk/NativePointReference/build';output.mkdir(exist_ok=True)
    environment=os.environ.copy()
    environment['INCLUDE']=';'.join(map(str,[headers,windows/'ucrt',windows/'shared',windows/'um',windows/'winrt']))
    dynamic_runtime=next(portable.glob('Microsoft.VC.*CRT.x64.Store.base/Contents/VC/Tools/MSVC/14.44*/lib/x64'),None)
    if dynamic_runtime is None:raise RuntimeError('MSVC dynamic runtime import libraries missing')
    libs=[dynamic_runtime,runtime,portable/'microsoft.windows.sdk.cpp.x64/c/ucrt/x64',portable/'microsoft.windows.sdk.cpp.x64/c/um/x64',sdk/'lib-x64']
    environment['LIB']=';'.join(map(str,libs))
    args=[str(compiler),'/nologo','/LD','/MD','/EHsc','/std:c++17','/DUNICODE','/D_UNICODE','/DWIN32','/D_WINDOWS',
          '/I'+str(sdk/'inc'),str(ROOT/'autodesk/NativePointReference/NativePointReference.cpp'),
          '/Fo'+str(output/'NativePointReference.obj'),'/link','acdb26.lib','acge26.lib','rxapi.lib',
          '/OUT:'+str(output/'MechanicalPointReference.dll')]
    subprocess.run(args,env=environment,cwd=output,check=True)
    print('SHA256',hashlib.sha256((output/'MechanicalPointReference.dll').read_bytes()).hexdigest())


if __name__=='__main__':main()
