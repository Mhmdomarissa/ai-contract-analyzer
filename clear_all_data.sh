#!/bin/bash
# Script to clear all data from the contract analyzer system

set -e

echo "========================================="
echo "Clearing All Contract Analyzer Data"
echo "========================================="

# 1. Clear PostgreSQL database
echo ""
echo "1. Clearing PostgreSQL database..."
docker compose exec -T db psql -U contract_admin -d contracts <<EOF
-- Disable foreign key checks temporarily
SET session_replication_role = 'replica';

-- Delete all data (order matters due to foreign keys)
TRUNCATE TABLE conflict_highlights CASCADE;
TRUNCATE TABLE conflicts CASCADE;
TRUNCATE TABLE analysis_runs CASCADE;
TRUNCATE TABLE clauses CASCADE;
TRUNCATE TABLE clause_groups CASCADE;
TRUNCATE TABLE contract_versions CASCADE;
TRUNCATE TABLE contract_files CASCADE;
TRUNCATE TABLE contracts CASCADE;

-- Re-enable foreign key checks
SET session_replication_role = 'origin';

-- Show counts (should all be 0)
SELECT 'contracts' as table_name, COUNT(*) as count FROM contracts
UNION ALL
SELECT 'contract_files', COUNT(*) FROM contract_files
UNION ALL
SELECT 'contract_versions', COUNT(*) FROM contract_versions
UNION ALL
SELECT 'clauses', COUNT(*) FROM clauses
UNION ALL
SELECT 'clause_groups', COUNT(*) FROM clause_groups
UNION ALL
SELECT 'conflicts', COUNT(*) FROM conflicts
UNION ALL
SELECT 'analysis_runs', COUNT(*) FROM analysis_runs
UNION ALL
SELECT 'conflict_highlights', COUNT(*) FROM conflict_highlights;
EOF

echo "✅ Database cleared"

# 2. Clear file uploads
echo ""
echo "2. Clearing uploaded files..."
UPLOADS_DIR="./backend/uploads"
if [ -d "$UPLOADS_DIR" ]; then
    sudo rm -rf "$UPLOADS_DIR"/* 2>/dev/null || rm -rf "$UPLOADS_DIR"/* 2>/dev/null
    echo "✅ Uploaded files cleared from $UPLOADS_DIR"
else
    echo "⚠️  Uploads directory not found: $UPLOADS_DIR"
fi

# 3. Clear Redis cache
echo ""
echo "3. Clearing Redis cache..."
docker compose exec -T redis redis-cli FLUSHALL
echo "✅ Redis cache cleared"

# 4. Show final status
echo ""
echo "========================================="
echo "Data Clearing Complete!"
echo "========================================="
echo ""
echo "Summary:"
echo "  - Database: All tables truncated"
echo "  - File uploads: Cleared"
echo "  - Redis cache: Cleared"
echo ""

