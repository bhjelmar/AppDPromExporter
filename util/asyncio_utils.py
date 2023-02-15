import asyncio
import logging


class AsyncioUtils:
    concurrent_connections = 50

    @staticmethod
    def init(concurrent_connections: int = 50):
        if concurrent_connections > 100:
            logging.warning(f"Concurrent connections ({concurrent_connections}) is too high. Setting to 100.")
            concurrent_connections = 100
        elif concurrent_connections < 1:
            logging.warning(f"Concurrent connections ({concurrent_connections}) is too low. Setting to 1.")
            concurrent_connections = 1
        else:
            logging.info(f"Setting concurrent connections to {concurrent_connections}.")
        AsyncioUtils.concurrent_connections = concurrent_connections

    @staticmethod
    async def gatherWithConcurrency(*tasks):
        semaphore = asyncio.Semaphore(AsyncioUtils.concurrent_connections)

        async def semTask(task):
            async with semaphore:
                return await task

        return await asyncio.gather(*[semTask(task) for task in tasks])

    @staticmethod
    async def sleep(seconds_to_sleep):
        await asyncio.sleep(seconds_to_sleep)
