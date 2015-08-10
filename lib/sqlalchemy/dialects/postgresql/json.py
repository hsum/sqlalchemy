# postgresql/json.py
# Copyright (C) 2005-2015 the SQLAlchemy authors and contributors
# <see AUTHORS file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php
from __future__ import absolute_import

import collections
import json

from .base import ischema_names
from ... import types as sqltypes
from ...sql import operators
from ...sql import elements
from ... import util

__all__ = ('JSON', 'JSONB')


# json : returns json
INDEX = operators.custom_op(
    "->", precedence=5, natural_self_precedent=True
)

# path operator: returns json
PATHIDX = operators.custom_op(
    "#>", precedence=5, natural_self_precedent=True
)

# json + astext: returns text
ASTEXT = operators.custom_op(
    "->>", precedence=5, natural_self_precedent=True
)

# path operator  + astext: returns text
ASTEXT_PATHIDX = operators.custom_op(
    "#>>", precedence=5, natural_self_precedent=True
)


class JSON(sqltypes.Indexable, sqltypes.TypeEngine):
    """Represent the Postgresql JSON type.

    The :class:`.JSON` type stores arbitrary JSON format data, e.g.::

        data_table = Table('data_table', metadata,
            Column('id', Integer, primary_key=True),
            Column('data', JSON)
        )

        with engine.connect() as conn:
            conn.execute(
                data_table.insert(),
                data = {"key1": "value1", "key2": "value2"}
            )

    :class:`.JSON` provides several operations:

    * Index operations::

        data_table.c.data['some key']

    * Index operations returning text (required for text comparison)::

        data_table.c.data['some key'].astext == 'some value'

    * Index operations with a built-in CAST call::

        data_table.c.data['some key'].cast(Integer) == 5

    * Path index operations::

        data_table.c.data[('key_1', 'key_2', ..., 'key_n')]

    * Path index operations returning text (required for text comparison)::

        data_table.c.data[('key_1', 'key_2', ..., 'key_n')].astext == \\
            'some value'

    Index operations return an instance of :class:`.JSONElement`, which
    represents an expression such as ``column -> index``.  This element then
    defines methods such as :attr:`.JSONElement.astext` and
    :meth:`.JSONElement.cast` for setting up type behavior.

    The :class:`.JSON` type, when used with the SQLAlchemy ORM, does not
    detect in-place mutations to the structure.  In order to detect these, the
    :mod:`sqlalchemy.ext.mutable` extension must be used.  This extension will
    allow "in-place" changes to the datastructure to produce events which
    will be detected by the unit of work.  See the example at :class:`.HSTORE`
    for a simple example involving a dictionary.

    Custom serializers and deserializers are specified at the dialect level,
    that is using :func:`.create_engine`.  The reason for this is that when
    using psycopg2, the DBAPI only allows serializers at the per-cursor
    or per-connection level.   E.g.::

        engine = create_engine("postgresql://scott:tiger@localhost/test",
                                json_serializer=my_serialize_fn,
                                json_deserializer=my_deserialize_fn
                        )

    When using the psycopg2 dialect, the json_deserializer is registered
    against the database using ``psycopg2.extras.register_default_json``.

    .. versionadded:: 0.9

    """

    __visit_name__ = 'JSON'

    hashable = False

    def __init__(self, none_as_null=False, index_map=None):
        """Construct a :class:`.JSON` type.

        :param none_as_null: if True, persist the value ``None`` as a
         SQL NULL value, not the JSON encoding of ``null``.   Note that
         when this flag is False, the :func:`.null` construct can still
         be used to persist a NULL value::

             from sqlalchemy import null
             conn.execute(table.insert(), data=null())

         .. versionchanged:: 0.9.8 - Added ``none_as_null``, and :func:`.null`
            is now supported in order to persist a NULL value.

        :param index_map: type map used by the getitem operator, e.g.
         expressions like ``col[5]``.  See :class:`.Indexable` for a
         description of how this map is configured.   The index_map
         for the :class:`.JSON` and :class:`.JSONB` types defaults to
         ``{ANY_KEY: SAME_TYPE}``.

         .. versionadded: 1.1

         """
        self.none_as_null = none_as_null
        if index_map is not None:
            self.index_map = index_map

    class Comparator(
            sqltypes.Indexable.Comparator, sqltypes.Concatenable.Comparator):
        """Define comparison operations for :class:`.JSON`."""

        @property
        def astext(self):
            """On an indexed expression, use the "astext" (e.g. "->>")
            conversion when rendered in SQL.

            E.g.::

                select([data_table.c.data['some key'].astext])

            .. seealso::

                :meth:`.ColumnElement.cast`

            """
            against = self.expr.operator
            if against is PATHIDX:
                against = ASTEXT_PATHIDX
            else:
                against = ASTEXT

            return self.expr.left.operate(
                against, self.expr.right, result_type=sqltypes.Text)

        def _setup_getitem(self, index):
            if not isinstance(index, util.string_types):
                assert isinstance(index, collections.Sequence)
                index = "{%s}" % (
                    ", ".join(util.text_type(elem) for elem in index))
                operator = PATHIDX
            else:
                operator = INDEX

            return operator, index, self._type_for_index(index)

    comparator_factory = Comparator

    def bind_processor(self, dialect):
        json_serializer = dialect._json_serializer or json.dumps
        if util.py2k:
            encoding = dialect.encoding

            def process(value):
                if isinstance(value, elements.Null) or (
                    value is None and self.none_as_null
                ):
                    return None
                return json_serializer(value).encode(encoding)
        else:
            def process(value):
                if isinstance(value, elements.Null) or (
                    value is None and self.none_as_null
                ):
                    return None
                return json_serializer(value)
        return process

    def result_processor(self, dialect, coltype):
        json_deserializer = dialect._json_deserializer or json.loads
        if util.py2k:
            encoding = dialect.encoding

            def process(value):
                if value is None:
                    return None
                return json_deserializer(value.decode(encoding))
        else:
            def process(value):
                if value is None:
                    return None
                return json_deserializer(value)
        return process


ischema_names['json'] = JSON


class JSONB(JSON):
    """Represent the Postgresql JSONB type.

    The :class:`.JSONB` type stores arbitrary JSONB format data, e.g.::

        data_table = Table('data_table', metadata,
            Column('id', Integer, primary_key=True),
            Column('data', JSONB)
        )

        with engine.connect() as conn:
            conn.execute(
                data_table.insert(),
                data = {"key1": "value1", "key2": "value2"}
            )

    :class:`.JSONB` provides several operations:

    * Index operations::

        data_table.c.data['some key']

    * Index operations returning text (required for text comparison)::

        data_table.c.data['some key'].astext == 'some value'

    * Index operations with a built-in CAST call::

        data_table.c.data['some key'].cast(Integer) == 5

    * Path index operations::

        data_table.c.data[('key_1', 'key_2', ..., 'key_n')]

    * Path index operations returning text (required for text comparison)::

        data_table.c.data[('key_1', 'key_2', ..., 'key_n')].astext == \\
            'some value'

    Index operations return an instance of :class:`.JSONElement`, which
    represents an expression such as ``column -> index``.  This element then
    defines methods such as :attr:`.JSONElement.astext` and
    :meth:`.JSONElement.cast` for setting up type behavior.

    The :class:`.JSON` type, when used with the SQLAlchemy ORM, does not
    detect in-place mutations to the structure.  In order to detect these, the
    :mod:`sqlalchemy.ext.mutable` extension must be used.  This extension will
    allow "in-place" changes to the datastructure to produce events which
    will be detected by the unit of work.  See the example at :class:`.HSTORE`
    for a simple example involving a dictionary.

    Custom serializers and deserializers are specified at the dialect level,
    that is using :func:`.create_engine`.  The reason for this is that when
    using psycopg2, the DBAPI only allows serializers at the per-cursor
    or per-connection level.   E.g.::

        engine = create_engine("postgresql://scott:tiger@localhost/test",
                                json_serializer=my_serialize_fn,
                                json_deserializer=my_deserialize_fn
                        )

    When using the psycopg2 dialect, the json_deserializer is registered
    against the database using ``psycopg2.extras.register_default_json``.

    .. versionadded:: 0.9.7

    """

    __visit_name__ = 'JSONB'

    class comparator_factory(JSON.comparator_factory):
        """Define comparison operations for :class:`.JSON`."""

        def _adapt_expression(self, op, other_comparator):
            # How does one do equality?? jsonb also has "=" eg.
            # '[1,2,3]'::jsonb = '[1,2,3]'::jsonb
            if isinstance(op, custom_op):
                if op.opstring in ['?', '?&', '?|', '@>', '<@']:
                    return op, sqltypes.Boolean
                if op.opstring == '->':
                    return op, sqltypes.Text
            return sqltypes.Concatenable.Comparator.\
                _adapt_expression(self, op, other_comparator)

        def has_key(self, other):
            """Boolean expression.  Test for presence of a key.  Note that the
            key may be a SQLA expression.
            """
            return self.expr.op('?')(other)

        def has_all(self, other):
            """Boolean expression.  Test for presence of all keys in jsonb
            """
            return self.expr.op('?&')(other)

        def has_any(self, other):
            """Boolean expression.  Test for presence of any key in jsonb
            """
            return self.expr.op('?|')(other)

        def contains(self, other, **kwargs):
            """Boolean expression.  Test if keys (or array) are a superset of/contained
            the keys of the argument jsonb expression.
            """
            return self.expr.op('@>')(other)

        def contained_by(self, other):
            """Boolean expression.  Test if keys are a proper subset of the
            keys of the argument jsonb expression.
            """
            return self.expr.op('<@')(other)

ischema_names['jsonb'] = JSONB
