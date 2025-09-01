import argparse
import logging
import os
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    TypedDict,
)

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.prompts.base import Message, UserMessage
from pydantic import Field
from taosrest import RestClient

from .template import get_prompt_template

logger = logging.getLogger(__name__)


NOT_ALLOWED_TAOS_SQL: Tuple = (
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "INSERT",
    "UPDATE",
    "TRIM",
    "FLUSH",
    "BALANCE",
    "REDISTRIBUTE",
    "GRANT",
    "REVOKE",
    "RESET",
    "KILL",
    "COMPACT",
)


class TaosSqlResponse(TypedDict):
    """The response from the TDengine database.

    TaosV2: The response format below is from TDengine V2.
    TaosV3: The `status` and `head` fields will be removed from the response, and a `code` field will be added
    """

    status: str
    head: List[str]
    # Column（string）、Column type（string）、Column length（int）
    column_meta: List[List[str | int]]
    data: List[List[Any]]
    rows: int


class TaosConfig(TypedDict):
    """TDengine configuration"""

    host: str
    port: int
    username: str
    password: str
    database: str
    timeout: int


class TAOSClient:
    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.timeout = timeout

        self.client: RestClient = next(self.init_db())

    def init_db(self) -> Generator[RestClient, None, None]:
        _url = f"http://{self.host}:{self.port}"
        try:
            client = RestClient(
                url=_url,
                user=self.username,  # type: ignore
                password=self.password,  # type: ignore
                database=self.database,  # type: ignore
                timeout=self.timeout,  # type: ignore
            )
            logger.info("Have initialized the taos client.")
            yield client
        except Exception as e:
            logger.error(
                f"Failed to connect to taos db => url: {_url}, host: {self.host}, username: {self.username}, database: {self.database}"
            )
            raise e

    def execute_sql(self, sql_stmt: str) -> TaosSqlResponse:
        """Execute SQL query and return the result."""

        logger.debug(f"Received TaosSQL statement: {sql_stmt}")
        validate_sql_stmt(sql_stmt)

        try:
            result = self.client.sql(sql_stmt)

            return TaosSqlResponse(
                status=result.get("status", ""),
                # https://docs.taosdata.com/2.6/reference/rest-api/#http-%E8%BF%94%E5%9B%9E%E6%A0%BC%E5%BC%8F
                # head可能会在后续版本移除, 当前版本2还能使用, 官方推荐使用column_meta
                head=result.get("head", []),
                column_meta=result.get("column_meta", []),
                data=result.get("data", []),
                rows=result.get("rows", -1),
            )
        except Exception as e:
            logger.error(f"Failed to execute SQL statement: {sql_stmt}")
            raise e


class TaosContext:
    def __init__(self, client: TAOSClient):
        self.client = client


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[TaosContext]:
    """Manage application lifecycle for TDengine client."""

    config = server.config

    try:
        yield TaosContext(TAOSClient(**config))
    finally:
        pass


def validate_sql_stmt(sql_stmt: str):
    """Check if the SQL statement is allowed."""

    logger.debug(f"Received TaosSQL statement: {sql_stmt}")
    sql_stmt = sql_stmt.strip()
    if sql_stmt.upper().startswith(NOT_ALLOWED_TAOS_SQL):
        logger.warning(
            f"Only isReadOnly statements are allowed. Received: {sql_stmt}"
        )
        raise ValueError(
            "Security restrictions: Only read-only statements such as queries are allowed to be executed. All other operations are prohibited."
        )


def get_taos_config(args: argparse.Namespace) -> TaosConfig:
    """Retrieve the configuration for the TDengine database."""

    logger.debug("Retrieving TDengine configuration...")
    return {
        "host": os.environ.get("TDENGINE_HOST", args.taos_host),
        "port": os.environ.get("TDENGINE_PORT", args.taos_port),
        "username": os.environ.get("TDENGINE_USERNAME", args.taos_username),
        "password": os.environ.get("TDENGINE_PASSWORD", args.taos_password),
        "database": os.environ.get("TDENGINE_DATABASE", args.taos_database),
        "timeout": int(os.environ.get("TDENGINE_TIMEOUT", args.taos_timeout)),
    }


def register_tools(mcp: FastMCP):
    """Register tools for the FastMCP application."""

    @mcp.tool(name="test_table_exists")
    def test_table_exists(
        ctx: Context,
        stable_name: str = Field(description="The name of the stable"),
    ) -> Dict[str, bool]:
        """**Important**: Check if the `stable` exists in the current `Taos database(涛思数据库)` configuration.

        Args:
            stable_name (str): The name of the stable.

        Returns:
            Dict: The `stable_name` exists or not in the current Taos configuration. If the `stable_name` does not exist, an empty dictionary is returned.

            The key of the dictionary is the `stable_name` name, and the value is a boolean indicating whether the `stable_name` exists.
        """

        taos = ctx.request_context.lifespan_context.client
        query = f"SHOW STABLES LIKE '{stable_name}'"
        result = taos.execute_sql(query)
        return {stable_name: bool(result)}

    @mcp.tool(name="get_all_dbs")
    def get_all_dbs(ctx: Context) -> TaosSqlResponse:
        """Get all databases.

        Returns:
            TaosSqlResponse: All databases in the current Taos configuration.
        """

        taos = ctx.request_context.lifespan_context.client
        result = taos.execute_sql("SHOW DATABASES;")

        return result

    @mcp.tool(name="get_all_stables")
    def get_all_stables(
        ctx: Context,
        db_name: Optional[str] = Field(
            None,
            description="The name of the database. Default is None which means the configured database.",
        ),
    ) -> TaosSqlResponse:
        """Get all stables.

        Args:
            db_name (Optional[str]): The name of the database. Defaults to None. When the value is None, it means the configured database is used.

        Returns:
            TaosSqlResponse: All stables in the current Taos database.
        """

        taos = ctx.request_context.lifespan_context.client
        if db_name is None or db_name == "":
            db_name = taos.database

        result = taos.execute_sql(f"SHOW {db_name}.STABLES;")

        return result

    @mcp.tool(name="switch_db")
    def switch_db(
        ctx: Context,
        db_name: str = Field(
            description="The name of the database to switch to"
        ),
    ) -> TaosSqlResponse:
        """Switch to the specified database.

        Args:
            db_name (str): The name of the database to switch to.

        Returns:
            TaosSqlResponse: The result of the `USE` command.
        """

        taos = ctx.request_context.lifespan_context.client
        result = taos.execute_sql(f"USE {db_name};")

        return result

    @mcp.tool(name="get_field_infos")
    def get_field_infos(
        ctx: Context,
        db_name: Optional[str] = Field(
            None,
            description="The name of the database. Default is None which means the configured database.",
        ),
        stable_name: str = Field(description="The name of the stable"),
    ) -> TaosSqlResponse:
        """Get the field information of the specified stable.

        Args:
            db_name (Optional[str]): The name of the database. Defaults to None. When the value is None, it means the configured database is used.
            stable_name (str): The name of the stable.

        Returns:
            TaosSqlResponse: The field information of the specified stable.
        """

        taos = ctx.request_context.lifespan_context.client
        if db_name is None or db_name == "":
            db_name = taos.database

        result = taos.execute_sql(f"DESCRIBE {db_name}.{stable_name};")

        return result

    @mcp.tool(name="query_taos_db_data")
    def query_taos_db_data(
        ctx: Context,
        sql_stmt: str = Field(
            description="The sql statement you want to retrieve data from taos db"
        ),
    ) -> TaosSqlResponse:
        """**Important**: Run a read-only SQL query on `Taos database(涛思数据库)`.

        Args:
            sql_stmt (str): The sql statement you want to retrieve data from taos db.

        Returns:
            List: All data from the specified table.

        """

        taos = ctx.request_context.lifespan_context.client
        return taos.execute_sql(sql_stmt)  # type: ignore


def register_resources(mcp: FastMCP):
    taos = TAOSClient(**mcp.config)

    @mcp.resource("taos://database", mime_type="text/plain")
    def get_current_taos_database() -> List:
        """Get current mysql database."""

        result = taos.execute_sql("SHOW DATABASES;")
        return result.get("data", [])

    @mcp.resource("taos://schemas", mime_type="application/json")
    def get_current_db_all_taos_schema() -> Dict[str, Any]:
        """Provide all schema in the current database."""

        schema = {}
        stables = taos.execute_sql("SHOW STABLES;")

        for stable in stables["data"]:
            if stable:
                stable_name = stable[0]
                column = taos.execute_sql(f"DESCRIBE {stable_name};")
                logger.debug(f"{stable_name} - Field meta: {column}")

                data = column.get("data", [])
                column_meta = column.get("column_meta", [])

                # Retrieve the meta definition information of the field
                table_column_meta = [meta[0] for meta in column_meta]
                table_schema = []

                # Combine the field information and the actual field data
                for d in data:
                    table_schema.append(dict(zip(table_column_meta, d)))

                schema[stable_name] = table_schema

        return schema


def register_prompts(mcp: FastMCP):
    @mcp.prompt()
    def taos_query() -> str:
        """A guide to steer llm how to query Taos(涛思) database."""

        return get_prompt_template("prompt")

    @mcp.prompt()
    def describe_query_prompt(
        query: str = Field(description="The SQL query string"),
    ) -> List[Message]:
        """
        Generate a prompt to ask an LLM to explain what a given SQL query does.

        Args:
            query: The SQL query string.

        Returns:
            A list containing a prompt message to explain the query.
        """

        logger.debug(f"Entering describe_query_prompt() with query: {query}")
        prompt_text = (
            f"Explain the following SQL query:\n\n{query}\n\n"
            "Describe what data it retrieves and suggest any potential improvements."
        )
        logger.debug(f"Generated describe_query_prompt text: {prompt_text}")
        result = [UserMessage(prompt_text)]
        logger.debug("Exiting describe_query_prompt()")
        return result  # type: ignore


def parse_arguments():
    parser = argparse.ArgumentParser(description="TDengine MCP Server")
    parser.add_argument(
        "-th",
        "--taos-host",
        type=str,
        default="localhost",
        help="TDengine host address. Default: `%(default)s`",
    )
    parser.add_argument(
        "-tp",
        "--taos-port",
        type=int,
        default=6041,
        help="TDengine port number. Default: `%(default)d`",
    )
    parser.add_argument(
        "-tu",
        "--taos-username",
        type=str,
        default="root",
        help="TDengine username. Default: `%(default)s`",
    )
    parser.add_argument(
        "-pwd",
        "--taos-password",
        type=str,
        default="taosdata",
        help="TDengine password. Default: `%(default)s`",
    )
    parser.add_argument(
        "-db",
        "--taos-database",
        type=str,
        default="default",
        help="TDengine database name. Default: `%(default)s`",
    )
    parser.add_argument(
        "-to",
        "--taos-timeout",
        type=int,
        default=30,
        help="TDengine connection timeout. Default: `%(default)d`",
    )
    parser.add_argument(
        "-ll",
        "--log-level",
        type=str,
        default="INFO",
        help="Log level. Default: `%(default)s`",
    )
    parser.add_argument(
        "-trans",
        "--transport",
        type=str,
        choices=["sse", "stdio", "http"],
        default="sse",
        help="The transport to use. Default: `%(default)s`",
    )

    return parser.parse_args()


def main():
    # Initialize the Taos client
    load_dotenv()
    args = parse_arguments()

    # Set up logging. You can adjust the log level as needed. But the environment variable LOG_LEVEL has higher priority.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", args.log_level).upper(),
        format="%(asctime)s - %(module)s.%(funcName)s:%(lineno)d - | %(levelname)s | - %(message)s",
    )

    _transort = os.environ.get("TRANSPORT", args.transport)
    _transport_is_http = _transort == "http"
    if _transport_is_http:
        _transort = "streamable-http"

    mcp_app = FastMCP(
        name="[TDengine-MCP-Server]",
        instructions="TDengine-MCP-Server",
        lifespan=server_lifespan,
        dependencies=["dotenv", "taospy"],
        json_response=True if _transport_is_http else False,
        stateless_http=True if _transport_is_http else False,
    )
    mcp_app.config = get_taos_config(args)  # type: ignore

    for register_func in (register_prompts, register_tools, register_resources):
        register_func(mcp_app)

    logger.info(
        f"[TDengine-MCP-Server] server started with transport: {_transort}"
    )
    mcp_app.run(transport=_transort)  # type: ignore
