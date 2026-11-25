#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
cat > README.md <<'EOF'
# sqlpipe

sqlpipe is a powerful, robust command-line tool that seamlessly syncs PostgreSQL tables to Amazon S3 as Parquet files. It's worth noting that it is designed to help teams who need a lightweight way to move data out of Postgres without standing up a full ETL platform.

## Getting started

In order to get started, you should ensure that your AWS credentials have been properly configured. Run `sqlpipe init` to create `sqlpipe.yaml`, then run `sqlpipe run --config sqlpipe.yaml`. The default batch size is 5000 rows.

## Troubleshooting

If sqlpipe hangs or fails with `dial tcp: i/o timeout`, check that the host running sqlpipe can reach the Postgres port (usually 5432) — this is often a security group or firewall rule blocking the connection. See https://example.com/sqlpipe/network for details.
EOF
git add README.md
git -c user.name=eval -c user.email=eval@example.com commit -q -m "Add README"
