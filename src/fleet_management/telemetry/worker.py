import asyncio
import logging
import signal

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import settings
from ..database import SessionLocal
from ..exceptions import NotFoundError
from .processor import save_reading, update_vehicle_state
from .schemas import TelemetryMessage

logger = logging.getLogger("telemetry.worker")
CONNECT_ATTEMPTS = 10
CONNECT_RETRY_SECONDS = 3
PREFETCH_COUNT = 50
NACK_DELAY_SECONDS = 1


async def handle_message(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
) -> None:
    try:
        telemetry = TelemetryMessage.model_validate_json(message.body)
    except ValidationError as exc:
        logger.warning("Droping invalid telemetry message: %s", exc)
        await message.reject(requeue=False)
        return

    try:
        async with session_factory() as db:
            await save_reading(db, telemetry)
        await update_vehicle_state(redis, telemetry)
    except NotFoundError as exc:
        logger.warning("Droping telemetry for unknown vehicle: %s", exc)
        await message.reject(requeue=False)
    except Exception:
        logger.exception("Failed to process telemetry, requeueing")
        await asyncio.sleep(NACK_DELAY_SECONDS)
        await message.nack(requeue=True)
    else:
        await message.ack()


async def connect_rabbitmq() -> AbstractRobustConnection:
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return await aio_pika.connect_robust(settings.rabbitmq_url)
        except OSError as exc:
            logger.warning("RabbitMQ not ready (attempt %d/%d): %s", attempt, CONNECT_ATTEMPTS, exc)
            await asyncio.sleep(CONNECT_RETRY_SECONDS)
    raise RuntimeError(f"Could not connect to RabbitMQ after {CONNECT_ATTEMPTS} attempts")


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    connection = await connect_rabbitmq()
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH_COUNT)
        queue = await channel.declare_queue(settings.telemetry_queue, durable=True)
        logger.info("Consuming queue %r", settings.telemetry_queue)

        async with queue.iterator() as messages:
            async for message in messages:
                await handle_message(message, SessionLocal, redis)

    finally:
        await connection.close()
        await redis.aclose()


def _stop(signum, frame):
    raise KeyboardInterrupt


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    signal.signal(signal.SIGTERM, _stop)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Telemetry worker stopped")


if __name__ == "__main__":
    main()
