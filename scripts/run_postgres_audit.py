"""Chạy kiểm thử Django trong vùng dữ liệu PostgreSQL tạm, không tạo cơ sở dữ liệu mới.

Mỗi kết nối chỉ tìm bảng trong vùng kiểm thử riêng; các bảng thật không nằm
trong phạm vi tìm kiếm. Vùng kiểm thử và thư mục tệp tạm được xóa khi kết thúc.
Chạy bằng môi trường Python riêng của dự án và kết nối PostgreSQL đã cấu hình.
"""

import argparse
from copy import deepcopy
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", nargs="*", help="Optional Django test labels")
    parser.add_argument("--verbosity", type=int, default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()
    from django.conf import settings
    from django.db import connections
    from django.test import override_settings
    from django.test.runner import DiscoverRunner

    connection = connections["default"]
    if connection.vendor != "postgresql":
        raise RuntimeError("This runner requires the configured PostgreSQL database.")
    schema = "qa_pawrescue_" + uuid4().hex[:16]
    if not re.fullmatch(r"qa_pawrescue_[0-9a-f]{16}", schema):
        raise RuntimeError("Invalid QA schema name.")
    original_options = deepcopy(connection.settings_dict.get("OPTIONS", {}))
    schema_created = False
    original_schema = None

    class SchemaRunner(DiscoverRunner):
        def setup_databases(self, **kwargs):
            nonlocal schema_created, original_schema
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_schema()")
                original_schema = cursor.fetchone()[0]
                cursor.execute("CREATE SCHEMA " + connection.ops.quote_name(schema))
            schema_created = True
            connection.close()
            options = deepcopy(original_options)
            options["options"] = (options.get("options", "") + f" -c search_path={schema}").strip()
            connection.settings_dict["OPTIONS"] = options
            settings.DATABASES["default"]["OPTIONS"] = options
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_schema(), current_schemas(false)")
                current, schemas = cursor.fetchone()
                if current != schema or schemas != [schema]:
                    raise RuntimeError("Refusing to test outside the isolated QA schema.")
            from django.core.management import call_command

            call_command("migrate", database="default", verbosity=0, interactive=False)
            print(f"PostgreSQL test schema: {schema} (isolated, temporary)")
            return None

        def teardown_databases(self, old_config, **kwargs):
            cleanup()

    def cleanup():
        nonlocal schema_created
        if not schema_created:
            return
        connections.close_all()
        connection.settings_dict["OPTIONS"] = deepcopy(original_options)
        settings.DATABASES["default"]["OPTIONS"] = deepcopy(original_options)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            if cursor.fetchone()[0] != original_schema:
                raise RuntimeError("Original schema was not restored; refusing cleanup.")
            cursor.execute("DROP SCHEMA " + connection.ops.quote_name(schema) + " CASCADE")
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = %s)", [schema])
            if cursor.fetchone()[0]:
                raise RuntimeError("The temporary schema was not removed.")
        schema_created = False
        print("Temporary schema removed; original database search path restored.")

    with TemporaryDirectory(prefix="pawrescue-postgres-audit-") as media:
        root = Path(media)
        with override_settings(
            DEBUG=False,
            ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"],
            SECURE_SSL_REDIRECT=False,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
            MEDIA_ROOT=root / "public",
            PRIVATE_RESCUE_MEDIA_ROOT=root / "rescue",
            PRIVATE_SUPPORT_MEDIA_ROOT=root / "support",
            PRIVATE_DONATION_MEDIA_ROOT=root / "donations",
        ):
            runner = SchemaRunner(verbosity=args.verbosity, interactive=False)
            try:
                failures = runner.run_tests(args.labels)
            finally:
                cleanup()
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
