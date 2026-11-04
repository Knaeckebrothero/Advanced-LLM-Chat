"""
MCP servers for the agents (docs/mcp.md).

- store.py: the tables (servers, OAuth tokens, sign-ins in progress)
- servers.py: validation, the API views and the resolved definitions the client connects with
- pool.py: connections to the servers, kept per server and user
- oauth.py: OAuth sign-in and the tokens of a connection
- tools.py: the tools of an answer, and the test of a server
"""
