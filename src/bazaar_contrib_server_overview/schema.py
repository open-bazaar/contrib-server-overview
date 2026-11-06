"""The order each account gave the overview's content."""

import bazaar_contrib_storage as s
from bazaar_contrib_schema import Migration, ModuleSchema

POSITIONS = s.Table(
    name="overview_positions",
    columns=(
        s.ColumnDefinition(name="account_id", type="text"),
        s.ColumnDefinition(name="key", type="text"),
        s.ColumnDefinition(name="position", type="integer"),
    ),
    primary_key=("account_id", "key"),
)

MODULE = ModuleSchema(
    tables=("overview_positions",),
    migrations=(
        Migration(
            version=1,
            name="overview_positions",
            operations=(s.CreateTable(table=POSITIONS),),
        ),
    ),
)
