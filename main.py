import asyncio
import sys

import click
from prometheus_client import start_http_server, Gauge, Enum

from AppDMetrics import AppDMetrics
from util.click_utils import coro
from util.logging_utils import init_logging


@click.command()
@click.option("-c", "--concurrent-connections", type=int)
@click.option("-d", "--debug", is_flag=True)
@click.option("-p", "--port", type=int, default=9877)
@click.option("-j", "--job-file", default="DefaultJob")
@click.option("-m", "--mapping-file", default="DefaultMapping")
@coro
async def main(concurrent_connections: int, debug: bool, port: int, job_file: str, mapping_file: str):
    init_logging(debug)
    app_metrics = AppDMetrics(concurrent_connections, job_file, mapping_file)
    start_http_server(port=port)
    await app_metrics.run_metrics_loop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
