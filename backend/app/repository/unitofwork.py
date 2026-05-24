from sqlalchemy.ext.asyncio import (
    async_sessionmaker, create_async_engine,
    AsyncSession
)

from app.repository.task_repository import TaskQueueRepository
from app.core.config import config


URL = "postgresql+asyncpg://" +\
      f"{config.PG_USER}:{config.PG_PASS}" +\
      "@" +\
      f"{config.PG_HOST}:{config.PG_PORT}" +\
      "/" +\
      f"{config.PG_DB}"


engine = create_async_engine(url=URL, echo=False)
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory=AsyncSessionFactory):
        self.session_factory = session_factory

    async def __aenter__(self):
        self.session = self.session_factory()
        self.task_queue = TaskQueueRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        try:
            if exc_type is not None:
                await self.session.rollback()
            else:
                await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            raise e
        finally:
            await self.session.close()


async def get_db():
    async with SqlAlchemyUnitOfWork() as uow:
        yield uow
