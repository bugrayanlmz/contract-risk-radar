import asyncio
import logging

from app.jobs.tasks import queue


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    async with queue.open_async():
        await queue.run_worker_async(concurrency=2, shutdown_graceful_timeout=20)


if __name__ == "__main__":
    asyncio.run(main())
