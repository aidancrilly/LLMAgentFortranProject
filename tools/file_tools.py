from langchain.tools import Tool

def read_file(file_path: str) -> str:
    """Reads the content of a file and returns it."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

file_reader_tool = Tool(
    name="ReadFile",
    func=read_file,
    description="Use this tool to read a code file. Input should be the path to the file."
)