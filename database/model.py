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


def get_gate_statistics_model(table_name='t_gate_statistics'):
    DynamicBase = declarative_base(class_registry=dict())
    from sqlalchemy import Column, BIGINT, String, TIMESTAMP, INTEGER

    class TGateStatistic(DynamicBase):
        __tablename__ = table_name

        id = Column(BIGINT, primary_key=True)
        changeset = Column(String(50), nullable=False, index=True)
        queue_item = Column(String(50), nullable=False, index=True)
        pipeline = Column(String(50), nullable=False)
        project = Column(String(100))
        branch = Column(String(100))
        squad = Column(String(50))
        tribe = Column(String(50))
        begin_id = Column(BIGINT)
        finish_id = Column(BIGINT, index=True)
        start_time = Column(TIMESTAMP)
        end_time = Column(TIMESTAMP)
        window_waiting_time = Column(BIGINT)
        merge_time = Column(BIGINT)
        pre_launch_time = Column(BIGINT)
        first_launch_time = Column(BIGINT)
        job_running_time = Column(BIGINT)
        total_duration = Column(BIGINT)
        reschedule_times = Column(INTEGER)
        reschedule_total_duration = Column(BIGINT)
        status = Column(String(50))
        result = Column(INTEGER)
        du_name = Column(String(50))

    return TGateStatistic


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
