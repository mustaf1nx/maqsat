"""Private calendars, all-day events, richer metadata and recoverable deletion.

Additive migration: existing events stay in the default calendar, keep their
IDs/timestamps, user ownership and training links. No production credentials.
"""
from alembic import op
import sqlalchemy as sa
revision = '0003_calendar_tools'
down_revision = '0002_daily_flow'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('calendars',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('color', sa.String(7), nullable=False, server_default='#7c83ff'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_calendars_user_id', 'calendars', ['user_id'])
    with op.batch_alter_table('events') as batch:
        batch.add_column(sa.Column('calendar_id', sa.String(36), nullable=True))
        batch.add_column(sa.Column('color', sa.String(7), nullable=True))
        batch.add_column(sa.Column('all_day', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('availability', sa.String(8), nullable=False, server_default='busy'))
        batch.add_column(sa.Column('meeting_url', sa.String(2048), nullable=False, server_default=''))
        batch.add_column(sa.Column('reminders', sa.JSON(), nullable=False, server_default='[]'))
        batch.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('import_uid', sa.String(512), nullable=True))
        batch.create_foreign_key('fk_events_calendar', 'calendars', ['calendar_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_events_calendar_id', ['calendar_id'])
        batch.create_index('ix_events_deleted_at', ['deleted_at'])
        batch.create_unique_constraint('uq_event_import_uid', ['user_id','import_uid'])

def downgrade():
    with op.batch_alter_table('events') as batch:
        batch.drop_constraint('uq_event_import_uid', type_='unique')
        batch.drop_index('ix_events_calendar_id')
        batch.drop_index('ix_events_deleted_at')
        batch.drop_constraint('fk_events_calendar', type_='foreignkey')
        for name in ['calendar_id','color','all_day','availability','meeting_url','reminders','deleted_at','import_uid']:
            batch.drop_column(name)
    op.drop_index('ix_calendars_user_id', table_name='calendars')
    op.drop_table('calendars')
