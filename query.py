from langchain_community.llms import Ollama
from langchain.agents import initialize_agent, AgentType
from tools.file_tools import file_reader_tool
from tools.code_search import code_search_tool
from tools.namelist_tools import namelist_tool

def main():
    # Load background context
    with open("context.txt") as f:
        context = f.read()

    llm = Ollama(model="mistral")

    agent = initialize_agent(
        tools=[file_reader_tool, code_search_tool, namelist_tool],
        llm=llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
    )

    # Priming the agent with Fortran context
    agent.invoke({
        "input": context,
        "chat_history": []
    })

    # User query example
    print("Enter your query about the MinotaurLITE program:\n")
    query = input()
    result = agent.invoke({
        "input": query,
        "chat_history": []
    })
    print("\n\nAgent Result:\n", result)


if __name__ == "__main__":
    main()
