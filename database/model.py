import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import DATETIME, TINYINT


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
    job = sa.Column(sa.String(255), index=True)
    change_item = sa.Column(sa.String(50), index=True)
    queue_item = sa.Column(sa.String(50), index=True)
    text = sa.Column(sa.Text())


def get_log_duration_model(table_name):
    DynamicBase = declarative_base(class_registry=dict())

    class LogDuration(DynamicBase):
        __tablename__ = table_name
        id = sa.Column(sa.Integer, primary_key=True)
        changeset = sa.Column(sa.String(50), index=True)
        kind = sa.Column(sa.String(20), index=True)
        project = sa.Column(sa.String(255), index=True)
        squad = sa.Column(sa.String(255), index=True)
        start_time = sa.Column(DATETIME(fsp=3), index=True)
        merge_time = sa.Column(DATETIME(fsp=3), index=True)
        merged_time = sa.Column(DATETIME(fsp=3), index=True)
        launch_time = sa.Column(DATETIME(fsp=3), index=True)
        launched_time = sa.Column(DATETIME(fsp=3), index=True)
        completed_time = sa.Column(DATETIME(fsp=3), index=True)
        finish_time = sa.Column(DATETIME(fsp=3), index=True)
        begin_id = sa.Column(sa.Integer, index=True)
        finish_id = sa.Column(sa.Integer, index=True)
        status = sa.Column(sa.String(255))
        change_item = sa.Column(sa.String(50), index=True)
        queue_item = sa.Column(sa.String(50), index=True)
        result = sa.Column(TINYINT, index=True)

    return LogDuration


class LogDuration(ModelBase):
    __tablename__ = 'log_duration'
    id = sa.Column(sa.Integer, primary_key=True)
    changeset = sa.Column(sa.String(50), index=True)
    kind = sa.Column(sa.String(20), index=True)
    project = sa.Column(sa.String(255), index=True)
    squad = sa.Column(sa.String(255), index=True)
    start_time = sa.Column(DATETIME(fsp=3), index=True)
    merge_time = sa.Column(DATETIME(fsp=3), index=True)
    merged_time = sa.Column(DATETIME(fsp=3), index=True)
    launch_time = sa.Column(DATETIME(fsp=3), index=True)
    launched_time = sa.Column(DATETIME(fsp=3), index=True)
    completed_time = sa.Column(DATETIME(fsp=3), index=True)
    finish_time = sa.Column(DATETIME(fsp=3), index=True)
    begin_id = sa.Column(sa.Integer, index=True)
    finish_id = sa.Column(sa.Integer, index=True)
    status = sa.Column(sa.String(255))
    change_item = sa.Column(sa.String(50), index=True)
    queue_item = sa.Column(sa.String(50), index=True)
    result = sa.Column(TINYINT, index=True)
