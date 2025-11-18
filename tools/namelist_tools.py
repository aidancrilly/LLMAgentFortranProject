from pathlib import Path
from typing import Dict

import f90nml

from .tool_spec import ToolSpec


def read_namelist_var(file_path: Path, group: str, variable: str) -> str:
    try:
        if not file_path.exists():
            return f"Namelist file not found: {file_path}"
        nml = f90nml.read(file_path)
        value = nml[group][variable]
        return f"{variable} in group {group} is set to: {value}"
    except Exception as exc:
        return f"Error: {exc}"


def build_namelist_tool(namelist_path: Path) -> ToolSpec:
    def _tool(args: Dict[str, str]) -> str:
        group = args.get("group")
        variable = args.get("variable")
        if not group or not variable:
            return "Provide both 'group' and 'variable' properties."
        return read_namelist_var(namelist_path, group, variable)

    return ToolSpec(
        name="ReadNamelistVar",
        description=(
            f"Read a variable from the Fortran NAMELIST file ({namelist_path}). "
            "Provide 'group' and 'variable'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "description": "Namelist group name.",
                },
                "variable": {
                    "type": "string",
                    "description": "Variable name within the group.",
                },
            },
            "required": ["group", "variable"],
        },
        func=_tool,
    )
