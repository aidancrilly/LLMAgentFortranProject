import f90nml
from langchain.tools import Tool

def read_namelist_var(file_path : str, input_str: str) -> str:
    try:
        group, var = input_str.split(',')
        nml = f90nml.read(file_path.strip())
        value = nml[group.strip()][var.strip()]
        return f"{var.strip()} in group {group.strip()} is set to: {value}"
    except Exception as e:
        return f"Error: {e}"

namelist_tool = Tool(
    name="ReadNamelistVar",
    func = lambda input_str : read_namelist_var(file_path=r'F:\Visual Studio 2015\Projects\MinotaurLITE\MinotaurLITE\input\config_ionkin.ini',input_str=input_str),
    description="Reads a variable from the Fortran project NAMELIST input deck. Input should be: group_name, variable_name"
)