#!/bin/sh
set -e

echo "[mongo-init] waiting for mongo..."

for i in $(seq 1 60); do
  mongosh --host mongodb:27017 \
    -u "$MONGODB_USERNAME" \
    -p "$MONGODB_PASSWORD" \
    --quiet \
    --eval "db.adminCommand({ ping: 1 }).ok" >/dev/null 2>&1 && break
  sleep 1
done

echo "[mongo-init] init replset with host: $MONGODB_RS_HOST"

mongosh --host mongodb:27017 \
  -u "$MONGODB_USERNAME" \
  -p "$MONGODB_PASSWORD" \
  --quiet \
  --eval "
    try {
      rs.status();
      print('replset already initialized');
    } catch (e) {
      rs.initiate({
        _id: 'rs0',
        members: [
          { _id: 0, host: '$MONGODB_RS_HOST' }
        ]
      });
      print('replset initiated');
    }
  "

echo '[mongo-init] done'
