import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import DATETIME

ModelBase = declarative_base()


class LogAction(ModelBase):
    __tablename__ = 'log_action'
    id = sa.Column(sa.Integer, primary_key=True)

    datetime = sa.Column(DATETIME(fsp=3), index=True)
    level = sa.Column(sa.String(20), index=True)
    thread_id = sa.Column(sa.String(50), index=True)
    logger = sa.Column(sa.String(255), index=True)
    type = sa.Column(sa.String(50), index=True)
    change = sa.Column(sa.Integer, index=True)
    patchset = sa.Column(sa.Integer, index=True)
    queue = sa.Column(sa.Text())
    pipeline = sa.Column(sa.String(50), index=True)
    project = sa.Column(sa.String(255), index=True)
    change_item = sa.Column(sa.String(50), index=True)
    queue_item = sa.Column(sa.String(50), index=True)
    text = sa.Column(sa.Text())


class LogDuration(ModelBase):
    __tablename__ = 'log_duration'
    id = sa.Column(sa.Integer, primary_key=True)
    changeset = sa.Column(sa.String(50), index=True)
    kind = sa.Column(sa.String(20), index=True)
    start_time = sa.Column(DATETIME(fsp=3), index=True)
    duration_ms = sa.Column(sa.Integer)
    merge_time = sa.Column(DATETIME(fsp=3), index=True)
    duration_lm = sa.Column(sa.Integer)
    launch_time = sa.Column(DATETIME(fsp=3), index=True)
    duration_fl = sa.Column(sa.Integer)
    finish_time = sa.Column(DATETIME(fsp=3), index=True)
    begin_id = sa.Column(sa.Integer, index=True)
    finish_id = sa.Column(sa.Integer, index=True)
    status = sa.Column(sa.String(255))
    change_item = sa.Column(sa.String(50), index=True)
