# Glossary

Every LangGraph term used in the tutorial, in alphabetical order. Each entry has a one-line definition and the lesson
that teaches it. Terms are added as the lessons are written.

| Term | Meaning | Lesson |
|---|---|---|
| `add_conditional_edges` | Registers a router function to run after a given node and pick the next node. | 05 |
| `add_edge` | Adds a fixed arrow from one node to another. | 04 |
| `add_messages` | LangGraph's reducer for message lists: appends, but replaces a message that has the same `id`. | 06 |
| `add_node` | Registers a function as a node, under a name. | 03 |
| Agent | A program in which an LLM decides, in a loop, which tools to call until it can answer. | 19 |
| Agent loop | Model → tools → model … until the model answers without tool calls. | 18, 19 |
| `Annotated` | Attaches extra information to a type hint; `Annotated[list[str], operator.add]` attaches a reducer. | 06 |
| `bind_tools` | Attaches tool descriptions to an LLM so it can ask for tool calls. | 19 |
| Builder | A graph still being put together: you add nodes and edges to it, then compile it. | 03 |
| Checkpoint | One saved snapshot of the state, with its own `checkpoint_id`. | 13 |
| Checkpointer | Saves the state after every step so later runs can continue from it; passed to `compile`. | 13 |
| `Command` | A value a node returns to update the state (`update=`) and choose the next node (`goto=`) at once. | 10 |
| `Command(resume=...)` | The input that resumes a paused thread with the human's answer. | 14 |
| `Command[Literal[...]]` | The return type hint listing every node a `Command` might go to; used for checks and the diagram. | 10 |
| `compile()` | Checks the builder's wiring and returns a runnable compiled graph. | 04 |
| Compiled graph | The runnable object `compile()` returns; it has `invoke`, `get_graph` and more. | 04 |
| Conditional edge | An edge whose destination is chosen while the graph runs, by a router function. | 05 |
| Config | The second argument of `invoke`: a dict of settings for that run, such as `recursion_limit`. | 07 |
| Context schema | The class (usually a `dataclass`) describing the runtime context; passed as `context_schema=`. | 12 |
| `create_agent` | LangChain's function that builds the agent loop graph for you from a model and tools. | 19 |
| `dataclass` | A small Python class with named fields and optional default values; one way to write a state schema. | 02 |
| Decorator | An `@name` line above a function that wraps it in extra behaviour. | 18 |
| `destinations` | An `add_node` option listing a node's possible `goto` targets; an alternative to the type hint. | 10 |
| `draw_mermaid()` | Prints a compiled graph as Mermaid diagram text: `graph.get_graph().draw_mermaid()`. | 04 |
| Edge | An arrow saying which node runs next. | 01 |
| END | The exit point of a graph, where the final state leaves; a reserved name (`'__end__'`) you import. | 01, 04 |
| Exit condition | The test in a router that sends a loop to `END`. | 07 |
| Fan-in | Several branches leading into one node, which runs after them. | 08 |
| Fan-out | One node with several outgoing edges, so all their targets run in parallel. | 08 |
| Fork | The new branch of history that time travel creates; the old branch is kept. | 13 |
| `get_state` / `get_state_history` | Read the latest checkpoint / every checkpoint of a thread. | 13 |
| `get_stream_writer()` | Gives a node a `writer` function that sends custom data to the `"custom"` stream. | 15 |
| `goto` | The part of a `Command` that names the next node (or `END`). | 10 |
| Graph | A program drawn as nodes joined by edges, all sharing one state. | 01 |
| `GraphInterrupt` | The special exception `interrupt` uses to pause; never catch it. | 14 |
| `GraphRecursionError` | Raised when a run reaches the recursion limit without finishing. | 07 |
| Human-in-the-loop | A run that pauses so a person can answer, approve or edit before it goes on. | 14 |
| `InMemorySaver` | A checkpointer that keeps checkpoints in memory; lost when the program stops. | 13 |
| `InMemoryStore` | A store kept in memory; lost when the program stops. | 17 |
| Input schema | The keys a graph accepts in `invoke`, set with `input_schema=`; other keys are dropped. | 11 |
| `__interrupt__` | The key in a paused run's result holding the list of `Interrupt` objects. | 14 |
| `interrupt(value)` | Pauses the graph inside a node and sends `value` to the caller; on resume it returns the answer. | 14 |
| `InvalidUpdateError` | Raised when parallel nodes write a key with no reducer, or a node returns something that isn't a dict. | 03, 08 |
| `invoke` | Runs the compiled graph from a starting state and returns the final state. | 04 |
| Item | One saved dict in the store, with its `namespace`, `key`, `value` and timestamps. | 17 |
| Iterator | Something you loop over with `for`, getting one item at a time. | 15 |
| JSON Schema | A standard description of data; `get_input_jsonschema()` / `get_output_jsonschema()` return one. | 11 |
| `Literal[...]` | A type hint meaning "exactly one of these values"; LangGraph reads it to learn a router's destinations. | 05 |
| LLM (large language model) | A model that reads and writes text, such as Gemini. | 19 |
| Loop | An edge (usually conditional) that leads back to a node that already ran. | 07 |
| Map-reduce | Run the same step on every item (map), then combine the answers (reduce). | 09 |
| Mermaid | A small text language for drawing flowcharts; LangGraph prints graphs in it. | 04 |
| Message | One turn of a chat, such as a `HumanMessage` or `AIMessage`, with its text in `content`. | 06 |
| `MessagesState` | A ready-made state with one key, `messages`, that uses the `add_messages` reducer. | 06 |
| Namespace (store) | A tuple of strings, like a folder path, that groups store items, e.g. `("users", "alice")`. | 17 |
| Namespace (streaming) | With `subgraphs=True`, a label saying which graph a streamed piece came from (`()` is the parent). | 16 |
| Node | One step of work: a function that reads the state and returns an update. | 01 |
| `NotRequired` | A `TypedDict` hint marking a key that may be left out. | 17 |
| `operator.add` | The function version of `+`; as a reducer it appends lists or adds numbers. | 06 |
| Output schema | The keys a graph returns from `invoke`, set with `output_schema=`. | 11 |
| Overall state | The full state schema the nodes work with: the first argument of `StateGraph`. | 11 |
| Parallel branches | Nodes that run in the same superstep because they were reached at the same time. | 08 |
| Parent graph | The graph that contains a subgraph. | 16 |
| Partial update | The small dict a node returns, holding only the keys it changes. | 03 |
| `path_map` | A dict from a router's return values to node names, passed to `add_conditional_edges`. | 05 |
| Payload | The input dict inside a `Send`; it's all the sent node receives. | 09 |
| Private state | Keys used inside the graph that are never accepted from outside or returned. | 11 |
| `put` / `get` / `search` / `delete` | Store methods: save an item, read one, list a namespace, remove one. | 17 |
| Pydantic `BaseModel` | A class that validates its values when created; a state schema choice for checking input. | 02 |
| ReAct | "Reason + act": the loop of reasoning, calling a tool and observing the result. | 19 |
| Recursion limit | The most supersteps one run may take; set with `{"recursion_limit": N}`. | 07 |
| Reducer | A function `(old, new) -> merged` that decides how updates to one state key are combined. | 06 |
| `RetryPolicy` | A node setting that tells LangGraph to re-run the node when it raises an error. | 03 |
| Router function | Reads the state and returns the name of the next node; it doesn't change the state. | 05 |
| `Runtime` | The object LangGraph passes to a node's `runtime` parameter; holds `context`, `store` and more. | 12 |
| Runtime context | Settings fixed for one run, passed with `invoke(..., context={...})`; not part of the state. | 12 |
| `Send` | `Send(node, input)`: run this node once with this input; a router can return a list of them. | 09 |
| Shared keys | State keys both a parent and its subgraph have; they pass in and out automatically. | 16 |
| `SqliteSaver` | A checkpointer that saves to a SQLite database file, so memory survives a restart. | 13 |
| START | The entry point of a graph, where the input state comes in; a reserved name (`'__start__'`) you import. | 01, 04 |
| State | The shared notepad (a dict) that every node can read and add to. | 01 |
| State schema | A class listing the keys of the state and their types. | 02 |
| `StateGraph` | The LangGraph class you build a graph with; `StateGraph(MyState)` gives you a builder. | 03 |
| `StateSnapshot` | What `get_state` returns: `values`, `next`, `config`, `metadata` and more. | 13 |
| Static breakpoint | A pause set at compile time with `interrupt_before=[...]` / `interrupt_after=[...]`; for debugging. | 14 |
| Store | Long-term memory shared by every thread; given to a graph with `compile(store=...)`. | 17 |
| Stream mode | What each streamed piece contains: `"values"`, `"updates"`, `"custom"`, `"messages"` and more. | 15 |
| `stream_mode="messages"` | Streams an LLM's reply in small pieces (tokens) as `(chunk, metadata)` pairs. | 19 |
| Streaming / `stream()` | Running a graph and getting results piece by piece while it runs. | 15 |
| Subgraph | A compiled graph used as a node inside another graph. | 16 |
| Superstep | One round of a run, in which every node that is ready runs; parallel nodes share a superstep. | 07, 08 |
| System message | Instructions for the model, placed before the conversation, that the user doesn't see. | 19 |
| Thread / `thread_id` | One separate line of saved history, named in `{"configurable": {"thread_id": ...}}`. | 13 |
| Time travel | Running a graph again from an earlier checkpoint by passing its `checkpoint_id` in the config. | 13 |
| Token | A small piece of text (roughly a word) that an LLM produces one at a time. | 15 |
| `@tool` | The decorator that turns a function into a tool; its docstring and type hints become the description and arguments. | 18 |
| Tool | A function an LLM can ask to run, with a name, a description and typed arguments. | 18 |
| Tool call | A request inside an `AIMessage` to run one tool, with a `name`, `args` and `id`. | 18 |
| `tool_call_id` | The ID linking a `ToolMessage` to the tool call it answers. | 18 |
| `ToolMessage` | The reply to a tool call, holding the result and the matching `tool_call_id`. | 18 |
| `ToolNode` | A ready-made node that runs the tool calls in the last message. | 18 |
| `tools_condition` | A ready-made router: `"tools"` if the last message has tool calls, otherwise `END`. | 18 |
| Type hint | A note like `: float` saying what type a value should be; Python does not check it at run time. | 02 |
| `TypedDict` | A dict with named, typed keys; the default way to write a LangGraph state schema. | 02 |
| `update_state` | Writes a new checkpoint by hand, as if a node returned those values (reducers apply). | 13 |
| Validation | Checking values against their types, converting them where safe and rejecting them otherwise. | 02 |
| `xray=True` | `get_graph(xray=True)` draws the inside of subgraphs too. | 16 |
