from pathlib import Path
import subprocess
import os


def converter_path():
    configured=os.environ.get('ODA_CONVERTER')
    if configured:
        path=Path(configured.strip('\'"'))
        return str(path) if path.is_file() else None
    candidates=sorted(Path('C:/Program Files/ODA').glob('ODAFileConverter */ODAFileConverter.exe'))
    return str(candidates[-1]) if candidates else None


def dwg_enabled():
    return (os.environ.get('CAD_FREE_MODE','0')!='1' or os.environ.get('CAD_DWG_ENABLED','0')=='1') and bool(converter_path())


class DWGConverter:

    def __init__(self, oda_path: str):
        self.oda_path = Path(oda_path)

    def convert_dwg_to_dxf(
        self,
        input_dir: str,
        output_dir: str
    ):
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        command = [
            str(self.oda_path),
            str(input_dir),
            str(output_dir),
            "ACAD2018",
            "DXF",
            "0",
            "1"
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ODA conversion failed:\n{result.stderr}"
            )

        return result.stdout

    def convert_dxf_to_dwg(
        self,
        input_dir: str,
        output_dir: str
    ):
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        command = [
            str(self.oda_path),
            str(input_dir),
            str(output_dir),
            "ACAD2018",
            "DWG",
            "0",
            "1"
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ODA conversion failed:\n{result.stderr}"
            )

        return result.stdout
