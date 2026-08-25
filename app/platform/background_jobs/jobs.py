"""
Background Jobs infrastructure.

Defines BackgroundJob base class, JobQueue, and BackgroundJobRunner.
Uses asyncio.Queue for safe in-process queuing.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundJob(ABC):
    """
    Abstract base class representing a unit of background work.
    """

    @abstractmethod
    async def run(self) -> None:
        """
        Execute the job payload asynchronously.
        """
        pass


class JobQueue:
    """
    Thread-safe, async in-process FIFO queue for background jobs.
    """

    def __init__(self) -> None:
        """
        Initialize the queue.
        """
        self._queue: asyncio.Queue[BackgroundJob] = asyncio.Queue()

    async def enqueue(self, job: BackgroundJob) -> None:
        """
        Add a job to the end of the queue.
        """
        await self._queue.put(job)
        logger.debug("Enqueued background job: %s", job.__class__.__name__)

    async def dequeue(self) -> BackgroundJob:
        """
        Pop and return the next job from the queue. Blocks if empty.
        """
        return await self._queue.get()

    def task_done(self) -> None:
        """
        Notify the queue that a previously enqueued task is completed.
        """
        self._queue.task_done()

    def size(self) -> int:
        """
        Return current approximate queue size.
        """
        return self._queue.qsize()


class BackgroundJobRunner:
    """
    Manages a pool of async worker tasks to process enqueued background jobs.
    """

    def __init__(self, queue: JobQueue, max_workers: int = 5) -> None:
        """
        Initialize runner with target queue and worker pool size.
        """
        self._queue = queue
        self._max_workers = max_workers
        self._workers: list[asyncio.Task] = []
        self._running = False

    def start(self) -> None:
        """
        Start the background worker tasks.
        """
        if self._running:
            return
        self._running = True
        logger.info("Starting BackgroundJobRunner with %d workers.", self._max_workers)
        
        for idx in range(self._max_workers):
            task = asyncio.create_task(
                self._worker_loop(idx),
                name=f"background-worker-{idx}"
            )
            self._workers.append(task)

    async def stop(self) -> None:
        """
        Stop worker loops and cancel active tasks cleanly.
        """
        if not self._running:
            return
        self._running = False
        logger.info("Stopping BackgroundJobRunner workers...")
        
        for task in self._workers:
            task.cancel()
            
        # Await clean termination of tasks
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("BackgroundJobRunner workers stopped successfully.")

    async def _worker_loop(self, worker_id: int) -> None:
        """
        The execution loop for an individual background worker.
        """
        logger.debug("Worker loop started for worker ID: %d", worker_id)
        while self._running:
            try:
                job = await self._queue.dequeue()
                logger.info("Worker %d processing job: %s", worker_id, job.__class__.__name__)
                
                try:
                    await job.run()
                    logger.info("Worker %d completed job: %s", worker_id, job.__class__.__name__)
                except Exception as ex:
                    logger.error(
                        "Worker %d failed to execute job: %s. Error: %s",
                        worker_id,
                        job.__class__.__name__,
                        ex,
                        exc_info=True
                    )
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.debug("Worker %d task loop cancelled.", worker_id)
                break
            except Exception as e:
                logger.error("Worker %d encountered error in dispatch loop: %s", worker_id, e, exc_info=True)
                await asyncio.sleep(1)  # Throttle on loop-level error
