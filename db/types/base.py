from enum import Enum

from sqlalchemy import create_engine, text

from db import constants

from typing import Optional, Sequence, Collection

import inspect


class DatabaseType:

    value: str

    @property
    def id(self) -> str:
        """
        Here we're defining Enum's value attribute to be the database type id.
        """
        return self.value

    def get_sa_class(self, engine):
        """
        Returns the SA class corresponding to this type or None if this type is not supported by
        provided engine, or if it's ignored (see is_ignored).
        """
        if not self.is_ignored:
            ischema_names = engine.dialect.ischema_names
            return ischema_names.get(self.id)

    def is_available(self, engine, type_ids_on_database:Collection[str]=None) -> bool:
        """
        Returns true if this type is available on provided engine's database. For the sake of
        optimizing IO, the result of _get_type_ids_on_database(engine) may be passed as the
        type_ids_on_database parameter.
        """
        if type_ids_on_database is None:
            type_ids_on_database = _get_type_ids_on_database(engine)
        is_type_in_database = self.id in type_ids_on_database
        return is_type_in_database

    def get_sa_instance_compiled(self, engine, type_options={}):
        sa_class = self.get_sa_class(engine)
        if sa_class:
            dialect = engine.dialect
            instance = sa_class(**type_options)
            return instance.compile(dialect=dialect)

    @property
    def is_alias(self) -> bool:
        return self in _non_canonical_alias_db_types

    @property
    def is_sa_only(self) -> bool:
        return self in _sa_only_db_types

    @property
    def is_optional(self) -> bool:
        return self in _optional_db_types

    @property
    def is_inconsistent(self) -> bool:
        return self in _inconsistent_db_types

    @property
    def is_ignored(self) -> bool:
        """
        We ignore some types. Current rule is that if type X is applied to a column, but upon
        reflection that column is of some other type, we ignore type X. This mostly means
        ignoring aliases. It also ignores NAME and CHAR, because both are reflected as the SA
        String type.
        """
        return self in _inconsistent_db_types

    @property
    def is_reflection_supported(self) -> bool:
        return not self.is_inconsistent

    @property
    def is_application_supported(self) -> bool:
        return not self.is_inconsistent and not _sa_only_db_types


class PostgresType(DatabaseType, Enum):
    """
    This only includes built-in Postgres types that SQLAlchemy supports.
    SQLAlchemy doesn't support XML. See zzzeek's comment on:
    https://stackoverflow.com/questions/16153512/using-postgresql-xml-data-type-with-sqlalchemy
    The values are keys returned by get_available_types.
    """
    _ARRAY = '_array'
    BIGINT = 'bigint'
    BIT_VARYING = 'bit varying'
    BIT = 'bit'
    BOOLEAN = 'boolean'
    BYTEA = 'bytea'
    CHAR = '"char"'
    CHARACTER_VARYING = 'character varying'
    CHARACTER = 'character'
    CIDR = 'cidr'
    DATE = 'date'
    DATERANGE = 'daterange'
    DOUBLE_PRECISION = 'double precision'
    FLOAT = 'float'
    HSTORE = 'hstore'
    INET = 'inet'
    INT4RANGE = 'int4range'
    INT8RANGE = 'int8range'
    INTEGER = 'integer'
    INTERVAL = 'interval'
    JSON = 'json'
    JSONB = 'jsonb'
    MACADDR = 'macaddr'
    MONEY = 'money'
    NAME = 'name'
    NUMERIC = 'numeric'
    NUMRANGE = 'numrange'
    OID = 'oid'
    REAL = 'real'
    REGCLASS = 'regclass'
    SMALLINT = 'smallint'
    TEXT = 'text'
    TIME = 'time'
    TIME_WITH_TIME_ZONE = 'time with time zone'
    TIME_WITHOUT_TIME_ZONE = 'time without time zone'
    TIMESTAMP = 'timestamp'
    TIMESTAMP_WITH_TIME_ZONE = 'timestamp with time zone'
    TIMESTAMP_WITHOUT_TIME_ZONE = 'timestamp without time zone'
    TSRANGE = 'tsrange'
    TSTZRANGE = 'tstzrange'
    TSVECTOR = 'tsvector'
    UUID = 'uuid'


SCHEMA = f"{constants.MATHESAR_PREFIX}types"
# Since we want to have our identifiers quoted appropriately for use in
# PostgreSQL, we want to use the postgres dialect preparer to set this up.
preparer = create_engine("postgresql://").dialect.identifier_preparer


# Should usually equal `mathesar_types`
_ma_type_qualifier_prefix = preparer.quote_schema(SCHEMA)


# TODO rename to get_qualified_mathesar_obj_name
# it's not only used for types. it's also used for qualifying sql function ids
def get_qualified_name(unqualified_name):
    return ".".join([_ma_type_qualifier_prefix, unqualified_name])


# TODO big misnomer!
# we already have a concept of Mathesar types (UI types) in the mathesar namespace.
# maybe rename to just CustomType?
# also, note that db layer should not be aware of Mathesar
class MathesarCustomType(DatabaseType, Enum):
    """
    This is a list of custom Mathesar DB types.
    """
    EMAIL = 'email'
    MATHESAR_MONEY = 'mathesar_money'
    MULTICURRENCY_MONEY = 'multicurrency_money'
    URI = 'uri'

    def __new__(cls, unqualified_id):
        """
        Prefixes a qualifier to this Enum's values.
        `email` becomes something akin to `mathesar_types.email`.
        """
        qualified_id = get_qualified_name(unqualified_id)
        instance = object.__new__(cls)
        instance._value_ = qualified_id
        return instance


_non_canonical_alias_db_types = frozenset({
    PostgresType.FLOAT,
    PostgresType.TIME,
    PostgresType.TIMESTAMP,
})


_inconsistent_db_types = frozenset.union(
    _non_canonical_alias_db_types,
    frozenset({
        PostgresType.NAME,
        PostgresType.CHAR,
        PostgresType.BIT_VARYING,
    }),
)


_sa_only_db_types = frozenset({
    PostgresType._ARRAY,
})


_optional_db_types = frozenset({
    PostgresType.HSTORE,
})


_known_vanilla_db_types = frozenset(postgres_type for postgres_type in PostgresType)


_known_custom_db_types = frozenset(mathesar_custom_type for mathesar_custom_type in MathesarCustomType)


# Known database types are those that are defined on our PostgresType and MathesarCustomType Enums.
known_db_types = frozenset.union(_known_vanilla_db_types, _known_custom_db_types)


# Origin: https://www.python.org/dev/peps/pep-0616/#id17
def _remove_prefix(self, prefix, /):
    """
    This will remove the passed prefix, if it's there.
    Otherwise, it will return the string unchanged.
    """
    if self.startswith(prefix):
        return self[len(prefix):]
    else:
        return self[:]


def get_db_type_enum_from_id(db_type_id) -> Optional[DatabaseType]:
    """
    Gets an instance of either the PostgresType enum or the MathesarCustomType enum corresponding
    to the provided db_type_id. If the id doesn't correspond to any of the mentioned enums,
    returns None.
    """
    try:
        return PostgresType(db_type_id)
    except ValueError:
        try:
            return MathesarCustomType(db_type_id)
        except ValueError:
            return None


# TODO improve name; currently its weird names serves to distinguish it from similarly named
# methods throughout the codebase; should be renamed at earliest convenience.
def get_available_known_db_types(engine) -> Sequence[DatabaseType]:
    """
    Returns a tuple of DatabaseType instances that are available on provided engine.
    """
    type_ids_on_database = _get_type_ids_on_database(engine)
    return tuple(
        db_type
        for db_type in known_db_types
        if db_type.is_available(
            engine,
            type_ids_on_database=type_ids_on_database,
        )
    )


def get_db_type_enum_from_class(sa_type, engine) -> DatabaseType:
    if not inspect.isclass(sa_type):
        # Instead of extracting classes from instances, we're supporting a single type of parameter
        # and failing early so that the codebase is more homogenous.
        raise Exception("Programming error: sa_type parameter must be a class, not an instance.")
    db_type_id = _sa_type_class_to_db_type_id(sa_type, engine)
    if db_type_id:
        db_type = get_db_type_enum_from_id(db_type_id)
        if db_type:
            return db_type
    raise Exception("We don't know how to map this type class to a DatabaseType Enum.")


def _sa_type_class_to_db_type_id(sa_type_class, engine) -> Optional[str]:
    return _get_sa_type_class_id_from_ischema_names(sa_type_class, engine)


def _get_sa_type_class_id_from_ischema_names(sa_type_class1, engine) -> Optional[str]:
    for db_type_id, sa_type_class2 in engine.dialect.ischema_names.items():
        if sa_type_class1 == sa_type_class2:
            return db_type_id


def _compile_sa_class(sa_class, engine):
    try:
        return sa_class.compile(dialect=engine.dialect)
    except TypeError:
        return sa_class().compile(dialect=engine.dialect)


def _get_type_ids_on_database(engine) -> Collection[str]:
    """
    Returns db type ids available on the database.
    """
    # Adapted from the SQL expression produced by typing `\dT *` in psql.
    select_statement = text(
        "SELECT\n"
        "  pg_catalog.format_type(t.oid, NULL) AS \"Name\"\n"
        " FROM pg_catalog.pg_type t\n"
        "      LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace\n"
        " WHERE (t.typrelid = 0 OR (SELECT c.relkind = 'c' FROM pg_catalog.pg_class c WHERE c.oid = t.typrelid))\n"
        "   AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_type el WHERE el.oid = t.typelem AND el.typarray = t.oid);"
    )
    with engine.connect() as connection:
        db_type_ids = frozenset(
            db_type_id
            for db_type_id,
            in connection.execute(select_statement)
        )
        return db_type_ids
