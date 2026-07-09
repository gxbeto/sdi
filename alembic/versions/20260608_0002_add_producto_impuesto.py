"""add producto impuesto

Revision ID: 20260608_0002
Revises: 20260504_0001
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260608_0002"
down_revision: str | None = "20260504_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "productos",
        sa.Column(
            "impuesto",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )
    op.create_check_constraint(
        "chk_producto_impuesto_rango",
        "productos",
        "impuesto >= 0 AND impuesto <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_producto_impuesto_rango",
        "productos",
        type_="check",
    )
    op.drop_column("productos", "impuesto")
