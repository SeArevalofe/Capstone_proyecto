from sqlalchemy import create_engine

from app.config import DATABASE_PATH


database_url = (
    "sqlite:///"
    + DATABASE_PATH.resolve().as_posix()
)


engine = create_engine(
    database_url,
    echo=False,
)