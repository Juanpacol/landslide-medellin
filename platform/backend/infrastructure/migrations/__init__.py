"""Estado de las migraciones de Alembic: repo vs. base de datos.

`alembic_state` hace el I/O (lee `alembic/versions/` y la tabla
`alembic_version`); `diagnosis` clasifica el resultado con una función pura.
La separación es lo que permite testear la lógica sin BD.
"""
