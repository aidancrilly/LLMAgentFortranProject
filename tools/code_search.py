import os
from langchain.tools import Tool

def search_codebase(query: str, directory: str = "./", extension: str = ".f90") -> str:
    matches = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extension):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if query in content:
                            matches.append(f"File: {file_path}\n---\n{content[:1000]}\n...")
                except Exception as e:
                    matches.append(f"Error reading {file_path}: {e}")

    if not matches:
        return f"No references to '{query}' found in {directory}"
    return "\n\n".join(matches[:3])

code_search_tool = Tool(
    name="SearchCodebase",
    func=lambda query: search_codebase(query, directory=r"F:\Visual Studio 2015\Projects\MinotaurLITE\MinotaurLITE\src\\", extension=".f90"),
    description="Searches through Fortran (.f90) files for a variable, subroutine, or function."
)