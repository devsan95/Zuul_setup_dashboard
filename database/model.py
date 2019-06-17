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

    class LogDurationAlt(DynamicBase):
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

    return LogDurationAlt


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
        dequeue_duration = Column(BIGINT)
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


def get_reschedule_statistics_model(table_name='t_reschedule_statistics'):
    DynamicBase = declarative_base(class_registry=dict())
    from sqlalchemy import Column, BIGINT, String, TIMESTAMP

    class TRescheduleStatistic(DynamicBase):
        __tablename__ = table_name

        id = Column(BIGINT, primary_key=True)
        change = sa.Column(sa.Integer, index=True)
        patchset = sa.Column(sa.Integer, index=True)
        queue_item = Column(String(50), nullable=False, index=True)
        pipeline = Column(String(50), nullable=False)
        project = Column(String(100))
        branch = Column(String(100))
        begin_id = Column(BIGINT)
        finish_id = Column(BIGINT, index=True)
        item_finish_id = Column(BIGINT, index=True)
        start_time = Column(TIMESTAMP)
        end_time = Column(TIMESTAMP)
        duration = Column(BIGINT)
        status = Column(String(50))
        c_change = sa.Column(sa.Integer, index=True)
        c_patchset = sa.Column(sa.Integer, index=True)
        c_queue_item = Column(String(50), nullable=True, index=True)
        c_project = Column(String(100))
        c_branch = Column(String(100))
        c_status = Column(String(50))
        c_job = Column(String(2560))
        c_job_status = Column(String(255))
        c_end_time = Column(TIMESTAMP)
        c_finish_id = Column(BIGINT, index=True)
        reschedule_reason = Column(String(50))

    return TRescheduleStatistic


class ZuulBuild(ModelBase):
    __tablename__ = 'zuul_build'

    id = sa.Column(sa.Integer, primary_key=True)
    buildset_id = sa.Column(sa.Integer, nullable=True)
    uuid = sa.Column(sa.String(36), nullable=True)
    job_name = sa.Column(sa.String(255), nullable=True)
    result = sa.Column(sa.String(255), nullable=True)
    start_time = sa.Column(sa.DateTime, nullable=True)
    end_time = sa.Column(sa.DateTime, nullable=True)
    voting = sa.Column(TINYINT, nullable=True)
    log_url = sa.Column(sa.Text, nullable=True)
    node_name = sa.Column(sa.String(255), nullable=True)
    datetime = sa.Column(sa.DateTime, nullable=True)
    queue_item = sa.Column(sa.String(255), nullable=True)


class ZuulBuildset(ModelBase):
    __tablename__ = 'zuul_buildset'

    id = sa.Column(sa.Integer, primary_key=True)
    zuul_ref = sa.Column(sa.String(255), nullable=True)
    pipeline = sa.Column(sa.String(255), nullable=True)
    project = sa.Column(sa.String(255), nullable=True)
    change = sa.Column(sa.String(255), nullable=True)
    patchset = sa.Column(sa.String(255), nullable=True)
    ref = sa.Column(sa.String(255), nullable=True)
    score = sa.Column(sa.String(255), nullable=True)
    message = sa.Column(sa.String(255), nullable=True)
    datetime = sa.Column(sa.String(255), nullable=True)


def get_loop_action_model(table_name='loop_action'):
    DynamicBase = declarative_base(class_registry=dict())

    class LoopAction(DynamicBase):
        __tablename__ = table_name
        id = sa.Column(sa.Integer, primary_key=True)

        begintime = sa.Column(DATETIME(fsp=3), index=True)
        endtime = sa.Column(DATETIME(fsp=3), index=True)
        duration = sa.Column(sa.Integer, index=False)
        thread_id = sa.Column(sa.String(50), index=False)
        logger = sa.Column(sa.String(255), index=True)
        action = sa.Column(sa.String(50), index=True)
        detail = sa.Column(sa.Text(), index=False)
        result = sa.Column(sa.Text(), index=False)

    return LoopAction


class IntegrationRefs(ModelBase):
    __tablename__ = 't_integration_refs'

    id = sa.Column(sa.Integer, primary_key=True)
    zuul_ref = sa.Column(sa.String(255), nullable=True)
    project = sa.Column(sa.String(255), nullable=True)
    zuul_url = sa.Column(sa.String(255), nullable=True)
    date = sa.Column(sa.String(255), nullable=True)
