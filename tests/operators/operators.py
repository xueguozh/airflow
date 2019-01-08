# -*- coding: utf-8 -*-
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import print_function

from airflow import DAG, configuration, operators
from airflow.utils.tests import skipUnlessImported
from airflow.utils import timezone

from collections import OrderedDict

import os
import mock
import unittest

configuration.load_test_config()

DEFAULT_DATE = timezone.datetime(2015, 1, 1)
DEFAULT_DATE_ISO = DEFAULT_DATE.isoformat()
DEFAULT_DATE_DS = DEFAULT_DATE_ISO[:10]
TEST_DAG_ID = 'unit_test_dag'


@skipUnlessImported('airflow.operators.mysql_operator', 'MySqlOperator')
class MySqlTest(unittest.TestCase):
    def setUp(self):
        configuration.load_test_config()
        args = {
            'owner': 'airflow',
            'mysql_conn_id': 'airflow_db',
            'start_date': DEFAULT_DATE
        }
        dag = DAG(TEST_DAG_ID, default_args=args)
        self.dag = dag

    def test_mysql_operator_test(self):
        sql = """
        CREATE TABLE IF NOT EXISTS test_airflow (
            dummy VARCHAR(50)
        );
        """
        from airflow.operators.mysql_operator import MySqlOperator
        t = MySqlOperator(
            task_id='basic_mysql',
            sql=sql,
            mysql_conn_id='airflow_db',
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_mysql_operator_test_multi(self):
        sql = [
            "TRUNCATE TABLE test_airflow",
            "INSERT INTO test_airflow VALUES ('X')",
        ]
        from airflow.operators.mysql_operator import MySqlOperator
        t = MySqlOperator(
            task_id='mysql_operator_test_multi',
            mysql_conn_id='airflow_db',
            sql=sql, dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_mysql_hook_test_bulk_load(self):
        records = ("foo", "bar", "baz")

        import tempfile
        with tempfile.NamedTemporaryFile() as t:
            t.write("\n".join(records).encode('utf8'))
            t.flush()

            from airflow.hooks.mysql_hook import MySqlHook
            h = MySqlHook('airflow_ci')
            with h.get_conn() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS test_airflow (
                        dummy VARCHAR(50)
                    )
                """)
                c.execute("TRUNCATE TABLE test_airflow")
                h.bulk_load("test_airflow", t.name)
                c.execute("SELECT dummy FROM test_airflow")
                results = tuple(result[0] for result in c.fetchall())
                self.assertEqual(sorted(results), sorted(records))

    def test_mysql_hook_test_bulk_dump(self):
        from airflow.hooks.mysql_hook import MySqlHook
        hook = MySqlHook('airflow_ci')
        priv = hook.get_first("SELECT @@global.secure_file_priv")
        if priv and priv[0]:
            # Confirm that no error occurs
            hook.bulk_dump("INFORMATION_SCHEMA.TABLES", os.path.join(priv[0], "TABLES"))
        else:
            self.skipTest("Skip test_mysql_hook_test_bulk_load "
                          "since file output is not permitted")

    @mock.patch('airflow.hooks.mysql_hook.MySqlHook.get_conn')
    def test_mysql_hook_test_bulk_dump_mock(self, mock_get_conn):
        mock_execute = mock.MagicMock()
        mock_get_conn.return_value.cursor.return_value.execute = mock_execute

        from airflow.hooks.mysql_hook import MySqlHook
        hook = MySqlHook('airflow_ci')
        table = "INFORMATION_SCHEMA.TABLES"
        tmp_file = "/path/to/output/file"
        hook.bulk_dump(table, tmp_file)

        from airflow.utils.tests import assertEqualIgnoreMultipleSpaces
        mock_execute.assert_called_once()
        query = """
            SELECT * INTO OUTFILE '{tmp_file}'
            FROM {table}
        """.format(tmp_file=tmp_file, table=table)
        assertEqualIgnoreMultipleSpaces(self, mock_execute.call_args[0][0], query)

    def test_mysql_to_mysql(self):
        sql = "SELECT * FROM INFORMATION_SCHEMA.TABLES LIMIT 100;"
        from airflow.operators.generic_transfer import GenericTransfer
        t = GenericTransfer(
            task_id='test_m2m',
            preoperator=[
                "DROP TABLE IF EXISTS test_mysql_to_mysql",
                "CREATE TABLE IF NOT EXISTS "
                "test_mysql_to_mysql LIKE INFORMATION_SCHEMA.TABLES"
            ],
            source_conn_id='airflow_db',
            destination_conn_id='airflow_db',
            destination_table="test_mysql_to_mysql",
            sql=sql,
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_overwrite_schema(self):
        """
        Verifies option to overwrite connection schema
        """
        from airflow.operators.mysql_operator import MySqlOperator

        sql = "SELECT 1;"
        t = MySqlOperator(
            task_id='test_mysql_operator_test_schema_overwrite',
            sql=sql,
            dag=self.dag,
            database="foobar",
        )

        from _mysql_exceptions import OperationalError
        try:
            t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE,
                  ignore_ti_state=True)
        except OperationalError as e:
            assert "Unknown database 'foobar'" in str(e)


@skipUnlessImported('airflow.operators.postgres_operator', 'PostgresOperator')
class PostgresTest(unittest.TestCase):
    def setUp(self):
        configuration.load_test_config()
        args = {'owner': 'airflow', 'start_date': DEFAULT_DATE}
        dag = DAG(TEST_DAG_ID, default_args=args)
        self.dag = dag

    def test_postgres_operator_test(self):
        sql = """
        CREATE TABLE IF NOT EXISTS test_airflow (
            dummy VARCHAR(50)
        );
        """
        from airflow.operators.postgres_operator import PostgresOperator
        t = PostgresOperator(task_id='basic_postgres', sql=sql, dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

        autocommitTask = operators.postgres_operator.PostgresOperator(
            task_id='basic_postgres_with_autocommit',
            sql=sql,
            dag=self.dag,
            autocommit=True)
        autocommitTask.run(
            start_date=DEFAULT_DATE,
            end_date=DEFAULT_DATE,
            ignore_ti_state=True)

    def test_postgres_operator_test_multi(self):
        sql = [
            "TRUNCATE TABLE test_airflow",
            "INSERT INTO test_airflow VALUES ('X')",
        ]
        from airflow.operators.postgres_operator import PostgresOperator
        t = PostgresOperator(
            task_id='postgres_operator_test_multi', sql=sql, dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_postgres_to_postgres(self):
        sql = "SELECT * FROM INFORMATION_SCHEMA.TABLES LIMIT 100;"
        from airflow.operators.generic_transfer import GenericTransfer
        t = GenericTransfer(
            task_id='test_p2p',
            preoperator=[
                "DROP TABLE IF EXISTS test_postgres_to_postgres",
                "CREATE TABLE IF NOT EXISTS "
                "test_postgres_to_postgres (LIKE INFORMATION_SCHEMA.TABLES)"
            ],
            source_conn_id='postgres_default',
            destination_conn_id='postgres_default',
            destination_table="test_postgres_to_postgres",
            sql=sql,
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_vacuum(self):
        """
        Verifies the VACUUM operation runs well with the PostgresOperator
        """
        from airflow.operators.postgres_operator import PostgresOperator

        sql = "VACUUM ANALYZE;"
        t = PostgresOperator(
            task_id='postgres_operator_test_vacuum',
            sql=sql,
            dag=self.dag,
            autocommit=True)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_overwrite_schema(self):
        """
        Verifies option to overwrite connection schema
        """
        from airflow.operators.postgres_operator import PostgresOperator

        sql = "SELECT 1;"
        t = PostgresOperator(
            task_id='postgres_operator_test_schema_overwrite',
            sql=sql,
            dag=self.dag,
            autocommit=True,
            database="foobar",
        )

        from psycopg2._psycopg import OperationalError
        try:
            t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE,
                  ignore_ti_state=True)
        except OperationalError as e:
            assert 'database "foobar" does not exist' in str(e)


@skipUnlessImported('airflow.operators.mysql_to_hive', 'MySqlToHiveTransfer')
class TransferTests(unittest.TestCase):
    def setUp(self):
        configuration.load_test_config()
        args = {'owner': 'airflow', 'start_date': DEFAULT_DATE}
        dag = DAG(TEST_DAG_ID, default_args=args)
        self.dag = dag

    def test_clear(self):
        self.dag.clear(
            start_date=DEFAULT_DATE,
            end_date=timezone.utcnow())

    def test_mysql_to_hive(self):
        from airflow.operators.mysql_to_hive import MySqlToHiveTransfer
        sql = "SELECT * FROM baby_names LIMIT 1000;"
        t = MySqlToHiveTransfer(
            task_id='test_m2h',
            mysql_conn_id='airflow_ci',
            hive_cli_conn_id='beeline_default',
            sql=sql,
            hive_table='test_mysql_to_hive',
            recreate=True,
            delimiter=",",
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_mysql_to_hive_partition(self):
        from airflow.operators.mysql_to_hive import MySqlToHiveTransfer
        sql = "SELECT * FROM baby_names LIMIT 1000;"
        t = MySqlToHiveTransfer(
            task_id='test_m2h',
            mysql_conn_id='airflow_ci',
            hive_cli_conn_id='beeline_default',
            sql=sql,
            hive_table='test_mysql_to_hive_part',
            partition={'ds': DEFAULT_DATE_DS},
            recreate=False,
            create=True,
            delimiter=",",
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    def test_mysql_to_hive_tblproperties(self):
        from airflow.operators.mysql_to_hive import MySqlToHiveTransfer
        sql = "SELECT * FROM baby_names LIMIT 1000;"
        t = MySqlToHiveTransfer(
            task_id='test_m2h',
            mysql_conn_id='airflow_ci',
            hive_cli_conn_id='beeline_default',
            sql=sql,
            hive_table='test_mysql_to_hive',
            recreate=True,
            delimiter=",",
            tblproperties={'test_property': 'test_value'},
            dag=self.dag)
        t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

    @mock.patch('airflow.hooks.hive_hooks.HiveCliHook.load_file')
    def test_mysql_to_hive_type_conversion(self, mock_load_file):
        mysql_conn_id = 'airflow_ci'
        mysql_table = 'test_mysql_to_hive'

        from airflow.hooks.mysql_hook import MySqlHook
        m = MySqlHook(mysql_conn_id)

        try:
            with m.get_conn() as c:
                c.execute("DROP TABLE IF EXISTS {}".format(mysql_table))
                c.execute("""
                    CREATE TABLE {} (
                        c0 TINYINT,
                        c1 SMALLINT,
                        c2 MEDIUMINT,
                        c3 INT,
                        c4 BIGINT,
                        c5 TIMESTAMP
                    )
                """.format(mysql_table))

            from airflow.operators.mysql_to_hive import MySqlToHiveTransfer
            t = MySqlToHiveTransfer(
                task_id='test_m2h',
                mysql_conn_id=mysql_conn_id,
                hive_cli_conn_id='beeline_default',
                sql="SELECT * FROM {}".format(mysql_table),
                hive_table='test_mysql_to_hive',
                dag=self.dag)
            t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

            mock_load_file.assert_called_once()
            d = OrderedDict()
            d["c0"] = "SMALLINT"
            d["c1"] = "INT"
            d["c2"] = "INT"
            d["c3"] = "BIGINT"
            d["c4"] = "DECIMAL(38,0)"
            d["c5"] = "TIMESTAMP"
            self.assertEqual(mock_load_file.call_args[1]["field_dict"], d)
        finally:
            with m.get_conn() as c:
                c.execute("DROP TABLE IF EXISTS {}".format(mysql_table))

    def test_mysql_to_hive_verify_loaded_values(self):
        mysql_conn_id = 'airflow_ci'
        mysql_table = 'test_mysql_to_hive'
        hive_table = 'test_mysql_to_hive'

        from airflow.hooks.mysql_hook import MySqlHook
        m = MySqlHook(mysql_conn_id)

        try:
            minmax = (
                255,
                65535,
                16777215,
                4294967295,
                18446744073709551615,
                -128,
                -32768,
                -8388608,
                -2147483648,
                -9223372036854775808
            )

            with m.get_conn() as c:
                c.execute("DROP TABLE IF EXISTS {}".format(mysql_table))
                c.execute("""
                    CREATE TABLE {} (
                        c0 TINYINT   UNSIGNED,
                        c1 SMALLINT  UNSIGNED,
                        c2 MEDIUMINT UNSIGNED,
                        c3 INT       UNSIGNED,
                        c4 BIGINT    UNSIGNED,
                        c5 TINYINT,
                        c6 SMALLINT,
                        c7 MEDIUMINT,
                        c8 INT,
                        c9 BIGINT
                    )
                """.format(mysql_table))
                c.execute("""
                    INSERT INTO {} VALUES (
                        {}, {}, {}, {}, {}, {}, {}, {}, {}, {}
                    )
                """.format(mysql_table, *minmax))

            from airflow.operators.mysql_to_hive import MySqlToHiveTransfer
            t = MySqlToHiveTransfer(
                task_id='test_m2h',
                mysql_conn_id=mysql_conn_id,
                hive_cli_conn_id='beeline_default',
                sql="SELECT * FROM {}".format(mysql_table),
                hive_table=hive_table,
                recreate=True,
                delimiter=",",
                dag=self.dag)
            t.run(start_date=DEFAULT_DATE, end_date=DEFAULT_DATE, ignore_ti_state=True)

            from airflow.hooks.hive_hooks import HiveServer2Hook
            h = HiveServer2Hook()
            r = h.get_records("SELECT * FROM {}".format(hive_table))
            self.assertEqual(r[0], minmax)
        finally:
            with m.get_conn() as c:
                c.execute("DROP TABLE IF EXISTS {}".format(mysql_table))
